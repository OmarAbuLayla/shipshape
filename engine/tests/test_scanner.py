from pathlib import Path

import pytest

from shipshape.scanner import discover_python_files


def _touch(root: Path, rel: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x = 1\n", encoding="utf-8")


def test_finds_project_files_and_skips_environments(tmp_path: Path) -> None:
    files = ["train.py", "pkg/model.py", ".venv/lib/site.py", "pkg/__pycache__/m.py", "notes.txt"]
    for rel in files:
        _touch(tmp_path, rel)

    found = [p.relative_to(tmp_path).as_posix() for p in discover_python_files(tmp_path)]

    assert found == ["pkg/model.py", "train.py"]


def test_ignored_name_above_root_does_not_hide_project(tmp_path: Path) -> None:
    root = tmp_path / "venv" / "my_project"
    _touch(root, "main.py")

    assert [p.name for p in discover_python_files(root)] == ["main.py"]


def test_rejects_non_directory(tmp_path: Path) -> None:
    with pytest.raises(NotADirectoryError):
        discover_python_files(tmp_path / "missing")
