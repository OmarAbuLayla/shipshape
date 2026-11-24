"""Run scans in the background and record their progress."""

from __future__ import annotations

import re
import shutil
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from shipshape.analyzer import analyze_project
from shipshape.llm.cache import ExplanationCache
from shipshape.llm.client import ChatClient, FatalLLMError, OpenAICompatibleClient
from shipshape.llm.explain import explain_report
from shipshape.llm.settings import SettingsError, load_settings
from shipshape.models import Report
from shipshape.project import Project

from shipshape_api.store import ScanStatus, ScanStore

PROGRESS = re.compile(r"\[(\d+)/(\d+)\]")


@dataclass(frozen=True)
class LLMConnection:
    """A ready client plus the provider name shown in reports."""

    client: ChatClient
    provider: str


ClientFactory = Callable[[], LLMConnection]


def default_client_factory() -> LLMConnection:
    """Build the client from ``.env`` / environment variables."""
    settings = load_settings()
    return LLMConnection(OpenAICompatibleClient(settings), settings.provider)


@dataclass(frozen=True)
class ScanJob:
    """Everything a background scan needs."""

    scan_id: str
    root: Path
    explain: bool
    max_findings: int
    cleanup: Path | None = None  # temporary folder to delete afterwards (uploads)


class ScanRunner:
    """A small worker pool. Two scans at a time keeps a laptop responsive."""

    def __init__(self, store: ScanStore, client_factory: ClientFactory, workers: int = 2) -> None:
        self.store = store
        self.client_factory = client_factory
        self.pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="scan")

    def submit(self, job: ScanJob) -> Future[None]:
        """Queue a scan; returns immediately."""
        return self.pool.submit(self._run, job)

    def shutdown(self) -> None:
        """Wait for running scans to finish."""
        self.pool.shutdown(wait=True)

    def _run(self, job: ScanJob) -> None:
        store = self.store
        try:
            store.update(job.scan_id, status=ScanStatus.RUNNING, progress="Analyzing the code")
            project = Project.load(job.root)
            report = analyze_project(project)
            if job.explain and report.findings:
                self._explain(job, project, report)
            store.finish(job.scan_id, report)
        except Exception as exc:  # report every failure on the scan instead of losing it
            store.fail(job.scan_id, f"The scan failed: {type(exc).__name__}: {exc}")
        finally:
            if job.cleanup is not None:
                shutil.rmtree(job.cleanup, ignore_errors=True)

    def _explain(self, job: ScanJob, project: Project, report: Report) -> None:
        total = min(len(report.findings), job.max_findings)
        self.store.update(job.scan_id, progress=f"Explaining findings: 0 of {total} done")

        def on_progress(line: str) -> None:
            # explain_report reports "[done/total] title"
            match = PROGRESS.match(line)
            if match:
                done, of = match.groups()
                self.store.update(job.scan_id, progress=f"Explaining findings: {done} of {of} done")

        try:
            connection = self.client_factory()
            explain_report(
                report,
                project,
                connection.client,
                provider=connection.provider,
                max_findings=job.max_findings,
                cache=ExplanationCache(),
                progress=on_progress,
            )
        except (SettingsError, FatalLLMError) as exc:
            # The analysis is still valid; keep it and say why explanations are missing.
            report.check_errors.append(f"Explanations skipped: {exc}")
