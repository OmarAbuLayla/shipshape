"""Checks for how the code is organised across files and functions."""

from __future__ import annotations

import ast
from collections import defaultdict
from collections.abc import Iterable, Iterator
from pathlib import PurePosixPath
from typing import Any, ClassVar

from radon.complexity import cc_visit
from radon.visitors import Class

from shipshape.astutil import top_level_imports
from shipshape.checks.base import Check, examples, plural
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
            try:
                blocks = cc_visit(source.text)
            except (SyntaxError, ValueError):
                continue
            for block in _flatten(blocks):
                complexity: int = block.complexity
                if complexity < COMPLEXITY_LIMIT:
                    continue
                name: str = f"{block.classname}.{block.name}" if block.classname else block.name
                hits.append((complexity, name, source.location(block.lineno, block.endline)))
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
