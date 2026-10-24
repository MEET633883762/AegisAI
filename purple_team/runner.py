"""Preview and bounded execution for fixed synthetic local website scenarios."""

from __future__ import annotations

import errno
import selectors
import socket
import time
from datetime import datetime, timezone
from uuid import uuid4

from local_assessment.policy import APPROVED_PORT
from private_api.live_website_connector import read_live_website_log_snapshot
from private_api.live_website_ingestion import ingest_live_local_website_logs
from private_api.store import SQLiteStore
from private_api.telemetry import TelemetryEventType, TelemetryFinding, TelemetryReport
from private_api.website_ingestion import FIXED_TENANT_ID
from purple_team.catalog import CATALOG_VERSION, SCENARIOS
from purple_team.models import (
    ScenarioComparison, ScenarioExecutionReport, ScenarioFindingEvidence,
    ScenarioPolicyDecision, ScenarioTelemetryEvidence,
)
from purple_team.policy import APPROVED_ORIGIN, LocalScenarioPolicy

REQUEST_TIMEOUT_SECONDS = 1.0
SCENARIO_DEADLINE_SECONDS = 4.0
MAX_RESPONSE_BYTES = 16_384


class _ScenarioRequestError(Exception):
    pass


def _exchange(method: str, path: str, deadline: float) -> tuple[int, int]:
    """Perform one fixed-origin request using nonblocking, deadline-aware socket I/O."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    request_deadline = min(deadline, time.monotonic() + REQUEST_TIMEOUT_SECONDS)
    try:
        sock.setblocking(False)
        with selectors.DefaultSelector() as selector:
            result = sock.connect_ex(("127.0.0.1", APPROVED_PORT))
            if result not in (0, errno.EISCONN):
                pending = {errno.EINPROGRESS, errno.EWOULDBLOCK, errno.EALREADY, errno.EINTR, 10035, 10036, 10037}
                if result not in pending:
                    raise _ScenarioRequestError("connection_failed")
                selector.register(sock, selectors.EVENT_WRITE)
                _wait(selector, sock, selectors.EVENT_WRITE, request_deadline, deadline)
                selector.unregister(sock)
                if sock.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR):
                    raise _ScenarioRequestError("connection_failed")

            headers = (
                f"{method} {path} HTTP/1.1\r\nHost: 127.0.0.1:{APPROVED_PORT}\r\n"
                "Accept: text/plain\r\nUser-Agent: AegisAI-Synthetic-Scenario/1\r\n"
                "Connection: close\r\nContent-Length: 0\r\n\r\n"
            ).encode("ascii")
            selector.register(sock, selectors.EVENT_WRITE)
            sent = 0
            while sent < len(headers):
                _wait(selector, sock, selectors.EVENT_WRITE, request_deadline, deadline)
                sent += sock.send(headers[sent:])
            selector.unregister(sock)

            response = bytearray()
            selector.register(sock, selectors.EVENT_READ)
            while b"\r\n\r\n" not in response:
                _wait(selector, sock, selectors.EVENT_READ, request_deadline, deadline)
                chunk = sock.recv(4096)
                if not chunk:
                    raise _ScenarioRequestError("incomplete_response")
                response.extend(chunk)
                if len(response) > MAX_RESPONSE_BYTES:
                    raise _ScenarioRequestError("response_limit_exceeded")
            marker = response.find(b"\r\n\r\n")
            header_block = bytes(response[:marker])
            status_line = header_block.split(b"\r\n", 1)[0]
            parts = status_line.split(b" ", 2)
            if len(parts) < 2 or not parts[1].isdigit():
                raise _ScenarioRequestError("malformed_response")
            status = int(parts[1])
            response_headers: dict[bytes, bytes] = {}
            for line in header_block.split(b"\r\n")[1:]:
                key, separator, value = line.partition(b":")
                if not separator:
                    raise _ScenarioRequestError("malformed_response")
                response_headers[key.strip().lower()] = value.strip()
            if 300 <= status < 400:
                # Redirects are never followed, including same-origin redirects.
                raise _ScenarioRequestError("redirect_not_followed")
            if b"transfer-encoding" in response_headers:
                raise _ScenarioRequestError("unsupported_response_encoding")
            raw_length = response_headers.get(b"content-length")
            if raw_length is None or not raw_length.isdigit():
                raise _ScenarioRequestError("malformed_response")
            body_length = int(raw_length)
            if body_length > MAX_RESPONSE_BYTES:
                raise _ScenarioRequestError("response_limit_exceeded")
            body_start = marker + 4
            while len(response) - body_start < body_length:
                _wait(selector, sock, selectors.EVENT_READ, request_deadline, deadline)
                chunk = sock.recv(min(4096, body_length - (len(response) - body_start)))
                if not chunk:
                    raise _ScenarioRequestError("incomplete_response")
                response.extend(chunk)
            return status, body_length
    except (OSError, ValueError) as exc:
        if isinstance(exc, _ScenarioRequestError):
            raise
        raise _ScenarioRequestError("request_failed") from None
    finally:
        sock.close()


def _wait(selector, sock, events: int, request_deadline: float, overall_deadline: float) -> None:
    now = time.monotonic()
    if now >= overall_deadline:
        raise _ScenarioRequestError("deadline_exceeded")
    if now >= request_deadline:
        raise _ScenarioRequestError("request_timeout")
    if not selector.select(min(request_deadline - now, overall_deadline - now)):
        raise _ScenarioRequestError("request_timeout")


class LocalPurpleTeamRunner:
    def __init__(self, store: SQLiteStore, *, policy: LocalScenarioPolicy | None = None,
                 request=_exchange, snapshot_reader=read_live_website_log_snapshot,
                 ingest=ingest_live_local_website_logs) -> None:
        self._store = store
        self._policy = policy or LocalScenarioPolicy()
        self._request = request
        self._snapshot_reader = snapshot_reader
        self._ingest = ingest

    @staticmethod
    def preview(scenario_id: str | None = None) -> list[dict[str, object]]:
        scenarios = [SCENARIOS[scenario_id]] if scenario_id in SCENARIOS else list(SCENARIOS.values())
        if scenario_id is not None and scenario_id not in SCENARIOS:
            raise ValueError("scenario is not in the reviewed catalog")
        return [{
            "catalog_version": CATALOG_VERSION, **scenario.model_dump(mode="json"),
            "target_origin": APPROVED_ORIGIN, "execution": "preview_only",
        } for scenario in scenarios]

    def _execute(self, scenario_id: str, scenario, *, explicitly_authorized: bool,
                 decision: ScenarioPolicyDecision, deadline: float):
        request_statuses: list[int] = []
        telemetry_evidence: tuple[ScenarioTelemetryEvidence, ...] = ()
        observed_findings: tuple[ScenarioFindingEvidence, ...] = ()
        telemetry_report: TelemetryReport | None = None
        error_category = None
        try:
            baseline_ids = {event.event_id for event in self._snapshot_reader().batch.events}
        except Exception:
            baseline_ids = set()
        for _ in range(decision.maximum_requests):
            # Fresh policy decision directly before every network operation.
            current = self._policy.authorize(scenario_id, explicitly_authorized=explicitly_authorized)
            if not current.allowed or current != decision:
                error_category = "policy_denied"
                break
            try:
                status, _response_bytes = self._request(scenario.request_method, scenario.request_path, deadline)
                request_statuses.append(status)
                if status != scenario.expected_status:
                    error_category = "unexpected_http_status"
                    break
            except Exception as exc:
                error_category = str(exc) if isinstance(exc, _ScenarioRequestError) else "request_failed"
                break
        if error_category is None:
            try:
                after = self._snapshot_reader().batch.events
                new_events = [event for event in after if event.event_id not in baseline_ids]
                matched_events = [event for event in new_events
                                  if event.event_type.value == scenario.expected_telemetry_type
                                  and event.route_code == scenario.expected_route_code
                                  and event.status_code == scenario.expected_status]
                if len(matched_events) > scenario.expected_count:
                    error_category = "ambiguous_source_activity"
                telemetry_evidence = tuple(ScenarioTelemetryEvidence(
                    event_id=event.event_id, evidence_ref=event.evidence_ref,
                    event_type=event.event_type.value, route_code=event.route_code or "",
                    status_code=event.status_code or 0, occurred_at_utc=event.occurred_at,
                ) for event in matched_events[:3])
                telemetry_report = self._ingest(self._store)
                matching_ids = {item.event_id for item in telemetry_evidence}
                matched_refs = {item.evidence_ref for item in telemetry_evidence}
                observed_findings = tuple(ScenarioFindingEvidence(
                    finding_id=finding.finding_id, rule_id=finding.rule_id,
                    evidence_refs=tuple(sorted(set(finding.evidence_refs).intersection(matched_refs))[:3]),
                ) for finding in telemetry_report.findings
                    if matching_ids.intersection(finding.event_ids)
                    and matching_ids.issubset(set(finding.event_ids)))
            except Exception:
                error_category = "telemetry_processing_error"
        return request_statuses, error_category, telemetry_evidence, observed_findings, telemetry_report

    def run(self, scenario_id: str, *, explicitly_authorized: bool = False) -> ScenarioExecutionReport:
        scenario = SCENARIOS.get(scenario_id)
        if scenario is None:
            decision = self._policy.authorize(scenario_id, explicitly_authorized=explicitly_authorized)
            raise PermissionError(decision.reason_code)
        decision = self._policy.authorize(scenario_id, explicitly_authorized=explicitly_authorized)
        started = datetime.now(timezone.utc)
        started_mono = time.monotonic()
        deadline = started_mono + SCENARIO_DEADLINE_SECONDS
        request_statuses: list[int] = []
        error_category = None
        telemetry_evidence: tuple[ScenarioTelemetryEvidence, ...] = ()
        observed_findings: tuple[ScenarioFindingEvidence, ...] = ()
        telemetry_report: TelemetryReport | None = None
        slot_token = uuid4().hex
        slot_acquired = False
        if decision.allowed:
            slot_acquired = self._store.acquire_purple_scenario_slot(FIXED_TENANT_ID, slot_token)
            if not slot_acquired:
                error_category = "concurrency_limit"
        if slot_acquired:
            try:
                (request_statuses, error_category, telemetry_evidence,
                 observed_findings, telemetry_report) = self._execute(
                    scenario_id, scenario, explicitly_authorized=explicitly_authorized,
                    decision=decision, deadline=deadline,
                )
            finally:
                self._store.release_purple_scenario_slot(FIXED_TENANT_ID, slot_token)

        expected_rules = set(scenario.expected_detection_rule_ids)
        observed_rules = {item.rule_id for item in observed_findings}
        passed = (
            decision.allowed and error_category is None
            and len(request_statuses) == scenario.expected_count
            and len(telemetry_evidence) == scenario.expected_count
            and observed_rules == expected_rules
        )
        if not decision.allowed or error_category == "concurrency_limit":
            status = "NOT_RUN"
        elif error_category:
            status = "ERROR"
        else:
            status = "PASSED" if passed else "FAILED"
        previous = self._store.latest_purple_scenario_run(FIXED_TENANT_ID, scenario_id)
        comparison = ScenarioComparison(
            previous_run_id=previous.run_id if previous else None,
            previous_status=previous.status if previous else None,
            outcome_changed=(previous.status != status) if previous else None,
        )
        completed = datetime.now(timezone.utc)
        report = ScenarioExecutionReport(
            scenario_id=scenario.scenario_id, scenario_version=scenario.version, status=status,
            started_at_utc=started, completed_at_utc=completed, policy_decision=decision,
            error_category=error_category,
            expected_telemetry_type=scenario.expected_telemetry_type,
            expected_route_code=scenario.expected_route_code, expected_status=scenario.expected_status,
            expected_count=scenario.expected_count, observed_http_statuses=tuple(request_statuses),
            observed_telemetry=telemetry_evidence,
            expected_detection_rule_ids=scenario.expected_detection_rule_ids,
            observed_findings=observed_findings, assessment_check_ids=scenario.assessment_check_ids,
            telemetry_report_id=telemetry_report.report_id if telemetry_report else None,
            telemetry_run_id=telemetry_report.run_id if telemetry_report else None,
            comparison=comparison,
            limitations=(
                "This is synthetic loopback scenario validation, not evidence of real-world control effectiveness.",
                "Observed logs and findings are reused from the fixed local synthetic telemetry pipeline.",
                "The catalog records expected detection rules separately from observed findings.",
                f"Sanitized execution error category: {error_category}." if error_category else "No execution error was reported.",
            ),
        )
        self._store.save_purple_scenario_run(FIXED_TENANT_ID, report)
        return report
