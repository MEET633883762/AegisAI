"""Loopback-only, read-only HTTP API for validated synthetic incident data."""

from __future__ import annotations

import ipaddress
import json
import re
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlsplit

from private_api.auth import LocalTokenRegistry, Principal
from private_api.models import (
    ErrorResponse,
    FindingsResponse,
    HealthResponse,
    IncidentsResponse,
    LiveWebsiteSourceStatusResponse,
    ProcessingStatusResponse,
    ProcessingRunSummary,
    TelemetryEvidenceResponse,
    TelemetryFindingsResponse,
    TelemetryReportResponse,
)
from private_api.store import SQLiteStore

MAX_REQUEST_BODY_BYTES = 16 * 1024
LOCAL_FRONTEND_ORIGINS = frozenset({
    "http://localhost:5174",
    "http://127.0.0.1:5174",
})
FINDING_ID_PATTERN = re.compile(r"^/api/findings/(finding-[a-f0-9]{12})/evidence$")
INCIDENT_ID_PATTERN = re.compile(r"^/api/incidents/(incident-[a-f0-9]{12})/report$")
TELEMETRY_FINDING_ID_PATTERN = re.compile(r"^/api/telemetry/findings/(tfinding-[a-f0-9]{12})/evidence$")


@dataclass(frozen=True)
class ApiResponse:
    status: int
    payload: dict[str, Any]


def _error(status: int, code: str, message: str) -> ApiResponse:
    response = ErrorResponse(error=code, message=message)
    return ApiResponse(status, response.model_dump(mode="json"))


class ApiApplication:
    """Request boundary; the authenticated principal supplies the only tenant scope."""

    def __init__(self, store: SQLiteStore, tokens: LocalTokenRegistry, *, scheduler_status=None) -> None:
        self.store = store
        self.tokens = tokens
        self.scheduler_status = scheduler_status or (lambda: "disabled")

    def _audit(
        self, *, tenant_id: str | None, event_type: str, method: str,
        route: str, outcome: str, details_code: str,
    ) -> bool:
        try:
            self.store.record_audit(
                tenant_id=tenant_id, event_type=event_type, method=method,
                route=route, outcome=outcome, details_code=details_code,
            )
            return True
        except Exception:
            return False

    @staticmethod
    def _route_name(path: str) -> tuple[str, str | None]:
        if path == "/health":
            return "health.read", None
        if path == "/api/findings":
            return "findings.list", None
        evidence_match = FINDING_ID_PATTERN.fullmatch(path)
        if evidence_match:
            return "findings.evidence", evidence_match.group(1)
        if path == "/api/incidents":
            return "incidents.list", None
        report_match = INCIDENT_ID_PATTERN.fullmatch(path)
        if report_match:
            return "incidents.report", report_match.group(1)
        if path == "/api/telemetry/findings":
            return "telemetry.findings", None
        evidence_match = TELEMETRY_FINDING_ID_PATTERN.fullmatch(path)
        if evidence_match:
            return "telemetry.evidence", evidence_match.group(1)
        if path == "/api/telemetry/reports/latest":
            return "telemetry.report", None
        if path == "/api/telemetry/sources/live-website/status":
            return "telemetry.source_status", None
        if path == "/api/processing":
            return "processing.read", None
        return "unknown", None

    @staticmethod
    def _required_scope(route: str) -> str | None:
        return {
            "health.read": "health:read",
            "findings.list": "findings:read",
            "findings.evidence": "evidence:read",
            "incidents.list": "incidents:read",
            "incidents.report": "reports:read",
            "telemetry.findings": "telemetry:read",
            "telemetry.evidence": "evidence:read",
            "telemetry.report": "reports:read",
            "telemetry.source_status": "telemetry:read",
            "processing.read": "processing:read",
        }.get(route)

    def _perform(self, principal: Principal, route: str, identifier: str | None) -> ApiResponse:
        tenant_id = principal.tenant_id
        if route == "health.read":
            if not self.store.ping():
                raise RuntimeError("health unavailable")
            return ApiResponse(200, HealthResponse(status="ok", mode="local_synthetic").model_dump(mode="json"))
        if route == "findings.list":
            return ApiResponse(200, FindingsResponse(
                data_classification="synthetic", label="SYNTHETIC - NOT REAL CLIENT DATA",
                tenant_id=tenant_id, findings=self.store.list_findings(tenant_id),
            ).model_dump(mode="json"))
        if route == "findings.evidence":
            evidence = self.store.get_evidence(tenant_id, identifier or "")
            if evidence is None:
                return _error(404, "not_found", "The requested resource was not found.")
            from private_api.models import EvidenceResponse
            return ApiResponse(200, EvidenceResponse(
                data_classification="synthetic", label="SYNTHETIC - NOT REAL CLIENT DATA",
                tenant_id=tenant_id, finding_id=identifier or "", evidence=evidence,
            ).model_dump(mode="json"))
        if route == "incidents.list":
            return ApiResponse(200, IncidentsResponse(
                data_classification="synthetic", label="SYNTHETIC - NOT REAL CLIENT DATA",
                tenant_id=tenant_id, incidents=self.store.list_incidents(tenant_id),
            ).model_dump(mode="json"))
        if route == "incidents.report":
            report = self.store.get_incident_report(tenant_id, identifier or "")
            if report is None:
                return _error(404, "not_found", "The requested resource was not found.")
            return ApiResponse(200, report.model_dump(mode="json"))
        if route == "telemetry.findings":
            return ApiResponse(200, TelemetryFindingsResponse(
                data_classification="synthetic", label="SYNTHETIC - NOT REAL CLIENT DATA",
                tenant_id=tenant_id, findings=self.store.list_telemetry_findings(tenant_id),
            ).model_dump(mode="json"))
        if route == "telemetry.evidence":
            evidence = self.store.list_telemetry_evidence(tenant_id, identifier or "")
            if evidence is None:
                return _error(404, "not_found", "The requested resource was not found.")
            return ApiResponse(200, TelemetryEvidenceResponse(
                data_classification="synthetic", label="SYNTHETIC - NOT REAL CLIENT DATA",
                tenant_id=tenant_id, finding_id=identifier or "", evidence=evidence,
            ).model_dump(mode="json"))
        if route == "telemetry.report":
            report = self.store.latest_telemetry_report(tenant_id)
            if report is None:
                return _error(404, "not_found", "The requested resource was not found.")
            return ApiResponse(200, TelemetryReportResponse(report=report).model_dump(mode="json"))
        if route == "telemetry.source_status":
            status = self.store.live_source_status(tenant_id)
            if status is None:
                return _error(404, "not_found", "The requested resource was not found.")
            return ApiResponse(200, LiveWebsiteSourceStatusResponse(
                data_classification="synthetic", label="SYNTHETIC - NOT REAL CLIENT DATA",
                tenant_id=tenant_id, source_key=self.store.LIVE_SOURCE_KEY, **status,
            ).model_dump(mode="json"))
        if route == "processing.read":
            latest = self.store.latest_telemetry_run(tenant_id)
            return ApiResponse(200, ProcessingStatusResponse(
                data_classification="synthetic", label="SYNTHETIC - NOT REAL CLIENT DATA",
                tenant_id=tenant_id, scheduler_state=self.scheduler_status(), interval_seconds=600,
                latest_run=ProcessingRunSummary.model_validate(latest) if latest else None,
            ).model_dump(mode="json"))
        return _error(404, "not_found", "The requested resource was not found.")

    def handle(
        self,
        *,
        method: str,
        target: str,
        authorization: str | None,
        body_length: int = 0,
        body: bytes = b"",
    ) -> ApiResponse:
        if body_length < 0:
            self._audit(tenant_id=None, event_type="request_rejected", method=method,
                        route="unknown", outcome="rejected", details_code="invalid_content_length")
            return _error(400, "bad_request", "The request could not be processed.")
        if body_length > MAX_REQUEST_BODY_BYTES:
            self._audit(tenant_id=None, event_type="request_rejected", method=method,
                        route="unknown", outcome="rejected", details_code="request_too_large")
            return _error(413, "request_too_large", "The request exceeds the allowed size.")

        authentication = self.tokens.authenticate(authorization)
        principal = authentication.principal
        if principal is None:
            self._audit(tenant_id=None, event_type="authentication_failure", method=method,
                        route="unknown", outcome="denied", details_code=authentication.reason)
            return _error(401, "unauthorized", "Authentication is required.")

        route_guess = "unknown"
        try:
            parsed = urlsplit(target)
            route_guess, _ = self._route_name(parsed.path)
        except ValueError:
            parsed = None
        if method != "GET":
            self._audit(tenant_id=principal.tenant_id, event_type="access_denial", method=method,
                        route=route_guess, outcome="denied", details_code="method_not_allowed")
            return _error(405, "method_not_allowed", "This operation is read-only.")
        if body_length != 0 or body:
            self._audit(tenant_id=principal.tenant_id, event_type="request_rejected", method=method,
                        route=route_guess, outcome="rejected", details_code="unexpected_request_body")
            return _error(400, "bad_request", "The request could not be processed.")
        if parsed is None or parsed.scheme or parsed.netloc or parsed.fragment:
            self._audit(tenant_id=principal.tenant_id, event_type="access_denial", method=method,
                        route="unknown", outcome="denied", details_code="invalid_request_target")
            return _error(400, "bad_request", "The request could not be processed.")
        route, identifier = self._route_name(parsed.path)
        if parsed.query:
            self._audit(tenant_id=principal.tenant_id, event_type="access_denial", method=method,
                        route=route, outcome="denied", details_code="query_parameters_not_supported")
            return _error(400, "bad_request", "The request could not be processed.")
        scope = self._required_scope(route)
        if scope is None:
            self._audit(tenant_id=principal.tenant_id, event_type="access_denial", method=method,
                        route="unknown", outcome="not_found", details_code="route_not_found")
            return _error(404, "not_found", "The requested resource was not found.")
        if not principal.allows(scope):
            self._audit(tenant_id=principal.tenant_id, event_type="access_denial", method=method,
                        route=route, outcome="denied", details_code="insufficient_scope")
            return _error(403, "forbidden", "Permission is insufficient for this operation.")

        try:
            response = self._perform(principal, route, identifier)
        except Exception:
            audit_ok = self._audit(
                tenant_id=principal.tenant_id, event_type="protected_operation", method=method,
                route=route, outcome="error", details_code="internal_error",
            )
            if not audit_ok:
                return _error(503, "temporarily_unavailable", "The service is temporarily unavailable.")
            return _error(500, "internal_error", "The service could not complete the request.")

        outcome = "success" if response.status < 400 else "not_found"
        audit_ok = self._audit(
            tenant_id=principal.tenant_id, event_type="protected_operation", method=method,
            route=route, outcome=outcome, details_code="completed" if outcome == "success" else "not_found",
        )
        if not audit_ok:
            return _error(503, "temporarily_unavailable", "The service is temporarily unavailable.")
        return response


class LocalApiHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, address: tuple[str, int], app: ApiApplication) -> None:
        self.app = app
        super().__init__(address, LocalApiRequestHandler)


class LocalApiRequestHandler(BaseHTTPRequestHandler):
    server_version = "AegisAI-Local"
    sys_version = ""

    def log_message(self, format: str, *args: Any) -> None:
        # The standard logger includes raw paths. Audit events record fixed route names only.
        return

    def _write_json(self, status: int, payload: dict[str, Any], *, cors_origin: str | None = None) -> None:
        encoded = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Vary", "Origin")
        if cors_origin in LOCAL_FRONTEND_ORIGINS:
            self.send_header("Access-Control-Allow-Origin", cors_origin)
        self.send_header("Connection", "close")
        self.end_headers()
        try:
            self.wfile.write(encoded)
        except (BrokenPipeError, ConnectionResetError):
            pass
        self.close_connection = True

    def send_error(self, code: int, message: str | None = None, explain: str | None = None) -> None:
        mapped = {
            400: ("bad_request", "The request could not be processed."),
            414: ("uri_too_long", "The request target is too long."),
            431: ("headers_too_large", "The request headers exceed the allowed size."),
        }.get(code, ("bad_request", "The request could not be processed."))
        self._write_json(code, ErrorResponse(error=mapped[0], message=mapped[1]).model_dump(mode="json"))

    def _handle(self) -> None:
        length_values = self.headers.get_all("Content-Length", [])
        if len(length_values) > 1 or self.headers.get("Transfer-Encoding") is not None:
            response = self.server.app.handle(
                method=self.command, target=self.path,
                authorization=self.headers.get("Authorization"), body_length=-1,
            )
            self._write_json(response.status, response.payload, cors_origin=self.headers.get("Origin"))
            return
        raw_length = length_values[0] if length_values else "0"
        if not re.fullmatch(r"[0-9]+", raw_length):
            content_length = -1
        else:
            content_length = int(raw_length)
        if content_length > MAX_REQUEST_BODY_BYTES:
            response = self.server.app.handle(
                method=self.command, target=self.path,
                authorization=self.headers.get("Authorization"), body_length=content_length,
            )
            self._write_json(response.status, response.payload, cors_origin=self.headers.get("Origin"))
            return
        body = self.rfile.read(max(0, content_length)) if content_length > 0 else b""
        response = self.server.app.handle(
            method=self.command, target=self.path,
            authorization=self.headers.get("Authorization"),
            body_length=content_length, body=body,
        )
        self._write_json(response.status, response.payload, cors_origin=self.headers.get("Origin"))

    def do_OPTIONS(self) -> None:  # noqa: N802 - stdlib handler method
        origin = self.headers.get("Origin")
        requested_method = self.headers.get("Access-Control-Request-Method", "").upper()
        requested_headers = {
            value.strip().lower()
            for value in self.headers.get("Access-Control-Request-Headers", "").split(",")
            if value.strip()
        }
        if (origin not in LOCAL_FRONTEND_ORIGINS or requested_method != "GET"
                or not requested_headers.issubset({"authorization"})):
            self._write_json(403, {"error": "cors_denied", "message": "Browser access is not allowed."})
            return
        self.send_response(204)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Origin", origin)
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Authorization")
        self.send_header("Access-Control-Max-Age", "300")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler method
        self._handle()

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler method
        self._handle()

    def do_PUT(self) -> None:  # noqa: N802 - stdlib handler method
        self._handle()

    def do_PATCH(self) -> None:  # noqa: N802 - stdlib handler method
        self._handle()

    def do_DELETE(self) -> None:  # noqa: N802 - stdlib handler method
        self._handle()


def create_local_server(app: ApiApplication, *, port: int = 8766) -> LocalApiHTTPServer:
    host = "127.0.0.1"
    if not ipaddress.ip_address(host).is_loopback:
        raise ValueError("the development API must bind to a loopback address")
    return LocalApiHTTPServer((host, port), app)
