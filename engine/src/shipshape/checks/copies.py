"""Checks for code that was copied instead of shared: whole packages and single files."""

from __future__ import annotations

from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import PurePosixPath
from typing import ClassVar

from shipshape.checks.base import Check, examples, plural
from shipshape.models import Dimension, Finding, Location, Severity
from shipshape.project import Project

DUPLICATE_OVERLAP = 0.6
DUPLICATE_MIN_FILES = 3
DUPLICATE_SIMILARITY = 0.8  # share of matching lines for a renamed copy
COPY_MIN_LINES = 10  # smaller files (tiny helpers, __init__) are not worth reporting
COPY_SIMILARITY = 0.85  # share of matching code lines for two files to count as copies
COPY_ALL_PAIRS_LIMIT = 400  # above this many files, only same-named files are compared


class DuplicatedPackage(Check):
    """The same package copied into several folders, a stand-in for version control.

    Packages with the same folder name are compared by their file names. Packages with
    different names (``data`` and ``data_old``) are compared by content as well, so a renamed
    copy is found without flagging unrelated packages that happen to share file names.
    """

    id: ClassVar[str] = "structure.duplicated-package"
    title: ClassVar[str] = "Same package copied in several places"
    severity: ClassVar[Severity] = Severity.MAJOR
    dimension: ClassVar[Dimension] = Dimension.STRUCTURE
    concept: ClassVar[str] = "Version control instead of copies"

    def run(self, project: Project) -> list[Finding]:
        """Compare every pair of packages; report each copied pair once (outermost first)."""
        dirs = sorted(
            {
                PurePosixPath(rel).parent.as_posix()
                for rel in project.files
                if PurePosixPath(rel).name == "__init__.py" and "/" in rel
            },
            key=lambda d: (d.count("/"), d),
        )
        contents = {
            d: {f[len(d) + 1 :] for f in project.files if f.startswith(d + "/")} for d in dirs
        }
        texts = {s.path: s.text for s in project.sources}
        reported: list[tuple[str, str]] = []
        findings = []
        for i, first in enumerate(dirs):
            for second in dirs[i + 1 :]:
                if _nested(first, second) or any(
                    _inside(first, a) and _inside(second, b) for a, b in reported
                ):
                    continue
                overlap = _package_overlap(first, second, contents, texts)
                if overlap is None:
                    continue
                reported.append((first, second))
                findings.append(self._finding(first, second, overlap))
        return findings

    def _finding(self, first: str, second: str, overlap: float) -> Finding:
        name_a, name_b = PurePosixPath(first).name, PurePosixPath(second).name
        if name_a == name_b:
            what = (
                f"The package `{name_a}` exists in two places (`{first}` and `{second}`) and "
                f"{overlap:.0%} of their files have the same names."
            )
            evidence = f"{overlap:.0%} file overlap"
        else:
            what = (
                f"`{first}` and `{second}` are copies of each other under different names: "
                f"{overlap:.0%} of their files are the same or nearly the same."
            )
            evidence = f"{overlap:.0%} of files (nearly) identical"
        message = (
            f"{what} Copies drift apart silently: a bug fixed in one stays in the other, and "
            f"nobody knows which is current. Keep one copy under git and use branches or "
            f"configuration for the variants; if one copy is unused, delete it."
        )
        return self.finding(
            message, [Location(path=first), Location(path=second)], evidence=evidence
        )


def _inside(path: str, folder: str) -> bool:
    return path == folder or path.startswith(folder + "/")


def _nested(first: str, second: str) -> bool:
    return _inside(first, second) or _inside(second, first)


def _similar(a: str, b: str) -> bool:
    """Same text, or nearly: at least DUPLICATE_SIMILARITY of the lines match."""
    if a == b:
        return True
    return SequenceMatcher(None, a.splitlines(), b.splitlines()).ratio() >= DUPLICATE_SIMILARITY


def _package_overlap(
    first: str, second: str, contents: dict[str, set[str]], texts: dict[str, str]
) -> float | None:
    """Share of files the two packages have in common, or ``None`` if they are not copies."""
    union = contents[first] | contents[second]
    if len(union) < DUPLICATE_MIN_FILES:
        return None
    shared = contents[first] & contents[second]
    if PurePosixPath(first).name != PurePosixPath(second).name:
        shared = {
            f
            for f in shared
            if f"{first}/{f}" in texts
            and f"{second}/{f}" in texts
            and _similar(texts[f"{first}/{f}"], texts[f"{second}/{f}"])
        }
    overlap = len(shared) / len(union)
    return overlap if overlap >= DUPLICATE_OVERLAP else None


def _code_lines(text: str) -> list[str]:
    """Lines that carry code: stripped, without blank lines and full-line comments."""
    return [
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def _near_copies(a: list[str], b: list[str]) -> bool:
    if a == b:
        return True
    shorter, longer = sorted((len(a), len(b)))
    if shorter / longer < COPY_SIMILARITY:
        return False
    set_a, set_b = set(a), set(b)
    if len(set_a & set_b) / len(set_a | set_b) < COPY_SIMILARITY - 0.15:
        return False  # cheap filter before the exact comparison
    return SequenceMatcher(None, a, b, autojunk=False).ratio() >= COPY_SIMILARITY


class CopiedFiles(Check):
    """The same file copied around: one copy per experiment folder, or ``x_2.py`` next to ``x.py``.

    Copies of whole packages are reported by ``structure.duplicated-package`` and left out here.
    """

    id: ClassVar[str] = "structure.copied-files"
    title: ClassVar[str] = "Files copied instead of shared"
    severity: ClassVar[Severity] = Severity.MAJOR
    dimension: ClassVar[Dimension] = Dimension.STRUCTURE
    concept: ClassVar[str] = "Version control instead of copies"

    def run(self, project: Project) -> list[Finding]:
        """Group files whose code is identical or nearly identical (85%+ of lines match)."""
        package_pairs = [
            (loc_a.path, loc_b.path)
            for finding in DuplicatedPackage().run(project)
            for loc_a, loc_b in [finding.locations[:2]]
        ]
        files = {
            s.path: _code_lines(s.text)
            for s in project.python_files
            if s.name != "__init__.py" and s.code_lines >= COPY_MIN_LINES
        }
        paths = sorted(files)
        all_pairs = len(paths) <= COPY_ALL_PAIRS_LIMIT
        parent = {p: p for p in paths}

        def root(p: str) -> str:
            while parent[p] != p:
                parent[p] = parent[parent[p]]
                p = parent[p]
            return p

        for i, first in enumerate(paths):
            for second in paths[i + 1 :]:
                same_name = PurePosixPath(first).name == PurePosixPath(second).name
                if not (same_name or all_pairs):
                    continue
                if any(
                    (_inside(first, a) and _inside(second, b))
                    or (_inside(first, b) and _inside(second, a))
                    for a, b in package_pairs
                ):
                    continue
                if root(first) != root(second) and _near_copies(files[first], files[second]):
                    parent[root(second)] = root(first)
        groups: dict[str, list[str]] = defaultdict(list)
        for path in paths:
            groups[root(path)].append(path)
        copies = sorted((g for g in groups.values() if len(g) > 1), key=lambda g: (-len(g), g[0]))
        if not copies:
            return []
        summary = [
            f"`{PurePosixPath(g[0]).name}` in {len(g)} copies"
            if len({PurePosixPath(p).name for p in g}) == 1
            else f"`{PurePosixPath(g[0]).name}` and {len(g) - 1} near copies"
            for g in copies
        ]
        message = (
            f"{plural(len(copies), 'file exists', 'files exist')} in several copies with "
            f"(nearly) the same code ({examples(summary)}). A bug fixed in one copy stays in the "
            f"others, and it is unclear which version produced which result. Keep one shared "
            f"module that every experiment imports, and put the differences into arguments or "
            f"a config file; git keeps the old versions."
        )
        return [
            self.finding(
                message,
                [Location(path=p) for group in copies for p in group],
                evidence=", ".join(summary[:6]).replace("`", ""),
            )
        ]
