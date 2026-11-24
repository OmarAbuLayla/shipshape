---
concept: Writing your first tests
summary: A handful of small tests turns "I think it works" into "it still works after every change"; pytest makes the first one take five minutes.
---

## The idea

A test is a small function that runs a piece of your code and checks the result. You do not need to test everything, and you do not need a framework course. Start with the parts where a silent mistake would hurt most: a feature function on a tiny array you can check by hand, a split that must keep subjects apart, a loader on a two-line example file. Put them in a `tests/` folder, name files `test_*.py`, and run `pytest`.

Once a few tests exist, every refactor and every fix comes with a safety net: if something breaks, you know within seconds.

## Before and after

```python
# Before: the only check is running the whole experiment and eyeballing the score
```

```python
# After: tests/test_features.py, run with `pytest`
import numpy as np

from features import rms


def test_rms_of_a_constant_signal_is_its_absolute_value():
    assert rms(np.full(100, -2.0)) == 2.0


def test_split_keeps_subjects_apart():
    train, test = split_by_subject(subjects=np.array([1, 1, 2, 2, 3, 3]))
    assert set(train).isdisjoint(set(test))
```

## Why engineers care

Without tests, every change is a gamble, and people stop improving code because they are afraid to break it. With tests, code can evolve. For job applications, a `tests/` folder is one of the first things a reviewer looks for in a repository.

## How Shipshape spots it

It reports a project with two or more Python modules and no test files at all (no `test_*.py`, `*_test.py` or `tests/` folder). It does not run tests or measure how much they cover; see "Test coverage where it matters" for the next step.

## Read more

- [pytest: get started](https://docs.pytest.org/en/stable/getting-started.html)
