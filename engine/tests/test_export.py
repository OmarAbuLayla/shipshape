"""Exports must work for plain scans and for scans with AI explanations."""

import csv
import io
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from shipshape.analyzer import analyze
from shipshape.cli import app
from shipshape.export import ExportFormat, export, format_for_path
from shipshape.models import Edit, Explanation, FixStatus, Report

from .conftest import FIXTURES_DIR


def _plain() -> Report:
    return analyze(FIXTURES_DIR / "leaky_emg")


def _explained() -> Report:
    report = _plain()
    finding = next(f for f in report.findings if f.check_id == "repro.hardcoded-path")
    finding.explanation = Explanation(
        summary="DATA_DIR only exists on one laptop.",
        what="train.py reads from a Desktop folder.",
        why="Nobody else can run it.",
        how_to_fix="1. Read the path from an environment variable.",
        behaviour_change="Default data folder becomes data/raw.",
        edits=[
            Edit(path="train.py", search='DATA_DIR = "C:/x"', replace='DATA_DIR = os.environ["D"]')
        ],
        fix_status=FixStatus.VERIFIED,
        model="deepseek-flash",
    )
    return report


def test_markdown_without_ai_lists_every_finding_with_its_message() -> None:
    report = _plain()

    text = export(report, ExportFormat.MARKDOWN)

    assert text.startswith("# Shipshape report: leaky_emg")
    assert "## Fix first (critical)" in text
    for finding in report.findings:
        assert finding.title in text
    assert "Data is split sample by sample" in text  # detector message used when no AI text


def test_markdown_with_ai_includes_explanation_fix_and_heads_up() -> None:
    text = export(_explained(), ExportFormat.MARKDOWN)

    assert "> DATA_DIR only exists on one laptop." in text
    assert "**Why it matters.** Nobody else can run it." in text
    assert "```diff" in text and '+ DATA_DIR = os.environ["D"]' in text
    assert "**Heads-up:** Default data folder becomes data/raw." in text


def test_csv_has_one_row_per_location_and_ai_columns() -> None:
    report = _explained()

    rows = list(csv.DictReader(io.StringIO(export(report, ExportFormat.CSV))))

    assert len(rows) == sum(len(f.locations) for f in report.findings)
    path_row = next(r for r in rows if r["check_id"] == "repro.hardcoded-path")
    assert (path_row["path"], path_row["line"]) == ("train.py", "7")
    assert path_row["fix_status"] == "verified"
    assert next(r for r in rows if r["check_id"] == "testing.no-tests")["ai_summary"] == ""


def test_json_round_trips() -> None:
    report = _explained()

    assert Report.model_validate(json.loads(export(report, ExportFormat.JSON))) == report


def test_exports_never_contain_a_hardcoded_secret() -> None:
    report = analyze(FIXTURES_DIR / "secrets_and_env")

    for fmt in ExportFormat:
        assert "abcd1234efgh5678ijkl9012" not in export(report, fmt)


@pytest.mark.parametrize(
    ("name", "fmt"), [("r.md", "md"), ("r.markdown", "md"), ("R.CSV", "csv"), ("r.json", "json")]
)
def test_format_from_extension(name: str, fmt: str) -> None:
    assert format_for_path(name).value == fmt


def test_cli_export_and_bad_extension(tmp_path: Path) -> None:
    out = tmp_path / "findings.md"
    runner = CliRunner()

    ok = runner.invoke(app, ["analyze", str(FIXTURES_DIR / "leaky_emg"), "--export", str(out)])
    bad = runner.invoke(
        app, ["analyze", str(FIXTURES_DIR / "leaky_emg"), "--export", str(tmp_path / "x.pdf")]
    )

    assert ok.exit_code == 0, ok.output
    assert out.read_text(encoding="utf-8").startswith("# Shipshape report")
    assert bad.exit_code == 2
