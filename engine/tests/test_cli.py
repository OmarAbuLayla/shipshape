import json
from pathlib import Path

from typer.testing import CliRunner

from shipshape import __version__
from shipshape.cli import app

from .conftest import FIXTURES_DIR

runner = CliRunner()


def test_analyze_json_is_a_valid_report(tmp_path: Path) -> None:
    (tmp_path / "train.py").write_text("print('hi')\n", encoding="utf-8")

    result = runner.invoke(app, ["analyze", str(tmp_path), "--format", "json"])

    assert result.exit_code == 0, result.output
    report = json.loads(result.output)
    assert report["engine_version"] == __version__
    assert report["files_scanned"] == ["train.py"]
    assert report["findings"] == []
    assert report["grade"] == "A"


def test_analyze_text_shows_scorecard_and_findings() -> None:
    result = runner.invoke(app, ["analyze", str(FIXTURES_DIR / "leaky_emg")])

    assert result.exit_code == 0, result.output
    assert "Overall grade" in result.output
    assert "Test data may share subjects" in result.output


def test_analyze_writes_json_file(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("", encoding="utf-8")
    out = tmp_path / "report.json"

    result = runner.invoke(app, ["analyze", str(tmp_path), "-o", str(out)])

    assert result.exit_code == 0, result.output
    assert json.loads(out.read_text(encoding="utf-8"))["files_scanned"] == ["a.py"]


def test_analyze_missing_folder_exits_with_error(tmp_path: Path) -> None:
    result = runner.invoke(app, ["analyze", str(tmp_path / "nope")])

    assert result.exit_code == 2


def test_eval_strict_passes_on_fixture_corpus() -> None:
    result = runner.invoke(app, ["eval", str(FIXTURES_DIR), "--strict"])

    assert result.exit_code == 0, result.output


def test_checks_lists_every_check() -> None:
    result = runner.invoke(app, ["checks"], env={"COLUMNS": "160"})

    assert result.exit_code == 0
    assert "correctness.grouped-split-leakage" in result.output
    assert "lint.undefined-name" in result.output
