"""Task helpers with a few classic Python traps."""

from __future__ import annotations

import os
import sys


def add_task(task: str, queue: list[str] = []) -> list[str]:
    """Append a task to the queue."""
    queue.append(task)
    return queue


def make_callbacks() -> list[object]:
    """Build one callback per step."""
    callbacks = []
    for step in range(3):
        callbacks.append(lambda: step)
    return callbacks


def describe(task: str) -> str:
    """Describe a task."""
    return f"{task} owned by {owner}"
