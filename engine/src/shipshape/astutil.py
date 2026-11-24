"""Small helpers on top of :mod:`ast` shared by several checks."""

from __future__ import annotations

import ast
import re
from collections.abc import Iterator

_WORD = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|\d+")
_DOCSTRING_OWNERS = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)


def split_words(identifier: str) -> list[str]:
    """Split ``snake_case``, ``camelCase`` or free text into lowercase words."""
    words: list[str] = []
    for part in re.split(r"[^A-Za-z0-9]+", identifier):
        words.extend(word.lower() for word in _WORD.findall(part))
    return words


def docstring_ids(tree: ast.AST) -> set[int]:
    """Return ``id()`` of every docstring constant, so callers can skip them."""
    ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, _DOCSTRING_OWNERS) and node.body:
            first = node.body[0]
            if (
                isinstance(first, ast.Expr)
                and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)
            ):
                ids.add(id(first.value))
    return ids


def string_constants(tree: ast.AST) -> Iterator[ast.Constant]:
    """Yield string literals that are not docstrings."""
    skip = docstring_ids(tree)
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in skip:
            yield node


def dotted_name(node: ast.expr) -> str:
    """Return ``a.b.c`` for names and attribute chains; calls resolve to their callee."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = dotted_name(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    if isinstance(node, ast.Call):
        return dotted_name(node.func)
    return ""


def calls(tree: ast.AST) -> Iterator[ast.Call]:
    """Yield every call expression."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            yield node


def call_name(call: ast.Call) -> str:
    """Dotted name of the called function, e.g. ``np.random.seed``."""
    return dotted_name(call.func)


def last_name(call: ast.Call) -> str:
    """Last component of the called name, e.g. ``seed`` for ``np.random.seed``."""
    return call_name(call).rsplit(".", 1)[-1]


def get_keyword(call: ast.Call, name: str) -> ast.keyword | None:
    """Return the keyword argument ``name`` if present."""
    return next((kw for kw in call.keywords if kw.arg == name), None)


def is_constant(node: ast.expr | None, value: object) -> bool:
    """True if ``node`` is the literal ``value`` (compared by identity for None/True/False)."""
    return isinstance(node, ast.Constant) and node.value is value


def has_main_guard(tree: ast.Module) -> bool:
    """True if the module has an ``if __name__ == "__main__":`` block."""
    for node in tree.body:
        if isinstance(node, ast.If) and isinstance(node.test, ast.Compare):
            left = node.test.left
            if isinstance(left, ast.Name) and left.id == "__name__":
                return True
    return False


def imported_names(tree: ast.AST) -> set[str]:
    """Dotted names of everything imported, including ``pkg.module.name`` for from-imports."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module:
                names.add(module)
            names.update(f"{module}.{alias.name}".lstrip(".") for alias in node.names)
    return names


def top_level_imports(tree: ast.AST) -> set[str]:
    """First component of every absolute import, e.g. ``numpy`` for ``numpy.linalg``."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module.split(".")[0])
    return names


def functions(tree: ast.AST) -> Iterator[ast.FunctionDef | ast.AsyncFunctionDef]:
    """Yield every function and method definition."""
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            yield node
