# Phase 2 — Local Private Backend Foundation

**Status:** Local development foundation; synthetic fixtures only. It is not a hosted service, production authentication system, or operational security product.

## Boundary and data flow

The public React + TypeScript + Vite website remains static and read-only. The private API is a separate Python process, binds only to `127.0.0.1`, and is not called by the public frontend or included in its strict static publisher allowlist. It loads the Phase 1 synthetic fixture through the existing bounded Pydantic pipeline, derives a report, and stores that report and its finding/evidence records in a local SQLite database. API requests are read-only. The API does not accept telemetry uploads, arbitrary URLs, credentials, or client-supplied tenant scopes; it does not connect to external systems, call an LLM, run the simulator, or invoke the Controller.

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

Each principal has role `local_read_only`, one tenant ID matching `synthetic-org-*`, and an explicit subset of read scopes. The API derives tenant scope from this principal for every store call. It rejects query parameters entirely, so a supplied `tenant_id` cannot override scope. Missing, invalid, or expired tokens receive the same generic 401 response. Insufficient permission receives a generic 403; inaccessible and nonexistent object IDs both receive the same 404. This is single-user/local-development authentication, not a customer identity system, account login, or production-ready auth design. Do not expose the listener to a LAN or the internet.

## API v1

All routes require a valid bearer token, including the minimal health response. Responses are JSON with `Cache-Control: no-store` and `X-Content-Type-Options: nosniff`.

| Method and route | Required scope | Response |
|---|---|---|
| `GET /health` | `health:read` | `{"status":"ok","mode":"local_synthetic"}`; no configuration or database path. |
| `GET /api/findings` | `findings:read` | Synthetic label, authenticated tenant ID, validated findings. |
| `GET /api/findings/{finding-id}/evidence` | `evidence:read` | Evidence references for a finding in the authenticated tenant. |
| `GET /api/incidents` | `incidents:read` | Synthetic incident summaries for the authenticated tenant. |
| `GET /api/incidents/{incident-id}/report` | `reports:read` | Validated synthetic incident report for the authenticated tenant. |

There are no write, registration, scanning, action, or Controller routes. Query strings and request bodies are rejected. The HTTP layer rejects bodies above 16 KiB before reading them; supported operations accept no body. Input fixture files still use the Phase 1 1 MiB bounded read and strict event schema.

## Persistence and audit

SQLite is appropriate for this local foundation because it provides a durable relational store without a service or new dependency. The ignored `.aegisai-local/private_api.sqlite3` contains only synthetic tenants, reports, findings, evidence references, and audit events. Tables use tenant-scoped composite keys/foreign keys and checks for the synthetic classification and allowed severity. Queries use placeholders and include `tenant_id = authenticated_principal.tenant_id`; returned findings and reports are validated again with Pydantic.

Audit rows record authentication failures, access denials, request rejections, and protected operations with timestamp, tenant where known, fixed route category, outcome, and categorical reason. Tokens, authorization headers, request bodies, and raw paths are not stored. The audit table is append-only through this API (there is no audit route); SQLite files can still be edited by the local OS user, so this is not tamper-evident audit storage.

There is no automatic retention or cleanup job. Stop the server before removing `.aegisai-local/private_api.sqlite3`; it contains synthetic data only. The directory is ignored by Git. Do not put real-client data into this database.

## Run locally

From the repository root:

```powershell
python scripts/run_private_api.py
```

The process prints the loopback URL and a newly generated token per tenant. Keep the token local and out of screenshots, source files, frontend assets, and commits. Example PowerShell request (replace the placeholder with the startup token):

```powershell
$headers = @{ Authorization = "Bearer <startup-token>" }
Invoke-RestMethod -Uri "http://127.0.0.1:8766/api/findings" -Headers $headers
Invoke-RestMethod -Uri "http://127.0.0.1:8766/api/incidents" -Headers $headers
```

To create two isolated synthetic namespaces for local authorization checks, use repeated CLI options:

```powershell
python scripts/run_private_api.py --tenant synthetic-org-alpha --tenant synthetic-org-beta
```

Each tenant receives its own generated token. A request for one tenant's finding or incident under the other token returns the same not-found response as an unknown ID.

## Tests and limitations

`tests/unit/test_private_api.py` covers authentication/expiry, permission checks, tenant-forgery attempts, cross-tenant reads, bounded/malformed requests, database failures, audit records, API response contracts, and loopback binding. The Phase 1 tests continue to cover synthetic parsing, correlation, evidence, and simulation policy. The frontend static publisher allowlist remains unchanged and is exercised by its existing static-release tests.

This foundation is not suitable for multi-user or remote access: it has no identity provider, password/MFA lifecycle, TLS, CSRF/browser integration, tenant onboarding/ownership verification, rate limiter, key rotation service, deployment hardening, backup/restore process, database encryption, tamper-evident audit, or production incident response. Those are explicit future design gates. No real-client telemetry or external target behavior is implemented or implied.
