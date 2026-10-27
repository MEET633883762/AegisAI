# Phase 2 — Local Private Backend Foundation

> Current setup: use Python 3.11 from the [development guide](DEVELOPMENT.md). PowerShell examples run from the repository root with `.\.venv\Scripts\python.exe`; on Linux use `.venv/bin/python`. Phase-specific verification counts are historical; see [current status](CURRENT_STATUS.md) for fresh checks.

**Status:** Local development foundation; synthetic fixtures only. It is not a hosted service, production authentication system, or operational security product.

## Boundary and data flow

The public React + TypeScript + Vite website remains static and read-only. The private API is a separate Python process, binds only to `127.0.0.1`, and is not called by the public frontend or included in its strict static publisher allowlist. It loads the Phase 1 synthetic fixture through the existing bounded Pydantic pipeline, derives a report, and stores that report and its finding/evidence records in a local SQLite database. The incident/finding routes introduced in this phase are read-only. The current API also has [optional scoped investigation writes](PHASE4_INVESTIGATION_CASES_AND_MEMORY.md) for analyst cases and notes; those do not execute security actions. The API does not accept telemetry uploads, arbitrary URLs, credentials, or client-supplied tenant scopes; it does not connect to external systems, call an LLM, run the simulator, or invoke the Controller.

```text
synthetic fixture -> Phase 1 schema validation/correlation -> SQLite (tenant-scoped rows)
                                                               ^
local bearer token -> server-side principal -> read permission -> scoped SELECTs
                                                               |
                                               sanitized audit events
```

The existing simulator Controller remains the sole authorization boundary for simulator actions. Its Red/Blue role, phase, and action policy is not a tenant authorization system. The private API has its own explicit read-scope policy and never imports or exposes Controller execution methods.

## Local authentication and authorization

At startup, the server generates a cryptographically random 256-bit bearer token for each bootstrapped synthetic tenant and prints it once to the local terminal. Tokens are held only as SHA-256 digests in process memory, expire after eight hours by default (configurable up to 24 hours), and are revoked on process exit/restart. No default credential or registration endpoint exists. Token principals are built at startup from the CLI's `--tenant` options; the HTTP request cannot create a principal or select a tenant.

Default principals have role `local_read_only`, one tenant ID matching `synthetic-org-*`, and explicit read scopes. Starting with `--enable-investigation-writes` issues a `local_investigator` principal with the additional `investigations:write` scope. The API derives tenant scope from this principal for every store call. The incident/finding routes reject query parameters. The later investigation-list route accepts only its bounded search/status filters; no request can supply a `tenant_id` to override scope. Missing, invalid, or expired tokens receive the same generic 401 response. Insufficient permission receives a generic 403; inaccessible and nonexistent object IDs both receive the same 404. This is single-user/local-development authentication, not a customer identity system, account login, or production-ready auth design. Do not expose the listener to a LAN or the internet.

## API v1

All routes require a valid bearer token, including the minimal health response. Responses are JSON with `Cache-Control: no-store` and `X-Content-Type-Options: nosniff`.

| Method and route | Required scope | Response |
|---|---|---|
| `GET /health` | `health:read` | `{"status":"ok","mode":"local_synthetic"}`; no configuration or database path. |
| `GET /api/findings` | `findings:read` | Synthetic label, authenticated tenant ID, validated findings. |
| `GET /api/findings/{finding-id}/evidence` | `evidence:read` | Evidence references for a finding in the authenticated tenant. |
| `GET /api/incidents` | `incidents:read` | Synthetic incident summaries for the authenticated tenant. |
| `GET /api/incidents/{incident-id}/report` | `reports:read` | Validated synthetic incident report for the authenticated tenant. |

The routes in this table accept no request body or query string and expose no registration, scanning, action, or Controller execution. Later local additions include telemetry, evaluation, assessment, executive-report, scenario-history, and investigation reads, plus separately scoped investigation `POST` routes. The HTTP body cap remains 16 KiB. See [the local dashboard guide](PHASE7A_LOCAL_DASHBOARD.md) for the current views and [investigation authorization](PHASE4_INVESTIGATION_CASES_AND_MEMORY.md) for write boundaries. Input fixture files still use the Phase 1 1 MiB bounded read and strict event schema.

## Persistence and audit

SQLite is appropriate for this local foundation because it provides a durable relational store without a service or new dependency. The ignored `.aegisai-local/private_api.sqlite3` contains only synthetic tenants, reports, findings, evidence references, and audit events. Tables use tenant-scoped composite keys/foreign keys and checks for the synthetic classification and allowed severity. Queries use placeholders and include `tenant_id = authenticated_principal.tenant_id`; returned findings and reports are validated again with Pydantic.

Audit rows record authentication failures, access denials, request rejections, and protected operations with timestamp, tenant where known, fixed route category, outcome, and categorical reason. Tokens, authorization headers, request bodies, and raw paths are not stored. The audit table is append-only through this API (there is no audit route); SQLite files can still be edited by the local OS user, so this is not tamper-evident audit storage.

There is no automatic retention or cleanup job. Stop the server before removing `.aegisai-local/private_api.sqlite3`; it contains synthetic data only. The directory is ignored by Git. Do not put real-client data into this database.

## Run locally

From the repository root:

```powershell
.\.venv\Scripts\python.exe scripts/run_private_api.py
```

The process prints the loopback URL and a newly generated token per tenant. Keep the token local and out of screenshots, source files, frontend assets, and commits. Example PowerShell request (replace the placeholder with the startup token):

```powershell
$headers = @{ Authorization = "Bearer <startup-token>" }
Invoke-RestMethod -Uri "http://127.0.0.1:8766/api/findings" -Headers $headers
Invoke-RestMethod -Uri "http://127.0.0.1:8766/api/incidents" -Headers $headers
```

To create two isolated synthetic namespaces for local authorization checks, use repeated CLI options:

```powershell
.\.venv\Scripts\python.exe scripts/run_private_api.py --tenant synthetic-org-alpha --tenant synthetic-org-beta
```

Each tenant receives its own generated token. A request for one tenant's finding or incident under the other token returns the same not-found response as an unknown ID.

## Tests and limitations

`tests/unit/test_private_api.py` covers authentication/expiry, permission checks, tenant-forgery attempts, cross-tenant reads, bounded/malformed requests, database failures, audit records, API response contracts, and loopback binding. The Phase 1 tests continue to cover synthetic parsing, correlation, evidence, and simulation policy. The frontend static publisher allowlist remains unchanged and is exercised by its existing static-release tests.

This foundation is not suitable for multi-user or remote access: it has no identity provider, password/MFA lifecycle, TLS, production browser-session/CSRF design, tenant onboarding/ownership verification, rate limiter, key rotation service, deployment hardening, managed backup/restore, database encryption, tamper-evident audit, or production incident response. The later same-computer dashboard uses only two fixed loopback CORS origins and ephemeral bearer tokens; that integration is not production authentication. Those are explicit future design gates. No real-client telemetry or external target behavior is implemented or implied.
