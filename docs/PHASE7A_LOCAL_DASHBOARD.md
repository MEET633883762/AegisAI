# Phase 7A — Local Security Dashboard

**Scope:** Local product demonstration using the existing synthetic-only API. This is not a production SOC, hosted service, or real-world detection claim.

## Experience and data sources

`frontend/local-dashboard.html` is a separate local operations page with Overview, Findings, Detection Lab, and System Health views. It uses the existing React, TypeScript, and Vite stack. The design is keyboard-operable, responsive, uses semantic headings, labeled controls, visible focus styles, and polite status/error announcements. Automated UI tests cover the main navigation, connecting, filters, finding details, evidence, empty and error states, and synthetic-data disclosure; manual browser and assistive-technology review remains appropriate.

| View | Data source | Notes |
|---|---|---|
| Overview | Authenticated `GET /api/telemetry/findings`, `GET /api/processing`, and `GET /api/telemetry/sources/live-website/status` | Counts are calculated from returned findings or the latest returned run/source counters. The processing model has accepted and duplicate counts; rejected-record counts exist only for the live source status. Missing source status is displayed as unavailable, never healthy. |
| Findings | Authenticated telemetry findings endpoint and selected finding's `GET /api/telemetry/findings/{id}/evidence` | Search plus severity, rule type, and status filters use actual returned fields. Evidence is retrieved from the server-scoped endpoint. No write or response controls exist. |
| Detection Lab | No data endpoint | Truthfully unavailable. The API does not expose the Phase 6B evaluation report. The private dataset/report is not copied into frontend assets, and no new API route was added. The page describes the benchmark semantics and local CLI command only. |
| System Health | Authenticated `GET /health`, `/api/processing`, and source status | Shows local API status, scheduler state, latest run, and available source counters. API/source failure or missing status is not presented as healthy. |

The API does not expose arbitrary tenant selection. Every route continues to derive tenant scope from the bearer principal. The page uses only fixed loopback routes and does not accept a base URL, path, file, or telemetry input.

## Authentication and browser boundary

Start the private API in a terminal with `python scripts/run_private_api.py`. It binds to `127.0.0.1:8766`, prints an ephemeral development bearer token, and serves synthetic data only. Start the Vite frontend with `npm run dev` in `frontend/`; open `http://localhost:5174/local-dashboard.html` (or `http://127.0.0.1:5174/local-dashboard.html`) on the same computer. Paste the current startup token into the local dashboard. The token is kept in component memory only, cleared on disconnect/page close, and is never written to URL, storage, source, or logs. Each request has a five-second timeout, `no-store`, no browser credentials, and a 2 MiB response-body limit.

The API grants browser CORS only to those two exact loopback development origins. Preflight permits only `GET`, `OPTIONS`, and the `Authorization` header; it does not permit cookies or credentials. Requests still require the same authenticated scope and tenant authorization as before. The API bind address, API routes, tokens, authorization behavior, store, and schema were not widened. The Vite development server binds all interfaces for the existing phone-preview workflow, but the local dashboard API connection is designed for the same computer; a LAN origin is not CORS-allowed.

Vite serves `local-dashboard.html` during local development. The standard production Vite build intentionally contains only the existing public pages, and `scripts/build_static_site.py`'s exact nine-file public allowlist is unchanged. The publisher copies none of `local-dashboard.html`, its bundle/styles, the API, database, telemetry files, or evaluation materials. The public landing page and research dashboard entry points were not changed by this phase.

## Limitations

- The Phase 6B confusion matrix, metrics, dataset version, and fingerprint remain unavailable in this dashboard because no approved API read path exists. The dashboard does not fabricate a substitute.
- The bearer token is a local development credential, not a durable identity system. Use only on the local computer and do not paste it into a remotely hosted page or share it.
- Browser CORS is an origin boundary, not authentication; the existing bearer and server-derived tenant scope remain the authorization boundary.
- Data remains synthetic. The live log source is the harmless local demo site from Phase 5B, not client telemetry.
- Automated UI tests are not a full accessibility audit. Screen-reader, browser, zoom, and phone review are manual follow-up.
- This work does not establish production readiness, operational monitoring, or detection effectiveness.

## Verification commands

From `frontend/`: `npm.cmd test` runs TypeScript checking, the production build, Vitest, and static-release tests. From the repository root: `python -m pytest -q -p no:cacheprovider`, `python -m compileall -q private_api platform_prototype scripts tests`, `python scripts/build_static_site.py --output <new-empty-directory>`, and `git diff --check`.
