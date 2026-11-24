"""Every concept a check teaches has a well-formed lesson, and every example in it is Python."""

from __future__ import annotations

import ast
import re

import pytest
from typer.testing import CliRunner

from shipshape.cli import app
from shipshape.lessons import (
    SECTIONS,
    LessonError,
    all_lessons,
    concept_checks,
    find_lesson,
    parse_lesson,
)

CODE_BLOCK = re.compile(r"```(\w*)\n(.*?)```", re.DOTALL)
LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


def test_every_concept_has_exactly_one_lesson() -> None:
    concepts = [lesson.concept for lesson in all_lessons()]

    assert sorted(concepts) == sorted(concept_checks())
    assert len(concepts) == len(set(concepts))


@pytest.mark.parametrize("lesson", all_lessons(), ids=lambda lesson: lesson.slug)
def test_lesson_is_complete(lesson) -> None:  # type: ignore[no-untyped-def]
    headings = re.findall(r"^## (.+)$", lesson.body, re.MULTILINE)
    assert headings == list(SECTIONS)
    assert lesson.checks, "a lesson no check links to"
    assert 20 < len(lesson.summary) < 200
    links = LINK.findall(CODE_BLOCK.sub("", lesson.body))  # code like `f[x](y)` is not a link
    assert links and all(url.startswith("https://") for url in links)
    blocks = CODE_BLOCK.findall(lesson.body)
    assert blocks, "a lesson without a before/after example"
    for language, code in blocks:
        assert language in {"python", "text"}
        if language == "python":
            ast.parse(code)  # examples must at least be valid Python


def test_find_by_slug_concept_or_check() -> None:
    lesson = find_lesson("data-leakage")

    assert lesson is not None and lesson.concept == "Data leakage in evaluation"
    assert find_lesson("DATA LEAKAGE IN EVALUATION") == lesson
    assert find_lesson("correctness.grouped-split-leakage") == lesson
    assert find_lesson("lint.mutable-default") == find_lesson("mutable-defaults")
    assert find_lesson("nothing like this") is None


def test_malformed_lessons_are_rejected() -> None:
    with pytest.raises(LessonError):
        parse_lesson("x", "# no front matter\n")
    with pytest.raises(LessonError):
        parse_lesson("x", "---\nconcept: C\n---\nbody\n")


def test_cli_lists_and_shows_lessons() -> None:
    runner = CliRunner()

    listing = runner.invoke(app, ["lessons"], env={"COLUMNS": "200"})
    shown = runner.invoke(app, ["lessons", "mutable-defaults"])
    unknown = runner.invoke(app, ["lessons", "nope"])

    assert listing.exit_code == 0 and "Data leakage in evaluation" in listing.output
    assert shown.exit_code == 0 and "default values once" in shown.output
    assert unknown.exit_code == 2
