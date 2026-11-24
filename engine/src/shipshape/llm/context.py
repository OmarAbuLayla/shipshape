"""Collect the code an LLM needs to explain one finding, and nothing more.

Only the enclosing function (or a small window) around each location is sent, plus the top
of the file so imports can be edited. Credentials are replaced with ``<REDACTED_n>``
placeholders before anything leaves the machine; :class:`Redactions` maps them back when a
fix is applied locally. ``.env`` files and other non-Python files are never sent.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from shipshape.checks.security import VENDOR_KEY, secret_values
from shipshape.models import Finding
from shipshape.project import Project, SourceFile

MAX_LOCATIONS = 3  # explain a few representative places, not all 112 prints
MAX_BLOCK_LINES = 60  # larger enclosing functions fall back to a window
WINDOW = 12
MAX_HEADER_LINES = 30
MAX_PROJECT_FILES = 40


@dataclass
class Redactions:
    """Placeholder <-> secret mapping for one request. Never serialised or logged."""

    by_value: dict[str, str] = field(default_factory=dict)

    def placeholder(self, secret: str) -> str:
        """Return (and remember) the placeholder for ``secret``."""
        if secret not in self.by_value:
            self.by_value[secret] = f"<REDACTED_{len(self.by_value) + 1}>"
        return self.by_value[secret]

    def redact(self, text: str) -> str:
        """Replace every known secret in ``text`` with its placeholder."""
        for secret, placeholder in sorted(self.by_value.items(), key=lambda kv: -len(kv[0])):
            text = text.replace(secret, placeholder)
        return VENDOR_KEY.sub(lambda m: self.placeholder(m.group(0)), text)

    def restore(self, text: str) -> str:
        """Put the real values back into text coming from the model (for local use only)."""
        for secret, placeholder in self.by_value.items():
            text = text.replace(placeholder, secret)
        return text

    def contains_placeholder(self, text: str) -> bool:
        """True if ``text`` still mentions a placeholder (e.g. a fix that keeps the secret)."""
        return bool(re.search(r"<REDACTED_\d+>", text))


@dataclass(frozen=True)
class FindingContext:
    """The user-message body for one finding, plus what is needed to apply fixes."""

    text: str
    files: tuple[str, ...]  # Python files whose code was shown (fixes may only touch these)
    sent_locations: tuple[tuple[str, int], ...]  # (path, line) of the locations shown
    redactions: Redactions


def _block_for(tree: ast.Module, line: int) -> tuple[int, int] | None:
    """Smallest function/class around ``line`` that is short enough to show whole."""
    best: tuple[int, int] | None = None
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            continue
        start = min([node.lineno, *(d.lineno for d in node.decorator_list)])
        end = node.end_lineno or node.lineno
        fits = start <= line <= end and end - start < MAX_BLOCK_LINES
        if fits and (best is None or end - start < best[1] - best[0]):
            best = (start, end)
    return best


def _header_end(source: SourceFile) -> int:
    """Last line of the module docstring/import block, capped."""
    assert source.tree is not None
    end = 0
    for node in source.tree.body:
        is_doc = isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)
        if isinstance(node, ast.Import | ast.ImportFrom) or (is_doc and end == 0):
            end = node.end_lineno or node.lineno
        elif end:
            break
    return min(end, MAX_HEADER_LINES)


def _merge(ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
    merged: list[tuple[int, int]] = []
    for start, end in sorted(ranges):
        if merged and start <= merged[-1][1] + 1:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return merged


def _file_section(source: SourceFile, lines_flagged: list[int]) -> str:
    assert source.tree is not None
    text_lines = source.text.splitlines()
    ranges: list[tuple[int, int]] = []
    header = _header_end(source)
    if header:
        ranges.append((1, header))
    for line in lines_flagged:
        block = _block_for(source.tree, line)
        ranges.append(block or (max(1, line - WINDOW), min(len(text_lines), line + WINDOW)))
    parts = [f"### File: {source.path}"]
    for start, end in _merge(ranges):
        flagged = [n for n in lines_flagged if start <= n <= end]
        note = f" (flagged: line {', '.join(map(str, flagged))})" if flagged else ""
        parts.append(f"--- lines {start}-{end}{note} ---")
        parts.append("\n".join(text_lines[start - 1 : end]))
    return "\n".join(parts)


def _project_overview(project: Project) -> str:
    rows = [
        f"- {s.path} ({s.code_lines} lines{', test' if s.is_test else ''})"
        for s in sorted(project.python_files, key=lambda s: -s.code_lines)[:MAX_PROJECT_FILES]
    ]
    others = [
        f
        for f in project.files
        if PurePosixPath(f).suffix in {".txt", ".toml", ".yml", ".yaml", ".cfg"}
    ]
    return "\n".join(
        ["### Project files", *rows, "", "### Config files", *(f"- {f}" for f in others[:20])]
    )


def build_context(project: Project, finding: Finding, fix_allowed: bool) -> FindingContext:
    """Describe ``finding`` and show the relevant code, with credentials redacted."""
    redactions = Redactions()
    for parsed in project.parsed:
        assert parsed.tree is not None
        for secret in secret_values(parsed.tree):
            redactions.placeholder(secret)

    by_path = {s.path: s for s in project.python_files}
    flagged: dict[str, list[int]] = {}
    sent: list[tuple[str, int]] = []
    for location in finding.locations:
        source = by_path.get(location.path)
        if source is None or location.start_line is None or location.cell is not None:
            continue
        if len(sent) >= MAX_LOCATIONS:
            break
        flagged.setdefault(source.path, []).append(location.start_line)
        sent.append((source.path, location.start_line))

    where = ", ".join(
        loc.path + (f":{loc.start_line}" if loc.start_line else "")
        for loc in finding.locations[:10]
    )
    more = f" and {len(finding.locations) - 10} more" if len(finding.locations) > 10 else ""
    header = [
        f"Check: {finding.check_id}",
        f"Title: {finding.title}",
        f"Severity: {finding.severity.value}",
        f"Concept: {finding.concept}",
        f"Detector message: {finding.message}",
        f"Locations ({len(finding.locations)}): {where}{more}",
        f"FIX ALLOWED: {'yes' if fix_allowed and flagged else 'no'}",
    ]
    if len(sent) < len(finding.locations) and sent:
        header.append(f"Code is shown for {len(sent)} representative locations only.")
    sections = [_file_section(by_path[path], lines) for path, lines in flagged.items()]
    if not sections:
        sections = [_project_overview(project)]
    text = redactions.redact("\n".join(header) + "\n\n" + "\n\n".join(sections))
    return FindingContext(text, tuple(flagged), tuple(sent), redactions)
