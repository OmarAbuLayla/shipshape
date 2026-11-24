# Shipshape for Claude Code

Shipshape as a Claude Code plugin: Claude is the LLM, so no API key is needed. Shipshape's
engine runs locally as an MCP server and provides what an LLM cannot do reliably on its own:
deterministic findings and a grade, 25 lessons, and a fix check that every edit must pass
before Claude applies it.

## Install

Requires [uv](https://docs.astral.sh/uv/) (the engine is fetched and run with `uvx`).

```
/plugin install shipshape --marketplace OmarAbuLayla/shipshape
```

### If the server times out on first start

The first start downloads and builds the engine with `uvx`, which can take longer than Claude
Code's default 30 seconds for an MCP server. Claude Code then skips the server for 15 minutes.
Two ways around it:

- Build it once in a terminal: run
  `uvx --from "git+https://github.com/OmarAbuLayla/shipshape#subdirectory=engine" shipshape-mcp`,
  wait until it sits silently (the server is running), stop it with Ctrl+C, then restart Claude
  Code. Later starts take about 10 seconds.
- Or give MCP servers more time: add `"env": { "MCP_TIMEOUT": "120000" }` to
  `~/.claude/settings.json` (two minutes).

The plugin follows the repository's `main` branch, so the first start after an update builds
the engine again.

## Use

| Skill | What it does |
|---|---|
| `/shipshape:review [folder]` | Scan, then explain the most important findings in your own code |
| `/shipshape:fix [which]` | Fix findings with edits Shipshape verified first; scan again for the new grade |
| `/shipshape:lesson [name]` | The concept behind a finding, with a before and after |

Claude can also use the skills on its own when you ask it to review or fix a Python project.

## Tools

The MCP server (`shipshape-mcp`) offers `scan`, `verify_fix`, `lesson` and `map`. It never
writes to your project: `verify_fix` checks edits in memory, and Claude applies them with its
own Edit tool, which asks for your permission as usual. `map` writes an HTML page to the
temporary folder.

## Compared with the standalone app

The plugin has no interactive map, before/after page, history or profile, and fixes change
your real files (the skill asks you to commit first), whereas the app always works on a copy.
Your code is read by Claude under your own Claude plan; nothing goes to DeepSeek.
