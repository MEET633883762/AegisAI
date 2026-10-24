from __future__ import annotations

from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
import time
from types import SimpleNamespace
from uuid import uuid4

import pytest

from private_api.telemetry import (
    SyntheticTelemetryEvent, TelemetryEventType, TelemetryFinding, TelemetrySeverity,
    detect_findings, make_telemetry_report,
)
from private_api.store import SQLiteStore
from scripts.run_purple_team_scenario import main as run_scenario_cli
from purple_team.catalog import SCENARIOS
from purple_team.runner import LocalPurpleTeamRunner, _exchange


def _event(scenario_id: str, index: int) -> SyntheticTelemetryEvent:
    scenario = SCENARIOS[scenario_id]
    is_auth = scenario.expected_telemetry_type == "auth_failure"
    return SyntheticTelemetryEvent(
        event_id=f"syn-scenario-{uuid4().hex}", occurred_at=datetime.now(timezone.utc),
        event_type=TelemetryEventType.AUTH_FAILURE if is_auth else TelemetryEventType.HTTP_ACCESS,
        asset_ref="synthetic-demo-website",
        actor_ref="synthetic-account-test" if is_auth else "synthetic-user-a",
        source_ref="synthetic-demo-site-live-access-error-logs-v1",
        evidence_ref=f"synthetic-website-evidence-{uuid4().hex}",
        http_method=scenario.request_method, route_code=scenario.expected_route_code,
        status_code=scenario.expected_status,
    )


def _report(events: list[SyntheticTelemetryEvent]):
    run_id = f"trun-{uuid4().hex[:16]}"
    findings = detect_findings(events, tenant_id="synthetic-org-demo")
    return make_telemetry_report(
        tenant_id="synthetic-org-demo", run_id=run_id, source_id="local_synthetic_fixture_v1",
        input_count=max(1, len(events)), accepted_count=max(1, len(events)), duplicate_count=0,
        findings=findings,
    )


def _runner(tmp_path, *, scenario_id, force_error=None):
    store = SQLiteStore(tmp_path / "purple.sqlite3")
    events: list[SyntheticTelemetryEvent] = []

    def request(method, path, _deadline):
        if force_error:
            from purple_team.runner import _ScenarioRequestError
            raise _ScenarioRequestError(force_error)
        events.append(_event(scenario_id, len(events)))
        expected = SCENARIOS[scenario_id].expected_status
        return expected, 26

    def snapshot_reader():
        return SimpleNamespace(batch=SimpleNamespace(events=tuple(events)))

    def ingest(_store):
        return _report(events)

    runner = LocalPurpleTeamRunner(store, request=request, snapshot_reader=snapshot_reader, ingest=ingest)
    return runner, store, events


def test_catalog_is_versioned_fixed_and_preview_sends_no_requests(tmp_path):
    assert {item.version for item in SCENARIOS.values()} == {"1.0"}
    assert all(item.cleanup_requirements and item.prerequisites and item.purpose for item in SCENARIOS.values())
    assert {item.request_path for item in SCENARIOS.values()} <= {"/health", "/login-failure"}
    preview = LocalPurpleTeamRunner.preview()
    assert len(preview) == len(SCENARIOS)
    assert all(item["execution"] == "preview_only" for item in preview)
    with pytest.raises(ValueError):
        LocalPurpleTeamRunner.preview("http://example.invalid/")


def test_cli_preview_does_not_initialize_or_write_database(tmp_path, capsys):
    database = tmp_path / "preview.sqlite3"
    assert run_scenario_cli(["--scenario", "local-health-baseline", "--database", str(database)]) == 0
    assert not database.exists()
    assert '"execution": "preview_only"' in capsys.readouterr().out


def test_denied_scenario_is_not_run_and_sends_zero_requests(tmp_path):
    scenario_id = "synthetic-auth-rejection"
    runner, store, events = _runner(tmp_path, scenario_id=scenario_id)
    result = runner.run(scenario_id)
    assert result.status == "NOT_RUN"
    assert result.policy_decision.reason_code == "explicit_authorization_required"
    assert result.observed_http_statuses == ()
    assert result.policy_decision.maximum_requests == 0
    assert events == []
    assert store.latest_purple_scenario_run("synthetic-org-demo", scenario_id).run_id == result.run_id


def test_only_one_scenario_run_can_hold_the_tenant_execution_slot(tmp_path):
    scenario_id = "synthetic-auth-rejection"
    runner, store, events = _runner(tmp_path, scenario_id=scenario_id)
    lease = "a" * 32
    assert store.acquire_purple_scenario_slot("synthetic-org-demo", lease)
    result = runner.run(scenario_id, explicitly_authorized=True)
    assert result.status == "NOT_RUN"
    assert result.limitations[-1] == "Sanitized execution error category: concurrency_limit."
    assert events == []
    store.release_purple_scenario_slot("synthetic-org-demo", lease)


def test_auth_rejection_scenario_observes_expected_telemetry_and_detection_and_compares_runs(tmp_path):
    scenario_id = "synthetic-auth-rejection"
    runner, store, events = _runner(tmp_path, scenario_id=scenario_id)
    first = runner.run(scenario_id, explicitly_authorized=True)
    assert first.status == "PASSED", first.model_dump_json(indent=2)
    assert len(events) == len(first.observed_telemetry) == 3
    assert first.observed_http_statuses == (401, 401, 401)
    assert {item.event_type for item in first.observed_telemetry} == {"auth_failure"}
    assert {item.rule_id for item in first.observed_findings} == {"AUTH-001"}
    assert first.observed_findings[0].evidence_refs
    assert first.telemetry_report_id and first.telemetry_run_id
    assert first.data_classification == "synthetic"
    assert "not evidence of real-world control effectiveness" in first.limitations[0].lower()

    second = runner.run(scenario_id, explicitly_authorized=True)
    assert second.status == "PASSED"
    assert second.comparison.previous_run_id == first.run_id
    assert second.comparison.previous_status == "PASSED"
    assert second.comparison.outcome_changed is False


def test_benign_health_scenario_passes_without_unexpected_findings(tmp_path):
    runner, _, _ = _runner(tmp_path, scenario_id="local-health-baseline")
    result = runner.run("local-health-baseline", explicitly_authorized=True)
    assert result.status == "PASSED"
    assert result.assessment_check_ids == ("health_status_v1",)
    assert result.expected_detection_rule_ids == ()
    assert result.observed_findings == ()


def test_unexpected_finding_type_linked_to_scenario_evidence_fails_comparison(tmp_path):
    runner, _, events = _runner(tmp_path, scenario_id="local-health-baseline")

    def unexpected_report(_store):
        event = events[-1]
        finding = TelemetryFinding(
            finding_id="tfinding-012345abcdef", rule_id="UNEXPECTED-001", rule_version="1.0",
            severity=TelemetrySeverity.LOW, confidence=0.4,
            first_seen_utc=event.occurred_at, last_seen_utc=event.occurred_at,
            asset_ref=event.asset_ref, evidence_refs=[event.evidence_ref], event_ids=[event.event_id],
            explanation="Synthetic test-only unexpected rule result.", confidence_factors=["focused regression fixture"],
        )
        return make_telemetry_report(
            tenant_id="synthetic-org-demo", run_id=f"trun-{uuid4().hex[:16]}",
            source_id="local_synthetic_fixture_v1", input_count=1, accepted_count=1,
            duplicate_count=0, findings=[finding],
        )

    runner._ingest = unexpected_report
    result = runner.run("local-health-baseline", explicitly_authorized=True)
    assert result.status == "FAILED"
    assert [item.rule_id for item in result.observed_findings] == ["UNEXPECTED-001"]


def test_request_error_is_recorded_without_retry_or_claim_of_success(tmp_path):
    runner, _, events = _runner(tmp_path, scenario_id="synthetic-auth-rejection", force_error="deadline_exceeded")
    result = runner.run("synthetic-auth-rejection", explicitly_authorized=True)
    assert result.status == "ERROR"
    assert result.error_category == "deadline_exceeded"
    assert result.observed_telemetry == ()
    assert events == []
    assert result.limitations[-1] == "Sanitized execution error category: deadline_exceeded."


def test_http_transport_uses_only_loopback_and_empty_fixed_post(monkeypatch):
    captured = {}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            captured["path"] = self.path
            captured["length"] = self.headers.get("Content-Length")
            captured["body"] = self.rfile.read(int(captured["length"]))
            self.send_response(401)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    monkeypatch.setattr("purple_team.runner.APPROVED_PORT", server.server_address[1])
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, body_bytes = _exchange("POST", "/login-failure", time.monotonic() + 2.0)
        assert (status, body_bytes) == (401, 0)
        assert captured == {"path": "/login-failure", "length": "0", "body": b""}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=1)
