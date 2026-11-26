"""All checks, in the order they run."""

from __future__ import annotations

from shipshape.checks.base import Check
from shipshape.checks.copies import CopiedFiles, DuplicatedPackage
from shipshape.checks.correctness import GroupedSplitLeakage, SwallowedException
from shipshape.checks.data_handling import ArrayNoneComparison, SilentDataSkip
from shipshape.checks.readability import (
    MissingDocstrings,
    MissingTypeHints,
    PrintDebugging,
    RestatingComments,
)
from shipshape.checks.reproducibility import (
    BrokenLocalImport,
    HardcodedPath,
    MissingEnvironment,
    MissingSeed,
    UnpinnedDependencies,
)
from shipshape.checks.ruff import RULES, RuffCheck
from shipshape.checks.security import EnvFileNotIgnored, HardcodedSecret
from shipshape.checks.structure import (
    ComplexFunction,
    ImportCycle,
    OversizedFile,
    UnusedModule,
)
from shipshape.checks.testing import NoTests, UntestedModules
from shipshape.checks.training import MissingEvalMode, MissingZeroGrad, TestSetSelection

__all__ = ["RULES", "Check", "default_checks"]


def default_checks() -> list[Check]:
    """Return a fresh instance of every built-in check."""
    return [
        GroupedSplitLeakage(),
        SwallowedException(),
        ArrayNoneComparison(),
        SilentDataSkip(),
        MissingZeroGrad(),
        MissingEvalMode(),
        TestSetSelection(),
        OversizedFile(),
        ComplexFunction(),
        DuplicatedPackage(),
        ImportCycle(),
        UnusedModule(),
        CopiedFiles(),
        HardcodedPath(),
        MissingEnvironment(),
        UnpinnedDependencies(),
        BrokenLocalImport(),
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
