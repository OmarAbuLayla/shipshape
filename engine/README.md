# shipshape (engine)

The analysis engine behind Shipshape. It scans a Python project, including notebooks, and reports findings, each with a severity, a quality dimension, a plain-language explanation and the concept it teaches. It never executes the project's code.

```bash
shipshape analyze path/to/project              # readable report with a scorecard
shipshape analyze path/to/project -o out.json  # also write the JSON report
shipshape analyze path/to/project --export findings.md   # or .json / .csv, with or without --explain
shipshape map path/to/project --html map.html  # architecture map (interactive page)
shipshape checks                               # list every check
shipshape lessons data-leakage                 # the lesson behind a check (omit the name to list all)
shipshape eval corpus/fixtures --strict        # precision/recall against labelled projects
```

## Checks

| Dimension | Check | What it looks for |
|---|---|---|
| Correctness | `correctness.grouped-split-leakage` | Sample-wise splits (`train_test_split`, `KFold`, `i % 5 == 4`, shuffled indices sliced into parts, `sample(frac=...)` with `drop`) in files and notebooks that also track subjects, patients, papers or similar, without a group-aware splitter |
| | `correctness.swallowed-exception` | Bare `except:` and `except Exception: pass` without a comment explaining why |
| | `correctness.array-none-comparison` | `== None` / `!= None` on a name that clearly holds a pandas or numpy object (assigned from `pd.`/`np.`, used with DataFrame methods, or merged): it crashes in an `if` |
| Structure | `structure.oversized-file` | Files with 400+ (minor) or 700+ (major) lines of code |
| | `structure.complex-function` | Cyclomatic complexity of 15 or more (radon) |
| | `structure.duplicated-package` | The same package copied into several folders: same-named packages by file names, renamed copies (`data` / `data_old`) by content |
| | `structure.copied-files` | The same file (or one with 85%+ identical code lines) in several places, e.g. one copy per experiment folder; copied packages are left to `structure.duplicated-package` |
| | `structure.unused-module` | Modules no file, test or notebook imports and that run nothing themselves (scripts, `__init__.py`, example folders and installable libraries are left out) |
| | `structure.import-cycle` | Modules that import each other at module level (lazy imports inside functions don't count) |
| Reproducibility | `repro.hardcoded-path` | Absolute, machine-specific paths in string literals (test files are skipped) |
| | `repro.missing-environment` | Third-party imports but no requirements/environment/pyproject file |
| | `repro.unpinned-dependencies` | Requirements without exact versions |
| | `repro.broken-local-import` | `import x.py`, and imports of project modules that only exist in other folders, so the script fails unless PYTHONPATH is set by hand (files in packages, tests and files that edit `sys.path` are left out) |
| | `repro.missing-seed` | Random calls, shuffling splits or weight init with no seed anywhere |
| Security | `security.env-file-not-ignored` | A `.env` file git would commit (asks `git check-ignore`; the file is never read) |
| | `security.hardcoded-secret` | Known key formats and credential-named variables with key-like values (always redacted) |
| Readability | `readability.print-debugging` | `print()` in importable modules (scripts, CLIs and UI code are exempt) |
| | `readability.restating-comments` | Comments that narrate the next line instead of explaining why |
| | `readability.missing-type-hints` | Most public functions unannotated |
| | `readability.missing-docstrings` | Most public definitions of 8+ lines undocumented |
| Testing | `testing.no-tests` | Two or more modules and no tests (a file named like a test only counts if it contains test functions, test classes or a pytest/unittest import) |
| | `testing.untested-modules` | Most modules with 10+ lines of code never imported by a test |
| (any) | `lint.*` | A curated set of 11 ruff rules (undefined names, mutable defaults, unused imports, ...) |

Grouped issues become one finding with many locations, so a project with 100 prints gets one finding, not 100. Thresholds are constants at the top of each check module.

## Lessons

Every finding names the concept it teaches, and every concept has a short lesson in `src/shipshape/lessons/`: the idea in plain words, a small before and after, why engineers care, how Shipshape detects it (and what it misses), and a few links. They are written by people, not generated, and a test makes sure every concept has one, every Python example parses and every link is `https`. Read them with `shipshape lessons`, in the web app ("Read the lesson" on any finding, or the Lessons page), or as plain Markdown.

## Leaving things out, visibly

Some files in a project are not its real code: generated files, vendored copies, or deliberately broken examples used by tests. List them in a `.shipshapeignore` file (gitignore-style patterns, relative to the file's folder; nested files work) and they are not scanned. A line `check:<id>` (wildcards allowed, e.g. `check:lint.*`) switches a check off for the project. For one deliberate line, add a comment on that line: `# shipshape: ignore[security.hardcoded-secret] fake key for tests`, or `# shipshape: ignore` for every check.

Nothing is dropped silently. Every report, in the terminal, the web app and all exports, lists how many files were left out and by which patterns, which checks were switched off, and every suppressed location. The scoring formula never changes; only what the project itself declared out of scope is left out of it.

Test files are also treated more gently by default, because they do things on purpose that would be a problem elsewhere: absolute paths in tests are not flagged, and a credential-like value found only in tests is reported as minor (with a hint to mark it as fake) instead of critical.

## Explanations and fixes (optional, needs an LLM key)

```bash
cp ../.env.example ../.env          # then pick a provider (deepseek, openai, openai-compatible), add its key and a model
shipshape llm-check --ping          # confirm the key and model work
shipshape analyze path/to/project --explain   # explanations + verified fixes
```

With `--explain`, the most severe findings (15 by default, `--max-findings` to change) each get a plain-language explanation: what is going on in this code, why an engineer cares, and how to fix it. For checks where a small local edit is the right fix (hard-coded paths, missing seeds, leakage splits, swallowed exceptions, the lint bugs, ...), the model also proposes search-and-replace edits. A fix is only shown as **verified** if, applied in memory, the edits match exactly, the file still parses, the original finding is gone, and no other check reports anything new in the changed files. Otherwise the model gets one retry with the reason, and then the fix is dropped. Verified means "valid and removes the problem", not "behaves the same": Shipshape never runs code.

What leaves your machine: the finding and the code around it (the enclosing function plus the top of the file). Credentials are replaced with `<REDACTED_n>` before sending, `.env` files are never sent, and the run prints which provider receives the code. Where it goes depends on the provider (DeepSeek's servers are in China; a local Ollama keeps everything on your machine), so check before using `--explain` on code you may not share. Answers are cached in `~/.shipshape/cache`, so unchanged code is never paid for twice, and every run ends with its API calls, tokens and (for DeepSeek's models) estimated cost. `shipshape explain-eval corpus/fixtures` runs the real model over the whole corpus and reports fix rates per check (this costs money).

## Applying fixes

```bash
shipshape fix path/to/project --patch fixes.patch   # then, inside the project: git apply fixes.patch
shipshape fix path/to/project --zip fixed.zip       # or a fixed copy of the whole project
shipshape fix path/to/project --only repro.hardcoded-path   # only some checks
```

`fix` explains the findings (like `--explain`), applies every verified fix to an in-memory copy, and scans the copy again, printing scores before and after. Fixes are applied one at a time, and each one is verified again against the code as the earlier fixes left it. Two fixes for the same lines would otherwise collide; a fix that no longer fits is never forced. Instead it gets one second round: the problem is explained again against the already fixed code (one more LLM call), and the new fix is verified and applied the same way; if that fails too, it is skipped with the reason (`--no-second-round` turns this off). Patches and zips keep each file's line endings, so Windows (CRLF) files apply cleanly. The project folder is never changed, and the patch and zip must be written outside it. The web app offers the same: tick the fixes you want, press "Apply fixes", and download the patch or the fixed project.

The same limit as before applies: Shipshape never runs code, so a verified fix is valid and removes the problem, but run your tests once after applying.

## The agent

```bash
shipshape agent path/to/project --patch agent.patch --zip fixed.zip --log agent.md
shipshape agent path/to/project --max-steps 20 --max-cost 0.05
```

An LLM (the configured provider, with tool calling) works through the findings with four tools: `list_findings`, `read_file`, `propose_fix` and `finish`. The model decides what to look at and what to change; Shipshape decides what is accepted. Every proposed fix goes through the same gates as the verified fixes and is applied only if it passes, to an in-memory copy, so the next step sees the improved code. Guard rails: a limit on model turns (30 by default), an estimated-cost limit ($0.10, enforced for models with a known price), and a doom-loop guard that blocks a finding after three rejected fixes. Credentials are redacted from everything the model reads; a secret line can be replaced by line number without the model ever seeing the value. Every step is printed and can be saved as a Markdown log. The project folder is never changed.

## Inside a coding assistant (MCP)

`shipshape-mcp` is an MCP server over stdio for Claude Code and other MCP clients; the [plugin](../plugin/README.md) starts it for you. In this mode the assistant is the LLM, and the server offers four tools:

| Tool | What it does |
|---|---|
| `scan(path, max_findings=50)` | The report as compact text: grade, each score with the findings that lowered it and how the grade is computed, and each finding with its check id, locations, message and lesson |
| `verify_fix(path, check_id, edits)` | Runs the fix gates above on the assistant's own edits (an exact search text, or whole lines by number so a secret never has to be quoted), in memory: PASSED, naming any places the problem is still reported in other files, or REJECTED with the reason |
| `lesson(name)` | A lesson by slug, concept or check id; empty lists them all |
| `map(path, output)` | Writes the standalone map page, by default to the temporary folder |

Since the assistant can read the whole project, its edits may touch any `.py` file, and the gate is stricter in return: in every edited file, every place the finding was reported must be gone. The server never writes to the project; the assistant applies a fix itself after it passed. Notebook cells cannot be verified.

## Architecture map

Every report includes a `graph`: files, notebooks and folders as nodes, internal imports as edges, test files linked to what they test, hard-coded data paths as external nodes, and missing pieces (no tests, no environment file) as dashed ghost nodes. Each node lists the findings pinned to it. Imports are resolved the way projects are actually run: `src/` layouts, packages, relative imports and "import the file next to me" all work, and when two files share a name the closest one wins.

Below the map, every report has `files`: each scanned file's blocks (top-level functions, classes and their methods, notebook cells, and the module-level code around them) with their line ranges, size and complexity, the findings that fall inside them, and which blocks of the same file call each other. Calls are matched by name inside one file, so they are a guide, not a complete call graph. Each file also carries a fingerprint of the scanned text, so a viewer can tell when the file changed since the scan.

`shipshape map --html map.html` writes a standalone page that draws it. Large projects open in a folder overview (one box per folder, arrows labelled with import counts), and "All files" shows every module. The page loads its layout library from a CDN, so it needs an internet connection.

## Measuring the checks

`corpus/fixtures/` holds small projects with planted issues and an `expected.yaml` each, including a clean negative control. `tests/test_corpus.py` requires every check to find exactly those issues: no misses and no false positives. See [docs/corpus.md](../docs/corpus.md) for labelling your own projects.

## Limitations

The checks are static heuristics. The leakage check recognises common split patterns, not leakage hidden in custom code or in how the data was collected, so it is phrased as a question. Thresholds were tuned on a small corpus. The map shows imports and literal file paths, not true data flow, and dynamic imports (`importlib`, `sys.path` tricks) are invisible to it. Type checking with mypy is not included, because it needs the scanned project's dependencies installed to be meaningful.
