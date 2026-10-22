from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from platform_prototype.replay import (
    MAX_SCENARIO_LIBRARY_BYTES,
    ReplayInputError,
    ReplayScenarioLibrary,
    evaluate_scenario_library,
    library_fingerprint,
    load_scenario_library_bytes,
)
from scripts.run_replay_lab import main as replay_cli_main

ROOT = Path(__file__).parents[2]
LIBRARY_PATH = ROOT / "platform_prototype" / "fixtures" / "replay_scenarios_v1.json"
MALFORMED_PATH = ROOT / "platform_prototype" / "fixtures" / "replay_scenarios_malformed_v1.json"
FIXED_START = datetime(2026, 10, 22, 10, tzinfo=timezone.utc)
FIXED_FINISH = datetime(2026, 10, 22, 10, 0, 1, tzinfo=timezone.utc)


def _library() -> ReplayScenarioLibrary:
    return load_scenario_library_bytes(LIBRARY_PATH.read_bytes())


def _evaluate(library: ReplayScenarioLibrary, replay_id: str = "replay-0000000000000001"):
    return evaluate_scenario_library(library, replay_id=replay_id,
                                     started_at=FIXED_START, finished_at=FIXED_FINISH)


def test_reviewed_library_is_synthetic_and_detects_each_existing_rule():
    library = _library()
    report = _evaluate(library)
    assert len(library.scenarios) == 10
    assert report.positive_scenario_count == report.benign_scenario_count == 5
    assert report.rule_ids == ["APP-001", "AUTH-001", "CONFIG-001", "VULN-001", "WEB-001"]
    assert report.counts.true_positives == 5
    assert report.counts.false_positives == report.counts.false_negatives == 0
    assert report.counts.true_negatives == 45
    assert report.counts.precision == report.counts.recall == report.counts.f1 == 1.0
    assert report.scenario_detection_coverage == report.evidence_completeness == 1.0
    assert all(item.rule_version == "1.0" for row in report.scenarios for item in row.findings)
    assert all(row.evidence_complete is True for row in report.scenarios if row.scenario_class == "positive")
    assert all(not row.observed_rule_ids for row in report.scenarios if row.scenario_class == "benign")
    assert report.recommendations == []


def test_replay_core_is_reproducible_but_each_run_id_is_unique():
    library = _library()
    first = _evaluate(library, "replay-0000000000000001")
    second = _evaluate(library, "replay-0000000000000002")
    assert first.replay_id != second.replay_id
    assert first.library_sha256 == library_fingerprint(library) == second.library_sha256
    assert first.scenarios == second.scenarios
    assert first.counts == second.counts
    assert first.per_rule == second.per_rule


def test_malformed_oversized_and_duplicate_scenario_library_are_rejected():
    with pytest.raises(ReplayInputError, match="validation failed"):
        load_scenario_library_bytes(MALFORMED_PATH.read_bytes())
    with pytest.raises(ReplayInputError, match="1 MiB"):
        load_scenario_library_bytes(b" " * (MAX_SCENARIO_LIBRARY_BYTES + 1))
    payload = json.loads(LIBRARY_PATH.read_bytes())
    payload["scenarios"].append(payload["scenarios"][0])
    with pytest.raises(ReplayInputError, match="validation failed"):
        load_scenario_library_bytes(json.dumps(payload).encode())


@pytest.mark.parametrize("mutation", [
    lambda data: data["scenarios"][0].update(description="x" * 301),
    lambda data: data["scenarios"][0]["events"][0].update(actor_ref="synthetic-" + "x" * 100),
    lambda data: data["scenarios"][0]["events"][1].update(event_id=data["scenarios"][0]["events"][0]["event_id"]),
    lambda data: data["scenarios"][0]["events"][1].update(evidence_ref=data["scenarios"][0]["events"][0]["evidence_ref"]),
    lambda data: data["scenarios"][0]["events"].extend(data["scenarios"][0]["events"] * 30),
])
def test_oversized_fields_event_counts_and_ambiguous_source_references_are_rejected(mutation):
    payload = json.loads(LIBRARY_PATH.read_bytes())
    mutation(payload)
    with pytest.raises(ReplayInputError):
        load_scenario_library_bytes(json.dumps(payload).encode())


@pytest.mark.parametrize("mutation", [
    lambda data: data["scenarios"][0].update(scenario_version="9.0"),
    lambda data: data["scenarios"][0]["events"][0].update(token="secret"),
    lambda data: data["scenarios"][0]["expected_evidence_refs"].append("synthetic-not-in-input"),
    lambda data: data["scenarios"][0].update(expected_rule_ids=["UNKNOWN-999"]),
    lambda data: data["scenarios"][0]["events"][0].update(occurred_at="2026-10-22T09:00:00"),
])
def test_scenario_validation_rejects_bad_schema_secrets_and_ambiguous_evidence(mutation):
    payload = json.loads(LIBRARY_PATH.read_bytes())
    mutation(payload)
    with pytest.raises(ReplayInputError):
        load_scenario_library_bytes(json.dumps(payload).encode())


def test_scenario_boundaries_prevent_cross_scenario_auth_correlation():
    library = _library()
    source = library.scenarios[5]
    second_event = source.events[1].model_copy(update={
        "event_id": "syn-replay-isolation-03",
        "evidence_ref": "synthetic-replay-isolation-03",
        "occurred_at": source.events[1].occurred_at,
    })
    second = source.model_copy(update={
        "scenario_id": "scenario-auth-benign-single-failure",
        "description": "One isolated authentication failure control.",
        "events": [second_event],
        "rationale": "A single event in this isolated scenario is below the authentication rule threshold.",
    })
    isolated = ReplayScenarioLibrary.model_validate(library.model_copy(update={
        "scenarios": [source, second],
    }).model_dump(mode="python"))
    result = _evaluate(isolated)
    assert all(not row.findings for row in result.scenarios)
    assert result.counts.true_negatives == 10


def _request_library(request_count: int, *, expected: bool) -> ReplayScenarioLibrary:
    payload = json.loads(LIBRARY_PATH.read_bytes())
    scenario = payload["scenarios"][1]
    scenario["scenario_id"] = "scenario-web-negative-control" if not expected else "scenario-web-under-threshold"
    scenario["scenario_class"] = "positive" if expected else "benign"
    scenario["events"][0]["request_count"] = request_count
    if expected:
        scenario["expected_rule_ids"] = ["WEB-001"]
        scenario["expected_evidence_refs"] = [scenario["events"][0]["evidence_ref"]]
        scenario["rationale"] = "This labeled challenge expects a rate finding despite the below-threshold input to expose a detection gap."
    else:
        scenario["expected_rule_ids"] = []
        scenario["expected_evidence_refs"] = []
        scenario["rationale"] = "A benign synthetic rate control should not produce an unexpected rule match."
    payload.update(scenarios=[scenario])
    return load_scenario_library_bytes(json.dumps(payload).encode())


def test_confusion_matrix_and_gap_recommendations_for_miss_and_false_alert():
    missed = _evaluate(_request_library(40, expected=True), "replay-0000000000000003")
    assert missed.counts.false_negatives == 1
    assert missed.missed_detections == [{"scenario_id": "scenario-web-under-threshold", "rule_id": "WEB-001"}]
    assert missed.recommendations[0].gap_type == "missed_detection"
    unexpected = _evaluate(_request_library(150, expected=False), "replay-0000000000000004")
    assert unexpected.counts.false_positives == 1
    assert unexpected.unexpected_alerts == [{"scenario_id": "scenario-web-negative-control", "rule_id": "WEB-001"}]
    assert unexpected.recommendations[0].gap_type == "unexpected_alert"


def test_missing_expected_evidence_is_reported_as_a_gap():
    payload = json.loads(LIBRARY_PATH.read_bytes())
    scenario = payload["scenarios"][1]
    scenario["events"].append({
        "event_id": "syn-replay-web-unrelated-auth",
        "occurred_at": "2026-10-22T09:10:30Z",
        "event_type": "auth_success",
        "asset_ref": "synthetic-web-a",
        "actor_ref": "synthetic-actor-a",
        "source_ref": "synthetic-source-rate",
        "evidence_ref": "synthetic-replay-web-unrelated-auth",
    })
    scenario["expected_evidence_refs"] = ["synthetic-replay-web-unrelated-auth"]
    library = load_scenario_library_bytes(json.dumps({**payload, "scenarios": [scenario]}).encode())
    report = _evaluate(library, "replay-0000000000000006")
    assert report.evidence_completeness == 0.0
    assert report.scenarios[0].evidence_complete is False
    assert report.recommendations[0].gap_type == "missing_evidence"


def test_zero_denominator_metrics_are_null_not_zero_or_one():
    library = _request_library(40, expected=False)
    report = _evaluate(library, "replay-0000000000000005")
    web = next(item for item in report.per_rule if item.rule_id == "WEB-001")
    assert web.true_negatives == 1
    assert web.precision is web.recall is web.f1 is None
    assert report.scenario_detection_coverage is None
    assert report.evidence_completeness is None


def test_cli_writes_only_new_report_paths(tmp_path, capsys):
    output = tmp_path / "report.json"
    assert replay_cli_main(["--report", str(output)]) == 0
    parsed = json.loads(output.read_text(encoding="utf-8"))
    assert parsed["data_classification"] == "synthetic"
    original = output.read_bytes()
    assert replay_cli_main(["--report", str(output)]) == 2
    assert output.read_bytes() == original
    assert "already exists" in capsys.readouterr().err
