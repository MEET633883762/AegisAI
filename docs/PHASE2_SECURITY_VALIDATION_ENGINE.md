# Phase 2 — Local Security Validation Engine

## Scope and design

This increment extends the existing separately gated `local_assessment` controller. The simulator `Controller` and `ControllerPolicy` remain unchanged. The private API remains read-only; running checks continues to require the local operator CLI. The browser cannot select a target, path, command, or check catalog.

The versioned `local-web-checks-v1` catalog contains the existing three fixed checks: health status, response security headers, and cookie attributes. Each report observation snapshots its check version, category, description, severity, expected and observed result, status, UTC observation time, evidence reference, and configuration version. Status values are `PASS`, `FAIL`, `ERROR`, and `NOT_APPLICABLE`. A lack of a cookie is `NOT_APPLICABLE`; a policy denial, failed request, timeout, oversized response, or refused redirect is `ERROR`. A status or cataloged configuration mismatch is `FAIL`. A response observation alone remains an observation or inferred risk; this checker does not produce confirmed vulnerability findings.

The catalog's ATT&CK technique and defensive control lists are intentionally empty. Passive header, cookie, and health observations do not establish adversary behavior, and no named control mapping has been independently reviewed for these checks. The catalog records that rationale rather than implying a mapping.

## Run comparison and persistence

The report builder keeps the existing deterministic content-based report ID and evidence deduplication. Tenant-scoped SQLite persistence compares inferred-risk identities with the most recent valid report snapshot and records introduced, resolved, and unchanged risks with their evidence references. Matching uses the check ID, classification, and title; changing evidence remains visible in the report while not falsely creating a new risk identity. A malformed prior snapshot is not used as a baseline. Repeat runs with unchanged report content update the latest timestamp/metadata rather than duplicating the report row. The normal store audit event is still recorded for each operator-initiated save.

There is no SQL schema change or migration. Version 2 report metadata uses the existing validated `report_metadata_json` column. The reader retains compatibility with version 1 metadata and its original observation/evidence digests. Existing retention remains bounded to 20 report snapshots per tenant, with orphan observation cleanup in the existing transaction.

## Safety boundaries

- Exact `http://127.0.0.1:8767` origin; only the three catalogued GET paths; policy is checked immediately before transport.
- No automatic redirects, external target selection, uploads, credentials, shell execution, exploit payloads, remediation actions, or LLM calls.
- At most three checks, 1-second per-request and 4-second overall deadlines, 16 KiB body cap; response evidence stores status, byte count, and a digest rather than the body.
- Existing private API authentication and tenant-derived report reads are unchanged. No endpoint starts an assessment.
- All automated assessment/storage tests use temporary databases and local ephemeral test servers.

## Baseline and verification

The pre-change baseline is recorded in [Phase 1 Baseline Report](PHASE1_BASELINE_REPORT.md). It includes the observed default Vitest worker-startup timeout and the passing single-worker retry. The assessment-focused tests cover fixed-target policy denials and zero requests, loopback success, redirect refusal, timeout/deadline, response bounds, result classification, evidence links, legacy schema compatibility, tenant isolation, audit behavior, and run comparisons.

Post-change checks observed: `python -m pytest -q -p no:cacheprovider tests/unit/test_local_assessment.py tests/unit/test_local_assessment_api.py tests/unit/test_local_assessment_reporting.py tests/unit/test_run_local_assessment_cli.py` — 44 passed; `python -m compileall -q local_assessment private_api scripts tests` — passed; frontend `npm.cmd run typecheck` — passed; frontend `npm.cmd run build` — passed; frontend `vitest run --pool=threads --maxWorkers=1 tests/local_dashboard.test.tsx` — 23 passed; frontend `npm.cmd run test:release` — 4 passed; `git diff --check` — passed (Git printed only existing line-ending normalization warnings).

This synthetic local checker is not a penetration test, does not establish exploitability or real-world detection accuracy, and does not support arbitrary environments. The historical comparison only sees retained valid assessment report snapshots; it is not a full event history.
