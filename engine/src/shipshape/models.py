"""Data contract shared by the engine, the API and the frontend.

Every check produces ``Finding`` objects; a scan produces one ``Report``.
Keep this module free of analysis logic so other layers can import it cheaply.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

SCHEMA_VERSION = "0.2"


class Severity(StrEnum):
    """How urgently a finding should be fixed."""

    CRITICAL = "critical"
    MAJOR = "major"
    MINOR = "minor"


SEVERITY_ORDER: dict[Severity, int] = {Severity.CRITICAL: 0, Severity.MAJOR: 1, Severity.MINOR: 2}


class Dimension(StrEnum):
    """Quality dimension a finding counts against on the scorecard."""

    CORRECTNESS = "correctness"
    STRUCTURE = "structure"
    REPRODUCIBILITY = "reproducibility"
    READABILITY = "readability"
    TESTING = "testing"
    SECURITY = "security"


class Location(BaseModel):
    """A place in the scanned project. Paths are POSIX-style and relative to the project root.

    For notebooks, ``cell`` is the 1-based index among code cells and the line numbers are
    relative to that cell. A path of ``"."`` means the project as a whole.
    """

    path: str
    start_line: int | None = Field(default=None, ge=1)
    end_line: int | None = Field(default=None, ge=1)
    cell: int | None = Field(default=None, ge=1)


class Finding(BaseModel):
    """One problem detected by one check, possibly at several places."""

    check_id: str = Field(description="Stable id of the check, e.g. 'repro.hardcoded-path'.")
    title: str
    severity: Severity
    dimension: Dimension
    concept: str = Field(description="Teaching concept, e.g. 'Config over hard-coding'.")
    message: str = Field(description="Specific, plain-language explanation for this project.")
    locations: list[Location] = Field(min_length=1)
    evidence: str = Field(default="", description="Short excerpt or measurement. Never a secret.")


class ProjectStats(BaseModel):
    """Size of the scanned project."""

    python_files: int = 0
    notebooks: int = 0
    lines_of_code: int = 0


class Report(BaseModel):
    """Result of scanning one project."""

    schema_version: str = SCHEMA_VERSION
    engine_version: str
    project_name: str
    stats: ProjectStats = Field(default_factory=ProjectStats)
    files_scanned: list[str] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    scores: dict[Dimension, int] = Field(default_factory=dict)
    grade: str = ""
    check_errors: list[str] = Field(
        default_factory=list, description="Checks that crashed; the rest of the report is valid."
    )
