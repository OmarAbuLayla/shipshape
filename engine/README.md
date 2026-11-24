# shipshape (engine)

The analysis engine behind Shipshape. It scans a Python project, including notebooks, and reports findings, each with a severity, a quality dimension, a plain-language explanation and the concept it teaches. It never executes the project's code.

```bash
shipshape analyze path/to/project              # readable report with a scorecard
shipshape analyze path/to/project -o out.json  # also write the JSON report
shipshape analyze path/to/project --export findings.md   # or .json / .csv, with or without --explain
shipshape map path/to/project --html map.html  # architecture map (interactive page)
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
| | `structure.import-cycle` | Modules that import each other at module level (lazy imports inside functions don't count) |
| Reproducibility | `repro.hardcoded-path` | Absolute, machine-specific paths in string literals (test files are skipped) |
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

## Leaving things out, visibly

Some files in a project are not its real code: generated files, vendored copies, or deliberately broken examples used by tests. List them in a `.shipshapeignore` file (gitignore-style patterns, relative to the file's folder; nested files work) and they are not scanned. A line `check:<id>` (wildcards allowed, e.g. `check:lint.*`) switches a check off for the project. For one deliberate line, add a comment on that line: `# shipshape: ignore[security.hardcoded-secret] fake key for tests`, or `# shipshape: ignore` for every check.

Nothing is dropped silently. Every report, in the terminal, the web app and all exports, lists how many files were left out and by which patterns, which checks were switched off, and every suppressed location. The scoring formula never changes; only what the project itself declared out of scope is left out of it.

Test files are also treated more gently by default, because they do things on purpose that would be a problem elsewhere: absolute paths in tests are not flagged, and a credential-like value found only in tests is reported as minor (with a hint to mark it as fake) instead of critical.

## Explanations and fixes (optional, needs an LLM key)

```bash
cp ../.env.example ../.env          # then add your DeepSeek key and pick a model
shipshape llm-check --ping          # confirm the key and model work
shipshape analyze path/to/project --explain   # explanations + verified fixes
```

With `--explain`, the most severe findings (15 by default, `--max-findings` to change) each get a plain-language explanation: what is going on in this code, why an engineer cares, and how to fix it. For checks where a small local edit is the right fix (hard-coded paths, missing seeds, leakage splits, swallowed exceptions, the lint bugs, ...), the model also proposes search-and-replace edits. A fix is only shown as **verified** if, applied in memory, the edits match exactly, the file still parses, the original finding is gone, and no other check reports anything new in the changed files. Otherwise the model gets one retry with the reason, and then the fix is dropped. Verified means "valid and removes the problem", not "behaves the same": Shipshape never runs code.

What leaves your machine: the finding and the code around it (the enclosing function plus the top of the file). Credentials are replaced with `<REDACTED_n>` before sending, `.env` files are never sent, and the run prints which provider receives the code. With DeepSeek that is a server in China; don't use `--explain` on code you may not share. Answers are cached in `~/.shipshape/cache`, so unchanged code is never paid for twice, and every run ends with its API calls, tokens and estimated cost. `shipshape explain-eval corpus/fixtures` runs the real model over the whole corpus and reports fix rates per check (this costs money).

## Applying fixes

```bash
shipshape fix path/to/project --patch fixes.patch   # then, inside the project: git apply fixes.patch
shipshape fix path/to/project --zip fixed.zip       # or a fixed copy of the whole project
shipshape fix path/to/project --only repro.hardcoded-path   # only some checks
```

`fix` explains the findings (like `--explain`), applies every verified fix to an in-memory copy, and scans the copy again, printing scores before and after. Fixes are applied one at a time, and each one is verified again against the code as the earlier fixes left it. Two fixes for the same lines would otherwise collide; a fix that no longer fits is skipped with the reason, never forced, and a fresh scan of the fixed code gives a new one. The project folder is never changed, and the patch and zip must be written outside it. The web app offers the same: tick the fixes you want, press "Apply fixes", and download the patch or the fixed project.

The same limit as before applies: Shipshape never runs code, so a verified fix is valid and removes the problem, but run your tests once after applying.

## Architecture map

Every report includes a `graph`: files, notebooks and folders as nodes, internal imports as edges, test files linked to what they test, hard-coded data paths as external nodes, and missing pieces (no tests, no environment file) as dashed ghost nodes. Each node lists the findings pinned to it. Imports are resolved the way projects are actually run: `src/` layouts, packages, relative imports and "import the file next to me" all work, and when two files share a name the closest one wins.

Below the map, every report has `files`: each scanned file's blocks (top-level functions, classes and their methods, notebook cells, and the module-level code around them) with their line ranges, size and complexity, the findings that fall inside them, and which blocks of the same file call each other. Calls are matched by name inside one file, so they are a guide, not a complete call graph. Each file also carries a fingerprint of the scanned text, so a viewer can tell when the file changed since the scan.

`shipshape map --html map.html` writes a standalone page that draws it. Large projects open in a folder overview (one box per folder, arrows labelled with import counts), and "All files" shows every module. The page loads its layout library from a CDN, so it needs an internet connection.

## Measuring the checks

`corpus/fixtures/` holds small projects with planted issues and an `expected.yaml` each, including a clean negative control. `tests/test_corpus.py` requires every check to find exactly those issues: no misses and no false positives. See [docs/corpus.md](../docs/corpus.md) for labelling your own projects.

## Limitations

The checks are static heuristics. The leakage check recognises common split patterns, not leakage hidden in custom code or in how the data was collected, so it is phrased as a question. Thresholds were tuned on a small corpus. The map shows imports and literal file paths, not true data flow, and dynamic imports (`importlib`, `sys.path` tricks) are invisible to it. Type checking with mypy is not included, because it needs the scanned project's dependencies installed to be meaningful.
