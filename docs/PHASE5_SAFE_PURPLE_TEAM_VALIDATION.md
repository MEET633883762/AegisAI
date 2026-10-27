# Phase 5 — Safe Purple-Team Validation

> Current setup: use Python 3.11 from the [development guide](DEVELOPMENT.md). PowerShell examples run from the repository root with `.\.venv\Scripts\python.exe`; on Linux use `.venv/bin/python`. Phase-specific verification counts are historical; see [current status](CURRENT_STATUS.md) for fresh checks.

## Scope

This increment adds a small, fixed catalog of synthetic scenarios against the existing loopback-only demo website at `http://127.0.0.1:8767`. It does not emulate an external adversary or test client infrastructure. Catalog version is `aegisai-purple-scenarios-v1`; scenario IDs are stable and each definition is versioned.

| Scenario | Purpose and requests | Expected telemetry | Expected detection | Assessment reference | Cleanup |
|---|---|---|---|---|---|
| `local-health-baseline` v1.0 | One `GET /health` | One `synthetic_http_access`, `health`, HTTP 200 | No finding associated with this request | `health_status_v1` | No site data changes; one bounded access record is subject to normal log rotation |
| `synthetic-auth-rejection` v1.0 | Three sequential empty-body `POST /login-failure` requests; sends no credentials | Three `auth_failure` records, `login`, HTTP 401 | Existing `AUTH-001` rule with evidence referencing these records | None | No account or site data changes; three bounded access records are subject to normal log rotation |

Prerequisite for both scenarios: the existing synthetic website is running on loopback. A 30-second SQLite lease limits execution to one active scenario per tenant, including across local processes, and expires after a crashed runner. The runner is serial, permits at most three requests, applies a one-second per-request timeout and a four-second overall deadline for network requests, and bounds response data to 16 KiB. The fixed log reader accepts at most 500 records from its approved active-plus-three-rotations files; storage uses existing bounded event retention. Redirects are disabled and malformed or unsupported response framing is rejected. Policy checks the catalog ID and fixed origin immediately before every request. No target, method, path, body, or request count is accepted from a caller.

## Preview and execution

From the repository root, preview without starting a database or sending requests:

```powershell
.\.venv\Scripts\python.exe scripts/run_purple_team_scenario.py
.\.venv\Scripts\python.exe scripts/run_purple_team_scenario.py --scenario synthetic-auth-rejection
```

After starting `.\.venv\Scripts\python.exe demo_site/telemetry_server.py`, explicitly authorize a synthetic run:

```powershell
.\.venv\Scripts\python.exe scripts/run_purple_team_scenario.py --scenario local-health-baseline --execute-synthetic --authorize-synthetic-execution --database .aegisai-local/presentation.sqlite3
.\.venv\Scripts\python.exe scripts/run_purple_team_scenario.py --scenario synthetic-auth-rejection --execute-synthetic --authorize-synthetic-execution --database .aegisai-local/presentation.sqlite3
```

`--execute-synthetic` without the separate authorization flag records `NOT_RUN` and sends zero requests. The origin and endpoints cannot be changed. The explicit flag is an operator authorization gate for the current synthetic-only functionality; it does not authorize any non-synthetic target, which has no catalog entry or implementation.

An execution reads the fixed active-plus-three-rotations JSONL source using the existing connector, runs the existing ingestion/detection flow using the selected SQLite store, and stores a compact scenario result, including actual HTTP statuses and a sanitized error category. It does not edit logs or invoke the simulator Controller. Result status is `NOT_RUN`, `PASSED`, `FAILED`, `ERROR`, or `NOT_APPLICABLE`. Comparisons reference the prior run for the same scenario and report whether its status changed. Expected detections and observed findings remain separate. A pass means the scenario's expected synthetic log records and rule output were observed; it does not establish real-world control effectiveness.

## Persistence and bounds

SQLite schema version 6 adds `purple_team_scenario_runs` and a tenant-scoped execution lease, both scoped to the fixed synthetic demo tenant. Reports include catalog/scenario versions, exact execution scope, timestamps, policy decision, expected and observed event types, event/evidence references, relevant rule IDs, assessment check IDs, and telemetry report/run IDs. No raw response bodies are persisted. At most 100 scenario results are retained per tenant. Every stored run creates a categorical protected-operation audit event. There is no public route or dashboard execution control.

## Limitations

- The scenarios cover two fixed behaviors on one local synthetic site; they do not prove comprehensive defensive coverage.
- The auth-rejection scenario invokes a harmless built-in route that accepts no credentials, request body, or account mutation. It is not a credential test.
- Live execution requires the fixed log source to remain within its supported bounded rotation window. Records rotated away before ingestion cannot be recovered.
- The report reuses current telemetry report findings and associates them only when finding event IDs intersect the newly observed scenario records. A missing expected match is reported as failure; it is not repaired by changing detection rules.
- Assessment references identify applicable check IDs; the scenario runner does not launch separate assessment checks or claim to have a persisted assessment report for them.
- No non-synthetic testing, external target, autonomous agent, remediation action, or arbitrary request capability exists.

## Focused tests

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/unit/test_purple_team_scenarios.py tests/unit/test_investigations.py tests/unit/test_local_assessment.py tests/unit/test_live_website_telemetry.py
```
