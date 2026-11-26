"""Checks for how data is handled: comparisons that crash on DataFrames, and data that
silently goes missing."""

from __future__ import annotations

import ast
from typing import ClassVar

from shipshape.astutil import calls, dotted_name, last_name
from shipshape.checks.base import Check, plural
from shipshape.checks.correctness import _is_silent
from shipshape.models import Dimension, Finding, Severity
from shipshape.project import Project

ARRAY_MODULES = frozenset({"pd", "pandas", "np", "numpy"})
# Methods that only DataFrames, Series or arrays have, or that return one. Not ``join`` or
# ``copy``: strings and lists have those too.
FRAME_METHODS = frozenset(
    {
        "merge",
        "groupby",
        "dropna",
        "fillna",
        "isna",
        "notna",
        "sort_values",
        "reset_index",
        "set_index",
        "drop_duplicates",
        "astype",
        "query",
        "to_csv",
        "to_numpy",
        "reshape",
    }
)
FRAME_ATTRIBUTES = frozenset({"iloc", "loc", "shape", "columns", "dtypes", "values", "ndim"})


def _is_array_call(node: ast.expr) -> bool:
    """``pd.read_csv(...)``, ``np.zeros(...)``, ``df.merge(...)`` and the like."""
    if not isinstance(node, ast.Call):
        return False
    root = dotted_name(node.func).split(".", 1)[0]
    method = node.func.attr if isinstance(node.func, ast.Attribute) else ""
    return root in ARRAY_MODULES or method in FRAME_METHODS


def _array_names(scope: ast.AST) -> set[str]:
    """Names in ``scope`` that clearly hold a DataFrame, Series or array."""
    names: set[str] = set()
    for node in ast.walk(scope):
        if isinstance(node, ast.Assign) and _is_array_call(node.value):
            names.update(t.id for t in node.targets if isinstance(t, ast.Name))
        elif isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            if node.attr in FRAME_ATTRIBUTES or node.attr in FRAME_METHODS:
                names.add(node.value.id)
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "merge"
            and node.args
            and isinstance(node.args[0], ast.Name)
        ):
            names.add(node.args[0].id)  # whatever is merged into a DataFrame is one too
    return names


def _none_compared_name(node: ast.Compare) -> str | None:
    """The name in ``x == None`` / ``None != x``, if that is what ``node`` is."""
    if len(node.ops) != 1 or not isinstance(node.ops[0], ast.Eq | ast.NotEq):
        return None
    left, right = node.left, node.comparators[0]
    for name, other in ((left, right), (right, left)):
        if isinstance(name, ast.Name) and isinstance(other, ast.Constant) and other.value is None:
            return name.id
    return None


def array_none_comparisons(tree: ast.Module) -> list[int]:
    """Lines comparing a DataFrame or array to None with ``==`` or ``!=``.

    Each function is its own scope; code outside functions is one more scope.
    """
    scopes: list[ast.AST] = [
        n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)
    ]
    module_level = ast.Module(
        body=[
            s
            for s in tree.body
            if not isinstance(s, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
        ],
        type_ignores=[],
    )
    lines: set[int] = set()
    for scope in [*scopes, module_level]:
        arrays = _array_names(scope)
        for node in ast.walk(scope):
            if isinstance(node, ast.Compare) and _none_compared_name(node) in arrays:
                lines.add(node.lineno)
    return sorted(lines)


class ArrayNoneComparison(Check):
    """``df == None`` on a DataFrame or array: compares element-wise and then crashes."""

    id: ClassVar[str] = "correctness.array-none-comparison"
    title: ClassVar[str] = "`== None` on a DataFrame or array"
    severity: ClassVar[Severity] = Severity.MAJOR
    dimension: ClassVar[Dimension] = Dimension.CORRECTNESS
    concept: ClassVar[str] = "Idiomatic Python"

    def run(self, project: Project) -> list[Finding]:
        """Flag ``== None`` / ``!= None`` on names that clearly hold pandas or numpy data."""
        locations = [
            source.location(line)
            for source in project.parsed
            if source.tree is not None
            for line in array_none_comparisons(source.tree)
        ]
        if not locations:
            return []
        message = (
            f"In {plural(len(locations), 'place')}, a DataFrame or array is compared to None "
            f"with `==` or `!=`. That compares every element, and using the result in an `if` "
            f'raises "The truth value ... is ambiguous", so the code crashes exactly when the '
            f"data is there. Use `is None` / `is not None`."
        )
        return [self.finding(message, locations)]


EXISTS_CALLS = frozenset({"exists", "isfile", "isdir", "is_file", "is_dir"})
TYPE_FILTERS = frozenset({"isfile", "isdir", "is_file", "is_dir"})
# Loops over a folder listing: there, isdir()/isfile() filters entries, nothing is missing.
LISTING_CALLS = frozenset({"listdir", "scandir", "iterdir", "glob", "rglob", "iglob", "walk"})
MISSING_FILE_ERRORS = frozenset({"FileNotFoundError", "OSError", "IOError", "NotADirectoryError"})


def _is_missing_file_test(test: ast.expr, over_listing: bool) -> bool:
    """``not os.path.exists(p)``, ``not p.is_file()`` and the like.

    In a loop over a folder listing, ``isdir``/``isfile`` only sort entries, so they don't count.
    """
    if not (
        isinstance(test, ast.UnaryOp)
        and isinstance(test.op, ast.Not)
        and isinstance(test.operand, ast.Call)
    ):
        return False
    name = last_name(test.operand)
    return name in EXISTS_CALLS and not (over_listing and name in TYPE_FILTERS)


def _iterates_listing(loop: ast.AST) -> bool:
    iterable = getattr(loop, "iter", None)
    return iterable is not None and any(last_name(c) in LISTING_CALLS for c in calls(iterable))


def _catches_missing_file(handler: ast.ExceptHandler) -> bool:
    names = (
        handler.type.elts
        if isinstance(handler.type, ast.Tuple)
        else [handler.type]
        if handler.type is not None
        else []
    )
    return any(isinstance(n, ast.Name) and n.id in MISSING_FILE_ERRORS for n in names)


def silent_skip_sites(tree: ast.AST, text: str = "") -> list[int]:
    """Lines inside loops where a missing file or folder is skipped without a word.

    A skip whose ``if`` or ``except`` line carries a comment is treated as deliberate.
    """
    source_lines = text.splitlines()
    lines: list[int] = []
    for loop in ast.walk(tree):
        if not isinstance(loop, ast.For | ast.AsyncFor | ast.While):
            continue
        over_listing = _iterates_listing(loop)
        for node in ast.walk(loop):
            if isinstance(node, ast.If):
                silent = (
                    _is_missing_file_test(node.test, over_listing)
                    and not node.orelse
                    and _is_silent(node.body)
                )
            elif isinstance(node, ast.ExceptHandler):
                silent = _catches_missing_file(node) and _is_silent(node.body)
            else:
                continue
            explained = node.lineno <= len(source_lines) and "#" in source_lines[node.lineno - 1]
            if silent and not explained:
                lines.append(node.lineno)
    return sorted(set(lines))


class SilentDataSkip(Check):
    """Loops that quietly skip missing files or folders, so a wrong path shrinks the data."""

    id: ClassVar[str] = "correctness.silent-data-skip"
    title: ClassVar[str] = "Missing data is skipped without a word"
    severity: ClassVar[Severity] = Severity.MAJOR
    dimension: ClassVar[Dimension] = Dimension.CORRECTNESS
    concept: ClassVar[str] = "Handling errors on purpose"

    def run(self, project: Project) -> list[Finding]:
        """Flag ``if not exists(...): continue`` and ``except FileNotFoundError: continue``."""
        locations = [
            source.location(line)
            for source in project.parsed
            if source.tree is not None and not source.is_test
            for line in silent_skip_sites(source.tree, source.text)
        ]
        if not locations:
            return []
        message = (
            f"In {plural(len(locations), 'place')}, a loop skips a missing file or folder and "
            f"carries on without telling anyone. A wrong path, a typo or a half-copied dataset "
            f"then gives a smaller dataset instead of an error, and the results quietly change. "
            f"Count and report what was skipped (or stop if nothing should be missing)."
        )
        return [self.finding(message, locations)]
