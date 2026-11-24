"""Apply verified fixes to an in-memory copy of a project, then scan it again.

Fixes were each verified against the original code. Applied together they can collide (two
fixes for the same line, say a leakage split and a missing seed), so they are applied one at a
time and every fix is verified again against the code as the earlier fixes left it. A fix that
no longer fits is skipped with the reason, never forced.

Optionally a second round regenerates the collided fixes: the partly fixed copy is scanned, the
problems that are still there are explained again (one LLM call each), and their new fixes are
verified and applied the same way. There is no third round. Nothing is written to disk here.
"""

from __future__ import annotations

import difflib
import io
import zipfile
from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from shipshape.analyzer import analyze_project
from shipshape.llm.context import build_context
from shipshape.llm.validate import FixRejectedError, validate_fix
from shipshape.models import CheckDelta, Finding, FixOutcome, FixRun, FixStatus, Report
from shipshape.project import Project
from shipshape.scanner import discover_files

# Explains ``report.findings`` in place against ``project`` (an LLM call per finding).
Regenerate = Callable[[Project, Report], object]

COLLIDED = "An earlier fix already changed the same code"
MAX_ZIP_BYTES = 200 * 1024 * 1024  # bigger projects get a patch only
NO_NEWLINE = "\n\\ No newline at end of file\n"  # git's marker for a last line without "\n"


@dataclass(frozen=True)
class FixResult:
    """The fix run plus the changed files' new contents (for writing a zip or a folder)."""

    run: FixRun
    texts: dict[str, str]
    after: Report


def fixable(finding: Finding) -> bool:
    """True if the finding has a verified fix with edits."""
    x = finding.explanation
    return x is not None and x.fix_status is FixStatus.VERIFIED and bool(x.edits)


def _apply_one(base: Project, current: Project, finding: Finding) -> Project:
    """Verify ``finding``'s fix against ``current`` and return the project with it applied.

    ``base`` is the code the fix was written against: its context holds the redaction mapping
    the edits use and the list of files the fix may touch.
    """
    assert finding.explanation is not None
    context = build_context(base, finding, fix_allowed=True)
    validated = validate_fix(current, context, finding, finding.explanation.edits)
    return current.with_texts(validated.new_texts)


def _deltas(before: Report, after: Report) -> list[CheckDelta]:
    counts_before = Counter[str]()
    counts_after = Counter[str]()
    titles: dict[str, str] = {}
    for report, counts in ((before, counts_before), (after, counts_after)):
        for finding in report.findings:
            counts[finding.check_id] += len(finding.locations)
            titles.setdefault(finding.check_id, finding.title)
    return [
        CheckDelta(check_id=c, title=titles[c], before=counts_before[c], after=counts_after[c])
        for c in sorted(titles)
        if counts_before[c] != counts_after[c]
    ]


def uses_crlf(root: Path, rel: str) -> bool:
    """True if the file on disk has Windows line endings (Shipshape reads text with plain LF)."""
    try:
        return b"\r\n" in (root / rel).read_bytes()
    except OSError:
        return False


def as_on_disk(text: str, crlf: bool) -> str:
    """Give scanned text the line endings of the file it came from."""
    return text.replace("\n", "\r\n") if crlf else text


def unified_patch(project: Project, texts: dict[str, str]) -> str:
    """A ``git apply``-compatible diff of every changed file, in each file's own line endings."""
    originals = {s.path: s.text for s in project.sources}
    chunks: list[str] = []
    for path in sorted(texts):
        crlf = uses_crlf(project.root, path)
        for line in difflib.unified_diff(
            as_on_disk(originals[path], crlf).splitlines(keepends=True),
            as_on_disk(texts[path], crlf).splitlines(keepends=True),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
        ):
            # A last line without a newline gets git's marker, or it would merge with the next.
            chunks.append(line if line.endswith("\n") else line + NO_NEWLINE)
    return "".join(chunks)


def _first_round(
    project: Project, report: Report, indices: Iterable[int]
) -> tuple[Project, list[FixOutcome]]:
    current = project
    outcomes: list[FixOutcome] = []
    for index in sorted(set(indices)):
        finding = report.findings[index]
        outcome = FixOutcome(
            finding=index, check_id=finding.check_id, title=finding.title, applied=False
        )
        if not fixable(finding):
            outcome.reason = "This finding has no verified fix."
        else:
            try:
                current = _apply_one(project, current, finding)
                outcome.applied = True
            except FixRejectedError as exc:
                outcome.reason = f"{COLLIDED}, so this one no longer fits ({exc})."
        outcomes.append(outcome)
    return current, outcomes


def _second_round(current: Project, collided: list[FixOutcome], regenerate: Regenerate) -> Project:
    """Explain the collided problems again against ``current`` and apply the new fixes."""
    interim = analyze_project(current)
    wanted = {o.check_id for o in collided}
    retry = interim.model_copy(
        update={"findings": [f for f in interim.findings if f.check_id in wanted]}
    )
    gone = wanted - {f.check_id for f in retry.findings}
    try:
        if retry.findings:
            regenerate(current, retry)
    except Exception as exc:  # no key, no credit, network: keep the first round's result
        for outcome in collided:
            outcome.reason += f" A second try was not possible: {exc}"
        return current
    base = current
    applied: set[str] = set()
    why: dict[str, str] = {}
    for finding in retry.findings:
        if not fixable(finding):
            why.setdefault(finding.check_id, "no verified fix came back")
            continue
        try:
            current = _apply_one(base, current, finding)
            applied.add(finding.check_id)
        except FixRejectedError as exc:
            why.setdefault(finding.check_id, str(exc))
    for outcome in collided:
        if outcome.check_id in gone:
            outcome.reason = "Not needed: the earlier fixes already removed this problem."
        elif outcome.check_id in applied:
            outcome.applied, outcome.second_round = True, True
            outcome.reason = "Regenerated against the fixed code and applied in a second round."
        else:
            outcome.reason += f" A second try did not fit either ({why.get(outcome.check_id)})."
    return current


def apply_fixes(
    project: Project,
    report: Report,
    indices: Iterable[int],
    regenerate: Regenerate | None = None,
) -> FixResult:
    """Apply the verified fixes of ``report.findings[i]`` for each ``i``, in report order.

    With ``regenerate``, fixes skipped because an earlier fix changed the same code get one
    second round against the fixed code.
    """
    current, outcomes = _first_round(project, report, indices)
    collided = [o for o in outcomes if o.reason.startswith(COLLIDED)]
    if regenerate is not None and collided:
        current = _second_round(current, collided, regenerate)

    before_texts = {s.path: s.text for s in project.sources}
    texts = {
        s.path: s.text
        for s in current.sources
        if s.path in current.overrides and s.text != before_texts.get(s.path)
    }
    after = analyze_project(current)
    run = FixRun(
        outcomes=outcomes,
        changed_files=sorted(texts),
        before_grade=report.grade,
        after_grade=after.grade,
        before_scores=report.scores,
        after_scores=after.scores,
        deltas=_deltas(report, after),
        patch=unified_patch(project, texts),
    )
    return FixResult(run=run, texts=texts, after=after)


def project_zip(root: Path, texts: dict[str, str], folder: str) -> bytes:
    """Zip the project under ``root`` with the changed files replaced, inside ``folder/``.

    Uses the same file discovery as a scan, so virtual environments, caches and ``.git`` are
    left out. Raises ``ValueError`` if the project is larger than :data:`MAX_ZIP_BYTES`.
    """
    files: Sequence[Path] = list(discover_files(root))
    total = sum(path.stat().st_size for path in files)
    if total > MAX_ZIP_BYTES:
        mb = MAX_ZIP_BYTES // (1024 * 1024)
        raise ValueError(f"The project is larger than {mb} MB; download the patch instead.")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            rel = path.relative_to(root).as_posix()
            name = f"{folder}/{rel}"
            if rel in texts:
                archive.writestr(name, as_on_disk(texts[rel], uses_crlf(root, rel)).encode())
            else:
                archive.write(path, name)
    return buffer.getvalue()
