"""Versioned expected-behavior cases; expected labels are assertions, not detector input."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from private_api.telemetry import (
    SyntheticTelemetryEvent,
    TelemetryConflictError,
    detect_findings,
    normalize_and_deduplicate,
)

ROBUSTNESS_SUITE_VERSION = "1.0"
START = datetime(2026, 10, 22, 12, tzinfo=timezone.utc)


def _event(event_id: str, event_type: str, minute: int, **fields) -> SyntheticTelemetryEvent:
    occurred_at = fields.pop("occurred_at", START + timedelta(minutes=minute))
    values = {
        "event_id": f"syn-p6c-{event_id}", "occurred_at": occurred_at,
        "event_type": event_type, "asset_ref": "synthetic-p6c-asset",
        "actor_ref": "synthetic-p6c-actor", "source_ref": "synthetic-p6c-source",
        "evidence_ref": f"synthetic-p6c-{event_id}",
    }
    values.update(fields)
    return SyntheticTelemetryEvent(**values)


def _run(case_id: str, events: list[SyntheticTelemetryEvent], expected: set[str]) -> list:
    normalized, _duplicates = normalize_and_deduplicate_for_test(events, case_id)
    findings = detect_findings(normalized, tenant_id="synthetic-org-p6c-regression")
    actual = {item.rule_id for item in findings}
    assert actual == expected, (
        f"robustness suite {ROBUSTNESS_SUITE_VERSION}, {case_id}: "
        f"expected={sorted(expected)}, actual={sorted(actual)}"
    )
    return findings


def normalize_and_deduplicate_for_test(events, _case_id):
    # Use the production normalizer with deterministic local batch metadata.
    from private_api.telemetry import SyntheticTelemetryBatch

    batch = SyntheticTelemetryBatch(
        schema_version="1.0", source_id="local_synthetic_fixture_v1",
        data_classification="synthetic", label="SYNTHETIC - NOT REAL CLIENT DATA",
        generated_at=max(event.occurred_at for event in events), events=events,
    )
    return normalize_and_deduplicate(batch)


@pytest.mark.parametrize(("request_count", "expected"), [
    (99, set()),
    (100, {"WEB-001"}),
    (101, {"WEB-001"}),
])
def test_request_count_just_below_at_and_above_rule_threshold(request_count, expected):
    _run(f"rate-count-{request_count}", [
        _event(f"rate-count-{request_count}", "request_rate_indicator", 0,
               request_count=request_count, window_seconds=60),
    ], expected)


@pytest.mark.parametrize(("window_seconds", "expected"), [
    (59, {"WEB-001"}),
    (60, {"WEB-001"}),
    (61, set()),
])
def test_rate_window_just_below_at_and_above_rule_threshold(window_seconds, expected):
    _run(f"rate-window-{window_seconds}", [
        _event(f"rate-window-{window_seconds}", "request_rate_indicator", 0,
               request_count=100, window_seconds=window_seconds),
    ], expected)


@pytest.mark.parametrize(("failure_count", "expected"), [
    (2, set()),
    (3, {"AUTH-001"}),
    (4, {"AUTH-001"}),
])
def test_authentication_failure_count_boundary(failure_count, expected):
    _run(f"auth-count-{failure_count}", [
        _event(f"auth-count-{failure_count}-{index}", "auth_failure", index)
        for index in range(failure_count)
    ], expected)


def test_authentication_window_at_and_just_beyond_existing_boundary():
    at_boundary = [
        _event("auth-window-at-0", "auth_failure", 0),
        _event("auth-window-at-5", "auth_failure", 5),
        _event("auth-window-at-10", "auth_failure", 10),
    ]
    beyond_boundary = [
        _event("auth-window-over-0", "auth_failure", 0),
        _event("auth-window-over-5", "auth_failure", 5),
        _event("auth-window-over-10", "auth_failure", 10, occurred_at=START + timedelta(minutes=10, seconds=1)),
    ]
    _run("auth-window-exactly-ten-minutes", at_boundary, {"AUTH-001"})
    _run("auth-window-ten-minutes-plus-one-second", beyond_boundary, set())


def test_noisy_benign_and_unrelated_events_do_not_create_other_finding_types():
    events = [
        _event("noise-rate", "request_rate_indicator", 0, request_count=100, window_seconds=60),
        _event("noise-single-auth", "auth_failure", 1, actor_ref="synthetic-p6c-other-actor"),
        _event("noise-routine-app", "simulated_suspicious_activity", 2, activity_code="routine_setting_read"),
        _event("noise-current-vuln", "synthetic_vulnerability_finding", 3, check_code="test_component_current"),
        _event("noise-debug-off", "synthetic_configuration_finding", 4, check_code="debug_mode_disabled"),
        _event("noise-http-404", "synthetic_http_access", 5, http_method="GET", route_code="not_found", status_code=404),
        _event("noise-safe-error", "synthetic_application_error", 6, error_code="RESOURCE_NOT_FOUND"),
    ]
    _run("noisy-benign-unrelated", events, {"WEB-001"})


def test_event_order_and_out_of_order_timestamps_normalize_to_same_behavior():
    events = [
        _event("ordered-auth-2", "auth_failure", 2),
        _event("ordered-auth-0", "auth_failure", 0),
        _event("ordered-success", "auth_success", 7),
        _event("ordered-auth-1", "auth_failure", 1),
    ]
    forward = _run("unordered-auth-forward", events, {"AUTH-001"})
    reverse = _run("unordered-auth-reverse", list(reversed(events)), {"AUTH-001"})
    assert forward[0].evidence_refs == reverse[0].evidence_refs
    assert set(forward[0].evidence_refs) == {event.evidence_ref for event in events}


def test_exact_duplicate_is_collapsed_but_conflicting_ids_and_evidence_fail_closed():
    three = [_event(f"duplicate-auth-{i}", "auth_failure", i) for i in range(3)]
    normalized, duplicate_count = normalize_and_deduplicate_for_test(three + [three[1]], "exact-duplicate")
    assert duplicate_count == 1
    findings = detect_findings(normalized, tenant_id="synthetic-org-p6c-duplicate")
    assert [item.rule_id for item in findings] == ["AUTH-001"]
    assert len(findings[0].evidence_refs) == 3

    conflict_id = three[0].model_copy(update={"actor_ref": "synthetic-p6c-contradiction"})
    with pytest.raises(TelemetryConflictError, match="conflicting content"):
        normalize_and_deduplicate_for_test([three[0], conflict_id], "conflicting-event-id")
    conflict_evidence = three[1].model_copy(update={"evidence_ref": three[0].evidence_ref})
    with pytest.raises(TelemetryConflictError, match="evidence reference"):
        normalize_and_deduplicate_for_test([three[0], conflict_evidence], "conflicting-evidence")


def test_missing_partial_or_contradictory_fields_are_rejected_by_existing_schema():
    valid = _event("partial-event", "auth_failure", 0).model_dump(mode="json")
    partial = dict(valid)
    partial.pop("evidence_ref")
    contradictory = {**valid, "request_count": 100, "window_seconds": 60}
    malformed = {**valid, "unknown_payload": "synthetic"}
    for record in (partial, contradictory, malformed):
        with pytest.raises(ValidationError):
            SyntheticTelemetryEvent.model_validate(record)


def test_multiple_independent_event_groups_produce_two_supported_findings():
    events = [
        _event("independent-rate", "request_rate_indicator", 0, request_count=120, window_seconds=60),
        _event("independent-app", "simulated_suspicious_activity", 1,
               activity_code="unusual_synthetic_file_access", asset_ref="synthetic-p6c-app"),
    ]
    findings = _run("independent-rate-and-app", events, {"APP-001", "WEB-001"})
    assert {item.rule_id: set(item.evidence_refs) for item in findings} == {
        "APP-001": {events[1].evidence_ref}, "WEB-001": {events[0].evidence_ref},
    }
