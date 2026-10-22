"""Bounded parsing, normalization, deduplication, and synthetic correlation."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pydantic import ValidationError

from platform_prototype.models import (
    ActionRequest,
    EvidenceReference,
    EventType,
    Finding,
    IncidentReport,
    Severity,
    SimulatedActionOutcome,
    SyntheticEvent,
    SyntheticEventBatch,
)
from platform_prototype.policy import evaluate_simulated_actions

MAX_INPUT_BYTES = 1_048_576
AUTH_FAILURE_WINDOW = timedelta(minutes=10)
SUCCESS_AFTER_FAILURE_WINDOW = timedelta(minutes=5)


class PrototypeInputError(ValueError):
    """Safe, input-independent explanation for rejected fixture data."""


def load_batch_bytes(data: bytes) -> SyntheticEventBatch:
    if len(data) > MAX_INPUT_BYTES:
        raise PrototypeInputError("synthetic event batch exceeds the 1 MiB size limit")
    try:
        batch = SyntheticEventBatch.model_validate_json(data)
    except ValidationError as exc:
        raise PrototypeInputError(f"synthetic event batch failed schema validation: {len(exc.errors())} issue(s)") from None
    return batch


def read_batch_file(path: Path) -> SyntheticEventBatch:
    try:
        with path.open("rb") as source:
            data = source.read(MAX_INPUT_BYTES + 1)
    except OSError as exc:
        raise PrototypeInputError(f"could not read input file: {exc.__class__.__name__}") from None
    return load_batch_bytes(data)


def _utc(value: datetime) -> datetime:
    return value.astimezone(timezone.utc)


def _stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("\0".join(parts).encode("utf-8")).hexdigest()[:12]
    return f"{prefix}-{digest}"


def _normalize_and_deduplicate(batch: SyntheticEventBatch) -> tuple[list[SyntheticEvent], int]:
    unique: dict[str, SyntheticEvent] = {}
    canonical: dict[str, str] = {}
    evidence_owners: dict[str, str] = {}
    duplicate_count = 0
    for original in batch.events:
        event = original.model_copy(update={"occurred_at": _utc(original.occurred_at)})
        serialized = event.model_dump_json()
        if event.event_id in unique:
            if canonical[event.event_id] != serialized:
                raise PrototypeInputError(f"conflicting duplicate event ID: {event.event_id}")
            duplicate_count += 1
            continue
        evidence_owner = evidence_owners.get(event.evidence_ref)
        if evidence_owner is not None and evidence_owner != event.event_id:
            raise PrototypeInputError(f"evidence reference is assigned to multiple event IDs: {event.evidence_ref}")
        unique[event.event_id] = event
        canonical[event.event_id] = serialized
        evidence_owners[event.evidence_ref] = event.event_id
    return sorted(unique.values(), key=lambda item: (item.occurred_at, item.event_id)), duplicate_count


def _best_failure_window(events: list[SyntheticEvent]) -> list[SyntheticEvent]:
    failures = [item for item in events if item.event_type is EventType.AUTH_FAILURE]
    best: list[SyntheticEvent] = []
    right = 0
    for left in range(len(failures)):
        right = max(right, left)
        while right < len(failures) and failures[right].occurred_at - failures[left].occurred_at <= AUTH_FAILURE_WINDOW:
            right += 1
        window = failures[left:right]
        if len(window) > len(best):
            best = window
    return best if len(best) >= 3 else []


def _correlate(events: list[SyntheticEvent]) -> list[Finding]:
    groups: dict[tuple[str, str, str], list[SyntheticEvent]] = {}
    for event in events:
        key = (event.asset_ref, event.actor_ref, event.source_ref)
        groups.setdefault(key, []).append(event)

    findings: list[Finding] = []
    for key, group in sorted(groups.items()):
        group.sort(key=lambda item: (item.occurred_at, item.event_id))
        failure_window = _best_failure_window(group)
        if not failure_window:
            continue

        last_failure = failure_window[-1].occurred_at
        success = next((item for item in group
                        if item.event_type is EventType.AUTH_SUCCESS
                        and timedelta(0) <= item.occurred_at - last_failure <= SUCCESS_AFTER_FAILURE_WINDOW), None)
        correlated = failure_window + ([success] if success else [])
        signal_types = [EventType.AUTH_FAILURE]
        if success:
            signal_types.append(EventType.AUTH_SUCCESS)
            rule_id = "auth_failures_followed_by_success"
            title = "Repeated synthetic authentication failures followed by success"
            severity = Severity.HIGH
            confidence = 0.90
            factors = [
                f"{len(failure_window)} distinct failures occurred within {int(AUTH_FAILURE_WINDOW.total_seconds() / 60)} minutes",
                "a success for the same synthetic asset, actor, and source followed within five minutes",
                "all evidence is from the labeled synthetic fixture",
            ]
            recommendation = "Manually review the synthetic authentication sequence; no account or session action was taken."
        else:
            rule_id = "synthetic_auth_failure_burst"
            title = "Repeated synthetic authentication failures"
            severity = Severity.HIGH if len(failure_window) >= 5 else Severity.MEDIUM
            confidence = min(0.95, 0.70 + 0.05 * (len(failure_window) - 3))
            factors = [
                f"{len(failure_window)} distinct failures occurred within {int(AUTH_FAILURE_WINDOW.total_seconds() / 60)} minutes",
                "asset, actor, and source references matched across the correlation window",
                "all evidence is from the labeled synthetic fixture",
            ]
            recommendation = "Manually review the synthetic authentication pattern and its evidence references."

        evidence_refs = [item.evidence_ref for item in correlated]
        event_ids = [item.event_id for item in correlated]
        finding_id = _stable_id("finding", rule_id, *event_ids)
        findings.append(Finding(
            finding_id=finding_id,
            correlation_key="|".join(key),
            rule_id=rule_id,
            title=title,
            severity=severity,
            confidence=confidence,
            confidence_factors=factors,
            signal_types=signal_types,
            evidence_refs=evidence_refs,
            recommendation=recommendation,
        ))
    return findings


def build_report(
    batch: SyntheticEventBatch,
    *,
    actions: list[ActionRequest] | None = None,
    generated_at: datetime | None = None,
) -> IncidentReport:
    events, duplicate_count = _normalize_and_deduplicate(batch)
    findings = _correlate(events)
    outcomes: list[SimulatedActionOutcome] = []
    if actions:
        outcomes = evaluate_simulated_actions(findings, actions)

    evidence_catalog = [EvidenceReference(
        evidence_ref=event.evidence_ref,
        event_id=event.event_id,
        event_type=event.event_type,
        occurred_at_utc=event.occurred_at,
        asset_ref=event.asset_ref,
        actor_ref=event.actor_ref,
        source_ref=event.source_ref,
    ) for event in events]
    report_id = _stable_id("report", batch.dataset_id, *(event.event_id for event in events))
    return IncidentReport(
        schema_version="1.0",
        report_type="aegisai_local_synthetic_incident_report",
        report_id=report_id,
        generated_at_utc=_utc(generated_at or datetime.now(timezone.utc)),
        data_classification="synthetic",
        label="SYNTHETIC - NOT REAL CLIENT DATA",
        dataset_id=batch.dataset_id,
        input_event_count=len(batch.events),
        unique_event_count=len(events),
        duplicate_event_count=duplicate_count,
        evidence_catalog=evidence_catalog,
        findings=findings,
        simulated_actions=outcomes,
        limitations=[
            "Synthetic fixture only; this report is not a real detection or security assessment.",
            "The deterministic rule demonstrates correlation logic and has not been validated against production telemetry.",
            "Recommendations are for manual review; simulated actions never contact systems or change state.",
        ],
    )


def analyze_bytes(
    data: bytes,
    *,
    actions: list[ActionRequest] | None = None,
    generated_at: datetime | None = None,
) -> IncidentReport:
    batch = load_batch_bytes(data)
    return build_report(batch, actions=actions, generated_at=generated_at)


def report_json(report: IncidentReport) -> str:
    return json.dumps(report.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n"
