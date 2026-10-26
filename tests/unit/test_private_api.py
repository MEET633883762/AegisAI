from __future__ import annotations

import http.client
import json
import socket
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from platform_prototype.models import SyntheticEventBatch
from platform_prototype.pipeline import build_report
from private_api.auth import LocalTokenRegistry
from private_api.server import ApiApplication, MAX_REQUEST_BODY_BYTES, create_local_server
from private_api.store import SQLiteStore

ROOT = Path(__file__).parents[2]
FIXTURE = ROOT / "platform_prototype" / "fixtures" / "synthetic_events_v1.json"
ALPHA = "synthetic-org-alpha"
BETA = "synthetic-org-beta"


def _report(*, beta: bool = False):
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    if beta:
        for event in payload["events"]:
            event["event_id"] = event["event_id"].replace("syn-auth-", "syn-beta-")
            event["evidence_ref"] = event["evidence_ref"].replace("synthetic-evidence-", "synthetic-beta-evidence-")
    batch = SyntheticEventBatch.model_validate(payload)
    return build_report(batch, generated_at=datetime(2026, 10, 22, tzinfo=timezone.utc))


@pytest.fixture
def api(tmp_path):
    store = SQLiteStore(tmp_path / "private.sqlite3")
    store.seed_tenant(ALPHA, _report())
    store.seed_tenant(BETA, _report(beta=True))
    tokens = LocalTokenRegistry()
    alpha_token = tokens.issue_development_token(ALPHA)
    beta_token = tokens.issue_development_token(BETA)
    return ApiApplication(store, tokens), store, alpha_token, beta_token


def _call(app, path="/api/findings", *, token=None, method="GET", body=b"", body_length=None):
    return app.handle(
        method=method, target=path,
        authorization=f"Bearer {token}" if token else None,
        body_length=len(body) if body_length is None else body_length,
        body=body,
    )


def test_unauthenticated_access_is_denied_and_audited(api):
    app, store, _, _ = api
    response = _call(app)
    assert response.status == 401
    assert response.payload == {"error": "unauthorized", "message": "Authentication is required."}
    event = store.audit_snapshot()[-1]
    assert event["event_type"] == "authentication_failure"
    assert event["details_code"] == "missing_token"


def test_invalid_and_expired_tokens_are_rejected_and_expiry_is_audited(api):
    app, store, _, _ = api
    assert _call(app, token="not-a-token").status == 401
    now = [1000.0]
    tokens = LocalTokenRegistry(clock=lambda: now[0])
    expired_token = tokens.issue_development_token(ALPHA, ttl_seconds=1)
    now[0] = 1001.0
    expired_app = ApiApplication(store, tokens)
    assert _call(expired_app, token=expired_token).status == 401
    assert store.audit_snapshot()[-1]["details_code"] == "expired_token"


def test_insufficient_permissions_are_denied_and_audited(api):
    _, store, _, _ = api
    tokens = LocalTokenRegistry()
    incidents_only = tokens.issue_development_token(ALPHA, scopes=frozenset({"incidents:read"}))
    app = ApiApplication(store, tokens)
    response = _call(app, token=incidents_only)
    assert response.status == 403
    assert response.payload["error"] == "forbidden"
    assert store.audit_snapshot()[-1]["details_code"] == "insufficient_scope"


def test_forged_tenant_parameter_is_rejected_and_cannot_change_scope(api):
    app, store, alpha_token, beta_token = api
    response = _call(app, "/api/findings?tenant_id=synthetic-org-alpha", token=beta_token)
    assert response.status == 400
    assert "findings" not in response.payload
    assert store.audit_snapshot()[-1]["details_code"] == "query_parameters_not_supported"
    visible = _call(app, token=beta_token)
    assert visible.status == 200
    assert visible.payload["tenant_id"] == BETA
    assert {item["finding_id"] for item in visible.payload["findings"]}.isdisjoint(
        {item["finding_id"] for item in _call(app, token=alpha_token).payload["findings"]}
    )


def test_cross_tenant_evidence_and_report_are_indistinguishable_from_missing(api):
    app, _, alpha_token, beta_token = api
    alpha_findings = _call(app, token=alpha_token).payload["findings"]
    alpha_finding = alpha_findings[0]["finding_id"]
    cross_tenant = _call(app, f"/api/findings/{alpha_finding}/evidence", token=beta_token)
    absent = _call(app, "/api/findings/finding-000000000000/evidence", token=beta_token)
    assert cross_tenant.status == absent.status == 404
    assert cross_tenant.payload == absent.payload
    alpha_incident = _call(app, "/api/incidents", token=alpha_token).payload["incidents"][0]["incident_id"]
    cross_report = _call(app, f"/api/incidents/{alpha_incident}/report", token=beta_token)
    assert cross_report.status == 404
    assert cross_report.payload == {"error": "not_found", "message": "The requested resource was not found."}


def test_malformed_and_oversized_requests_are_rejected(api):
    app, store, _, token = api
    malformed = _call(app, "/api/findings", token=token, body=b"{", body_length=1)
    oversized = _call(app, "/api/findings", token=token,
                      body_length=MAX_REQUEST_BODY_BYTES + 1)
    assert malformed.status == 400
    assert oversized.status == 413
    assert [event["details_code"] for event in store.audit_snapshot()[-2:]] == [
        "unexpected_request_body", "request_too_large",
    ]


def test_only_read_methods_are_supported(api):
    app, store, _, token = api
    response = _call(app, "/api/findings", token=token, method="POST")
    assert response.status == 405
    assert response.payload["error"] == "method_not_allowed"
    assert store.audit_snapshot()[-1]["details_code"] == "method_not_allowed"


def test_finding_evidence_summaries_reports_and_health_are_validated(api):
    app, store, _, token = api
    findings = _call(app, token=token)
    assert findings.status == 200
    assert findings.payload["data_classification"] == "synthetic"
    assert findings.payload["label"] == "SYNTHETIC - NOT REAL CLIENT DATA"
    assert len(findings.payload["findings"]) == 2
    finding_id = findings.payload["findings"][0]["finding_id"]
    evidence = _call(app, f"/api/findings/{finding_id}/evidence", token=token)
    assert evidence.status == 200
    assert evidence.payload["evidence"]
    incidents = _call(app, "/api/incidents", token=token)
    assert incidents.status == 200
    incident_id = incidents.payload["incidents"][0]["incident_id"]
    report = _call(app, f"/api/incidents/{incident_id}/report", token=token)
    assert report.status == 200
    assert report.payload["report"]["report_type"] == "aegisai_local_synthetic_incident_report"
    health = _call(app, "/health", token=token)
    assert health.payload == {"status": "ok", "mode": "local_synthetic"}
    readiness = _call(app, "/ready", token=token)
    assert readiness.status == 200
    assert readiness.payload == {"status": "ready", "mode": "local_synthetic"}
    operations = [event for event in store.audit_snapshot() if event["event_type"] == "protected_operation"]
    assert len(operations) == 6
    assert all(event["outcome"] == "success" for event in operations)


def test_database_error_returns_safe_response_and_records_failure(api):
    app, store, _, token = api
    with patch.object(store, "list_findings", side_effect=RuntimeError("secret db path and stack")):
        response = _call(app, token=token)
    encoded = json.dumps(response.payload)
    assert response.status == 500
    assert response.payload == {
        "error": "internal_error", "message": "The service could not complete the request."
    }
    assert "secret" not in encoded and "RuntimeError" not in encoded
    assert store.audit_snapshot()[-1]["details_code"] == "internal_error"
    assert store.audit_snapshot()[-1]["outcome"] == "error"


def test_readiness_requires_health_scope_and_fails_safely(api):
    app, store, _, token = api
    assert _call(app, "/ready").status == 401
    reports_only = LocalTokenRegistry()
    reports_token = reports_only.issue_development_token(ALPHA, scopes=frozenset({"reports:read"}))
    assert _call(ApiApplication(store, reports_only), "/ready", token=reports_token).status == 403
    with patch.object(store, "ping", side_effect=RuntimeError("private db detail")):
        failed = _call(app, "/ready", token=token)
    assert failed.status == 500
    assert failed.payload == {"error": "internal_error", "message": "The service could not complete the request."}
    assert "private" not in json.dumps(failed.payload)


def test_development_api_refuses_nonlocal_runtime_mode_before_store_access(monkeypatch, capsys):
    from scripts import run_private_api

    monkeypatch.setenv("AEGISAI_ENV", "production")
    with patch.object(run_private_api, "SQLiteStore", side_effect=AssertionError("must not touch database")):
        assert run_private_api.main([]) == 2
    assert "unsupported_runtime_mode" in capsys.readouterr().err


def test_http_handler_closes_idle_partial_request(monkeypatch, api):
    app, _, _, _ = api
    monkeypatch.setattr("private_api.server.REQUEST_SOCKET_TIMEOUT_SECONDS", 0.2)
    monkeypatch.setattr("private_api.server.MAX_CONCURRENT_REQUESTS", 1)
    server = create_local_server(app, port=0)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()
    client = None
    excess_client = None
    try:
        host, port = server.server_address
        client = socket.create_connection((host, port), timeout=1)
        client.sendall(b"GET /health HTTP/1.1\r\n")
        time.sleep(0.05)
        excess_client = socket.create_connection((host, port), timeout=1)
        assert excess_client.recv(1) == b""
        time.sleep(0.25)
        assert client.recv(1) == b""
    finally:
        if client is not None:
            client.close()
        if excess_client is not None:
            excess_client.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_live_source_status_is_authenticated_read_only_and_tenant_scoped(api):
    app, store, alpha_token, beta_token = api
    path = "/api/telemetry/sources/live-website/status"
    unavailable = _call(app, path, token=alpha_token)
    assert unavailable.status == 200
    assert unavailable.payload["status"] == "unavailable"
    assert unavailable.payload["tenant_id"] == ALPHA
    assert unavailable.payload["input_event_count"] is None
    assert unavailable.payload["accepted_event_count"] is None
    assert unavailable.payload["last_attempt_at_utc"] is None

    store.start_live_source_attempt(ALPHA)
    store.finish_live_source_attempt(
        ALPHA, status="healthy", input_count=4, accepted_count=2, duplicate_count=2,
        position_sha256="a" * 64, position_bytes=512,
    )
    assert _call(app, path).status == 401
    tokens = LocalTokenRegistry()
    reports_only = tokens.issue_development_token(ALPHA, scopes=frozenset({"reports:read"}))
    assert _call(ApiApplication(store, tokens), path, token=reports_only).status == 403
    visible = _call(app, path, token=alpha_token)
    assert visible.status == 200
    assert visible.payload["accepted_event_count"] == 2
    assert visible.payload["duplicate_event_count"] == 2
    assert visible.payload["position_bytes"] == 512
    assert "path" not in json.dumps(visible.payload).lower()
    other_tenant = _call(app, path, token=beta_token)
    assert other_tenant.status == 200
    assert other_tenant.payload["status"] == "unavailable"
    assert other_tenant.payload["tenant_id"] == BETA
    assert other_tenant.payload["input_event_count"] is None
    assert other_tenant.payload["accepted_event_count"] is None
    assert _call(app, path + "?tenant_id=" + ALPHA, token=alpha_token).status == 400
    assert store.audit_snapshot()[-1]["details_code"] == "query_parameters_not_supported"


def test_local_http_server_binds_loopback_and_sets_safe_response_headers(api):
    app, _, _, token = api
    server = create_local_server(app, port=0)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        assert host == "127.0.0.1"
        connection = http.client.HTTPConnection(host, port, timeout=2)
        connection.request("GET", "/health", headers={"Authorization": f"Bearer {token}"})
        response = connection.getresponse()
        body = json.loads(response.read())
        assert response.status == 200
        assert body == {"status": "ok", "mode": "local_synthetic"}
        assert response.getheader("Cache-Control") == "no-store"
        assert response.getheader("X-Content-Type-Options") == "nosniff"
        connection.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.mark.parametrize("content_length, expected_status", [
    ("9" * 5000, 413),
    ("0" * 5000, 200),
])
def test_http_content_length_is_bounded_before_integer_conversion(api, content_length, expected_status):
    app, _, _, token = api
    server = create_local_server(app, port=0)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        connection = http.client.HTTPConnection(host, port, timeout=2)
        connection.request("GET", "/health", headers={
            "Authorization": f"Bearer {token}", "Content-Length": content_length,
        })
        response = connection.getresponse()
        payload = json.loads(response.read())
        assert response.status == expected_status
        assert response.getheader("Content-Type") == "application/json; charset=utf-8"
        assert payload.get("error") == ("request_too_large" if expected_status == 413 else None)
        connection.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_local_http_server_allows_only_fixed_loopback_frontend_cors_origins(api):
    app, _, _, token = api
    server = create_local_server(app, port=0)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        origin = "http://127.0.0.1:5174"
        connection = http.client.HTTPConnection(host, port, timeout=2)
        connection.request("OPTIONS", "/api/telemetry/findings", headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        })
        preflight = connection.getresponse()
        preflight.read()
        assert preflight.status == 204
        assert preflight.getheader("Access-Control-Allow-Origin") == origin
        assert preflight.getheader("Access-Control-Allow-Methods") == "GET, POST, OPTIONS"
        assert preflight.getheader("Access-Control-Allow-Credentials") is None
        connection.close()

        connection = http.client.HTTPConnection(host, port, timeout=2)
        connection.request("OPTIONS", "/api/investigations/cases", headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization, content-type",
        })
        write_preflight = connection.getresponse()
        write_preflight.read()
        assert write_preflight.status == 204
        assert write_preflight.getheader("Access-Control-Allow-Origin") == origin
        connection.close()

        connection = http.client.HTTPConnection(host, port, timeout=2)
        connection.request("GET", "/health", headers={"Origin": origin, "Authorization": f"Bearer {token}"})
        allowed = connection.getresponse()
        allowed.read()
        assert allowed.status == 200
        assert allowed.getheader("Access-Control-Allow-Origin") == origin
        connection.close()

        connection = http.client.HTTPConnection(host, port, timeout=2)
        connection.request("OPTIONS", "/health", headers={
            "Origin": "http://192.168.1.22:5174",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        })
        denied = connection.getresponse()
        denied.read()
        assert denied.status == 403
        assert denied.getheader("Access-Control-Allow-Origin") is None
        connection.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_phase1_synthetic_pipeline_contract_remains_unchanged():
    report = build_report(
        SyntheticEventBatch.model_validate_json(FIXTURE.read_bytes()),
        generated_at=datetime(2026, 10, 22, tzinfo=timezone.utc),
    )
    assert report.label == "SYNTHETIC - NOT REAL CLIENT DATA"
    assert (report.input_event_count, report.unique_event_count, report.duplicate_event_count) == (9, 8, 1)
    assert len(report.findings) == 2
    assert report.simulated_actions == []


def test_static_publisher_allowlist_is_unchanged_and_excludes_backend():
    from scripts.build_static_site import STATIC_ALLOWLIST

    assert STATIC_ALLOWLIST == (
        "_headers", "index.html", "dashboard.html", "privacy.html", "assets/app.css", "assets/main.js",
        "assets/public_demo_episode.json", "assets/public_demo_assessment_baseline.json",
        "assets/public_demo_assessment_hardened.json",
    )
    assert not any("private_api" in item or "sqlite" in item for item in STATIC_ALLOWLIST)
