# Phase 6B — Detection Metrics and Evaluation

## Scope and counting unit

Phase 6B evaluates the fixed Phase 6A synthetic dataset with the existing local detector. It does not change detection rules, persist benchmark records in the application database, or connect to public endpoints, external systems, or the Controller. The deterministic report is written by default to `results/evaluation/phase6b_detection_evaluation_v1.json`; the CLI refuses to overwrite an existing file. `--stdout` prints the same report without creating a file.

The counting unit is **one accepted scenario × one supported rule type**, with five pairs per accepted scenario. For each pair, the expected label is whether that rule is in the scenario's complete Phase 6A expected-finding partition, and the observed label is whether the existing detector emitted that rule at least once. Thus a wrong rule type produces a false positive for the unexpected rule and a false negative for the missed expected rule. Repeated findings of the same type do not add counts. Exact duplicate events are normalized and deduplicated by the existing input path before detection.

## Metrics and zero denominators

The report includes aggregate and per-rule TP, FP, TN, and FN counts, with these formulas:

- Precision = TP / (TP + FP)
- Recall = TP / (TP + FN)
- F1 = 2 × TP / (2 × TP + FP + FN)
- False-positive rate = FP / (FP + TN)
- False-negative rate = FN / (FN + TP)

Every metric stores its denominator and a status. A zero denominator yields `value: null` and `undefined_zero_denominator`; it is not represented as 0 or 1. The report also provides per-scenario expected and actual finding types, missing and unexpected types, required and observed evidence references, missing or unsupported evidence, duplicate counts, pass/fail, and reason codes.

Evidence completeness is reported as reference counts: expected, present, missing, and unexpected. A required reference is present when the corresponding expected rule's finding includes it. An unexpected evidence reference is one the detector emitted that is absent from the validated scenario input. Additional valid input evidence is not classified as unexpected merely because it was not marked required.

## Invalid inputs

Phase 6A scenarios labeled for rejection are passed through the same event-schema and normalization/deduplication validation path, but never to detection. Their expected and observed rejection categories and diagnostic status are reported under `rejected_inputs`. They do not contribute TP, FP, TN, FN, or any metric denominator. This prevents an empty finding set for malformed data from being counted as a true negative.

## Reproducibility and report schema

The JSON report schema is version `1.0`. It includes the Phase 6A dataset ID/version and canonical dataset SHA-256 fingerprint. It also fingerprints a canonical configuration record containing the supported rule IDs, rule version, rule-to-event mapping, and the explicit rate/authentication thresholds and time windows used by the existing detector. This is a configuration fingerprint, not a hash of every implementation byte; code changes that do not update exposed configuration/version values may not change it.

Scenario order and list ordering are deterministic. No run timestamp, random identifier, tenant value, or persisted database state enters the report. The report is bounded to 1 MiB. The CLI reads only the fixed checked-in Phase 6A fixture and offers no user-controlled input/output path.

## Commands

From the repository root:

```powershell
python scripts/run_detection_evaluation.py
python scripts/run_detection_evaluation.py --stdout
python -m pytest -q -p no:cacheprovider tests/unit/test_evaluation_dataset.py tests/unit/test_detection_evaluation.py
```

The default command creates a new report file and exits without overwriting if it already exists. To retain the report, copy it to a separately named review artifact; do not overwrite original assessment evidence.

## Interpretation and limitations

The report evaluates a small, explicitly authored synthetic suite against current rules. It is useful for reproducibility, detecting regressions in these examples, and inspecting evidence behavior. It does not estimate real-world detection accuracy, false-alarm rates, operational effectiveness, or customer risk. The current perfect score on this fixture, where observed, is not evidence of production quality. Ground truth is manually authored and independent of each evaluator run but still reflects a small scenario design. Do not tune rules automatically from this report or present the metrics as a security guarantee.

## Next step: Phase 6C

Phase 6C can review benchmark coverage and add a separately approved, independently authored synthetic dataset or review workflow. Any expansion should version the dataset, preserve label/detector separation, include negative and boundary controls, and document provenance before interpreting aggregate metrics. Do not add real-client telemetry without a separate privacy, authorization, and data-governance decision.
