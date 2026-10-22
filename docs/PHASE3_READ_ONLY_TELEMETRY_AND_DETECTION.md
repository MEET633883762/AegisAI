# Phase 3 — Read-Only Synthetic Telemetry and Continuous Detection

**Status:** Local prototype only. All input is synthetic fixture data. This does not establish real-world detection accuracy or provide a production security monitoring service.

## Scope and data flow

The public React + TypeScript + Vite site remains static, read-only, and disconnected from this pipeline. Phase 1 CLI and Phase 2 incident endpoints remain available. The Phase 3 processor adds a separate, fixed local fixture source; there is no HTTP ingestion endpoint and no caller can select a tenant or source through an ingestion request.

```text
platform_prototype/fixtures/synthetic_telemetry_v1.json
  -> bounded read (1 MiB) + strict Pydantic schema
  -> UTC normalization + event/evidence deduplication
  -> deterministic versioned rules
  -> tenant-scoped SQLite transaction (events, findings, evidence, observations, report, run)
  -> authenticated read-only Phase 2 API routes
```

The API derives tenant scope from its in-memory authenticated principal. The scheduler receives its tenant list from the local startup configuration. It does not trust a tenant ID from a telemetry record. The simulator Controller remains unrelated and is never called.

## Input contract and validation

`SyntheticTelemetryBatch` schema version `1.0` requires source ID `local_synthetic_fixture_v1`, classification `synthetic`, the explicit `SYNTHETIC - NOT REAL CLIENT DATA` label, an aware generation timestamp, and 1–500 events. Files are read with a `MAX_INPUT_BYTES + 1` bound (1 MiB maximum). Models reject unknown fields and limit identifiers and values. Event IDs and all asset, actor, source, and evidence references must use the `synthetic-*` namespace. Timestamps require an offset; event times are normalized to UTC before storage and detection.

Supported event types are `auth_failure`, `auth_success`, `request_rate_indicator`, `simulated_suspicious_activity`, `synthetic_vulnerability_finding`, and `synthetic_configuration_finding`. Each type has an exact allowlist of applicable fields and values. Phase 4 adds explicit benign synthetic codes `routine_setting_read`, `test_component_current`, and `debug_mode_disabled`; the related detection rules ignore those codes. Existing suspicious codes and rule thresholds are unchanged. The schema has no free-form message, credential, token, tenant, target URL, or raw log field. Exact replays deduplicate by tenant and event ID/content; reuse of an event ID with changed content or reuse of an evidence reference by another event is rejected. All event IDs and evidence references remain tenant-scoped.

The bundled fixture contains 10 records, including one exact duplicate, across all supported types. It is an illustration, not client telemetry.

## Deterministic rules

All rules are version `1.0`; their output is a deterministic synthetic exercise, not measured detection performance.

| Rule | Input and behavior | Output |
|---|---|---|
| `AUTH-001` | Reuses the Phase 1 authentication correlation for repeated failed authentication events. | Carries the existing explainable severity/confidence and evidence references. |
| `WEB-001` | Synthetic request-rate indicators with at least 100 requests in a window of at most 60 seconds; indicators are grouped by synthetic asset, actor, and source across the retained detection window. | Medium / 0.82 confidence; high / 0.92 when an indicator is at least 500. |
| `APP-001` | Explicitly allowlisted simulated application activity codes. | High / 0.85 confidence; explanation identifies fixture metadata. |
| `VULN-001` | Allowlisted `test_component_outdated` synthetic vulnerability check. | Medium / 0.80 confidence. |
| `CONFIG-001` | Allowlisted `debug_mode_enabled` synthetic configuration check. | Medium / 0.80 confidence. |

Findings include deterministic tenant-scoped IDs, rule ID/version, severity, confidence, first/last timestamps, synthetic asset, event/evidence references, explanation, confidence factors, and status. Reprocessing preserves existing status and first-seen time, appends evidence and immutable observation snapshots, and does not delete older findings or audit rows. Each report includes input/accepted/duplicate counts and explicit limitations.

## Storage and retention

SQLite schema migrations are additive. Phase 3 advanced `PRAGMA user_version` to `1`; Phase 4 adds a retention index and advances it to `2`. Existing Phase 2 tables and rows are retained. New tables use tenant-scoped keys for events, findings, evidence links, finding observations, reports, and processing runs. A processing cycle writes within a transaction; event conflicts roll back the cycle. Stored events are capped at 10,000 per tenant and each detection pass considers at most the most recent 500 events.

Phase 3 originally had no automated retention. Phase 4 now retains at most the latest 100 telemetry runs and their reports per tenant and 100 observations per finding; see [Phase 4 replay and retention details](PHASE4_ISOLATED_REPLAY_AND_DETECTION_GAP_ANALYSIS.md). Telemetry events remain bounded at 10,000 per tenant. Audit rows are not pruned. The ignored local database under `.aegisai-local/` contains synthetic records only. Stop the local API before an operator removes that database to clear all prototype records. Do not store real client data in it.

## Scheduler

The API starts one local scheduler owner per database. It performs one immediate cycle, then waits 600 seconds between cycles. The owner holds an OS file lock for the database, preventing another local API process from starting a second scheduler for that database. Cycles do not overlap. Each tenant's cycle runs in a child worker process with a 20-second timeout and at most one retry; failures and timeouts are stored as categorical run states. Shutdown signals and joins the scheduler and terminates its active worker. The local fixture is revalidated on each cycle. The scheduler is bounded to five configured synthetic tenants.

This single-host file lock is not distributed coordination. Any future multi-instance deployment must use a distributed scheduler/lease or equivalent coordination, plus a separately reviewed production authentication, storage, retention, and operations design. No deployment scheduler runs in this phase.

## Local API additions

The API continues to bind to `127.0.0.1` and uses the Phase 2 development bearer-token and explicit-scope model. New authenticated GET routes are:

| Route | Scope | Data |
|---|---|---|
| `/api/telemetry/findings` | `telemetry:read` | Findings scoped to the authenticated tenant. |
| `/api/telemetry/findings/{finding-id}/evidence` | `evidence:read` | Evidence references for a tenant-owned finding. |
| `/api/telemetry/reports/latest` | `reports:read` | Latest completed synthetic report for that tenant. |
| `/api/processing` | `processing:read` | Scheduler state and latest tenant run summary. |

No telemetry write/ingestion, job execution, scan, or Controller route is exposed. Query strings remain unsupported. Do not expose this development API to a LAN or the internet.

## Run and verify

From the repository root:

```powershell
python scripts/run_private_api.py
```

The process prints a new local development token at startup. Keep it private and out of source files, screenshots, and commits. The API seeds Phase 1 sample data and starts the synthetic fixture scheduler. The worker module is an internal child process and expects a run already recorded as `started`; use the API scheduler rather than invoking it directly. Focused tests:

```powershell
python -m pytest tests/unit/test_private_telemetry.py tests/unit/test_scheduler.py tests/unit/test_private_api.py tests/unit/test_platform_prototype.py -q
```

## Limitations

The rules use handcrafted synthetic indicators and fixed thresholds; they do not demonstrate production efficacy, inspect real systems, infer attacker behavior, or establish that an asset is vulnerable. There is no external event source, public website integration, real-client telemetry, remote scanning, LLM, or defensive action. This remains a local engineering prototype, not a production-ready service.
