"""Checks for how the code is organised across files and functions."""

from __future__ import annotations

import ast
from collections import defaultdict
from collections.abc import Iterable, Iterator
from difflib import SequenceMatcher
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
DUPLICATE_SIMILARITY = 0.8  # share of matching lines for a renamed copy


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
    """The same package copied into several folders, a stand-in for version control.

    Packages with the same folder name are compared by their file names. Packages with
    different names (``data`` and ``data_old``) are compared by content as well, so a renamed
    copy is found without flagging unrelated packages that happen to share file names.
    """

    id: ClassVar[str] = "structure.duplicated-package"
    title: ClassVar[str] = "Same package copied in several places"
    severity: ClassVar[Severity] = Severity.MAJOR
    dimension: ClassVar[Dimension] = Dimension.STRUCTURE
    concept: ClassVar[str] = "Version control instead of copies"

    def run(self, project: Project) -> list[Finding]:
        """Compare every pair of packages; report each copied pair once (outermost first)."""
        dirs = sorted(
            {
                PurePosixPath(rel).parent.as_posix()
                for rel in project.files
                if PurePosixPath(rel).name == "__init__.py" and "/" in rel
            },
            key=lambda d: (d.count("/"), d),
        )
        contents = {
            d: {f[len(d) + 1 :] for f in project.files if f.startswith(d + "/")} for d in dirs
        }
        texts = {s.path: s.text for s in project.sources}
        reported: list[tuple[str, str]] = []
        findings = []
        for i, first in enumerate(dirs):
            for second in dirs[i + 1 :]:
                if _nested(first, second) or any(
                    _inside(first, a) and _inside(second, b) for a, b in reported
                ):
                    continue
                overlap = _package_overlap(first, second, contents, texts)
                if overlap is None:
                    continue
                reported.append((first, second))
                findings.append(self._finding(first, second, overlap))
        return findings

    def _finding(self, first: str, second: str, overlap: float) -> Finding:
        name_a, name_b = PurePosixPath(first).name, PurePosixPath(second).name
        if name_a == name_b:
            what = (
                f"The package `{name_a}` exists in two places (`{first}` and `{second}`) and "
                f"{overlap:.0%} of their files have the same names."
            )
            evidence = f"{overlap:.0%} file overlap"
        else:
            what = (
                f"`{first}` and `{second}` are copies of each other under different names: "
                f"{overlap:.0%} of their files are the same or nearly the same."
            )
            evidence = f"{overlap:.0%} of files (nearly) identical"
        message = (
            f"{what} Copies drift apart silently: a bug fixed in one stays in the other, and "
            f"nobody knows which is current. Keep one copy under git and use branches or "
            f"configuration for the variants; if one copy is unused, delete it."
        )
        return self.finding(
            message, [Location(path=first), Location(path=second)], evidence=evidence
        )


def _inside(path: str, folder: str) -> bool:
    return path == folder or path.startswith(folder + "/")


def _nested(first: str, second: str) -> bool:
    return _inside(first, second) or _inside(second, first)


def _similar(a: str, b: str) -> bool:
    """Same text, or nearly: at least DUPLICATE_SIMILARITY of the lines match."""
    if a == b:
        return True
    return SequenceMatcher(None, a.splitlines(), b.splitlines()).ratio() >= DUPLICATE_SIMILARITY


def _package_overlap(
    first: str, second: str, contents: dict[str, set[str]], texts: dict[str, str]
) -> float | None:
    """Share of files the two packages have in common, or ``None`` if they are not copies."""
    union = contents[first] | contents[second]
    if len(union) < DUPLICATE_MIN_FILES:
        return None
    shared = contents[first] & contents[second]
    if PurePosixPath(first).name != PurePosixPath(second).name:
        shared = {
            f
            for f in shared
            if f"{first}/{f}" in texts
            and f"{second}/{f}" in texts
            and _similar(texts[f"{first}/{f}"], texts[f"{second}/{f}"])
        }
    overlap = len(shared) / len(union)
    return overlap if overlap >= DUPLICATE_OVERLAP else None


NOT_LIBRARY_MODULES = frozenset(
    {"__init__.py", "__main__.py", "setup.py", "conftest.py", "noxfile.py", "manage.py"}
)
EXAMPLE_FOLDERS = frozenset({"examples", "example", "docs", "scripts", "notebooks", "benchmarks"})


def _is_library_project(project: Project) -> bool:
    """Installable packages expose modules to their users, so "unused here" means little."""
    return bool(project.files_matching("setup.py", "setup.cfg", max_depth=1)) or any(
        "[project]" in s or "[tool.poetry]" in s
        for s in (
            (project.root / rel).read_text(encoding="utf-8", errors="replace")
            for rel in project.files_matching("pyproject.toml", max_depth=1)
        )
    )


def _runs_on_its_own(tree: ast.Module) -> bool:
    """True for scripts: a ``__main__`` guard or top-level code beyond definitions."""
    quiet = (
        ast.Import,
        ast.ImportFrom,
        ast.FunctionDef,
        ast.AsyncFunctionDef,
        ast.ClassDef,
        ast.Assign,
        ast.AnnAssign,
        ast.Pass,
    )
    for statement in tree.body:
        if isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Constant):
            continue  # docstring
        if not isinstance(statement, quiet):
            return True  # an if __name__ == "__main__" block, a call, a loop, ...
    return False


class UnusedModule(Check):
    """Modules no other file imports and that do not run anything themselves: dead code."""

    id: ClassVar[str] = "structure.unused-module"
    title: ClassVar[str] = "Modules nothing uses"
    severity: ClassVar[Severity] = Severity.MINOR
    dimension: ClassVar[Dimension] = Dimension.STRUCTURE
    concept: ClassVar[str] = "Keeping code lean"

    def run(self, project: Project) -> list[Finding]:
        """Flag library-style modules no file (code, test or notebook) imports.

        Scripts (top-level code or a ``__main__`` guard), package ``__init__`` files, example
        folders and installable libraries (whose modules are meant for other projects) are
        left out, and so are projects whose files never import each other.
        """
        if _is_library_project(project):
            return []
        links, _ = resolve_imports(project)
        imported = {link.target for link in links if link.source != link.target}
        if not imported:
            return []  # loose files that never import each other: nothing to be unused by
        unused = [
            source.path
            for source in project.python_files
            if source.path not in imported
            and not source.is_test
            and source.name not in NOT_LIBRARY_MODULES
            and not EXAMPLE_FOLDERS & set(source.dir_parts)
            and source.tree is not None
            and source.tree.body
            and not _runs_on_its_own(source.tree)
        ]
        if not unused:
            return []
        message = (
            f"{plural(len(unused), 'module is', 'modules are')} never imported by any other "
            f"file, test or notebook, and {'it does' if len(unused) == 1 else 'they do'} not "
            f"run anything on {'its' if len(unused) == 1 else 'their'} own "
            f'({examples(unused)}). Dead code still gets read, searched and "fixed", and it '
            f"makes the project look bigger than it is. Delete it (git keeps the history), or "
            f"import it where it was meant to be used."
        )
        return [self.finding(message, [Location(path=path) for path in unused])]


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
