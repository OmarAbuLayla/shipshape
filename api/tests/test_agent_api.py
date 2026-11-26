"""The agent behind the API: background run, live steps, stored result, downloads."""

from __future__ import annotations

import io
import json
import time
import zipfile
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from shipshape.llm.client import ToolCall, ToolTurn

from shipshape_api.app import create_app
from shipshape_api.jobs import LLMConnection

LINT = "def collect(item, bucket=[]):\n    bucket.append(item)\n    return bucket\n"
FIXED = (
    "def collect(item, bucket=None):\n"
    "    if bucket is None:\n"
    "        bucket = []\n"
    "    bucket.append(item)\n"
    "    return bucket\n"
)


def _call(name: str, **arguments: Any) -> ToolCall:
    return ToolCall(f"call-{name}", name, json.dumps(arguments))


class ScriptedAgentModel:
    """Fixes the mutable default, then finishes; can be told to fail instead."""

    model = "fake-agent"

    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.turns = [
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

    def complete_tools(
        self, messages: Sequence[dict[str, Any]], tools: Sequence[dict[str, Any]]
    ) -> ToolTurn:
        if self.fail:
            from shipshape.llm.client import LLMError

            raise LLMError("Rate limited. Try again in a moment.")
        return ToolTurn("", tuple(self.turns.pop(0)), 100, 0, 20)


def _app(tmp_path: Path, model: ScriptedAgentModel) -> TestClient:
    app = create_app(
        data_dir=tmp_path / "data",
        client_factory=lambda: LLMConnection(None, "deepseek"),  # type: ignore[arg-type]
        web_dist=tmp_path / "no-dist",
        tool_client_factory=lambda: model,
    )
    return TestClient(app)


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    root.mkdir()
    (root / "lib.py").write_text(LINT, encoding="utf-8")
    return root


@pytest.fixture
def keyed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "fake-key-for-tests-only-0000")
    monkeypatch.setenv("SHIPSHAPE_CACHE_DIR", str(tmp_path / "cache"))
    yield


def _scan(client: TestClient, root: Path) -> str:
    scan_id = str(client.post("/api/scans", json={"path": str(root)}).json()["id"])
    for _ in range(600):
        if client.get(f"/api/scans/{scan_id}").json()["status"] == "done":
            return scan_id
        time.sleep(0.05)
    raise AssertionError("scan did not finish")


def _wait_agent(client: TestClient, scan_id: str) -> dict[str, Any]:
    for _ in range(600):
        state: dict[str, Any] = client.get(f"/api/scans/{scan_id}/agent").json()
        if state["status"] != "running":
            return state
        time.sleep(0.05)
    raise AssertionError("agent did not finish")


def test_agent_runs_in_the_background_and_keeps_the_result(
    tmp_path: Path, project: Path, keyed: None
) -> None:
    with _app(tmp_path, ScriptedAgentModel()) as client:
        scan_id = _scan(client, project)
        assert client.get(f"/api/scans/{scan_id}/agent").status_code == 404
        started = client.post(f"/api/scans/{scan_id}/agent", json={"max_steps": 10})
        assert started.status_code == 202
        assert started.json()["status"] == "running"
        state = _wait_agent(client, scan_id)

        assert state["status"] == "done", state["error"]
        assert [s["tool"] for s in state["steps"]] == ["read_file", "propose_fix", "finish"]
        assert state["run"]["summary"] == "Fixed the shared default list."
        assert state["run"]["fixes_applied"] == ["lint.mutable-default: default to None"]
        assert state["zip_available"] is True
        assert (project / "lib.py").read_text(encoding="utf-8") == LINT

        patch = client.get(f"/api/scans/{scan_id}/agent/download", params={"format": "patch"})
        assert "bucket is None" in patch.text
        archive = client.get(f"/api/scans/{scan_id}/agent/download", params={"format": "zip"})
        with zipfile.ZipFile(io.BytesIO(archive.content)) as zf:
            assert "project-fixed/lib.py" in zf.namelist()

    # The finished run survives a restart (it is stored with the scan).
    with _app(tmp_path, ScriptedAgentModel()) as client:
        again = client.get(f"/api/scans/{scan_id}/agent").json()
        assert again["status"] == "done"
        assert again["run"]["after_grade"]


def test_agent_failure_is_reported_not_stuck(tmp_path: Path, project: Path, keyed: None) -> None:
    with _app(tmp_path, ScriptedAgentModel(fail=True)) as client:
        scan_id = _scan(client, project)
        client.post(f"/api/scans/{scan_id}/agent", json={})
        state = _wait_agent(client, scan_id)
        assert state["status"] == "failed"
        assert "Rate limited" in state["error"]


def test_agent_needs_a_key_and_a_known_scan(
    tmp_path: Path, project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for var in ("DEEPSEEK_API_KEY", "SHIPSHAPE_LLM_PROVIDER"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.chdir(tmp_path)  # no .env above a temporary folder
    with _app(tmp_path, ScriptedAgentModel()) as client:
        assert client.post("/api/scans/nope/agent", json={}).status_code == 404
        scan_id = _scan(client, project)
        response = client.post(f"/api/scans/{scan_id}/agent", json={})
        assert response.status_code == 409
        assert "LLM key" in response.json()["detail"]
