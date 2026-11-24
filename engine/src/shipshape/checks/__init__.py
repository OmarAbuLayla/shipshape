"""All checks, in the order they run."""

from __future__ import annotations

from shipshape.checks.base import Check
from shipshape.checks.correctness import (
    ArrayNoneComparison,
    GroupedSplitLeakage,
    SwallowedException,
)
from shipshape.checks.readability import (
    MissingDocstrings,
    MissingTypeHints,
    PrintDebugging,
    RestatingComments,
)
from shipshape.checks.reproducibility import (
    HardcodedPath,
    MissingEnvironment,
    MissingSeed,
    UnpinnedDependencies,
)
from shipshape.checks.ruff import RULES, RuffCheck
from shipshape.checks.security import EnvFileNotIgnored, HardcodedSecret
from shipshape.checks.structure import (
    ComplexFunction,
    DuplicatedPackage,
    ImportCycle,
    OversizedFile,
)
from shipshape.checks.testing import NoTests, UntestedModules

__all__ = ["RULES", "Check", "default_checks"]


def default_checks() -> list[Check]:
    """Return a fresh instance of every built-in check."""
    return [
        GroupedSplitLeakage(),
        SwallowedException(),
        ArrayNoneComparison(),
        OversizedFile(),
        ComplexFunction(),
        DuplicatedPackage(),
        ImportCycle(),
        HardcodedPath(),
        MissingEnvironment(),
        UnpinnedDependencies(),
        MissingSeed(),
        EnvFileNotIgnored(),
        HardcodedSecret(),
        PrintDebugging(),
        RestatingComments(),
        MissingTypeHints(),
        MissingDocstrings(),
        NoTests(),
        UntestedModules(),
        RuffCheck(),
    ]
