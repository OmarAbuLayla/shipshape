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
| GET | `/api/scans` | Past scans, newest first |
| GET | `/api/scans/{id}` | Status and progress of one scan |
| GET | `/api/scans/{id}/report` | The full report (findings, graph, explanations) |
| DELETE | `/api/scans/{id}` | Forget a scan |

Uploaded code is unpacked into a temporary folder and deleted when the scan finishes. Zips are checked before extraction: no absolute paths, no `..`, no links, and size and file-count limits.
