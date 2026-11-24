# shipshape (engine)

The analysis engine behind Shipshape. It scans a Python project, including notebooks, and reports findings, each with a severity, a quality dimension, a plain-language explanation and the concept it teaches. It never executes the project's code.

```bash
shipshape analyze path/to/project              # readable report with a scorecard
shipshape analyze path/to/project -o out.json  # also write the JSON report
shipshape checks                               # list every check
shipshape eval corpus/fixtures --strict        # precision/recall against labelled projects
```

## Checks

| Dimension | Check | What it looks for |
|---|---|---|
| Correctness | `correctness.grouped-split-leakage` | Sample-wise splits (`train_test_split`, `KFold`, `i % 5 == 4`) in files that also track subjects, patients, papers or similar, without a group-aware splitter |
| | `correctness.swallowed-exception` | Bare `except:` and `except Exception: pass` without a comment explaining why |
| Structure | `structure.oversized-file` | Files with 400+ (minor) or 700+ (major) lines of code |
| | `structure.complex-function` | Cyclomatic complexity of 15 or more (radon) |
| | `structure.duplicated-package` | The same package copied into several folders |
| Reproducibility | `repro.hardcoded-path` | Absolute, machine-specific paths in string literals |
| | `repro.missing-environment` | Third-party imports but no requirements/environment/pyproject file |
| | `repro.unpinned-dependencies` | Requirements without exact versions |
| | `repro.missing-seed` | Random calls, shuffling splits or weight init with no seed anywhere |
| Security | `security.env-file-not-ignored` | A `.env` file git would commit (asks `git check-ignore`; the file is never read) |
| | `security.hardcoded-secret` | Known key formats and credential-named variables with key-like values (always redacted) |
| Readability | `readability.print-debugging` | `print()` in importable modules (scripts, CLIs and UI code are exempt) |
| | `readability.restating-comments` | Comments that narrate the next line instead of explaining why |
| | `readability.missing-type-hints` | Most public functions unannotated |
| | `readability.missing-docstrings` | Most public definitions of 8+ lines undocumented |
| Testing | `testing.no-tests` | Two or more modules and no tests |
| | `testing.untested-modules` | Most larger modules never imported by a test |
| (any) | `lint.*` | A curated set of 11 ruff rules (undefined names, mutable defaults, unused imports, ...) |

Grouped issues become one finding with many locations, so a project with 100 prints gets one finding, not 100. Thresholds are constants at the top of each check module.

## Measuring the checks

`corpus/fixtures/` holds small projects with planted issues and an `expected.yaml` each, including a clean negative control. `tests/test_corpus.py` requires every check to find exactly those issues: no misses and no false positives. See [docs/corpus.md](../docs/corpus.md) for labelling your own projects.

## Limitations

The checks are static heuristics. The leakage check recognises common split patterns, not leakage hidden in custom code or in how the data was collected, so it is phrased as a question. Thresholds were tuned on a small corpus. Type checking with mypy is not included, because it needs the scanned project's dependencies installed to be meaningful.
