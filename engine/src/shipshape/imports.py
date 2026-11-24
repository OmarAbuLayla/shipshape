"""Resolve a project's imports to the project's own files.

Python's real resolution depends on ``sys.path`` at run time, which a static scan cannot
know. We approximate it the way vibe-coded projects are actually run: every file is
reachable by any dotted suffix of its path (``src/pkg/mod.py`` answers to ``pkg.mod`` and
``mod``), so ``src/`` layouts, package imports and "import the file next to me" all work.
When several files match, the one closest to the importing file wins.
"""

from __future__ import annotations

import ast
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from shipshape.project import Project, SourceFile


@dataclass
class ImportLink:
    """``source`` imports ``target`` (both project-relative file paths)."""

    source: str
    target: str
    line: int
    module_level: bool
    names: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class _RawImport:
    module: str  # dotted name, "" for "from . import x"
    level: int  # 0 for absolute imports
    names: tuple[str, ...]  # imported names for from-imports, () for "import x"
    line: int
    module_level: bool


def _dotted_suffixes(path: str) -> list[str]:
    parts = list(PurePosixPath(path).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return [".".join(parts[i:]) for i in range(len(parts)) if parts[i:]]


def _raw_imports(tree: ast.Module) -> list[_RawImport]:
    found: list[_RawImport] = []

    def visit(node: ast.AST, in_function: bool) -> None:
        for child in ast.iter_child_nodes(node):
            nested = in_function or isinstance(
                child, ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda
            )
            if isinstance(child, ast.Import):
                found.extend(
                    _RawImport(alias.name, 0, (), child.lineno, not in_function)
                    for alias in child.names
                )
            elif isinstance(child, ast.ImportFrom):
                names = tuple(alias.name for alias in child.names)
                found.append(
                    _RawImport(
                        child.module or "", child.level, names, child.lineno, not in_function
                    )
                )
            visit(child, nested)

    visit(tree, in_function=False)
    return found


class ImportResolver:
    """Maps dotted module names and relative imports to project files."""

    def __init__(self, project: Project) -> None:
        self.files = {s.path for s in project.sources if not s.is_notebook}
        self.index: dict[str, list[str]] = defaultdict(list)
        for path in sorted(self.files):
            for name in _dotted_suffixes(path):
                self.index[name].append(path)
        self.local_tops = {name.split(".")[0] for name in self.index}

    def _nearest(self, candidates: list[str], importer: str) -> str:
        importer_dir = PurePosixPath(importer).parent.parts

        def shared(path: str) -> tuple[int, int]:
            parts = PurePosixPath(path).parent.parts
            common = 0
            for a, b in zip(importer_dir, parts, strict=False):
                if a != b:
                    break
                common += 1
            return (-common, len(parts))

        return min(candidates, key=shared)

    def absolute(self, dotted: str, importer: str) -> str | None:
        """Resolve ``pkg.mod`` to a file, or ``None`` for stdlib/third-party/unknown."""
        if not dotted or dotted.split(".")[0] in sys.stdlib_module_names:
            return None
        candidates = [c for c in self.index.get(dotted, []) if c != importer]
        return self._nearest(candidates, importer) if candidates else None

    def relative(self, module: str, level: int, importer: str) -> str | None:
        """Resolve ``from ..pkg import x`` relative to ``importer``'s folder."""
        base = PurePosixPath(importer).parent
        for _ in range(level - 1):
            base = base.parent
        target = base.joinpath(*module.split(".")) if module else base
        for candidate in (f"{target.as_posix()}.py", f"{target.as_posix()}/__init__.py"):
            normalized = candidate.removeprefix("./")
            if normalized in self.files:
                return normalized
        return None

    def resolve(self, source: SourceFile) -> tuple[list[ImportLink], list[str]]:
        """Return the file-to-file links of one source, plus imports that look local but fail."""
        assert source.tree is not None
        links: list[ImportLink] = []
        unresolved: list[str] = []
        for raw in _raw_imports(source.tree):
            targets: list[tuple[str, list[str]]] = []
            if raw.level:
                base = self.relative(raw.module, raw.level, source.path)
                for name in raw.names:
                    sub = self.relative(f"{raw.module}.{name}".strip("."), raw.level, source.path)
                    if sub:
                        targets.append((sub, []))
                    elif base:
                        targets.append((base, [name]))
                shown = "." * raw.level + raw.module
            else:
                base = self.absolute(raw.module, source.path)
                for name in raw.names:
                    sub = self.absolute(f"{raw.module}.{name}", source.path)
                    if sub and sub != base:
                        targets.append((sub, []))
                    elif base:
                        targets.append((base, [name]))
                if not raw.names and base:
                    targets.append((base, []))
                shown = raw.module
                if not targets and raw.module.split(".")[0] in self.local_tops:
                    unresolved.append(f"{source.path}:{raw.line} {shown}")
            if raw.level and not targets:
                unresolved.append(f"{source.path}:{raw.line} {shown}")
            links.extend(
                ImportLink(source.path, target, raw.line, raw.module_level, names)
                for target, names in targets
                if target != source.path
            )
        return links, unresolved


def resolve_imports(project: Project) -> tuple[list[ImportLink], list[str]]:
    """All internal import links of a project, merged per (source, target) pair."""
    resolver = ImportResolver(project)
    merged: dict[tuple[str, str], ImportLink] = {}
    unresolved: list[str] = []
    for source in project.parsed:
        links, missing = resolver.resolve(source)
        unresolved.extend(missing)
        for link in links:
            key = (link.source, link.target)
            if key not in merged:
                merged[key] = link
                continue
            existing = merged[key]
            existing.names = sorted(set(existing.names) | set(link.names))
            if link.module_level and not existing.module_level:
                existing.module_level, existing.line = True, link.line
            elif link.module_level == existing.module_level:
                existing.line = min(existing.line, link.line)
    return list(merged.values()), unresolved
