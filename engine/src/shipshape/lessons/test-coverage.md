---
concept: Test coverage where it matters
summary: Tests exist, but most larger modules are never touched by them; aim tests at the code whose mistakes would change your results.
---

## The idea

Having a `tests/` folder is the start; what matters is what the tests touch. If the tests only cover a utility module while the data loading, the splitting and the feature extraction are untested, the risky parts are still unprotected. Coverage tools measure which lines run during the tests. You do not need 100%: aim at the modules where a quiet bug would change your numbers or your conclusions.

## Before and after

```text
# Before
tests/test_utils.py      tests a string helper
data.py                  untested
features.py              untested
train.py                 untested
```

```text
# After
tests/test_utils.py
tests/test_data.py       loads a tiny example recording
tests/test_features.py   checks features on arrays computed by hand
tests/test_split.py      checks that subjects never cross the split
```

## Why engineers care

Tests in the wrong place give false confidence. Reviewers look at what is tested, not only that something is, and the parts closest to your results deserve the strongest checks.

## How Shipshape spots it

It looks at which modules the test files import. When half or more of the modules with 10 or more lines of code (and at least two of them) are never imported by any test, it lists them. Importing is a rough proxy: a module can be imported and still barely exercised. Run a coverage tool for the real numbers.

## Read more

- [coverage.py](https://coverage.readthedocs.io/)
- [pytest: good integration practices](https://docs.pytest.org/en/stable/explanation/goodpractices.html)
