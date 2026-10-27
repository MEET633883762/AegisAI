# Phase 4 — Isolated Synthetic Replay and Detection-Gap Analysis

> Current setup: use Python 3.11 from the [development guide](DEVELOPMENT.md). PowerShell examples run from the repository root with `.\.venv\Scripts\python.exe`; on Linux use `.venv/bin/python`. Phase-specific verification counts are historical; see [current status](CURRENT_STATUS.md) for fresh checks.

**Status:** Local evaluation lab. This is not an attack engine, production detection benchmark, or evidence of real-world efficacy.

## Boundaries and architecture

Replay reads only `platform_prototype/fixtures/replay_scenarios_v1.json`, a reviewed, checked-in synthetic library. It has no scenario-path option, upload route, target URL, network access, persistent replay store, schedule, Controller call, defensive action, or public website integration. Replay is a separate on-demand CLI operation and is never invoked by the Phase 3 ten-minute scheduler.

Each scenario is independently normalized and passed to the existing `private_api.telemetry.detect_findings` rules. A scenario-specific synthetic namespace is used for deterministic finding IDs; scenarios are not combined, persisted, or sent to the scheduler. This prevents cross-scenario correlation and replay data cannot contaminate Phase 3 SQLite records.

## Scenario library schema v1

The top-level object requires `schema_version`, `library_id`, `library_version`, synthetic classification and label, and 1–100 scenarios. Each scenario requires a unique `scenario_id`, `scenario_version`, synthetic classification, `scenario_class` (`positive` or `benign`), category, description, 1–100 existing `SyntheticTelemetryEvent` records, expected rule IDs, expected evidence references, and rationale. The library is limited to 1 MiB and 1,000 total events. Event schema and allowlists are reused from Phase 3. Unknown fields, unsupported versions/rules, naive timestamps, extra fields, excessive lengths/counts, duplicate scenario/event/evidence IDs, and evidence references not present in that scenario are rejected with a safe issue count.

The library covers repeated authentication failures and success, high request rate, simulated application setting activity, a synthetic outdated-component check, and a synthetic configuration warning. Benign controls cover below-threshold authentication/rate indicators plus `routine_setting_read`, `test_component_current`, and `debug_mode_disabled` records for application, vulnerability, and configuration rule families. These three allowlisted benign codes were added to the synthetic schema; existing detection codes, thresholds, and positive behavior are unchanged. `replay_scenarios_malformed_v1.json` is an intentionally invalid negative fixture; the CLI never loads it.

## Metric definitions

The evaluation universe is every pair of scenario and supported rule ID (`AUTH-001`, `WEB-001`, `APP-001`, `VULN-001`, `CONFIG-001`). A pair is expected-positive only when that scenario labels the rule in `expected_rule_ids`.

- **TP:** expected rule is observed in that scenario.
- **FN:** expected rule is absent in that scenario.
- **FP:** a rule is observed but was not expected for that scenario, including unexpected benign alerts.
- **TN:** a rule is neither expected nor observed in that scenario.
- **Precision:** `TP / (TP + FP)`; null if the denominator is zero.
- **Recall:** `TP / (TP + FN)`; null if the denominator is zero.
- **F1:** `2TP / (2TP + FP + FN)`; null if its denominator is zero.
- **Scenario detection coverage:** positive scenarios where all expected rules were observed divided by positive scenarios; null if there are no positive scenarios.
- **Evidence completeness:** expected scenario/rule pairs with all labeled evidence references present in the matched finding divided by all expected pairs; null if there are no expected pairs. A missed rule is incomplete.

Metrics are reported overall and per rule. The report includes the expected/observed rules and evidence references for each scenario, finding records, missed detections, unexpected alerts, and recommendations tied to observed gaps. A clean result emits no gap recommendation. A zero denominator is never presented as 0% or 100%.

The sample library currently yields **TP 5, FP 0, TN 45, FN 0**, with precision/recall/F1 and positive scenario coverage/evidence completeness each reported as `1.0`. These values describe only five hand-labeled synthetic positives and five controls; they are not statistical estimates or real-world performance claims.

## Reproducibility and report

Each CLI invocation gets a unique `replay_id` and UTC start/finish timestamps. Scenario findings, rule matches, evidence, metrics, and a SHA-256 fingerprint of the validated library are deterministic for unchanged input and rule versions. Replay has no state-changing side effect, so rerunning is idempotent with respect to the application. The report is synthetic-labeled and includes library version/provenance, all per-scenario results, confusion counts, nullable ratios, evidence completeness, missed/unexpected cases, gap-specific recommendations, and limitations.

## CLI

From the repository root:

```powershell
.\.venv\Scripts\python.exe scripts/run_replay_lab.py
```

Output is JSON on stdout. To save it, specify a new path; existing output files are refused:

```powershell
.\.venv\Scripts\python.exe scripts/run_replay_lab.py --report results/synthetic_detection_gap_report.json
```

The command accepts no library path, event input, target, or execution option. `results/` assessment files are not read or changed by this tool.

## Phase 3 history retention

SQLite schema version advances additively from 1 to 2 to add a retention index. Per tenant, the store retains the newest 100 telemetry run rows and their reports, and the newest 100 distinct observation snapshots per finding. Cleanup is transactionally applied when a run starts/completes/fails or is skipped. Existing Phase 2 incidents/findings and original assessment artifacts are outside this policy. Telemetry event rows remain bounded at 10,000 per tenant; telemetry findings and evidence are bounded by those stored events. Audit rows remain append-only and are never pruned by this cleanup.

Existing records are not truncated merely by the migration. On future runs above the caps, older synthetic run/report and observation history is pruned as part of the retention policy. There is no separate cleanup CLI. This policy is a local prototype convenience, not a compliance retention schedule or secure deletion guarantee. Other local database users should back up data they want to keep before continuing periodic runs.

## Verification and limitations

`tests/unit/test_replay_lab.py` covers schema rejection, malformed and oversized fixtures, duplicate identities/references, scenario isolation, reproducible rule results, evidence completeness, confusion-matrix cases, and undefined metrics. `tests/unit/test_private_telemetry.py` covers the additive migration and bounded retention while asserting audit rows remain. `tests/unit/test_scheduler.py` covers overlap, retries, timeouts, repeated start, idempotent processing, and shutdown.

All events are synthetic fixture records, all detections are deterministic examples, and all metrics are based on a tiny authored scenario set. The lab does not execute attacks, exploit code, malware, network requests, scans, LLM calls, or response actions. It does not establish vulnerability or security status for any real system.
