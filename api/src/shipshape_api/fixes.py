"""Apply verified fixes for a finished scan and keep the results for download.

Folder scans are fixed from the folder as it is now; if it changed since the scan, fixes that
no longer match are skipped with a reason. Uploads are fixed from the original zip, which is
kept next to the database for this purpose and deleted with the scan.
"""

from __future__ import annotations

import shutil
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field
from shipshape.fixes import Regenerate, apply_fixes, project_zip
from shipshape.models import FixRun, Report
from shipshape.project import Project

from shipshape_api.store import ScanSummary
from shipshape_api.uploads import UploadError, extract_project


class FixUnavailableError(RuntimeError):
    """Fixes cannot be applied to this scan; the message says why, for the user."""


class DownloadFormat(StrEnum):
    """What a fix run can be downloaded as."""

    PATCH = "patch"
    ZIP = "zip"


class FixRequest(BaseModel):
    """Which findings' fixes to apply (indices into the report's findings)."""

    findings: list[int] = Field(min_length=1, max_length=200)
    second_round: bool = Field(
        default=True, description="Regenerate fixes that collided with earlier ones (LLM calls)."
    )


class FixRunResponse(FixRun):
    """A fix run plus whether a zip of the fixed project can be downloaded."""

    zip_available: bool = False
    zip_note: str = ""


def upload_path(data_dir: Path, scan_id: str) -> Path:
    """Where an uploaded zip is kept."""
    return data_dir / "uploads" / f"{scan_id}.zip"


def zip_path(data_dir: Path, scan_id: str) -> Path:
    """Where the fixed project of the last fix run is kept."""
    return data_dir / "fixed" / f"{scan_id}.zip"


def keep_upload(data_dir: Path, scan_id: str, archive: Path) -> None:
    """Copy an uploaded zip next to the database."""
    target = upload_path(data_dir, scan_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(archive, target)


def forget(data_dir: Path, scan_id: str) -> None:
    """Delete everything kept on disk for a scan."""
    upload_path(data_dir, scan_id).unlink(missing_ok=True)
    zip_path(data_dir, scan_id).unlink(missing_ok=True)


@contextmanager
def project_copy(data_dir: Path, summary: ScanSummary, root: str | None) -> Iterator[Project]:
    """The scanned project, loaded fresh: the folder as it is now, or the kept upload unpacked.

    Raises :class:`FixUnavailableError` if neither is available any more. Nothing is written to
    the folder; an unpacked upload is deleted afterwards.
    """
    workdir: Path | None = None
    try:
        if summary.source == "upload":
            kept = upload_path(data_dir, summary.id)
            if not kept.is_file():
                raise FixUnavailableError("The uploaded zip is no longer available.")
            workdir = Path(tempfile.mkdtemp(prefix="shipshape-fix-"))
            try:
                project_root = extract_project(kept, workdir)
            except UploadError as exc:
                raise FixUnavailableError(str(exc)) from exc
        else:
            if root is None or not Path(root).is_dir():
                raise FixUnavailableError("The scanned folder no longer exists.")
            project_root = Path(root)
        yield Project.load(project_root)
    finally:
        if workdir is not None:
            shutil.rmtree(workdir, ignore_errors=True)


def run(
    data_dir: Path,
    summary: ScanSummary,
    root: str | None,
    report: Report,
    indices: list[int],
    regenerate: Regenerate | None = None,
) -> FixRunResponse:
    """Apply the chosen fixes to a copy of the scanned project and store the fixed zip."""
    if any(i < 0 or i >= len(report.findings) for i in indices):
        raise FixUnavailableError("Unknown finding number.")
    with project_copy(data_dir, summary, root) as project:
        result = apply_fixes(project, report, indices, regenerate)
        response = FixRunResponse(**result.run.model_dump())
        target = zip_path(data_dir, summary.id)
        target.unlink(missing_ok=True)
        if result.texts:
            try:
                data = project_zip(project.root, result.texts, f"{summary.name}-fixed")
            except ValueError as exc:
                response.zip_note = str(exc)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
                response.zip_available = True
        return response
