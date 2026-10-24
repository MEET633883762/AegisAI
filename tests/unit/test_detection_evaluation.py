from __future__ import annotations

import json
from pathlib import Path

import pytest

from platform_prototype.evaluation import (
    ConfusionCounts,
    EvaluationExecutionError,
    detector_config_fingerprint,
    _metrics,
    evaluate_dataset,
    report_json,
)
from platform_prototype.evaluation_dataset import load_evaluation_dataset_bytes
from private_api.telemetry import detect_findings
from scripts import run_detection_evaluation as cli

ROOT = Path(__file__).parents[2]
DATASET_PATH = ROOT / "platform_prototype" / "fixtures" / "evaluation_dataset_v1.json"


def _dataset():
    return load_evaluation_dataset_bytes(DATASET_PATH.read_bytes())


def test_hand_calculated_confusion_metrics_and_denominators():
    metrics = _metrics(ConfusionCounts(
        true_positives=8, false_positives=2, true_negatives=10, false_negatives=4,
    ))
    assert metrics.precision.value == 0.8
    assert metrics.precision.denominator == 10
    assert metrics.recall.value == 8 / 12
    assert metrics.recall.denominator == 12
    assert metrics.f1.value == 16 / 22
    assert metrics.f1.denominator == 22
    assert metrics.specificity.value == 10 / 12
    assert metrics.specificity.denominator == 12
    assert metrics.false_positive_rate.value == 2 / 12
    assert metrics.false_positive_rate.denominator == 12
    assert metrics.false_negative_rate.value == 4 / 12
    assert metrics.false_negative_rate.denominator == 12


def test_zero_denominators_are_explicitly_undefined():
    metrics = _metrics(ConfusionCounts(
        true_positives=0, false_positives=0, true_negatives=3, false_negatives=0,
    ))
    assert metrics.precision.value is metrics.recall.value is metrics.f1.value is None
    assert metrics.false_negative_rate.value is None
    assert metrics.specificity.value == 1
    assert metrics.specificity.denominator == 3
    assert metrics.false_positive_rate.value == 0
    assert metrics.precision.status == "undefined_zero_denominator"


def test_all_metrics_are_explicit_when_each_denominator_is_zero():
    metrics = _metrics(ConfusionCounts(
        true_positives=0, false_positives=0, true_negatives=0, false_negatives=0,
    ))
    assert all(getattr(metrics, name).value is None for name in (
        "precision", "recall", "f1", "specificity", "false_positive_rate", "false_negative_rate",
    ))
    assert all(getattr(metrics, name).denominator == 0 for name in (
        "precision", "recall", "f1", "specificity", "false_positive_rate", "false_negative_rate",
    ))
    assert all(getattr(metrics, name).status == "undefined_zero_denominator" for name in (
        "precision", "recall", "f1", "specificity", "false_positive_rate", "false_negative_rate",
    ))


def test_phase6a_dataset_evaluates_with_type_level_multi_rule_counts():
    report = evaluate_dataset(_dataset())
    assert report.valid_scenario_count == 15
    assert report.rejected_scenario_count == 4
    assert sum((report.counts.true_positives, report.counts.false_positives,
                report.counts.true_negatives, report.counts.false_negatives)) == 15 * 5
    assert all(item.status == "pass" for item in report.scenarios + report.rejected_inputs)
    assert all(item.actual_finding_types == item.expected_finding_types for item in report.scenarios)
    assert report.evidence_summary["missing_references"] == 0
    assert report.rejected_inputs and report.counts.true_negatives != report.rejected_scenario_count
    assert report.metrics.precision.denominator == 9
    assert report.metrics.recall.denominator == 9
    assert report.metrics.f1.denominator == 18
    assert report.metrics.false_positive_rate.denominator == 66
    assert report.metrics.false_negative_rate.denominator == 9
    assert sum(item.counts.true_positives + item.counts.false_positives +
               item.counts.true_negatives + item.counts.false_negatives for item in report.per_rule) == 75
    assert report.metrics.specificity.value == 1.0
    assert report.metrics.specificity.denominator == 66
    assert all(item.evaluated_rule_ids == sorted({row.rule_id for row in report.per_rule})
               for item in report.scenarios)
    assert all(item.technique_ids == [] for item in report.scenario_rule_mapping)
    assert report.technique_coverage == []
    assert [(item.technique_id, item.status) for item in report.untested_techniques] == [("T1110", "candidate_not_mapped")]
    assert report.coverage_status == "partial"
    assert report.warnings


def test_wrong_rule_type_counts_as_false_positive_and_false_negative():
    dataset = _dataset()
    scenario = next(item for item in dataset.scenarios if item.scenario_id == "p6a-independent-app-and-rate")
    isolated = dataset.model_copy(update={"scenarios": [scenario]})

    def wrong_type(events, *, tenant_id):
        findings = detect_findings(events, tenant_id=tenant_id)
        return [item.model_copy(update={"rule_id": "CONFIG-001"}) if item.rule_id == "WEB-001" else item
                for item in findings]

    report = evaluate_dataset(isolated, detector=wrong_type)
    assert report.counts.false_positives == 1
    assert report.counts.false_negatives == 1
    row = report.scenarios[0]
    assert row.missing_expected_types == ["WEB-001"]
    assert row.unexpected_types == ["CONFIG-001"]
    assert row.status == "fail"


def test_multiple_independent_events_and_duplicate_records_do_not_inflate_counts():
    dataset = _dataset()
    scenario = next(item for item in dataset.scenarios if item.scenario_id == "p6a-auth-exact-duplicate-replay")
    report = evaluate_dataset(dataset.model_copy(update={"scenarios": [scenario]}))
    row = report.scenarios[0]
    assert row.duplicate_event_count == 1
    assert report.counts.true_positives == 1
    assert report.counts.false_negatives == 0


def test_duplicate_findings_are_counted_once_and_diagnosed():
    dataset = _dataset()
    scenario = next(item for item in dataset.scenarios if item.scenario_id == "p6a-independent-app-and-rate")
    isolated = dataset.model_copy(update={"scenarios": [scenario]})

    def duplicate(events, *, tenant_id):
        findings = detect_findings(events, tenant_id=tenant_id)
        # Duplicate APP finding includes a fabricated reference and must not hide that evidence anomaly.
        duplicate_app = next(item for item in findings if item.rule_id == "APP-001").model_copy(
            update={"evidence_refs": ["synthetic-not-in-input"]},
        )
        wrong_type = findings[0].model_copy(update={"rule_id": "CONFIG-001"})
        return findings + [duplicate_app, wrong_type]

    report = evaluate_dataset(isolated, detector=duplicate)
    assert report.counts.true_positives == 2
    assert report.counts.false_positives == 1
    assert report.scenarios[0].duplicate_finding_count == 1
    assert report.scenarios[0].unexpected_types == ["CONFIG-001"]
    assert report.scenarios[0].unexpected_evidence == {"APP-001": ["synthetic-not-in-input"]}


def test_missing_and_unexpected_evidence_are_reported():
    dataset = _dataset()
    scenario = next(item for item in dataset.scenarios if item.scenario_id == "p6a-app-suspicious-code")
    isolated = dataset.model_copy(update={"scenarios": [scenario]})

    def bad_evidence(events, *, tenant_id):
        return [item.model_copy(update={"evidence_refs": ["synthetic-not-in-input"]})
                for item in detect_findings(events, tenant_id=tenant_id)]

    report = evaluate_dataset(isolated, detector=bad_evidence)
    row = report.scenarios[0]
    assert row.missing_evidence == {"APP-001": scenario.ground_truth.required_evidence[0].evidence_refs}
    assert row.unexpected_evidence == {"APP-001": ["synthetic-not-in-input"]}
    assert row.status == "fail"


def test_rejected_inputs_stay_out_of_all_confusion_matrix_counts():
    dataset = _dataset()
    rejected = [item for item in dataset.scenarios if item.ground_truth.expected_input_outcome == "reject"]
    report = evaluate_dataset(dataset.model_copy(update={"scenarios": rejected}))
    assert report.valid_scenario_count == 0
    assert report.rejected_scenario_count == len(rejected)
    assert report.counts == ConfusionCounts(
        true_positives=0, false_positives=0, true_negatives=0, false_negatives=0,
    )
    assert report.metrics.precision.value is None
    assert all(item.status == "pass" for item in report.rejected_inputs)


def test_ground_truth_never_enters_detector_inputs():
    dataset = _dataset()
    seen = []

    def spy(events, *, tenant_id):
        seen.extend(events)
        assert all(not hasattr(event, "ground_truth") for event in events)
        return detect_findings(events, tenant_id=tenant_id)

    evaluate_dataset(dataset, detector=spy)
    assert seen
    assert all("ground_truth" not in event.model_dump() for event in seen)


def test_report_json_and_fingerprints_are_deterministic():
    dataset = _dataset()
    first = report_json(evaluate_dataset(dataset))
    second = report_json(evaluate_dataset(dataset))
    assert first == second
    payload = json.loads(first)
    assert payload["dataset_sha256"] == evaluate_dataset(dataset).dataset_sha256
    assert payload["detector_config_sha256"] == evaluate_dataset(dataset).detector_config_sha256


def test_detector_configuration_fingerprint_tracks_threshold_configuration(monkeypatch):
    from private_api import telemetry

    before = detector_config_fingerprint()
    monkeypatch.setattr(telemetry, "REQUEST_RATE_THRESHOLD", telemetry.REQUEST_RATE_THRESHOLD + 1)
    assert detector_config_fingerprint() != before


def test_detector_failure_or_invalid_output_cannot_return_a_complete_report():
    dataset = _dataset()
    calls = 0

    def interrupted(events, *, tenant_id):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("internal detector detail")
        return detect_findings(events, tenant_id=tenant_id)

    with pytest.raises(EvaluationExecutionError, match="evaluation incomplete"):
        evaluate_dataset(dataset, detector=interrupted)

    with pytest.raises(EvaluationExecutionError, match="invalid result"):
        evaluate_dataset(dataset, detector=lambda events, *, tenant_id: ())


def test_evaluator_revalidates_duplicate_scenario_ids_and_fails_closed():
    dataset = _dataset()
    duplicate = dataset.model_copy(update={"scenarios": [dataset.scenarios[0], dataset.scenarios[0]]})
    with pytest.raises(EvaluationExecutionError, match="dataset validation failed"):
        evaluate_dataset(duplicate)


def test_cli_writes_to_fixed_location_refuses_overwrite_and_supports_stdout(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "DEFAULT_REPORT_PATH", tmp_path / "report.json")
    assert cli.main([]) == 0
    original = cli.DEFAULT_REPORT_PATH.read_bytes()
    assert cli.main([]) == 2
    assert cli.DEFAULT_REPORT_PATH.read_bytes() == original
    assert "not overwritten" in capsys.readouterr().err
    assert cli.main(["--stdout"]) == 0
    assert json.loads(capsys.readouterr().out)["dataset_version"] == "1.0"


def test_cli_rejects_arbitrary_output_path_argument():
    with pytest.raises(SystemExit):
        cli.main(["--report", "somewhere.json"])


def test_cli_history_is_opt_in_and_uses_temporary_store(tmp_path, monkeypatch, capsys):
    from platform_prototype.evaluation_history import read_evaluation_history

    history_path = tmp_path / "isolated-history.sqlite3"
    monkeypatch.setattr(cli, "DEFAULT_HISTORY_PATH", history_path)
    assert cli.main(["--stdout", "--record-history"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["schema_version"] == "1.1"
    latest, runs = read_evaluation_history(history_path)
    assert latest is not None and latest.dataset_sha256 == output["dataset_sha256"]
    assert len(runs) == 1 and runs[0].total_evaluated_pairs == 75

