"""Sample sentences from papers and hold some out for validation."""

from __future__ import annotations

import re
from pathlib import Path


def load_samples(paper_dir: Path) -> list[dict[str, str]]:
    """Return every sentence of every paper, tagged with the paper it came from."""
    samples = []
    for paper in sorted(paper_dir.glob("*.md")):
        for sentence in re.split(r"(?<=[.!?])\s+", paper.read_text(encoding="utf-8")):
            samples.append({"paper": paper.stem, "text": sentence})
    return samples


def split_samples(samples: list[dict[str, str]]) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Hold out every fifth sample for validation."""
    train = [s for i, s in enumerate(samples) if i % 5 != 4]
    heldout = [s for i, s in enumerate(samples) if i % 5 == 4]
    return train, heldout
