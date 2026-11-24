"""Scan records in a small SQLite database. Thread-safe: background jobs write, requests read."""

from __future__ import annotations

import sqlite3
import threading
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel
from shipshape.models import Report

SCHEMA = """
CREATE TABLE IF NOT EXISTS scans (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    source TEXT NOT NULL,
    explain INTEGER NOT NULL,
    status TEXT NOT NULL,
    progress TEXT NOT NULL DEFAULT '',
    error TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    finished_at TEXT,
    grade TEXT,
    findings INTEGER,
    report TEXT
)
"""


class ScanStatus(StrEnum):
    """Where a scan is in its life."""

    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class ScanSummary(BaseModel):
    """Everything about a scan except the (large) report."""

    id: str
    name: str
    source: str  # "path" or "upload"
    explain: bool
    status: ScanStatus
    progress: str
    error: str
    created_at: str
    finished_at: str | None
    grade: str | None
    findings: int | None


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class ScanStore:
    """Create, update and read scans. One connection guarded by a lock is plenty here."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        with self._lock:
            self._db.execute(SCHEMA)
            # A server restart interrupts running jobs; don't leave them "running" forever.
            self._db.execute(
                "UPDATE scans SET status = ?, error = ? WHERE status IN (?, ?)",
                (
                    ScanStatus.FAILED,
                    "Interrupted by a server restart.",
                    ScanStatus.QUEUED,
                    ScanStatus.RUNNING,
                ),
            )
            self._db.commit()

    def create(self, scan_id: str, name: str, source: str, explain: bool) -> ScanSummary:
        """Insert a new queued scan."""
        with self._lock:
            self._db.execute(
                "INSERT INTO scans (id, name, source, explain, status, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (scan_id, name, source, int(explain), ScanStatus.QUEUED, _now()),
            )
            self._db.commit()
        summary = self.get(scan_id)
        assert summary is not None
        return summary

    def update(
        self, scan_id: str, *, status: ScanStatus | None = None, progress: str | None = None
    ) -> None:
        """Change status and/or progress text."""
        fields, values = [], []
        if status is not None:
            fields.append("status = ?")
            values.append(status.value)
        if progress is not None:
            fields.append("progress = ?")
            values.append(progress)
        if not fields:
            return
        with self._lock:
            self._db.execute(
                f"UPDATE scans SET {', '.join(fields)} WHERE id = ?", (*values, scan_id)
            )
            self._db.commit()

    def finish(self, scan_id: str, report: Report) -> None:
        """Store the report and mark the scan done."""
        with self._lock:
            self._db.execute(
                "UPDATE scans SET status = ?, progress = '', finished_at = ?, grade = ?, "
                "findings = ?, report = ? WHERE id = ?",
                (
                    ScanStatus.DONE,
                    _now(),
                    report.grade,
                    len(report.findings),
                    report.model_dump_json(),
                    scan_id,
                ),
            )
            self._db.commit()

    def fail(self, scan_id: str, error: str) -> None:
        """Mark the scan failed with a message that is safe to show."""
        with self._lock:
            self._db.execute(
                "UPDATE scans SET status = ?, error = ?, finished_at = ? WHERE id = ?",
                (ScanStatus.FAILED, error, _now(), scan_id),
            )
            self._db.commit()

    def get(self, scan_id: str) -> ScanSummary | None:
        """One scan without its report, or ``None``."""
        with self._lock:
            row = self._db.execute("SELECT * FROM scans WHERE id = ?", (scan_id,)).fetchone()
        return self._summary(row) if row else None

    def report(self, scan_id: str) -> str | None:
        """The stored report as JSON text, or ``None`` if there is none (yet)."""
        with self._lock:
            row = self._db.execute("SELECT report FROM scans WHERE id = ?", (scan_id,)).fetchone()
        return row["report"] if row and row["report"] else None

    def list(self, limit: int = 50) -> list[ScanSummary]:
        """Newest scans first."""
        with self._lock:
            rows = self._db.execute(
                "SELECT * FROM scans ORDER BY created_at DESC, rowid DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._summary(row) for row in rows]

    def delete(self, scan_id: str) -> bool:
        """Remove a scan; True if it existed."""
        with self._lock:
            cursor = self._db.execute("DELETE FROM scans WHERE id = ?", (scan_id,))
            self._db.commit()
        return cursor.rowcount > 0

    @staticmethod
    def _summary(row: sqlite3.Row) -> ScanSummary:
        return ScanSummary(
            id=row["id"],
            name=row["name"],
            source=row["source"],
            explain=bool(row["explain"]),
            status=ScanStatus(row["status"]),
            progress=row["progress"],
            error=row["error"],
            created_at=row["created_at"],
            finished_at=row["finished_at"],
            grade=row["grade"],
            findings=row["findings"],
        )
