# web

The Shipshape review app: React 18 + TypeScript + Vite, with React Flow and ELK for the architecture map.

```bash
npm ci
npm run dev        # http://localhost:5173, proxies /api to shipshape-api on :8000
npm run build      # writes dist/, which shipshape-api serves at http://127.0.0.1:8000
npm test           # view-model, layout, highlighter and formatting tests (Vitest)
npm run lint && npm run typecheck
```

## Screens

- **New scan**: scan a folder on this computer or upload a `.zip`, optionally with AI explanations (the switch says which provider receives code and roughly what it costs).
- **Progress**: live steps ("Explaining findings: 4 of 12 done"), then the review opens on its own.
- **Review**: grade and per-dimension scores on top; issues grouped into *Fix first / Worth fixing / Polish* on the left; the architecture map in the middle; the explanation, highlighted fix diff, heads-up and verification note on the right. Selecting an issue highlights and pans to its boxes; clicking a box filters the issues. Large projects open as one box per folder; open a folder in place with *open ▸* or a double-click.
- **History**: past scans with grade, findings and date.

## Code layout

```
src/lib/        types (mirror the report schema), API client, graph view model, ELK layout,
                Python highlighter, formatting helpers - all unit-tested, no React
src/review/     review screen: IssueList, MapView, DetailPanel, Diff
src/pages/      Home, ScanPage (progress + lazy-loaded review), History
src/styles.css  the design system: tokens for light and dark, components
```

The review screen (map and layout engine, about 500 KB gzipped) is loaded only when a report is opened, so the start page stays small.
