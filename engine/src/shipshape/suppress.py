"""Apply a project's own ignore rules to findings: disabled checks and inline comments.

Nothing is dropped silently: every location left out becomes a :class:`Suppression` in the
report, so a reader can always see what the score does not include.
"""

from __future__ import annotations

import fnmatch

from shipshape.ignore import pragma_ids
from shipshape.models import Finding, Location, Suppression
from shipshape.project import Project, SourceFile


def _source_line(source: SourceFile, location: Location) -> str | None:
    """The text of the line a location points at (notebook cells translated back)."""
    if location.start_line is None:
        return None
    line = location.start_line
    if location.cell is not None and source.cell_starts:
        line = source.cell_starts[location.cell - 1] + location.start_line - 1
    lines = source.text.splitlines()
    return lines[line - 1] if 0 < line <= len(lines) else None


def _pragma_covers(ids: set[str], check_id: str) -> bool:
    return any(pattern == "*" or fnmatch.fnmatch(check_id, pattern) for pattern in ids)


def apply_suppressions(
    project: Project, findings: list[Finding]
) -> tuple[list[Finding], list[Suppression]]:
    """Remove what the project asked to ignore; return the kept findings and what was removed.

    A finding whose check is disabled is removed whole. Otherwise each location whose line has
    a matching ``# shipshape: ignore`` comment is removed, and a finding left with no locations
    disappears. Locations in excluded files (for example from ruff, which reads the disk) are
    removed too, without a suppression entry, since the whole file is already listed as excluded.
    """
    by_path = {s.path: s for s in project.sources}
    kept: list[Finding] = []
    suppressed: list[Suppression] = []
    for finding in findings:
        if project.ignore.check_disabled(finding.check_id):
            suppressed.extend(
                Suppression(
                    check_id=finding.check_id,
                    title=finding.title,
                    location=loc,
                    how="check disabled",
                )
                for loc in finding.locations
            )
            continue
        locations: list[Location] = []
        for loc in finding.locations:
            if loc.path != "." and project.ignore.ignores(loc.path):
                continue
            source = by_path.get(loc.path)
            line = _source_line(source, loc) if source else None
            ids = pragma_ids(line) if line is not None else None
            if ids is not None and _pragma_covers(ids, finding.check_id):
                suppressed.append(
                    Suppression(
                        check_id=finding.check_id,
                        title=finding.title,
                        location=loc,
                        how="inline comment",
                    )
                )
            else:
                locations.append(loc)
        if len(locations) == len(finding.locations):
            kept.append(finding)
        elif locations:
            kept.append(finding.model_copy(update={"locations": locations}))
    return kept, suppressed
