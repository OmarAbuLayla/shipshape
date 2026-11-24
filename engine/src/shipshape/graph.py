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


def build_graph(project: Project, findings: Sequence[Finding]) -> ProjectGraph:
    """Assemble nodes, edges and finding attachments for ``project``."""
    local_names = project.local_module_names()
    nodes: dict[str, GraphNode] = {}
    for source in project.sources:
        nodes[source.path] = _source_node(source, local_names)
    for rel in project.files_matching(*ENVIRONMENT_FILES, max_depth=3):
        parent = str(PurePosixPath(rel).parent)
        nodes[rel] = GraphNode(
            id=rel,
            kind=NodeKind.CONFIG,
            label=PurePosixPath(rel).name,
            parent=None if parent == "." else parent,
        )

    edges: list[GraphEdge] = []
    links, unresolved = resolve_imports(project)
    for link in links:
        kind = EdgeKind.TEST if nodes[link.source].kind is NodeKind.TEST else EdgeKind.IMPORT
        edges.append(
            GraphEdge(
                source=link.source,
                target=link.target,
                kind=kind,
                names=link.names,
                line=link.line,
            )
        )
    for source in project.parsed:
        assert source.tree is not None
        if source.is_test:  # tests use made-up absolute paths on purpose; they are not data
            continue
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

    _add_folders(nodes)
    project_findings: list[int] = []
    for index, finding in enumerate(findings):
        attached = False
        for location in finding.locations:
            path = location.path
            if path == "." and finding.check_id in GHOSTS:
                ghost_id, label = GHOSTS[finding.check_id]
                path = ghost_id
                nodes.setdefault(
                    ghost_id, GraphNode(id=ghost_id, kind=NodeKind.MISSING, label=label)
                )
            elif path not in nodes and path != "." and path in project.files:
                parent = str(PurePosixPath(path).parent)
                nodes[path] = GraphNode(
                    id=path,
                    kind=NodeKind.CONFIG,
                    label=PurePosixPath(path).name,
                    parent=None if parent == "." else parent,
                )
            node = nodes.get(path)
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

    _add_folders(nodes)  # config nodes created while attaching may live in new folders
    return ProjectGraph(
        nodes=sorted(nodes.values(), key=lambda n: (n.kind != NodeKind.FOLDER, n.id)),
        edges=edges,
        project_findings=project_findings,
        unresolved_imports=unresolved,
    )
