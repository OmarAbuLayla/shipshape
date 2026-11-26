"""Run all checks on a project and assemble the report."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from shipshape import __version__
from shipshape.blocks import file_info
from shipshape.checks import Check, default_checks
from shipshape.graph import build_graph
from shipshape.models import (
    SEVERITY_ORDER,
    Exclusions,
    Finding,
    ProjectStats,
    Report,
    SkippedFile,
)
from shipshape.project import Project, skipped_sources
from shipshape.scoring import dimension_scores, overall_grade
from shipshape.suppress import apply_suppressions


def analyze(root: Path, checks: Sequence[Check] | None = None) -> Report:
    """Scan ``root`` with ``checks`` (all built-in checks by default) and return a report.

    A check that crashes is recorded in ``check_errors`` instead of failing the whole scan.
    No code from the project is executed.
    """
    return analyze_project(Project.load(root), checks)


def analyze_project(
    project: Project,
    checks: Sequence[Check] | None = None,
    raw_out: list[Finding] | None = None,
) -> Report:
    """Like :func:`analyze`, for a project that is already loaded.

    The project's own ignore rules are applied before scoring; everything they remove is listed
    in ``Report.exclusions``. The scoring formula itself never changes. If ``raw_out`` is given,
    every finding before suppression is appended to it (the fix gates count those).
    """
    raw: list[Finding] = []
    errors: list[str] = []
    for check in checks if checks is not None else default_checks():
        try:
            raw.extend(check.run(project))
        except Exception as exc:  # one broken check must not hide all other results
            errors.append(f"{check.id}: {type(exc).__name__}: {exc}")
    if raw_out is not None:
        raw_out.extend(raw)
    findings, suppressed = apply_suppressions(project, raw)
    findings.sort(key=lambda f: (SEVERITY_ORDER[f.severity], f.dimension, f.check_id))
    scores = dimension_scores(findings)
    graph = None
    try:
        graph = build_graph(project, findings)
    except Exception as exc:  # the report is still useful without a map
        errors.append(f"graph: {type(exc).__name__}: {exc}")
    files = {}
    try:
        files = file_info(project, findings)
    except Exception as exc:  # blocks are a convenience; the findings stand without them
        errors.append(f"blocks: {type(exc).__name__}: {exc}")
    return Report(
        engine_version=__version__,
        project_name=project.name,
        stats=ProjectStats(
            python_files=sum(not s.is_notebook for s in project.sources),
            notebooks=sum(s.is_notebook for s in project.sources),
            lines_of_code=sum(s.code_lines for s in project.sources),
        ),
        files_scanned=[s.path for s in project.sources],
        findings=findings,
        scores=scores,
        grade=overall_grade(scores),
        check_errors=errors,
        skipped=[SkippedFile(path=p, reason=r) for p, r in skipped_sources(project)],
        graph=graph,
        files=files,
        exclusions=Exclusions(
            ignore_files=list(project.ignore.files),
            patterns=[p.describe() for p in project.ignore.patterns],
            files_excluded=len(project.excluded),
            disabled_checks=list(project.ignore.disabled_checks),
            suppressed=suppressed,
        ),
    )
