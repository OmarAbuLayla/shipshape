# Evaluating the checks

Shipshape's checks are judged like a classifier. For every check we count:

- **Precision**: of the locations it reported, how many were real issues.
- **Recall**: of the issues we know about, how many it found.

## Public fixture corpus

`engine/corpus/fixtures/` contains small projects with deliberately planted issues. Each has an `expected.yaml`:

```yaml
expected:
  - {check: repro.hardcoded-path, path: train.py, line: 7}   # line matches within +-1
  - {check: repro.missing-seed, path: analysis.ipynb, cell: 3, line: 1}
  - {check: testing.no-tests, path: "."}                     # "." = whole project
```

`clean_project` expects nothing, so any finding there is a false positive. The test suite runs the corpus and fails on any miss or false positive.

## Private real-project corpus

Real projects can't live in the repository, so they're listed in a manifest inside `local/` (git-ignored):

```yaml
# local/real_corpus.yaml
projects:
  - name: writing-humanizer
    root: C:/path/to/Writing Humanizer
    expected:
      - {check: correctness.grouped-split-leakage, path: main.py, line: 128}
```

```bash
shipshape eval --manifest local/real_corpus.yaml
shipshape eval engine/corpus/fixtures --manifest local/real_corpus.yaml   # both
```

When you add a check, add a fixture that triggers it and make sure the clean project stays clean.
