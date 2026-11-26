"""Check a proposed fix before anyone sees it. Nothing here writes to the user's project.

Gates, in order:
1. Every edit targets a Python file that was shown, and its search text appears exactly once.
2. Every changed file still parses.
3. The original finding is gone from the places that were targeted (the check is re-run).
4. No other check reports more problems in the changed files than before.

Passing proves the fix is valid Python that removes the problem without adding detectable
new ones. It does not prove the program behaves the same: Shipshape never runs code.
"""

from __future__ import annotations

import ast
import tempfile
import warnings
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from shipshape.checks import Check, default_checks
from shipshape.checks.ruff import RuffCheck
from shipshape.llm.context import FindingContext
from shipshape.models import Edit, Finding
from shipshape.project import Project

# Project-wide checks that count modules above a size threshold: a fix that adds a few lines
# can push a file over it without adding a problem, so they never block a fix.
NOT_A_NEW_PROBLEM = frozenset({"testing.untested-modules", "testing.no-tests"})


class FixRejectedError(ValueError):
    """A gate failed; the message says which one and why, in words the model can act on."""


@dataclass(frozen=True)
class ValidatedFix:
    """Edits that passed every gate, with the real (unredacted) file contents after applying."""

    edits: list[Edit]
    new_texts: dict[str, str]


def apply_edits(project: Project, context: FindingContext, edits: list[Edit]) -> dict[str, str]:
    """Gate 1: apply search/replace edits in memory and return the changed file texts."""
    texts: dict[str, str] = {}
    by_path = {s.path: s for s in project.python_files}
    for number, edit in enumerate(edits, start=1):
        if edit.path not in context.files or edit.path not in by_path:
            raise FixRejectedError(
                f"edit {number} targets {edit.path!r}, which was not shown to you"
            )
        if context.redactions.contains_placeholder(edit.replace):
            raise FixRejectedError(
                f"edit {number} puts a <REDACTED_n> placeholder into the new code"
            )
        search = context.redactions.restore(edit.search)
        replacement = edit.replace
        current = texts.get(edit.path, by_path[edit.path].text)
        if not search.strip():
            raise FixRejectedError(f"edit {number} has an empty search text")
        count = current.count(search)
        if count != 1:
            where = "does not appear" if count == 0 else f"appears {count} times"
            raise FixRejectedError(f"edit {number}: the search text {where} in {edit.path}")
        texts[edit.path] = current.replace(search, replacement, 1)
    return texts


def _parses(text: str) -> str | None:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            ast.parse(text)
    except SyntaxError as exc:
        return f"line {exc.lineno}: {exc.msg}"
    return None


def _counts(project: Project, paths: set[str], checks: list[Check]) -> Counter[str]:
    """Locations per check id inside ``paths``. Ruff only looks at those files."""
    counts: Counter[str] = Counter()
    for check in checks:
        for finding in check.run(project):
            counts[finding.check_id] += sum(loc.path in paths for loc in finding.locations)
    with tempfile.TemporaryDirectory(prefix="shipshape-fix-") as tmp:
        root = Path(tmp)
        by_path = {s.path: s.text for s in project.sources}
        for path in paths:
            target = root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(by_path[path], encoding="utf-8")
        for finding in RuffCheck().run(Project(root=root, sources=(), files=())):
            counts[finding.check_id] += sum(loc.path in paths for loc in finding.locations)
    return counts


def validate_fix(
    project: Project, context: FindingContext, finding: Finding, edits: list[Edit]
) -> ValidatedFix:
    """Run all gates; raise :class:`FixRejectedError` with a reason on the first failure."""
    if not edits:
        raise FixRejectedError("no edits were proposed")
    new_texts = apply_edits(project, context, edits)
    for path, text in new_texts.items():
        problem = _parses(text)
        if problem:
            raise FixRejectedError(f"{path} no longer parses after the edits ({problem})")

    touched = set(new_texts)
    checks = [c for c in default_checks() if not isinstance(c, RuffCheck)]
    before = _counts(project, touched, checks)
    after = _counts(project.with_texts(new_texts), touched, checks)

    targeted = sum(path in touched for path, _ in context.sent_locations) or 1
    if before[finding.check_id] - after[finding.check_id] < targeted:
        raise FixRejectedError(
            f"the problem is still reported in the edited code ({finding.check_id}: "
            f"{before[finding.check_id]} before, {after[finding.check_id]} after)"
        )
    new_problems = [
        f"{check_id} ({before[check_id]} -> {count})"
        for check_id, count in sorted(after.items())
        if check_id != finding.check_id
        and check_id not in NOT_A_NEW_PROBLEM
        and count > before[check_id]
    ]
    if new_problems:
        raise FixRejectedError(f"the edits introduce new problems: {', '.join(new_problems)}")
    return ValidatedFix(edits, new_texts)
