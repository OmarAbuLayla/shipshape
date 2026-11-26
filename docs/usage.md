# Using Shipshape

Four ways in, all built on the same engine:

| | Web app | Command line | Claude Code plugin | Other MCP clients |
|---|---|---|---|---|
| **Best for** | The map, the agent live, before/after | Scripts, CI, quick checks | Code you already work on in Claude Code | Claude Desktop and others |
| **Needs** | conda, Node.js 22 | conda | Claude Code and [uv](https://docs.astral.sh/uv/) | uv |
| **AI** | Your key, optional | Your key, optional | Claude (your plan) | That client's model |
| **Your files** | Never changed | Never changed | Edited after `verify_fix` passed | As the client decides |

## Web app

```bash
conda env create -f environment.yml
conda activate shipshape
cd web && npm ci && npm run build && cd ..
shipshape-api          # from the repository root; open http://127.0.0.1:8000
```

Paste a project folder (or upload a zip) and press *Start scan*. The review shows the grade, the findings and a map of the project; click a file to zoom into its functions and code. Tick verified fixes and press *Apply* for a before/after page with a patch or zip, or press **Agent** to let the agent work through the project while you watch. On Windows, each new terminal starts in conda's `base`, so run `conda activate shipshape` first.

## Command line

Same conda environment, no Node.js needed:

```bash
shipshape analyze path/to/project                    # findings and grade
shipshape analyze path/to/project --explain          # plus AI explanations and verified fixes
shipshape analyze path/to/project --export report.md # Markdown, JSON or CSV
shipshape fix path/to/project --patch fixes.patch    # apply verified fixes to a copy
shipshape agent path/to/project --patch agent.patch --log agent.md
shipshape map path/to/project --html map.html        # standalone map
shipshape lessons data-leakage                       # the lesson behind a check
```

## Claude Code plugin

Inside Claude Code:

```
/plugin install shipshape --marketplace OmarAbuLayla/shipshape
```

Claude explains the findings and writes the fixes; Shipshape's engine runs locally as an MCP server and supplies the findings, the grade, the lessons, and the `verify_fix` check every fix must pass. Ask for a review in your own words, or use `/shipshape:review`, `/shipshape:fix` and `/shipshape:lesson`. A bundled reviewer subagent does a whole review in its own context and returns a short report.

The first start after installing or updating builds the engine and can take a minute; see the [plugin README](../plugin/README.md) if Claude Code gives up on it. The plugin pins the engine to a release tag, so it only changes when you update the plugin.

## Other MCP clients

Any client that can start a local stdio MCP server gets the `scan`, `verify_fix`, `lesson` and `map` tools. For Claude Desktop, add this to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "shipshape": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/OmarAbuLayla/shipshape@v0.8.1#subdirectory=engine", "shipshape-mcp"]
    }
  }
}
```

With the conda environment installed, `"command": "shipshape-mcp"` works too. Other clients get the tools, not the Claude Code skills; so far Shipshape has been tested in Claude Code only.

## AI providers

For explanations, fixes and the agent in the web app and the command line, copy `.env.example` to `.env`, pick a provider and check it with `shipshape llm-check --ping`:

| Provider | `SHIPSHAPE_LLM_PROVIDER` | Settings |
|---|---|---|
| DeepSeek (default, cheapest) | `deepseek` | `DEEPSEEK_API_KEY` |
| OpenAI | `openai` | `OPENAI_API_KEY`, `SHIPSHAPE_LLM_MODEL` |
| OpenRouter, Mistral, Groq, Ollama, ... | `openai-compatible` | `SHIPSHAPE_LLM_BASE_URL`, `SHIPSHAPE_LLM_API_KEY`, `SHIPSHAPE_LLM_MODEL` |

Run `shipshape-api` from the repository root so it finds `.env`. Cost estimates are shown for DeepSeek's models; the prompts were tuned with DeepSeek, so other models may get fewer fixes through verification.

## The agent

Start it from a review (**Agent**) or with `shipshape agent`. It works on a copy and stops on its own: after 30 model turns, at about $0.10, or when it is done. Every step is shown, and the run ends with a summary of what changed, what was left for you, and every change in behaviour, plus a patch and a fixed zip. A typical run on a small project takes one to two minutes and about $0.03. How it works: [How it works](how-it-works.md#the-agent).

## Leaving things out

List generated or example code in a `.shipshapeignore` file (gitignore syntax), or mark a line with `# shipshape: ignore[check-id]`. Every report says what was left out, so scores stay traceable.
