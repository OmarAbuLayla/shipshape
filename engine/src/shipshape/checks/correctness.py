"""Checks for code that runs but can give wrong or misleading results."""

from __future__ import annotations

import ast
import re
from typing import ClassVar

from shipshape.astutil import calls, last_name, split_words
from shipshape.checks.base import Check, plural
from shipshape.models import Dimension, Finding, Location, Severity
from shipshape.project import Project, SourceFile

# Words that usually name the unit samples must not be split across, most meaningful first:
# when a file mentions both `subject` and `recording`, the subject is the unit to report.
GROUP_WORDS: tuple[str, ...] = (
    "subject",
    "patient",
    "participant",
    "speaker",
    "donor",
    "person",
    "individual",
    "paper",
    "session",
    "recording",
)
SPLIT_FUNCTIONS = frozenset({"train_test_split", "random_split"})
SAMPLE_SPLITTERS = frozenset(
    {
        "KFold",
        "StratifiedKFold",
        "ShuffleSplit",
        "StratifiedShuffleSplit",
        "RepeatedKFold",
        "RepeatedStratifiedKFold",
    }
)
GROUP_SPLITTERS = frozenset(
    {
        "GroupKFold",
        "GroupShuffleSplit",
        "LeaveOneGroupOut",
        "LeavePGroupsOut",
        "StratifiedGroupKFold",
    }
)
_IDENTIFIER_LIKE = re.compile(r"[A-Za-z_][A-Za-z0-9_ ]{0,39}")


def _singular(word: str) -> str:
    return word[:-1] if word.endswith("s") and len(word) > 4 else word


def _names_in(node: ast.AST) -> list[str]:
    if isinstance(node, ast.Name):
        return [node.id]
    if isinstance(node, ast.Attribute):
        return [node.attr]
    if isinstance(node, ast.arg):
        return [node.arg]
    if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
        return [node.name]
    if isinstance(node, ast.keyword) and node.arg:
        return [node.arg]
    if (
        isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and _IDENTIFIER_LIKE.fullmatch(node.value)
    ):
        return [node.value]
    return []


def group_mentions(tree: ast.AST) -> dict[str, int]:
    """Map each group word used in identifiers or short strings to its first line."""
    seen: dict[str, int] = {}
    for node in ast.walk(tree):
        line = getattr(node, "lineno", None)
        if not isinstance(line, int):
            continue
        for name in _names_in(node):
            for word in (_singular(w) for w in split_words(name)):
                if word in GROUP_WORDS and line < seen.get(word, line + 1):
                    seen[word] = line
    return seen


def _uses_group_split(tree: ast.AST) -> bool:
    return any(
        last_name(call) in GROUP_SPLITTERS or any(kw.arg == "groups" for kw in call.keywords)
        for call in calls(tree)
    )


def _is_modulo_filter(node: ast.expr) -> bool:
    """True for ``i % 5 == 4``-style conditions, a common hand-rolled split."""
    if not (isinstance(node, ast.Compare) and isinstance(node.left, ast.BinOp)):
        return False
    divisor = node.left.right
    return (
        isinstance(node.left.op, ast.Mod)
        and isinstance(divisor, ast.Constant)
        and isinstance(divisor.value, int)
        and 2 <= divisor.value <= 20
    )


def sample_split_sites(tree: ast.AST) -> list[int]:
    """Line numbers where data is split sample by sample."""
    lines = [
        call.lineno for call in calls(tree) if last_name(call) in SPLIT_FUNCTIONS | SAMPLE_SPLITTERS
    ]
    for node in ast.walk(tree):
        if isinstance(node, ast.comprehension):
            lines.extend(cond.lineno for cond in node.ifs if _is_modulo_filter(cond))
    return sorted(set(lines))


class GroupedSplitLeakage(Check):
    """Sample-wise splits in code that also tracks subjects, patients, papers and similar."""

    id: ClassVar[str] = "correctness.grouped-split-leakage"
    title: ClassVar[str] = "Test data may share subjects with training data"
    severity: ClassVar[Severity] = Severity.CRITICAL
    dimension: ClassVar[Dimension] = Dimension.CORRECTNESS
    concept: ClassVar[str] = "Data leakage in evaluation"

    def run(self, project: Project) -> list[Finding]:
        """Flag files that split per sample while a grouping variable is in scope."""
        return [f for source in project.parsed if (f := self._check(source)) is not None]

    def _check(self, source: SourceFile) -> Finding | None:
        assert source.tree is not None
        sites = sample_split_sites(source.tree)
        if not sites or _uses_group_split(source.tree):
            return None
        mentions = group_mentions(source.tree)
        if not mentions:
            return None
        word = min(mentions, key=GROUP_WORDS.index)
        line = mentions[word]
        message = (
            f"Data is split sample by sample, but this file also tracks `{word}` "
            f"(first on line {line}). If samples from the same {word} end up on both the "
            f"training and the test side, the test score partly measures how well the model "
            f"remembers that {word}, so it will look better than it really is. Use a "
            f"group-aware split (for example GroupShuffleSplit with groups set to the {word} "
            f"ids), unless mixing is intended for this experiment."
        )
        return self.finding(
            message,
            [source.location(site) for site in sites],
            evidence=f"group variable `{word}`, {plural(len(sites), 'split site')}",
        )


def _is_silent(body: list[ast.stmt]) -> bool:
    return all(
        isinstance(stmt, ast.Pass | ast.Continue)
        or (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant))
        for stmt in body
    )


class SwallowedException(Check):
    """``except:`` or ``except Exception: pass`` that hides every error."""

    id: ClassVar[str] = "correctness.swallowed-exception"
    title: ClassVar[str] = "Errors are silently swallowed"
    severity: ClassVar[Severity] = Severity.MAJOR
    dimension: ClassVar[Dimension] = Dimension.CORRECTNESS
    concept: ClassVar[str] = "Handling errors on purpose"

    def run(self, project: Project) -> list[Finding]:
        """Collect bare excepts and broad excepts whose body does nothing.

        A handler whose ``except`` line carries a comment is treated as deliberate: the
        author has explained why ignoring the error is safe, which is what we teach.
        """
        locations: list[Location] = []
        for source in project.parsed:
            assert source.tree is not None
            lines = source.text.splitlines()
            for node in ast.walk(source.tree):
                if not isinstance(node, ast.ExceptHandler):
                    continue
                if "#" in lines[node.lineno - 1].split("except", 1)[-1]:
                    continue
                broad = node.type is None or (
                    isinstance(node.type, ast.Name)
                    and node.type.id in {"Exception", "BaseException"}
                )
                if broad and (node.type is None or _is_silent(node.body)):
                    locations.append(source.location(node.lineno))
        if not locations:
            return []
        message = (
            f"In {plural(len(locations), 'place')}, every exception is caught and then ignored, "
            f"or a bare `except:` catches even Ctrl+C. Errors disappear silently, so a "
            f"broken run can look like a successful one. Catch the specific exception you "
            f"expect, and log or re-raise everything else."
        )
        return [self.finding(message, locations)]
