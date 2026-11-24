"""A local skill profile: which concepts keep coming up across your projects.

Built only from the scan history in the local database: no accounts, nothing leaves the
machine. Scans are grouped into projects (the scanned folder, or the name for uploads). A
project's latest scan says where it stands now; concepts that appeared in its earlier scans but
not in the latest one count as resolved there, but only if the files they were found in are
still part of the latest scan and the problem was not silenced there: a problem that vanished
because its files were deleted or left out with .shipshapeignore, or because a
``# shipshape: ignore`` comment or a disabled check hides it, was not fixed, so it is not
counted.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import PurePath

from pydantic import BaseModel, Field
from shipshape.lessons import concept_checks, find_lesson
from shipshape.models import SEVERITY_ORDER, Severity

from shipshape_api.store import ScanSummary


class ConceptStat(BaseModel):
    """One concept across all projects."""

    concept: str
    lesson: str | None  # slug, for the link
    dimension: str
    severity: Severity  # worst severity among current findings (or the last one seen)
    projects: list[str] = Field(default_factory=list)  # where it appears in the latest scan
    places: int = 0  # locations in those latest scans
    resolved_in: list[str] = Field(default_factory=list)  # seen earlier, gone in the latest scan


class ProjectStat(BaseModel):
    """One project's history."""

    name: str
    scans: int
    first_grade: str
    latest_grade: str
    latest_scan: str  # scan id, for the link
    latest_at: str
    findings: int


class Profile(BaseModel):
    """Everything the profile page shows."""

    scans: int = 0
    projects: list[ProjectStat] = Field(default_factory=list)
    concepts: list[ConceptStat] = Field(default_factory=list)


@dataclass
class _Seen:
    """What a concept looked like in one scan."""

    places: int = 0
    severity: Severity = Severity.MINOR
    dimension: str = ""
    paths: set[str] = field(default_factory=set)  # where it was found


@dataclass
class _Scan:
    summary: ScanSummary
    concepts: dict[str, _Seen]
    covered: set[str]  # paths the scan looked at ("." for the project as a whole)
    silenced: dict[str, set[str]]  # concept -> paths where the project suppressed it


@dataclass
class _Project:
    name: str
    scans: list[_Scan] = field(default_factory=list)


def _concepts(report: dict[str, object]) -> dict[str, _Seen]:
    seen: dict[str, _Seen] = {}
    findings: list[dict[str, object]] = report.get("findings", [])  # type: ignore[assignment]
    for finding in findings:
        concept = str(finding["concept"])
        severity = Severity(str(finding["severity"]))
        stat = seen.setdefault(
            concept, _Seen(severity=severity, dimension=str(finding["dimension"]))
        )
        locations: list[dict[str, object]] = finding["locations"]  # type: ignore[assignment]
        stat.places += len(locations)
        stat.paths.update(str(location["path"]) for location in locations)
        stat.severity = min(stat.severity, severity, key=SEVERITY_ORDER.__getitem__)
    return seen


def _covered(report: dict[str, object]) -> set[str]:
    """Every path a scan looked at: its source files and the files and folders on its map."""
    covered = {"."} | {str(path) for path in report.get("files_scanned", [])}  # type: ignore[attr-defined]
    graph = report.get("graph") or {}
    covered |= {str(node["id"]) for node in graph.get("nodes", [])}  # type: ignore[attr-defined]
    return covered


def _silenced(report: dict[str, object]) -> dict[str, set[str]]:
    """Paths where each concept was suppressed by an inline comment or a disabled check."""
    concept_of = {
        check: concept for concept, checks in concept_checks().items() for check in checks
    }
    silenced: dict[str, set[str]] = {}
    exclusions = report.get("exclusions") or {}
    for item in exclusions.get("suppressed", []):  # type: ignore[attr-defined]
        concept = concept_of.get(str(item["check_id"]))
        if concept:
            silenced.setdefault(concept, set()).add(str(item["location"]["path"]))
    return silenced


def _key(summary: ScanSummary, root: str | None, roots_by_name: dict[str, set[str]]) -> str:
    """Which project a scan belongs to: its folder, or for uploads its name.

    Folder scans from before the folder was recorded join the folder project with the same
    name when there is exactly one; otherwise they form their own project.
    """
    if summary.source != "path":
        return f"upload:{summary.name}"
    if root:
        return f"path:{root}"
    known = roots_by_name.get(summary.name, set())
    return f"path:{next(iter(known))}" if len(known) == 1 else f"folder:{summary.name}"


def _display_names(projects: dict[str, _Project], roots: dict[str, str | None]) -> None:
    """Make names unique: two folders called `analysis` get their parent folder added."""
    by_name: dict[str, list[str]] = {}
    for key, project in projects.items():
        by_name.setdefault(project.name, []).append(key)
    for keys in by_name.values():
        if len(keys) < 2:
            continue
        for key in keys:
            root = roots.get(key)
            parent = PurePath(root).parent.name if root else "upload"
            projects[key].name = f"{projects[key].name} ({parent})"


def _group(history: list[tuple[ScanSummary, str | None, str]]) -> dict[str, _Project]:
    """Sort scans into projects, oldest scan first in each."""
    roots_by_name: dict[str, set[str]] = {}
    for summary, root, _ in history:
        if summary.source == "path" and root:
            roots_by_name.setdefault(summary.name, set()).add(root)
    projects: dict[str, _Project] = {}
    roots: dict[str, str | None] = {}
    for summary, root, raw in history:
        key = _key(summary, root, roots_by_name)
        roots[key] = key.removeprefix("path:") if key.startswith("path:") else None
        report = json.loads(raw)
        projects.setdefault(key, _Project(name=summary.name)).scans.append(
            _Scan(summary, _concepts(report), _covered(report), _silenced(report))
        )
    _display_names(projects, roots)
    return projects


def _resolved(project: _Project) -> dict[str, _Seen]:
    """Concepts gone from the latest scan while their files are still checked (truly fixed)."""
    latest = project.scans[-1]
    earlier = {c for scan in project.scans[:-1] for c in scan.concepts} - latest.concepts.keys()
    fixed = {}
    for concept in earlier:
        last = next(s.concepts[concept] for s in reversed(project.scans) if concept in s.concepts)
        still_checked = (last.paths & latest.covered) - latest.silenced.get(concept, set())
        if still_checked:  # otherwise: files gone, left out or silenced, not fixed
            fixed[concept] = last
    return fixed


def _project_stat(project: _Project) -> ProjectStat:
    first, latest = project.scans[0].summary, project.scans[-1].summary
    return ProjectStat(
        name=project.name,
        scans=len(project.scans),
        first_grade=first.grade or "",
        latest_grade=latest.grade or "",
        latest_scan=latest.id,
        latest_at=latest.created_at,
        findings=latest.findings or 0,
    )


def build_profile(scans: Iterable[tuple[ScanSummary, str | None, str]]) -> Profile:
    """Aggregate finished scans, oldest first: (summary, scanned folder, report JSON)."""
    history = list(scans)
    projects = _group(history)
    concepts: dict[str, ConceptStat] = {}
    for project in projects.values():
        for concept, seen in project.scans[-1].concepts.items():
            stat = concepts.setdefault(concept, _new_stat(concept, seen))
            stat.projects.append(project.name)
            stat.places += seen.places
            stat.severity = min(stat.severity, seen.severity, key=SEVERITY_ORDER.__getitem__)
        for concept, last in _resolved(project).items():
            concepts.setdefault(concept, _new_stat(concept, last)).resolved_in.append(project.name)
    return Profile(
        scans=len(history),
        projects=sorted(
            (_project_stat(p) for p in projects.values()), key=lambda p: p.latest_at, reverse=True
        ),
        concepts=sorted(
            concepts.values(),
            key=lambda c: (-len(c.projects), SEVERITY_ORDER[c.severity], -c.places, c.concept),
        ),
    )


def _new_stat(concept: str, seen: _Seen) -> ConceptStat:
    lesson = find_lesson(concept)
    return ConceptStat(
        concept=concept,
        lesson=lesson.slug if lesson else None,
        dimension=seen.dimension,
        severity=seen.severity,
    )
