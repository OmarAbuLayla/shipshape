"""A trivial model."""

from __future__ import annotations


def predict(values: list[float]) -> float:
    """Return the mean as the prediction."""
    return sum(values) / max(len(values), 1)
