"""Checks for whether anything verifies that the code does what it claims."""

from __future__ import annotations

from typing import ClassVar

from shipshape.astutil import imported_names
from shipshape.checks.base import Check, examples, plural
from shipshape.models import Dimension, Finding, Location, Severity
from shipshape.project import Project, SourceFile

NOT_MODULES = frozenset({"__init__.py", "__main__.py", "setup.py", "conftest.py"})
MIN_MODULE_LINES = 10
UNTESTED_SHARE = 0.5


def code_modules(project: Project, min_lines: int = MIN_MODULE_LINES) -> list[SourceFile]:
    """Non-test ``.py`` modules with at least ``min_lines`` lines of code."""
    return [
        s
        for s in project.python_files
        if not s.is_test and s.name not in NOT_MODULES and s.code_lines >= min_lines
    ]


class NoTests(Check):
    """A multi-module project with no tests at all."""

    id: ClassVar[str] = "testing.no-tests"
    title: ClassVar[str] = "No tests"
    severity: ClassVar[Severity] = Severity.MAJOR
    dimension: ClassVar[Dimension] = Dimension.TESTING
    concept: ClassVar[str] = "Writing your first tests"

    def run(self, project: Project) -> list[Finding]:
        """Flag projects with two or more real modules and no test files."""
        if any(s.is_test for s in project.sources):
            return []
        modules = code_modules(project)
        if len(modules) < 2:
            return []
        largest = max(modules, key=lambda s: s.code_lines)
        message = (
            f"The project has {plural(len(modules), 'module')} and no tests. Tests are how an "
            f"engineer trusts code they didn't write, and how you know a change didn't break "
            f"something. Start with two or three small pytest tests for `{largest.path}`, "
            f"the largest module."
        )
        return [self.finding(message, [Location(path=".")])]


class UntestedModules(Check):
    """Tests exist, but most modules are never imported by them."""

    id: ClassVar[str] = "testing.untested-modules"
    title: ClassVar[str] = "Most modules have no tests"
    severity: ClassVar[Severity] = Severity.MINOR
    dimension: ClassVar[Dimension] = Dimension.TESTING
    concept: ClassVar[str] = "Test coverage where it matters"

    def run(self, project: Project) -> list[Finding]:
        """Compare modules of 10+ lines of code against the names imported by test files."""
        tests = [s for s in project.parsed if s.is_test]
        if not tests:
            return []
        tokens: set[str] = set()
        for test in tests:
            assert test.tree is not None
            for name in imported_names(test.tree):
                tokens.update(name.split("."))
        modules = code_modules(project)
        untested = [m for m in modules if m.stem not in tokens]
        if len(untested) < 2 or len(untested) / len(modules) < UNTESTED_SHARE:
            return []
        message = (
            f"{len(untested)} of {len(modules)} modules are never imported by a test "
            f"({examples([m.path for m in untested])}). Bugs there are only found by users. "
            f"Add at least one test per module, starting with the ones that compute results."
        )
        return [self.finding(message, [Location(path=m.path) for m in untested])]
