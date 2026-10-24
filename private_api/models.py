"""Validated response contracts for the synthetic-only local API."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from platform_prototype.models import Finding, IncidentReport
from platform_prototype.evaluation import (
    ConfusionCounts, Metrics, RuleEventMapping, ScenarioRuleMapping, TechniqueCoverage, UntestedTechnique,
)
from platform_prototype.evaluation_history import EvaluationRunSummary
from local_assessment.models import AssessmentReport
from purple_team.models import ScenarioExecutionReport
from private_api.telemetry import TelemetryFinding, TelemetryReport
from private_api.executive_reports import ExecutiveIncidentReport


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class HealthResponse(ApiModel):
    status: Literal["ok"]
    mode: Literal["local_synthetic"]


class ReadinessResponse(ApiModel):
    status: Literal["ready"]
    mode: Literal["local_synthetic"]


class ErrorResponse(ApiModel):
    error: str = Field(min_length=1, max_length=64)
    message: str = Field(min_length=1, max_length=160)


class FindingsResponse(ApiModel):
    data_classification: Literal["synthetic"]
    label: Literal["SYNTHETIC - NOT REAL CLIENT DATA"]
    tenant_id: str
    findings: list[Finding]


class EvidenceReferenceResponse(ApiModel):
    evidence_ref: str
    event_id: str
    event_type: Literal[
        "auth_failure", "auth_success", "request_rate_indicator",
        "simulated_suspicious_activity", "synthetic_vulnerability_finding",
        "synthetic_configuration_finding", "synthetic_http_access",
        "synthetic_application_error",
    ]
    occurred_at_utc: datetime
    asset_ref: str
    actor_ref: str
    source_ref: str


class EvidenceResponse(ApiModel):
    data_classification: Literal["synthetic"]
    label: Literal["SYNTHETIC - NOT REAL CLIENT DATA"]
    tenant_id: str
    finding_id: str
    evidence: list[EvidenceReferenceResponse]


class IncidentSummary(ApiModel):
    incident_id: str
    report_id: str
    dataset_id: str
    data_classification: Literal["synthetic"]
    label: Literal["SYNTHETIC - NOT REAL CLIENT DATA"]
    generated_at_utc: datetime
    finding_count: int = Field(ge=0)
    high_severity_count: int = Field(ge=0)


class IncidentsResponse(ApiModel):
    data_classification: Literal["synthetic"]
    label: Literal["SYNTHETIC - NOT REAL CLIENT DATA"]
    tenant_id: str
    incidents: list[IncidentSummary]


class IncidentReportResponse(ApiModel):
    data_classification: Literal["synthetic"]
    label: Literal["SYNTHETIC - NOT REAL CLIENT DATA"]
    tenant_id: str
    incident_id: str
    report: IncidentReport


class TelemetryFindingsResponse(ApiModel):
    data_classification: Literal["synthetic"]
    label: Literal["SYNTHETIC - NOT REAL CLIENT DATA"]
    tenant_id: str
    findings: list[TelemetryFinding]


class TelemetryEvidenceResponse(ApiModel):
    data_classification: Literal["synthetic"]
    label: Literal["SYNTHETIC - NOT REAL CLIENT DATA"]
    tenant_id: str
    finding_id: str
    evidence: list[EvidenceReferenceResponse]


class ProcessingRunSummary(ApiModel):
    run_id: str
    source_id: Literal["local_synthetic_fixture_v1"]
    status: Literal["started", "completed", "skipped", "failed"]
    scheduled_at_utc: datetime
    started_at_utc: datetime
    completed_at_utc: datetime | None
    attempt: int = Field(ge=1)
    input_event_count: int = Field(ge=0)
    accepted_event_count: int = Field(ge=0)
    duplicate_event_count: int = Field(ge=0)
    finding_count: int = Field(ge=0)
    error_code: str | None = Field(default=None, max_length=80)


class ProcessingStatusResponse(ApiModel):
    data_classification: Literal["synthetic"]
    label: Literal["SYNTHETIC - NOT REAL CLIENT DATA"]
    tenant_id: str
    scheduler_state: Literal["running", "unavailable", "stopped", "disabled"]
    interval_seconds: Literal[600]
    latest_run: ProcessingRunSummary | None


class LiveWebsiteSourceStatusResponse(ApiModel):
    data_classification: Literal["synthetic"]
    label: Literal["SYNTHETIC - NOT REAL CLIENT DATA"]
    tenant_id: str
    source_key: Literal["synthetic_demo_site_live_logs_v1"]
    last_attempt_at_utc: datetime | None
    last_success_at_utc: datetime | None
    status: Literal["running", "healthy", "failed", "unavailable"]
    input_event_count: int | None = Field(ge=0)
    accepted_event_count: int | None = Field(ge=0)
    duplicate_event_count: int | None = Field(ge=0)
    rejected_record_count: int | None = Field(ge=0)
    position_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    position_bytes: int | None = Field(ge=0)
    error_code: Literal["source_invalid", "processing_error", "store_error"] | None


class TelemetryReportResponse(ApiModel):
    report: TelemetryReport


class ExecutiveReportResponse(ApiModel):
    data_classification: Literal["synthetic"]
    label: Literal["SYNTHETIC - NOT REAL CLIENT DATA"]
    tenant_id: str
    report: ExecutiveIncidentReport


class LocalAssessmentReportResponse(ApiModel):
    data_classification: Literal["synthetic"]
    label: Literal["LOCAL SYNTHETIC WEBSITE ASSESSMENT"]
    tenant_id: str
    report: AssessmentReport | None
    history: list["AssessmentHistoryEntry"] = Field(max_length=20)


class AssessmentHistoryEntry(ApiModel):
    report_id: str = Field(pattern=r"^assessment-report-[a-f0-9]{16}$")
    generated_at_utc: datetime
    inferred_risk_count: int = Field(ge=0, le=12)
    confirmed_finding_count: int = Field(ge=0, le=12)
    comparison_status: Literal["baseline", "compared"] | None
    previous_report_id: str | None = Field(default=None, pattern=r"^assessment-report-[a-f0-9]{16}$")
    newly_introduced_count: int = Field(ge=0, le=12)
    resolved_count: int = Field(ge=0, le=12)


class PurpleScenarioRunsResponse(ApiModel):
    data_classification: Literal["synthetic"] = "synthetic"
    label: Literal["SYNTHETIC LOCAL SCENARIO HISTORY - NOT A REAL-WORLD CONTROL TEST"] = (
        "SYNTHETIC LOCAL SCENARIO HISTORY - NOT A REAL-WORLD CONTROL TEST"
    )
    tenant_id: str
    runs: list[ScenarioExecutionReport] = Field(max_length=20)


class DetectionRuleSummary(ApiModel):
    rule_id: str
    counts: ConfusionCounts
    metrics: Metrics


class DetectionEvaluationSummary(ApiModel):
    schema_version: Literal["1.0", "1.1"]
    report_type: Literal["aegisai_synthetic_detection_evaluation_report"]
    dataset_id: str
    dataset_version: str
    dataset_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    detector_config_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    rule_catalog_version: str
    detector_rule_version: str
    scenario_rule_mapping_version: str
    attack_mapping_catalog_version: str
    counting_unit: str
    counts: ConfusionCounts
    metrics: Metrics
    total_evaluated_pairs: int = Field(ge=0)
    per_rule: list[DetectionRuleSummary]
    rule_event_mapping: list[RuleEventMapping] = Field(max_length=32)
    scenario_rule_mapping: list[ScenarioRuleMapping] = Field(max_length=50)
    technique_coverage: list[TechniqueCoverage] = Field(max_length=32)
    untested_techniques: list[UntestedTechnique] = Field(max_length=32)
    coverage_status: Literal["complete", "partial", "legacy_unavailable"]
    warnings: list[str] = Field(max_length=32)
    valid_scenario_count: int = Field(ge=0)
    rejected_scenario_count: int = Field(ge=0)
    history: list[EvaluationRunSummary] = Field(max_length=20)
    limitations: list[str] = Field(min_length=1)


class DetectionEvaluationResponse(ApiModel):
    data_classification: Literal["synthetic"]
    label: Literal["SYNTHETIC EVALUATION - NOT REAL SECURITY PERFORMANCE"]
    tenant_id: str
    report: DetectionEvaluationSummary
