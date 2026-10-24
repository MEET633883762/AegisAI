"""Versioned contracts for harmless local scenario validation."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ScenarioModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ScenarioDefinition(ScenarioModel):
    scenario_id: str = Field(pattern=r"^[a-z][a-z0-9-]{2,63}$")
    version: str = Field(pattern=r"^\d+\.\d+$")
    purpose: str = Field(min_length=1, max_length=300)
    prerequisites: tuple[str, ...] = Field(max_length=8)
    expected_telemetry_type: Literal["synthetic_http_access", "auth_failure"]
    expected_route_code: Literal["health", "login"]
    expected_status: int = Field(ge=100, le=599)
    expected_count: int = Field(ge=1, le=3)
    expected_detection_rule_ids: tuple[str, ...] = Field(max_length=4)
    assessment_check_ids: tuple[str, ...] = Field(max_length=4)
    cleanup_requirements: str = Field(min_length=1, max_length=300)
    request_method: Literal["GET", "POST"]
    request_path: Literal["/health", "/login-failure"]

    @model_validator(mode="after")
    def fixed_request_matches_expectations(self) -> "ScenarioDefinition":
        if self.request_path == "/health":
            valid = (self.request_method == "GET" and self.expected_route_code == "health"
                     and self.expected_status == 200 and self.expected_count == 1
                     and self.expected_telemetry_type == "synthetic_http_access")
        else:
            valid = (self.request_method == "POST" and self.expected_route_code == "login"
                     and self.expected_status == 401 and self.expected_count == 3
                     and self.expected_telemetry_type == "auth_failure")
        if not valid:
            raise ValueError("scenario request and expected telemetry must match the reviewed fixed site behavior")
        return self


class ScenarioPolicyDecision(ScenarioModel):
    scenario_id: str
    target_origin: str
    allowed: bool
    reason_code: Literal["approved", "explicit_authorization_required", "scenario_not_allowlisted", "target_not_allowlisted"]
    maximum_requests: int = Field(ge=0, le=3)


class ScenarioTelemetryEvidence(ScenarioModel):
    event_id: str = Field(min_length=1, max_length=80)
    evidence_ref: str = Field(min_length=1, max_length=100)
    event_type: str
    route_code: str
    status_code: int = Field(ge=100, le=599)
    occurred_at_utc: datetime

    @field_validator("occurred_at_utc")
    @classmethod
    def utc_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("scenario evidence timestamp must include a timezone")
        return value.astimezone(timezone.utc)


class ScenarioFindingEvidence(ScenarioModel):
    finding_id: str = Field(pattern=r"^tfinding-[a-f0-9]{12}$")
    rule_id: str = Field(min_length=1, max_length=40)
    evidence_refs: tuple[str, ...] = Field(max_length=3)


class ScenarioComparison(ScenarioModel):
    previous_run_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")
    previous_status: Literal["NOT_RUN", "PASSED", "FAILED", "ERROR", "NOT_APPLICABLE"] | None = None
    outcome_changed: bool | None = None


class ScenarioExecutionReport(ScenarioModel):
    schema_version: Literal["1.0"] = "1.0"
    catalog_version: Literal["aegisai-purple-scenarios-v1"] = "aegisai-purple-scenarios-v1"
    run_id: str = Field(default_factory=lambda: uuid4().hex, pattern=r"^[a-f0-9]{32}$")
    scenario_id: str
    scenario_version: str
    status: Literal["NOT_RUN", "PASSED", "FAILED", "ERROR", "NOT_APPLICABLE"]
    data_classification: Literal["synthetic"] = "synthetic"
    label: Literal["SYNTHETIC LOCAL SCENARIO - NOT A REAL-WORLD CONTROL TEST"] = "SYNTHETIC LOCAL SCENARIO - NOT A REAL-WORLD CONTROL TEST"
    target_origin: Literal["http://127.0.0.1:8767"] = "http://127.0.0.1:8767"
    execution_scope: Literal["fixed_loopback_synthetic_website"] = "fixed_loopback_synthetic_website"
    started_at_utc: datetime
    completed_at_utc: datetime
    policy_decision: ScenarioPolicyDecision
    error_category: Literal[
        "policy_denied", "concurrency_limit", "deadline_exceeded", "request_timeout",
        "connection_failed", "request_failed", "incomplete_response", "response_limit_exceeded", "malformed_response",
        "unsupported_response_encoding", "redirect_not_followed", "unexpected_http_status",
        "ambiguous_source_activity", "telemetry_processing_error",
    ] | None = None
    expected_telemetry_type: str
    expected_route_code: str
    expected_status: int
    expected_count: int
    observed_http_statuses: tuple[int, ...] = Field(max_length=3)
    observed_telemetry: tuple[ScenarioTelemetryEvidence, ...] = Field(max_length=3)
    expected_detection_rule_ids: tuple[str, ...] = Field(max_length=4)
    observed_findings: tuple[ScenarioFindingEvidence, ...] = Field(max_length=20)
    assessment_check_ids: tuple[str, ...] = Field(max_length=4)
    telemetry_report_id: str | None = Field(default=None, pattern=r"^treport-[a-f0-9]{12}$")
    telemetry_run_id: str | None = Field(default=None, pattern=r"^trun-[a-f0-9]{16}$")
    comparison: ScenarioComparison = Field(default_factory=ScenarioComparison)
    limitations: tuple[str, ...] = Field(min_length=1, max_length=6)

    @field_validator("started_at_utc", "completed_at_utc")
    @classmethod
    def aware_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("scenario timestamps must include a timezone")
        return value.astimezone(timezone.utc)

