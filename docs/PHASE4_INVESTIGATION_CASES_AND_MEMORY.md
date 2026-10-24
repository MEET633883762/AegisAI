# Phase 4 — Investigation cases and memory

This phase adds a human-led case layer to the authenticated local dashboard. It organizes existing tenant-scoped telemetry findings and evidence; it does not run detection, assessment checks, simulator actions, or automated response.

## Case data and labels

Each stored case receives a stable `case-<16 hex>` identifier, a bounded title, status (`open`, `under_review`, or `closed`), and created/updated UTC timestamps. Findings may be linked only when they already exist as telemetry findings for the authenticated tenant. A finding link records its rationale and is explicitly classified as an `inferred_relationship` or `analyst_conclusion`. Evidence links are accepted only when the evidence reference already exists for that same tenant and linked finding; they are labeled `verified_evidence` to mean the stored reference was checked, not that the finding is confirmed.

Append-only analyst notes are labeled either `analyst_conclusion` or `unresolved_hypothesis`. Case creation and status changes appear as `case_activity`. The timeline combines case history, linked finding timestamps, verified stored event timestamps, and explicitly linked assessment/evaluation context. These labels do not promote inferred relationships or hypotheses into facts. Recommendations are deterministic manual-review recommendations from the existing executive report builder and carry the supporting finding IDs. No LLM or external analysis service is used.

Assessment context can reference only a report stored for the authenticated tenant. Evaluation context can reference only a run in the fixed synthetic evaluation history currently loaded by the private API. Context links identify reports/runs and timestamps; they do not copy their raw data into a case or assert that their findings are related.

## API, authorization, and storage

The private API exposes authenticated `GET /api/investigations/cases` and `GET /api/investigations/cases/{case_id}` routes with server-side tenant scoping. The list supports bounded `q` title search and fixed status filters. Writes use only controlled `POST` routes for case creation, finding/evidence/context association, append-only notes, and status changes. Request bodies are size-limited by the existing API boundary and validated with strict models. Bearer tokens and secret-like strings are rejected from case rationale and note text; payloads are not copied into the global audit log.

Read-only development tokens cannot write cases. To explicitly issue the local startup token with the narrow `investigations:write` scope, start the private API with:

```powershell
python scripts/run_private_api.py --enable-investigation-writes
```

All other routes retain their existing scopes and behavior. The case store uses additive schema version 5 tables with composite `(tenant_id, case_id)` ownership and foreign keys to existing tenant findings/evidence. Case writes append categorized history in the same SQLite transaction. The API also records the existing `protected_operation` audit event. Caps are 200 cases per tenant, 100 findings and 500 evidence references per case, 500 notes, 40 historical context references, and 2,000 total history entries per case. The case list returns at most 200 rows. Existing cases are not automatically pruned or deleted.

## Limitations

- The first version links current synthetic telemetry findings, not the older simulator incident findings.
- Assessment and evaluation runs must be linked explicitly; the system does not infer correlation between separate run types.
- Evaluation run history is fixed local synthetic benchmark context and is not tenant-generated detection evidence.
- Search is over case titles/IDs, with a status filter; it is not a general event-query language.
- This is a local prototype, not a production incident-management system. It has no multi-user analyst identity, distributed access control, notifications, AI assistant, or response actions.

## Verification

Focused Python coverage uses temporary SQLite databases only:

```powershell
python -m pytest -q -p no:cacheprovider tests/unit/test_investigations.py tests/unit/test_private_api.py tests/unit/test_private_telemetry.py tests/unit/test_local_assessment_reporting.py
```

Dashboard coverage and type checking:

```powershell
cd frontend
npm.cmd run typecheck
npm.cmd run test:unit -- tests/local_dashboard.test.tsx
```

The schema-upgrade test starts from a temporary v4 database with only the v4 tables and verifies the additive v5 tables. No local application database or original assessment report is used by these tests.
