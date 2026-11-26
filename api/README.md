# shipshape-api

Local web API behind the Shipshape web app. It starts scans in the background, reports progress and serves finished reports. It listens on 127.0.0.1 only: it is a tool for your own machine, not a public server.

```bash
shipshape-api                 # http://127.0.0.1:8000, interactive docs at /docs
```

Run it from the repository root so it finds the `.env` file with your LLM settings.

| Method | Path | What it does |
|---|---|---|
| GET | `/api/health` | Engine version and whether an LLM is configured (never the key) |
| POST | `/api/scans` | Scan a folder on this machine: `{"path": "...", "explain": false}` |
| POST | `/api/scans/upload` | Scan an uploaded `.zip` (form fields `file`, `explain`) |
| GET | `/api/profile` | Concepts across all your scanned projects: where they appear now and where they were resolved |
| GET | `/api/lessons` | Every concept lesson (slug, concept, summary, checks) |
| GET | `/api/lessons/{name}` | One lesson with its Markdown body, by slug, concept or check id |
| GET | `/api/scans` | Past scans, newest first |
| GET | `/api/scans/{id}` | Status and progress of one scan |
| GET | `/api/scans/{id}/report` | The full report (findings, graph, explanations) |
| GET | `/api/scans/{id}/export?format=md` | Download the findings as Markdown (`md`), `json` or `csv` |
| GET | `/api/scans/{id}/source?path=train.py` | The scanned code of one file of the scan (only files that were scanned), and whether it changed since |
| POST | `/api/scans/{id}/fixes` | Apply verified fixes to a copy and scan it again: `{"findings": [0, 3]}`; fixes that collide get a second round unless `"second_round": false` |
| GET | `/api/scans/{id}/fixes` | The last fix run: scores before and after, applied and skipped fixes, the patch |
| GET | `/api/scans/{id}/fixes/download?format=patch` | The fixes as a patch for `git apply`, or `zip` for the fixed project |
| POST | `/api/scans/{id}/agent` | Start the agent on a copy of the scanned project, in the background: `{"max_steps": 30, "max_cost_usd": 0.1}` (needs an LLM key; one run at a time) |
| GET | `/api/scans/{id}/agent` | The running or last agent run: status, every step so far, then the result (grades, summary, patch) |
| GET | `/api/scans/{id}/agent/download?format=patch` | The agent's fixes as a patch, or `zip` for the fixed project |
| DELETE | `/api/scans/{id}` | Forget a scan (and every file kept for it) |

Applying fixes never changes the scanned folder or upload. Folder scans are fixed from the folder as it is now, so fixes for code you changed since the scan are skipped with a reason. Uploads are fixed from the original zip, which is kept in the data folder (`~/.shipshape/api/uploads`) until you delete the scan.

The profile is built only from the local scan history: no accounts, nothing leaves the machine. Each project counts with its latest scan. A concept counts as resolved in a project only if it appeared in an earlier scan, is gone from the latest one, and the files it was found in are still scanned and not silenced by `.shipshapeignore` or `# shipshape: ignore`. It cannot tell a real fix from a check that changed between engine versions.

Uploaded code is unpacked into a temporary folder and deleted when the scan finishes. Zips are checked before extraction: no absolute paths, no `..`, no links, and size and file-count limits.
