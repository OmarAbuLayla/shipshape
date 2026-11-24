"""Checks for how easy the code is to read and use for someone who didn't write it."""

from __future__ import annotations

import ast
import io
import re
import tokenize
from typing import ClassVar

from shipshape.astutil import calls, functions, has_main_guard, split_words, top_level_imports
from shipshape.checks.base import Check, plural
from shipshape.models import Dimension, Finding, Location, Severity
from shipshape.project import Project, SourceFile

ENTRY_POINT_NAMES = frozenset({"main.py", "__main__.py", "cli.py", "app.py", "manage.py", "run.py"})
SCRIPT_DIRS = frozenset({"scripts", "examples", "bin", "tools", "notebooks", "demo", "demos"})
INTERFACE_WORDS = frozenset({"cli", "terminal", "console", "ui", "tui", "repl", "demo", "script"})
CLI_LIBRARIES = frozenset({"argparse", "typer", "click", "fire"})
PRINT_THRESHOLD = 5
RESTATING_THRESHOLD = 5
UNTYPED_SHARE = 0.5
UNDOCUMENTED_SHARE = 0.6
MIN_FUNCTIONS = 5
DOCSTRING_MIN_LINES = 8

IMPERATIVE_COMMENT = re.compile(
    r"^(?:this (?:function|method|class|code|line|block|loop|variable) "
    r"(?:is used to|will|does|is responsible for|is for)"
    r"|(?:loop|iterate) (?:through|over)\b"
    r"|(?:open|load|create|initiali[sz]e|define|set|get|call|return|calculate|compute|print|"
    r"import|loop|iterate|increment|append|add|check|save|read|write|convert|update|store|"
    r"declare|instantiate|close) (?:the|a|an|all|each|our|this|new)\b)",
    re.IGNORECASE,
)
REASONING = re.compile(
    r"\b(?:because|since|so that|to avoid|otherwise|workaround|why|instead|note|assum\w*|"
    r"hack|todo|fixme|bug|e\.g|i\.e)\b",
    re.IGNORECASE,
)
SKIP_COMMENT_PREFIXES = (
    "#!",
    "# type:",
    "# noqa",
    "# pylint",
    "# -*-",
    "# %%",
    "# fmt",
    "# pragma",
)
STOP_WORDS = frozenset(
    {"the", "this", "that", "and", "for", "with", "from", "into", "are", "all", "each", "then"}
    | {"its", "our", "will", "use", "uses", "used", "using", "here", "now", "just", "also"}
)


def is_library_module(source: SourceFile) -> bool:
    """True for importable modules, as opposed to scripts, entry points and user interfaces."""
    if source.is_notebook or source.is_test or source.tree is None:
        return False
    if source.name in ENTRY_POINT_NAMES or set(source.dir_parts) & SCRIPT_DIRS:
        return False
    if (set(split_words(source.stem)) | set(source.dir_parts)) & INTERFACE_WORDS:
        return False
    return not (has_main_guard(source.tree) or top_level_imports(source.tree) & CLI_LIBRARIES)


class PrintDebugging(Check):
    """``print`` calls inside modules that other code imports."""

    id: ClassVar[str] = "readability.print-debugging"
    title: ClassVar[str] = "print() used instead of logging"
    severity: ClassVar[Severity] = Severity.MINOR
    dimension: ClassVar[Dimension] = Dimension.READABILITY
    concept: ClassVar[str] = "Logging instead of printing"

    def run(self, project: Project) -> list[Finding]:
        """Count prints in library modules; scripts and command-line tools may print."""
        locations: list[Location] = []
        modules: set[str] = set()
        for source in project.sources:
            if not is_library_module(source):
                continue
            assert source.tree is not None
            for call in calls(source.tree):
                if isinstance(call.func, ast.Name) and call.func.id == "print":
                    locations.append(source.location(call.lineno))
                    modules.add(source.path)
        if len(locations) < PRINT_THRESHOLD:
            return []
        message = (
            f"{plural(len(locations), 'print() call')} in {plural(len(modules), 'module')} that "
            f"other code imports. Prints can't be turned down, filtered or redirected, so they "
            f"clutter the output of every program that uses these modules. Use the `logging` "
            f"module and keep print() for scripts and command-line output."
        )
        return [self.finding(message, locations)]


def _stem(word: str) -> str:
    for suffix in ("ing", "ed", "es", "s"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            return word[: -len(suffix)]
    return word


def _is_commented_out_code(body: str) -> bool:
    if not re.search(r"[=()\[\]:]", body):
        return False
    try:
        ast.parse(body)
    except SyntaxError:
        return False
    return True


def is_restating(body: str, next_code: str) -> bool:
    """True if a comment only repeats what the following line of code says."""
    if not body or REASONING.search(body) or _is_commented_out_code(body):
        return False
    if IMPERATIVE_COMMENT.match(body) and len(body.split()) <= 8:
        return True
    words = [w.lower() for w in re.findall(r"[A-Za-z]+", body) if len(w) >= 3]
    content = {_stem(w) for w in words if w not in STOP_WORDS}
    if not 1 <= len(content) <= 6:
        return False
    code_words = {_stem(w) for w in split_words(next_code)}
    return len(content & code_words) / len(content) >= 0.75


def restating_comments(source: SourceFile) -> list[tuple[int, str]]:
    """Return (line, text) of full-line comments that restate the next line of code."""
    lines = source.text.splitlines()
    found: list[tuple[int, str]] = []
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(source.text).readline))
    except (tokenize.TokenError, SyntaxError):
        return found
    for token in tokens:
        if token.type != tokenize.COMMENT:
            continue
        row, col = token.start
        if lines[row - 1][:col].strip() or token.string.startswith(SKIP_COMMENT_PREFIXES):
            continue
        next_code = next(
            (line for line in lines[row:] if line.strip() and not line.lstrip().startswith("#")),
            "",
        )
        body = token.string.lstrip("#").strip()
        if is_restating(body, next_code):
            found.append((row, body))
    return found


class RestatingComments(Check):
    """Comments that narrate the code instead of explaining it."""

    id: ClassVar[str] = "readability.restating-comments"
    title: ClassVar[str] = "Comments repeat the code"
    severity: ClassVar[Severity] = Severity.MINOR
    dimension: ClassVar[Dimension] = Dimension.READABILITY
    concept: ClassVar[str] = "Comments that earn their place"

    def run(self, project: Project) -> list[Finding]:
        """Collect restating comments across the project; report only if they are a habit."""
        hits: list[tuple[str, Location]] = []
        for source in project.parsed:
            hits.extend((text, source.location(row)) for row, text in restating_comments(source))
        if len(hits) < RESTATING_THRESHOLD:
            return []
        message = (
            f"{plural(len(hits), 'comment')} repeat what the next line already says, for "
            f"example “{hits[0][0]}”. They add reading time without adding "
            f"information, and they are a typical sign of unedited AI output. Delete them and "
            f"keep comments that explain why: a parameter choice, an assumption, a workaround."
        )
        return [self.finding(message, [loc for _, loc in hits], evidence=hits[0][0])]


FunctionNode = ast.FunctionDef | ast.AsyncFunctionDef


def _public_functions(project: Project) -> list[tuple[SourceFile, FunctionNode]]:
    result: list[tuple[SourceFile, FunctionNode]] = []
    for source in project.python_files:
        if source.is_test:
            continue
        assert source.tree is not None
        result.extend(
            (source, fn)
            for fn in functions(source.tree)
            if not fn.name.startswith("_") or fn.name == "__init__"
        )
    return result


def _is_typed(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    args = fn.args
    params = [*args.posonlyargs, *args.args, *args.kwonlyargs]
    params += [p for p in (args.vararg, args.kwarg) if p is not None]
    params = [p for p in params if p.arg not in {"self", "cls"}]
    if fn.returns is not None or any(p.annotation is not None for p in params):
        return True
    return fn.name == "__init__" and not params


class MissingTypeHints(Check):
    """Most public functions have no type hints."""

    id: ClassVar[str] = "readability.missing-type-hints"
    title: ClassVar[str] = "Functions without type hints"
    severity: ClassVar[Severity] = Severity.MINOR
    dimension: ClassVar[Dimension] = Dimension.READABILITY
    concept: ClassVar[str] = "Type hints as documentation"

    def run(self, project: Project) -> list[Finding]:
        """Report when at least half of the public functions are completely unannotated."""
        public = _public_functions(project)
        untyped = [(source, fn) for source, fn in public if not _is_typed(fn)]
        if len(public) < MIN_FUNCTIONS or len(untyped) / len(public) < UNTYPED_SHARE:
            return []
        message = (
            f"{len(untyped)} of {len(public)} public functions have no type hints at all. "
            f"Readers (and editors and AI tools) have to guess what goes in and what comes "
            f"out. Annotate parameters and return values, starting with the functions other "
            f"modules call."
        )
        return [self.finding(message, [s.location(fn.lineno) for s, fn in untyped])]


class MissingDocstrings(Check):
    """Most larger public functions and classes have no docstring."""

    id: ClassVar[str] = "readability.missing-docstrings"
    title: ClassVar[str] = "Larger functions without docstrings"
    severity: ClassVar[Severity] = Severity.MINOR
    dimension: ClassVar[Dimension] = Dimension.READABILITY
    concept: ClassVar[str] = "Documenting interfaces"

    def run(self, project: Project) -> list[Finding]:
        """Report when most public definitions of 8+ lines lack a docstring."""
        eligible: list[tuple[SourceFile, ast.AST, int]] = []
        for source in project.python_files:
            if source.is_test:
                continue
            assert source.tree is not None
            for node in ast.walk(source.tree):
                if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
                    continue
                length = (node.end_lineno or node.lineno) - node.lineno
                if node.name.startswith("_") or length < DOCSTRING_MIN_LINES:
                    continue
                eligible.append((source, node, node.lineno))
        missing = [
            (source, line)
            for source, node, line in eligible
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
            and ast.get_docstring(node) is None
        ]
        if len(eligible) < MIN_FUNCTIONS or len(missing) / len(eligible) < UNDOCUMENTED_SHARE:
            return []
        message = (
            f"{len(missing)} of {len(eligible)} public functions and classes longer than "
            f"{DOCSTRING_MIN_LINES} lines have no docstring. A one-line summary of what it "
            f"does and returns saves every reader from working it out from the body."
        )
        return [self.finding(message, [s.location(line) for s, line in missing])]
