# Shipshape

**Code is cheap now. Judgment isn't.**

Shipshape takes a vibe-coded project and shows you, on a map of your own code, what a senior engineer would object to and why. Then it helps you fix it. You end up with code a team would accept, and you learn the judgment behind it.

It is built first for people whose code gets judged by someone else, like researchers, students and domain experts, and it knows research-specific pitfalls such as data leakage across subjects, missing random seeds and unpinned environments.

> **Status:** Phase 4 of 8 done. A local web app scans a Python project (folder or zip), runs 29 checks, draws an interactive architecture map with every problem pinned to it, and (optionally, with an LLM key) explains each finding in plain language with fixes that are verified before they are shown. Applying fixes is next. See the [roadmap](docs/ROADMAP.md).

## How it works

1. **Analyze.** Deterministic tools (ruff, radon and custom AST checks) find concrete problems. Nothing in the project is executed.
2. **Map.** The project is drawn as an architecture map, with each problem pinned where it happens.
3. **Explain.** An LLM explains each finding in plain language, grounded in the tool output and the exact lines. Credentials are redacted before anything is sent.
4. **Verify.** Proposed fixes are applied in memory and must parse, remove the finding and add no new findings before they are shown.

## Repository layout

```
engine/   Python analysis engine and CLI (checks, map, explanations)
api/      Local FastAPI server: background scans, history, serves the web app
web/      React + TypeScript review app
docs/     Roadmap and evaluation notes
```

## Getting started

Requires [conda](https://docs.conda.io/) (or Python 3.11+) and Node.js 22.

```bash
conda env create -f environment.yml
conda activate shipshape
cd web && npm ci && npm run build && cd ..   # build the web app once

shipshape-api                                # open http://127.0.0.1:8000
```

For AI explanations, copy `.env.example` to `.env`, add a DeepSeek API key and check it with `shipshape llm-check --ping`. Run `shipshape-api` from the repository root so it finds `.env`.

The command line works without the web app:

```bash
shipshape analyze path/to/your/project              # findings and scorecard
shipshape analyze path/to/your/project --explain    # plus explanations and verified fixes
shipshape map path/to/your/project --html map.html  # quick standalone map
shipshape checks                                    # what it looks for
```

The [engine README](engine/README.md) lists every check and its limitations, the [API README](api/README.md) the endpoints, and the [web README](web/README.md) the screens.

## Development

```bash
cd engine && ruff check . && mypy && pytest          # engine
cd api && ruff check . && mypy && pytest             # API
cd web && npm run lint && npm run typecheck && npm test && npm run build
cd web && npm run dev                                # hot-reloading UI on :5173 (API on :8000)
```

CI runs all three on every push.

## License

MIT, see [LICENSE](LICENSE).
