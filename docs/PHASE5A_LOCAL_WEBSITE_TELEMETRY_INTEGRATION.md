# Phase 5A — Local Website Telemetry Integration

> Current setup: use Python 3.11 from the [development guide](DEVELOPMENT.md). PowerShell examples run from the repository root with `.\.venv\Scripts\python.exe`; on Linux use `.venv/bin/python`. Phase-specific verification counts are historical; see [current status](CURRENT_STATUS.md) for fresh checks.

## Scope and boundaries

Phase 5A adds a local-only adapter for one checked-in, deterministic synthetic access/error-log sample. It does not read logs emitted by the demo web server, modify that website, accept uploads, accept caller-selected paths or URLs, or add an HTTP ingestion route. All records are marked synthetic and use fixed synthetic asset, actor, source, and tenant identifiers. A suspicious indicator is a rule match over authored fixture data, not a confirmed attack.

The public React + TypeScript + Vite site and its static publisher allowlist are unchanged. The adapter has no frontend connection and does not call the simulator Controller. It performs no scans, attack execution, configuration changes, blocking, remediation, network access, or LLM calls.

## Data flow

```text
demo_site/fixtures/synthetic_website_logs_v1.json
    -> fixed-path, bounded read (maximum 1 MiB)
    -> strict schema and event-code validation (maximum 500 records)
    -> UTC normalization and stable event/evidence references
    -> existing Phase 3 duplicate/conflict checks and deterministic detector
    -> existing tenant-scoped SQLite events, findings, evidence, report, run status, audit
```

The only direct operator entry point is `scripts/ingest_local_website_telemetry.py`; it has no command-line arguments. The path, database default, and tenant are constants in local Python code. The operator running the command has local filesystem authority. This CLI is not an authenticated API endpoint; Phase 2 API authentication and its server-derived tenant scope are unchanged. The ingestion operation itself always writes to `synthetic-org-demo`, never to a tenant supplied by the fixture or caller.

The existing database schema version and source ID remain unchanged. `source_id=local_synthetic_fixture_v1` identifies the existing storage pipeline; each resulting event retains the specific `source_ref=synthetic-demo-site-access-error-logs-v1`. Two additive telemetry event types preserve ordinary access and harmless error observations without detection: `synthetic_http_access` and `synthetic_application_error`. Existing rule IDs, versions, thresholds, and classification behavior are unchanged. The sample currently exercises `AUTH-001` and `WEB-001`; access and application-error records remain evidence but do not alert.

## Sample log schema

The fixed JSON file uses schema version `1.0`, source identifier `synthetic_demo_site_access_error_logs_v1`, classification `synthetic`, and label `SYNTHETIC WEBSITE LOGS - NOT REAL REQUESTS`. Each record has a bounded synthetic `record_id`, timezone-aware timestamp, allowlisted record type, generic synthetic actor, and evidence identifier. Supported types are:

- `http_access`: allowlisted method, route code, and HTTP status.
- `auth_failure`: only a synthetic `POST` to route code `login` with status 401 or 403.
- `request_rate`: a bounded request count and window in seconds.
- `application_error`: one allowlisted harmless error code.

Raw URL strings, IP addresses, user names, credentials, arbitrary text, free-form messages, and exception traces are not part of the schema. Unknown fields and event codes are rejected. A bounded read reads at most 1 MiB plus one sentinel byte before parsing. Symlink sources and sources outside the approved fixture directory are rejected. Schema failures report only an issue count; filesystem errors report an exception category, not a path or file contents. Timestamps are converted to UTC. The existing telemetry deduplicator accepts identical replayed event IDs and rejects conflicting IDs or evidence references.

## Run and inspect

From the repository root in PowerShell:

```powershell
.\.venv\Scripts\python.exe scripts/ingest_local_website_telemetry.py
```

The command prints the structured synthetic telemetry report. It stores records in `.aegisai-local/private_api.sqlite3`, uses the existing local retention policy, and appends a categorical `website_telemetry.ingest` audit row. It does not print the source path or raw log records. Repeated runs produce a new run/report record but event rows deduplicate; detections are recomputed idempotently from the bounded tenant history.

The API can continue to be run separately with `.\.venv\Scripts\python.exe scripts/run_private_api.py`; its authenticated read-only routes can display persisted data for the same fixed synthetic tenant after startup. The public static site does not call this API. Do not pass client telemetry to this prototype.

## Verification and limitations

Tests cover schema and event-code rejection, byte/record bounds, UTC normalization, stable evidence provenance, duplicate and conflicting records, symlink and missing-source handling, repeated ingestion, tenant fixation, audit outcomes, and absence of a public ingestion route. Phase 3 deterministic detections and scheduler behavior remain covered by their existing tests.

This is a fixture adapter, not a production web-server, reverse-proxy, SIEM, or client-log connector. It does not validate the accuracy of any rule on real traffic. The sample has authored normal access, failed-authentication, high request-rate, and harmless error observations; none were generated by sending requests or attacks to the website. Any future real connector requires separately reviewed written scope, identity, redaction, authorization, retention, and operational controls.
