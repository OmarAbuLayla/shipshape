"""Function blocks: line ranges, nesting, calls, and findings pinned to the right block."""

from __future__ import annotations

import json

from shipshape.analyzer import analyze_project
from shipshape.blocks import file_info
from shipshape.checks.reproducibility import HardcodedPath
from shipshape.models import Block, BlockKind, Finding, Location

from .conftest import MakeProject

CODE = '''"""A module."""
import os

DATA = "/home/alice/data.csv"


def load(path):
    """Load it."""
    return helper(path)


def helper(path):
    return os.path.exists(path)


class Trainer:
    def __init__(self):
        self.data = load(DATA)

    @staticmethod
    def tool():
        return 1

    def fit(self):
        for _ in range(3):
            self.step()
        return Trainer.tool()

    def step(self):
        pass


# a comment between definitions
if __name__ == "__main__":
    Trainer().fit()
'''


def _blocks(make_project: MakeProject, files: dict[str, str]) -> dict[str, Block]:
    project = make_project(files)
    info = file_info(project, [])
    return {b.name: b for i in info.values() for b in i.blocks}


def test_functions_classes_methods_and_module_code(make_project: MakeProject) -> None:
    blocks = _blocks(make_project, {"m.py": CODE})

    assert set(blocks) == {
        "load", "helper", "Trainer", "Trainer.__init__", "Trainer.tool", "Trainer.fit",
        "Trainer.step", "module code",
    }  # fmt: skip
    assert blocks["load"].kind is BlockKind.FUNCTION and blocks["load"].has_docstring
    assert (blocks["load"].start_line, blocks["load"].end_line) == (7, 9)
    assert blocks["Trainer.fit"].parent == "m.py::Trainer"
    assert blocks["Trainer.tool"].start_line == 20  # the decorator line belongs to the block
    assert blocks["Trainer.fit"].complexity == 2
    assert blocks["Trainer"].complexity == 2  # the most complex method
    assert blocks["module code"].kind is BlockKind.MODULE


def test_calls_are_linked_inside_the_file(make_project: MakeProject) -> None:
    blocks = _blocks(make_project, {"m.py": CODE})

    assert blocks["load"].calls == ["m.py::helper"]
    assert blocks["Trainer.__init__"].calls == ["m.py::load"]
    assert blocks["Trainer.fit"].calls == ["m.py::Trainer.step", "m.py::Trainer.tool"]
    assert blocks["module code"].calls == ["m.py::Trainer"]  # Trainer() under the main guard
    assert blocks["helper"].calls == []  # os.path.exists is in another module


def test_findings_go_to_the_innermost_block(make_project: MakeProject) -> None:
    project = make_project({"m.py": CODE})
    findings = [
        Finding(
            check_id="x", title="x", severity="minor", dimension="structure", concept="c",
            message="m",
            locations=[
                Location(path="m.py", start_line=26),  # inside Trainer.fit
                Location(path="m.py", start_line=4),  # top-level assignment
                Location(path="m.py", start_line=33),  # comment between definitions
                Location(path="."),
            ],
        )
    ]  # fmt: skip

    blocks = {b.name: b for b in file_info(project, findings)["m.py"].blocks}

    assert blocks["Trainer.fit"].findings == [0]
    assert blocks["Trainer"].findings == []
    assert blocks["module code"].findings == [0]


def test_notebook_cells_are_blocks(make_project: MakeProject) -> None:
    cells = [
        {"cell_type": "code", "source": ["import os\n"], "metadata": {}, "outputs": []},
        {"cell_type": "markdown", "source": ["# notes"], "metadata": {}},
        {
            "cell_type": "code",
            "source": ["def train():\n", "    return 1\n"],
            "metadata": {},
            "outputs": [],
        },
        {
            "cell_type": "code",
            "source": ['P = "/home/alice/x.csv"\n', "train()\n"],
            "metadata": {},
            "outputs": [],
        },
    ]
    notebook = {"cells": cells, "metadata": {}, "nbformat": 4, "nbformat_minor": 5}
    project = make_project({"nb.ipynb": json.dumps(notebook)})
    report = analyze_project(project, [HardcodedPath()])

    info = report.files["nb.ipynb"]
    blocks = {b.name: b for b in info.blocks}
    assert info.cell_starts == [1, 2, 4]
    assert [b.name for b in info.blocks if b.kind is BlockKind.CELL] == [
        "cell 1",
        "cell 2",
        "cell 3",
    ]
    assert blocks["train"].parent == "nb.ipynb::cell 2"
    assert blocks["cell 3"].calls == ["nb.ipynb::train"]
    assert blocks["cell 3"].findings == [0]  # finding at cell 3, line 1 -> scanned line 4
    assert "module code" not in blocks


def test_redefined_names_get_distinct_ids(make_project: MakeProject) -> None:
    project = make_project({"m.py": "def f():\n    pass\n\n\ndef f():\n    pass\n"})

    ids = [b.id for b in file_info(project, [])["m.py"].blocks if b.kind is BlockKind.FUNCTION]

    assert ids == ["m.py::f", "m.py::f@5"]


def test_broken_file_has_a_fingerprint_but_no_blocks(make_project: MakeProject) -> None:
    project = make_project({"bad.py": "def f(:\n", "ok.py": "X = 1\n"})

    info = file_info(project, [])

    assert info["bad.py"].blocks == []
    assert len(info["bad.py"].sha256) == 64
    assert [b.name for b in info["ok.py"].blocks] == ["module code"]
