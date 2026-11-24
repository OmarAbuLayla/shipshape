# Shipshape

**Code is cheap now. Judgment isn't.**

Shipshape takes a vibe-coded project and shows you, on a map of your own code, what a senior engineer would object to and why. Then it helps you fix it. You end up with code a team would accept, and you learn the judgment behind it.

It is built first for people whose code gets judged by someone else, like researchers, students and domain experts, and it knows research-specific pitfalls such as data leakage across subjects, missing random seeds and unpinned environments.

> **Status:** Phase 3 of 8 built. The engine runs 29 checks (18 custom + 11 curated ruff rules) on Python projects and notebooks, measured against a fixture corpus, draws an architecture map, and (optionally, with an LLM key) explains findings in plain language with statically verified fixes. No web app yet. See the [roadmap](docs/ROADMAP.md).

## How it works

1. **Analyze.** Deterministic tools (ruff, mypy, radon and custom AST checks) find concrete problems.
2. **Map.** The project is drawn as an architecture map, with each problem pinned where it happens.
3. **Explain.** An LLM explains each finding in plain language, grounded in the tool output and the exact lines.
4. **Fix and learn.** Validated fixes are applied as diffs, and every fix links to a short lesson on the concept behind it.

## Repository layout

```
engine/   Python analysis engine and CLI (the core)
api/      FastAPI service (Phase 4)
web/      React + TypeScript review screen (Phase 4)
docs/     Roadmap and design notes
```

## Getting started

Requires [conda](https://docs.conda.io/) (or any Python 3.11+).

```bash
conda env create -f environment.yml
conda activate shipshape
pre-commit install

shipshape analyze path/to/your/project
shipshape map path/to/your/project --html map.html   # interactive architecture map
shipshape analyze path/to/your/project --explain     # plain-language explanations + fixes (needs a key, see below)
shipshape checks          # what it looks for
```

The [engine README](engine/README.md) lists every check and its limitations.

Run the checks the CI runs:

```bash
cd engine
ruff check . && ruff format --check .
mypy
pytest
```

## License

MIT, see [LICENSE](LICENSE).
