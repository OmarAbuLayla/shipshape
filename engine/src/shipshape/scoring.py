"""Turn findings into a rough 0-100 score per dimension and an overall letter grade.

The numbers are a guide for spotting where the biggest problems are, not a measurement.
"""

from __future__ import annotations

from collections.abc import Iterable

from shipshape.models import Dimension, Finding, Severity

PENALTY: dict[Severity, int] = {Severity.CRITICAL: 40, Severity.MAJOR: 15, Severity.MINOR: 5}
GRADES: tuple[tuple[int, str], ...] = ((90, "A"), (75, "B"), (60, "C"), (40, "D"))


def dimension_scores(findings: Iterable[Finding]) -> dict[Dimension, int]:
    """Start every dimension at 100 and subtract a fixed penalty per finding."""
    scores = dict.fromkeys(Dimension, 100)
    for finding in findings:
        scores[finding.dimension] = max(0, scores[finding.dimension] - PENALTY[finding.severity])
    return scores


def overall_grade(scores: dict[Dimension, int]) -> str:
    """Letter grade from the average dimension score."""
    average = sum(scores.values()) / len(scores) if scores else 100
    return next((letter for limit, letter in GRADES if average >= limit), "E")
