import json

import pytest

from shipshape.notebooks import NotebookError, notebook_to_source


def _notebook(*cells: tuple[str, str]) -> str:
    return json.dumps({"cells": [{"cell_type": kind, "source": source} for kind, source in cells]})


def test_code_cells_are_concatenated_with_start_lines() -> None:
    text, starts = notebook_to_source(
        _notebook(("code", "a = 1\nb = 2"), ("markdown", "# title"), ("code", "c = 3"))
    )

    assert text.splitlines() == ["a = 1", "b = 2", "c = 3"]
    assert starts == (1, 3)


def test_magics_and_broken_cells_are_blanked_but_keep_line_numbers() -> None:
    text, starts = notebook_to_source(
        _notebook(("code", "%matplotlib inline\nx = 1"), ("code", "broken ((("), ("code", "y = 2"))
    )

    assert text.splitlines() == ["", "x = 1", "", "y = 2"]
    assert starts == (1, 3, 4)


def test_invalid_json_raises() -> None:
    with pytest.raises(NotebookError):
        notebook_to_source("not json")
