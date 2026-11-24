"""Turn findings into explanations with validated fixes.

Per finding: build the context, check the cache, ask the model, parse its JSON, validate the
fix, and retry once with the reason if parsing or validation fails. One API call per finding
in the normal case, two at most.
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from pydantic import BaseModel, Field, ValidationError

from shipshape.llm.cache import ExplanationCache, cache_key
from shipshape.llm.client import ChatClient, Completion, FatalLLMError, LLMError, Message
from shipshape.llm.context import FindingContext, build_context
from shipshape.llm.prompts import SYSTEM_PROMPT, retry_message
from shipshape.llm.settings import estimate_cost
from shipshape.llm.validate import FixRejectedError, validate_fix
from shipshape.models import Edit, ExplainStats, Explanation, Finding, FixStatus, Report
from shipshape.project import Project

# Checks where a small local edit is the right fix. Everything else gets an explanation and
# manual steps only: splitting a large file or guessing package versions automatically would
# do more harm than good.
FIXABLE_CHECKS = frozenset(
    {
        "correctness.grouped-split-leakage",
        "correctness.swallowed-exception",
        "repro.hardcoded-path",
        "repro.missing-seed",
        "security.hardcoded-secret",
        "readability.print-debugging",
        "readability.restating-comments",
        "lint.undefined-name",
        "lint.mutable-default",
        "lint.loop-closure",
        "lint.redefined-name",
        "lint.unused-import",
        "lint.unused-variable",
        "lint.star-import",
        "lint.none-comparison",
        "lint.bool-comparison",
    }
)
DEFAULT_MAX_FINDINGS = 15
DEFAULT_CONCURRENCY = 6  # parallel API calls; DeepSeek allows far more, this keeps bursts polite
VERIFIED_NOTE = (
    "Verified by static checks: applies cleanly, parses, removes the finding and adds no new "
    "findings. Behaviour was not tested."
)


class _Answer(BaseModel):
    summary: str
    what: str
    why: str
    how_to_fix: str
    behaviour_change: str = ""
    edits: list[Edit] = Field(default_factory=list)


@dataclass
class _Usage:
    calls: int = 0
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0

    def add(self, completion: Completion) -> None:
        self.calls += 1
        self.input_tokens += completion.input_tokens
        self.cached_input_tokens += completion.cached_input_tokens
        self.output_tokens += completion.output_tokens

    def merge(self, other: _Usage) -> None:
        self.calls += other.calls
        self.input_tokens += other.input_tokens
        self.cached_input_tokens += other.cached_input_tokens
        self.output_tokens += other.output_tokens


def _parse(text: str) -> _Answer:
    if not text.strip():
        raise ValueError("the answer was empty (it was probably not valid JSON)")
    try:
        return _Answer.model_validate(json.loads(text))
    except json.JSONDecodeError as exc:
        raise ValueError(f"the answer is not valid JSON ({exc.msg})") from exc
    except ValidationError as exc:
        fields = ", ".join(str(err["loc"][0]) for err in exc.errors() if err["loc"])
        raise ValueError(f"the JSON is missing or has wrong fields: {fields}") from exc


def _explain_one(
    client: ChatClient,
    project: Project,
    finding: Finding,
    context: FindingContext,
    fix_allowed: bool,
    usage: _Usage,
) -> tuple[Explanation, bool]:
    """Return the explanation and whether a retry was needed."""
    messages: list[Message] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": context.text},
    ]
    answer: _Answer | None = None
    rejection = ""
    for attempt in range(2):
        completion = client.complete(messages)
        usage.add(completion)
        try:
            answer = _parse(completion.text)
        except ValueError as exc:
            problem = str(exc)
        else:
            if not fix_allowed or not answer.edits:
                return _build(answer, client.model, FixStatus.NONE, ""), attempt > 0
            try:
                validate_fix(project, context, finding, answer.edits)
            except FixRejectedError as exc:
                problem = rejection = str(exc)
            else:
                return _build(answer, client.model, FixStatus.VERIFIED, VERIFIED_NOTE), attempt > 0
        if attempt == 0:
            messages += [
                {"role": "assistant", "content": completion.text},
                {"role": "user", "content": retry_message(problem)},
            ]
    if answer is None:
        raise LLMError(f"no usable answer after a retry: {problem}")
    return _build(answer, client.model, FixStatus.REJECTED, f"Fix rejected: {rejection}"), True


def _build(answer: _Answer, model: str, status: FixStatus, note: str) -> Explanation:
    return Explanation(
        summary=answer.summary,
        what=answer.what,
        why=answer.why,
        how_to_fix=answer.how_to_fix,
        behaviour_change=answer.behaviour_change if status is not FixStatus.NONE else "",
        edits=answer.edits if status is not FixStatus.NONE else [],
        fix_status=status,
        fix_note=note,
        model=model,
    )


@dataclass
class _Outcome:
    """Result of one finding's task, merged into the stats on the main thread."""

    explanation: Explanation | None = None
    usage: _Usage = field(default_factory=lambda: _Usage())
    cached: bool = False
    retried: bool = False
    failed: bool = False
    fatal: FatalLLMError | None = None


def _explain_with_cache(
    client: ChatClient,
    project: Project,
    finding: Finding,
    cache: ExplanationCache,
    stop: threading.Event,
) -> _Outcome:
    """Explain one finding (or reuse the cache). Runs on a worker thread."""
    fix_allowed = finding.check_id in FIXABLE_CHECKS
    context = build_context(project, finding, fix_allowed)
    key = cache_key(client.model, finding.check_id, fix_allowed, context.text)
    cached = cache.get(key)
    if cached is not None:
        return _Outcome(explanation=cached.model_copy(update={"cached": True}), cached=True)
    outcome = _Outcome()
    if stop.is_set():
        outcome.failed = True
        return outcome
    try:
        explanation, retried = _explain_one(
            client, project, finding, context, fix_allowed, outcome.usage
        )
    except FatalLLMError as exc:
        stop.set()
        outcome.fatal = exc
        return outcome
    except LLMError:
        outcome.failed = True
        return outcome
    cache.put(key, explanation)
    outcome.explanation, outcome.retried = explanation, retried
    return outcome


def explain_report(
    report: Report,
    project: Project,
    client: ChatClient,
    *,
    provider: str,
    max_findings: int = DEFAULT_MAX_FINDINGS,
    cache: ExplanationCache | None = None,
    progress: Callable[[str], None] | None = None,
    concurrency: int = DEFAULT_CONCURRENCY,
) -> ExplainStats:
    """Attach explanations to the most severe findings of ``report`` (in place).

    Findings are already sorted by severity, so the limit keeps the important ones. Up to
    ``concurrency`` findings are explained at the same time. A fatal error (bad key, no
    credit) cancels the findings not started yet and is re-raised; any other failure skips
    just that finding.
    """
    cache = cache or ExplanationCache()
    usage = _Usage()
    stats = ExplainStats(provider=provider, model=client.model)
    started = time.perf_counter()
    selected = report.findings[:max_findings]
    stop = threading.Event()
    lock = threading.Lock()
    done = 0

    def work(finding: Finding) -> _Outcome:
        nonlocal done
        outcome = _explain_with_cache(client, project, finding, cache, stop)
        with lock:
            done += 1
            if progress:
                progress(f"[{done}/{len(selected)}] {finding.title}")
        return outcome

    fatal: FatalLLMError | None = None
    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        outcomes = list(pool.map(work, selected))
    for finding, outcome in zip(selected, outcomes, strict=True):
        usage.merge(outcome.usage)
        if outcome.fatal is not None:
            fatal = fatal or outcome.fatal
            continue
        if outcome.failed or outcome.explanation is None:
            stats.failures += outcome.failed
            continue
        finding.explanation = outcome.explanation
        stats.cache_hits += outcome.cached
        stats.retries += outcome.retried
        stats.findings_explained += 1
        stats.fixes_verified += outcome.explanation.fix_status is FixStatus.VERIFIED
        stats.fixes_rejected += outcome.explanation.fix_status is FixStatus.REJECTED
    if fatal is not None:
        raise fatal

    stats.api_calls = usage.calls
    stats.input_tokens = usage.input_tokens
    stats.cached_input_tokens = usage.cached_input_tokens
    stats.output_tokens = usage.output_tokens
    stats.estimated_cost_usd = estimate_cost(
        client.model, usage.input_tokens, usage.cached_input_tokens, usage.output_tokens
    )
    stats.seconds = time.perf_counter() - started
    report.explain_stats = stats
    return stats
