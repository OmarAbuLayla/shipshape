"""Data contract shared by the engine, the API and the frontend.

Every check produces ``Finding`` objects; a scan produces one ``Report``.
Keep this module free of analysis logic so other layers can import it cheaply.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

SCHEMA_VERSION = "0.5"


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
    explanation: Explanation | None = None


class FixStatus(StrEnum):
    """Whether a proposed fix survived validation."""

    VERIFIED = "verified"  # applied cleanly, parses, removes the finding, adds no new findings
    REJECTED = "rejected"  # a fix was proposed but failed a validation gate
    NONE = "none"  # explanation only, by design or because the model proposed no fix


class Edit(BaseModel):
    """Replace one exact piece of text in one file."""

    path: str
    search: str
    replace: str


class Explanation(BaseModel):
    """LLM-written teaching text for one finding, plus a validated fix if there is one."""

    summary: str
    what: str = Field(description="What is going on in this code.")
    why: str = Field(description="Why an engineer cares.")
    how_to_fix: str = Field(description="Steps a person can follow, even without the edits.")
    behaviour_change: str = Field(
        default="", description="What a user of the code would notice if the fix is applied."
    )
    edits: list[Edit] = Field(default_factory=list)
    fix_status: FixStatus = FixStatus.NONE
    fix_note: str = Field(default="", description="Why a fix was rejected, or what was checked.")
    model: str = ""
    cached: bool = False


class ExplainStats(BaseModel):
    """What one explanation run cost and achieved."""

    provider: str
    model: str
    findings_explained: int = 0
    api_calls: int = 0
    retries: int = 0
    cache_hits: int = 0
    failures: int = 0
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost_usd: float | None = None
    fixes_verified: int = 0
    fixes_rejected: int = 0
    seconds: float = 0.0


class ProjectStats(BaseModel):
    """Size of the scanned project."""

    python_files: int = 0
    notebooks: int = 0
    lines_of_code: int = 0


class Suppression(BaseModel):
    """One finding location the project asked Shipshape to leave out, and how it asked."""

    check_id: str
    title: str
    location: Location
    how: str  # "inline comment" or "check disabled"


class Exclusions(BaseModel):
    """Everything left out of a report on the project's own request, so scores stay traceable."""

    ignore_files: list[str] = Field(default_factory=list)
    patterns: list[str] = Field(default_factory=list)
    files_excluded: int = 0
    disabled_checks: list[str] = Field(default_factory=list)
    suppressed: list[Suppression] = Field(default_factory=list)

    @property
    def any(self) -> bool:
        """True if anything at all was left out."""
        return bool(self.files_excluded or self.disabled_checks or self.suppressed)


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
    graph: ProjectGraph | None = None
    explain_stats: ExplainStats | None = None
    exclusions: Exclusions = Field(default_factory=Exclusions)


class NodeKind(StrEnum):
    """What a map node stands for."""

    MODULE = "module"
    NOTEBOOK = "notebook"
    TEST = "test"
    FOLDER = "folder"
    CONFIG = "config"
    EXTERNAL = "external"
    MISSING = "missing"


class EdgeKind(StrEnum):
    """What a map edge stands for."""

    IMPORT = "import"
    TEST = "test"
    READS = "reads"


class GraphNode(BaseModel):
    """One box on the architecture map."""

    id: str = Field(description="File/folder path, or 'missing:...' / 'external:...'.")
    kind: NodeKind
    label: str
    parent: str | None = Field(default=None, description="Id of the enclosing folder node.")
    role: str = Field(default="", description="entry, library, script, test or notebook.")
    lines_of_code: int = 0
    functions: int = 0
    classes: int = 0
    max_complexity: int = 0
    third_party: list[str] = Field(default_factory=list)
    findings: list[int] = Field(default_factory=list, description="Indices into report.findings.")
    worst_severity: Severity | None = None


class GraphEdge(BaseModel):
    """One arrow on the architecture map."""

    source: str
    target: str
    kind: EdgeKind
    names: list[str] = Field(default_factory=list, description="Imported names, if any.")
    line: int | None = None


class ProjectGraph(BaseModel):
    """Architecture map of a project: files, folders, missing pieces and their connections."""

    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)
    project_findings: list[int] = Field(
        default_factory=list, description="Findings that belong to no single node."
    )
    unresolved_imports: list[str] = Field(
        default_factory=list, description="Imports that look local but match no file."
    )


Finding.model_rebuild()
Report.model_rebuild()
