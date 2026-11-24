"""Checks for how the code is organised across files and functions."""

from __future__ import annotations

import ast
from collections import defaultdict
from collections.abc import Iterable, Iterator
from itertools import pairwise
from pathlib import PurePosixPath
from typing import Any, ClassVar

from radon.complexity import cc_visit
from radon.visitors import Class

from shipshape.astutil import top_level_imports
from shipshape.checks.base import Check, examples, plural
from shipshape.imports import ImportLink, resolve_imports
from shipshape.models import Dimension, Finding, Location, Severity
from shipshape.project import Project

OVERSIZED_MINOR = 400  # lines of code
OVERSIZED_MAJOR = 700
COMPLEXITY_LIMIT = 15  # cyclomatic complexity
COMPLEXITY_MAJOR = 25
DUPLICATE_OVERLAP = 0.6
DUPLICATE_MIN_FILES = 3


class OversizedFile(Check):
    """Single files large enough that they almost certainly do several jobs."""

    id: ClassVar[str] = "structure.oversized-file"
    title: ClassVar[str] = "File is doing too many jobs"
    severity: ClassVar[Severity] = Severity.MAJOR
    dimension: ClassVar[Dimension] = Dimension.STRUCTURE
    concept: ClassVar[str] = "Separation of concerns"

    def run(self, project: Project) -> list[Finding]:
        """Flag each non-test ``.py`` file above the size thresholds."""
        findings = []
        for source in project.python_files:
            if source.is_test or source.code_lines < OVERSIZED_MINOR:
                continue
            assert source.tree is not None
            definitions = sum(
                isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
                for node in source.tree.body
            )
            packages = len(top_level_imports(source.tree))
            severity = Severity.MAJOR if source.code_lines >= OVERSIZED_MAJOR else Severity.MINOR
            defs = plural(definitions, "top-level definition")
            message = (
                f"`{source.path}` has {source.code_lines} lines of code, {defs} "
                f"and imports from {plural(packages, 'package')}. A file this size usually "
                f"mixes several jobs, which makes it hard to review, test or reuse any one of "
                f"them. Split it by responsibility, for example loading, processing, model, "
                f"and reporting."
            )
            findings.append(
                self.finding(
                    message,
                    [Location(path=source.path)],
                    evidence=f"{source.code_lines} lines of code",
                    severity=severity,
                )
            )
        return findings


def _flatten(blocks: Iterable[Any]) -> Iterator[Any]:
    for block in blocks:
        if isinstance(block, Class):
            yield from _flatten(block.methods)
            yield from _flatten(block.inner_classes)
        else:
            yield block
            yield from _flatten(block.closures)


def function_complexities(text: str) -> list[tuple[str, int, int, int]]:
    """(qualified name, cyclomatic complexity, first line, last line) of every function."""
    try:
        blocks = cc_visit(text)
    except (SyntaxError, ValueError):
        return []
    # radon lists methods both at the top level and inside their class, so the same function
    # can appear twice; a function is identified by the line its definition starts on.
    by_line: dict[int, tuple[str, int, int, int]] = {}
    for block in _flatten(blocks):
        name: str = f"{block.classname}.{block.name}" if block.classname else block.name
        line = int(block.lineno)
        known = by_line.get(line)
        if known is None or len(name) > len(known[0]):  # keep the qualified "Class.method" name
            by_line[line] = (name, int(block.complexity), line, int(block.endline))
    return sorted(by_line.values(), key=lambda item: item[2])


class ComplexFunction(Check):
    """Functions with so many branches that they are hard to follow and to test."""

    id: ClassVar[str] = "structure.complex-function"
    title: ClassVar[str] = "Functions with too many branches"
    severity: ClassVar[Severity] = Severity.MINOR
    dimension: ClassVar[Dimension] = Dimension.STRUCTURE
    concept: ClassVar[str] = "Keeping functions small"

    def run(self, project: Project) -> list[Finding]:
        """Report every function at or above the complexity limit, as one finding."""
        hits: list[tuple[int, str, Location]] = []
        for source in project.parsed:
            if source.is_test:
                continue
            for name, complexity, start, end in function_complexities(source.text):
                if complexity >= COMPLEXITY_LIMIT:
                    hits.append((complexity, name, source.location(start, end)))
        if not hits:
            return []
        hits.sort(key=lambda hit: hit[0], reverse=True)
        worst, worst_name, _ = hits[0]
        message = (
            f"{plural(len(hits), 'function has', 'functions have')} a cyclomatic complexity of "
            f"{COMPLEXITY_LIMIT} or more (highest: `{worst_name}` at {worst}). Each branch is "
            f"a separate path that needs its own test, and long if/elif chains hide bugs. "
            f"Split them into smaller functions or replace branch chains with a lookup table."
        )
        severity = Severity.MAJOR if worst >= COMPLEXITY_MAJOR else Severity.MINOR
        return [
            self.finding(
                message,
                [location for _, _, location in hits],
                evidence=examples([f"{name} ({cc})" for cc, name, _ in hits]),
                severity=severity,
            )
        ]


class DuplicatedPackage(Check):
    """The same package copied into several folders, a stand-in for version control."""

    id: ClassVar[str] = "structure.duplicated-package"
    title: ClassVar[str] = "Same package copied in several places"
    severity: ClassVar[Severity] = Severity.MAJOR
    dimension: ClassVar[Dimension] = Dimension.STRUCTURE
    concept: ClassVar[str] = "Version control instead of copies"

    def run(self, project: Project) -> list[Finding]:
        """Compare same-named packages by the overlap of their file lists."""
        packages: dict[str, list[str]] = defaultdict(list)
        for rel in project.files:
            path = PurePosixPath(rel)
            if path.name == "__init__.py" and len(path.parts) > 1:
                packages[path.parent.name].append(path.parent.as_posix())

        reported: list[tuple[str, str]] = []
        findings = []
        for name, dirs in sorted(packages.items(), key=lambda item: min(map(len, item[1]))):
            contents = {
                d: {f[len(d) + 1 :] for f in project.files if f.startswith(d + "/")} for d in dirs
            }
            for i, first in enumerate(dirs):
                for second in dirs[i + 1 :]:
                    if any(
                        first.startswith(a + "/") and second.startswith(b + "/")
                        for a, b in reported
                    ):
                        continue
                    union = contents[first] | contents[second]
                    if len(union) < DUPLICATE_MIN_FILES:
                        continue
                    overlap = len(contents[first] & contents[second]) / len(union)
                    if overlap < DUPLICATE_OVERLAP:
                        continue
                    reported.append((first, second))
                    message = (
                        f"The package `{name}` exists in two places (`{first}` and `{second}`) "
                        f"and {overlap:.0%} of their files have the same names. Copies drift "
                        f"apart silently: a bug fixed in one stays in the other, and nobody "
                        f"knows which is current. Keep one copy under git and use branches "
                        f"or configuration for the variants."
                    )
                    findings.append(
                        self.finding(
                            message,
                            [Location(path=first), Location(path=second)],
                            evidence=f"{overlap:.0%} file overlap",
                        )
                    )
        return findings


def strongly_connected(adjacency: dict[str, set[str]]) -> list[list[str]]:
    """Strongly connected components (Kosaraju, iterative so deep graphs cannot overflow)."""
    order: list[str] = []
    seen: set[str] = set()
    for start in sorted(adjacency):
        if start in seen:
            continue
        seen.add(start)
        stack: list[tuple[str, Iterator[str]]] = [(start, iter(sorted(adjacency[start])))]
        while stack:
            node, neighbours = stack[-1]
            nxt = next(neighbours, None)
            if nxt is None:
                stack.pop()
                order.append(node)
            elif nxt not in seen:
                seen.add(nxt)
                stack.append((nxt, iter(sorted(adjacency.get(nxt, ())))))
    reverse: dict[str, set[str]] = defaultdict(set)
    for node, targets in adjacency.items():
        for target in targets:
            reverse[target].add(node)
    components: list[list[str]] = []
    assigned: set[str] = set()
    for node in reversed(order):
        if node in assigned:
            continue
        assigned.add(node)
        component, pending = [], [node]
        while pending:
            current = pending.pop()
            component.append(current)
            for source in reverse[current] - assigned:
                assigned.add(source)
                pending.append(source)
        components.append(sorted(component))
    return components


def _shortest_cycle(start: str, adjacency: dict[str, set[str]], members: set[str]) -> list[str]:
    """Shortest path from ``start`` back to itself inside one component (breadth-first)."""
    previous: dict[str, str] = {}
    frontier = [start]
    while frontier:
        following = []
        for node in frontier:
            for target in sorted(adjacency.get(node, set()) & members):
                if target == start:
                    path = [node]
                    while path[-1] != start:
                        path.append(previous[path[-1]])
                    return [start, *reversed(path[:-1]), start]
                if target not in previous:
                    previous[target] = node
                    following.append(target)
        frontier = following
    return [start, start]


def _is_parent_package(link: ImportLink) -> bool:
    """A module importing its own package's ``__init__``: a common, usually harmless pattern."""
    target = PurePosixPath(link.target)
    return target.name == "__init__.py" and target.parent in PurePosixPath(link.source).parents


class ImportCycle(Check):
    """Modules that import each other, directly or in a loop."""

    id: ClassVar[str] = "structure.import-cycle"
    title: ClassVar[str] = "Modules import each other in a circle"
    severity: ClassVar[Severity] = Severity.MAJOR
    dimension: ClassVar[Dimension] = Dimension.STRUCTURE
    concept: ClassVar[str] = "Dependency direction"

    def run(self, project: Project) -> list[Finding]:
        """Find cycles among module-level imports of non-test modules."""
        tests = {s.path for s in project.sources if s.is_test}
        links, _ = resolve_imports(project)
        usable = [
            link
            for link in links
            if link.module_level
            and link.source not in tests
            and link.target not in tests
            and not _is_parent_package(link)
        ]
        adjacency: dict[str, set[str]] = defaultdict(set)
        line_of: dict[tuple[str, str], int] = {}
        for link in usable:
            adjacency[link.source].add(link.target)
            adjacency.setdefault(link.target, set())
            line_of[(link.source, link.target)] = link.line
        findings = []
        for component in strongly_connected(adjacency):
            if len(component) < 2:
                continue
            cycle = _shortest_cycle(component[0], adjacency, set(component))
            locations = [Location(path=a, start_line=line_of[(a, b)]) for a, b in pairwise(cycle)]
            chain = " → ".join(f"`{PurePosixPath(p).name}`" for p in cycle)
            others = len(component) - (len(cycle) - 1)
            extra = f" ({plural(others, 'more module')} in the same loop)" if others else ""
            message = (
                f"{chain} import each other at module level{extra}. Python then loads one of "
                f"them half-finished, which causes confusing ImportErrors that depend on which "
                f"file runs first, and it means neither module can be understood or tested "
                f"alone. Move the shared code into a third module both can import, or make the "
                f"dependency point one way."
            )
            findings.append(self.finding(message, locations, evidence=chain))
        return findings
