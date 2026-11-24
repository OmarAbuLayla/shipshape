"""Import resolution and map building."""

from pathlib import Path

from typer.testing import CliRunner

from shipshape.analyzer import analyze
from shipshape.checks.structure import ImportCycle, strongly_connected
from shipshape.cli import app
from shipshape.imports import resolve_imports
from shipshape.models import EdgeKind, NodeKind, Severity

from .conftest import FIXTURES_DIR, MakeProject


def _links(make_project: MakeProject, files: dict[str, str]) -> set[tuple[str, str]]:
    links, _ = resolve_imports(make_project(files))
    return {(link.source, link.target) for link in links}


def test_src_layout_package_import(make_project: MakeProject) -> None:
    links = _links(
        make_project,
        {
            "src/pkg/__init__.py": "",
            "src/pkg/a.py": "from pkg import b\nfrom pkg.c import helper\n",
            "src/pkg/b.py": "",
            "src/pkg/c.py": "def helper(): ...\n",
        },
    )

    assert links == {("src/pkg/a.py", "src/pkg/b.py"), ("src/pkg/a.py", "src/pkg/c.py")}


def test_relative_imports(make_project: MakeProject) -> None:
    links = _links(
        make_project,
        {
            "pkg/__init__.py": "X = 1\n",
            "pkg/a.py": "from . import b\nfrom .b import f\n",
            "pkg/b.py": "def f(): ...\n",
            "pkg/sub/__init__.py": "",
            "pkg/sub/c.py": "from ..b import f\nfrom .. import X\n",
        },
    )

    assert links == {
        ("pkg/a.py", "pkg/b.py"),
        ("pkg/sub/c.py", "pkg/b.py"),
        ("pkg/sub/c.py", "pkg/__init__.py"),
    }


def test_sibling_script_imports_and_nearest_duplicate(make_project: MakeProject) -> None:
    links = _links(
        make_project,
        {
            "train.py": "from data import prepare\nimport json\nimport numpy\n",
            "data.py": "def prepare(): ...\n",
            "x/main.py": "import utils\n",
            "x/utils.py": "",
            "y/utils.py": "",
        },
    )

    assert links == {("train.py", "data.py"), ("x/main.py", "x/utils.py")}


def test_unresolved_local_import_is_reported(make_project: MakeProject) -> None:
    _, unresolved = resolve_imports(
        make_project({"pkg/__init__.py": "", "pkg/a.py": "import pkg.missing\n"})
    )

    assert unresolved == ["pkg/a.py:1 pkg.missing"]


def test_strongly_connected_components() -> None:
    components = strongly_connected({"a": {"b"}, "b": {"a", "c"}, "c": set()})

    assert sorted(components) == [["a", "b"], ["c"]]


def test_child_importing_parent_package_is_not_a_cycle(make_project: MakeProject) -> None:
    project = make_project(
        {"pkg/__init__.py": "from pkg.a import f\n", "pkg/a.py": "from pkg import X\n"}
    )

    assert ImportCycle().run(project) == []


def test_graph_of_leaky_emg_fixture() -> None:
    report = analyze(FIXTURES_DIR / "leaky_emg")
    assert report.graph is not None
    nodes = {n.id: n for n in report.graph.nodes}
    edges = {(e.source, e.target, e.kind) for e in report.graph.edges}

    assert ("train.py", "data.py", EdgeKind.IMPORT) in edges
    assert ("train.py", "utils.py", EdgeKind.IMPORT) in edges
    assert ("train.py", "external:C:/Users/me/Desktop/emg_data_FINAL2", EdgeKind.READS) in edges
    assert nodes["missing:tests"].kind is NodeKind.MISSING
    assert nodes["train.py"].role == "entry"
    assert nodes["data.py"].worst_severity is Severity.CRITICAL
    assert nodes["data.py"].third_party == ["numpy", "sklearn"]
    assert nodes["requirements.txt"].kind is NodeKind.CONFIG


def test_graph_attaches_folder_findings_and_test_edges() -> None:
    report = analyze(FIXTURES_DIR / "big_and_tangled")
    assert report.graph is not None
    nodes = {n.id: n for n in report.graph.nodes}

    assert nodes["lab/core"].kind is NodeKind.FOLDER
    assert nodes["lab/core"].findings
    assert any(e.kind is EdgeKind.TEST for e in report.graph.edges)


def test_notebook_reads_external_path_with_cell_line() -> None:
    report = analyze(FIXTURES_DIR / "notebook_only")
    assert report.graph is not None

    reads = [e for e in report.graph.edges if e.kind is EdgeKind.READS]

    assert [(e.source, e.line) for e in reads] == [("analysis.ipynb", 1)]


def test_map_command_writes_html_with_embedded_report(tmp_path: Path) -> None:
    html = tmp_path / "map.html"

    result = CliRunner().invoke(
        app, ["map", str(FIXTURES_DIR / "leaky_emg"), "--html", str(html)], env={"COLUMNS": "120"}
    )

    assert result.exit_code == 0, result.output
    page = html.read_text(encoding="utf-8")
    assert "/*__REPORT__*/" not in page
    assert '"project_name":"leaky_emg"' in page
    assert "Most depended-on modules" in result.output
