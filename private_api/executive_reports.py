"""Deterministic executive report models and builder over tenant-scoped telemetry."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Literal, Sequence

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from private_api.auth import TENANT_PATTERN
from private_api.telemetry import TelemetryEventType, TelemetryFinding, TelemetrySeverity


class ExecutiveReportModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class ExecutiveSeverityCounts(ExecutiveReportModel):
    low: int = Field(ge=0)
    medium: int = Field(ge=0)
    high: int = Field(ge=0)
    critical: int = Field(ge=0)


class ExecutiveStatusCounts(ExecutiveReportModel):
    open: int = Field(ge=0)
    acknowledged: int = Field(ge=0)
    closed: int = Field(ge=0)


class ExecutiveFindingCounts(ExecutiveReportModel):
    by_severity: ExecutiveSeverityCounts
    by_status: ExecutiveStatusCounts


class ExecutiveObservation(ExecutiveReportModel):
    """A minimized representation of evidence already linked to a stored finding."""

    evidence_ref: str = Field(min_length=1, max_length=100, pattern=r"^synthetic-[a-zA-Z0-9_-]+$")
    event_id: str = Field(min_length=1, max_length=80, pattern=r"^syn-[a-zA-Z0-9_-]+$")
    event_type: TelemetryEventType
    occurred_at_utc: datetime
    related_finding_ids: list[str] = Field(default_factory=list, max_length=10_000)

    @field_validator("occurred_at_utc")
    @classmethod
    def normalize_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("evidence timestamp must include a timezone")
        return value.astimezone(timezone.utc)


class ExecutiveRisk(ExecutiveReportModel):
    classification: Literal["inferred_risk"] = "inferred_risk"
    finding_id: str
    rule_id: str
    severity: TelemetrySeverity
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False)
    status: Literal["open", "acknowledged", "closed"]
    first_seen_utc: datetime
    last_seen_utc: datetime
    asset_ref: str
    explanation: str
    confidence_factors: list[str]
    evidence_refs: list[str]

    @field_validator("first_seen_utc", "last_seen_utc")
    @classmethod
    def normalize_finding_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("finding timestamp must include a timezone")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def times_are_ordered(self) -> ExecutiveRisk:
        if self.last_seen_utc < self.first_seen_utc:
            raise ValueError("last_seen_utc must not precede first_seen_utc")
        return self


class ExecutiveRecommendation(ExecutiveReportModel):
    category: Literal["investigation", "remediation"]
    finding_id: str
    text: str = Field(min_length=1, max_length=500)


class ExecutiveTimelineEntry(ExecutiveReportModel):
    occurred_at_utc: datetime
    evidence_ref: str
    event_id: str
    event_type: TelemetryEventType
    finding_ids: list[str] = Field(min_length=1, max_length=10_000)


class ExecutiveIncidentReport(ExecutiveReportModel):
    schema_version: Literal["1.0"] = "1.0"
    report_type: Literal["aegisai_executive_incident_report"] = "aegisai_executive_incident_report"
    report_id: str = Field(pattern=r"^executive-report-[a-f0-9]{16}$")
    tenant_id: str = Field(pattern=r"^synthetic-org-[a-z0-9][a-z0-9-]{0,44}$")
    generated_at_utc: datetime
    data_classification: Literal["synthetic"] = "synthetic"
    label: Literal["SYNTHETIC - NOT REAL CLIENT DATA"] = "SYNTHETIC - NOT REAL CLIENT DATA"
    executive_summary: str = Field(min_length=1, max_length=1000)
    finding_counts: ExecutiveFindingCounts
    observations: list[ExecutiveObservation] = Field(max_length=10_000)
    inferred_risks: list[ExecutiveRisk] = Field(max_length=10_000)
    confirmed_findings: list[dict] = Field(max_length=0)
    timeline: list[ExecutiveTimelineEntry] = Field(max_length=10_000)
    recommendations: list[ExecutiveRecommendation] = Field(max_length=20_000)
    limitations: list[str] = Field(min_length=1, max_length=20)

    @field_validator("generated_at_utc")
    @classmethod
    def normalize_generation_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("generation timestamp must include a timezone")
        return value.astimezone(timezone.utc)


class ExecutiveReportInputError(ValueError):
    """Safe input error when source findings cannot be represented faithfully."""


def build_executive_report(
    *,
    tenant_id: str,
    findings: Sequence[TelemetryFinding],
    evidence: Sequence[ExecutiveObservation],
    generated_at_utc: datetime | None = None,
) -> ExecutiveIncidentReport:
    """Build a report from findings/evidence already read within one tenant scope.

    Callers must obtain both input collections through tenant-filtered storage methods.
    This function validates the tenant, limits inputs, and rejects missing or conflicting
    evidence rather than manufacturing references or promoting inferred risks.
    """
    if not isinstance(tenant_id, str) or not TENANT_PATTERN.fullmatch(tenant_id):
        raise ExecutiveReportInputError("invalid report tenant")
    if len(findings) > 10_000 or len(evidence) > 50_000:
        raise ExecutiveReportInputError("report input exceeds the supported size")
    generated_at = generated_at_utc or datetime.now(timezone.utc)
    if generated_at.tzinfo is None or generated_at.utcoffset() is None:
        raise ExecutiveReportInputError("generation timestamp must include a timezone")
    generated_at = generated_at.astimezone(timezone.utc)

    ordered_findings = sorted(findings, key=lambda item: item.finding_id)
    finding_ids = [item.finding_id for item in ordered_findings]
    if len(set(finding_ids)) != len(finding_ids):
        raise ExecutiveReportInputError("finding IDs must be unique")
    evidence_by_ref: dict[str, ExecutiveObservation] = {}
    for item in evidence:
        prior = evidence_by_ref.get(item.evidence_ref)
        if prior is not None:
            # Relationship IDs can differ when evidence supports multiple findings; compare source facts only.
            prior_facts = prior.model_dump(exclude={"related_finding_ids"})
            item_facts = item.model_dump(exclude={"related_finding_ids"})
            if prior_facts != item_facts:
                raise ExecutiveReportInputError("conflicting evidence reference")
            continue
        evidence_by_ref[item.evidence_ref] = item

    referenced = {ref for finding in ordered_findings for ref in finding.evidence_refs}
    missing = referenced - set(evidence_by_ref)
    if missing:
        raise ExecutiveReportInputError("finding references missing evidence")
    for finding in ordered_findings:
        if any(evidence_by_ref[ref].event_id not in finding.event_ids for ref in finding.evidence_refs):
            raise ExecutiveReportInputError("evidence does not match finding event references")
    unexpected = set(evidence_by_ref) - referenced
    if unexpected:
        # Do not include unrelated evidence in an executive report.
        evidence_by_ref = {key: value for key, value in evidence_by_ref.items() if key in referenced}

    findings_for_evidence: dict[str, list[str]] = {ref: [] for ref in referenced}
    for finding in ordered_findings:
        for ref in finding.evidence_refs:
            findings_for_evidence[ref].append(finding.finding_id)
    observations = [
        item.model_copy(update={"related_finding_ids": sorted(set(findings_for_evidence[ref]))})
        for ref, item in sorted(evidence_by_ref.items(), key=lambda pair: (pair[1].occurred_at_utc, pair[0]))
    ]
    risks = [ExecutiveRisk(
        finding_id=item.finding_id, rule_id=item.rule_id, severity=item.severity,
        confidence=item.confidence, status=item.status, first_seen_utc=item.first_seen_utc,
        last_seen_utc=item.last_seen_utc, asset_ref=item.asset_ref, explanation=item.explanation,
        confidence_factors=item.confidence_factors, evidence_refs=item.evidence_refs,
    ) for item in ordered_findings]
    timeline = [ExecutiveTimelineEntry(
        occurred_at_utc=item.occurred_at_utc, evidence_ref=item.evidence_ref,
        event_id=item.event_id, event_type=item.event_type,
        finding_ids=item.related_finding_ids,
    ) for item in observations]

    severity_values = {item.value for item in TelemetrySeverity}
    status_values = ("open", "acknowledged", "closed")
    counts = ExecutiveFindingCounts(
        by_severity=ExecutiveSeverityCounts(**{
            key: sum(item.severity.value == key for item in ordered_findings)
            for key in sorted(severity_values)
        }),
        by_status=ExecutiveStatusCounts(**{
            key: sum(item.status == key for item in ordered_findings) for key in status_values
        }),
    )
    summary = (
        f"This report summarizes {len(ordered_findings)} synthetic rule finding(s) across "
        f"{len(observations)} linked evidence reference(s). Findings are inferred risks requiring "
        "human review; this report does not establish real-world compromise, exploitability, or detection accuracy."
    )
    recommendations = [recommendation for item in ordered_findings for recommendation in (
        ExecutiveRecommendation(
            category="investigation", finding_id=item.finding_id,
            text="Review the listed evidence references and independently validate the signal against an authorized source.",
        ),
        ExecutiveRecommendation(
            category="remediation", finding_id=item.finding_id,
            text="If independently confirmed, plan any corrective work through approved change control; no action is taken by this report.",
        ),
    )]
    limitations = [
        "All source findings and evidence in this report are synthetic local prototype data.",
        "Rule findings are presented as inferred risks; the source data does not establish confirmed findings.",
        "Recommendations are for manual review only; no client systems are changed or contacted.",
        "The report includes only evidence references linked to the supplied tenant-scoped findings.",
    ]
    identity_payload = {
        "tenant_id": tenant_id,
        "generated_at_utc": generated_at.isoformat(),
        "findings": [item.model_dump(mode="json") for item in risks],
        "observations": [item.model_dump(mode="json") for item in observations],
    }
    canonical = json.dumps(identity_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    report_id = "executive-report-" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
    return ExecutiveIncidentReport(
        report_id=report_id, tenant_id=tenant_id, generated_at_utc=generated_at,
        executive_summary=summary, finding_counts=counts, observations=observations,
        inferred_risks=risks, confirmed_findings=[], timeline=timeline,
        recommendations=recommendations, limitations=limitations,
    )
