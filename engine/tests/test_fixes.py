"""Applying several verified fixes together: order, collisions, re-scan, patch and zip."""

from __future__ import annotations

import io
import zipfile

import pytest
from typer.testing import CliRunner

from shipshape import cli
from shipshape.analyzer import analyze_project
from shipshape.fixes import apply_fixes, project_zip
from shipshape.models import Edit, Explanation, Finding, FixStatus, Report

from .conftest import MakeProject

PATHS = 'DATA = "/home/alice/data/raw.csv"\nOUT = "/home/alice/out"\n'
LINT = "def collect(item, bucket=[]):\n    bucket.append(item)\n    return bucket\n"


def _with_fix(finding: Finding, *edits: Edit) -> Finding:
    explanation = Explanation(
        summary="s",
        what="w",
        why="y",
        how_to_fix="h",
        edits=list(edits),
        fix_status=FixStatus.VERIFIED,
    )
    return finding.model_copy(update={"explanation": explanation})


def _only(report: Report, check_id: str) -> int:
    (index,) = [i for i, f in enumerate(report.findings) if f.check_id == check_id]
    return index


PATH_FIX = (
    Edit(path="paths.py", search='"/home/alice/data/raw.csv"', replace='"data/raw.csv"'),
    Edit(path="paths.py", search='"/home/alice/out"', replace='"out"'),
)


def test_fixes_are_applied_and_the_project_is_rescanned(make_project: MakeProject) -> None:
    project = make_project({"paths.py": PATHS, "lint.py": LINT})
    report = analyze_project(project)
    paths = _only(report, "repro.hardcoded-path")
    report.findings[paths] = _with_fix(report.findings[paths], *PATH_FIX)
    lint = _only(report, "lint.mutable-default")
    report.findings[lint] = _with_fix(
        report.findings[lint],
        Edit(
            path="lint.py",
            search="def collect(item, bucket=[]):\n",
            replace=(
                "def collect(item, bucket=None):\n    bucket = [] if bucket is None else bucket\n"
            ),
        ),
    )

    result = apply_fixes(project, report, [paths, lint])

    assert [o.applied for o in result.run.outcomes] == [True, True]
    assert result.run.changed_files == ["lint.py", "paths.py"]
    after_checks = {f.check_id for f in result.after.findings}
    # ruff reads the disk; the fixed lint.py only exists in memory and must still be re-checked
    assert "lint.mutable-default" not in after_checks
    assert "repro.hardcoded-path" not in after_checks
    assert {d.check_id: (d.before, d.after) for d in result.run.deltas} == {
        "lint.mutable-default": (1, 0),
        "repro.hardcoded-path": (2, 0),
    }
    assert "--- a/paths.py" in result.run.patch and '+DATA = "data/raw.csv"' in result.run.patch
    assert (project.root / "paths.py").read_text(encoding="utf-8") == PATHS  # disk untouched


def test_colliding_fix_is_skipped_with_a_reason(make_project: MakeProject) -> None:
    project = make_project({"paths.py": PATHS})
    report = analyze_project(project)
    first = _only(report, "repro.hardcoded-path")
    report.findings[first] = _with_fix(report.findings[first], *PATH_FIX)
    # a second fix written against the original text of the same line
    report.findings.append(_with_fix(report.findings[first], PATH_FIX[0]))

    result = apply_fixes(project, report, [first, len(report.findings) - 1])

    applied, skipped = result.run.outcomes
    assert applied.applied and not skipped.applied
    assert "does not appear" in skipped.reason


def test_finding_without_verified_fix_is_skipped(make_project: MakeProject) -> None:
    project = make_project({"paths.py": PATHS})
    report = analyze_project(project)

    result = apply_fixes(project, report, [0])

    assert not result.run.outcomes[0].applied
    assert result.run.changed_files == []
    assert result.run.patch == ""
    assert result.run.after_grade == report.grade


def test_zip_contains_the_fixed_project(make_project: MakeProject) -> None:
    project = make_project({"paths.py": PATHS, "notes.txt": "keep me\n"})
    data = project_zip(project.root, {"paths.py": 'DATA = "x"\n'}, "demo-fixed")
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        assert sorted(archive.namelist()) == ["demo-fixed/notes.txt", "demo-fixed/paths.py"]
        assert archive.read("demo-fixed/paths.py") == b'DATA = "x"\n'


def test_cli_fix_writes_patch_and_zip_but_not_the_project(
    make_project: MakeProject,
    tmp_path_factory: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = make_project({"paths.py": PATHS})
    report = analyze_project(project)
    index = _only(report, "repro.hardcoded-path")
    report.findings[index] = _with_fix(report.findings[index], *PATH_FIX)
    monkeypatch.setattr(cli, "_scan_project", lambda *args: (project, report))
    out = tmp_path_factory.mktemp("out")

    result = CliRunner().invoke(
        cli.app,
        ["fix", str(project.root), "--patch", str(out / "f.patch"), "--zip", str(out / "f.zip")],
    )

    assert result.exit_code == 0, result.output
    assert "Applied 1 of 1 fixes" in result.output
    assert '+DATA = "data/raw.csv"' in (out / "f.patch").read_text(encoding="utf-8")
    assert zipfile.is_zipfile(out / "f.zip")
    assert (project.root / "paths.py").read_text(encoding="utf-8") == PATHS


def test_cli_fix_refuses_to_write_inside_the_project(make_project: MakeProject) -> None:
    project = make_project({"paths.py": PATHS})
    result = CliRunner().invoke(
        cli.app, ["fix", str(project.root), "--patch", str(project.root / "f.patch")]
    )
    assert result.exit_code == 2
