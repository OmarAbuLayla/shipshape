"""Measure how well the checks find planted issues: precision and recall per check.

A corpus is a folder of projects, each with an ``expected.yaml``::

    expected:
      - check: repro.hardcoded-path
        path: train.py
        line: 7          # optional; matches within +-1 line
        cell: 2          # optional, notebooks only

Every location a check reports must match an expected entry (otherwise it is a false
positive), and every expected entry must be matched by some location (otherwise it is a
false negative). Real projects that cannot live in the corpus folder are listed in a
manifest file with the same ``expected`` lists plus a ``root`` path.
"""

from __future__ import annotations

import shutil
import tempfile
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from shipshape.analyzer import analyze
from shipshape.models import Location, Report

EXPECTED_FILE = "expected.yaml"


@dataclass(frozen=True)
class Expected:
    """One issue a check should report."""

    check: str
    path: str
    line: int | None = None
    cell: int | None = None

    def matches(self, check: str, location: Location) -> bool:
        """True if ``location`` reported by ``check`` is this expected issue."""
        if check != self.check or location.path != self.path:
            return False
        if self.cell is not None and location.cell != self.cell:
            return False
        if self.line is None:
            return True
        start = location.start_line
        if start is None:
            return False
        end = location.end_line or start
        return start - 1 <= self.line <= end + 1


@dataclass(frozen=True)
class Case:
    """A project plus the issues it is known to contain."""

    name: str
    root: Path
    expected: tuple[Expected, ...]
    # Files written into a temporary copy before scanning, for test data that must not
    # live in the repository itself (such as a fake .env file).
    setup_files: tuple[tuple[str, str], ...] = ()


@dataclass
class CheckScore:
    """Counts for one check across the corpus."""

    true_positives: int = 0  # reported locations that were expected
    false_positives: int = 0  # reported locations that were not expected
    found: int = 0  # expected issues that were reported
    missed: int = 0  # expected issues that were not reported

    @property
    def precision(self) -> float | None:
        """Share of reported locations that were right."""
        total = self.true_positives + self.false_positives
        return self.true_positives / total if total else None

    @property
    def recall(self) -> float | None:
        """Share of expected issues that were found."""
        total = self.found + self.missed
        return self.found / total if total else None


@dataclass
class EvalResult:
    """Scores per check plus a readable list of every mistake."""

    scores: dict[str, CheckScore] = field(default_factory=lambda: defaultdict(CheckScore))
    mistakes: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def perfect(self) -> bool:
        """True when there are no false positives, misses or crashed checks."""
        return not self.mistakes and not self.errors


def _parse_expected(raw: object, source: Path) -> tuple[Expected, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise ValueError(f"{source}: 'expected' must be a list")
    items = []
    for entry in raw:
        if not isinstance(entry, dict) or "check" not in entry or "path" not in entry:
            raise ValueError(f"{source}: every expected entry needs 'check' and 'path'")
        items.append(
            Expected(
                check=str(entry["check"]),
                path=str(entry["path"]),
                line=entry.get("line"),
                cell=entry.get("cell"),
            )
        )
    return tuple(items)


def load_corpus(corpus_dir: Path) -> list[Case]:
    """Load every sub-folder of ``corpus_dir`` that has an ``expected.yaml``."""
    cases = []
    for spec in sorted(corpus_dir.glob(f"*/{EXPECTED_FILE}")):
        data = yaml.safe_load(spec.read_text(encoding="utf-8")) or {}
        setup = data.get("setup_files") or {}
        if not isinstance(setup, dict):
            raise ValueError(f"{spec}: 'setup_files' must map file names to contents")
        cases.append(
            Case(
                spec.parent.name,
                spec.parent,
                _parse_expected(data.get("expected"), spec),
                tuple((str(name), str(text)) for name, text in setup.items()),
            )
        )
    return cases


def load_manifest(manifest: Path) -> list[Case]:
    """Load projects listed in a manifest (``projects: [{name, root, expected}]``)."""
    data = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
    cases = []
    for entry in data.get("projects", []):
        root = Path(entry["root"])
        if not root.is_absolute():
            root = manifest.parent / root
        name = str(entry.get("name", root.name))
        cases.append(Case(name, root, _parse_expected(entry.get("expected"), manifest)))
    return cases


def _analyze_case(case: Case) -> Report:
    """Scan the case, in a temporary copy with its setup files if it has any."""
    if not case.setup_files:
        return analyze(case.root)
    with tempfile.TemporaryDirectory(prefix="shipshape-eval-") as tmp:
        copy = Path(tmp) / case.root.name
        shutil.copytree(case.root, copy)
        for name, text in case.setup_files:
            (copy / name).write_text(text, encoding="utf-8")
        return analyze(copy)


def evaluate(cases: list[Case]) -> EvalResult:
    """Analyse every case and score each check against its expected issues."""
    result = EvalResult()
    for case in cases:
        report = _analyze_case(case)
        result.errors.extend(f"{case.name}: {error}" for error in report.check_errors)
        matched: set[Expected] = set()
        for finding in report.findings:
            score = result.scores[finding.check_id]
            for location in finding.locations:
                hits = [e for e in case.expected if e.matches(finding.check_id, location)]
                if hits:
                    score.true_positives += 1
                    matched.update(hits)
                else:
                    score.false_positives += 1
                    where = location.path + (
                        f":{location.start_line}" if location.start_line else ""
                    )
                    result.mistakes.append(f"{case.name}: unexpected {finding.check_id} at {where}")
        for expected in case.expected:
            score = result.scores[expected.check]
            if expected in matched:
                score.found += 1
            else:
                score.missed += 1
                where = expected.path + (f":{expected.line}" if expected.line else "")
                result.mistakes.append(f"{case.name}: missed {expected.check} at {where}")
    return result
