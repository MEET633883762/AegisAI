"""Deterministic episode metrics derived from controller audit and telemetry evidence."""
from __future__ import annotations

from dataclasses import dataclass
from statistics import mean
from typing import Iterable

from controller.orchestrator import AuditRecord, Controller
from environment.actions import BlueActionType
from telemetry.events import Alert, EventType, Severity, TelemetryEvent


RESPONSE_ACTIONS = {
    BlueActionType.BLOCK_SOURCE.value,
    BlueActionType.DISABLE_SERVICE.value,
    BlueActionType.ISOLATE_HOST.value,
    BlueActionType.RESET_CREDENTIAL.value,
    BlueActionType.PATCH_SIMULATED_VULNERABILITY.value,
}


@dataclass(frozen=True)
class EpisodeMetrics:
    """Metrics for one completed or bounded simulation episode."""

    scenario_id: str
    template_id: str
    seed: int
    steps: int
    attack_success: bool
    detection_rate: float
    mean_detection_time: float | None
    mitigation_success_rate: float
    false_positive_rate: float
    decision_latency_ms: float | None
    total_alerts: int
    malicious_alerts: int
    benign_alerts: int
    response_required_alerts: int
    detected_malicious_alerts: int
    mitigated_alerts: int


@dataclass(frozen=True)
class AggregateMetrics:
    """Aggregate metrics across a reproducible set of episode results."""

    episodes: int
    attack_success_rate: float
    detection_rate: float
    mean_detection_time: float | None
    mitigation_success_rate: float
    false_positive_rate: float
    mean_decision_latency_ms: float | None


def _event_map(events: Iterable[TelemetryEvent]) -> dict[int, TelemetryEvent]:
    return {event.event_id: event for event in events}


def _alert_is_benign(alert: Alert, events: dict[int, TelemetryEvent]) -> bool:
    evidence = [events[eid] for eid in alert.evidence_event_ids if eid in events]
    return bool(evidence) and all(event.actor == "benign" for event in evidence)


def _alert_is_malicious(alert: Alert, events: dict[int, TelemetryEvent]) -> bool:
    evidence = [events[eid] for eid in alert.evidence_event_ids if eid in events]
    return bool(evidence) and any(event.actor == "red" for event in evidence)


def _detection_steps(alert: Alert, events: dict[int, TelemetryEvent], audit: list[AuditRecord]) -> int | None:
    evidence_steps = [events[eid].step for eid in alert.evidence_event_ids if eid in events]
    if not evidence_steps:
        return None
    candidates = [
        record.step for record in audit
        if record.role.value == "blue"
        and record.action_type == BlueActionType.INVESTIGATE_ALERT.value
        and record.authorized
        and record.success
        and record.target == alert.host
        and record.parameters.get("alert_id") == str(alert.alert_id)
        and record.step >= alert.step
    ]
    if not candidates:
        return None
    return max(0, min(candidates) - min(evidence_steps))


def _has_mitigation(alert: Alert, audit: list[AuditRecord]) -> bool:
    if alert.severity not in {Severity.HIGH, Severity.CRITICAL}:
        return False
    return any(
        record.role.value == "blue"
        and record.authorized
        and record.success
        and record.action_type in RESPONSE_ACTIONS
        and record.step >= alert.step
        and record.target == alert.host
        for record in audit
    )


def calculate_episode_metrics(
    controller: Controller,
    *,
    decision_latencies_ms: Iterable[float] = (),
) -> EpisodeMetrics:
    """Calculate metrics from controller-owned audit/telemetry evidence.

    No metric is manually supplied by an agent. Attack success comes from the
    simulator ground truth; detection/false-positive metrics come from alert
    evidence and Blue investigation; mitigation comes from authorized successful
    defensive actions.
    """
    events = _event_map(controller.telemetry_log().events())
    alerts = list(controller.telemetry_log().alerts())
    audit = list(controller.audit_log())

    malicious = [a for a in alerts if _alert_is_malicious(a, events)]
    benign = [a for a in alerts if _alert_is_benign(a, events)]
    investigated_ids = {
        record.parameters.get("alert_id")
        for record in audit
        if record.role.value == "blue"
        and record.action_type == BlueActionType.INVESTIGATE_ALERT.value
        and record.authorized
        and record.success
    }
    detected = [a for a in malicious if str(a.alert_id) in investigated_ids]
    response_required = [a for a in malicious if a.severity in {Severity.HIGH, Severity.CRITICAL}]
    mitigated = [a for a in response_required if _has_mitigation(a, audit)]

    detection_times = [
        dt for alert in malicious
        if (dt := _detection_steps(alert, events, audit)) is not None
    ]
    latencies = list(decision_latencies_ms)

    attack_success = any(
        event.actor == "red" and event.type is EventType.DATA_EXFILTRATION
        for event in events.values()
    )

    return EpisodeMetrics(
        scenario_id=controller.scenario.scenario_id,
        template_id=controller.scenario.template_id,
        seed=controller.scenario.seed,
        steps=controller.step,
        attack_success=attack_success,
        detection_rate=(len(detected) / len(malicious)) if malicious else 0.0,
        mean_detection_time=mean(detection_times) if detection_times else None,
        mitigation_success_rate=(len(mitigated) / len(response_required)) if response_required else 0.0,
        false_positive_rate=(sum(1 for a in benign if str(a.alert_id) in investigated_ids) / len(benign)) if benign else 0.0,
        decision_latency_ms=mean(latencies) if latencies else None,
        total_alerts=len(alerts),
        malicious_alerts=len(malicious),
        benign_alerts=len(benign),
        response_required_alerts=len(response_required),
        detected_malicious_alerts=len(detected),
        mitigated_alerts=len(mitigated),
    )


def aggregate_metrics(results: Iterable[EpisodeMetrics]) -> AggregateMetrics:
    rows = list(results)
    if not rows:
        raise ValueError("at least one episode result is required")
    detection_values = [r.detection_rate for r in rows]
    mitigation_values = [r.mitigation_success_rate for r in rows]
    fp_values = [r.false_positive_rate for r in rows]
    detection_times = [r.mean_detection_time for r in rows if r.mean_detection_time is not None]
    latencies = [r.decision_latency_ms for r in rows if r.decision_latency_ms is not None]
    return AggregateMetrics(
        episodes=len(rows),
        attack_success_rate=sum(r.attack_success for r in rows) / len(rows),
        detection_rate=mean(detection_values),
        mean_detection_time=mean(detection_times) if detection_times else None,
        mitigation_success_rate=mean(mitigation_values),
        false_positive_rate=mean(fp_values),
        mean_decision_latency_ms=mean(latencies) if latencies else None,
    )
