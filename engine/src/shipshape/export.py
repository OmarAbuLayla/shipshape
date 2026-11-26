"""Export a report as JSON, Markdown or CSV.

JSON is the complete report (for tools). Markdown is for people: paste it into an issue, a
README or a supervisor email. CSV has one row per location, for spreadsheets. All three work
with or without AI explanations; explanations and fixes are included when present.
"""

from __future__ import annotations

import csv
import io
from collections import Counter
from enum import StrEnum

from shipshape.models import Dimension, Exclusions, Finding, Location, Report, Severity

SEVERITY_HEADINGS = {
    Severity.CRITICAL: "Fix first (critical)",
    Severity.MAJOR: "Worth fixing (major)",
    Severity.MINOR: "Polish (minor)",
}


class ExportFormat(StrEnum):
    """Supported export formats; values double as file extensions."""

    JSON = "json"
    MARKDOWN = "md"
    CSV = "csv"


def format_location(location: Location) -> str:
    """``path:line`` or ``path [code cell 2]:line``; ``whole project`` for project-wide findings."""
    if location.path == ".":
        return "whole project"
    text = location.path
    if location.cell is not None:
        text += f" [code cell {location.cell}]"
    if location.start_line is not None:
        text += f":{location.start_line}"
    return text


SKIPPED_HEADING = "Not analysed"
SKIPPED_NOTE = (
    "Shipshape could not read these files, so any problems in them are missing from the "
    "findings and the scores"
)


def describe_skipped(report: Report, limit: int = 20) -> list[str]:
    """One line per file Shipshape could not analyse, with the reason."""
    lines = [f"`{s.path}`: {s.reason}" for s in report.skipped[:limit]]
    if len(report.skipped) > limit:
        lines.append(f"... and {len(report.skipped) - limit} more")
    return lines


def describe_exclusions(exclusions: Exclusions) -> list[str]:
    """One sentence per kind of exclusion; empty when the report covers everything."""
    lines = []
    if exclusions.files_excluded:
        files = "file" if exclusions.files_excluded == 1 else "files"
        patterns = ", ".join(f"`{p}`" for p in exclusions.patterns[:6])
        more = ", ..." if len(exclusions.patterns) > 6 else ""
        lines.append(
            f"{exclusions.files_excluded} {files} left out by .shipshapeignore ({patterns}{more})."
        )
    if exclusions.disabled_checks:
        names = ", ".join(f"`{c}`" for c in exclusions.disabled_checks)
        lines.append(f"Checks switched off for this project: {names}.")
    inline = Counter(s.check_id for s in exclusions.suppressed if s.how == "inline comment")
    if inline:
        total = sum(inline.values())
        places = "place" if total == 1 else "places"
        ids = ", ".join(f"`{c}` ({n})" for c, n in inline.most_common())
        lines.append(f"{total} {places} marked `# shipshape: ignore` in the code: {ids}.")
    return lines


def _finding_markdown(number: int, finding: Finding) -> list[str]:
    lines = [
        f"### {number}. {finding.title}",
        "",
        f"`{finding.check_id}` · {finding.severity.value} · {finding.dimension.value} · "
        f"concept: {finding.concept}",
        "",
    ]
    shown = finding.locations[:15]
    where = ", ".join(f"`{format_location(loc)}`" for loc in shown)
    more = f" and {len(finding.locations) - len(shown)} more" if len(finding.locations) > 15 else ""
    lines += [f"**Where:** {where}{more}", ""]
    x = finding.explanation
    if x is None:
        lines += [finding.message, ""]
        return lines
    lines += [
        f"> {x.summary}",
        "",
        f"**What's going on.** {x.what}",
        "",
        f"**Why it matters.** {x.why}",
        "",
        f"**How to fix it.** {x.how_to_fix}",
        "",
    ]
    if x.fix_status.value == "verified" and x.edits:
        lines.append("**Proposed fix** (verified by static checks; behaviour not tested):")
        lines.append("")
        for edit in x.edits:
            lines.append(f"`{edit.path}`")
            lines.append("```diff")
            lines += [f"- {line}" for line in edit.search.splitlines()]
            lines += [f"+ {line}" for line in edit.replace.splitlines()]
            lines += ["```", ""]
        if x.behaviour_change:
            lines += [f"**Heads-up:** {x.behaviour_change}", ""]
    elif x.fix_status.value == "rejected":
        lines += [f"*{x.fix_note}*", ""]
    return lines


def to_markdown(report: Report) -> str:
    """A readable report: summary, scores, then every finding grouped by severity."""
    s = report.stats
    lines = [
        f"# Shipshape report: {report.project_name}",
        "",
        f"Grade **{report.grade}** (rough guide) · {s.python_files} Python files, "
        f"{s.notebooks} notebooks, {s.lines_of_code:,} lines of code · "
        f"{len(report.findings)} findings",
        "",
        "| Dimension | Score |",
        "|---|---|",
    ]
    lines += [f"| {d.value.capitalize()} | {report.scores.get(d, 100)} |" for d in Dimension]
    lines.append("")
    excluded = describe_exclusions(report.exclusions)
    if excluded:
        lines += ["**Not included in the scores** (on this project's own request):", ""]
        lines += [f"- {line}" for line in excluded]
        lines.append("")
    skipped = describe_skipped(report)
    if skipped:
        lines += [f"**{SKIPPED_HEADING}.** {SKIPPED_NOTE}:", ""]
        lines += [f"- {line}" for line in skipped]
        lines.append("")
    stats = report.explain_stats
    if stats is not None:
        cost = ""
        if stats.api_calls and stats.estimated_cost_usd is not None:
            cost = f", about ${stats.estimated_cost_usd:.4f}"
        if stats.cache_hits:
            cost += f" ({stats.cache_hits} from cache, no cost)"
        lines += [
            f"Explanations by {stats.model} ({stats.provider}): {stats.findings_explained} "
            f"findings explained, {stats.fixes_verified} verified fixes{cost}.",
            "",
        ]
    number = 0
    for severity, heading in SEVERITY_HEADINGS.items():
        group = [f for f in report.findings if f.severity is severity]
        if not group:
            continue
        lines += [f"## {heading}", ""]
        for finding in group:
            number += 1
            lines += _finding_markdown(number, finding)
    if not report.findings:
        lines += ["No findings. This project is in good shape.", ""]
    for error in report.check_errors:
        lines.append(f"- Note: {error}")
    lines += [
        "",
        f"*Generated by Shipshape {report.engine_version}. Nothing in the project was executed.*",
        "",
    ]
    return "\n".join(lines)


CSV_COLUMNS = [
    "finding",
    "severity",
    "dimension",
    "check_id",
    "title",
    "path",
    "line",
    "cell",
    "concept",
    "message",
    "ai_summary",
    "fix_status",
]


def to_csv(report: Report) -> str:
    """One row per location, so a spreadsheet can filter by file."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(CSV_COLUMNS)
    for number, finding in enumerate(report.findings, start=1):
        x = finding.explanation
        for location in finding.locations:
            writer.writerow(
                [
                    number,
                    finding.severity.value,
                    finding.dimension.value,
                    finding.check_id,
                    finding.title,
                    location.path,
                    location.start_line or "",
                    location.cell or "",
                    finding.concept,
                    finding.message,
                    x.summary if x else "",
                    x.fix_status.value if x else "",
                ]
            )
    return buffer.getvalue()


def export(report: Report, fmt: ExportFormat) -> str:
    """Render ``report`` in ``fmt``."""
    if fmt is ExportFormat.JSON:
        return report.model_dump_json(indent=2) + "\n"
    if fmt is ExportFormat.MARKDOWN:
        return to_markdown(report)
    return to_csv(report)


def format_for_path(name: str) -> ExportFormat:
    """Pick the format from a file name's extension (.json, .md/.markdown, .csv)."""
    suffix = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if suffix == "markdown":
        suffix = "md"
    try:
        return ExportFormat(suffix)
    except ValueError as exc:
        raise ValueError(f"Unknown export format {suffix!r}: use .json, .md or .csv") from exc
