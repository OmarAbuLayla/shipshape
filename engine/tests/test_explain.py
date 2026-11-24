"""The explanation pipeline, tested with a fake LLM: no network, no cost."""

import json
from collections.abc import Sequence
from pathlib import Path

import pytest

from shipshape.analyzer import analyze_project
from shipshape.llm.cache import ExplanationCache
from shipshape.llm.client import Completion, FatalLLMError, Message
from shipshape.llm.context import build_context
from shipshape.llm.explain import explain_report
from shipshape.models import FixStatus, Report
from shipshape.project import Project

from .conftest import FIXTURES_DIR

SECRET = "abcd1234efgh5678ijkl9012"  # the fake key in the secrets fixture


class FakeClient:
    """Returns scripted answers in order and records every request."""

    model = "deepseek-flash"

    def __init__(self, *answers: str | Exception) -> None:
        self.answers = list(answers)
        self.requests: list[list[Message]] = []

    def complete(self, messages: Sequence[Message]) -> Completion:
        self.requests.append([dict(m) for m in messages])
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return Completion(
            answer, input_tokens=1000, cached_input_tokens=600, output_tokens=200, seconds=0.1
        )


def _answer(edits: list[dict[str, str]] | None = None) -> str:
    return json.dumps(
        {
            "summary": "The data folder only exists on one laptop.",
            "what": "DATA_DIR points to a folder on your Desktop.",
            "why": "Nobody else can run train.py without editing it.",
            "how_to_fix": "Read the folder from an environment variable.",
            "edits": edits or [],
        }
    )


def _report_with(fixture: str, check_id: str) -> tuple[Report, Project]:
    project = Project.load(FIXTURES_DIR / fixture)
    report = analyze_project(project)
    report.findings = [f for f in report.findings if f.check_id == check_id]
    assert report.findings, f"fixture {fixture} has no {check_id} finding"
    return report, project


def _run(report: Report, project: Project, client: FakeClient, tmp_path: Path) -> None:
    explain_report(report, project, client, provider="deepseek", cache=ExplanationCache(tmp_path))


PATH_FIX = [
    {"path": "train.py", "search": "import torch\n", "replace": "import os\n\nimport torch\n"},
    {
        "path": "train.py",
        "search": 'DATA_DIR = "C:/Users/me/Desktop/emg_data_FINAL2"',
        "replace": 'DATA_DIR = os.environ.get("EMG_DATA_DIR", "data/raw")',
    },
]


def test_good_fix_is_verified(tmp_path: Path) -> None:
    report, project = _report_with("leaky_emg", "repro.hardcoded-path")
    client = FakeClient(_answer(PATH_FIX))

    _run(report, project, client, tmp_path)

    explanation = report.findings[0].explanation
    assert explanation is not None
    assert explanation.fix_status is FixStatus.VERIFIED
    assert len(client.requests) == 1
    assert report.explain_stats is not None and report.explain_stats.fixes_verified == 1


def test_fix_that_breaks_code_is_rejected_after_one_retry(tmp_path: Path) -> None:
    without_import = [PATH_FIX[1]]  # uses os without importing it
    report, project = _report_with("leaky_emg", "repro.hardcoded-path")
    client = FakeClient(_answer(without_import), _answer(without_import))

    _run(report, project, client, tmp_path)

    explanation = report.findings[0].explanation
    assert explanation is not None
    assert explanation.fix_status is FixStatus.REJECTED
    assert "lint.undefined-name" in explanation.fix_note
    assert len(client.requests) == 2
    assert "could not be used" in client.requests[1][-1]["content"]


def test_search_text_must_exist(tmp_path: Path) -> None:
    wrong = [{"path": "train.py", "search": "DATA = 1", "replace": "DATA = 2"}]
    report, project = _report_with("leaky_emg", "repro.hardcoded-path")
    client = FakeClient(_answer(wrong), _answer(PATH_FIX))

    _run(report, project, client, tmp_path)

    explanation = report.findings[0].explanation
    assert explanation is not None and explanation.fix_status is FixStatus.VERIFIED
    assert "does not appear" in client.requests[1][-1]["content"]


def test_invalid_json_gets_one_retry(tmp_path: Path) -> None:
    report, project = _report_with("leaky_emg", "repro.hardcoded-path")
    client = FakeClient("this is not json", _answer())

    _run(report, project, client, tmp_path)

    assert report.findings[0].explanation is not None
    assert report.explain_stats is not None and report.explain_stats.retries == 1


def test_two_unusable_answers_skip_the_finding(tmp_path: Path) -> None:
    report, project = _report_with("leaky_emg", "repro.hardcoded-path")
    client = FakeClient("", "{}")

    _run(report, project, client, tmp_path)

    assert report.findings[0].explanation is None
    assert report.explain_stats is not None and report.explain_stats.failures == 1


def test_explanation_only_checks_never_get_edits(tmp_path: Path) -> None:
    report, project = _report_with("leaky_emg", "testing.no-tests")
    client = FakeClient(_answer(PATH_FIX))

    _run(report, project, client, tmp_path)

    explanation = report.findings[0].explanation
    assert explanation is not None
    assert explanation.fix_status is FixStatus.NONE and explanation.edits == []
    assert "FIX ALLOWED: no" in client.requests[0][1]["content"]


def test_secret_is_never_sent_and_fix_still_applies(tmp_path: Path) -> None:
    report, project = _report_with("secrets_and_env", "security.hardcoded-secret")
    fix = [
        {
            "path": "client.py",
            "search": "import requests\n",
            "replace": "import os\n\nimport requests\n",
        },
        {
            "path": "client.py",
            "search": 'api_key = "<REDACTED_1>"',
            "replace": 'api_key = os.environ["API_KEY"]',
        },
    ]
    client = FakeClient(_answer(fix))

    _run(report, project, client, tmp_path)

    sent = json.dumps(client.requests)
    assert SECRET not in sent
    assert "<REDACTED_1>" in sent
    explanation = report.findings[0].explanation
    assert explanation is not None and explanation.fix_status is FixStatus.VERIFIED
    assert SECRET not in report.model_dump_json()


def test_cache_avoids_paying_twice(tmp_path: Path) -> None:
    report, project = _report_with("leaky_emg", "repro.hardcoded-path")
    _run(report, project, FakeClient(_answer(PATH_FIX)), tmp_path)

    again, project = _report_with("leaky_emg", "repro.hardcoded-path")
    client = FakeClient()  # any call would fail: no answers left
    _run(again, project, client, tmp_path)

    assert client.requests == []
    assert again.explain_stats is not None and again.explain_stats.cache_hits == 1
    assert again.findings[0].explanation is not None and again.findings[0].explanation.cached


def test_fatal_error_stops_the_run(tmp_path: Path) -> None:
    report, project = _report_with("leaky_emg", "repro.hardcoded-path")

    with pytest.raises(FatalLLMError):
        _run(report, project, FakeClient(FatalLLMError("bad key")), tmp_path)


def test_usage_and_cost_are_counted(tmp_path: Path) -> None:
    report, project = _report_with("leaky_emg", "repro.hardcoded-path")

    _run(report, project, FakeClient(_answer(PATH_FIX)), tmp_path)

    stats = report.explain_stats
    assert stats is not None
    assert (stats.api_calls, stats.input_tokens, stats.cached_input_tokens) == (1, 1000, 600)
    assert stats.estimated_cost_usd == pytest.approx((400 * 0.30 + 600 * 0.006 + 200 * 1.20) / 1e6)


def test_context_shows_enclosing_function_and_imports() -> None:
    report, project = _report_with("leaky_emg", "correctness.grouped-split-leakage")

    context = build_context(project, report.findings[0], fix_allowed=True)

    assert "def prepare_dataset" in context.text
    assert "from sklearn.model_selection import train_test_split" in context.text
    assert "FIX ALLOWED: yes" in context.text
    assert "flagged: line 18" in context.text
    assert context.files == ("data.py",)


def test_explain_without_key_fails_clearly(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from typer.testing import CliRunner

    from shipshape.cli import app

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    result = CliRunner().invoke(app, ["analyze", str(FIXTURES_DIR / "leaky_emg"), "--explain"])

    assert result.exit_code == 2
    assert "No API key" in result.output


def test_text_report_shows_explanation_and_diff(tmp_path: Path) -> None:
    from rich.console import Console

    from shipshape.render import render_report

    report, project = _report_with("leaky_emg", "repro.hardcoded-path")
    _run(report, project, FakeClient(_answer(PATH_FIX)), tmp_path)
    console = Console(record=True, width=120)

    render_report(report, console)

    text = console.export_text()
    assert "fix: verified" in text
    assert '+ DATA_DIR = os.environ.get("EMG_DATA_DIR", "data/raw")' in text
    assert "1 API calls" in text


def test_behaviour_change_is_kept_for_verified_fixes_and_shown(tmp_path: Path) -> None:
    from rich.console import Console

    from shipshape.render import render_report

    answer = json.loads(_answer(PATH_FIX))
    answer["behaviour_change"] = (
        "The script now reads data from data/raw unless EMG_DATA_DIR is set."
    )
    report, project = _report_with("leaky_emg", "repro.hardcoded-path")
    _run(report, project, FakeClient(json.dumps(answer)), tmp_path)
    console = Console(record=True, width=160)

    render_report(report, console)

    explanation = report.findings[0].explanation
    assert explanation is not None and explanation.behaviour_change.startswith("The script now")
    assert "Heads-up: The script now reads data" in console.export_text()


def test_prompt_asks_for_short_problem_first_answers() -> None:
    from shipshape.llm.prompts import SYSTEM_PROMPT

    assert "names the problem, not the fix" in SYSTEM_PROMPT
    assert "at most 3 short numbered steps" in SYSTEM_PROMPT
    assert '"behaviour_change"' in SYSTEM_PROMPT


class SlowClient:
    """Thread-safe fake: every call takes ``delay`` seconds and echoes the check id."""

    model = "deepseek-flash"

    def __init__(self, delay: float = 0.0, fail_with: Exception | None = None) -> None:
        import threading

        self.delay = delay
        self.fail_with = fail_with
        self.calls = 0
        self._lock = threading.Lock()

    def complete(self, messages: Sequence[Message]) -> Completion:
        import time

        with self._lock:
            self.calls += 1
        time.sleep(self.delay)
        if self.fail_with is not None:
            raise self.fail_with
        check = messages[1]["content"].splitlines()[0].removeprefix("Check: ")
        answer = json.loads(_answer())
        answer["summary"] = check
        return Completion(json.dumps(answer), 500, 0, 100, self.delay)


def test_findings_are_explained_in_parallel_and_stay_matched(tmp_path: Path) -> None:
    import time

    project = Project.load(FIXTURES_DIR / "leaky_emg")
    report = analyze_project(project)
    client = SlowClient(delay=0.3)

    started = time.perf_counter()
    explain_report(
        report,
        project,
        client,
        provider="deepseek",
        cache=ExplanationCache(tmp_path),
        concurrency=6,
    )
    elapsed = time.perf_counter() - started

    assert client.calls == len(report.findings) == 9
    assert elapsed < 9 * 0.3 * 0.6  # clearly faster than one after another
    for finding in report.findings:
        assert finding.explanation is not None
        assert finding.explanation.summary == finding.check_id


def test_fatal_error_cancels_findings_not_started(tmp_path: Path) -> None:
    project = Project.load(FIXTURES_DIR / "leaky_emg")
    report = analyze_project(project)
    client = SlowClient(delay=0.2, fail_with=FatalLLMError("no credit"))

    with pytest.raises(FatalLLMError):
        explain_report(
            report,
            project,
            client,
            provider="deepseek",
            cache=ExplanationCache(tmp_path),
            concurrency=2,
        )

    assert client.calls < len(report.findings)
