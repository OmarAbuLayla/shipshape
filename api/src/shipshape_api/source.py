"""Serve the code of a scanned file, for the web app's code view.

Reports deliberately contain no source code, so the code view asks for one file at a time.
Only files that were part of the scan are served. Folder scans read the folder as it is now;
uploads read the original zip kept for the scan. Either way the text is produced exactly as the
scan produced it (notebooks become their code cells joined), and compared with the fingerprint
stored in the report, so the app can warn when line numbers may have moved.
"""

from __future__ import annotations

import hashlib
import shutil
import tempfile
from pathlib import Path

from pydantic import BaseModel
from shipshape.models import Report
from shipshape.project import read_source

from shipshape_api.fixes import upload_path
from shipshape_api.store import ScanSummary
from shipshape_api.uploads import UploadError, extract_project


class SourceUnavailableError(RuntimeError):
    """The file can't be served; the message says why, for the user."""


class SourceFile(BaseModel):
    """One file's scanned text."""

    path: str
    text: str
    cell_starts: list[int]
    changed: bool  # True if the file differs from what was scanned


def _read(root: Path, rel: str) -> tuple[str, tuple[int, ...]]:
    target = (root / rel).resolve()
    if not target.is_relative_to(root.resolve()):
        raise SourceUnavailableError("That file is not part of this scan.")
    if not target.is_file():
        raise SourceUnavailableError(f"{rel} no longer exists in the scanned folder.")
    loaded = read_source(target)
    if loaded is None:
        raise SourceUnavailableError(f"{rel} can no longer be read.")
    return loaded


def load(
    data_dir: Path, summary: ScanSummary, root: str | None, report: Report, rel: str
) -> SourceFile:
    """The scanned text of ``rel`` for this scan."""
    if rel not in report.files_scanned:
        raise SourceUnavailableError("That file is not part of this scan.")
    if summary.source == "upload":
        kept = upload_path(data_dir, summary.id)
        if not kept.is_file():
            raise SourceUnavailableError(
                "The uploaded zip was not kept for this scan (older scans did not keep it), so "
                "its code can't be shown. Upload the project again to see its code."
            )
        workdir = Path(tempfile.mkdtemp(prefix="shipshape-source-"))
        try:
            text, starts = _read(extract_project(kept, workdir), rel)
        except UploadError as exc:
            raise SourceUnavailableError(str(exc)) from exc
        finally:
            shutil.rmtree(workdir, ignore_errors=True)
    else:
        if root is None or not Path(root).is_dir():
            raise SourceUnavailableError("The scanned folder no longer exists.")
        text, starts = _read(Path(root), rel)
    info = report.files.get(rel)
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return SourceFile(
        path=rel,
        text=text,
        cell_starts=list(starts),
        changed=info is not None and info.sha256 != digest,
    )
