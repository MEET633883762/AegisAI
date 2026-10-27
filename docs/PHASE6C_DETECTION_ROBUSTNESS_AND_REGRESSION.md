# Phase 6C — Detection Robustness and Regression

> Current setup: use Python 3.11 from the [development guide](DEVELOPMENT.md). PowerShell examples run from the repository root with `.\.venv\Scripts\python.exe`; on Linux use `.venv/bin/python`. Phase-specific verification counts are historical; see [current status](CURRENT_STATUS.md) for fresh checks.

## Audit of the Phase 6B report

The saved Phase 6B report was checked against the evaluator and the fixed Phase 6A labels. There are 15 accepted scenarios and five supported rule types, so the counting unit yields 75 scenario-rule pairs. The 9 expected positive labels map to 9 TP and the other 66 pairs to 66 TN. No rejected scenario enters those counts. Per-rule counts are APP-001 2 TP/13 TN, AUTH-001 2/13, CONFIG-001 1/14, VULN-001 1/14, and WEB-001 3/12; all current false-positive and false-negative counts are zero for these authored cases.

The report's metric denominators are consistent with its formulas: precision 9 (TP+FP), recall 9 (TP+FN), F1 18 (2TP+FP+FN), false-positive rate 66 (FP+TN), and false-negative rate 9 (FN+TP). The counts are a deterministic fixture regression result, not an estimate of detection performance.

Ground-truth expected rule IDs are a separately authored partition in `ground_truth`; `validate_detector_input` creates telemetry event models from `detector_input` only. The evaluator passes only those event models to `detect_findings`. The dataset loader validates expected input acceptance/rejection using schema and deduplication validation, but does not execute detection to validate finding labels.

The evaluator loops through every supported rule for every accepted scenario. Wrong finding types are in the observed set and therefore add an FP for that type while a missing expected type adds an FN. Rejected scenarios are validated and listed separately. Exact duplicate event records pass through the existing normalizer and do not inflate detector findings. Same-rule duplicate findings do not create extra TP counts.

### Defect found and correction

During audit, `_unique_findings` retained only the first finding for each rule before examining evidence. This kept confusion counts binary as intended, but could discard later evidence from a duplicate finding and hide an unsupported evidence reference. The evaluator now merges evidence references for duplicate findings of the same rule before evidence diagnostics while still counting the rule only once. A regression test combines duplicate output, an unsupported reference, and an unexpected rule type; it verifies the FP and evidence anomaly remain visible.

The evaluator now revalidates the dataset model before execution and rejects duplicate scenario IDs even if a caller constructs a model with an unchecked copy. Detector exceptions or invalid output raise a safe incomplete-evaluation error; no partial report is returned. Regression tests cover both paths.

## Versioned robustness behavior suite

`tests/unit/test_detection_robustness.py` defines behavior suite version `1.0`. Each test names a case, lists the explicit expected supported rule IDs, and reports the case ID, expected set, and actual set on mismatch. The suite exercises:

- Request-count boundary: 99 / 100 / 101 against the existing threshold.
- Request-window boundary: 59 / 60 / 61 seconds.
- Authentication failure count: 2 / 3 / 4, plus the ten-minute correlation boundary and one second beyond it.
- Noisy benign routine activity, safe errors, HTTP access, and unrelated authentication evidence alongside one expected rate finding.
- Out-of-order event records with chronological timestamps and a success at the existing follow-up boundary.
- Exact duplicate collapse; conflicting event IDs and evidence references rejected by the existing normalizer.
- Missing, contradictory, and unknown fields rejected by the existing Pydantic event schema.
- Two independent findings in one event set with evidence checked per finding type.
- Wrong and duplicate finding outputs, missing/unsupported evidence, and interrupted detector execution in evaluator tests.

The Phase 6A dataset remains version 1.0 and its ground truth is unchanged. This Phase 6C behavior suite is separate test code with explicit expected outcomes; it does not overwrite Phase 6B's saved report. Detection rules and thresholds were not changed.

## Reproducibility and fingerprint scope

The evaluation report has no timestamp or random run ID. Dataset fingerprinting uses canonical validated dataset content (including ground-truth labels); its JSON object key order and whitespace do not affect the hash, but scenario/event array order remains meaningful input. The detector configuration fingerprint includes supported rule IDs, rule version, event-type mapping, and explicit rate/authentication thresholds and windows. It is a configuration fingerprint, not a source-code hash: changes to hard-coded rule implementation or allowlisted activity/check values that do not update those exposed configuration fields may not change that fingerprint. This is a known blind spot.

The report serializer and scenario sizes are bounded. The local CLI reads only the fixed fixture and creates the default `results/evaluation/` report with exclusive-create semantics or prints it with `--stdout`. Its later `--record-history` option stores bounded history in a separate fixed local database; it does not call the application tenant database. Current schema 1.1 metadata and history are documented in the [Detection Lab extension](DETECTION_ENGINEERING_AND_EVALUATION.md). A failure during any scenario produces no report object. Exact duplicate report output may use platform-specific stdout line endings; parsed JSON is stable.

## Tests and limitations

Run from the repository root:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/unit/test_evaluation_dataset.py tests/unit/test_detection_evaluation.py tests/unit/test_detection_robustness.py
.\.venv\Scripts\python.exe -m pytest -q
```

The checks show that the existing rules behave as expected for these synthetic examples. They do not prove that the rules are complete, calibrated, robust to real telemetry, or effective against real attacks. The suite is small, hand-authored, and limited to existing event and rule types. Its outcomes must not be used as production accuracy claims or as automatic rule-tuning targets.

### Historical Phase 6C verification

- `python -m pytest -q -p no:cacheprovider tests/unit/test_evaluation_dataset.py tests/unit/test_detection_evaluation.py tests/unit/test_detection_robustness.py` — 43 passed.
- `python -m pytest -q -p no:cacheprovider` — 346 passed.
- `npm.cmd test` from `frontend/` — passed TypeScript checking, Vite production build, 20 Vitest tests, and 3 Node static-release tests.
- `python -m compileall -q private_api platform_prototype scripts tests` — passed.
- Static publisher verification — exact 9-file allowlist passed; no evaluation dataset or report was published.
- `git diff --check` — passed; Git emitted only existing LF-to-CRLF conversion warnings.

The ignored SQLite database and original assessment reports were not accessed. No schema migration was needed.
