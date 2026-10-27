# Phase 5C — Telemetry Reliability and Recovery

> Current setup: use Python 3.11 from the [development guide](DEVELOPMENT.md). PowerShell examples run from the repository root with `.\.venv\Scripts\python.exe`; on Linux use `.venv/bin/python`. Phase-specific verification counts are historical; see [current status](CURRENT_STATUS.md) for fresh checks.

Phase 5C implementation recorded 2026-10-22. This is a local synthetic reliability prototype, not a production telemetry service.

## Existing behavior and gaps

Phase 5A reads one fixed checked-in synthetic fixture. Phase 5B reads the loopback test site's fixed JSONL files under `.aegisai-local/website-telemetry/`; callers cannot select a path, URL, or tenant. The reader bounds each file to 1 MiB, each line to 16 KiB, and each combined snapshot to 500 complete records. It ignores a final line without a newline so a later run can read it after completion. Before Phase 5C it read only the active file and `.1` rotation for each log type.

Ingestion rereads the retained bounded snapshot from the beginning on every run. Deterministic event and evidence identifiers plus tenant-scoped SQLite uniqueness/content-hash checks make exact replays idempotent and conflicting IDs fail. Events, finding changes, evidence, report, and completed run are committed in one SQLite transaction. A failure before commit rolls them back; an audit row is attempted separately after the operation. The repeated full read is intentionally used instead of byte-offset checkpoints: an offset can advance past a partial record or become invalid after truncation/rotation.

## Phase 5C behavior

- The source reader now has a fixed, ordered window of active, `.1`, `.2`, and `.3` files for each of access and error logs. The 1 MiB per-file byte limit and 500-record combined snapshot limit still apply. The source reader accepts no path arguments and resolves each file within the fixed local log directory; symlinks and outside paths are rejected.
- Every run rereads complete records in the retained window. Partial trailing lines are ignored and reconsidered on the next run. SQLite's unique `(tenant_id, event_id)` and `(tenant_id, evidence_ref)` constraints plus content hashes reject conflicting replays rather than silently merging them.
- `telemetry_source_status` is created by an additive schema version 2 → 3 migration. It is keyed by tenant and one fixed live-demo source key. It stores last attempt/success, current status, bounded counts, total observed bytes, a SHA-256 fingerprint of the current retained snapshot, and a categorical error code. It stores no log lines or filesystem paths. Source status is returned only through the existing authenticated private API boundary at `GET /api/telemetry/sources/live-website/status`, using the authenticated principal's tenant and `telemetry:read` scope.
- A successful source status update shares the transaction that commits events, findings, report, and the run. An interrupted transaction therefore does not publish a success status. Failed attempts record only `source_invalid`, `processing_error`, or `store_error`; raw records and stack traces are not returned by the status route.
- If no source-status row exists yet, the existing authenticated status route returns a read-only `unavailable` response with null counters and timestamps. This makes “not recorded” distinct from healthy without inserting state or changing the database schema. The dashboard marks a failed refresh as unavailable and warns that any retained source values may be stale.
- Parsing fails closed at the first malformed complete record. `rejected_record_count` is therefore a bounded count of the rejected record that stopped that attempt, not a claim that later unread lines were inspected.
- Existing retention remains in force: telemetry runs/reports are capped at 100 per tenant, finding observations at 100 per finding, and telemetry events at 10,000 per tenant. Audit rows remain append-only and are not covered by those caps.

## Recovery guarantees and limits

If a process stops before a cycle commits, the next run rereads the currently retained complete records and retries. If a line is partially written, a later run can ingest it after the newline and full record arrive. Repeated reads do not add duplicate events/evidence or duplicate findings; each ingestion attempt still creates its intended run/report and audit entry.

The source fingerprint is an operator observation, not a checkpoint and not proof that earlier data was ingested. A status of `running` after a hard process termination means the attempt may have stopped before status completion; the next attempt replaces it. The system cannot recover records already removed from the active log and all four retained generations before ingestion, nor can it guarantee a consistent multi-file snapshot while logs are concurrently written/rotated. This prototype has no durable log archive, file locking, filesystem watcher, or distributed coordination. The fixed source window is bounded, not lossless.

## Schema, tests, and operation

The Phase 5C migration to schema version 3 added only the `telemetry_source_status` table. The current store is version 6 after later assessment, investigation, and scenario-history additions. Migration tests use temporary databases and verify existing rows survive an upgrade from version 2. No change to Phase 1/2 event schemas, the public static frontend, the simulator, or the Controller is intended.

Run the local synthetic site, traffic generator, and ingestion workflow as documented in [Phase 5B](PHASE5B_LOCAL_LIVE_TELEMETRY_VALIDATION.md). The authenticated source status route is read-only. Use only temporary test directories/databases for reliability tests.

Verification commands:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m compileall -q private_api scripts tests
npm.cmd --prefix frontend test
npm.cmd --prefix frontend run build
.\.venv\Scripts\python.exe scripts/build_static_site.py --output <new-empty-output-directory>
git diff --check
```

This phase remains a local synthetic prototype. It is not production-ready, does not ingest client telemetry, and does not establish real-world detection accuracy or data-loss guarantees.
