from shipshape.project import SourceFile, count_code_lines

from .conftest import MakeProject


def test_loads_sources_and_keeps_unparsable_files(make_project: MakeProject) -> None:
    project = make_project(
        {"ok.py": "x = 1\n", "broken.py": "def (:\n", "notes.md": "hi", ".venv/lib/a.py": "y = 2"}
    )

    paths = {s.path: s for s in project.sources}
    assert set(paths) == {"ok.py", "broken.py"}
    assert paths["ok.py"].tree is not None
    assert paths["broken.py"].tree is None
    assert "notes.md" in project.files


def test_notebook_location_is_translated_to_cell_and_line() -> None:
    source = SourceFile("nb.ipynb", "a\nb\nc\nd\n", None, 4, cell_starts=(1, 3))

    location = source.location(4)

    assert (location.cell, location.start_line) == (2, 2)


def test_test_files_are_recognised(make_project: MakeProject) -> None:
    project = make_project({"tests/helpers.py": "", "test_x.py": "", "pkg/model.py": ""})

    assert {s.path for s in project.sources if s.is_test} == {"tests/helpers.py", "test_x.py"}


def test_count_code_lines_ignores_blank_and_comment_lines() -> None:
    assert count_code_lines("x = 1\n\n# note\n  # indented note\ny = 2\n") == 2
