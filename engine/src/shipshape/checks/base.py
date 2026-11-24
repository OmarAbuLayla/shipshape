"""The interface every check implements."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import ClassVar

from shipshape.models import Dimension, Finding, Location, Severity
from shipshape.project import Project


class Check(ABC):
    """A single, independent analysis. Subclasses set the class attributes and ``run``."""

    id: ClassVar[str]
    title: ClassVar[str]
    severity: ClassVar[Severity]
    dimension: ClassVar[Dimension]
    concept: ClassVar[str]

    @abstractmethod
    def run(self, project: Project) -> list[Finding]:
        """Analyse ``project`` and return zero or more findings."""

    def finding(
        self,
        message: str,
        locations: Sequence[Location],
        *,
        evidence: str = "",
        severity: Severity | None = None,
    ) -> Finding:
        """Build a finding pre-filled with this check's metadata."""
        return Finding(
            check_id=self.id,
            title=self.title,
            severity=severity or self.severity,
            dimension=self.dimension,
            concept=self.concept,
            message=message,
            locations=list(locations),
            evidence=evidence,
        )


def plural(count: int, word: str, plural_form: str | None = None) -> str:
    """Return ``"1 file"`` / ``"3 files"``."""
    return f"{count} {word if count == 1 else (plural_form or word + 's')}"


def examples(items: Sequence[str], limit: int = 3) -> str:
    """Join up to ``limit`` unique items as inline code, e.g. ``"`a`, `b` and 2 more"``."""
    unique = list(dict.fromkeys(items))
    shown = ", ".join(f"`{item}`" for item in unique[:limit])
    rest = len(unique) - limit
    return f"{shown} and {rest} more" if rest > 0 else shown
