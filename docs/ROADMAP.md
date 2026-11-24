# Roadmap

Every phase ends with something that can be demonstrated on its own.

Status: Phases 0 to 4 are done. Real run of Phase 3 with prompt version 2026-11-24.2 (deepseek-flash, fixture corpus, November 2026): 23 findings explained with 24 API calls (1 retry, 0 failures), about 970 input tokens (64% served from DeepSeek's prefix cache) and 870 output tokens per call, about $0.028 in total at peak prices, 135 s wall time (calls run one after another, about 5-6 s each). Every fix proposed for a Python file passed validation (11 of 11); notebook findings are explanation-only by design. The tightened prompt made explanations about 26% shorter and adds a "heads-up" when a fix changes visible behaviour.

Phase 4: local API (background scans, SQLite history, safe zip uploads, serves the app) and the React review app (start, progress, review with issue list, architecture map and explanation panel, history; light and dark). Explanation calls run in parallel (9 findings: 14 s instead of about 50 s).

Open follow-ups: development-only npm advisories (Vite dev server, Vitest, ESLint internals) need major upgrades of the build tools; the runtime dependencies have none. Very large projects stay readable by fitting at no less than 60% zoom rather than showing everything at once.

Known follow-up for Phase 5: fixes are generated per finding, so two fixes can touch the same line (for example the leakage split and the missing seed). Applying several fixes must happen one at a time, re-validating each against the already-changed code.

| Phase | Goal | Demo at the end |
|---|---|---|
| 0. Foundations | Repo layout, environment, CI, pre-commit, README | `shipshape analyze` runs and CI is green |
| 1. Analysis engine | Unified findings from ruff, radon and custom AST checks (mypy deferred: it needs the scanned project's dependencies) (hard-coded paths, missing seeds, subject leakage, oversized files, missing env/tests). A test corpus of repos with planted issues to measure precision and recall | The CLI finds real problems in one of my old projects |
| 2. Map builder | Import/data-flow graph with per-file metrics, missing pieces as ghost nodes, findings attached to nodes | Graph JSON for any scanned repo |
| 3. Explanation layer | LLM explains each finding (what, why, fix, concept). Every fix is validated: patch applies, code parses, ruff passes, finding disappears on re-scan | Validated, plain-language explanations in the report |
| 4. API + review screen | FastAPI upload/job/result endpoints; React review screen with issue list, map, panel and scorecard | Local web app, screen-recorded for the portfolio |
| 5. Applying fixes | Apply accepted fixes, re-scan, download the improved repo; GitHub PR later | Score goes up for real after fixes |
| 6. Blocks + lessons | Read-only function blocks anchored to line ranges; concept lessons; skill profile with accounts | Zoom from map to blocks to lines |
| 7. User testing | 5 to 10 students and researchers use it; measure understanding before and after | Evidence for whether the idea works |
| 8. Launch and decide | Public beta, demo video, write-up; decide between portfolio piece, side project or startup | A public link |

Later: two-way block editing for single functions, a course built from common mistakes, more languages, a sandbox for running user tests, a local/offline mode.

## Principles

- The engine never executes uploaded code until a proper sandbox exists.
- Deterministic tools detect problems. The LLM only explains and proposes fixes, and every claim points to a line.
- Advice is scaled to the project's size and purpose. Small scripts should not be pushed into frameworks.
