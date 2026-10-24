"""Loopback-only API for validated synthetic data and bounded human-led investigation cases."""

from __future__ import annotations

import ipaddress
import json
import re
import threading
from dataclasses import dataclass
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlsplit
from pydantic import ValidationError

from platform_prototype.evaluation import MAX_REPORT_BYTES, EvaluationReport
from platform_prototype.evaluation_history import read_evaluation_history
from private_api.auth import LocalTokenRegistry, Principal
from private_api.executive_reports import (
    ExecutiveObservation,
    ExecutiveReportInputError,
    build_executive_report,
)
from private_api.models import (
    DetectionEvaluationResponse,
    DetectionEvaluationSummary,
    DetectionRuleSummary,
    ErrorResponse,
    ExecutiveReportResponse,
    FindingsResponse,
    HealthResponse,
    ReadinessResponse,
    IncidentsResponse,
    LiveWebsiteSourceStatusResponse,
    LocalAssessmentReportResponse,
    AssessmentHistoryEntry,
    PurpleScenarioRunsResponse,
    ProcessingStatusResponse,
    ProcessingRunSummary,
    TelemetryEvidenceResponse,
    TelemetryFindingsResponse,
    TelemetryReportResponse,
)
from private_api.store import SQLiteStore
from private_api.telemetry import SyntheticTelemetryEvent, TelemetryFinding
from private_api.investigations import (
    AddAnalystNoteRequest, AddContextRequest, AddEvidenceLinkRequest, AddFindingLinkRequest,
    CaseContextReference, CaseEvidenceLink, CaseFindingLink, CaseNote, CaseRecommendation,
    CaseTimelineEntry, CreateCaseRequest, InvestigationCase, InvestigationCaseResponse,
    InvestigationCasesResponse, UpdateCaseStatusRequest,
)
from purple_team.catalog import SCENARIOS as PURPLE_SCENARIOS

MAX_REQUEST_BODY_BYTES = 16 * 1024
MAX_CONCURRENT_REQUESTS = 32
REQUEST_SOCKET_TIMEOUT_SECONDS = 5
LOCAL_FRONTEND_ORIGINS = frozenset({
    "http://localhost:5174",
    "http://127.0.0.1:5174",
})
FINDING_ID_PATTERN = re.compile(r"^/api/findings/(finding-[a-f0-9]{12})/evidence$")
INCIDENT_ID_PATTERN = re.compile(r"^/api/incidents/(incident-[a-f0-9]{12})/report$")
TELEMETRY_FINDING_ID_PATTERN = re.compile(r"^/api/telemetry/findings/(tfinding-[a-f0-9]{12})/evidence$")
INVESTIGATION_CASE_ID_PATTERN = re.compile(r"^/api/investigations/cases/(case-[a-f0-9]{16})$")
INVESTIGATION_CASE_ACTION_PATTERN = re.compile(
    r"^/api/investigations/cases/(case-[a-f0-9]{16})/(findings|evidence|notes|status|context)$"
)
EVALUATION_REPORT_PATH = Path(__file__).resolve().parents[1] / "results" / "evaluation" / "phase6b_detection_evaluation_v1.json"
EVALUATION_HISTORY_DATABASE_PATH = Path(__file__).resolve().parents[1] / ".aegisai-local" / "detection_evaluation_history.sqlite3"


@dataclass(frozen=True)
class ApiResponse:
    status: int
    payload: dict[str, Any]


def _error(status: int, code: str, message: str) -> ApiResponse:
    response = ErrorResponse(error=code, message=message)
    return ApiResponse(status, response.model_dump(mode="json"))


def _load_detection_evaluation_summary() -> DetectionEvaluationSummary | None:
    """Read a bounded fixed report and omit scenario-level diagnostics from responses."""
    try:
        report, history = read_evaluation_history(EVALUATION_HISTORY_DATABASE_PATH)
        if report is None:
            with EVALUATION_REPORT_PATH.open("rb") as source:
                raw = source.read(MAX_REPORT_BYTES + 1)
            if len(raw) > MAX_REPORT_BYTES:
                return None
            # Validate the fixed CLI output contract before projecting its summary.
            report = EvaluationReport.model_validate_json(raw)
        counts = report.counts
        return DetectionEvaluationSummary(
            schema_version=report.schema_version,
            report_type=report.report_type,
            dataset_id=report.dataset_id,
            dataset_version=report.dataset_version,
            dataset_sha256=report.dataset_sha256,
            detector_config_sha256=report.detector_config_sha256,
            rule_catalog_version=report.rule_catalog_version,
            detector_rule_version=report.detector_rule_version,
            scenario_rule_mapping_version=report.scenario_rule_mapping_version,
            attack_mapping_catalog_version=report.attack_mapping_catalog_version,
            counting_unit=report.counting_unit,
            counts=counts,
            metrics=report.metrics,
            total_evaluated_pairs=(counts.true_positives + counts.false_positives
                                   + counts.true_negatives + counts.false_negatives),
            per_rule=[DetectionRuleSummary(rule_id=item.rule_id, counts=item.counts, metrics=item.metrics)
                      for item in report.per_rule],
            rule_event_mapping=report.rule_event_mapping,
            scenario_rule_mapping=report.scenario_rule_mapping,
            technique_coverage=report.technique_coverage,
            untested_techniques=report.untested_techniques,
            coverage_status=report.coverage_status,
            warnings=report.warnings,
            valid_scenario_count=report.valid_scenario_count,
            rejected_scenario_count=report.rejected_scenario_count,
            history=history,
            limitations=report.limitations,
        )
    except Exception:
        # Keep filesystem, validation, and detector errors out of the public response.
        return None


class ApiApplication:
    """Request boundary; the authenticated principal supplies the only tenant scope."""

    def __init__(self, store: SQLiteStore, tokens: LocalTokenRegistry, *, scheduler_status=None) -> None:
        self.store = store
        self.tokens = tokens
        self.scheduler_status = scheduler_status or (lambda: "disabled")
        self.detection_evaluation = _load_detection_evaluation_summary()

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
    def _route_name(path: str, method: str = "GET") -> tuple[str, str | None]:
        if path == "/api/investigations/cases":
            return ("investigations.create" if method == "POST" else "investigations.list"), None
        case_match = INVESTIGATION_CASE_ID_PATTERN.fullmatch(path)
        if case_match and method == "GET":
            return "investigations.detail", case_match.group(1)
        action_match = INVESTIGATION_CASE_ACTION_PATTERN.fullmatch(path)
        if action_match and method == "POST":
            return f"investigations.{action_match.group(2)}", action_match.group(1)
        if path == "/health":
            return "health.read", None
        if path == "/ready":
            return "readiness.read", None
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
        if path == "/api/reports/executive/latest":
            return "executive.report", None
        if path == "/api/assessment/reports/latest":
            return "assessment.report", None
        if path == "/api/purple-team/scenarios/runs":
            return "purple.scenario_runs", None
        if path == "/api/evaluation/reports/latest":
            return "evaluation.report", None
        if path == "/api/telemetry/sources/live-website/status":
            return "telemetry.source_status", None
        if path == "/api/processing":
            return "processing.read", None
        return "unknown", None

    @staticmethod
    def _required_scope(route: str) -> str | None:
        return {
            "health.read": "health:read",
            "readiness.read": "health:read",
            "findings.list": "findings:read",
            "findings.evidence": "evidence:read",
            "incidents.list": "incidents:read",
            "incidents.report": "reports:read",
            "telemetry.findings": "telemetry:read",
            "telemetry.evidence": "evidence:read",
            "telemetry.report": "reports:read",
            "executive.report": "reports:read",
            "assessment.report": "reports:read",
            "purple.scenario_runs": "reports:read",
            "evaluation.report": "reports:read",
            "telemetry.source_status": "telemetry:read",
            "processing.read": "processing:read",
            "investigations.list": "investigations:read",
            "investigations.detail": "investigations:read",
            "investigations.create": "investigations:write",
            "investigations.findings": "investigations:write",
            "investigations.evidence": "investigations:write",
            "investigations.notes": "investigations:write",
            "investigations.status": "investigations:write",
            "investigations.context": "investigations:write",
        }.get(route)

    def _perform(self, principal: Principal, route: str, identifier: str | None,
                 *, body: dict[str, Any] | None = None, query: dict[str, list[str]] | None = None) -> ApiResponse:
        tenant_id = principal.tenant_id
        if route == "health.read":
            if not self.store.ping():
                raise RuntimeError("health unavailable")
            return ApiResponse(200, HealthResponse(status="ok", mode="local_synthetic").model_dump(mode="json"))
        if route == "readiness.read":
            if not self.store.ping():
                raise RuntimeError("readiness unavailable")
            return ApiResponse(200, ReadinessResponse(
                status="ready", mode="local_synthetic",
            ).model_dump(mode="json"))
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
        if route == "executive.report":
            findings = self.store.list_telemetry_findings(tenant_id)
            evidence = []
            for finding in findings:
                references = self.store.list_telemetry_evidence(tenant_id, finding.finding_id)
                if references is None:
                    return _error(
                        503, "temporarily_unavailable",
                        "The executive report is temporarily unavailable.",
                    )
                evidence.extend(
                    ExecutiveObservation(
                        evidence_ref=item.evidence_ref,
                        event_id=item.event_id,
                        event_type=item.event_type,
                        occurred_at_utc=item.occurred_at_utc,
                    )
                    for item in references
                )
            try:
                report = build_executive_report(
                    tenant_id=tenant_id, findings=findings, evidence=evidence,
                )
            except ExecutiveReportInputError:
                return _error(
                    503, "temporarily_unavailable",
                    "The executive report is temporarily unavailable.",
                )
            return ApiResponse(200, ExecutiveReportResponse(
                data_classification="synthetic",
                label="SYNTHETIC - NOT REAL CLIENT DATA",
                tenant_id=tenant_id,
                report=report,
            ).model_dump(mode="json"))
        if route == "assessment.report":
            report = self.store.latest_assessment_report(tenant_id)
            history = [AssessmentHistoryEntry.model_validate(item) for item in self.store.assessment_report_history(tenant_id)]
            return ApiResponse(200, LocalAssessmentReportResponse(
                data_classification="synthetic", label="LOCAL SYNTHETIC WEBSITE ASSESSMENT",
                tenant_id=tenant_id, report=report, history=history,
            ).model_dump(mode="json"))
        if route == "purple.scenario_runs":
            runs = self.store.list_purple_scenario_runs(tenant_id)
            if any(run.scenario_id not in PURPLE_SCENARIOS
                   or run.scenario_version != PURPLE_SCENARIOS[run.scenario_id].version for run in runs):
                return _error(503, "temporarily_unavailable", "Scenario history is temporarily unavailable.")
            return ApiResponse(200, PurpleScenarioRunsResponse(
                tenant_id=tenant_id, runs=runs,
            ).model_dump(mode="json"))
        if route == "evaluation.report":
            if self.detection_evaluation is None:
                return _error(503, "temporarily_unavailable", "The synthetic evaluation report is temporarily unavailable.")
            return ApiResponse(200, DetectionEvaluationResponse(
                data_classification="synthetic",
                label="SYNTHETIC EVALUATION - NOT REAL SECURITY PERFORMANCE",
                tenant_id=tenant_id,
                report=self.detection_evaluation,
            ).model_dump(mode="json"))
        if route == "telemetry.source_status":
            status = self.store.live_source_status(tenant_id)
            if status is None:
                return ApiResponse(200, LiveWebsiteSourceStatusResponse(
                    data_classification="synthetic", label="SYNTHETIC - NOT REAL CLIENT DATA",
                    tenant_id=tenant_id, source_key=self.store.LIVE_SOURCE_KEY,
                    last_attempt_at_utc=None, last_success_at_utc=None, status="unavailable",
                    input_event_count=None, accepted_event_count=None, duplicate_event_count=None,
                    rejected_record_count=None, position_sha256=None, position_bytes=None, error_code=None,
                ).model_dump(mode="json"))
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
        if route == "investigations.list":
            values = query or {}
            if set(values) - {"q", "status"} or any(len(items) != 1 for items in values.values()):
                return _error(400, "bad_request", "The investigation filter is invalid.")
            search = values.get("q", [""])[0]
            status = values.get("status", [None])[0]
            if len(search) > 80 or status not in {None, "open", "under_review", "closed"}:
                return _error(400, "bad_request", "The investigation filter is invalid.")
            cases = self.store.list_investigation_cases(tenant_id, status=status, search=search or None)
            return ApiResponse(200, InvestigationCasesResponse(tenant_id=tenant_id, cases=cases).model_dump(mode="json"))
        if route == "investigations.create":
            case_id = self.store.create_investigation_case(tenant_id, CreateCaseRequest.model_validate(body or {}))
            return ApiResponse(201, {"tenant_id": tenant_id, "case_id": case_id})
        if route == "investigations.detail":
            record = self.store.get_investigation_case(tenant_id, identifier or "")
            if record is None:
                return _error(404, "not_found", "The requested resource was not found.")
            finding_links = [CaseFindingLink.model_validate(item) for item in record["findings"]]
            evidence_links = [CaseEvidenceLink.model_validate(item) for item in record["evidence"]]
            notes = [CaseNote(classification=item["classification"], text=item["description"],
                              created_at_utc=item["occurred_at_utc"])
                     for item in record["history"] if item["event_type"] == "note_added"]
            timeline = [CaseTimelineEntry(
                occurred_at_utc=item["occurred_at_utc"], category="case_history",
                reference_id=item["reference_id"], description=item["description"],
                classification=item["classification"],
            ) for item in record["history"]]
            linked_findings = [TelemetryFinding.model_validate_json(item) for item in record["finding_records"]]
            source_events = [SyntheticTelemetryEvent.model_validate_json(item) for item in record["evidence_records"]]
            observations_by_ref = {
                event.evidence_ref: ExecutiveObservation(
                    evidence_ref=event.evidence_ref, event_id=event.event_id,
                    event_type=event.event_type, occurred_at_utc=event.occurred_at,
                ) for event in source_events
            }
            for finding in linked_findings:
                timeline.extend((
                    CaseTimelineEntry(occurred_at_utc=finding.first_seen_utc, category="finding",
                                      reference_id=finding.finding_id, description=f"Rule {finding.rule_id} first observed.",
                                      classification="inferred_relationship"),
                    CaseTimelineEntry(occurred_at_utc=finding.last_seen_utc, category="finding",
                                      reference_id=finding.finding_id, description=f"Rule {finding.rule_id} last observed.",
                                      classification="inferred_relationship"),
                ))
            for event in source_events:
                timeline.append(CaseTimelineEntry(
                    occurred_at_utc=event.occurred_at, category="evidence",
                    reference_id=event.evidence_ref,
                    description=f"Verified stored event {event.event_id}.",
                    classification="verified_evidence",
                ))
            contexts = []
            for item in record["contexts"]:
                generated = (self.store.assessment_report_time(tenant_id, item["source_id"])
                             if item["source_type"] == "assessment_report" else None)
                label = "Tenant local website assessment report"
                if item["source_type"] == "evaluation_run" and self.detection_evaluation is not None:
                    run = next((run for run in self.detection_evaluation.history if run.run_id == item["source_id"]), None)
                    generated = run.generated_at_utc.isoformat() if run else None
                    label = "Synthetic detection evaluation run"
                if generated:
                    context = CaseContextReference(source_type=item["source_type"], source_id=item["source_id"],
                                                   generated_at_utc=generated, label=label)
                    contexts.append(context)
                    timeline.append(CaseTimelineEntry(
                        occurred_at_utc=context.generated_at_utc,
                        category="assessment_context" if item["source_type"] == "assessment_report" else "evaluation_context",
                        reference_id=context.source_id, description=context.label, classification="context",
                    ))
            recommendations = []
            for finding in linked_findings:
                try:
                    report = build_executive_report(
                        tenant_id=tenant_id, findings=[finding],
                        evidence=[observations_by_ref[ref] for ref in finding.evidence_refs if ref in observations_by_ref],
                    )
                    recommendations.extend(CaseRecommendation(
                        category=item.category, text=item.text, supporting_finding_ids=[finding.finding_id],
                    ) for item in report.recommendations)
                except ExecutiveReportInputError:
                    pass
            case_data = record["case"]
            case = InvestigationCase(
                **case_data, finding_count=len(finding_links), evidence_count=len(evidence_links),
                findings=finding_links, evidence=evidence_links, notes=notes, context=contexts,
                timeline=sorted(timeline, key=lambda event: (event.occurred_at_utc, event.reference_id))[:2000],
                recommendations=recommendations,
            )
            return ApiResponse(200, InvestigationCaseResponse(tenant_id=tenant_id, case=case).model_dump(mode="json"))
        if route in {"investigations.findings", "investigations.evidence", "investigations.notes",
                     "investigations.status", "investigations.context"}:
            if route == "investigations.findings":
                ok = self.store.add_case_finding(tenant_id, identifier or "", AddFindingLinkRequest.model_validate(body or {}))
            elif route == "investigations.evidence":
                ok = self.store.add_case_evidence(tenant_id, identifier or "", AddEvidenceLinkRequest.model_validate(body or {}))
            elif route == "investigations.notes":
                ok = self.store.add_case_note(tenant_id, identifier or "", AddAnalystNoteRequest.model_validate(body or {}))
            elif route == "investigations.status":
                ok = self.store.update_case_status(tenant_id, identifier or "", UpdateCaseStatusRequest.model_validate(body or {}))
            else:
                request = AddContextRequest.model_validate(body or {})
                if request.source_type == "assessment_report":
                    generated = self.store.assessment_report_time(tenant_id, request.source_id)
                else:
                    run = next((run for run in (self.detection_evaluation.history if self.detection_evaluation else [])
                                if run.run_id == request.source_id), None)
                    generated = run.generated_at_utc.isoformat() if run else None
                ok = bool(generated and self.store.add_case_context(
                    tenant_id, identifier or "", request, generated_at_utc=generated,
                ))
            if not ok:
                return _error(404, "not_found", "The requested resource was not found.")
            return ApiResponse(200, {"tenant_id": tenant_id, "updated": True})
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
            route_guess, _ = self._route_name(parsed.path, method)
        except ValueError:
            parsed = None
        if parsed is None or parsed.scheme or parsed.netloc or parsed.fragment:
            self._audit(tenant_id=principal.tenant_id, event_type="access_denial", method=method,
                        route="unknown", outcome="denied", details_code="invalid_request_target")
            return _error(400, "bad_request", "The request could not be processed.")
        route, identifier = self._route_name(parsed.path, method)
        allowed_method = ("GET" if route.startswith("investigations.list") or route == "investigations.detail"
                          or route in {"health.read", "readiness.read", "findings.list", "findings.evidence", "incidents.list",
                                       "incidents.report", "telemetry.findings", "telemetry.evidence",
                                       "telemetry.report", "executive.report", "assessment.report",
                                       "purple.scenario_runs",
                                       "evaluation.report", "telemetry.source_status", "processing.read"}
                          else "POST" if route.startswith("investigations.") else None)
        if method != allowed_method:
            self._audit(tenant_id=principal.tenant_id, event_type="access_denial", method=method,
                        route=route if route != "unknown" else route_guess,
                        outcome="denied", details_code="method_not_allowed")
            return _error(405, "method_not_allowed", "The method is not allowed for this operation.")
        if method == "GET" and (body_length != 0 or body):
            self._audit(tenant_id=principal.tenant_id, event_type="request_rejected", method=method,
                        route=route_guess, outcome="rejected", details_code="unexpected_request_body")
            return _error(400, "bad_request", "The request could not be processed.")
        try:
            query = parse_qs(parsed.query, keep_blank_values=True, strict_parsing=True) if parsed.query else {}
        except ValueError:
            self._audit(tenant_id=principal.tenant_id, event_type="request_rejected", method=method,
                        route=route, outcome="rejected", details_code="invalid_query")
            return _error(400, "bad_request", "The investigation filter is invalid.")
        if query and route != "investigations.list":
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
            parsed_body = None
            if method == "POST":
                if not body or body_length != len(body):
                    raise ValueError("missing request body")
                parsed_body = json.loads(body.decode("utf-8"))
                if not isinstance(parsed_body, dict):
                    raise ValueError("request body must be an object")
            response = self._perform(principal, route, identifier, body=parsed_body, query=query)
        except ValidationError:
            if method == "GET":
                self._audit(
                    tenant_id=principal.tenant_id, event_type="protected_operation", method=method,
                    route=route, outcome="error", details_code="invalid_stored_data",
                )
                return _error(500, "internal_error", "The service could not complete the request.")
            self._audit(tenant_id=principal.tenant_id, event_type="request_rejected", method=method,
                        route=route, outcome="rejected", details_code="invalid_request_body")
            return _error(400, "bad_request", "The request could not be processed.")
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
            self._audit(tenant_id=principal.tenant_id, event_type="request_rejected", method=method,
                        route=route, outcome="rejected", details_code="invalid_request_body")
            return _error(400, "bad_request", "The request could not be processed.")
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
        self._request_slots = threading.BoundedSemaphore(MAX_CONCURRENT_REQUESTS)
        super().__init__(address, LocalApiRequestHandler)

    def process_request(self, request, client_address) -> None:
        if not self._request_slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._request_slots.release()
            raise

    def process_request_thread(self, request, client_address) -> None:
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._request_slots.release()


class LocalApiRequestHandler(BaseHTTPRequestHandler):
    server_version = "AegisAI-Local"
    sys_version = ""

    def setup(self) -> None:
        self.request.settimeout(REQUEST_SOCKET_TIMEOUT_SECONDS)
        super().setup()

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
        if (origin not in LOCAL_FRONTEND_ORIGINS or requested_method not in {"GET", "POST"}
                or not requested_headers.issubset({"authorization", "content-type"})):
            self._write_json(403, {"error": "cors_denied", "message": "Browser access is not allowed."})
            return
        self.send_response(204)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Origin", origin)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
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
