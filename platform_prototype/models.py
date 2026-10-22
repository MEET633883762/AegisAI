"""Strict data contracts for the local synthetic operations prototype."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class EventType(str, Enum):
    AUTH_FAILURE = "auth_failure"
    AUTH_SUCCESS = "auth_success"


class Severity(str, Enum):
    MEDIUM = "medium"
    HIGH = "high"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class SyntheticEvent(StrictModel):
    event_id: str = Field(min_length=1, max_length=80, pattern=r"^syn-[a-zA-Z0-9_-]+$")
    occurred_at: datetime
    event_type: EventType
    asset_ref: str = Field(min_length=1, max_length=100, pattern=r"^synthetic-[a-zA-Z0-9_-]+$")
    actor_ref: str = Field(min_length=1, max_length=100, pattern=r"^synthetic-[a-zA-Z0-9_-]+$")
    source_ref: str = Field(min_length=1, max_length=100, pattern=r"^synthetic-[a-zA-Z0-9_-]+$")
    evidence_ref: str = Field(min_length=1, max_length=100, pattern=r"^synthetic-[a-zA-Z0-9_-]+$")

    @field_validator("occurred_at")
    @classmethod
    def timestamp_must_have_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("occurred_at must include a timezone offset")
        return value


class SyntheticEventBatch(StrictModel):
    schema_version: Literal["1.0"]
    dataset_id: str = Field(min_length=1, max_length=100, pattern=r"^synthetic-[a-zA-Z0-9_-]+$")
    data_classification: Literal["synthetic"]
    label: Literal["SYNTHETIC - NOT REAL CLIENT DATA"]
    generated_at: datetime
    events: list[SyntheticEvent] = Field(min_length=1, max_length=500)

    @field_validator("generated_at")
    @classmethod
    def generated_at_must_have_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("generated_at must include a timezone offset")
        return value


class ActionRequest(StrictModel):
    finding_id: str = Field(min_length=1, max_length=100, pattern=r"^finding-[a-f0-9]{12}$")
    action_type: str = Field(min_length=1, max_length=80, pattern=r"^[a-z][a-z0-9_]*$")


class EvidenceReference(StrictModel):
    evidence_ref: str
    event_id: str
    event_type: EventType
    occurred_at_utc: datetime
    asset_ref: str
    actor_ref: str
    source_ref: str


class Finding(StrictModel):
    finding_id: str = Field(pattern=r"^finding-[a-f0-9]{12}$")
    correlation_key: str = Field(min_length=1, max_length=120)
    rule_id: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=160)
    severity: Severity
    confidence: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)
    confidence_factors: list[str] = Field(min_length=1, max_length=8)
    signal_types: list[EventType] = Field(min_length=1, max_length=4)
    evidence_refs: list[str] = Field(min_length=1, max_length=500)
    recommendation: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def evidence_is_unique(self) -> Finding:
        if len(set(self.evidence_refs)) != len(self.evidence_refs):
            raise ValueError("evidence_refs must be unique")
        return self


class SimulatedActionOutcome(StrictModel):
    finding_id: str
    action_type: str
    mode: Literal["simulation"] = "simulation"
    status: Literal["simulated", "denied"]
    executed: Literal[False] = False
    reason: str = Field(min_length=1, max_length=300)


class IncidentReport(StrictModel):
    schema_version: Literal["1.0"]
    report_type: Literal["aegisai_local_synthetic_incident_report"]
    report_id: str = Field(pattern=r"^report-[a-f0-9]{12}$")
    generated_at_utc: datetime
    data_classification: Literal["synthetic"]
    label: Literal["SYNTHETIC - NOT REAL CLIENT DATA"]
    dataset_id: str
    input_event_count: int = Field(ge=0)
    unique_event_count: int = Field(ge=0)
    duplicate_event_count: int = Field(ge=0)
    evidence_catalog: list[EvidenceReference]
    findings: list[Finding]
    simulated_actions: list[SimulatedActionOutcome]
    limitations: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def counts_are_consistent(self) -> IncidentReport:
        if self.input_event_count != self.unique_event_count + self.duplicate_event_count:
            raise ValueError("event counts must satisfy input = unique + duplicates")
        known_evidence = {item.evidence_ref for item in self.evidence_catalog}
        for finding in self.findings:
            if not set(finding.evidence_refs).issubset(known_evidence):
                raise ValueError("each finding evidence reference must exist in the evidence catalog")
        finding_ids = {item.finding_id for item in self.findings}
        if any(item.finding_id not in finding_ids for item in self.simulated_actions):
            raise ValueError("simulated actions must reference a report finding")
        return self
