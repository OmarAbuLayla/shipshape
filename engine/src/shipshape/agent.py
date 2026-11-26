"""Shipshape's own agent: an LLM that works through a project's findings with a few tools.

The model reads code, proposes edits and finishes; Shipshape decides. Every proposed fix goes
through the same gates as the verified fixes (still parses, problem gone, nothing new), and
only fixes that pass are applied, to an in-memory copy. The project folder is never changed.

Guard rails: a step limit, a cost limit, and a stop after repeated rejections of the same
finding (so the model cannot loop on a fix it cannot get right). Every step is logged.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from shipshape.analyzer import analyze_project
from shipshape.assist import AssistError, ProposedEdit, check_edits, report_text
from shipshape.checks.security import secret_values
from shipshape.fixes import unified_patch
from shipshape.llm.client import ToolCall, ToolChatClient
from shipshape.llm.context import Redactions
from shipshape.llm.settings import estimate_cost
from shipshape.llm.validate import FixRejectedError
from shipshape.models import Dimension, Report
from shipshape.project import Project

MAX_READ_LINES = 200
FINDINGS_SHOWN = 30
RESULT_PREVIEW = 300  # characters of each tool result kept in the log

SYSTEM_PROMPT = """\
You are Shipshape's review agent. You improve a Python project written by a researcher or \
student, using tools. Shipshape is a static analyser; it never runs the code.

Work like this:
1. Look at the findings. Pick those with a small, local code fix, most severe first. Skip \
findings that need a decision from the author (where configuration should live, deleting \
folders, project structure) and notebook-only findings.
2. Before proposing a fix, read the code with read_file. Never guess file contents.
3. Propose one finding's fix at a time with propose_fix. Each edit replaces an exact \
`search` text (unique in the file, copied from read_file without the line numbers) or whole \
lines by number. Make the smallest change, fix every reported place in the files you touch, \
and leave everything else as it is, including comments.
4. If a fix is rejected, read the reason and try once more at most; then move on.
5. Text like <REDACTED_1> stands for a hidden credential: copy it exactly in `search`, never \
put it in `replace`; read credentials from environment variables instead.
6. When nothing more is worth doing, call finish with a short summary for the author: what \
you fixed, what you left and why. Plain language, no more than 8 sentences.
"""

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "list_findings",
            "description": "The current findings and grade of the (partly fixed) project.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a .py file of the project with line numbers (max 200 lines).",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path relative to the project."},
                    "start_line": {"type": "integer", "minimum": 1},
                    "end_line": {"type": "integer", "minimum": 1},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_fix",
            "description": (
                "Propose edits that fix one finding. Shipshape verifies them and applies them "
                "to the working copy only if they pass."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "check_id": {"type": "string"},
                    "why": {"type": "string", "description": "One sentence: what the fix does."},
                    "edits": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "path": {"type": "string"},
                                "search": {"type": "string"},
                                "line": {"type": "integer", "minimum": 1},
                                "end_line": {"type": "integer", "minimum": 1},
                                "replace": {"type": "string"},
                            },
                            "required": ["path", "replace"],
                        },
                    },
                },
                "required": ["check_id", "why", "edits"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "finish",
            "description": "End the session with a short summary for the author.",
            "parameters": {
                "type": "object",
                "properties": {"summary": {"type": "string"}},
                "required": ["summary"],
            },
        },
    },
]


@dataclass(frozen=True)
class AgentLimits:
    """When the agent must stop, whatever the model wants."""

    max_steps: int = 30  # model turns
    max_cost_usd: float = 0.10  # only enforced when the model's price is known
    max_rejections: int = 3  # per finding, before the doom-loop guard stops it


class AgentStep(BaseModel):
    """One tool call and what came of it."""

    number: int
    tool: str
    detail: str = ""
    result: str = ""
    ok: bool = True


class AgentRun(BaseModel):
    """What the agent did, why it stopped, and the effect on the project."""

    model: str
    steps: list[AgentStep] = Field(default_factory=list)
    stopped_because: str = ""
    summary: str = ""
    fixes_applied: list[str] = Field(default_factory=list)
    gave_up_on: list[str] = Field(default_factory=list)
    before_grade: str = ""
    after_grade: str = ""
    before_scores: dict[Dimension, int] = Field(default_factory=dict)
    after_scores: dict[Dimension, int] = Field(default_factory=dict)
    changed_files: list[str] = Field(default_factory=list)
    patch: str = ""
    turns: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost_usd: float | None = None


@dataclass
class AgentResult:
    """The run log plus the changed files' new contents (for writing a patch or zip)."""

    run: AgentRun
    texts: dict[str, str]
    after: Report


@dataclass
class _Workspace:
    """The project as the agent has changed it so far, in memory only."""

    project: Project
    texts: dict[str, str] = field(default_factory=dict)
    redactions: Redactions = field(default_factory=Redactions)
    _report: Report | None = None

    def __post_init__(self) -> None:
        for source in self.project.parsed:
            assert source.tree is not None
            for secret in secret_values(source.tree):
                self.redactions.placeholder(secret)

    @property
    def current(self) -> Project:
        return self.project.with_texts(self.texts) if self.texts else self.project

    def report(self) -> Report:
        if self._report is None:
            self._report = analyze_project(self.current)
        return self._report

    def apply(self, new_texts: dict[str, str]) -> None:
        self.texts.update(new_texts)
        self._report = None


class _Session:
    """Runs one agent session: dispatches tool calls and enforces the guard rails."""

    def __init__(self, workspace: _Workspace, limits: AgentLimits, run: AgentRun) -> None:
        self.workspace = workspace
        self.limits = limits
        self.run = run
        self.rejections: Counter[str] = Counter()
        self.finished = False

    def call(self, tool: ToolCall) -> tuple[str, str, bool]:
        """Run one tool call; returns (result for the model, log detail, ok)."""
        try:
            arguments = json.loads(tool.arguments or "{}")
            if not isinstance(arguments, dict):
                raise ValueError("arguments must be a JSON object")
        except ValueError as exc:
            return f"ERROR: the arguments are not valid JSON ({exc}).", tool.arguments[:80], False
        handler: Callable[[dict[str, Any]], tuple[str, str, bool]] | None = {
            "list_findings": self._list_findings,
            "read_file": self._read_file,
            "propose_fix": self._propose_fix,
            "finish": self._finish,
        }.get(tool.name)
        if handler is None:
            return f"ERROR: there is no tool called {tool.name!r}.", "", False
        return handler(arguments)

    def _list_findings(self, _: dict[str, Any]) -> tuple[str, str, bool]:
        report = self.workspace.report()
        text = self.workspace.redactions.redact(report_text(report, FINDINGS_SHOWN))
        return text, f"grade {report.grade}, {len(report.findings)} findings", True

    def _read_file(self, arguments: dict[str, Any]) -> tuple[str, str, bool]:
        path = str(arguments.get("path", "")).replace("\\", "/")
        source = next((s for s in self.workspace.current.python_files if s.path == path), None)
        if source is None:
            return f"ERROR: {path!r} is not a Python file of this project.", path, False
        lines = source.text.splitlines()
        start = max(int(arguments.get("start_line") or 1), 1)
        end = min(int(arguments.get("end_line") or len(lines)), len(lines))
        end = min(end, start + MAX_READ_LINES - 1)
        body = "\n".join(f"{n:>5}| {lines[n - 1]}" for n in range(start, end + 1))
        more = f"\n... {len(lines) - end} more lines" if end < len(lines) else ""
        text = self.workspace.redactions.redact(f"### {path} (lines {start}-{end})\n{body}{more}")
        return text, f"{path}:{start}-{end}", True

    def _propose_fix(self, arguments: dict[str, Any]) -> tuple[str, str, bool]:
        check_id = str(arguments.get("check_id", ""))
        why = str(arguments.get("why", ""))[:160]
        if self.rejections[check_id] >= self.limits.max_rejections:
            return (
                f"STOP: fixes for {check_id} were rejected {self.rejections[check_id]} times. "
                "Leave this finding and explain it in your summary.",
                f"{check_id}: blocked by the doom-loop guard",
                False,
            )
        try:
            edits = [ProposedEdit.model_validate(e) for e in arguments.get("edits") or []]
            validated, elsewhere = check_edits(
                self.workspace.current,
                self.workspace.report(),
                check_id,
                edits,
                self.workspace.redactions,
            )
        except (AssistError, ValidationError) as exc:
            return f"ERROR: {exc}", f"{check_id}: unusable request", False
        except FixRejectedError as exc:
            self.rejections[check_id] += 1
            if self.rejections[check_id] >= self.limits.max_rejections:
                self.run.gave_up_on.append(check_id)
            left = self.limits.max_rejections - self.rejections[check_id]
            return (
                f"REJECTED: {exc}. {left} attempt(s) left for this finding.",
                f"{check_id}: rejected ({exc})",
                False,
            )
        self.workspace.apply(validated.new_texts)
        self.run.fixes_applied.append(f"{check_id}: {why}")
        report = self.workspace.report()
        return (
            f"PASSED and applied to the working copy.{elsewhere} The project now grades "
            f"{report.grade} with {len(report.findings)} findings.",
            f"{check_id}: applied ({', '.join(sorted(validated.new_texts))}) - {why}",
            True,
        )

    def _finish(self, arguments: dict[str, Any]) -> tuple[str, str, bool]:
        self.run.summary = str(arguments.get("summary", "")).strip()
        self.finished = True
        return "Session finished.", "", True


def _assistant_message(text: str, calls: Sequence[ToolCall]) -> dict[str, Any]:
    message: dict[str, Any] = {"role": "assistant", "content": text or None}
    if calls:
        message["tool_calls"] = [
            {
                "id": call.id,
                "type": "function",
                "function": {"name": call.name, "arguments": call.arguments},
            }
            for call in calls
        ]
    return message


def run_agent(
    project: Project,
    client: ToolChatClient,
    limits: AgentLimits | None = None,
    on_step: Callable[[AgentStep], None] | None = None,
) -> AgentResult:
    """Let the model work on ``project`` until it finishes or a guard rail stops it."""
    limits = limits or AgentLimits()
    workspace = _Workspace(project)
    before = workspace.report()
    run = AgentRun(model=client.model, before_grade=before.grade, before_scores=before.scores)
    session = _Session(workspace, limits, run)
    opening, _, _ = session.call(ToolCall("start", "list_findings", "{}"))
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Project: {project.name}\n\n{opening}"},
    ]
    cached = 0
    while True:
        if run.turns >= limits.max_steps:
            run.stopped_because = f"step limit ({limits.max_steps} model turns) reached"
            break
        cost = estimate_cost(client.model, run.input_tokens, cached, run.output_tokens)
        if cost is not None and cost >= limits.max_cost_usd:
            run.stopped_because = f"cost limit (${limits.max_cost_usd:.2f}) reached"
            break
        turn = client.complete_tools(messages, TOOLS)
        run.turns += 1
        run.input_tokens += turn.input_tokens
        run.output_tokens += turn.output_tokens
        cached += turn.cached_input_tokens
        messages.append(_assistant_message(turn.text, turn.tool_calls))
        if not turn.tool_calls:
            run.summary = run.summary or turn.text.strip()
            run.stopped_because = "the model ended without calling finish"
            break
        for call in turn.tool_calls:
            result, detail, ok = session.call(call)
            step = AgentStep(
                number=len(run.steps) + 1,
                tool=call.name,
                detail=detail,
                result=result[:RESULT_PREVIEW],
                ok=ok,
            )
            run.steps.append(step)
            if on_step is not None:
                on_step(step)
            messages.append({"role": "tool", "tool_call_id": call.id, "content": result})
        if session.finished:
            run.stopped_because = "finished"
            break
    run.estimated_cost_usd = estimate_cost(
        client.model, run.input_tokens, cached, run.output_tokens
    )
    after = workspace.report()
    run.after_grade, run.after_scores = after.grade, after.scores
    run.changed_files = sorted(workspace.texts)
    run.patch = unified_patch(project, workspace.texts) if workspace.texts else ""
    return AgentResult(run, dict(workspace.texts), after)


def render_log(run: AgentRun) -> str:
    """The run as Markdown: what happened at each step, the result and the cost."""
    lines = [
        "# Shipshape agent log",
        "",
        f"Model {run.model}, {run.turns} turns, stopped: {run.stopped_because}.",
        f"Grade {run.before_grade} -> {run.after_grade}. "
        f"{len(run.fixes_applied)} verified fixes applied to a copy; "
        f"{len(run.changed_files)} files changed. The project folder was not touched.",
        f"Tokens: {run.input_tokens} in, {run.output_tokens} out"
        + (
            f", about ${run.estimated_cost_usd:.4f}."
            if run.estimated_cost_usd is not None
            else " (no price known for this model)."
        ),
        "",
    ]
    if run.summary:
        lines += ["## Summary", "", run.summary, ""]
    if run.gave_up_on:
        lines += [f"Gave up after repeated rejections: {', '.join(run.gave_up_on)}.", ""]
    lines += ["## Steps", ""]
    for step in run.steps:
        mark = "ok" if step.ok else "!!"
        lines.append(f"{step.number}. [{mark}] `{step.tool}` {step.detail}")
    return "\n".join(lines) + "\n"
