# Phase 7A — Local Security Dashboard

**Scope:** Local product demonstration using the existing synthetic-only API. This is not a production SOC, hosted service, or real-world detection claim.

## Experience and data sources

`frontend/local-dashboard.html` is a separate local operations page with Overview, Findings, Detection Lab, and System Health views. It uses the existing React, TypeScript, and Vite stack. The design is keyboard-operable, responsive, uses semantic headings, labeled controls, visible focus styles, and polite status/error announcements. Automated UI tests cover the main navigation, connecting, filters, finding details, evidence, empty and error states, and synthetic-data disclosure; manual browser and assistive-technology review remains appropriate.

| View | Data source | Notes |
|---|---|---|
| Overview | Authenticated `GET /api/telemetry/findings`, `GET /api/processing`, and `GET /api/telemetry/sources/live-website/status` | Counts are calculated from returned findings or the latest returned run/source counters. The processing model has accepted and duplicate counts; rejected-record counts exist only for the live source status. Missing source status is displayed as unavailable, never healthy. |
| Findings | Authenticated telemetry findings endpoint and selected finding's `GET /api/telemetry/findings/{id}/evidence` | Search plus severity, rule type, and status filters use actual returned fields. Evidence is retrieved from the server-scoped endpoint. No write or response controls exist. |
| Detection Lab | Authenticated `GET /api/evaluation/reports/latest` (`reports:read`) | The API reads the fixed Phase 6B report or the latest opt-in bounded history report and returns aggregate/per-rule metrics, scenario-rule coverage, provenance, history comparisons, and limitations. It does not run evaluation or return raw event inputs. If neither source is available or valid, it returns a generic unavailable response. |
| System Health | Authenticated `GET /health`, `/api/processing`, and source status | Shows local API status, scheduler state, latest run, and available source counters. API/source failure or missing status is not presented as healthy. |

The API does not expose arbitrary tenant selection. Every route continues to derive tenant scope from the bearer principal. The page uses only fixed loopback routes and does not accept a base URL, path, file, or telemetry input.

## Authentication and browser boundary

Start the private API in a terminal with `python scripts/run_private_api.py`. It binds to `127.0.0.1:8766`, prints an ephemeral development bearer token, and serves synthetic data only. In a second PowerShell terminal, run:

```powershell
cd C:\AegisAI\frontend
npm.cmd run dev:dashboard
```

This starts Vite on port `5174`, prints direct dashboard URLs, and asks Vite to open `/local-dashboard.html` in the default browser. The direct same-computer URL is `http://localhost:5174/local-dashboard.html`. The regular `npm.cmd run dev` command remains available and serves the public landing page at `/`; it also prints the dashboard URL. The local dashboard remains a separate development entry point, not a replacement for the landing page. Paste the current startup token into the local dashboard. The token is kept in component memory only, cleared on disconnect/page close, and is never written to URL, storage, source, or logs. Each request has a five-second timeout, `no-store`, no browser credentials, and a 2 MiB response-body limit.

The API grants browser CORS only to those two exact loopback development origins. Preflight permits only `GET`, `OPTIONS`, and the `Authorization` header; it does not permit cookies or credentials. Requests still require the same authenticated scope and tenant authorization as before. The API bind address, route set, token behavior, authorization, store, and database schema were not widened. The authenticated `/health` route is a liveness check; `/ready` uses the same `health:read` scope and reports only whether the local store can answer a simple readiness query. HTTP request bodies are capped at 16 KiB, accepted connections have a five-second socket inactivity timeout, and active request handlers are capped at 32. The existing authenticated source-status response now represents an unrecorded source explicitly as `status: unavailable` with null counters; it does not create a database record or claim a healthy source. The Vite development server binds all interfaces for the existing phone-preview workflow, but the local dashboard API connection is designed for the same computer; a LAN origin is not CORS-allowed.

Vite serves `local-dashboard.html` during local development. The standard production Vite build intentionally contains only the existing public pages, and `scripts/build_static_site.py`'s exact nine-file public allowlist is unchanged. The publisher copies none of `local-dashboard.html`, its bundle/styles, the API, database, telemetry files, or evaluation materials. The public landing page and research dashboard entry points were not changed by this phase.

### Troubleshooting

- **Wrong page at `/`:** `/` is intentionally the public landing page. Use `http://localhost:5174/local-dashboard.html` or `npm.cmd run dev:dashboard`.
- **404 at the dashboard URL:** confirm the Vite terminal says it is ready on port `5174` and that Vite was started from `frontend/`.
- **Port conflict:** Vite uses `--strictPort`, so it exits instead of silently selecting a different port. Stop the process using `5174`, then rerun the command.
- **Dashboard loads but says it is disconnected:** start the private API in a second terminal and paste its current startup token. The API is loopback-only; a phone or other LAN device cannot use the API connection, and LAN browser origins are not CORS-allowed.
- **Dashboard missing from a published build:** expected. The local dashboard is intentionally excluded from both the production Vite build and the nine-file static publisher allowlist.

## Limitations

- The Phase 6B summary is read from the fixed CLI output when the private API starts; the API does not run evaluation or create the report. If the report is absent, use the existing CLI to generate it before starting the API. It remains synthetic benchmark evidence only; rejected scenario diagnostics and dataset content are not exposed.
- The bearer token is a local development credential, not a durable identity system. Use only on the local computer and do not paste it into a remotely hosted page or share it.
- Each API start creates a fresh random development token in memory and prints it once to that terminal. To rotate it, stop and restart the API; this invalidates every token from the previous process. Protect terminal output and clear any copied token when finished. `AEGISAI_ENV` may be omitted or set to `local`/`development`; any other value causes startup to stop before reading fixtures or opening the database. This project has no supported production authentication or deployment mode. Do not deploy this API or reuse its development tokens; a future deployment needs a reviewed identity provider or secret manager, scoped short-lived credentials, and separate network controls.
- Browser CORS is an origin boundary, not authentication; the existing bearer and server-derived tenant scope remain the authorization boundary.
- Data remains synthetic. The live log source is the harmless local demo site from Phase 5B, not client telemetry.
- Automated UI tests are not a full accessibility audit. Screen-reader, browser, zoom, and phone review are manual follow-up.
- This work does not establish production readiness, operational monitoring, or detection effectiveness.

## Verification commands

From `frontend/`: `npm.cmd test` runs TypeScript checking, the production build, Vitest, and static-release tests. From the repository root: `python -m pytest -q -p no:cacheprovider`, `python -m compileall -q private_api platform_prototype scripts tests`, `python scripts/build_static_site.py --output <new-empty-directory>`, and `git diff --check`.
