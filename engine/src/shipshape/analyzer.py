"""Run all checks on a project and assemble the report."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from shipshape import __version__
from shipshape.checks import Check, default_checks
from shipshape.models import SEVERITY_ORDER, Finding, ProjectStats, Report
from shipshape.project import Project
from shipshape.scoring import dimension_scores, overall_grade


def analyze(root: Path, checks: Sequence[Check] | None = None) -> Report:
    """Scan ``root`` with ``checks`` (all built-in checks by default) and return a report.

    A check that crashes is recorded in ``check_errors`` instead of failing the whole scan.
    No code from the project is executed.
    """
    project = Project.load(root)
    findings: list[Finding] = []
    errors: list[str] = []
    for check in checks if checks is not None else default_checks():
        try:
            findings.extend(check.run(project))
        except Exception as exc:  # one broken check must not hide all other results
            errors.append(f"{check.id}: {type(exc).__name__}: {exc}")
    findings.sort(key=lambda f: (SEVERITY_ORDER[f.severity], f.dimension, f.check_id))
    scores = dimension_scores(findings)
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
    )
