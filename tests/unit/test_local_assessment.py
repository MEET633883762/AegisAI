from __future__ import annotations

import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from local_assessment.controller import LocalAssessmentController
from local_assessment.catalog import CHECK_CATALOG, CHECK_CATALOG_VERSION
from local_assessment.models import AssessmentCheck, CheckId, CheckOutcome
from local_assessment.policy import APPROVED_ORIGIN, LocalAssessmentPolicy


def check(check_id=CheckId.HEALTH_STATUS, origin=APPROVED_ORIGIN):
    return AssessmentCheck(check_id=check_id, target_origin=origin)


def stub_exchange(monkeypatch, *, status=200, headers=None, body=b"ok"):
    calls = []
    def exchange(path, request_deadline, assessment_deadline):
        calls.append((path, request_deadline, assessment_deadline))
        return status, headers or {}, body
    monkeypatch.setattr("local_assessment.controller._exchange_http", exchange)
    return calls


@contextmanager
def local_http_server(monkeypatch, handler_type):
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_type)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    origin = f"http://127.0.0.1:{server.server_port}"
    monkeypatch.setattr("local_assessment.policy.APPROVED_ORIGIN", origin)
    monkeypatch.setattr("local_assessment.policy.APPROVED_PORT", server.server_port)
    monkeypatch.setattr("local_assessment.controller.APPROVED_ORIGIN", origin)
    monkeypatch.setattr("local_assessment.controller.APPROVED_PORT", server.server_port)
    try:
        yield server, origin
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.mark.parametrize("origin", [
    "https://127.0.0.1:8767", "http://127.0.0.1:8768", "http://localhost:8767",
    "http://192.0.2.1:8767", "http://user:pass@127.0.0.1:8767",
    "http://127.0.0.1:8767/path", "http://127.0.0.1:8767?x=1",
    "http://127.0.0.1", "http://[::1]:8767",
])
def test_policy_denies_non_exact_origins(origin):
    decision = LocalAssessmentPolicy().authorize(check(origin=origin))
    assert not decision.allowed
    assert decision.reason_code == "target_not_allowlisted"


def test_denied_check_never_calls_network(monkeypatch):
    sent = []
    monkeypatch.setattr("local_assessment.controller._exchange_http", lambda *_: sent.append("request"))
    result = LocalAssessmentController().run([check(origin="http://example.com:8767")])
    assert result.decisions[0].allowed is False
    assert result.observations[0].outcome == "denied"
    assert result.observations[0].outcome_status is CheckOutcome.ERROR
    assert sent == []


def test_policy_is_rechecked_at_transport_boundary(monkeypatch):
    from local_assessment.models import AssessmentDecision

    class ChangingPolicy:
        calls = 0
        def authorize(self, proposal):
            self.calls += 1
            if self.calls == 1:
                return LocalAssessmentPolicy().authorize(proposal)
            return AssessmentDecision(check_id=proposal.check_id, target_origin=proposal.target_origin,
                                      allowed=False, reason_code="policy_revoked")

    sent = []
    monkeypatch.setattr("local_assessment.controller._exchange_http", lambda *_: sent.append("request"))
    result = LocalAssessmentController(ChangingPolicy()).run([check()])
    assert not result.decisions[0].allowed
    assert result.decisions[0].reason_code == "policy_revoked"
    assert result.observations[0].outcome == "denied"
    assert result.observations[0].outcome_status is CheckOutcome.ERROR
    assert sent == []


def test_allowlisted_status_observation_has_bounded_evidence(monkeypatch):
    calls = stub_exchange(monkeypatch, body=b"Synthetic site is running.\n")
    result = LocalAssessmentController().run([check()])
    observation = result.observations[0]
    assert result.decisions[0].allowed
    assert observation.outcome == "observed"
    assert observation.facts["status"] == 200
    assert observation.facts["status_matches_expectation"] is True
    assert observation.evidence.response_bytes == len(b"Synthetic site is running.\n")
    assert observation.evidence.response_sha256
    assert calls[0][0] == "/health"
    assert calls[0][1] <= calls[0][2]
    assert observation.outcome_status is CheckOutcome.PASS
    assert observation.check_version == "1.0"
    assert observation.category == "availability"
    assert observation.expected_result and observation.observed_result
    assert observation.observed_at_utc.tzinfo is not None


def test_runner_uses_actual_ephemeral_loopback_test_server(monkeypatch):
    requested = []
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            requested.append((self.client_address[0], self.path))
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(b"synthetic test response")
        def log_message(self, *_args): pass

    with local_http_server(monkeypatch, Handler) as (_server, origin):
        result = LocalAssessmentController().run([check(origin=origin)])
    assert requested == [("127.0.0.1", "/health")]
    assert result.observations[0].facts["status_matches_expectation"] is True
    assert result.observations[0].evidence.response_bytes == len(b"synthetic test response")


def test_real_loopback_redirect_is_not_followed(monkeypatch):
    requested = []
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            requested.append(self.path)
            self.send_response(302)
            self.send_header("Location", "https://outside.example/landing")
            self.end_headers()
        def log_message(self, *_args): pass

    with local_http_server(monkeypatch, Handler) as (_server, origin):
        result = LocalAssessmentController().run([check(origin=origin)])
    observation = result.observations[0]
    assert requested == ["/health"]
    assert observation.outcome == "redirect_denied_out_of_scope"
    assert observation.facts["redirect_followed"] is False
    assert observation.facts["redirect_target_approved"] is False


def test_real_loopback_timeout_is_reported_safely(monkeypatch):
    import time

    monkeypatch.setattr("local_assessment.controller.REQUEST_TIMEOUT_SECONDS", 0.05)
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            time.sleep(0.15)
            try:
                self.send_response(200)
                self.end_headers()
            except OSError:
                pass
        def log_message(self, *_args): pass

    with local_http_server(monkeypatch, Handler) as (_server, origin):
        result = LocalAssessmentController().run([check(origin=origin)])
    observation = result.observations[0]
    assert observation.outcome == "request_failed"
    assert observation.error_category == "request_failed"
    assert "outside.example" not in str(observation.model_dump())


def test_malformed_local_http_response_is_sanitized_as_error(monkeypatch):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.wfile.write(b"not a valid HTTP response\r\n\r\n")
        def log_message(self, *_args): pass

    with local_http_server(monkeypatch, Handler) as (_server, origin):
        observation = LocalAssessmentController().run([check(origin=origin)]).observations[0]
    assert observation.outcome == "request_failed"
    assert observation.outcome_status is CheckOutcome.ERROR
    assert observation.facts == {"reason_code": "local_request_failed"}


def test_unavailable_loopback_target_is_error_without_sensitive_details(monkeypatch):
    import socket
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    origin = f"http://127.0.0.1:{port}"
    monkeypatch.setattr("local_assessment.policy.APPROVED_PORT", port)
    monkeypatch.setattr("local_assessment.controller.APPROVED_PORT", port)
    observation = LocalAssessmentController().run([check(origin=origin)]).observations[0]
    assert observation.outcome == "request_failed"
    assert observation.outcome_status is CheckOutcome.ERROR
    assert observation.error_category == "request_failed"
    assert observation.facts == {"reason_code": "local_request_failed"}
    assert "WinError" not in str(observation.model_dump())


def test_trickling_response_cannot_exceed_assessment_deadline_and_socket_is_closed(monkeypatch):
    import time
    import local_assessment.controller as controller_module

    deadline_seconds = 0.18
    monkeypatch.setattr("local_assessment.controller.ASSESSMENT_DEADLINE_SECONDS", deadline_seconds)
    monkeypatch.setattr("local_assessment.controller.REQUEST_TIMEOUT_SECONDS", 0.8)
    opened_sockets = []
    real_socket = controller_module.socket.socket
    def tracked_socket(*args, **kwargs):
        created = real_socket(*args, **kwargs)
        opened_sockets.append(created)
        return created
    monkeypatch.setattr(controller_module.socket, "socket", tracked_socket)

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Length", "40")
            self.end_headers()
            try:
                for _ in range(40):
                    self.wfile.write(b"x")
                    self.wfile.flush()
                    time.sleep(0.025)
            except OSError:
                pass
        def log_message(self, *_args): pass

    with local_http_server(monkeypatch, Handler) as (_server, origin):
        started = time.monotonic()
        result = LocalAssessmentController().run([check(origin=origin)])
        elapsed = time.monotonic() - started
    observation = result.observations[0]
    assert elapsed < 0.65
    assert observation.outcome == "deadline_exceeded"
    assert observation.error_category == "deadline_exceeded"
    assert opened_sockets and all(item.fileno() == -1 for item in opened_sockets)


def test_real_loopback_oversized_response_is_bounded(monkeypatch):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body = b"x" * 16_385
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        def log_message(self, *_args): pass

    with local_http_server(monkeypatch, Handler) as (_server, origin):
        result = LocalAssessmentController().run([check(origin=origin)])
    observation = result.observations[0]
    assert observation.outcome == "response_too_large"
    assert observation.evidence is None


def test_security_headers_are_reported_as_facts_not_vulnerability_claims(monkeypatch):
    stub_exchange(monkeypatch, headers={"x-content-type-options": "nosniff"})
    observation = LocalAssessmentController().run([check(CheckId.SECURITY_HEADERS)]).observations[0]
    assert observation.outcome == "headers_observed"
    assert observation.facts["x-content-type-options"] == "nosniff"
    assert "finding" not in observation.facts
    assert observation.outcome_status is CheckOutcome.FAIL


def test_security_header_check_passes_only_when_every_catalogued_header_is_present(monkeypatch):
    stub_exchange(monkeypatch, headers={
        "content-security-policy": "default-src 'self'", "x-content-type-options": "nosniff",
        "referrer-policy": "no-referrer", "permissions-policy": "camera=()",
    })
    result = LocalAssessmentController().run([check(CheckId.SECURITY_HEADERS)])
    assert result.observations[0].outcome_status is CheckOutcome.PASS


def test_non_200_health_response_is_a_failed_observation(monkeypatch):
    stub_exchange(monkeypatch, status=503)
    observation = LocalAssessmentController().run([check()]).observations[0]
    assert observation.outcome_status is CheckOutcome.FAIL
    assert observation.observed_result == "Observed HTTP 503; expected HTTP 200."


def test_catalog_is_complete_versioned_and_does_not_claim_unjustified_mappings():
    assert CHECK_CATALOG_VERSION == "local-web-checks-v1"
    assert set(CHECK_CATALOG) == set(CheckId)
    for check_id, definition in CHECK_CATALOG.items():
        assert definition.check_id is check_id and definition.version == "1.0"
        assert definition.description and definition.expected_result and definition.severity
        assert definition.mitre_attack_technique_ids == ()
        assert definition.defensive_control_ids == ()
        assert "do not observe adversary behavior" in definition.mapping_rationale


def test_cookie_check_reports_not_applicable_if_no_cookie(monkeypatch):
    stub_exchange(monkeypatch)
    observation = LocalAssessmentController().run([check(CheckId.COOKIE_ATTRIBUTES)]).observations[0]
    assert observation.outcome == "not_applicable_no_cookie"
    assert observation.facts["cookie_returned"] is False
    assert observation.outcome_status is CheckOutcome.NOT_APPLICABLE


def test_cookie_flags_are_normalized_without_returning_cookie_value(monkeypatch):
    stub_exchange(monkeypatch, headers={"set-cookie": "session=private-value; Secure; HttpOnly; SameSite=Strict"})
    observation = LocalAssessmentController().run([check(CheckId.COOKIE_ATTRIBUTES)]).observations[0]
    assert observation.facts == {"status": 200, "expected_status": 200,
                                 "status_matches_expectation": True, "cookie_returned": True,
                                 "secure": True, "httponly": True, "samesite": "strict"}
    assert "private-value" not in str(observation.model_dump())


def test_redirect_is_returned_as_observation_and_never_followed(monkeypatch):
    calls = []
    def exchange(path, request_deadline, assessment_deadline):
        calls.append(path)
        return 302, {"location": "https://example.com/"}, b""
    monkeypatch.setattr("local_assessment.controller._exchange_http", exchange)
    result = LocalAssessmentController().run([check()])
    assert calls == ["/health"]
    assert result.observations[0].outcome == "redirect_denied_out_of_scope"
    assert result.observations[0].facts["redirect_followed"] is False
    assert result.observations[0].facts["redirect_target_approved"] is False
    assert result.observations[0].decision.allowed


def test_same_origin_redirect_is_inspected_but_still_not_followed(monkeypatch):
    requests = []
    def exchange(path, request_deadline, assessment_deadline):
        requests.append(path)
        return 302, {"location": "/"}, b""
    monkeypatch.setattr("local_assessment.controller._exchange_http", exchange)
    result = LocalAssessmentController().run([check()])
    assert result.observations[0].outcome == "redirect_not_followed"
    assert result.observations[0].facts["redirect_target_approved"] is True
    assert requests == ["/health"]


def test_timeout_is_sanitized(monkeypatch):
    def timeout(*_args, **_kwargs): raise TimeoutError("sensitive detail")
    monkeypatch.setattr("local_assessment.controller._exchange_http", timeout)
    observation = LocalAssessmentController().run([check()]).observations[0]
    assert observation.outcome == "request_failed"
    assert observation.facts == {"reason_code": "local_request_failed"}
    assert observation.error_category == "request_failed"
    assert observation.duration_ms >= 0
    assert observation.outcome_status is CheckOutcome.ERROR


def test_response_body_is_read_only_to_limit(monkeypatch):
    from local_assessment.controller import _ResponseLimitExceeded
    def oversized(*_args, **_kwargs): raise _ResponseLimitExceeded
    monkeypatch.setattr("local_assessment.controller._exchange_http", oversized)
    observation = LocalAssessmentController().run([check()]).observations[0]
    assert observation.outcome == "response_too_large"
    assert observation.evidence is None
    assert observation.outcome_status is CheckOutcome.ERROR


def test_response_headers_are_bounded(monkeypatch):
    from local_assessment.controller import _ResponseLimitExceeded
    def oversized(*_args, **_kwargs): raise _ResponseLimitExceeded
    monkeypatch.setattr("local_assessment.controller._exchange_http", oversized)
    observation = LocalAssessmentController().run([check()]).observations[0]
    assert observation.outcome == "response_too_large"


def test_request_count_limit_fails_before_any_request(monkeypatch):
    sent = []
    monkeypatch.setattr("local_assessment.controller._exchange_http", lambda *_: sent.append(1))
    with pytest.raises(ValueError, match="request-count limit"):
        LocalAssessmentController().run([check(), check(CheckId.SECURITY_HEADERS), check(CheckId.COOKIE_ATTRIBUTES), check()])
    assert sent == []


def test_runner_supplies_only_the_fixed_allowlisted_catalog():
    from local_assessment.runner import LocalAssessmentRunner

    class CaptureController:
        captured = ()
        def run(self, checks):
            self.captured = tuple(checks)
            from local_assessment.models import AssessmentResult
            from local_assessment.policy import LocalAssessmentPolicy
            return AssessmentResult(
                decisions=tuple(LocalAssessmentPolicy().authorize(item) for item in checks),
                observations=(),
            )

    controller = CaptureController()
    result = LocalAssessmentRunner(controller).run()
    assert [item.check_id for item in controller.captured] == [
        CheckId.HEALTH_STATUS, CheckId.SECURITY_HEADERS, CheckId.COOKIE_ATTRIBUTES,
    ]
    assert all(item.target_origin == APPROVED_ORIGIN for item in controller.captured)
    assert all(decision.allowed for decision in result.decisions)


def test_check_model_rejects_unknown_fields_and_check_ids():
    with pytest.raises(ValueError):
        AssessmentCheck(check_id="arbitrary", target_origin=APPROVED_ORIGIN)
    with pytest.raises(ValueError):
        AssessmentCheck(check_id=CheckId.HEALTH_STATUS, target_origin=APPROVED_ORIGIN, path="/other")
