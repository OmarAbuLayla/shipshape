"""Receive and unpack uploaded projects safely.

A zip is untrusted input. Before anything is written we reject absolute paths, ``..``
segments, symbolic links and archives that are too large or contain too many files (a "zip
bomb"). Folders the scanner ignores anyway (virtualenvs, node_modules, .git) are skipped.
"""

from __future__ import annotations

import stat
import zipfile
from collections.abc import Iterable
from pathlib import Path, PurePosixPath

from shipshape.scanner import IGNORED_DIRS

MAX_UPLOAD_BYTES = 100 * 1024 * 1024  # the compressed zip
MAX_EXTRACTED_BYTES = 500 * 1024 * 1024
MAX_FILES = 20_000
CHUNK = 1024 * 1024


class UploadError(ValueError):
    """The upload is unusable; the message is safe to show to the user."""


def save_stream(chunks: Iterable[bytes], target: Path, limit: int = MAX_UPLOAD_BYTES) -> int:
    """Write an upload to ``target`` without ever holding more than one chunk in memory."""
    written = 0
    with target.open("wb") as handle:
        for chunk in chunks:
            written += len(chunk)
            if written > limit:
                raise UploadError(f"The zip is larger than {limit // (1024 * 1024)} MB.")
            handle.write(chunk)
    return written


def _is_symlink(info: zipfile.ZipInfo) -> bool:
    return stat.S_ISLNK(info.external_attr >> 16)


def _safe_parts(name: str) -> tuple[str, ...] | None:
    """Path parts of a zip entry, or ``None`` if the entry must not be extracted."""
    normalized = name.replace("\\", "/")
    path = PurePosixPath(normalized)
    if normalized.startswith("/") or (path.parts and path.parts[0].endswith(":")):
        return None
    if any(part in {"..", ""} for part in path.parts):
        return None
    return path.parts


def extract_project(zip_path: Path, dest: Path) -> Path:
    """Unpack ``zip_path`` into ``dest`` and return the project root inside it.

    If everything sits inside one top-level folder (the usual "Download ZIP" layout), that
    folder is the root.
    """
    try:
        archive = zipfile.ZipFile(zip_path)
    except zipfile.BadZipFile as exc:
        raise UploadError("That file is not a valid .zip archive.") from exc
    with archive:
        entries = archive.infolist()
        if len(entries) > MAX_FILES:
            raise UploadError(f"The zip contains more than {MAX_FILES:,} files.")
        if sum(info.file_size for info in entries) > MAX_EXTRACTED_BYTES:
            raise UploadError("The zip would unpack to more than 500 MB.")
        for info in entries:
            parts = _safe_parts(info.filename)
            if parts is None or _is_symlink(info):
                raise UploadError(f"Unsafe path in the zip: {info.filename!r}.")
            if info.is_dir() or any(part in IGNORED_DIRS for part in parts[:-1]):
                continue
            target = dest.joinpath(*parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as source, target.open("wb") as out:
                while block := source.read(CHUNK):
                    out.write(block)

    children = [p for p in dest.iterdir() if not p.name.startswith("__MACOSX")]
    if len(children) == 1 and children[0].is_dir():
        return children[0]
    return dest
