# Roadmap

Every phase ends with something that can be demonstrated on its own.

Status: Phases 0 to 5 are done; Phase 6 is next. Real run of Phase 3 with prompt version 2026-11-24.2 (deepseek-flash, fixture corpus, November 2026): 23 findings explained with 24 API calls (1 retry, 0 failures), about 970 input tokens (64% served from DeepSeek's prefix cache) and 870 output tokens per call, about $0.028 in total at peak prices, 135 s wall time (calls run one after another, about 5-6 s each). Every fix proposed for a Python file passed validation (11 of 11); notebook findings are explanation-only by design. The tightened prompt made explanations about 26% shorter and adds a "heads-up" when a fix changes visible behaviour.

Phase 4: local API (background scans, SQLite history, safe zip uploads, serves the app) and the React review app (start, progress, review with issue list, architecture map and explanation panel, history; light and dark). Explanation calls run in parallel (9 findings: 14 s instead of about 50 s).

After Phase 4: the brand kit, exports (JSON, Markdown, CSV, with or without AI), `.shipshapeignore` files and inline `# shipshape: ignore` comments (everything left out is listed in every report; the scoring formula is unchanged), and gentler handling of test files. Shipshape now reviews itself: the first self-scan found a bug in the complexity check (every method was counted twice), and its two most complex functions (`render_map_summary`, 25, and `build_graph`, 23) were split up on its advice. Self-scan: grade A, Structure 90, with the deliberately broken corpus fixtures excluded.

Open follow-ups: development-only npm advisories (Vite dev server, Vitest, ESLint internals) need major upgrades of the build tools; the runtime dependencies have none. Very large projects stay readable by fitting at no less than 60% zoom rather than showing everything at once.

Phase 5: verified fixes are applied together, one at a time, each verified again against the code the earlier fixes left (on the leaky EMG fixture the leakage fix and the seed fix touch the same lines: 5 of 6 fixes apply, the seed fix is skipped with the reason, grade B to A). The copy is scanned again; the result downloads as a `git apply` patch or a fixed zip, from the CLI (`shipshape fix`) and the web app. The scanned project is never changed. Later: GitHub pull requests, and a second round that regenerates skipped fixes against the fixed code.

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
