"""The agent loop with a scripted fake model: tools, verification, guard rails, log."""

from __future__ import annotations

import json
from collections.abc import Sequence
from types import SimpleNamespace
from typing import Any

import pytest
from typer.testing import CliRunner

from shipshape import cli, cli_agent
from shipshape.agent import AgentLimits, render_log, run_agent
from shipshape.llm.client import ToolCall, ToolTurn

from .conftest import MakeProject

LINT = "def collect(item, bucket=[]):\n    bucket.append(item)\n    return bucket\n"
FIXED = (
    "def collect(item, bucket=None):\n"
    "    if bucket is None:\n"
    "        bucket = []\n"
    "    bucket.append(item)\n"
    "    return bucket\n"
)
SECRET = "sk-test-not-real-0123456789abcdefABCDEF"  # shipshape: ignore[security.hardcoded-secret]


def _call(name: str, **arguments: Any) -> ToolCall:
    return ToolCall(f"call-{name}", name, json.dumps(arguments))


class ScriptedModel:
    """Plays back a fixed list of turns and records what it was shown."""

    def __init__(self, turns: list[list[ToolCall]], model: str = "fake-model") -> None:
        self.model = model
        self.turns = turns
        self.seen: list[list[dict[str, Any]]] = []

    def complete_tools(
        self, messages: Sequence[dict[str, Any]], tools: Sequence[dict[str, Any]]
    ) -> ToolTurn:
        self.seen.append(list(messages))
        calls = self.turns.pop(0) if self.turns else [_call("list_findings")]
        return ToolTurn("", tuple(calls), 1000, 0, 200)


def test_a_verified_fix_is_applied_to_the_copy_only(make_project: MakeProject) -> None:
    project = make_project({"lib.py": LINT})
    model = ScriptedModel(
        [
            [_call("read_file", path="lib.py")],
            [
                _call(
                    "propose_fix",
                    check_id="lint.mutable-default",
                    why="default to None",
                    edits=[{"path": "lib.py", "search": LINT, "replace": FIXED}],
                )
            ],
            [_call("finish", summary="Fixed the shared default list.")],
        ]
    )
    result = run_agent(project, model)
    assert result.run.stopped_because == "finished"
    assert result.texts == {"lib.py": FIXED}
    assert (project.root / "lib.py").read_text(encoding="utf-8") == LINT
    assert "lint.mutable-default" not in {f.check_id for f in result.after.findings}
    assert result.run.fixes_applied == ["lint.mutable-default: default to None"]
    assert "+    if bucket is None:" in result.run.patch
    log = render_log(result.run)
    assert "Fixed the shared default list." in log
    assert "project folder was not touched" in log


def test_repeated_rejections_trigger_the_doom_loop_guard(make_project: MakeProject) -> None:
    project = make_project({"lib.py": LINT})
    bad = _call(
        "propose_fix",
        check_id="lint.mutable-default",
        why="try",
        edits=[{"path": "lib.py", "search": "return bucket", "replace": "return list(bucket)"}],
    )
    model = ScriptedModel([[bad], [bad], [bad], [bad], [_call("finish", summary="gave up")]])
    result = run_agent(project, model, AgentLimits(max_rejections=3))
    details = [step.result for step in result.run.steps if step.tool == "propose_fix"]
    assert [d.split(":")[0] for d in details] == ["REJECTED", "REJECTED", "REJECTED", "STOP"]
    assert result.run.gave_up_on == ["lint.mutable-default"]
    assert result.texts == {}


def test_the_step_limit_stops_a_model_that_never_finishes(make_project: MakeProject) -> None:
    project = make_project({"lib.py": LINT})
    result = run_agent(project, ScriptedModel([]), AgentLimits(max_steps=4))
    assert result.run.turns == 4
    assert result.run.stopped_because.startswith("step limit")


def test_the_cost_limit_stops_the_run(make_project: MakeProject) -> None:
    project = make_project({"lib.py": LINT})

    class Expensive(ScriptedModel):
        def complete_tools(
            self, messages: Sequence[dict[str, Any]], tools: Sequence[dict[str, Any]]
        ) -> ToolTurn:
            return ToolTurn("", (_call("list_findings"),), 200_000, 0, 20_000)

    result = run_agent(project, Expensive([], model="deepseek-flash"), AgentLimits(0, 0.05))
    assert result.run.stopped_because.startswith("step limit")
    result = run_agent(project, Expensive([], model="deepseek-flash"), AgentLimits(50, 0.05))
    assert result.run.stopped_because.startswith("cost limit")
    assert result.run.turns == 1


def test_secrets_are_redacted_in_everything_the_model_reads(make_project: MakeProject) -> None:
    project = make_project({"settings.py": f'API_KEY = "{SECRET}"\n'})
    model = ScriptedModel(
        [[_call("read_file", path="settings.py")], [_call("finish", summary="done")]]
    )
    result = run_agent(project, model)
    shown = json.dumps(model.seen)
    assert SECRET not in shown
    assert "<REDACTED_1>" in shown
    assert SECRET not in render_log(result.run)


def test_secret_line_can_be_fixed_by_line_number(make_project: MakeProject) -> None:
    project = make_project({"settings.py": f'import os\n\nAPI_KEY = "{SECRET}"\n'})
    fix = _call(
        "propose_fix",
        check_id="security.hardcoded-secret",
        why="read the key from the environment",
        edits=[{"path": "settings.py", "line": 3, "replace": 'API_KEY = os.environ["API_KEY"]'}],
    )
    result = run_agent(project, ScriptedModel([[fix], [_call("finish", summary="ok")]]))
    assert result.texts == {"settings.py": 'import os\n\nAPI_KEY = os.environ["API_KEY"]\n'}


def test_broken_arguments_and_unknown_tools_are_reported_back(make_project: MakeProject) -> None:
    project = make_project({"lib.py": LINT})
    model = ScriptedModel(
        [
            [ToolCall("x", "read_file", "{not json"), ToolCall("y", "delete_everything", "{}")],
            [_call("finish", summary="done")],
        ]
    )
    result = run_agent(project, model)
    first, second = result.run.steps[:2]
    assert not first.ok and "not valid JSON" in first.result
    assert not second.ok and "no tool called" in second.result


def test_agent_command_writes_patch_and_log_outside_the_project(
    make_project: MakeProject,
    tmp_path_factory: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = make_project({"lib.py": LINT})
    out = tmp_path_factory.mktemp("out")
    model = ScriptedModel(
        [
            [
                _call(
                    "propose_fix",
                    check_id="lint.mutable-default",
                    why="default to None",
                    edits=[{"path": "lib.py", "search": LINT, "replace": FIXED}],
                )
            ],
            [_call("finish", summary="Fixed one finding.")],
        ]
    )
    monkeypatch.setattr(
        cli_agent, "load_settings", lambda: SimpleNamespace(model="fake", base_url="x")
    )
    monkeypatch.setattr(cli_agent, "OpenAICompatibleClient", lambda settings: model)
    result = CliRunner().invoke(
        cli.app,
        ["agent", str(project.root), "--patch", str(out / "a.patch"), "--log", str(out / "log.md")],
    )
    assert result.exit_code == 0, result.output
    assert "Fixed one finding." in result.output
    assert "bucket is None" in (out / "a.patch").read_text(encoding="utf-8")
    assert "Shipshape agent log" in (out / "log.md").read_text(encoding="utf-8")
    assert (project.root / "lib.py").read_text(encoding="utf-8") == LINT

    inside = CliRunner().invoke(
        cli.app, ["agent", str(project.root), "--log", str(project.root / "l.md")]
    )
    assert inside.exit_code == 2
