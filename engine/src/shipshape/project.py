"""Load a project from disk once, so every check can share the parsed result."""

from __future__ import annotations

import ast
import fnmatch
import warnings
from bisect import bisect_right
from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath

from shipshape.models import Location
from shipshape.notebooks import NotebookError, notebook_to_source
from shipshape.scanner import discover_files

MAX_SOURCE_BYTES = 1_000_000  # larger files are almost always generated or data
TEST_DIR_NAMES = frozenset({"tests", "test"})


def count_code_lines(text: str) -> int:
    """Count lines that are neither blank nor pure comments."""
    return sum(
        1 for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")
    )


def _parse(text: str) -> ast.Module | None:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return ast.parse(text)
    except (SyntaxError, ValueError):
        return None


@dataclass(frozen=True)
class SourceFile:
    """A Python file or notebook, with its parsed syntax tree (``None`` if it does not parse)."""

    path: str
    text: str
    tree: ast.Module | None
    code_lines: int
    cell_starts: tuple[int, ...] = ()

    @property
    def is_notebook(self) -> bool:
        """True for ``.ipynb`` files."""
        return self.path.endswith(".ipynb")

    @property
    def name(self) -> str:
        """File name without directories."""
        return PurePosixPath(self.path).name

    @property
    def stem(self) -> str:
        """File name without directories or extension."""
        return PurePosixPath(self.path).stem

    @property
    def dir_parts(self) -> tuple[str, ...]:
        """Directory names between the project root and this file."""
        return PurePosixPath(self.path).parts[:-1]

    @property
    def is_test(self) -> bool:
        """True for test modules (pytest naming conventions or a ``tests`` folder)."""
        return (
            self.name.startswith("test_")
            or self.name.endswith("_test.py")
            or self.name == "conftest.py"
            or any(part in TEST_DIR_NAMES for part in self.dir_parts)
        )

    def location(self, start_line: int | None = None, end_line: int | None = None) -> Location:
        """Build a ``Location``, translating notebook lines into (cell, line-in-cell)."""
        if not self.cell_starts or start_line is None:
            return Location(path=self.path, start_line=start_line, end_line=end_line)
        index = max(bisect_right(self.cell_starts, start_line) - 1, 0)
        base = self.cell_starts[index]
        next_start = self.cell_starts[index + 1] if index + 1 < len(self.cell_starts) else None
        in_cell_end = None
        if end_line is not None and (next_start is None or end_line < next_start):
            in_cell_end = end_line - base + 1
        return Location(
            path=self.path, cell=index + 1, start_line=start_line - base + 1, end_line=in_cell_end
        )


@dataclass(frozen=True)
class Project:
    """Everything the checks need to know about a project."""

    root: Path
    sources: tuple[SourceFile, ...]
    files: tuple[str, ...]

    @property
    def name(self) -> str:
        """Folder name of the project."""
        return self.root.name

    @property
    def parsed(self) -> list[SourceFile]:
        """Sources whose syntax tree is available."""
        return [s for s in self.sources if s.tree is not None]

    @property
    def python_files(self) -> list[SourceFile]:
        """Parsed ``.py`` files (no notebooks)."""
        return [s for s in self.parsed if not s.is_notebook]

    def files_matching(self, *patterns: str, max_depth: int | None = None) -> list[str]:
        """Return project files whose name matches any glob pattern, optionally depth-limited."""
        matches = []
        for rel in self.files:
            path = PurePosixPath(rel)
            if max_depth is not None and len(path.parts) > max_depth:
                continue
            if any(fnmatch.fnmatch(path.name, pattern) for pattern in patterns):
                matches.append(rel)
        return matches

    def local_module_names(self) -> set[str]:
        """Names a project's own imports can resolve to: module stems and their folder names."""
        names: set[str] = set()
        for rel in self.files:
            path = PurePosixPath(rel)
            if path.suffix in {".py", ".ipynb"}:
                names.add(path.stem)
                names.update(path.parts[:-1])
        return names

    def with_texts(self, texts: dict[str, str]) -> Project:
        """A copy of the project in which the given files have new contents (in memory only)."""
        sources = tuple(
            SourceFile(
                s.path, texts[s.path], _parse(texts[s.path]), count_code_lines(texts[s.path])
            )
            if s.path in texts
            else s
            for s in self.sources
        )
        return replace(self, sources=sources)

    @classmethod
    def load(cls, root: Path) -> Project:
        """Read and parse every Python file and notebook under ``root``."""
        root = root.resolve()
        sources: list[SourceFile] = []
        files: list[str] = []
        for path in discover_files(root):
            rel = path.relative_to(root).as_posix()
            files.append(rel)
            if path.suffix not in {".py", ".ipynb"}:
                continue
            try:
                if path.stat().st_size > MAX_SOURCE_BYTES:
                    continue
                raw = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if path.suffix == ".ipynb":
                try:
                    text, starts = notebook_to_source(raw)
                except NotebookError:
                    continue
            else:
                text, starts = raw, ()
            sources.append(SourceFile(rel, text, _parse(text), count_code_lines(text), starts))
        return cls(root=root, sources=tuple(sources), files=tuple(files))
