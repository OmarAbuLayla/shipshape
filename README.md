# Shipshape

![Shipshape](web/public/brand/social-preview.png)

**Code is cheap now. Judgment isn't.**

Shipshape reviews vibe-coded Python projects the way a careful senior engineer would. It finds what an engineer would object to, shows it on a map of your code, explains it in plain language, and fixes it, but only with fixes it has verified. It is built for people whose code gets judged by someone else (researchers, students, domain experts) and knows research pitfalls like data leakage across subjects, missing seeds and hard-coded data paths. It never runs your code.

## What it does

- **Finds problems.** 37 static checks in six dimensions (correctness, structure, reproducibility, readability, testing, security), with a grade. Research and deep-learning bugs included: leakage across subjects, the test set used to pick the best epoch, no `zero_grad`, no `eval()`, data skipped silently, copied files, imports that only work on the author's machine. Every check is measured on a corpus of projects with planted problems.
- **Shows them on a map** of folders, files and imports, then down to functions and the exact lines.
- **Explains and teaches.** With an LLM key, each finding is explained in terms of your code, and every concept has a short hand-written lesson (26 in all).
- **Fixes, verified.** A fix is only offered if, applied in memory, the code still parses, the problem is gone and nothing new appears. Fixes go to a copy, with a patch or zip to download; your files are never changed.
- **Or lets an agent do it.** An LLM works through the findings with tools, and Shipshape verifies every fix before accepting it ([more below](#the-agent)).

## Quick start

Requires [conda](https://docs.conda.io/) (or Python 3.11+) and Node.js 22.

```bash
conda env create -f environment.yml
conda activate shipshape
cd web && npm ci && npm run build && cd ..
shipshape-api                    # open http://127.0.0.1:8000
```

Paste a project folder (or upload a zip) and press *Start scan*. For AI explanations and the agent, copy `.env.example` to `.env` and add a key (see [AI providers](#ai-providers)).

## Four ways to use it

| | Web app | Command line | Claude Code plugin | Other MCP clients |
|---|---|---|---|---|
| **Best for** | The map, the agent live, before/after | Scripts, CI, quick checks | Code you already work on in Claude Code | Claude Desktop and others |
| **Needs** | conda, Node.js | conda | Claude Code and [uv](https://docs.astral.sh/uv/) | uv |
| **AI** | Your key, optional | Your key, optional | Claude (your plan) | That client's model |
| **Your files** | Never changed | Never changed | Edited after `verify_fix` passed | As the client decides |

**Web app:** see [Quick start](#quick-start). In a review, tick verified fixes and press *Apply*, or press **Agent**.

**Command line** (same conda environment):

```bash
shipshape analyze path/to/project --export report.md   # findings, grade, export
shipshape fix path/to/project --patch fixes.patch      # verified fixes, as a patch
shipshape agent path/to/project --patch agent.patch    # let the agent fix
shipshape lessons data-leakage                         # the lesson behind a check
```

**Claude Code plugin:** run `/plugin install shipshape --marketplace OmarAbuLayla/shipshape` inside Claude Code, then ask for a review or use `/shipshape:review`, `/shipshape:fix` and `/shipshape:lesson`. A bundled reviewer subagent does a full review in its own context. The first start builds the engine and can take a minute; see the [plugin README](plugin/README.md).

**Other MCP clients:** add this to the client's MCP configuration (for Claude Desktop, `claude_desktop_config.json`) to get the `scan`, `verify_fix`, `lesson` and `map` tools. So far tested in Claude Code only.

```json
{"mcpServers": {"shipshape": {"command": "uvx", "args": ["--from", "git+https://github.com/OmarAbuLayla/shipshape@v0.8.1#subdirectory=engine", "shipshape-mcp"]}}}
```

## The agent

The model decides what to read and what to change; **Shipshape decides what is accepted**. Every proposed fix passes the same checks as a verified fix before it is applied to a copy, and a rejected fix comes back with the reason. Limits keep it predictable: 30 turns, about $0.10, three rejections per finding, three files per fix, and no changes to what the program does. Every step is shown live in the web app and ends with the model's own summary.

On the small `heart_risk` test project a run takes one to two minutes and about $0.03 (grade D to B). On an 8,000-line research project it fixed 7 problems across 18 files for about $0.06 and left the design decisions to the author.

## AI providers

Copy `.env.example` to `.env`, pick a provider and check it with `shipshape llm-check --ping`:

| Provider | `SHIPSHAPE_LLM_PROVIDER` | Settings |
|---|---|---|
| DeepSeek (default, cheapest) | `deepseek` | `DEEPSEEK_API_KEY` |
| OpenAI | `openai` | `OPENAI_API_KEY`, `SHIPSHAPE_LLM_MODEL` |
| OpenRouter, Mistral, Groq, Ollama, ... | `openai-compatible` | `SHIPSHAPE_LLM_BASE_URL`, `SHIPSHAPE_LLM_API_KEY`, `SHIPSHAPE_LLM_MODEL` |

The prompts were tuned with DeepSeek; other models may get fewer fixes through verification.

## Privacy

Everything runs on your machine; without an LLM key nothing leaves it. With a key, only the finding and the code around it are sent, with credentials removed, and `.env` files are never sent. Where the code goes depends on your provider (DeepSeek's servers are in China; a local Ollama keeps everything local). In the Claude Code plugin, Claude reads your code under your own Claude plan.

## Limits, honestly

The checks are static heuristics: they recognise common patterns, not every way a bug can be written, and the leakage check is phrased as a question because Shipshape cannot know how your data was collected. A verified fix is valid and removes the problem without new detectable ones, but Shipshape never runs code, so run your tests after applying. Python and notebooks only.

## Shipshape reviewed itself

Its first self-scan found a bug in Shipshape (every class method counted twice) and pointed at its two most tangled functions, which were then split up. Testing it on real research code found five more bugs in Shipshape, now fixed. It grades itself **A**.

## Development

| Part | What it is |
|---|---|
| `engine/` | The checks, map, fix verification, agent and CLI (Python, ruff, radon, AST checks) |
| `api/` | FastAPI server with background jobs and SQLite history; binds to 127.0.0.1 only |
| `web/` | React and TypeScript, React Flow with ELK for the map |
| `plugin/` | Claude Code plugin: skills, reviewer subagent, MCP config |

```bash
cd engine && ruff check . && mypy && pytest     # includes the corpus evaluation
cd api && ruff check . && mypy && pytest
cd web && npm run lint && npm run typecheck && npm test
```

CI runs all three on every push. Details: [engine](engine/README.md) (every check and its limits), [API](api/README.md), [web](web/README.md), [corpus](docs/corpus.md).

## License

MIT, see [LICENSE](LICENSE).
