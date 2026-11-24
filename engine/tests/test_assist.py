"""Shipshape as tools for a coding assistant: scan text, fix gates, lessons, map, MCP server."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from shipshape import assist
from shipshape.mcp_server import server

from .conftest import MakeProject

LINT = "def collect(item, bucket=[]):\n    bucket.append(item)\n    return bucket\n"
FIXED = (
    "def collect(item, bucket=None):\n"
    "    if bucket is None:\n"
    "        bucket = []\n"
    "    bucket.append(item)\n"
    "    return bucket\n"
)


def _call(tool: str, arguments: dict[str, object]) -> str:
    result = asyncio.run(server.call_tool(tool, arguments))
    return "".join(getattr(block, "text", "") for block in getattr(result, "content", []))


def test_scan_lists_findings_with_check_ids_and_lessons(make_project: MakeProject) -> None:
    project = make_project({"lib.py": LINT})
    text = assist.scan(str(project.root))
    assert "grade" in text
    assert "(lint.mutable-default)" in text
    assert "lib.py:1" in text
    assert "lesson: mutable-defaults" in text


def test_scan_caps_the_number_of_findings(make_project: MakeProject) -> None:
    project = make_project({"lib.py": LINT + "import os\n", "b.py": "import sys\n"})
    text = assist.scan(str(project.root), max_findings=1)
    assert "more findings not shown" in text


def test_scan_rejects_a_missing_folder(tmp_path: Path) -> None:
    with pytest.raises(assist.AssistError, match="not a folder"):
        assist.scan(str(tmp_path / "nope"))


def test_verify_passes_a_real_fix_and_changes_nothing(make_project: MakeProject) -> None:
    project = make_project({"pkg/lib.py": LINT})
    edits = [assist.ProposedEdit(path="pkg\\lib.py", search=LINT, replace=FIXED)]
    message = assist.verify_edits(str(project.root), "lint.mutable-default", edits)
    assert message.startswith("PASSED")
    assert (project.root / "pkg" / "lib.py").read_text(encoding="utf-8") == LINT


def test_verify_rejects_a_fix_that_leaves_the_problem(make_project: MakeProject) -> None:
    project = make_project({"lib.py": LINT})
    edits = [
        assist.ProposedEdit(path="lib.py", search="return bucket", replace="return list(bucket)")
    ]
    with pytest.raises(assist.FixRejectedError, match="still reported"):
        assist.verify_edits(str(project.root), "lint.mutable-default", edits)


def test_verify_rejects_broken_code_and_unknown_search(make_project: MakeProject) -> None:
    project = make_project({"lib.py": LINT})
    broken = [assist.ProposedEdit(path="lib.py", search=LINT, replace="def collect(:\n")]
    with pytest.raises(assist.FixRejectedError, match="no longer parses"):
        assist.verify_edits(str(project.root), "lint.mutable-default", broken)
    missing = [assist.ProposedEdit(path="lib.py", search="not there", replace="x")]
    with pytest.raises(assist.FixRejectedError, match="does not appear"):
        assist.verify_edits(str(project.root), "lint.mutable-default", missing)


def test_verify_asks_for_a_new_scan_when_the_finding_is_gone(make_project: MakeProject) -> None:
    project = make_project({"lib.py": FIXED})
    with pytest.raises(assist.AssistError, match="scan again"):
        assist.verify_edits(str(project.root), "lint.mutable-default", [])


def test_lesson_by_check_id_and_listing() -> None:
    assert assist.lesson("lint.mutable-default").startswith("# Mutable default arguments")
    listing = assist.lesson("")
    assert "data-leakage" in listing
    assert assist.lesson("no-such-thing").startswith("No lesson matches")


def test_map_goes_to_the_given_file_not_the_project(
    make_project: MakeProject, tmp_path_factory: pytest.TempPathFactory
) -> None:
    project = make_project({"lib.py": LINT})
    output = tmp_path_factory.mktemp("out") / "map.html"
    written = assist.write_map(str(project.root), str(output))
    assert written == output.resolve()
    assert "<html" in output.read_text(encoding="utf-8").lower()
    assert not list(project.root.glob("*.html"))


def test_server_offers_the_four_tools() -> None:
    names = {tool.name for tool in asyncio.run(server.list_tools())}
    assert names == {"scan", "verify_fix", "lesson", "map"}


def test_server_reports_rejections_as_text_and_bad_paths_as_errors(
    make_project: MakeProject,
) -> None:
    project = make_project({"lib.py": LINT})
    edit = {"path": "lib.py", "search": "return bucket", "replace": "return list(bucket)"}
    text = _call(
        "verify_fix",
        {"path": str(project.root), "check_id": "lint.mutable-default", "edits": [edit]},
    )
    assert text.startswith("REJECTED")
    with pytest.raises(ToolError, match="not a folder"):
        _call("scan", {"path": str(project.root / "missing")})


def test_line_edits_replace_whole_lines_without_quoting_them(make_project: MakeProject) -> None:
    project = make_project({"lib.py": LINT})
    edits = [
        assist.ProposedEdit(
            path="lib.py",
            line=1,
            replace="def collect(item, bucket=None):\n    bucket = bucket or []",
        )
    ]
    message = assist.verify_edits(str(project.root), "lint.mutable-default", edits)
    assert message.startswith("PASSED")


def test_line_edits_outside_the_file_are_refused(make_project: MakeProject) -> None:
    project = make_project({"lib.py": LINT})
    edits = [assist.ProposedEdit(path="lib.py", line=2, end_line=9, replace="x")]
    with pytest.raises(assist.AssistError, match="outside"):
        assist.verify_edits(str(project.root), "lint.mutable-default", edits)
    both = [assist.ProposedEdit(path="lib.py", line=1, search="def", replace="x")]
    with pytest.raises(assist.AssistError, match="not both"):
        assist.verify_edits(str(project.root), "lint.mutable-default", both)


def test_passed_names_places_left_in_other_files(make_project: MakeProject) -> None:
    project = make_project({"a.py": LINT, "copy/b.py": LINT})
    edits = [assist.ProposedEdit(path="a.py", search=LINT, replace=FIXED)]
    message = assist.verify_edits(str(project.root), "lint.mutable-default", edits)
    assert "still reported elsewhere" in message
    assert "copy/b.py:1" in message


def test_scan_explains_scores_and_notebook_cells(make_project: MakeProject) -> None:
    project = make_project({"lib.py": LINT})
    text = assist.scan(str(project.root))
    assert "1 major -15" in text
    assert "How the grade works" in text
    assert "counts code cells only" in text
