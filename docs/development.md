# Development

| Part | What it is |
|---|---|
| `engine/` | The checks, map, fix verification, agent, MCP server and CLI (Python 3.11, ruff, radon, AST checks) |
| `api/` | FastAPI server with background jobs and SQLite history; binds to 127.0.0.1 only |
| `web/` | React and TypeScript, React Flow with ELK for the map, Vite |
| `plugin/` | Claude Code plugin: skills, reviewer subagent, MCP config pinned to an engine release |

```bash
cd engine && ruff check . && mypy && pytest     # includes the corpus evaluation
cd api && ruff check . && mypy && pytest
cd web && npm run lint && npm run typecheck && npm test && npm run build
cd web && npm run dev                           # hot-reloading UI on :5173 (API on :8000)
```

CI runs all three on every push. Details: [engine](../engine/README.md) (every check and its limits), [API](../api/README.md) (endpoints), [web](../web/README.md) (screens), [corpus](corpus.md) (how the checks are measured).

## Releasing the plugin

The plugin pins the engine to the tag that matches its version. A release bumps `plugin/.claude-plugin/plugin.json` and the tag in `plugin/.mcp.json` together (a test checks they match), is pushed, and then that commit is tagged `v<version>`.
