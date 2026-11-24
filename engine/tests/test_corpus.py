"""Regression test: every check must find exactly the issues planted in the fixture corpus."""

from shipshape.evaluation import evaluate, load_corpus

from .conftest import FIXTURES_DIR


def test_fixture_corpus_is_found_exactly() -> None:
    cases = load_corpus(FIXTURES_DIR)
    assert len(cases) >= 7

    result = evaluate(cases)

    assert result.errors == []
    assert result.mistakes == [], "\n".join(result.mistakes)
