"""Concept lessons: one short Markdown lesson for every concept a check teaches.

Lessons live next to this module as ``<slug>.md``, with a small front matter block::

    ---
    concept: Data leakage in evaluation
    summary: One sentence that shows up in lists.
    ---

followed by the sections "The idea", "Before and after", "Why engineers care", "How Shipshape
spots it" and "Read more". They are written by people, not generated, and the same for
everyone; which checks teach a lesson is derived from the checks themselves.
"""

from __future__ import annotations

from functools import cache
from importlib import resources

from pydantic import BaseModel, Field

from shipshape.checks import RULES, default_checks

SECTIONS = (
    "The idea",
    "Before and after",
    "Why engineers care",
    "How Shipshape spots it",
    "Read more",
)


class LessonError(ValueError):
    """A lesson file is malformed."""


class Lesson(BaseModel):
    """One concept lesson."""

    slug: str
    concept: str
    summary: str
    checks: list[str] = Field(default_factory=list)  # check ids that teach this concept
    body: str = Field(default="", description="Markdown, without the front matter.")


def concept_checks() -> dict[str, list[str]]:
    """Every concept taught by a built-in check or lint rule, with the check ids teaching it."""
    concepts: dict[str, list[str]] = {}
    for check in default_checks():
        if check.id != "lint":
            concepts.setdefault(check.concept, []).append(check.id)
    for rule in RULES.values():
        concepts.setdefault(rule.concept, []).append(rule.check_id)
    return {concept: sorted(set(ids)) for concept, ids in concepts.items()}


def parse_lesson(slug: str, text: str) -> Lesson:
    """Split front matter from the Markdown body."""
    if not text.startswith("---\n"):
        raise LessonError(f"{slug}: missing front matter")
    try:
        header, body = text[4:].split("\n---\n", 1)
    except ValueError as exc:
        raise LessonError(f"{slug}: unterminated front matter") from exc
    fields = {}
    for line in header.splitlines():
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip()
    missing = {"concept", "summary"} - fields.keys()
    if missing:
        raise LessonError(f"{slug}: front matter lacks {', '.join(sorted(missing))}")
    return Lesson(
        slug=slug, concept=fields["concept"], summary=fields["summary"], body=body.strip()
    )


@cache
def all_lessons() -> tuple[Lesson, ...]:
    """Every bundled lesson, sorted by concept, with the checks that teach it."""
    checks = concept_checks()
    lessons = []
    for entry in resources.files(__name__).iterdir():
        if entry.name.endswith(".md"):
            lesson = parse_lesson(entry.name[:-3], entry.read_text(encoding="utf-8"))
            lesson.checks = checks.get(lesson.concept, [])
            lessons.append(lesson)
    return tuple(sorted(lessons, key=lambda item: item.concept.lower()))


def find_lesson(name: str) -> Lesson | None:
    """Look a lesson up by slug, concept or check id (case-insensitive)."""
    wanted = name.strip().lower()
    for lesson in all_lessons():
        if wanted in {lesson.slug, lesson.concept.lower(), *(c.lower() for c in lesson.checks)}:
            return lesson
    return None
