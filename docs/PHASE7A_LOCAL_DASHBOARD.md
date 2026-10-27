# Phase 7A — Local Security Dashboard

> Current setup: use Python 3.11 from the [development guide](DEVELOPMENT.md). PowerShell examples run from the repository root with `.\.venv\Scripts\python.exe`; on Linux use `.venv/bin/python`. Phase-specific verification counts are historical; see [current status](CURRENT_STATUS.md) for fresh checks.

**Scope:** Local product demonstration using the existing synthetic-only API. This is not a production SOC, hosted service, or real-world detection claim.

## Experience and data sources

`frontend/local-dashboard.html` is a separate local operations page with eight views: Overview, Findings, Detection Lab, Scenario Validation, Assessment, Executive Reports, Cases, and System Health. Its indigo/navy interface is separate from the public landing page and recorded walkthrough. It uses the existing React, TypeScript, and Vite stack. The design is keyboard-operable, responsive, uses semantic headings, labeled controls, visible focus styles, and polite status/error announcements. Automated UI tests cover the main navigation, connecting, filters, finding details, evidence, empty and error states, and synthetic-data disclosure; manual browser and assistive-technology review remains appropriate.

| View | Data source | Notes |
|---|---|---|
| Overview | Authenticated `GET /api/telemetry/findings`, `GET /api/processing`, and `GET /api/telemetry/sources/live-website/status` | Counts are calculated from returned findings or the latest returned run/source counters. The processing model has accepted and duplicate counts; rejected-record counts exist only for the live source status. Missing source status is displayed as unavailable, never healthy. |
| Findings | Authenticated telemetry findings endpoint and selected finding's `GET /api/telemetry/findings/{id}/evidence` | Search plus severity, rule type, and status filters use actual returned fields. Evidence is retrieved from the server-scoped endpoint. No write or response controls exist. |
| Detection Lab | Authenticated `GET /api/evaluation/reports/latest` (`reports:read`) | The API reads the fixed Phase 6B report or the latest opt-in bounded history report and returns aggregate/per-rule metrics, scenario-rule coverage, provenance, history comparisons, and limitations. It does not run evaluation or return raw event inputs. If neither source is available or valid, it returns a generic unavailable response. |
| Scenario Validation | Authenticated `GET /api/purple-team/scenarios/runs` (`reports:read`) | Shows persisted authorized synthetic run outcomes and comparisons. No browser control launches a scenario. |
| Assessment | Authenticated `GET /api/assessment/reports/latest` (`reports:read`) | Shows the latest fixed-site assessment, observations, inferred risks, evidence, and retained run comparison. Checks run separately from the CLI. |
| Executive Reports | Authenticated `GET /api/reports/executive/latest` (`reports:read`) | Summarizes linked synthetic findings/evidence and offers a browser-local report download. |
| Cases | Authenticated investigation list/detail routes (`investigations:read`) | Reads cases and verified stored references. Creation, notes, associations, and status updates require the separately enabled `investigations:write` scope; they do not execute response actions. |
| System Health | Authenticated `GET /health`, `/api/processing`, and source status | Shows local API status, scheduler state, latest run, and available source counters. API/source failure or missing status is not presented as healthy. |

The API does not expose arbitrary tenant selection. Every route continues to derive tenant scope from the bearer principal. The page uses only fixed loopback routes and does not accept a base URL, path, file, or telemetry input.

### Navigation and evidence workflow

Each section has a validated URL fragment, for example `local-dashboard.html#findings` or `#detection`. Reload and browser Back/Forward restore that section; fragments contain only the view ID, never a token or finding payload. Navigation moves keyboard focus to the view heading. Selecting a recent finding on Overview opens Findings and its server-scoped evidence, clearing filters that would hide it.

The queue shows a live matching count and **Clear filters** action. A genuinely empty returned dataset is distinguished from a filter with no matches and from disconnected/unavailable data. Filtering does not discard the selected evidence; a note identifies a selection outside the active filter. Failed refreshes preserve earlier values with a stale-data warning rather than manufacturing a successful or empty result.

## Authentication and browser boundary

Use the reviewed Python 3.11 environment from [the development setup](DEVELOPMENT.md). From the repository root, start the private API in one PowerShell terminal:

```powershell
.\.venv\Scripts\python.exe scripts/run_private_api.py
```

If its dependencies are already installed in Python 3.11 directly, use `py -3.11 scripts/run_private_api.py`. On Linux, use `.venv/bin/python scripts/run_private_api.py` after the Linux setup. An unqualified `python` may select an older installation; `.python-version` does not switch Windows `PATH`.

The API binds to `127.0.0.1:8766`, prints an ephemeral development bearer token, and serves synthetic data only. In a second PowerShell terminal at the repository root, run:

```powershell
npm.cmd --prefix frontend run dev:dashboard -- --host 127.0.0.1
```

This starts Vite on port `5174`, prints direct dashboard URLs, and asks Vite to open `/local-dashboard.html` in the default browser. The direct same-computer URL is `http://localhost:5174/local-dashboard.html`. The regular `npm.cmd --prefix frontend run dev -- --host 127.0.0.1` command remains available and serves the public landing page at `/`; it also prints the dashboard URL. The local dashboard remains a separate development entry point, not a replacement for the landing page. Paste the current startup token into the local dashboard. The token is kept in component memory only, cleared on disconnect/page close, and is never written to URL, storage, source, or logs. Each request has a five-second timeout, `no-store`, no browser credentials, and a 2 MiB response-body limit.

The API grants browser CORS only to `http://localhost:5174` and `http://127.0.0.1:5174`. Preflight permits `GET` and `POST`, with `Authorization` and `Content-Type`; the server answers preflight through `OPTIONS` and does not allow browser cookies/credentials. `POST` is limited to the controlled investigation routes and still requires `investigations:write`. CORS permission does not replace the route, scope, or server-derived tenant checks. The listener remains loopback-only. The authenticated `/health` route is a liveness check; `/ready` uses the same `health:read` scope and reports only whether the local store can answer a simple readiness query. HTTP request bodies are capped at 16 KiB, accepted connections have a five-second socket inactivity timeout, and active request handlers are capped at 32. The existing authenticated source-status response now represents an unrecorded source explicitly as `status: unavailable` with null counters; it does not create a database record or claim a healthy source. The explicit `--host 127.0.0.1` above restricts Vite to this computer. The package's default Vite command can bind all interfaces for phone previews, but the local dashboard API connection is designed for the same computer; a LAN origin is not CORS-allowed.

Vite serves `local-dashboard.html` during local development. The standard production Vite build intentionally contains only the existing public pages, and `scripts/build_static_site.py`'s exact nine-file public allowlist is unchanged. The publisher copies none of `local-dashboard.html`, its bundle/styles, the API, database, telemetry files, or evaluation materials. The public landing page and research walkthrough have their own presentation controls, searchable evidence, and fixed published samples; see [the frontend guide](../frontend/README.md). They do not call the private API.

### Optional analyst case writes

Default startup tokens are read-only. To use the Cases view's analyst write controls, explicitly start a new local API process with:

```powershell
.\.venv\Scripts\python.exe scripts/run_private_api.py --enable-investigation-writes
```

Use that process's new token. This grants only scoped case creation, notes, verified-reference links, and status changes; it does not authorize assessments, scenario execution, simulator actions, or remediation. See [investigation cases](PHASE4_INVESTIGATION_CASES_AND_MEMORY.md) for bounds and evidence labels.

### Troubleshooting

- **Python version check / `StrEnum` import error:** the API requires Python 3.11 or later. The current launcher stops with an actionable version message before importing application modules; an older checkout may show a `Python310` traceback. Follow [the Python-version fix](DEVELOPMENT.md#python-version-mismatch-strenum) to create the reviewed 3.11 environment, install its dependencies, and start the API using its explicit interpreter.
- **Wrong page at `/`:** `/` is intentionally the public landing page. Use `http://localhost:5174/local-dashboard.html` or the repository-root command `npm.cmd --prefix frontend run dev:dashboard -- --host 127.0.0.1`.
- **404 at the dashboard URL:** confirm the Vite terminal says it is ready on port `5174` and that the repository-root `npm.cmd --prefix frontend` command is being used (or start Vite directly from `frontend/`).
- **Port conflict:** Vite uses `--strictPort`, so it exits instead of silently selecting a different port. Stop a known earlier AegisAI server or resolve the conflicting process before rerunning the command.
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

From `frontend/`: `npm.cmd test` runs TypeScript checking, the production build, Vitest, and static-release tests. From the repository root in PowerShell: `.\.venv\Scripts\python.exe -m pytest -q`, `.\.venv\Scripts\python.exe -m compileall -q private_api platform_prototype scripts tests`, `.\.venv\Scripts\python.exe scripts/build_static_site.py --output <new-empty-directory>`, and `git diff --check`. On Linux, use `.venv/bin/python` for the same Python commands.
