"""Strict synthetic telemetry input contracts and deterministic versioned rules."""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from platform_prototype.models import SyntheticEvent, SyntheticEventBatch
from platform_prototype.pipeline import MAX_INPUT_BYTES, build_report

MAX_TELEMETRY_EVENTS = 500
MAX_STORED_EVENTS_PER_TENANT = 10_000
MAX_DETECTION_EVENTS = 500
MAX_RETAINED_RUNS_PER_TENANT = 100
MAX_RETAINED_OBSERVATIONS_PER_FINDING = 100
DETECTION_WINDOW = timedelta(minutes=10)
REQUEST_RATE_THRESHOLD = 100
REQUEST_RATE_WINDOW_SECONDS = 60
RULE_VERSION = "1.0"


class TelemetryEventType(str, Enum):
    AUTH_FAILURE = "auth_failure"
    AUTH_SUCCESS = "auth_success"
    REQUEST_RATE = "request_rate_indicator"
    SIMULATED_ACTIVITY = "simulated_suspicious_activity"
    VULNERABILITY = "synthetic_vulnerability_finding"
    CONFIGURATION = "synthetic_configuration_finding"
    HTTP_ACCESS = "synthetic_http_access"
    APPLICATION_ERROR = "synthetic_application_error"


class TelemetrySeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class TelemetryModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class SyntheticTelemetryEvent(TelemetryModel):
    event_id: str = Field(min_length=1, max_length=80, pattern=r"^syn-[a-zA-Z0-9_-]+$")
    occurred_at: datetime
    event_type: TelemetryEventType
    asset_ref: str = Field(min_length=1, max_length=100, pattern=r"^synthetic-[a-zA-Z0-9_-]+$")
    actor_ref: str = Field(min_length=1, max_length=100, pattern=r"^synthetic-[a-zA-Z0-9_-]+$")
    source_ref: str = Field(min_length=1, max_length=100, pattern=r"^synthetic-[a-zA-Z0-9_-]+$")
    evidence_ref: str = Field(min_length=1, max_length=100, pattern=r"^synthetic-[a-zA-Z0-9_-]+$")
    request_count: int | None = Field(default=None, ge=1, le=100_000)
    window_seconds: int | None = Field(default=None, ge=1, le=600)
    activity_code: Literal[
        "unexpected_admin_setting_change", "unusual_synthetic_file_access", "routine_setting_read",
    ] | None = None
    check_code: Literal[
        "test_component_outdated", "test_component_current", "debug_mode_enabled", "debug_mode_disabled",
    ] | None = None
    http_method: Literal["GET", "POST", "HEAD"] | None = None
    route_code: Literal["home", "login", "health", "api_read", "not_found"] | None = None
    status_code: int | None = Field(default=None, ge=100, le=599)
    error_code: Literal[
        "HANDLER_TIMEOUT", "SAFE_VALIDATION_REJECTED", "RESOURCE_NOT_FOUND", "DEMO_ERROR_RESPONSE",
    ] | None = None

    @field_validator("occurred_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("occurred_at must include a timezone offset")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def type_fields_are_exact(self) -> SyntheticTelemetryEvent:
        has_rate_fields = self.request_count is not None or self.window_seconds is not None
        has_http_fields = self.http_method is not None or self.route_code is not None or self.status_code is not None
        if self.event_type is TelemetryEventType.REQUEST_RATE:
            if self.request_count is None or self.window_seconds is None or has_http_fields or self.error_code is not None:
                raise ValueError("request_rate_indicator requires request_count and window_seconds")
            if self.activity_code is not None or self.check_code is not None:
                raise ValueError("request_rate_indicator cannot contain activity/check fields")
        elif self.event_type is TelemetryEventType.SIMULATED_ACTIVITY:
            if self.activity_code is None or self.check_code is not None or has_rate_fields:
                raise ValueError("simulated activity requires only an allowlisted activity_code")
        elif self.event_type in {TelemetryEventType.VULNERABILITY, TelemetryEventType.CONFIGURATION}:
            if self.check_code is None or self.activity_code is not None or has_rate_fields or has_http_fields or self.error_code is not None:
                raise ValueError("synthetic check event requires only an allowlisted check_code")
            if self.event_type is TelemetryEventType.VULNERABILITY and self.check_code not in {
                "test_component_outdated", "test_component_current",
            }:
                raise ValueError("vulnerability event check_code is unsupported")
            if self.event_type is TelemetryEventType.CONFIGURATION and self.check_code not in {
                "debug_mode_enabled", "debug_mode_disabled",
            }:
                raise ValueError("configuration event check_code is unsupported")
        elif self.event_type is TelemetryEventType.HTTP_ACCESS:
            if not has_http_fields or any(value is None for value in (self.http_method, self.route_code, self.status_code)):
                raise ValueError("synthetic_http_access requires method, route_code and status_code")
            if has_rate_fields or self.activity_code is not None or self.check_code is not None or self.error_code is not None:
                raise ValueError("synthetic_http_access cannot contain fields for other event types")
        elif self.event_type is TelemetryEventType.APPLICATION_ERROR:
            if self.error_code is None or has_http_fields or has_rate_fields or self.activity_code is not None or self.check_code is not None:
                raise ValueError("synthetic_application_error requires only an allowlisted error_code")
        elif self.event_type is TelemetryEventType.AUTH_FAILURE and has_http_fields:
            if any(value is None for value in (self.http_method, self.route_code, self.status_code)):
                raise ValueError("authentication HTTP evidence requires method, route_code and status_code")
            if self.http_method != "POST" or self.route_code != "login" or self.status_code not in {401, 403}:
                raise ValueError("authentication failure HTTP evidence must be a failed synthetic login")
            if has_rate_fields or self.activity_code is not None or self.check_code is not None or self.error_code is not None:
                raise ValueError("authentication HTTP evidence cannot contain fields for other event types")
        elif has_rate_fields or self.activity_code is not None or self.check_code is not None or has_http_fields or self.error_code is not None:
            raise ValueError("authentication events cannot contain fields for other event types")
        return self


class SyntheticTelemetryBatch(TelemetryModel):
    schema_version: Literal["1.0"]
    source_id: Literal["local_synthetic_fixture_v1"]
    data_classification: Literal["synthetic"]
    label: Literal["SYNTHETIC - NOT REAL CLIENT DATA"]
    generated_at: datetime
    events: list[SyntheticTelemetryEvent] = Field(min_length=1, max_length=MAX_TELEMETRY_EVENTS)

    @field_validator("generated_at")
    @classmethod
    def generated_time_must_be_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("generated_at must include a timezone offset")
        return value.astimezone(timezone.utc)


class TelemetryFinding(TelemetryModel):
    finding_id: str = Field(pattern=r"^tfinding-[a-f0-9]{12}$")
    rule_id: str = Field(min_length=1, max_length=40)
    rule_version: Literal["1.0"]
    severity: TelemetrySeverity
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False)
    first_seen_utc: datetime
    last_seen_utc: datetime
    asset_ref: str = Field(pattern=r"^synthetic-[a-zA-Z0-9_-]+$")
    evidence_refs: list[str] = Field(min_length=1, max_length=MAX_TELEMETRY_EVENTS)
    event_ids: list[str] = Field(min_length=1, max_length=MAX_TELEMETRY_EVENTS)
    explanation: str = Field(min_length=1, max_length=1000)
    confidence_factors: list[str] = Field(min_length=1, max_length=8)
    status: Literal["open", "acknowledged", "closed"] = "open"

    @model_validator(mode="after")
    def times_and_evidence_are_consistent(self) -> TelemetryFinding:
        if self.last_seen_utc < self.first_seen_utc:
            raise ValueError("last_seen_utc must not precede first_seen_utc")
        if len(set(self.evidence_refs)) != len(self.evidence_refs):
            raise ValueError("evidence references must be unique")
        if len(set(self.event_ids)) != len(self.event_ids):
            raise ValueError("event IDs must be unique")
        return self


class TelemetryReport(TelemetryModel):
    schema_version: Literal["1.0"]
    report_type: Literal["aegisai_local_synthetic_telemetry_report"]
    report_id: str = Field(pattern=r"^treport-[a-f0-9]{12}$")
    run_id: str = Field(pattern=r"^trun-[a-f0-9]{16}$")
    tenant_id: str = Field(pattern=r"^synthetic-org-[a-z0-9][a-z0-9-]{0,44}$")
    source_id: Literal["local_synthetic_fixture_v1"]
    data_classification: Literal["synthetic"]
    label: Literal["SYNTHETIC - NOT REAL CLIENT DATA"]
    generated_at_utc: datetime
    input_event_count: int = Field(ge=1)
    accepted_event_count: int = Field(ge=0)
    duplicate_event_count: int = Field(ge=0)
    findings: list[TelemetryFinding]
    limitations: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def counts_are_consistent(self) -> TelemetryReport:
        if self.input_event_count != self.accepted_event_count + self.duplicate_event_count:
            raise ValueError("input count must equal accepted plus duplicate events")
        return self


class TelemetryInputError(ValueError):
    """Safe validation error without echoing untrusted fixture contents."""


class TelemetryConflictError(ValueError):
    """A replay reused an event or evidence ID with conflicting content."""


def load_telemetry_bytes(raw: bytes) -> SyntheticTelemetryBatch:
    if len(raw) > MAX_INPUT_BYTES:
        raise TelemetryInputError("synthetic telemetry exceeds the 1 MiB size limit")
    try:
        return SyntheticTelemetryBatch.model_validate_json(raw)
    except Exception as exc:
        # Pydantic's error contains input values; keep only an issue count.
        errors = exc.errors() if hasattr(exc, "errors") else []
        raise TelemetryInputError(f"synthetic telemetry schema validation failed: {len(errors)} issue(s)") from None


def read_telemetry_file(path: Path) -> SyntheticTelemetryBatch:
    try:
        with path.open("rb") as fixture:
            raw = fixture.read(MAX_INPUT_BYTES + 1)
    except OSError as exc:
        raise TelemetryInputError(f"could not read synthetic source: {exc.__class__.__name__}") from None
    return load_telemetry_bytes(raw)


def normalize_and_deduplicate(batch: SyntheticTelemetryBatch) -> tuple[list[SyntheticTelemetryEvent], int]:
    by_event_id: dict[str, SyntheticTelemetryEvent] = {}
    canonical_by_id: dict[str, str] = {}
    evidence_owner: dict[str, str] = {}
    duplicate_count = 0
    for original in batch.events:
        event = original.model_copy(update={"occurred_at": original.occurred_at.astimezone(timezone.utc)})
        canonical = event.model_dump_json()
        prior = by_event_id.get(event.event_id)
        if prior is not None:
            if canonical_by_id[event.event_id] != canonical:
                raise TelemetryConflictError(f"event ID has conflicting content: {event.event_id}")
            duplicate_count += 1
            continue
        owner = evidence_owner.get(event.evidence_ref)
        if owner is not None and owner != event.event_id:
            raise TelemetryConflictError(f"evidence reference is assigned to multiple event IDs: {event.evidence_ref}")
        by_event_id[event.event_id] = event
        canonical_by_id[event.event_id] = canonical
        evidence_owner[event.evidence_ref] = event.event_id
    events = sorted(by_event_id.values(), key=lambda event: (event.occurred_at, event.event_id))
    return events, duplicate_count


def _finding_id(tenant_id: str, rule_id: str, correlation_key: str) -> str:
    value = hashlib.sha256(f"{tenant_id}\0{rule_id}\0{RULE_VERSION}\0{correlation_key}".encode()).hexdigest()[:12]
    return f"tfinding-{value}"


def _make_finding(
    *, tenant_id: str, rule_id: str, correlation_key: str, severity: TelemetrySeverity,
    confidence: float, explanation: str, factors: list[str], events: list[SyntheticTelemetryEvent],
) -> TelemetryFinding:
    ordered = sorted(events, key=lambda item: (item.occurred_at, item.event_id))
    return TelemetryFinding(
        finding_id=_finding_id(tenant_id, rule_id, correlation_key),
        rule_id=rule_id, rule_version=RULE_VERSION, severity=severity, confidence=confidence,
        first_seen_utc=ordered[0].occurred_at, last_seen_utc=ordered[-1].occurred_at,
        asset_ref=ordered[0].asset_ref,
        evidence_refs=list(dict.fromkeys(item.evidence_ref for item in ordered)),
        event_ids=list(dict.fromkeys(item.event_id for item in ordered)),
        explanation=explanation, confidence_factors=factors, status="open",
    )


def detect_findings(
    events: list[SyntheticTelemetryEvent], *, tenant_id: str,
) -> list[TelemetryFinding]:
    findings: list[TelemetryFinding] = []
    by_evidence = {event.evidence_ref: event for event in events}
    auth_events = [event for event in events if event.event_type in {
        TelemetryEventType.AUTH_FAILURE, TelemetryEventType.AUTH_SUCCESS,
    }]
    if auth_events:
        auth_batch = SyntheticEventBatch(
            schema_version="1.0", dataset_id="synthetic-telemetry-auth-v1",
            data_classification="synthetic", label="SYNTHETIC - NOT REAL CLIENT DATA",
            generated_at=datetime.now(timezone.utc),
            events=[SyntheticEvent(
                event_id=event.event_id, occurred_at=event.occurred_at,
                event_type=event.event_type.value, asset_ref=event.asset_ref,
                actor_ref=event.actor_ref, source_ref=event.source_ref,
                evidence_ref=event.evidence_ref,
            ) for event in auth_events],
        )
        auth_report = build_report(auth_batch)
        for finding in auth_report.findings:
            supporting = [by_evidence[ref] for ref in finding.evidence_refs]
            rule_id = "AUTH-001"
            correlation = "|".join((rule_id, *sorted(item.event_id for item in supporting)))
            severity = TelemetrySeverity(finding.severity.value)
            findings.append(_make_finding(
                tenant_id=tenant_id, rule_id=rule_id, correlation_key=correlation,
                severity=severity, confidence=finding.confidence,
                explanation=f"{finding.title}. " + "; ".join(finding.confidence_factors),
                factors=finding.confidence_factors, events=supporting,
            ))

    request_groups: dict[tuple[str, str, str], list[SyntheticTelemetryEvent]] = {}
    activity_groups: dict[tuple[str, str, str, str], list[SyntheticTelemetryEvent]] = {}
    check_groups: dict[tuple[str, str, str], list[SyntheticTelemetryEvent]] = {}
    for event in events:
        key = (event.asset_ref, event.actor_ref, event.source_ref)
        if event.event_type is TelemetryEventType.REQUEST_RATE:
            request_groups.setdefault(key, []).append(event)
        elif event.event_type is TelemetryEventType.SIMULATED_ACTIVITY:
            if event.activity_code in {"unexpected_admin_setting_change", "unusual_synthetic_file_access"}:
                activity_groups.setdefault((*key, event.activity_code), []).append(event)
        elif event.event_type in {TelemetryEventType.VULNERABILITY, TelemetryEventType.CONFIGURATION}:
            finding_codes = {"test_component_outdated", "debug_mode_enabled"}
            if event.check_code in finding_codes:
                check_groups.setdefault((event.asset_ref, event.event_type.value, event.check_code), []).append(event)

    for key, group in sorted(request_groups.items()):
        qualifying = [event for event in group
                      if event.request_count is not None and event.request_count >= REQUEST_RATE_THRESHOLD
                      and event.window_seconds is not None and event.window_seconds <= REQUEST_RATE_WINDOW_SECONDS]
        if not qualifying:
            continue
        peak = max(event.request_count or 0 for event in qualifying)
        high = peak >= 500
        correlated = [event for event in qualifying
                      if max(item.occurred_at for item in qualifying) - event.occurred_at <= DETECTION_WINDOW]
        count = sum(item.request_count or 0 for item in correlated)
        findings.append(_make_finding(
            tenant_id=tenant_id, rule_id="WEB-001",
            correlation_key="|".join(("WEB-001", *key)),
            severity=TelemetrySeverity.HIGH if high else TelemetrySeverity.MEDIUM,
            confidence=0.92 if high else 0.82,
            explanation=(f"Synthetic request-rate indicators totaled {count} requests in windows of "
                         f"{REQUEST_RATE_WINDOW_SECONDS} seconds or less; the highest indicator was {peak}."),
            factors=[f"{len(correlated)} allowlisted request-rate indicator(s) matched",
                     f"peak indicator {peak} met the {'high' if high else 'medium'} demonstration threshold",
                     "all records are from the labeled synthetic local source"],
            events=correlated,
        ))

    for key, group in sorted(activity_groups.items()):
        kind = key[-1]
        findings.append(_make_finding(
            tenant_id=tenant_id, rule_id="APP-001",
            correlation_key="|".join(("APP-001", *key)),
            severity=TelemetrySeverity.HIGH, confidence=0.85,
            explanation=f"The synthetic fixture contains simulated application activity: {kind}.",
            factors=["activity code is explicitly allowlisted in telemetry schema",
                     "finding is based on fixture metadata rather than observed client behavior",
                     "all records are synthetic"], events=group,
        ))

    for key, group in sorted(check_groups.items()):
        asset_ref, kind, check_code = key
        is_vulnerability = kind == TelemetryEventType.VULNERABILITY.value
        rule_id = "VULN-001" if is_vulnerability else "CONFIG-001"
        display = "synthetic component/version check" if is_vulnerability else "synthetic configuration check"
        findings.append(_make_finding(
            tenant_id=tenant_id, rule_id=rule_id,
            correlation_key="|".join((rule_id, asset_ref, check_code)),
            severity=TelemetrySeverity.MEDIUM, confidence=0.80,
            explanation=f"The synthetic fixture records {display} `{check_code}` for {asset_ref}.",
            factors=[f"allowlisted synthetic check code: {check_code}",
                     "no client asset was inspected", "all records are synthetic"], events=group,
        ))
    return sorted(findings, key=lambda item: (item.rule_id, item.finding_id))


def make_telemetry_report(
    *, tenant_id: str, run_id: str, source_id: str,
    input_count: int, accepted_count: int, duplicate_count: int,
    findings: list[TelemetryFinding], generated_at: datetime | None = None,
) -> TelemetryReport:
    report_id = "treport-" + hashlib.sha256(f"{tenant_id}\0{run_id}".encode()).hexdigest()[:12]
    return TelemetryReport(
        schema_version="1.0", report_type="aegisai_local_synthetic_telemetry_report",
        report_id=report_id, run_id=run_id, tenant_id=tenant_id, source_id=source_id,
        data_classification="synthetic", label="SYNTHETIC - NOT REAL CLIENT DATA",
        generated_at_utc=(generated_at or datetime.now(timezone.utc)).astimezone(timezone.utc),
        input_event_count=input_count, accepted_event_count=accepted_count,
        duplicate_event_count=duplicate_count, findings=findings,
        limitations=[
            "Synthetic fixture only; findings do not represent real attacks or real detections.",
            "Rules and severity thresholds are deterministic demonstrations, not calibrated production controls.",
            "No external systems, client telemetry, scans, LLMs, or defensive actions are used.",
        ],
    )
