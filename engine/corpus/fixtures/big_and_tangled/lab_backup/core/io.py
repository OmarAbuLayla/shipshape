"""Reading recordings."""

from __future__ import annotations


def read_lines(text: str) -> list[str]:
    """Split text into non-empty lines."""
    return [line for line in text.splitlines() if line.strip()]
