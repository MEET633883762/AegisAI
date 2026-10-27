# Detection engineering and evaluation extension

> Current setup: use Python 3.11 from the [development guide](DEVELOPMENT.md). PowerShell examples run from the repository root with `.\.venv\Scripts\python.exe`; on Linux use `.venv/bin/python`. Phase-specific verification counts are historical; see [current status](CURRENT_STATUS.md) for fresh checks.

This change extends the existing Phase 6 Detection Lab. It does not add a second detector or change any detection rule or threshold.

## Dataset, labels, and counting

The versioned Phase 6A dataset remains the source of the synthetic test events and independently authored expected labels. The evaluator validates the dataset, then sends only normalized event models to the existing detector. Ground-truth labels are read separately after detection. Accepted scenarios are evaluated against every supported rule, so the counting unit is one accepted-scenario by supported-rule pair. Rejected inputs are reported as validation outcomes and excluded from all confusion-matrix denominators. Duplicate findings are collapsed by rule before binary counts; missing and unexpected evidence remain visible in scenario diagnostics.

The 1.1 report adds aggregate and per-rule specificity alongside precision, recall, F1, false-positive rate, and false-negative rate. Every metric stores its denominator. A zero denominator produces `value: null` and `undefined_zero_denominator`; it is never replaced with zero. The report fingerprints the dataset and detector configuration and records the dataset, rule, scenario-rule mapping, and ATT&CK mapping catalog versions.

`scenario_rule_mapping` explicitly lists expected, evaluated, and observed rule IDs and the scenario result. `rule_event_mapping` documents each supported rule's existing event-type scope. This documents evaluation coverage without putting expected labels into detector input.

## ATT&CK scope and evaluation gaps

No Phase 6A scenario is directly mapped to an ATT&CK technique. The data is synthetic rule-test input, not adversary emulation. In particular, `T1110` (Brute Force) is listed as an untested candidate: the synthetic records represent authentication failures but do not establish systematic password guessing, credential use, or hash cracking. MITRE describes T1110 in terms of repeated/systematic password guessing or cracking; an `auth_failure` event by itself does not prove that behavior ([MITRE ATT&CK T1110](https://attack.mitre.org/techniques/T1110/)). Thus the report's technique coverage is empty and coverage status is partial. The dashboard shows this gap instead of claiming unsupported technique coverage.

## Historical runs

History is opt-in and stored in a separate local file at `.aegisai-local/detection_evaluation_history.sqlite3`; it is not the application tenant database and no application database migration is involved. The file is created only when the operator invokes the evaluator with `--record-history`. It stores the bounded report, generated UTC time, run ID, and report hash. At most 20 runs are retained. Comparisons use the immediately previous retained report and list scenario IDs newly marked failing or resolved. Run timestamps/IDs are history metadata; the benchmark report itself remains deterministic.

The existing authenticated `GET /api/evaluation/reports/latest` route continues to require `reports:read`. It reads the latest optional history report and a bounded history summary from the fixed local path when the API process starts; if no history exists, it falls back to the existing fixed JSON report. It does not run evaluation. Restart the private API after recording runs so its startup snapshot reloads. The dashboard receives aggregate metrics and an explicit synthetic scenario/rule coverage summary, not raw event inputs. Expected and observed rule IDs remain separate fields.

Run a new report to stdout and record it in history with:

```powershell
.\.venv\Scripts\python.exe scripts/run_detection_evaluation.py --stdout --record-history
```

The normal `--stdout` and default report-file behavior remain unchanged when `--record-history` is omitted. Evaluation/history tests use temporary SQLite files only.

## Interpretation and limits

The current data contains 15 accepted scenarios and is hand-authored synthetic data. Warnings are included in each new report. These metrics are deterministic regression measurements for this narrow fixture; they are not statistical estimates, production-control measurements, or real-world detection accuracy. The source rules and ground-truth labels were not changed to improve benchmark results. No machine learning or autonomous AI is used by this evaluator.

Legacy schema 1.0 reports remain readable. The API derives specificity from their stored confusion counts, but reports created before explicit mapping metadata have `legacy_unavailable` coverage and do not acquire invented scenario or technique mappings. To produce a full 1.1 report and history summary, run the opt-in command above.

Focused verification commands:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/unit/test_evaluation_dataset.py tests/unit/test_detection_evaluation.py tests/unit/test_detection_robustness.py tests/unit/test_evaluation_history.py tests/unit/test_detection_evaluation_api.py
cd frontend
npm.cmd test
```
