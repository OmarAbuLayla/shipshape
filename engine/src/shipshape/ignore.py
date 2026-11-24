"""Ignore rules: let a project say which files are not its real code, and which lines are fine.

Two mechanisms, both visible in every report so a score can always be traced back:

``.shipshapeignore`` files (gitignore-style, one pattern per line, relative to the file's folder)::

    # deliberately broken examples used by the test suite
    engine/corpus/fixtures/
    *_generated.py
    check:lint.too-many-arguments     # switch a check off for this project

Inline comments, for one deliberate line::

    API_KEY = "fake-key-for-tests"  # shipshape: ignore[security.hardcoded-secret] fake value

``# shipshape: ignore`` without brackets suppresses every check on that line. Negation (``!``)
is not supported.
"""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

IGNORE_FILE = ".shipshapeignore"
PRAGMA = re.compile(r"#\s*shipshape:\s*ignore(?:\[([^\]]*)\])?", re.IGNORECASE)


@dataclass(frozen=True)
class Pattern:
    """One path pattern from one ignore file."""

    base: str  # folder of the ignore file, "" for the project root
    text: str  # the pattern as written

    def matches(self, rel: str) -> bool:
        """True if the project-relative path ``rel`` is covered by this pattern."""
        if self.base:
            if not rel.startswith(self.base + "/"):
                return False
            rel = rel[len(self.base) + 1 :]
        pattern = self.text
        directory = pattern.endswith("/")
        pattern = pattern.strip("/")
        if not pattern:
            return False
        anchored = "/" in pattern or self.text.startswith("/")
        path = PurePosixPath(rel)
        if directory:
            folders = [p.as_posix() for p in reversed(path.parents) if p.as_posix() != "."]
            if anchored:
                return any(fnmatch.fnmatch(folder, pattern) for folder in folders)
            return any(fnmatch.fnmatch(part, pattern) for part in path.parts[:-1])
        if anchored:
            return fnmatch.fnmatch(rel, pattern) or any(
                fnmatch.fnmatch(p.as_posix(), pattern) for p in path.parents if p.as_posix() != "."
            )
        return any(fnmatch.fnmatch(part, pattern) for part in path.parts)

    def describe(self) -> str:
        """The pattern with its ignore file's folder, for reports."""
        return f"{self.base}/{self.text}" if self.base else self.text


@dataclass(frozen=True)
class IgnoreRules:
    """All ignore files of a project, parsed."""

    files: tuple[str, ...] = ()
    patterns: tuple[Pattern, ...] = ()
    disabled_checks: tuple[str, ...] = ()

    def ignores(self, rel: str) -> bool:
        """True if the file is excluded from analysis."""
        return PurePosixPath(rel).name != IGNORE_FILE and any(p.matches(rel) for p in self.patterns)

    def check_disabled(self, check_id: str) -> bool:
        """True if a ``check:`` line switches this check off."""
        return any(fnmatch.fnmatch(check_id, pattern) for pattern in self.disabled_checks)


def load_rules(root: Path, rel_files: list[str]) -> IgnoreRules:
    """Read every ``.shipshapeignore`` among ``rel_files`` (project-relative POSIX paths)."""
    files = sorted(f for f in rel_files if PurePosixPath(f).name == IGNORE_FILE)
    patterns: list[Pattern] = []
    disabled: list[str] = []
    for rel in files:
        base = str(PurePosixPath(rel).parent)
        base = "" if base == "." else base
        try:
            text = (root / rel).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for raw in text.splitlines():
            line = raw.split(" #", 1)[0].strip()
            if not line or line.startswith("#"):
                continue
            if line.lower().startswith("check:"):
                disabled.append(line.split(":", 1)[1].strip())
            else:
                patterns.append(Pattern(base, line))
    return IgnoreRules(tuple(files), tuple(patterns), tuple(disabled))


def pragma_ids(line: str) -> set[str] | None:
    """Check ids an inline comment on ``line`` suppresses.

    ``None`` means there is no comment; ``{"*"}`` means every check.
    """
    match = PRAGMA.search(line)
    if match is None:
        return None
    if match.group(1) is None:
        return {"*"}
    return {part.strip() for part in match.group(1).split(",") if part.strip()} or {"*"}
