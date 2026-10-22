"""Validated response contracts for the synthetic-only local API."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from platform_prototype.models import Finding, IncidentReport
from private_api.telemetry import TelemetryFinding, TelemetryReport


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class HealthResponse(ApiModel):
    status: Literal["ok"]
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
        "synthetic_configuration_finding",
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
    last_attempt_at_utc: datetime
    last_success_at_utc: datetime | None
    status: Literal["running", "healthy", "failed"]
    input_event_count: int = Field(ge=0)
    accepted_event_count: int = Field(ge=0)
    duplicate_event_count: int = Field(ge=0)
    rejected_record_count: int = Field(ge=0)
    position_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    position_bytes: int = Field(ge=0)
    error_code: Literal["source_invalid", "processing_error", "store_error"] | None


class TelemetryReportResponse(ApiModel):
    report: TelemetryReport
