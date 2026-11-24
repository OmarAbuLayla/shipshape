"""Ignore files, inline suppressions and the gentler handling of test files."""

from __future__ import annotations

import json

from shipshape.analyzer import analyze_project
from shipshape.checks.reproducibility import HardcodedPath
from shipshape.checks.security import HardcodedSecret
from shipshape.export import ExportFormat, export
from shipshape.ignore import Pattern, pragma_ids
from shipshape.models import Severity

from .conftest import MakeProject

PATH_LINE = 'DATA = "/home/alice/data/raw.csv"\n'


def test_patterns_follow_gitignore_rules() -> None:
    folder = Pattern("", "fixtures/")
    assert folder.matches("engine/corpus/fixtures/a/train.py")
    assert not folder.matches("engine/fixtures.py")
    anchored = Pattern("", "engine/corpus/fixtures/")
    assert anchored.matches("engine/corpus/fixtures/a/train.py")
    assert not anchored.matches("other/engine/corpus/fixtures/a.py")
    glob = Pattern("", "*_generated.py")
    assert glob.matches("pkg/api_generated.py")
    nested = Pattern("pkg", "old/")
    assert nested.matches("pkg/old/x.py")
    assert not nested.matches("old/x.py")


def test_pragma_parsing() -> None:
    assert pragma_ids("x = 1") is None
    assert pragma_ids("x = 1  # shipshape: ignore") == {"*"}
    assert pragma_ids("x = 1  # Shipshape: ignore[a.b, c.*]  why") == {"a.b", "c.*"}


def test_ignored_files_are_left_out_and_reported(make_project: MakeProject) -> None:
    project = make_project(
        {
            ".shipshapeignore": "# examples\nexamples/\n",
            "main.py": "def run() -> None:\n    pass\n",
            "examples/bad.py": PATH_LINE,
        }
    )
    assert "examples/bad.py" not in project.files
    report = analyze_project(project)
    assert not [f for f in report.findings if f.check_id == "repro.hardcoded-path"]
    assert report.exclusions.files_excluded == 1
    assert report.exclusions.patterns == ["examples/"]
    assert report.files_scanned == ["main.py"]


def test_disabled_checks_are_listed_not_hidden(make_project: MakeProject) -> None:
    project = make_project({".shipshapeignore": "check:repro.*\n", "main.py": PATH_LINE})
    report = analyze_project(project)
    assert not [f for f in report.findings if f.check_id.startswith("repro.")]
    assert report.exclusions.disabled_checks == ["repro.*"]
    assert any(s.check_id == "repro.hardcoded-path" for s in report.exclusions.suppressed)


def test_inline_comment_suppresses_only_its_own_line(make_project: MakeProject) -> None:
    project = make_project(
        {
            "a.py": 'A = "/home/alice/a.csv"  # shipshape: ignore[repro.hardcoded-path] demo\n',
            "b.py": PATH_LINE,
        }
    )
    report = analyze_project(project, [HardcodedPath()])
    (finding,) = report.findings
    assert [loc.path for loc in finding.locations] == ["b.py"]
    (suppressed,) = report.exclusions.suppressed
    assert suppressed.location.path == "a.py"
    assert suppressed.how == "inline comment"


def test_inline_comment_for_another_check_does_not_suppress(make_project: MakeProject) -> None:
    project = make_project({"a.py": 'A = "/home/alice/a.csv"  # shipshape: ignore[lint.*]\n'})
    report = analyze_project(project, [HardcodedPath()])
    assert len(report.findings) == 1
    assert not report.exclusions.suppressed


def test_inline_comment_works_in_notebooks(make_project: MakeProject) -> None:
    cells = [
        {"cell_type": "code", "source": ["import os\n"], "metadata": {}, "outputs": []},
        {
            "cell_type": "code",
            "source": ['P = "/home/alice/x.csv"  # shipshape: ignore\n'],
            "metadata": {},
            "outputs": [],
        },
    ]

    notebook = {"cells": cells, "metadata": {}, "nbformat": 4, "nbformat_minor": 5}
    project = make_project({"nb.ipynb": json.dumps(notebook)})
    report = analyze_project(project, [HardcodedPath()])
    assert not report.findings
    assert report.exclusions.suppressed[0].location.cell == 2


def test_paths_in_tests_are_not_flagged(make_project: MakeProject) -> None:
    project = make_project({"tests/test_paths.py": PATH_LINE})
    assert HardcodedPath().run(project) == []


def test_secrets_only_in_tests_are_minor(make_project: MakeProject) -> None:
    key = 'API_KEY = "Zx9vQ2mL7pR4tY8wK3nB6cD1"\n'
    project = make_project({"tests/test_client.py": key, "client.py": key})
    findings = HardcodedSecret().run(project)
    by_severity = {f.severity: [loc.path for loc in f.locations] for f in findings}
    assert by_severity == {
        Severity.CRITICAL: ["client.py"],
        Severity.MINOR: ["tests/test_client.py"],
    }


def test_exports_say_what_was_left_out(make_project: MakeProject) -> None:
    project = make_project({".shipshapeignore": "examples/\n", "examples/x.py": PATH_LINE})
    markdown = export(analyze_project(project), ExportFormat.MARKDOWN)
    assert "Not included in the scores" in markdown
    assert "1 file left out by .shipshapeignore" in markdown


def test_nothing_left_out_means_no_note(make_project: MakeProject) -> None:
    project = make_project({"main.py": "X = 1\n"})
    report = analyze_project(project)
    assert not report.exclusions.any
    assert "Not included" not in export(report, ExportFormat.MARKDOWN)
