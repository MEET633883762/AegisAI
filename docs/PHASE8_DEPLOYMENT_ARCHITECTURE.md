# Phase 8 — Deployment architecture and release boundary

For current runtime setup and fresh verification, use [DEVELOPMENT.md](DEVELOPMENT.md) and [CURRENT_STATUS.md](CURRENT_STATUS.md). Runnable packaging examples below were refreshed on 2026-10-27. This architecture's production boundaries and unmet deployment gates remain unchanged.

**Status:** architecture decision only. Nothing was deployed or published. The public static site can be packaged for a static host. The private API, dashboard, assessment runner, telemetry pipeline, and SQLite store remain local synthetic development components and are not production-ready.

## Repository findings

- The public website is React + TypeScript + Vite. `scripts/build_static_site.py` copies an explicit nine-path allowlist from `frontend/.vite-build/` plus `frontend/_headers`, and refuses non-empty output directories. The allowlist is unchanged by this phase.
- The private API is a Python `ThreadingHTTPServer` fixed to `127.0.0.1`. It uses ephemeral in-memory development bearer tokens, fixed local CORS origins, and synthetic tenant identifiers. It has no TLS termination, external identity provider, production secret configuration, deployment server, or hosted trusted-origin configuration. `AEGISAI_ENV` values other than `local` or `development` cause startup to stop.
- The store is SQLite schema version 6. The ignored `.aegisai-local/` directory contains local state. `SQLiteStore` performs additive `CREATE TABLE IF NOT EXISTS` initialization and rejects databases newer than the application; there is no standalone migration command or down migration.
- No container, compose, process-manager, or cloud deployment artifact is configured. The frontend `_headers` file uses Cloudflare Pages header syntax; another static host must be configured with equivalent headers explicitly.

## Decision

### A. Public website

Deploy only the generated output of the strict static publisher to a static HTTPS host. Do not deploy from the repository root or publish the frontend source directory. Keep the exact publisher allowlist:

```text
_headers
index.html
dashboard.html
privacy.html
assets/app.css
assets/main.js
assets/public_demo_episode.json
assets/public_demo_assessment_baseline.json
assets/public_demo_assessment_hardened.json
```

The private local dashboard is not in this list. Neither are Python modules, source maps, SQLite files, `.aegisai-local/`, credentials, private reports, evaluation datasets, or development configuration. Do not add serverless functions or API proxy routes to the public site. Retain HTTPS, the existing CSP and security headers, and configure equivalent headers if the chosen host does not consume `_headers` directly. Review the actual hosted response headers before public release.

Package a release into a new empty directory, from the repository root after creating the Python 3.11 environment:

```powershell
npm.cmd --prefix frontend ci
npm.cmd --prefix frontend test
.\.venv\Scripts\python.exe scripts/build_static_site.py --output dist/aegisai-release
```

`npm.cmd --prefix frontend test` includes the production build. On Linux, use `npm` and `.venv/bin/python` in the same commands. If reviewed dependencies are installed directly into Python 3.11 on Windows, `py -3.11 scripts/build_static_site.py --output dist/aegisai-release` is another explicit interpreter choice. `.python-version` does not switch an existing `python` command on `PATH`.

Review the output tree and confirm it contains only the nine paths above before selecting it as the static host's publish directory. The commands prepare a package; they do not publish it.

### B. Private application/API

**Current supported deployment: none.** Keep the private API and local dashboard on the developer workstation, bound to loopback. Do not expose port 8766 or the Vite development server to the internet or a shared LAN. The development bearer token is printed to the local terminal and revoked when the process exits; it is not a deployable credential. The API has no production authentication, TLS, trusted proxy, or external origin configuration.

For a future internal pilot, the fitting target shape is a single private application instance in a restricted private network behind a maintained HTTPS reverse proxy, with the dashboard and API on a private operator origin. Require a real identity provider or managed secret mechanism, short-lived scoped credentials, explicit trusted-origin/CORS configuration, rate limiting, centralized redacted logs, and operator access controls before implementing that target. Do not run this code behind a public reverse proxy as-is. No provider or product is selected here.

### C. Database and storage

The current SQLite store is appropriate only for local synthetic use. It expects a durable local file and supports one local application deployment pattern; ephemeral container storage would lose state. For a future single-instance private pilot that intentionally retains SQLite, mount a persistent encrypted volume, restrict filesystem access to the service account, stop or quiesce writes for file-level copies, and use SQLite's backup API for consistent backups. Store backups separately with access controls and retention. Document and rehearse restore into an isolated location before relying on them.

Schema initialization happens when `SQLiteStore` opens a database. There are no down migrations. Before any future schema upgrade, stop the app, take and verify a backup, test the upgrade on a copy, and retain the previous application version. Roll back by restoring the pre-upgrade copy if the new schema is incompatible; do not launch older code against a schema version it does not support. This document does not authorize or perform a database migration or backup.

### D. Development and demonstration

Keep the harmless website on `127.0.0.1:8767`, the private API on `127.0.0.1:8766`, and use only synthetic fixtures, fixed local checks, and the ignored local data directory. Use an explicitly selected presentation database when needed. Never place production credentials or real customer telemetry in this environment. The public static site remains read-only and independent from these services.

The public demo runs at `http://localhost:5174/dashboard.html` with Vite and needs no Python service. The separate operations UI is `http://localhost:5174/local-dashboard.html`; start its API with `.\.venv\Scripts\python.exe scripts/run_private_api.py` and use the ephemeral startup token. See [the local dashboard guide](PHASE7A_LOCAL_DASHBOARD.md). The older, separate four-header website demonstration uses port 8765; do not confuse it with the telemetry website on 8767.

## Production release gates

Do not promote the private application until all of these are designed, implemented, and reviewed:

1. Production authentication and authorization, including tenant identity from a trusted principal.
2. HTTPS, trusted proxy handling, origin/CORS policy, and secure credential lifecycle.
3. Production-grade request and concurrency limits, observability, and redacted audit/log retention.
4. Persistent storage, access controls, tested backups/restores, and explicit migration/rollback procedures.
5. Deployment-specific health/readiness probes, least-privilege service identity, patching, and incident response ownership.
6. Threat-model, security, accessibility, and hosted-header review; owner approval for the selected host and data handling.

The current `/health` and authenticated `/ready` endpoints support local operation checks only. They do not establish production readiness. There is no production environment file, container, API deployment manifest, migration runner, backup automation, or rollback automation, and none is added because it could imply unsupported readiness.

## Troubleshooting and rollback

- If the published package contains an unexpected file, do not publish it. The publisher should reject output outside its allowlist; inspect the generated folder and the allowlist implementation.
- If the static host does not apply `_headers`, configure equivalent CSP, HSTS, frame, MIME, referrer, and permissions headers in that host before release.
- If the local API refuses startup under a non-local `AEGISAI_ENV`, that is intentional. Do not change the environment to bypass the guard for deployment.
- For a static release regression, switch the static host back to the last reviewed release artifact using its documented rollback process, then verify page and response headers. No deployment or rollback has been performed.
- For a future private service/database rollback, stop writes, preserve the failed deployment logs without secrets, restore the verified pre-upgrade database backup if required, deploy the last compatible application version, and verify readiness before reopening access. No production restore procedure has yet been exercised.

## Current status

The public static artifact is the only deployment candidate. The private API/dashboard and all telemetry, assessment, evaluation, and investigation persistence remain local prototypes. This architecture does not claim production readiness, real-world detection performance, or a verified recovery capability.
