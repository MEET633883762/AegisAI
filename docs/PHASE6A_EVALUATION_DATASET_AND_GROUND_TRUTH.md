# Phase 6A — Detection Evaluation Dataset and Ground Truth

## Scope

Phase 6A adds a versioned local benchmark fixture for the existing synthetic detection rules. It does not add an evaluator report, performance metrics, a public route, a database migration, or any frontend behavior. The fixture contains no real client data and is not evidence of security effectiveness.

## Dataset format and labels

The fixed file is `platform_prototype/fixtures/evaluation_dataset_v1.json`. It declares dataset ID `aegisai_synthetic_detection_evaluation`, schema and dataset version `1.0`, synthetic classification, and a synthetic-only label. Its 19 ordered scenarios include 8 accepted positive examples, 7 accepted benign/insufficient-evidence controls, and 4 inputs expected to be rejected.

Each scenario has a stable `p6a-...` ID, category, difficulty, description, and `detector_input` array. Its separate `ground_truth` object states whether input should be accepted or rejected; for rejected cases it names the expected validation/conflict category. It also partitions all five existing rule IDs—`AUTH-001`, `WEB-001`, `APP-001`, `VULN-001`, and `CONFIG-001`—into expected findings and expected absences. `required_evidence` associates expected rule IDs with exact evidence references.

Coverage includes existing suspicious patterns, benign codes, values at and adjacent to existing rule thresholds, an exact duplicate replay, insufficient evidence, two independent findings in one scenario, malformed/incomplete records, conflicting event IDs, and conflicting evidence references. The dataset adds no event type, finding type, or detection rule.

## Separation and validation

`detector_input` is validated using the existing `SyntheticTelemetryEvent` schema and `normalize_and_deduplicate`. `validate_detector_input` returns only normalized event models; it does not return or attach `ground_truth`. Strict event-model validation rejects unexpected label fields. Expected outputs were authored from the existing rule contracts before comparing the current detector behavior; loading/validating the dataset checks input acceptance or rejection only and does not call `detect_findings`.

The loader accepts bytes only up to 1 MiB. The schema bounds the library to 50 scenarios, 50 records per scenario, and 500 total records. It rejects unsupported versions, duplicate scenario IDs, unpartitioned or unsupported ground-truth rule labels, evidence references absent from the scenario input, and input examples whose actual schema/deduplication outcome disagrees with their declared acceptance/rejection category. Invalid examples remain raw JSON records only so the existing validator can reject them safely; they are never passed to detection.

Scenario array order and scenario IDs are stable. `dataset_fingerprint` hashes canonical JSON with sorted object keys and compact separators; array order remains meaningful. The digest therefore changes when events, labels, metadata, or scenario ordering changes, but not when JSON whitespace or object-key order changes.

## Tests

Run focused tests with:

```powershell
python -m pytest -q -p no:cacheprovider tests/unit/test_evaluation_dataset.py
```

The tests cover versions, size limits, unique IDs, complete positive/negative rule labels, evidence references, stable IDs/fingerprints, expected positive and benign behavior, threshold boundaries, exact duplicates, insufficient evidence, malformed/conflicting inputs, detector-input isolation, and the unchanged supported rule set/threshold constants.

## What this dataset can establish

It can establish that the fixture is bounded and internally consistent, that its invalid examples reach the declared input-validation failure category, and that selected hand-authored examples exercise existing behavior with the stated evidence references. It cannot establish detection accuracy on real systems, representative prevalence, statistical confidence, operational false-positive rates, or resistance to adversarial evasion. Phase 6A does not publish aggregate accuracy metrics.

## Next step: Phase 6B

Phase 6B may add a separate deterministic evaluator that runs accepted scenarios in isolation, compares observed findings/evidence to this independent ground truth, and reports bounded per-rule confusion counts and evidence completeness. Rejected inputs should be measured as validation outcomes, not detection misses. Phase 6B must not tune rules to fit the fixture and should retain the small-sample limitations in every report.
