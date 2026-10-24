"""Bounded local assessment executor; every request passes policy immediately first."""

from __future__ import annotations

import hashlib
import errno
import re
import selectors
import socket
import time
from datetime import datetime, timezone
from urllib.parse import urljoin, urlsplit
from uuid import uuid4

from local_assessment.models import (
    AssessmentCheck, AssessmentDecision, AssessmentEvidence,
    AssessmentObservation, AssessmentResult, CheckId,
)
from local_assessment.catalog import CHECK_CATALOG, CONFIGURATION_VERSION, classify_result
from local_assessment.policy import (
    APPROVED_ORIGIN, APPROVED_PORT, CHECK_PATHS, MAX_CHECKS_PER_ASSESSMENT, LocalAssessmentPolicy,
)

REQUEST_TIMEOUT_SECONDS = 1.0
ASSESSMENT_DEADLINE_SECONDS = 4.0
MAX_RESPONSE_BYTES = 16_384
SECURITY_HEADERS = (
    "content-security-policy", "x-content-type-options", "referrer-policy", "permissions-policy",
)


class _RequestTimedOut(Exception):
    pass


class _AssessmentDeadlineExceeded(Exception):
    pass


class _ResponseLimitExceeded(Exception):
    pass


def _wait_for_socket(selector, events: int, request_deadline: float, assessment_deadline: float) -> None:
    while True:
        now = time.monotonic()
        if now >= assessment_deadline:
            raise _AssessmentDeadlineExceeded
        if now >= request_deadline:
            raise _RequestTimedOut
        ready = selector.select(min(request_deadline - now, assessment_deadline - now))
        if ready:
            return


def _parse_response_headers(header_block: bytes) -> tuple[int, dict[str, str]]:
    lines = header_block.split(b"\r\n")
    status_line = re.fullmatch(rb"HTTP/1\.[01] ([1-5][0-9]{2})(?: [^\r\n]*)?", lines[0])
    if status_line is None:
        raise OSError("invalid local HTTP response")
    headers: dict[str, str] = {}
    for line in lines[1:]:
        if not line:
            continue
        name, separator, value = line.partition(b":")
        if not separator or not re.fullmatch(rb"[!#$%&'*+.^_`|~0-9A-Za-z-]+", name):
            raise OSError("invalid local HTTP response")
        key = name.decode("ascii").lower()
        headers.setdefault(key, value.strip().decode("latin-1"))
    return int(status_line.group(1)), headers


def _exchange_http(path: str, request_deadline: float, assessment_deadline: float) -> tuple[int, dict[str, str], bytes]:
    """Perform one fixed-origin HTTP request using deadline-aware nonblocking I/O."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.setblocking(False)
        with selectors.DefaultSelector() as selector:
            result = sock.connect_ex(("127.0.0.1", APPROVED_PORT))
            if result not in (0, errno.EISCONN):
                pending = {errno.EINPROGRESS, errno.EWOULDBLOCK, errno.EALREADY, errno.EINTR, 10035, 10036, 10037}
                if result not in pending:
                    raise OSError(result, "loopback connection failed")
                selector.register(sock, selectors.EVENT_WRITE)
                _wait_for_socket(selector, selectors.EVENT_WRITE, request_deadline, assessment_deadline)
                selector.unregister(sock)
                connect_error = sock.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
                if connect_error:
                    raise OSError(connect_error, "loopback connection failed")

            request = (
                f"GET {path} HTTP/1.1\r\nHost: 127.0.0.1:{APPROVED_PORT}\r\n"
                "Accept: text/plain\r\nUser-Agent: AegisAI-Local-Assessment/1\r\n"
                "Connection: close\r\n\r\n"
            ).encode("ascii")
            selector.register(sock, selectors.EVENT_WRITE)
            sent = 0
            while sent < len(request):
                _wait_for_socket(selector, selectors.EVENT_WRITE, request_deadline, assessment_deadline)
                sent += sock.send(request[sent:])
            selector.unregister(sock)

            response = bytearray()
            header_end = -1
            status: int | None = None
            headers: dict[str, str] = {}
            expected_body_bytes: int | None = None
            selector.register(sock, selectors.EVENT_READ)
            while True:
                _wait_for_socket(selector, selectors.EVENT_READ, request_deadline, assessment_deadline)
                chunk = sock.recv(min(4096, (2 * MAX_RESPONSE_BYTES + 5) - len(response)))
                if not chunk:
                    if header_end < 0 or (expected_body_bytes is not None and len(response) - header_end - 4 < expected_body_bytes):
                        raise OSError("incomplete local HTTP response")
                    break
                response.extend(chunk)
                if header_end < 0:
                    header_end = response.find(b"\r\n\r\n")
                    if header_end < 0:
                        if len(response) > MAX_RESPONSE_BYTES:
                            raise _ResponseLimitExceeded
                        continue
                    if header_end > MAX_RESPONSE_BYTES:
                        raise _ResponseLimitExceeded
                    status, headers = _parse_response_headers(bytes(response[:header_end]))
                    if "transfer-encoding" in headers:
                        raise OSError("unsupported local HTTP transfer encoding")
                    if "content-length" in headers:
                        try:
                            expected_body_bytes = int(headers["content-length"])
                        except ValueError as error:
                            raise OSError("invalid local HTTP response length") from error
                        if expected_body_bytes < 0:
                            raise OSError("invalid local HTTP response length")
                        if expected_body_bytes > MAX_RESPONSE_BYTES:
                            raise _ResponseLimitExceeded
                body_size = len(response) - header_end - 4
                if body_size > MAX_RESPONSE_BYTES:
                    raise _ResponseLimitExceeded
                if expected_body_bytes is not None and body_size >= expected_body_bytes:
                    body_start = header_end + 4
                    return status, headers, bytes(response[body_start:body_start + expected_body_bytes])
                if len(response) >= 2 * MAX_RESPONSE_BYTES + 5:
                    raise _ResponseLimitExceeded
            assert status is not None
            return status, headers, bytes(response[header_end + 4:])
    finally:
        sock.close()


class LocalAssessmentController:
    """Runs only fixed GET checks; it cannot perform simulator or response actions."""

    def __init__(self, policy: LocalAssessmentPolicy | None = None) -> None:
        self._policy = policy or LocalAssessmentPolicy()

    def run(self, checks: tuple[AssessmentCheck, ...] | list[AssessmentCheck]) -> AssessmentResult:
        if len(checks) > MAX_CHECKS_PER_ASSESSMENT:
            raise ValueError("assessment request-count limit exceeded")
        deadline = time.monotonic() + ASSESSMENT_DEADLINE_SECONDS
        decisions: list[AssessmentDecision] = []
        observations: list[AssessmentObservation] = []
        assessment_id = uuid4().hex
        assessment_started_at = datetime.now(timezone.utc)
        for check in checks:
            # Authorization occurs immediately before request construction and send.
            decision = self._policy.authorize(check)
            decisions.append(decision)
            if not decision.allowed:
                observations.append(self._make_observation(
                    check.check_id, decision, outcome="denied", duration_ms=0,
                    error_category="policy_denied", facts={"reason_code": decision.reason_code},
                ))
                continue
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                observations.append(self._make_observation(
                    check.check_id, decision, outcome="not_run_deadline", duration_ms=0,
                    error_category="deadline_exceeded", facts={"reason_code": "assessment_deadline_exceeded"},
                ))
                continue
            observation = self._execute(
                check, decision, assessment_id, deadline,
            )
            # The executor rechecks policy at the transport boundary; expose that final decision.
            decisions[-1] = observation.decision
            observations.append(observation)
        return AssessmentResult(run_id=assessment_id, started_at_utc=assessment_started_at,
                                decisions=tuple(decisions), observations=tuple(observations))

    @staticmethod
    def _make_observation(
        check_id: CheckId, decision: AssessmentDecision, *, outcome: str, duration_ms: int,
        facts: dict[str, str | int | bool | None], error_category: str | None = None,
        evidence: AssessmentEvidence | None = None,
    ) -> AssessmentObservation:
        definition = CHECK_CATALOG[check_id]
        status, observed_result = classify_result(check_id, decision, outcome, error_category, facts)
        return AssessmentObservation(
            check_id=check_id, category=definition.category, description=definition.description,
            severity=definition.severity, check_version=definition.version,
            configuration_version=CONFIGURATION_VERSION, expected_result=definition.expected_result,
            observed_result=observed_result, outcome_status=status, observed_at_utc=datetime.now(timezone.utc),
            decision=decision, outcome=outcome, duration_ms=duration_ms,
            error_category=error_category, facts=facts, evidence=evidence,
        )

    def _execute(
        self, check: AssessmentCheck, decision: AssessmentDecision,
        assessment_id: str, assessment_deadline: float,
    ) -> AssessmentObservation:
        if (not decision.allowed or decision.check_id is not check.check_id
                or decision.target_origin != check.target_origin):
            raise PermissionError("assessment policy approval required")
        started = time.monotonic()
        request_deadline = min(assessment_deadline, started + REQUEST_TIMEOUT_SECONDS)
        def observation(**fields):
            return self._make_observation(
                check.check_id, decision,
                duration_ms=min(4_000, max(0, int((time.monotonic() - started) * 1000))),
                **fields,
            )
        path = CHECK_PATHS[check.check_id]
        url = APPROVED_ORIGIN + path
        final_decision = self._policy.authorize(check)
        if not final_decision.allowed or final_decision != decision:
            decision = final_decision
            return observation(outcome="denied", error_category="policy_denied",
                               facts={"reason_code": decision.reason_code})
        try:
            status, headers, raw = _exchange_http(path, request_deadline, assessment_deadline)
            observed_at = datetime.now(timezone.utc)
            evidence = AssessmentEvidence(
                evidence_ref=f"web-assessment-{assessment_id}-{check.check_id.value}",
                observed_at_utc=observed_at, request_path=path, response_status=status,
                response_bytes=len(raw), response_sha256=hashlib.sha256(raw).hexdigest(),
            )
            facts: dict[str, str | int | bool | None] = {
                "status": status, "expected_status": 200, "status_matches_expectation": status == 200,
            }
            outcome = "observed"
            if check.check_id is CheckId.SECURITY_HEADERS:
                for name in SECURITY_HEADERS:
                    value = headers.get(name)
                    facts[name] = value[:512] if value is not None else None
                outcome = "headers_observed"
            elif check.check_id is CheckId.COOKIE_ATTRIBUTES:
                cookie = headers.get("set-cookie")
                if cookie is None:
                    facts.update(cookie_returned=False, secure=None, httponly=None, samesite=None)
                    outcome = "not_applicable_no_cookie"
                else:
                    lowered = cookie.lower()
                    facts.update(cookie_returned=True, secure="; secure" in f"; {lowered}",
                                 httponly="httponly" in lowered,
                                 samesite=next((value for part in cookie.split(";")
                                                if part.strip().lower().startswith("samesite=")
                                                for value in [part.split("=", 1)[1].strip().lower()]
                                                if value in {"strict", "lax", "none"}), None))
                    outcome = "cookie_attributes_observed"
            location = headers.get("location")
            if 300 <= status < 400:
                redirect_approved = _same_approved_origin(url, location)
                facts["redirect_followed"] = False
                facts["redirect_location_present"] = location is not None
                facts["redirect_target_approved"] = redirect_approved
                outcome = "redirect_not_followed" if redirect_approved else "redirect_denied_out_of_scope"
            return observation(outcome=outcome, facts=facts, evidence=evidence)
        except _ResponseLimitExceeded:
            return observation(outcome="response_too_large", error_category="response_limit_exceeded",
                               facts={"reason_code": "response_limit_exceeded"})
        except _AssessmentDeadlineExceeded:
            return observation(outcome="deadline_exceeded", error_category="deadline_exceeded",
                               facts={"reason_code": "assessment_deadline_exceeded"})
        except (_RequestTimedOut, TimeoutError, OSError):
            return observation(outcome="request_failed", error_category="request_failed",
                               facts={"reason_code": "local_request_failed"})


def _same_approved_origin(request_url: str, location: str | None) -> bool:
    """Classify a redirect target without opening it; all redirects remain unfollowed."""
    if not location:
        return False
    try:
        target = urlsplit(urljoin(request_url, location))
        return (
            target.scheme == "http" and target.hostname == "127.0.0.1"
            and target.port == APPROVED_PORT and target.username is None and target.password is None
            and target.path in CHECK_PATHS.values() and not target.query and not target.fragment
        )
    except (TypeError, ValueError):
        return False
