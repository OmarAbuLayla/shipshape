"""Training loop."""

from __future__ import annotations


def fit(values: list[float]) -> float:
    """Fit by returning the maximum."""
    return max(values, default=0.0)
