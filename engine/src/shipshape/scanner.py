"""Discover the files that belong to a project."""

from __future__ import annotations

import os
from pathlib import Path

# Directories that never contain the user's own code.
IGNORED_DIRS: frozenset[str] = frozenset(
    {
        ".git",
        ".hg",
        ".idea",
        ".ipynb_checkpoints",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        ".venv",
        ".vscode",
        "__pycache__",
        "build",
        "dist",
        "env",
        "node_modules",
        "site-packages",
        "venv",
    }
)


def discover_files(root: Path) -> list[Path]:
    """Return every file under ``root``, sorted, without descending into ignored directories."""
    if not root.is_dir():
        raise NotADirectoryError(f"Not a directory: {root}")
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(
            d for d in dirnames if d not in IGNORED_DIRS and not d.endswith(".egg-info")
        )
        found.extend(Path(dirpath) / name for name in filenames)
    return sorted(found)


def discover_python_files(root: Path) -> list[Path]:
    """Return all ``.py`` files under ``root``, sorted, skipping virtualenvs and tool caches."""
    return [path for path in discover_files(root) if path.suffix == ".py"]
