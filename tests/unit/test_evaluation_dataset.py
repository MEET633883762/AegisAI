from __future__ import annotations

import json
from pathlib import Path

import pytest

import private_api.telemetry as rules
from platform_prototype.evaluation_dataset import (
    MAX_EVALUATION_DATASET_BYTES,
    EvaluationDatasetError,
    dataset_fingerprint,
    load_evaluation_dataset_bytes,
    validate_detector_input,
)
from platform_prototype.replay import SUPPORTED_RULE_IDS
from private_api.telemetry import detect_findings

ROOT = Path(__file__).parents[2]
DATASET_PATH = ROOT / "platform_prototype" / "fixtures" / "evaluation_dataset_v1.json"
EXPECTED_ORDER = [
    "p6a-auth-at-window-boundary",
    "p6a-auth-two-failure-control",
    "p6a-rate-exact-threshold",
    "p6a-rate-one-below-threshold",
    "p6a-rate-high-threshold",
    "p6a-rate-window-over-limit",
    "p6a-app-suspicious-code",
    "p6a-app-routine-read-control",
    "p6a-vulnerability-outdated-check",
    "p6a-vulnerability-current-control",
    "p6a-config-debug-enabled",
    "p6a-config-debug-disabled-control",
    "p6a-auth-exact-duplicate-replay",
    "p6a-auth-insufficient-evidence",
    "p6a-independent-app-and-rate",
    "p6a-reject-unknown-event-type",
    "p6a-reject-incomplete-event",
    "p6a-reject-conflicting-event-id",
    "p6a-reject-conflicting-evidence-ref",
]
SUPPORTED = ["APP-001", "AUTH-001", "CONFIG-001", "VULN-001", "WEB-001"]


def _raw() -> dict:
    return json.loads(DATASET_PATH.read_text(encoding="utf-8"))


def _load(payload: dict | None = None):
    return load_evaluation_dataset_bytes(json.dumps(payload or _raw()).encode("utf-8"))


def test_dataset_schema_version_order_balance_and_ground_truth_partition():
    dataset = _load()
    assert dataset.schema_version == dataset.dataset_version == "1.0"
    assert [item.scenario_id for item in dataset.scenarios] == EXPECTED_ORDER
    accepted = [item for item in dataset.scenarios if item.ground_truth.expected_input_outcome == "accept"]
    rejected = [item for item in dataset.scenarios if item.ground_truth.expected_input_outcome == "reject"]
    positive = [item for item in accepted if item.ground_truth.expected_finding_types]
    benign = [item for item in accepted if not item.ground_truth.expected_finding_types]
    assert (len(positive), len(benign), len(rejected)) == (8, 7, 4)
    assert all(
        set(item.ground_truth.expected_finding_types + item.ground_truth.expected_no_finding_types) == set(SUPPORTED)
        for item in dataset.scenarios
    )


def test_dataset_ids_and_fingerprint_are_stable_and_canonical():
    raw = DATASET_PATH.read_bytes()
    first = load_evaluation_dataset_bytes(raw)
    reserialized = json.dumps(json.loads(raw), sort_keys=True, indent=2).encode("utf-8")
    second = load_evaluation_dataset_bytes(reserialized)
    assert [item.scenario_id for item in first.scenarios] == [item.scenario_id for item in second.scenarios]
    assert dataset_fingerprint(first) == dataset_fingerprint(second)
    assert len(dataset_fingerprint(first)) == 64


@pytest.mark.parametrize("mutation", [
    lambda data: data.update(schema_version="9.0"),
    lambda data: data["scenarios"][0].update(scenario_id="p6a-invalid ID"),
    lambda data: data["scenarios"].append(data["scenarios"][0]),
    lambda data: data["scenarios"][0]["ground_truth"].update(expected_finding_types=["UNKNOWN-999"]),
    lambda data: data["scenarios"][0]["ground_truth"]["required_evidence"][0]["evidence_refs"].append(
        "synthetic-not-in-input"),
    lambda data: data["scenarios"][0]["ground_truth"].update(expected_no_finding_types=[]),
])
def test_unsupported_versions_duplicate_scenario_ids_and_bad_labels_are_rejected(mutation):
    payload = _raw()
    mutation(payload)
    with pytest.raises(EvaluationDatasetError, match="validation failed"):
        _load(payload)


def test_dataset_size_is_bounded_before_json_validation():
    with pytest.raises(EvaluationDatasetError, match="1 MiB"):
        load_evaluation_dataset_bytes(b" " * (MAX_EVALUATION_DATASET_BYTES + 1))


def test_event_and_evidence_identifiers_cannot_be_reused_across_scenarios():
    payload = _raw()
    payload["scenarios"][1]["detector_input"] = [payload["scenarios"][0]["detector_input"][0]]
    with pytest.raises(EvaluationDatasetError, match="validation failed"):
        _load(payload)


def test_positive_benign_boundary_duplicate_and_insufficient_evidence_cases():
    dataset = _load()
    by_id = {item.scenario_id: item for item in dataset.scenarios}
    expectations = {
        "p6a-auth-at-window-boundary": {"AUTH-001"},
        "p6a-auth-two-failure-control": set(),
        "p6a-rate-exact-threshold": {"WEB-001"},
        "p6a-rate-one-below-threshold": set(),
        "p6a-rate-high-threshold": {"WEB-001"},
        "p6a-rate-window-over-limit": set(),
        "p6a-app-suspicious-code": {"APP-001"},
        "p6a-app-routine-read-control": set(),
        "p6a-vulnerability-outdated-check": {"VULN-001"},
        "p6a-vulnerability-current-control": set(),
        "p6a-config-debug-enabled": {"CONFIG-001"},
        "p6a-config-debug-disabled-control": set(),
        "p6a-auth-exact-duplicate-replay": {"AUTH-001"},
        "p6a-auth-insufficient-evidence": set(),
        "p6a-independent-app-and-rate": {"APP-001", "WEB-001"},
    }
    for index, (scenario_id, expected) in enumerate(expectations.items()):
        scenario = by_id[scenario_id]
        records = validate_detector_input(scenario)
        observed = {finding.rule_id for finding in detect_findings(
            records, tenant_id=f"synthetic-org-eval-{index}",
        )}
        assert observed == expected
        assert set(scenario.ground_truth.expected_finding_types) == expected
        assert all("ground_truth" not in record.model_dump() for record in records)
        findings_by_rule = {finding.rule_id: set(finding.evidence_refs) for finding in detect_findings(
            records, tenant_id=f"synthetic-org-eval-evidence-{index}",
        )}
        for requirement in scenario.ground_truth.required_evidence:
            assert set(requirement.evidence_refs).issubset(findings_by_rule[requirement.rule_id])


def test_invalid_input_scenarios_are_rejected_before_detector_invocation():
    dataset = _load()
    rejected = [item for item in dataset.scenarios if item.ground_truth.expected_input_outcome == "reject"]
    assert len(rejected) == 4
    for scenario in rejected:
        with pytest.raises(EvaluationDatasetError, match="labeled for safe rejection"):
            validate_detector_input(scenario)
        assert scenario.ground_truth.expected_finding_types == []


def test_existing_detection_rule_thresholds_and_version_are_unchanged():
    assert rules.RULE_VERSION == "1.0"
    assert rules.REQUEST_RATE_THRESHOLD == 100
    assert rules.REQUEST_RATE_WINDOW_SECONDS == 60
    assert set(SUPPORTED_RULE_IDS) == set(SUPPORTED)
