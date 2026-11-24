"""Shipshape as a set of tools for a coding assistant (used by the MCP server).

In this mode the assistant is the LLM: it explains findings and writes fixes itself. Shipshape
provides what an LLM cannot do reliably on its own: deterministic findings and a grade, the
lessons, and the same fix gates the built-in explanations go through. Nothing here writes to
the scanned project; the assistant applies a fix only after :func:`verify_edits` passed it.
"""

from __future__ import annotations

import tempfile
from collections.abc import Iterable
from pathlib import Path

from shipshape.analyzer import analyze_project
from shipshape.export import describe_exclusions, format_location
from shipshape.lessons import all_lessons, find_lesson
from shipshape.llm.context import FindingContext, Redactions
from shipshape.llm.validate import FixRejectedError, validate_fix
from shipshape.models import Dimension, Edit, Finding, Report
from shipshape.project import Project
from shipshape.viewer import render_map_html

DEFAULT_MAX_FINDINGS = 50
MAX_LOCATIONS_SHOWN = 12


class AssistError(ValueError):
    """A request the tools cannot serve; the message tells the assistant what to do instead."""


def load_project(path: str) -> Project:
    """Load the project folder at ``path`` or explain why it cannot be scanned."""
    root = Path(path).expanduser()
    if not root.is_dir():
        raise AssistError(f"{path} is not a folder. Pass the project's root folder.")
    return Project.load(root)


def _finding_lines(number: int, finding: Finding) -> list[str]:
    lesson = find_lesson(finding.check_id)
    shown = finding.locations[:MAX_LOCATIONS_SHOWN]
    where = ", ".join(format_location(loc) for loc in shown)
    if len(finding.locations) > len(shown):
        where += f" and {len(finding.locations) - len(shown)} more"
    lines = [
        f"{number}. [{finding.severity.value}] {finding.title} ({finding.check_id})",
        f"   Where: {where}",
        f"   {finding.message}",
    ]
    if finding.evidence:
        lines.append(f"   Evidence: {finding.evidence}")
    lines.append(f"   Concept: {finding.concept}" + (f" (lesson: {lesson.slug})" if lesson else ""))
    return lines


def report_text(report: Report, max_findings: int = DEFAULT_MAX_FINDINGS) -> str:
    """A compact, plain-text report for an assistant to read and explain."""
    s = report.stats
    scores = ", ".join(f"{d.value} {report.scores.get(d, 100)}" for d in Dimension)
    lines = [
        f"Shipshape report for {report.project_name}: grade {report.grade} (rough guide).",
        f"{s.python_files} Python files, {s.notebooks} notebooks, {s.lines_of_code} lines of "
        f"code, {len(report.findings)} findings.",
        f"Scores (0-100): {scores}.",
    ]
    excluded = describe_exclusions(report.exclusions)
    if excluded:
        lines.append("Left out on the project's own request: " + " ".join(excluded))
    lines.append("")
    for number, finding in enumerate(report.findings[:max_findings], start=1):
        lines += _finding_lines(number, finding)
    hidden = len(report.findings) - max_findings
    if hidden > 0:
        lines.append(f"... {hidden} more findings not shown (raise max_findings to see them).")
    if not report.findings:
        lines.append("No findings. This project is in good shape.")
    lines += [f"Note: {error}" for error in report.check_errors]
    lines += [
        "",
        "Locations in notebooks are shown as [cell N]; verify_fix only handles .py files.",
        "Nothing in the project was executed.",
    ]
    return "\n".join(lines)


def scan(path: str, max_findings: int = DEFAULT_MAX_FINDINGS) -> str:
    """Scan the project at ``path`` and return the report as text."""
    return report_text(analyze_project(load_project(path)), max_findings)


def _context(project: Project, findings: Iterable[Finding]) -> FindingContext:
    """Fix gates for an assistant that can see every file: any ``.py`` file may be edited."""
    python = {s.path for s in project.python_files}
    located = tuple(
        (loc.path, loc.start_line)
        for finding in findings
        for loc in finding.locations
        if loc.path in python and loc.start_line is not None and loc.cell is None
    )
    return FindingContext("", tuple(sorted(python)), located, Redactions())


def verify_edits(path: str, check_id: str, edits: list[Edit]) -> str:
    """Run the fix gates on ``edits`` for the problem ``check_id`` reports, in memory only.

    Passing means: every search text appears exactly once, every edited file still parses,
    the problem is gone from every place it was reported in the edited files, and no other
    check reports more problems there than before. Raises :class:`FixRejectedError` otherwise.
    """
    project = load_project(path)
    report = analyze_project(project)
    matching = [f for f in report.findings if f.check_id == check_id]
    if not matching:
        raise AssistError(
            f"The current scan has no {check_id} finding. It may be fixed already; scan again."
        )
    edits = [edit.model_copy(update={"path": edit.path.replace("\\", "/")}) for edit in edits]
    validated = validate_fix(project, _context(project, matching), matching[0], edits)
    files = ", ".join(sorted(validated.new_texts))
    return (
        f"PASSED. The edits remove {check_id} from {files} without new problems. Apply exactly "
        "these edits now, then run the project's tests if it has any: Shipshape never runs "
        "code, so it cannot prove the behaviour is unchanged."
    )


def lesson(name: str = "") -> str:
    """The lesson for a slug, concept or check id; the list of lessons if none matches."""
    found = find_lesson(name) if name.strip() else None
    if found is not None:
        checks = ", ".join(found.checks) or "none"
        return f"# {found.concept}\n\n{found.summary}\n\nTaught by: {checks}\n\n{found.body}"
    listing = "\n".join(f"- {item.slug}: {item.summary}" for item in all_lessons())
    prefix = f"No lesson matches {name!r}. " if name.strip() else ""
    return f"{prefix}Available lessons (pass a slug, concept or check id):\n{listing}"


def write_map(path: str, output: str = "") -> Path:
    """Write the standalone architecture map page and return where it was written.

    By default the page goes to the system's temporary folder, never into the project.
    """
    project = load_project(path)
    report = analyze_project(project)
    target = (
        Path(output).expanduser()
        if output
        else Path(tempfile.gettempdir()) / "shipshape" / f"{project.name}-map.html"
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_map_html(report), encoding="utf-8")
    return target.resolve()


__all__ = [
    "AssistError",
    "FixRejectedError",
    "lesson",
    "report_text",
    "scan",
    "verify_edits",
    "write_map",
]
