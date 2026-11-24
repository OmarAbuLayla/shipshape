"""The local skill profile: projects, current concepts, and what was resolved."""

from __future__ import annotations

import json

from shipshape_api.profile import build_profile
from shipshape_api.store import ScanStatus, ScanSummary

LEAK = ("Data leakage in evaluation", "critical", "correctness", 1)
PATHS = ("Config over hard-coding", "major", "reproducibility", 2)
PRINTS = ("Logging instead of printing", "minor", "readability", 5)


def _scan(
    scan_id: str,
    name: str,
    when: str,
    grade: str,
    *concepts: tuple[str, str, str, int],
    source: str = "path",
) -> tuple[ScanSummary, str]:
    findings = [
        {"concept": c, "severity": s, "dimension": d, "locations": [{"path": "x.py"}] * n}
        for c, s, d, n in concepts
    ]
    report = {"findings": findings, "files_scanned": ["x.py"]}
    summary = ScanSummary(
        id=scan_id, name=name, source=source, explain=False, status=ScanStatus.DONE, progress="",
        error="", created_at=when, finished_at=when, grade=grade, findings=len(findings),
    )  # fmt: skip
    return summary, json.dumps(report)


def test_latest_scan_counts_and_earlier_concepts_are_resolved() -> None:
    a1, r1 = _scan("a1", "emg", "2026-11-01", "D", LEAK, PATHS)
    a2, r2 = _scan("a2", "emg", "2026-11-20", "B", PATHS, PRINTS)
    b1, r3 = _scan("b1", "thesis", "2026-11-10", "C", PATHS)

    profile = build_profile([(a1, "/p/emg", r1), (b1, "/p/thesis", r3), (a2, "/p/emg", r2)])

    assert profile.scans == 3
    concepts = {c.concept: c for c in profile.concepts}
    assert profile.concepts[0].concept == "Config over hard-coding"  # in the most projects
    assert concepts["Config over hard-coding"].projects == ["emg", "thesis"]
    assert concepts["Config over hard-coding"].places == 4
    assert concepts["Data leakage in evaluation"].projects == []
    assert concepts["Data leakage in evaluation"].resolved_in == ["emg"]
    assert concepts["Data leakage in evaluation"].lesson == "data-leakage"
    assert concepts["Logging instead of printing"].severity == "minor"
    emg = next(p for p in profile.projects if p.name == "emg")
    assert (emg.scans, emg.first_grade, emg.latest_grade, emg.latest_scan) == (2, "D", "B", "a2")
    assert [p.name for p in profile.projects] == ["emg", "thesis"]  # most recent first


def test_projects_are_told_apart_and_old_scans_join_their_folder() -> None:
    one, r1 = _scan("1", "analysis", "2026-11-01", "C", PATHS)
    two, r2 = _scan("2", "analysis", "2026-11-02", "B", PATHS)
    old, r3 = _scan("3", "thesis", "2026-10-01", "D", LEAK)
    new, r4 = _scan("4", "thesis", "2026-11-03", "C", PATHS)
    upload, r5 = _scan("5", "thesis", "2026-11-04", "A", source="upload")

    profile = build_profile(
        [(old, None, r3), (one, "/lab/a/analysis", r1), (two, "/lab/b/analysis", r2),
         (new, "/home/thesis", r4), (upload, None, r5)]
    )  # fmt: skip

    names = sorted(p.name for p in profile.projects)
    assert names == ["analysis (a)", "analysis (b)", "thesis (home)", "thesis (upload)"]
    thesis = next(p for p in profile.projects if p.name == "thesis (home)")
    assert thesis.scans == 2  # the scan without a recorded folder joined it
    leak = next(c for c in profile.concepts if c.concept == "Data leakage in evaluation")
    assert leak.resolved_in == ["thesis (home)"]


def test_empty_history() -> None:
    profile = build_profile([])

    assert profile.scans == 0 and profile.projects == [] and profile.concepts == []


def test_problems_in_files_no_longer_scanned_are_not_resolved() -> None:
    first, r1 = _scan("1", "lab", "2026-11-01", "D", LEAK, PATHS)
    raw = json.loads(r1)
    raw["findings"][0]["locations"] = [{"path": "fixtures/bad.py"}]  # the leak was in a fixture
    raw["files_scanned"] = ["x.py", "fixtures/bad.py"]
    later, r2 = _scan("2", "lab", "2026-11-02", "B")  # fixtures now left out, paths fixed

    profile = build_profile([(first, "/lab", json.dumps(raw)), (later, "/lab", r2)])

    resolved = {c.concept for c in profile.concepts if c.resolved_in}
    assert resolved == {"Config over hard-coding"}


def test_silenced_problems_are_not_resolved() -> None:
    first, r1 = _scan(
        "1", "lab", "2026-11-01", "C", ("Keeping secrets out of git", "critical", "security", 1)
    )
    later, r2 = _scan("2", "lab", "2026-11-02", "A")
    raw = json.loads(r2)
    raw["exclusions"] = {
        "suppressed": [
            {
                "check_id": "security.hardcoded-secret",
                "title": "t",
                "location": {"path": "x.py"},
                "how": "inline comment",
            }
        ]
    }

    profile = build_profile([(first, "/lab", r1), (later, "/lab", json.dumps(raw))])

    assert [c for c in profile.concepts if c.resolved_in] == []
