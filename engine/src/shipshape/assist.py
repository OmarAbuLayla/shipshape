"""Shipshape as a set of tools for a coding assistant (used by the MCP server).

In this mode the assistant is the LLM: it explains findings and writes fixes itself. Shipshape
provides what an LLM cannot do reliably on its own: deterministic findings and a grade, the
lessons, and the same fix gates the built-in explanations go through. Nothing here writes to
the scanned project; the assistant applies a fix only after :func:`verify_edits` passed it.
"""

from __future__ import annotations

import tempfile
from collections import Counter
from collections.abc import Iterable
from pathlib import Path

from pydantic import BaseModel, Field

from shipshape.analyzer import analyze_project
from shipshape.export import (
    GOOD_HEADING,
    SKIPPED_NOTE,
    describe_exclusions,
    describe_skipped,
    describe_strengths,
    format_location,
)
from shipshape.lessons import all_lessons, find_lesson
from shipshape.llm.context import FindingContext, Redactions
from shipshape.llm.validate import FixRejectedError, ValidatedFix, validate_fix
from shipshape.models import Dimension, Edit, Finding, Report, Severity
from shipshape.project import Project
from shipshape.scoring import GRADES, PENALTY
from shipshape.viewer import render_map_html

DEFAULT_MAX_FINDINGS = 50
MAX_LOCATIONS_SHOWN = 12


class AssistError(ValueError):
    """A request the tools cannot serve; the message tells the assistant what to do instead."""


class ProposedEdit(BaseModel):
    """One edit from the assistant: replace a unique search text, or whole lines by number.

    Line numbers let an edit replace a line without quoting it, so a secret never has to be
    repeated. They refer to the file as it is on disk now, counted from 1.
    """

    path: str = Field(description="Path of a .py file, relative to the project folder.")
    replace: str = Field(description="The new text.")
    search: str = Field(default="", description="Exact text to replace; unique in the file.")
    line: int | None = Field(default=None, ge=1, description="First line to replace instead.")
    end_line: int | None = Field(default=None, ge=1, description="Last line (default: line).")


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


def _score_lines(report: Report) -> list[str]:
    """Each dimension's score with the findings that lowered it, and how the grade is made."""
    lines = ["Scores (0-100), each starting at 100:"]
    for dimension in Dimension:
        counts = Counter(f.severity for f in report.findings if f.dimension is dimension)
        parts = [
            f"{counts[severity]} {severity.value} -{counts[severity] * PENALTY[severity]}"
            for severity in Severity
            if counts[severity]
        ]
        lost = sum(counts[severity] * PENALTY[severity] for severity in Severity)
        floor = ", capped at 0" if lost > 100 else ""
        reason = f" ({', '.join(parts)}{floor})" if parts else " (no findings)"
        lines.append(f"- {dimension.value} {report.scores.get(dimension, 100)}{reason}")
    penalties = ", ".join(f"{s.value} -{points}" for s, points in PENALTY.items())
    grades = ", ".join(f"{letter} from {limit}" for limit, letter in GRADES)
    lines.append(
        f"How the grade works: every finding costs its dimension a fixed amount ({penalties}), "
        f"however many places it covers; the grade comes from the average of the six scores "
        f"({grades}, E below). A dimension with no findings scores 100 even if it is thin "
        "(one small test is enough for testing), so read scores together with the findings."
    )
    return lines


def report_text(report: Report, max_findings: int = DEFAULT_MAX_FINDINGS) -> str:
    """A compact, plain-text report for an assistant to read and explain."""
    s = report.stats
    lines = [
        f"Shipshape report for {report.project_name}: grade {report.grade} (rough guide).",
        f"{s.python_files} Python files, {s.notebooks} notebooks, {s.lines_of_code} lines of "
        f"code, {len(report.findings)} findings.",
        *_score_lines(report),
    ]
    excluded = describe_exclusions(report.exclusions)
    if excluded:
        lines.append("Left out on the project's own request: " + " ".join(excluded))
    skipped = describe_skipped(report)
    if skipped:
        lines.append(f"NOT ANALYSED. {SKIPPED_NOTE}: " + "; ".join(skipped))
    good = describe_strengths(report, limit=None)
    if good:
        lines.append(f"{GOOD_HEADING} (tell the user): " + " ".join(good))
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
        "Notebook locations read 'path [code cell N]:line': N counts code cells only, from 1 "
        "(Markdown cells are skipped), and the line is within that cell. verify_fix only "
        "handles .py files.",
        "Nothing in the project was executed.",
    ]
    return "\n".join(lines)


def scan(path: str, max_findings: int = DEFAULT_MAX_FINDINGS) -> str:
    """Scan the project at ``path`` and return the report as text."""
    return report_text(analyze_project(load_project(path)), max_findings)


def _context(
    project: Project, findings: Iterable[Finding], redactions: Redactions | None = None
) -> FindingContext:
    """Fix gates for an assistant that can see every file: any ``.py`` file may be edited.

    ``redactions`` maps the placeholders the assistant saw back to the real secrets.
    """
    python = {s.path for s in project.python_files}
    located = tuple(
        (loc.path, loc.start_line)
        for finding in findings
        for loc in finding.locations
        if loc.path in python and loc.start_line is not None and loc.cell is None
    )
    return FindingContext("", tuple(sorted(python)), located, redactions or Redactions())


def _as_edit(project: Project, number: int, proposed: ProposedEdit) -> Edit:
    """Turn a proposed edit into a search/replace edit, reading line-based ones from disk."""
    path = proposed.path.replace("\\", "/")
    if proposed.line is None:
        if proposed.end_line is not None:
            raise AssistError(f"Edit {number} has end_line but no line.")
        return Edit(path=path, search=proposed.search, replace=proposed.replace)
    if proposed.search:
        raise AssistError(f"Edit {number}: give either search or line numbers, not both.")
    source = next((s for s in project.python_files if s.path == path), None)
    if source is None:
        raise AssistError(f"Edit {number}: {path} is not a Python file of this project.")
    lines = source.text.splitlines(keepends=True)
    end = proposed.end_line or proposed.line
    if end < proposed.line or end > len(lines):
        raise AssistError(f"Edit {number}: lines {proposed.line}-{end} are outside {path}.")
    search = "".join(lines[proposed.line - 1 : end])
    replace = proposed.replace
    if search.endswith("\n") and replace and not replace.endswith("\n"):
        replace += "\n"  # whole lines were replaced; keep the line break the assistant left out
    return Edit(path=path, search=search, replace=replace)


def _elsewhere(findings: list[Finding], touched: set[str]) -> str:
    """Where the problem is still reported outside the edited files, for the PASSED message."""
    places = [
        format_location(loc)
        for finding in findings
        for loc in finding.locations
        if loc.path not in touched
    ]
    if not places:
        return ""
    shown = ", ".join(places[:8]) + (f" and {len(places) - 8} more" if len(places) > 8 else "")
    return f" It is still reported elsewhere, untouched by these edits: {shown}."


def check_edits(
    project: Project,
    report: Report,
    check_id: str,
    edits: list[ProposedEdit],
    redactions: Redactions | None = None,
    raw_findings: list[Finding] | None = None,
) -> tuple[ValidatedFix, str]:
    """Run the fix gates on ``edits`` for ``check_id`` in ``report``; nothing is written.

    Returns the validated fix and a note on places still reported in untouched files.
    Raises :class:`AssistError` for unusable requests and :class:`FixRejectedError` when a
    gate fails.
    """
    matching = [f for f in report.findings if f.check_id == check_id]
    if not matching:
        raise AssistError(
            f"The current scan has no {check_id} finding. It may be fixed already; scan again."
        )
    resolved = [_as_edit(project, n, edit) for n, edit in enumerate(edits, start=1)]
    context = _context(project, matching, redactions)
    validated = validate_fix(project, context, matching[0], resolved, raw_findings)
    return validated, _elsewhere(matching, set(validated.new_texts))


def verify_edits(path: str, check_id: str, edits: list[ProposedEdit]) -> str:
    """Run the fix gates on ``edits`` for the problem ``check_id`` reports, in memory only.

    Passing means: every search text appears exactly once, every edited file still parses,
    the problem is gone from every place it was reported in the edited files, and no other
    check reports more problems there than before. Raises :class:`FixRejectedError` otherwise.
    """
    project = load_project(path)
    validated, elsewhere = check_edits(project, analyze_project(project), check_id, edits)
    touched = set(validated.new_texts)
    return (
        f"PASSED. The edits remove {check_id} from {', '.join(sorted(touched))} without new "
        f"problems.{elsewhere} Apply exactly these edits now, then run the "
        "project's tests if it has any: Shipshape never runs code, so it cannot prove the "
        "behaviour is unchanged."
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
    "ProposedEdit",
    "lesson",
    "report_text",
    "scan",
    "verify_edits",
    "write_map",
]
