from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from platform_prototype.models import ActionRequest, Finding, Severity, SyntheticEventBatch
from platform_prototype.pipeline import MAX_INPUT_BYTES, PrototypeInputError, analyze_bytes, load_batch_bytes

FIXTURE = Path(__file__).parents[2] / "platform_prototype" / "fixtures" / "synthetic_events_v1.json"
FIXTURE_BYTES = FIXTURE.read_bytes()


def _payload() -> dict:
    return json.loads(FIXTURE_BYTES)


def _report(**kwargs):
    return analyze_bytes(FIXTURE_BYTES, generated_at=datetime(2026, 10, 22, tzinfo=timezone.utc), **kwargs)


def test_fixture_builds_explainable_synthetic_report_with_dedup_and_evidence():
    report = _report()
    assert report.label == "SYNTHETIC - NOT REAL CLIENT DATA"
    assert (report.input_event_count, report.unique_event_count, report.duplicate_event_count) == (9, 8, 1)
    assert len(report.findings) == 2
    success_finding = next(finding for finding in report.findings if len(finding.signal_types) == 2)
    burst_finding = next(finding for finding in report.findings if len(finding.signal_types) == 1)
    assert success_finding.severity is Severity.HIGH
    assert success_finding.confidence == 0.9
    assert len(success_finding.evidence_refs) == 5
    assert burst_finding.severity is Severity.MEDIUM
    assert burst_finding.confidence == 0.7
    assert all(finding.confidence_factors and finding.recommendation for finding in report.findings)
    assert all(item.occurred_at_utc.utcoffset().total_seconds() == 0 for item in report.evidence_catalog)
    assert len({item.evidence_ref for item in report.evidence_catalog}) == report.unique_event_count


@pytest.mark.parametrize("raw", [b"{", b"[]", b"null", b"not json"])
def test_malformed_json_is_rejected_without_echoing_input(raw):
    with pytest.raises(PrototypeInputError, match="schema validation"):
        load_batch_bytes(raw)


def test_missing_required_fields_and_unsupported_schema_are_rejected():
    missing = _payload()
    del missing["events"][0]["evidence_ref"]
    with pytest.raises(PrototypeInputError):
        load_batch_bytes(json.dumps(missing).encode())
    unsupported = _payload()
    unsupported["schema_version"] = "9.0"
    with pytest.raises(PrototypeInputError):
        load_batch_bytes(json.dumps(unsupported).encode())


def test_real_classification_and_naive_timestamps_are_rejected():
    real = _payload()
    real["data_classification"] = "real"
    with pytest.raises(PrototypeInputError):
        load_batch_bytes(json.dumps(real).encode())
    naive = _payload()
    naive["events"][0]["occurred_at"] = "2026-10-22T10:00:00"
    with pytest.raises(PrototypeInputError):
        load_batch_bytes(json.dumps(naive).encode())


def test_oversized_input_is_rejected_at_byte_limit():
    with pytest.raises(PrototypeInputError, match="1 MiB"):
        load_batch_bytes(b" " * (MAX_INPUT_BYTES + 1))


def test_exact_duplicate_collapses_but_conflicting_duplicate_id_is_rejected():
    payload = _payload()
    batch = SyntheticEventBatch.model_validate(payload)
    report = _report()
    assert report.duplicate_event_count == 1
    payload["events"][-1]["source_ref"] = "synthetic-different-source"
    batch_bytes = json.dumps(payload).encode()
    with pytest.raises(PrototypeInputError, match="conflicting duplicate"):
        analyze_bytes(batch_bytes)
    assert batch.events[-1].event_id == "syn-auth-008"


def test_evidence_reference_cannot_be_ambiguous_across_events():
    payload = _payload()
    payload["events"][1]["evidence_ref"] = payload["events"][0]["evidence_ref"]
    with pytest.raises(PrototypeInputError, match="multiple event IDs"):
        analyze_bytes(json.dumps(payload).encode())


def test_missing_or_unlinked_finding_evidence_is_rejected():
    with pytest.raises(ValidationError, match="evidence_refs"):
        Finding(
            finding_id="finding-aaaaaaaaaaaa", correlation_key="x", rule_id="x", title="x",
            severity="medium", confidence=0.7, confidence_factors=["x"], signal_types=["auth_failure"],
            evidence_refs=[], recommendation="review",
        )
    report = _report()
    dumped = report.model_dump(mode="json")
    dumped["findings"][0]["evidence_refs"][0] = "synthetic-not-in-catalog"
    with pytest.raises(ValidationError, match="evidence reference"):
        type(report).model_validate(dumped)


def test_policy_rejects_unknown_and_repeated_actions_and_never_executes():
    finding_id = _report().findings[0].finding_id
    report = _report(actions=[
        ActionRequest(finding_id=finding_id, action_type="block_indicator"),
        ActionRequest(finding_id=finding_id, action_type="block_indicator"),
    ])
    assert [item.status for item in report.simulated_actions] == ["denied", "denied"]
    assert all(item.executed is False and item.mode == "simulation" for item in report.simulated_actions)


def test_allowed_action_requires_explicit_request_and_is_only_simulated():
    report = _report()
    finding_id = report.findings[0].finding_id
    allowed = _report(actions=[ActionRequest(finding_id=finding_id, action_type="increase_monitoring")])
    outcome = allowed.simulated_actions[0]
    assert outcome.status == "simulated"
    assert outcome.executed is False
    assert "no system action was executed" in outcome.reason


def test_report_contract_has_provenance_counts_and_limitations():
    report = _report()
    payload = report.model_dump(mode="json")
    assert payload["schema_version"] == "1.0"
    assert payload["report_type"] == "aegisai_local_synthetic_incident_report"
    assert payload["dataset_id"] == "synthetic-auth-investigation-v1"
    assert payload["generated_at_utc"].startswith("2026-10-22T00:00:00")
    assert len(payload["limitations"]) >= 1
