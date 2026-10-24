"""Typed contracts for the local, human-led investigation case layer."""

from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class InvestigationModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


_SECRET_LIKE = re.compile(r"(?i)(?:\bbearer\s+[A-Za-z0-9._~+/=-]{8,}|\b(?:api[_-]?key|access[_-]?token|password|secret)\s*[:=]\s*[^\s,;]{8,})")


def _reject_secret_like_text(value: str) -> str:
    if _SECRET_LIKE.search(value):
        raise ValueError("secret-like values are not allowed in investigation text")
    return value


class CreateCaseRequest(InvestigationModel):
    title: str = Field(min_length=1, max_length=120)


class AddFindingLinkRequest(InvestigationModel):
    finding_id: str = Field(pattern=r"^tfinding-[a-f0-9]{12}$")
    relationship: Literal["inferred_relationship", "analyst_conclusion"]
    rationale: str = Field(min_length=1, max_length=500)

    @field_validator("rationale")
    @classmethod
    def no_secrets(cls, value: str) -> str:
        return _reject_secret_like_text(value)


class AddEvidenceLinkRequest(InvestigationModel):
    finding_id: str = Field(pattern=r"^tfinding-[a-f0-9]{12}$")
    evidence_ref: str = Field(min_length=1, max_length=100, pattern=r"^synthetic-[a-zA-Z0-9_-]+$")
    rationale: str = Field(min_length=1, max_length=500)

    @field_validator("rationale")
    @classmethod
    def no_secrets(cls, value: str) -> str:
        return _reject_secret_like_text(value)


class AddAnalystNoteRequest(InvestigationModel):
    classification: Literal["analyst_conclusion", "unresolved_hypothesis"]
    text: str = Field(min_length=1, max_length=1000)

    @field_validator("text")
    @classmethod
    def no_secrets(cls, value: str) -> str:
        return _reject_secret_like_text(value)


class UpdateCaseStatusRequest(InvestigationModel):
    status: Literal["open", "under_review", "closed"]


class AddContextRequest(InvestigationModel):
    source_type: Literal["assessment_report", "evaluation_run"]
    source_id: str = Field(min_length=1, max_length=80)


class InvestigationCaseSummary(InvestigationModel):
    case_id: str = Field(pattern=r"^case-[a-f0-9]{16}$")
    title: str
    status: Literal["open", "under_review", "closed"]
    created_at_utc: datetime
    updated_at_utc: datetime
    finding_count: int = Field(ge=0)
    evidence_count: int = Field(ge=0)


class CaseFindingLink(InvestigationModel):
    finding_id: str
    relationship: Literal["inferred_relationship", "analyst_conclusion"]
    rationale: str
    linked_at_utc: datetime


class CaseEvidenceLink(InvestigationModel):
    finding_id: str
    evidence_ref: str
    rationale: str
    linked_at_utc: datetime


class CaseNote(InvestigationModel):
    classification: Literal["analyst_conclusion", "unresolved_hypothesis"]
    text: str
    created_at_utc: datetime


class CaseContextReference(InvestigationModel):
    source_type: Literal["assessment_report", "evaluation_run"]
    source_id: str
    generated_at_utc: datetime
    label: str


class CaseTimelineEntry(InvestigationModel):
    occurred_at_utc: datetime
    category: Literal["case_history", "finding", "evidence", "assessment_context", "evaluation_context"]
    reference_id: str
    description: str
    classification: Literal["verified_evidence", "analyst_conclusion", "inferred_relationship", "unresolved_hypothesis", "context", "case_activity"]

    @field_validator("occurred_at_utc")
    @classmethod
    def utc_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timeline timestamps must include timezone")
        return value.astimezone(timezone.utc)


class CaseRecommendation(InvestigationModel):
    category: Literal["investigation", "remediation"]
    text: str = Field(min_length=1, max_length=500)
    supporting_finding_ids: list[str] = Field(min_length=1, max_length=100)

class InvestigationCase(InvestigationCaseSummary):
    findings: list[CaseFindingLink] = Field(max_length=100)
    evidence: list[CaseEvidenceLink] = Field(max_length=500)
    notes: list[CaseNote] = Field(max_length=500)
    context: list[CaseContextReference] = Field(max_length=40)
    timeline: list[CaseTimelineEntry] = Field(max_length=2000)
    recommendations: list[CaseRecommendation] = Field(max_length=200)


class InvestigationCasesResponse(InvestigationModel):
    data_classification: Literal["synthetic"] = "synthetic"
    label: Literal["SYNTHETIC - HUMAN-LED INVESTIGATION"] = "SYNTHETIC - HUMAN-LED INVESTIGATION"
    tenant_id: str
    cases: list[InvestigationCaseSummary] = Field(max_length=200)


class InvestigationCaseResponse(InvestigationModel):
    data_classification: Literal["synthetic"] = "synthetic"
    label: Literal["SYNTHETIC - HUMAN-LED INVESTIGATION"] = "SYNTHETIC - HUMAN-LED INVESTIGATION"
    tenant_id: str
    case: InvestigationCase
