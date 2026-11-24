from collections.abc import Callable
from pathlib import Path

import pytest

from shipshape.project import Project

ENGINE_DIR = Path(__file__).resolve().parents[1]
FIXTURES_DIR = ENGINE_DIR / "corpus" / "fixtures"

MakeProject = Callable[[dict[str, str]], Project]


@pytest.fixture
def make_project(tmp_path: Path) -> MakeProject:
    """Write ``{relative_path: content}`` into a temp folder and load it as a Project."""

    def _make(files: dict[str, str]) -> Project:
        for rel, content in files.items():
            path = tmp_path / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        return Project.load(tmp_path)

    return _make
