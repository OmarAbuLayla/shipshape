"""Build the architecture map: files and folders as nodes, imports and file reads as edges.

Findings are pinned to the node they belong to. Missing pieces (no tests, no environment
file) become dashed "ghost" nodes, and hard-coded data paths become external nodes, so the
map shows what is absent as well as what is there.
"""

from __future__ import annotations

import ast
import sys
from collections.abc import Sequence
from pathlib import PurePosixPath

from shipshape.astutil import has_main_guard, top_level_imports
from shipshape.checks.readability import CLI_LIBRARIES, ENTRY_POINT_NAMES, SCRIPT_DIRS
from shipshape.checks.reproducibility import ENVIRONMENT_FILES, absolute_paths
from shipshape.checks.structure import function_complexities
from shipshape.imports import resolve_imports
from shipshape.models import (
    SEVERITY_ORDER,
    EdgeKind,
    Finding,
    GraphEdge,
    GraphNode,
    NodeKind,
    ProjectGraph,
)
from shipshape.project import Project, SourceFile

# Project-wide findings that are drawn as a ghost node instead of floating unattached.
GHOSTS: dict[str, tuple[str, str]] = {
    "repro.missing-environment": ("missing:environment", "environment.yml"),
    "testing.no-tests": ("missing:tests", "tests/"),
}


def module_role(source: SourceFile) -> str:
    """Classify a source as test, notebook, script, entry point or library module."""
    if source.is_test:
        return "test"
    if source.is_notebook:
        return "notebook"
    if set(source.dir_parts) & SCRIPT_DIRS:
        return "script"
    if source.tree is not None and (
        source.name in ENTRY_POINT_NAMES
        or has_main_guard(source.tree)
        or top_level_imports(source.tree) & CLI_LIBRARIES
    ):
        return "entry"
    return "library"


def _short_path(value: str) -> str:
    parts = PurePosixPath(value.replace("\\", "/")).parts
    return value if len(parts) <= 3 else "…/" + "/".join(parts[-2:])


def _source_node(source: SourceFile, local_names: set[str]) -> GraphNode:
    parent = "/".join(source.dir_parts) or None
    kind = (
        NodeKind.TEST
        if source.is_test
        else NodeKind.NOTEBOOK
        if source.is_notebook
        else NodeKind.MODULE
    )
    functions = classes = complexity = 0
    third_party: list[str] = []
    if source.tree is not None:
        for node in ast.walk(source.tree):
            functions += isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
            classes += isinstance(node, ast.ClassDef)
        complexity = max((cc for _, cc, _, _ in function_complexities(source.text)), default=0)
        third_party = sorted(
            name
            for name in top_level_imports(source.tree)
            if name not in sys.stdlib_module_names
            and name not in local_names
            and name != "__future__"
        )
    return GraphNode(
        id=source.path,
        kind=kind,
        label=source.name,
        parent=parent,
        role=module_role(source),
        lines_of_code=source.code_lines,
        functions=functions,
        classes=classes,
        max_complexity=complexity,
        third_party=third_party,
    )


def _add_folders(nodes: dict[str, GraphNode]) -> None:
    """Create a folder node for every directory that encloses a node, if not present yet."""
    folders: set[str] = set()
    for node in list(nodes.values()):
        if node.parent is None:
            continue
        parts = PurePosixPath(node.parent).parts
        folders.update("/".join(parts[: i + 1]) for i in range(len(parts)))
    for folder in sorted(folders - nodes.keys()):
        nodes[folder] = GraphNode(
            id=folder,
            kind=NodeKind.FOLDER,
            label=PurePosixPath(folder).name + "/",
            parent=str(PurePosixPath(folder).parent) if "/" in folder else None,
        )


def _config_node(rel: str) -> GraphNode:
    """A node for a non-Python file such as ``requirements.txt``."""
    parent = str(PurePosixPath(rel).parent)
    return GraphNode(
        id=rel,
        kind=NodeKind.CONFIG,
        label=PurePosixPath(rel).name,
        parent=None if parent == "." else parent,
    )


def _import_edges(
    project: Project, nodes: dict[str, GraphNode]
) -> tuple[list[GraphEdge], list[str]]:
    """Import edges (test edges when the importer is a test) and the imports left unresolved."""
    links, unresolved = resolve_imports(project)
    edges = [
        GraphEdge(
            source=link.source,
            target=link.target,
            kind=EdgeKind.TEST if nodes[link.source].kind is NodeKind.TEST else EdgeKind.IMPORT,
            names=link.names,
            line=link.line,
        )
        for link in links
    ]
    return edges, unresolved


def _read_edges(project: Project, nodes: dict[str, GraphNode]) -> list[GraphEdge]:
    """External nodes for hard-coded absolute paths, and an edge from each file that uses one.

    Tests are skipped: they use made-up absolute paths on purpose, and those are not data.
    """
    edges = []
    for source in project.parsed:
        if source.is_test:
            continue
        assert source.tree is not None
        for value, line in absolute_paths(source.tree):
            external_id = f"external:{value}"
            nodes.setdefault(
                external_id,
                GraphNode(id=external_id, kind=NodeKind.EXTERNAL, label=_short_path(value)),
            )
            edges.append(
                GraphEdge(
                    source=source.path,
                    target=external_id,
                    kind=EdgeKind.READS,
                    line=source.location(line).start_line,
                )
            )
    return edges


def _node_for(
    path: str, check_id: str, nodes: dict[str, GraphNode], project: Project
) -> GraphNode | None:
    """The node a finding location belongs to, creating ghost or config nodes when needed."""
    if path == "." and check_id in GHOSTS:
        ghost_id, label = GHOSTS[check_id]
        return nodes.setdefault(
            ghost_id, GraphNode(id=ghost_id, kind=NodeKind.MISSING, label=label)
        )
    if path not in nodes and path != "." and path in project.files:
        nodes[path] = _config_node(path)
    return nodes.get(path)


def _attach_findings(
    findings: Sequence[Finding], nodes: dict[str, GraphNode], project: Project
) -> list[int]:
    """Pin each finding to its nodes; return the indices that belong to no node."""
    project_findings: list[int] = []
    for index, finding in enumerate(findings):
        attached = False
        for location in finding.locations:
            node = _node_for(location.path, finding.check_id, nodes, project)
            if node is None:
                continue
            if index not in node.findings:
                node.findings.append(index)
            attached = True
        if not attached:
            project_findings.append(index)
    for node in nodes.values():
        if node.findings:
            node.worst_severity = min(
                (findings[i].severity for i in node.findings), key=SEVERITY_ORDER.__getitem__
            )
    return project_findings


def build_graph(project: Project, findings: Sequence[Finding]) -> ProjectGraph:
    """Assemble nodes, edges and finding attachments for ``project``."""
    local_names = project.local_module_names()
    nodes = {source.path: _source_node(source, local_names) for source in project.sources}
    for rel in project.files_matching(*ENVIRONMENT_FILES, max_depth=3):
        nodes[rel] = _config_node(rel)
    edges, unresolved = _import_edges(project, nodes)
    edges += _read_edges(project, nodes)
    _add_folders(nodes)
    project_findings = _attach_findings(findings, nodes, project)
    _add_folders(nodes)  # config nodes created while attaching may live in new folders
    return ProjectGraph(
        nodes=sorted(nodes.values(), key=lambda n: (n.kind != NodeKind.FOLDER, n.id)),
        edges=edges,
        project_findings=project_findings,
        unresolved_imports=unresolved,
    )
