# Phase 1 — Local Synthetic Security Operations Prototype

> Current setup: use Python 3.11 from the [development guide](DEVELOPMENT.md). PowerShell examples run from the repository root with `.\.venv\Scripts\python.exe`; on Linux use `.venv/bin/python`. Phase-specific verification counts are historical; see [current status](CURRENT_STATUS.md) for fresh checks.

**Status:** Local research prototype. Synthetic fixtures only; not a production detection or defense system.

## Scope and separation

This CLI is separate from the public React + TypeScript + Vite website and from the existing Red/Blue simulator and Controller execution path. It has no listener, client connector, external network call, credential handling, LLM call, production response integration, database, or scheduler. It does not detect or defend against real attacks. The public static publisher allowlist is unchanged and does not include this package, fixture, CLI, or tests.

All inputs must explicitly identify as synthetic and use `synthetic-*` references. Never put real client logs, names, identifiers, credentials, or production data in fixtures or reports. Output is local JSON. Treat the report as synthetic research material and remove it when no longer needed.

## Event schema v1

Input is a JSON object with `schema_version` (`"1.0"`), synthetic `dataset_id`, `data_classification` (`"synthetic"`), the exact label `SYNTHETIC - NOT REAL CLIENT DATA`, timezone-aware `generated_at`, and 1–500 events. The file is limited to 1 MiB, read with a bounded read before parsing. Unknown fields are rejected.

Each event has a `syn-*` event ID, timezone-aware timestamp, allowlisted type (`auth_failure` or `auth_success`), synthetic asset/actor/source references, and a synthetic evidence reference. No raw log message or arbitrary extra field is accepted. Timestamps are normalized to UTC for ordering and report evidence. Exact repeated event IDs with identical normalized content collapse; conflicting reuse of an ID rejects the batch. Correlation is deterministic and groups only matching synthetic asset, actor, and source references.

## Analysis and report

The sample rule correlates at least three failures within ten minutes. A matching success within five minutes after the last failure increases severity to high and confidence to 0.90. Otherwise, three or four failures are medium, five or more are high, and confidence starts at 0.70 and rises by 0.05 per additional event up to 0.95. Reports include rule IDs, matched signal types, factors, recommendations, evidence references/catalog entries, event counts, dataset provenance, and explicit limitations. These thresholds are demonstration logic, not empirically calibrated risk scores.

Report schema v1 is `aegisai_local_synthetic_incident_report`. It is labeled synthetic and includes `report_id`, UTC generation time, dataset ID, input/unique/duplicate counts, evidence catalog, findings, simulated action outcomes, and limitations. The schema rejects findings with missing or unlinked evidence and inconsistent counts.

## Manual workflow and commands

From the repository root:

```powershell
.\.venv\Scripts\python.exe scripts/run_platform_prototype.py
```

This reads the checked-in synthetic fixture and prints a JSON report. To choose another synthetic input, pass `--input path\to\synthetic-events.json`. The same schema and 1 MiB read limit apply. Save output to a new file with `--report path\to\incident-report.json`; an existing file is never overwritten.

Manual investigation is the default. To request a visibly labeled, policy-gated simulation, first copy a `finding_id` from a report, then run:

```powershell
.\.venv\Scripts\python.exe scripts/run_platform_prototype.py --simulate-action increase_monitoring finding-<12-hex-id> --confirm-simulation
```

Only `increase_monitoring` and `create_review_task` are allowlisted. The policy requires a report finding with evidence and confidence at least 0.70; duplicate requests and unsupported actions are denied. Every outcome has `mode: "simulation"` and `executed: false`. No system state changes or external calls occur. Do not interpret an allowed simulation as a completed defensive action.

## Persistence, cleanup, and future scheduling

No SQLite database is justified for a one-shot local CLI that processes synthetic fixtures and returns a report. It retains nothing between invocations. If an operator saves a report with `--report`, that file is an operator-created local artifact; delete it when no longer needed, and do not place it in the public static output. There is no automated retention or secure deletion claim.

This one-shot CLI starts no background scheduler. The separate [Phase 3 API scheduler](PHASE3_READ_ONLY_TELEMETRY_AND_DETECTION.md) is now implemented for the fixed local synthetic fixture, with one owner per database, bounded workers, explicit run states, and a ten-minute cadence. That scheduler does not change this CLI or authorize production scanning or response. Any real-client workflow still requires separate architecture, authorization, privacy, retention, and security review.

## Verification

Focused tests live in `tests/unit/test_platform_prototype.py`; the full Python suite is run with `.\.venv\Scripts\python.exe -m pytest -q`. The frontend regression suite is run from `frontend/` using `npm test`. The strict static publisher allowlist remains the only publication boundary; verify it using the existing frontend static release tests and `.\.venv\Scripts\python.exe scripts/build_static_site.py` with a new empty output path when a release artifact is needed.
