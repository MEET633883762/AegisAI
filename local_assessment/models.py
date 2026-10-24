"""Typed, bounded data contracts for the local website assessment."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from enum import StrEnum
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def assessment_observation_digest(item: "AssessmentObservation") -> str:
    """Stable identity ignores capture time/duration, retaining observed content and outcome."""
    import hashlib
    import json

    evidence = item.evidence
    stable = {
        "check_id": item.check_id.value,
        "decision": {"allowed": item.decision.allowed, "reason_code": item.decision.reason_code},
        "outcome": item.outcome,
        "error_category": item.error_category,
        "facts": item.facts,
        "evidence": None if evidence is None else {
            "path": evidence.request_path, "status": evidence.response_status,
            "bytes": evidence.response_bytes, "sha256": evidence.response_sha256,
        },
    }
    # Preserve identifiers written by schema 1.0 reports while making schema 2.0
    # identities sensitive to catalog/configuration/result changes.
    if item.check_version != "legacy":
        stable.update({
            "outcome_status": item.outcome_status.value if item.outcome_status else None,
            "check_version": item.check_version,
            "category": item.category,
            "severity": item.severity,
            "expected_result": item.expected_result,
            "observed_result": item.observed_result,
        })
    encoded = json.dumps(stable, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("ascii")).hexdigest()


def assessment_observation_reference(item: "AssessmentObservation") -> str:
    return f"assessment-observation-{assessment_observation_digest(item)[:24]}"


class CheckId(StrEnum):
    HEALTH_STATUS = "health_status_v1"
    SECURITY_HEADERS = "security_headers_v1"
    COOKIE_ATTRIBUTES = "cookie_attributes_v1"


class CheckOutcome(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    ERROR = "ERROR"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class AssessmentCheckDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    check_id: CheckId
    version: str = Field(pattern=r"^\d+\.\d+$")
    category: Literal["availability", "response_security", "cookie_configuration"]
    description: str = Field(min_length=1, max_length=240)
    severity: Literal["informational", "low", "medium"]
    expected_result: str = Field(min_length=1, max_length=300)
    mitre_attack_technique_ids: tuple[str, ...] = Field(max_length=4)
    defensive_control_ids: tuple[str, ...] = Field(max_length=4)
    mapping_rationale: str = Field(min_length=1, max_length=300)


class AssessmentCheck(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    check_id: CheckId
    target_origin: str = Field(min_length=1, max_length=256)


class AssessmentDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    check_id: CheckId
    target_origin: str
    allowed: bool
    reason_code: str


class AssessmentEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_ref: str = Field(min_length=1, max_length=96)
    source: str = "loopback_http_response"
    observed_at_utc: datetime
    request_method: str = "GET"
    request_path: Literal["/", "/health"]
    response_status: int = Field(ge=100, le=599)
    response_bytes: int = Field(ge=0, le=16_384)
    response_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class AssessmentObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    check_id: CheckId
    category: Literal["availability", "response_security", "cookie_configuration", "legacy"] = "legacy"
    description: str = "Check description unavailable in legacy report."
    severity: Literal["informational", "low", "medium"] = "informational"
    check_version: str = Field(default="legacy", max_length=32)
    configuration_version: str = Field(default="legacy", max_length=64)
    expected_result: str = Field(default="Not recorded by the legacy report.", max_length=300)
    observed_result: str = Field(default="Not recorded by the legacy report.", max_length=512)
    outcome_status: CheckOutcome | None = None
    observed_at_utc: datetime | None = None
    decision: AssessmentDecision
    outcome: str = Field(min_length=1, max_length=40)
    duration_ms: int = Field(ge=0, le=4_000)
    error_category: Literal[
        "policy_denied", "deadline_exceeded", "request_failed", "response_limit_exceeded",
    ] | None = None
    facts: dict[str, str | int | bool | None] = Field(max_length=12)
    evidence: AssessmentEvidence | None = None

    @field_validator("observed_at_utc")
    @classmethod
    def _aware_observation_time(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("observed_at_utc must include a timezone")
        return value

    @field_validator("facts")
    @classmethod
    def _bounded_facts(cls, value: dict[str, str | int | bool | None]) -> dict[str, str | int | bool | None]:
        if any(len(key) > 64 or (isinstance(item, str) and len(item) > 512) for key, item in value.items()):
            raise ValueError("assessment facts exceed their field-size limit")
        return value


class AssessmentResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "2.0"
    run_id: str = Field(default_factory=lambda: uuid4().hex, pattern=r"^[a-f0-9]{32}$")
    started_at_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    label: str = "LOCAL SYNTHETIC WEBSITE ASSESSMENT"
    decisions: tuple[AssessmentDecision, ...] = Field(max_length=3)
    observations: tuple[AssessmentObservation, ...] = Field(max_length=3)


class AssessmentIssue(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    issue_id: str = Field(pattern=r"^assessment-issue-[a-f0-9]{16}$")
    check_id: CheckId
    classification: Literal["inferred_risk", "confirmed_finding"]
    title: str = Field(min_length=1, max_length=160)
    rationale: str = Field(min_length=1, max_length=500)
    severity: Literal["informational", "low", "medium"] = "medium"
    recommendation: str = Field(default="Review this observation manually.", min_length=1, max_length=500)
    evidence_refs: tuple[str, ...] = Field(min_length=1, max_length=3)


class AssessmentFindingChange(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    finding_key: str = Field(pattern=r"^assessment-finding-[a-f0-9]{16}$")
    issue_id: str = Field(pattern=r"^assessment-issue-[a-f0-9]{16}$")
    check_id: CheckId
    title: str = Field(min_length=1, max_length=160)
    evidence_refs: tuple[str, ...] = Field(max_length=3)


class AssessmentRunComparison(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["baseline", "compared"]
    previous_report_id: str | None = None
    newly_introduced: tuple[AssessmentFindingChange, ...] = Field(max_length=12)
    resolved: tuple[AssessmentFindingChange, ...] = Field(max_length=12)
    unchanged: tuple[AssessmentFindingChange, ...] = Field(max_length=12)


class AssessmentReport(BaseModel):
    """Sanitized assessment report; raw body content is never represented."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0", "2.0"] = "1.0"
    report_id: str = Field(pattern=r"^assessment-report-[a-f0-9]{16}$")
    run_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")
    started_at_utc: datetime | None = None
    generated_at_utc: datetime
    configuration_version: str = "legacy"
    check_catalog_version: str = "legacy"
    provenance: Literal["fixed_loopback_synthetic_website", "legacy"] = "legacy"
    comparison: AssessmentRunComparison | None = None
    data_classification: Literal["synthetic"] = "synthetic"
    label: Literal["LOCAL SYNTHETIC WEBSITE ASSESSMENT"] = "LOCAL SYNTHETIC WEBSITE ASSESSMENT"
    raw_observations: tuple[AssessmentObservation, ...] = Field(max_length=3)
    inferred_risks: tuple[AssessmentIssue, ...] = Field(max_length=12)
    confirmed_findings: tuple[AssessmentIssue, ...] = Field(max_length=12)
    duplicate_observation_count: int = Field(ge=0, le=3)
    limitations: tuple[str, ...] = Field(min_length=1, max_length=8)

    @field_validator("generated_at_utc")
    @classmethod
    def _aware_report_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("generated_at_utc must include a timezone")
        return value

    @model_validator(mode="after")
    def _validate_evidence_links(self) -> "AssessmentReport":
        refs = [item.evidence.evidence_ref for item in self.raw_observations if item.evidence]
        if len(refs) != len(set(refs)):
            raise ValueError("assessment evidence references must be unique")
        known = set(refs)
        if any(item.classification != "inferred_risk" for item in self.inferred_risks):
            raise ValueError("inferred_risks must contain inferred-risk items")
        if any(item.classification != "confirmed_finding" for item in self.confirmed_findings):
            raise ValueError("confirmed_findings must contain confirmed items")
        if self.confirmed_findings:
            raise ValueError("the current observation-only checks do not support confirmed findings")
        if any(not set(item.evidence_refs).issubset(known)
               for item in (*self.inferred_risks, *self.confirmed_findings)):
            raise ValueError("assessment issue references unknown evidence")
        hashes = sorted({assessment_observation_digest(item) for item in self.raw_observations})
        expected_report = hashlib.sha256("\n".join(hashes).encode("ascii")).hexdigest()[:16]
        if self.report_id != f"assessment-report-{expected_report}":
            raise ValueError("assessment report ID does not match its observations")
        for item in self.raw_observations:
            if item.evidence is not None:
                expected_ref = f"assessment-evidence-{assessment_observation_digest(item)[:24]}"
                if item.evidence.evidence_ref != expected_ref:
                    raise ValueError("assessment evidence reference does not match its observation")
        return self

    @classmethod
    def from_result(cls, result: AssessmentResult) -> "AssessmentReport":
        canonical: dict[str, AssessmentObservation] = {}
        keys: list[str] = []
        for item in result.observations:
            evidence = item.evidence
            digest = assessment_observation_digest(item)
            keys.append(digest)
            if digest not in canonical:
                stable_evidence = evidence.model_copy(update={"evidence_ref": f"assessment-evidence-{digest[:24]}"}) if evidence else None
                canonical[digest] = item.model_copy(update={"evidence": stable_evidence})
        ordered_keys = sorted(set(keys))
        observations = tuple(canonical[key] for key in ordered_keys)
        report_digest = hashlib.sha256("\n".join(ordered_keys).encode("ascii")).hexdigest()[:16]
        risks: list[AssessmentIssue] = []
        header_expectations = {
            "content-security-policy": "A Content-Security-Policy response header was not observed.",
            "x-content-type-options": "X-Content-Type-Options was absent or did not equal nosniff.",
            "referrer-policy": "A Referrer-Policy response header was not observed.",
            "permissions-policy": "A Permissions-Policy response header was not observed.",
        }
        for item in observations:
            candidates: list[tuple[str, str]] = []
            if item.facts.get("status_matches_expectation") is False:
                candidates.append(("Unexpected HTTP status observed.", "The response status differed from the check's documented expected status; this is an inferred review item, not a confirmed vulnerability."))
            if item.check_id is CheckId.SECURITY_HEADERS:
                for header, rationale in header_expectations.items():
                    value = item.facts.get(header)
                    expected = "nosniff" if header == "x-content-type-options" else None
                    if value is None or (expected is not None and str(value).strip().lower() != expected):
                        candidates.append((f"Review {header} configuration", rationale + " This observation alone does not establish exploitability."))
            if item.check_id is CheckId.COOKIE_ATTRIBUTES and item.facts.get("cookie_returned") is True:
                if item.facts.get("secure") is not True or item.facts.get("httponly") is not True or item.facts.get("samesite") is None:
                    candidates.append(("Review returned cookie attributes", "One or more expected cookie security attributes were not observed; this is an inferred review item, not a confirmed vulnerability."))
            ref = item.evidence.evidence_ref if item.evidence else None
            if ref:
                for title, rationale in candidates:
                    issue_digest = hashlib.sha256(f"{item.check_id.value}\0{title}\0{ref}".encode()).hexdigest()[:16]
                    recommendation = {
                        CheckId.SECURITY_HEADERS: "Review and configure the documented response security headers on the local demo site; verify the change manually before treating it as a finding.",
                        CheckId.COOKIE_ATTRIBUTES: "Review the returned cookie attributes and configure Secure, HttpOnly, and an appropriate SameSite policy where cookies are required.",
                        CheckId.HEALTH_STATUS: "Review availability of the fixed local demo site's health endpoint and investigate the observed status manually.",
                    }[item.check_id]
                    risks.append(AssessmentIssue(
                        issue_id=f"assessment-issue-{issue_digest}", check_id=item.check_id,
                        classification="inferred_risk", title=title, rationale=rationale,
                        severity=item.severity, recommendation=recommendation,
                        evidence_refs=(ref,),
                    ))
        return cls(
            schema_version="2.0", run_id=result.run_id, started_at_utc=result.started_at_utc,
            report_id=f"assessment-report-{report_digest}", generated_at_utc=datetime.now(timezone.utc),
            configuration_version="local-website-config-v1", check_catalog_version="local-web-checks-v1",
            provenance="fixed_loopback_synthetic_website",
            raw_observations=observations, inferred_risks=tuple(risks), confirmed_findings=(),
            duplicate_observation_count=len(keys) - len(ordered_keys),
            comparison=AssessmentRunComparison(status="baseline", newly_introduced=(), resolved=(), unchanged=()),
            limitations=("Synthetic loopback test-site observations only; not evidence of real-world attacks.",
                         "Inferred risks require human review; no confirmed vulnerability is asserted by this report."),
        )

    @classmethod
    def validate_for_storage(cls, value: object) -> "AssessmentReport":
        return cls.model_validate(value)
