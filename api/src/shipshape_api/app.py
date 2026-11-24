"""The FastAPI application: scans, progress, reports, and (when built) the web app itself."""

from __future__ import annotations

import os
import shutil
import tempfile
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from shipshape import __version__ as engine_version
from shipshape.export import ExportFormat, export
from shipshape.llm.explain import DEFAULT_MAX_FINDINGS
from shipshape.llm.settings import SettingsError, load_settings
from shipshape.models import Report

from shipshape_api import __version__, fixes
from shipshape_api.fixes import FixRequest, FixRunResponse
from shipshape_api.jobs import ClientFactory, ScanJob, ScanRunner, default_client_factory
from shipshape_api.store import ScanStore, ScanSummary
from shipshape_api.uploads import CHUNK, UploadError, extract_project, save_stream

REPO_ROOT = Path(__file__).resolve().parents[3]
EXPORT_TYPES = {
    ExportFormat.JSON: "application/json",
    ExportFormat.MARKDOWN: "text/markdown; charset=utf-8",
    ExportFormat.CSV: "text/csv; charset=utf-8",
}


def _safe_name(name: str) -> str:
    """A file-name-safe version of a project name (letters, digits, dash, underscore)."""
    cleaned = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in name).strip("-")
    return cleaned or "project"


DEV_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]


def default_data_dir() -> Path:
    """``SHIPSHAPE_DATA_DIR`` or ``~/.shipshape/api``."""
    override = os.environ.get("SHIPSHAPE_DATA_DIR")
    return Path(override) if override else Path.home() / ".shipshape" / "api"


class ScanRequest(BaseModel):
    """Scan a folder that already exists on this machine."""

    path: str
    explain: bool = False
    max_findings: int = Field(default=DEFAULT_MAX_FINDINGS, ge=1, le=50)


class LLMStatus(BaseModel):
    """Whether explanations are available. Never contains the key."""

    configured: bool
    provider: str | None = None
    model: str | None = None
    problem: str | None = None


class Health(BaseModel):
    """Versions and LLM availability."""

    status: str = "ok"
    api_version: str
    engine_version: str
    llm: LLMStatus


def _llm_status() -> LLMStatus:
    try:
        settings = load_settings()
    except SettingsError as exc:
        return LLMStatus(configured=False, problem=str(exc))
    if not settings.api_key:
        return LLMStatus(
            configured=False,
            provider=settings.provider,
            model=settings.model,
            problem=f"No API key: set {settings.key_var} in .env",
        )
    return LLMStatus(configured=True, provider=settings.provider, model=settings.model)


def create_app(
    data_dir: Path | None = None,
    client_factory: ClientFactory = default_client_factory,
    web_dist: Path | None = None,
) -> FastAPI:
    """Build the app. Tests pass a temporary ``data_dir`` and a fake ``client_factory``."""
    data_dir = data_dir or default_data_dir()
    store = ScanStore(data_dir / "scans.sqlite3")
    runner = ScanRunner(store, client_factory)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        runner.shutdown()

    app = FastAPI(title="Shipshape", version=__version__, lifespan=lifespan)
    app.state.store = store
    app.state.runner = runner
    app.add_middleware(
        CORSMiddleware, allow_origins=DEV_ORIGINS, allow_methods=["*"], allow_headers=["*"]
    )

    @app.get("/api/health")
    def health() -> Health:
        """Engine version and whether an LLM is configured."""
        return Health(api_version=__version__, engine_version=engine_version, llm=_llm_status())

    @app.post("/api/scans", status_code=202)
    def scan_path(request: ScanRequest) -> ScanSummary:
        """Start scanning a folder on this machine."""
        root = Path(request.path).expanduser()
        if not root.is_dir():
            raise HTTPException(400, f"Not a folder on this machine: {request.path}")
        scan_id = uuid.uuid4().hex[:12]
        summary = store.create(
            scan_id, root.resolve().name, "path", request.explain, str(root.resolve())
        )
        runner.submit(ScanJob(scan_id, root.resolve(), request.explain, request.max_findings))
        return summary

    @app.post("/api/scans/upload", status_code=202)
    def scan_upload(
        file: Annotated[UploadFile, File(description="A .zip of the project")],
        explain: Annotated[bool, Form()] = False,
        max_findings: Annotated[int, Form(ge=1, le=50)] = DEFAULT_MAX_FINDINGS,
    ) -> ScanSummary:
        """Start scanning an uploaded zip. The unpacked copy is deleted afterwards."""
        workdir = Path(tempfile.mkdtemp(prefix="shipshape-upload-"))
        try:
            archive = workdir / "upload.zip"
            save_stream(iter(lambda: file.file.read(CHUNK), b""), archive)
            root = extract_project(archive, workdir / "project")
        except UploadError as exc:
            shutil.rmtree(workdir, ignore_errors=True)
            raise HTTPException(400, str(exc)) from exc
        name = Path(file.filename or "upload").stem if root == workdir / "project" else root.name
        scan_id = uuid.uuid4().hex[:12]
        # Keep the original zip so verified fixes can be applied to it later.
        fixes.keep_upload(data_dir, scan_id, archive)
        summary = store.create(scan_id, name, "upload", explain)
        runner.submit(ScanJob(scan_id, root, explain, max_findings, cleanup=workdir))
        return summary

    @app.get("/api/scans")
    def list_scans() -> list[ScanSummary]:
        """Past scans, newest first."""
        return store.list()

    @app.get("/api/scans/{scan_id}")
    def get_scan(scan_id: str) -> ScanSummary:
        """Status and progress of one scan."""
        summary = store.get(scan_id)
        if summary is None:
            raise HTTPException(404, "No such scan.")
        return summary

    @app.get("/api/scans/{scan_id}/report")
    def get_report(scan_id: str) -> Response:
        """The finished report as JSON (409 while the scan is still running)."""
        if store.get(scan_id) is None:
            raise HTTPException(404, "No such scan.")
        report = store.report(scan_id)
        if report is None:
            raise HTTPException(409, "The report is not ready.")
        return Response(report, media_type="application/json")

    @app.get("/api/scans/{scan_id}/export")
    def export_report(scan_id: str, format: ExportFormat = ExportFormat.MARKDOWN) -> Response:
        """Download the findings as JSON, Markdown (``md``) or CSV, with or without AI text."""
        summary = store.get(scan_id)
        if summary is None:
            raise HTTPException(404, "No such scan.")
        raw = store.report(scan_id)
        if raw is None:
            raise HTTPException(409, "The report is not ready.")
        body = export(Report.model_validate_json(raw), format)
        filename = f"{_safe_name(summary.name)}-shipshape.{format.value}"
        return Response(
            body,
            media_type=EXPORT_TYPES[format],
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @app.post("/api/scans/{scan_id}/fixes")
    def apply_fixes(scan_id: str, request: FixRequest) -> FixRunResponse:
        """Apply the chosen verified fixes to a copy, scan it again, and keep the result.

        The scanned folder (or uploaded zip) is never changed.
        """
        summary = store.get(scan_id)
        if summary is None:
            raise HTTPException(404, "No such scan.")
        raw = store.report(scan_id)
        if raw is None:
            raise HTTPException(409, "The report is not ready.")
        try:
            result = fixes.run(
                data_dir,
                summary,
                store.root(scan_id),
                Report.model_validate_json(raw),
                request.findings,
            )
        except fixes.FixUnavailableError as exc:
            raise HTTPException(409, str(exc)) from exc
        store.save_fixes(scan_id, result.model_dump_json())
        return result

    @app.get("/api/scans/{scan_id}/fixes")
    def last_fixes(scan_id: str) -> FixRunResponse:
        """The last fix run of this scan (404 if fixes were never applied)."""
        raw = store.fixes(scan_id)
        if raw is None:
            raise HTTPException(404, "No fixes applied to this scan yet.")
        return FixRunResponse.model_validate_json(raw)

    @app.get("/api/scans/{scan_id}/fixes/download")
    def download_fixes(scan_id: str, format: fixes.DownloadFormat) -> Response:
        """The last fix run as a ``.patch`` file or a zip of the fixed project."""
        summary = store.get(scan_id)
        raw = store.fixes(scan_id)
        if summary is None or raw is None:
            raise HTTPException(404, "No fixes applied to this scan yet.")
        name = _safe_name(summary.name)
        if format is fixes.DownloadFormat.PATCH:
            body = FixRunResponse.model_validate_json(raw).patch.encode("utf-8")
            media, filename = "text/x-diff; charset=utf-8", f"{name}-shipshape.patch"
        else:
            path = fixes.zip_path(data_dir, scan_id)
            if not path.is_file():
                raise HTTPException(404, "No zip for this fix run; download the patch instead.")
            body, media, filename = path.read_bytes(), "application/zip", f"{name}-fixed.zip"
        return Response(
            body,
            media_type=media,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @app.delete("/api/scans/{scan_id}", status_code=204)
    def delete_scan(scan_id: str) -> None:
        """Forget a scan."""
        if not store.delete(scan_id):
            raise HTTPException(404, "No such scan.")
        fixes.forget(data_dir, scan_id)

    dist = (web_dist or REPO_ROOT / "web" / "dist").resolve()
    if (dist / "index.html").is_file():
        if (dist / "assets").is_dir():
            app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def web_app(path: str) -> FileResponse:
            """Serve the built web app; unknown paths get index.html (client-side routes)."""
            if path.startswith("api/"):
                raise HTTPException(404, "Not found.")
            candidate = (dist / path).resolve()
            if path and candidate.is_file() and candidate.is_relative_to(dist):
                return FileResponse(candidate)
            return FileResponse(dist / "index.html")

    return app
