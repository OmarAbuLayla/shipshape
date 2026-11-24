"""Function blocks: the level between the architecture map and the lines of code.

Every scanned file is split into blocks (top-level functions, classes and their methods, the
code cells of a notebook, and the module-level code around them), each anchored to a line range.
Findings are pinned to the innermost block that contains their line, and blocks that call each
other inside the same file are linked. Calls are matched by name, so they are a good guide,
not a complete call graph: calls through variables, other files or ``getattr`` are not seen.
"""

from __future__ import annotations

import ast
import hashlib
from collections.abc import Iterable, Sequence

from shipshape.checks.structure import function_complexities
from shipshape.models import Block, BlockKind, FileInfo, Finding, Location
from shipshape.project import Project, SourceFile, count_code_lines

FunctionNode = ast.FunctionDef | ast.AsyncFunctionDef
MODULE_NAME = "module code"


def absolute_line(source: SourceFile, location: Location) -> int | None:
    """A location's line in the scanned text (notebook cell lines translated back)."""
    if location.start_line is None:
        return None
    if location.cell is not None and source.cell_starts:
        return source.cell_starts[location.cell - 1] + location.start_line - 1
    return location.start_line


def _has_docstring(node: FunctionNode | ast.ClassDef) -> bool:
    first = node.body[0] if node.body else None
    return (
        isinstance(first, ast.Expr)
        and isinstance(first.value, ast.Constant)
        and isinstance(first.value.value, str)
    )


def _span(node: ast.stmt) -> tuple[int, int]:
    """First line (including decorators) and last line of a statement."""
    decorators = getattr(node, "decorator_list", [])
    start = min([node.lineno, *(d.lineno for d in decorators)])
    return start, node.end_lineno or node.lineno


def _called_names(nodes: Iterable[ast.AST]) -> tuple[set[str], set[tuple[str, str]]]:
    """Plain names called (``f()``, ``Cls()``) and ``obj.method()`` calls as (obj, method)."""
    plain: set[str] = set()
    dotted: set[tuple[str, str]] = set()
    for root in nodes:
        for node in ast.walk(root):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if isinstance(func, ast.Name):
                plain.add(func.id)
            elif isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
                dotted.add((func.value.id, func.attr))
    return plain, dotted


class _FileBlocks:
    """Builds the blocks of one parsed file."""

    def __init__(self, source: SourceFile) -> None:
        assert source.tree is not None
        self.source = source
        self.tree = source.tree
        self.lines = source.text.splitlines()
        self.complexity = {line: cc for _, cc, line, _ in function_complexities(source.text)}
        self.blocks: list[Block] = []
        self.nodes: dict[str, list[ast.AST]] = {}  # block id -> code that belongs to it
        self.class_of: dict[str, str] = {}  # method block id -> class block id

    def _code_lines(self, start: int, end: int) -> int:
        return count_code_lines("\n".join(self.lines[start - 1 : end]))

    def _add(self, name: str, kind: BlockKind, start: int, end: int, **extra: object) -> Block:
        block_id = f"{self.source.path}::{name}"
        if any(b.id == block_id for b in self.blocks):  # a name defined twice in one file
            block_id = f"{block_id}@{start}"
        block = Block(
            id=block_id,
            path=self.source.path,
            name=name,
            kind=kind,
            start_line=start,
            end_line=end,
            lines_of_code=self._code_lines(start, end),
            **extra,  # type: ignore[arg-type]
        )
        self.blocks.append(block)
        return block

    def _cell_of(self, line: int) -> str | None:
        cells = [b for b in self.blocks if b.kind is BlockKind.CELL]
        return next((c.id for c in cells if c.start_line <= line <= c.end_line), None)

    def build(self) -> list[Block]:
        starts = self.source.cell_starts
        for number, start in enumerate(starts, start=1):
            end = starts[number] - 1 if number < len(starts) else len(self.lines)
            self._add(f"cell {number}", BlockKind.CELL, start, max(start, end))
        loose: list[ast.stmt] = []  # top-level code outside functions and classes
        for node in self.tree.body:
            if isinstance(node, FunctionNode):
                self._function(node, BlockKind.FUNCTION, node.name, None)
            elif isinstance(node, ast.ClassDef):
                self._class(node)
            else:
                loose.append(node)
        if starts:  # in notebooks the cells hold the loose code
            for cell in [b for b in self.blocks if b.kind is BlockKind.CELL]:
                self.nodes[cell.id] = [
                    n for n in loose if cell.start_line <= n.lineno <= cell.end_line
                ]
        else:
            # Always present in .py files: findings on lines outside every function (top-level
            # code, a comment between functions) need a home.
            module = self._add(MODULE_NAME, BlockKind.MODULE, 1, max(1, len(self.lines)))
            module.lines_of_code = sum(self._code_lines(*_span(n)) for n in loose)
            self.nodes[module.id] = list(loose)
        self._link_calls()
        return self.blocks

    def _function(
        self, node: FunctionNode, kind: BlockKind, name: str, parent: str | None
    ) -> Block:
        start, end = _span(node)
        block = self._add(
            name,
            kind,
            start,
            end,
            parent=parent or self._cell_of(start),
            complexity=self.complexity.get(node.lineno, 1),
            has_docstring=_has_docstring(node),
        )
        self.nodes[block.id] = [node]
        return block

    def _class(self, node: ast.ClassDef) -> None:
        start, end = _span(node)
        block = self._add(
            node.name,
            BlockKind.CLASS,
            start,
            end,
            parent=self._cell_of(start),
            has_docstring=_has_docstring(node),
        )
        body: list[ast.AST] = []
        for item in node.body:
            if isinstance(item, FunctionNode):
                method = self._function(
                    item, BlockKind.METHOD, f"{node.name}.{item.name}", block.id
                )
                self.class_of[method.id] = block.id
                block.complexity = max(block.complexity, method.complexity)
            else:
                body.append(item)
        self.nodes[block.id] = body

    def _link_calls(self) -> None:
        top = {
            b.name: b.id
            for b in self.blocks
            if b.kind in (BlockKind.FUNCTION, BlockKind.CLASS) and "@" not in b.id
        }
        methods = {b.id: b for b in self.blocks if b.kind is BlockKind.METHOD}
        for block in self.blocks:
            plain, dotted = _called_names(self.nodes.get(block.id, []))
            targets = {top[name] for name in plain if name in top}
            owner = self.class_of.get(block.id)
            own_class = owner.split("::", 1)[1] if owner else None
            for obj, method in dotted:
                # self.x() / cls.x() inside a class, or SomeClass.x() for a class in this file
                cls = own_class if obj in {"self", "cls"} else obj
                target = f"{self.source.path}::{cls}.{method}"
                if cls is not None and target in methods:
                    targets.add(target)
            targets.discard(block.id)
            block.calls = sorted(targets)


def _innermost(blocks: Sequence[Block], line: int) -> Block | None:
    """The smallest block containing ``line``; module code only if nothing else does."""
    containing = [
        b for b in blocks if b.kind is not BlockKind.MODULE and b.start_line <= line <= b.end_line
    ]
    if containing:
        return min(containing, key=lambda b: b.end_line - b.start_line)
    return next((b for b in blocks if b.kind is BlockKind.MODULE), None)


def file_info(project: Project, findings: Sequence[Finding]) -> dict[str, FileInfo]:
    """Blocks, fingerprint and cell layout of every scanned file, with findings pinned."""
    infos: dict[str, FileInfo] = {}
    for source in project.sources:
        blocks = _FileBlocks(source).build() if source.tree is not None else []
        infos[source.path] = FileInfo(
            sha256=hashlib.sha256(source.text.encode("utf-8")).hexdigest(),
            lines=len(source.text.splitlines()),
            cell_starts=list(source.cell_starts),
            blocks=blocks,
        )
    by_path = {s.path: s for s in project.sources}
    for index, finding in enumerate(findings):
        for location in finding.locations:
            scanned = by_path.get(location.path)
            if scanned is None:
                continue
            line = absolute_line(scanned, location)
            block = _innermost(infos[scanned.path].blocks, line) if line is not None else None
            if block is not None and index not in block.findings:
                block.findings.append(index)
    return infos
