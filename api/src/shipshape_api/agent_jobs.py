"""Run Shipshape's agent on a finished scan in the background, with live steps for the web app.

One agent run at a time (it is a paid, multi-minute job). Steps are kept in memory while it
runs; the finished run is stored with the scan, and its fixed project is kept as a zip.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field
from shipshape.agent import AgentLimits, AgentRun, AgentStep, run_agent
from shipshape.fixes import project_zip
from shipshape.llm.client import LLMError, OpenAICompatibleClient, ToolChatClient
from shipshape.llm.settings import SettingsError, load_settings

from shipshape_api.fixes import FixUnavailableError, project_copy
from shipshape_api.store import ScanStore, ScanSummary

ToolClientFactory = Callable[[], ToolChatClient]


def default_tool_client() -> ToolChatClient:
    """The configured provider's client (from ``.env`` / environment variables)."""
    return OpenAICompatibleClient(load_settings())


class AgentBusyError(RuntimeError):
    """An agent run is already going on."""


class AgentStatus(StrEnum):
    """Where an agent run is."""

    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class AgentStart(BaseModel):
    """Limits for one agent run."""

    max_steps: int = Field(default=AgentLimits.max_steps, ge=1, le=100)
    max_cost_usd: float = Field(default=AgentLimits.max_cost_usd, ge=0.0, le=2.0)


class AgentState(BaseModel):
    """What the web app shows: the steps so far, and the finished run once there is one."""

    scan_id: str
    status: AgentStatus
    max_steps: int
    max_cost_usd: float
    steps: list[AgentStep] = Field(default_factory=list)
    run: AgentRun | None = None
    error: str = ""
    zip_available: bool = False


def agent_zip_path(data_dir: Path, scan_id: str) -> Path:
    """Where the project fixed by the last agent run is kept."""
    return data_dir / "agent" / f"{scan_id}.zip"


def forget_agent(data_dir: Path, scan_id: str) -> None:
    """Delete the agent's zip for a scan."""
    agent_zip_path(data_dir, scan_id).unlink(missing_ok=True)


class AgentRunner:
    """Runs one agent session at a time in a worker thread."""

    def __init__(self, store: ScanStore, data_dir: Path, client_factory: ToolClientFactory):
        self.store = store
        self.data_dir = data_dir
        self.client_factory = client_factory
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="agent")
        self._lock = threading.Lock()
        self._live: dict[str, AgentState] = {}

    def start(self, summary: ScanSummary, root: str | None, limits: AgentStart) -> AgentState:
        """Queue a run for ``summary``; raises :class:`AgentBusyError` if one is going on."""
        with self._lock:
            if any(s.status is AgentStatus.RUNNING for s in self._live.values()):
                raise AgentBusyError("The agent is already working on a project. Wait for it.")
            state = AgentState(
                scan_id=summary.id,
                status=AgentStatus.RUNNING,
                max_steps=limits.max_steps,
                max_cost_usd=limits.max_cost_usd,
            )
            self._live[summary.id] = state
        self.pool.submit(self._work, summary, root, limits)
        return state.model_copy(deep=True)

    def state(self, scan_id: str) -> AgentState | None:
        """The running or last finished run of a scan, or ``None``."""
        with self._lock:
            live = self._live.get(scan_id)
            if live is not None:
                return live.model_copy(deep=True)
        raw = self.store.agent(scan_id)
        return AgentState.model_validate_json(raw) if raw else None

    def shutdown(self) -> None:
        """Wait for a running session to finish."""
        self.pool.shutdown(wait=True)

    def _record(self, scan_id: str, step: AgentStep) -> None:
        with self._lock:
            self._live[scan_id].steps.append(step)

    def _finish(self, scan_id: str, **changes: object) -> None:
        with self._lock:
            state = self._live.pop(scan_id)
            final = state.model_copy(update=changes)
        self.store.save_agent(scan_id, final.model_dump_json())

    def _work(self, summary: ScanSummary, root: str | None, limits: AgentStart) -> None:
        scan_id = summary.id
        try:
            client = self.client_factory()
            with project_copy(self.data_dir, summary, root) as project:
                result = run_agent(
                    project,
                    client,
                    AgentLimits(limits.max_steps, limits.max_cost_usd),
                    lambda step: self._record(scan_id, step),
                )
                target = agent_zip_path(self.data_dir, scan_id)
                target.unlink(missing_ok=True)
                zip_available = False
                if result.texts:
                    try:
                        data = project_zip(project.root, result.texts, f"{summary.name}-fixed")
                    except ValueError:
                        pass  # too large for a zip; the patch is still there
                    else:
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_bytes(data)
                        zip_available = True
            self._finish(
                scan_id,
                status=AgentStatus.DONE,
                run=result.run,
                steps=result.run.steps,
                zip_available=zip_available,
            )
        except (SettingsError, LLMError, FixUnavailableError) as exc:
            self._finish(scan_id, status=AgentStatus.FAILED, error=str(exc))
        except Exception as exc:  # never leave a run stuck at "running"
            self._finish(
                scan_id,
                status=AgentStatus.FAILED,
                error=f"The agent failed: {type(exc).__name__}: {exc}",
            )
