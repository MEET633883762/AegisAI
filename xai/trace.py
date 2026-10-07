"""Structured, evidence-grounded XAI decision traces.

XAI in AegisAI records observable decision context and factual outcomes. It does not
attempt to expose or reconstruct hidden chain-of-thought.
"""
from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from environment.actions import ActionResult, Role
from telemetry.observation_builder import BlueObservation, RedObservation


class ReasonCategory(str, Enum):
    RECONNAISSANCE = "reconnaissance"
    INITIAL_ACCESS = "initial_access"
    CREDENTIAL_ACCESS = "credential_access"
    LATERAL_MOVEMENT = "lateral_movement"
    COLLECTION = "collection"
    EXFILTRATION = "exfiltration"
    MONITORING = "monitoring"
    INVESTIGATION = "investigation"
    CONTAINMENT = "containment"
    HARDENING = "hardening"
    RECOVERY = "recovery"
    INCIDENT_MANAGEMENT = "incident_management"
    OTHER = "other"


class EvidenceItem(BaseModel):
    """Small, structured evidence item copied only from the agent-visible observation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source: str
    reference: str
    value: str


class DecisionTrace(BaseModel):
    """One auditable observation -> decision -> outcome record.

    `rationale` is the agent-generated explanation, not a claim of hidden model reasoning.
    `evidence` contains only information available to the agent at decision time.
    `actual_outcome` and `success` are controller/environment facts.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    trace_id: int
    episode_id: str
    scenario_id: str
    step: int
    role: Role
    timestamp: str
    observation: dict[str, Any]
    evidence: list[EvidenceItem] = Field(default_factory=list)
    action: dict[str, Any]
    rationale: str = ""
    reason_category: ReasonCategory = ReasonCategory.OTHER
    expected_outcome: str | None = None
    actual_outcome: str | None = None
    success: bool | None = None
    state_change_count: int = 0
    event_ids: list[int] = Field(default_factory=list)
    post_hoc_lesson: str | None = None
    provider: str | None = None
    model: str | None = None
    decision_latency_seconds: float | None = Field(default=None, ge=0.0)


def observation_dict(observation: RedObservation | BlueObservation) -> dict[str, Any]:
    """Return an isolated JSON-compatible snapshot of the role-visible observation."""
    return observation.model_dump(mode="json")


def extract_evidence(observation: RedObservation | BlueObservation) -> list[EvidenceItem]:
    """Extract concise evidence without consulting hidden simulator/controller state."""
    items: list[EvidenceItem] = []

    if isinstance(observation, RedObservation):
        for host in observation.known_hosts:
            items.append(EvidenceItem(
                source="red_observation",
                reference=f"host:{host.id}",
                value=(f"compromised={host.compromised};ports={host.open_ports};"
                       f"services={[s.name for s in host.services]}"),
            ))
        for credential in observation.known_credentials:
            items.append(EvidenceItem(
                source="red_observation",
                reference=f"credential:{credential.id}",
                value=f"principal={credential.principal}",
            ))
        if observation.last_result is not None:
            items.append(EvidenceItem(
                source="red_observation",
                reference="last_result",
                value=(f"action={observation.last_result.action_type};"
                       f"target={observation.last_result.target};"
                       f"success={observation.last_result.success};"
                       f"outcome={observation.last_result.outcome.value}"),
            ))
    else:
        for alert in observation.alerts:
            items.append(EvidenceItem(
                source="blue_observation",
                reference=f"alert:{alert.alert_id}",
                value=(f"type={alert.type};host={alert.host};severity={alert.severity.value};"
                       f"investigated={alert.investigated}"),
            ))
        for event in observation.recent_events:
            items.append(EvidenceItem(
                source="blue_observation",
                reference=f"event:{event.event_id}",
                value=f"type={event.type};host={event.host};src={event.src}",
            ))
        if observation.last_result is not None:
            items.append(EvidenceItem(
                source="blue_observation",
                reference="last_result",
                value=(f"action={observation.last_result.action_type};"
                       f"target={observation.last_result.target};"
                       f"success={observation.last_result.success};"
                       f"outcome={observation.last_result.outcome.value}"),
            ))

    return items


_REASON_MAP = {
    "DISCOVER_HOST": ReasonCategory.RECONNAISSANCE,
    "DISCOVER_SERVICE": ReasonCategory.RECONNAISSANCE,
    "ENUMERATE_PORT": ReasonCategory.RECONNAISSANCE,
    "ATTEMPT_ACCESS": ReasonCategory.INITIAL_ACCESS,
    "EXPLOIT_SIMULATED_VULNERABILITY": ReasonCategory.INITIAL_ACCESS,
    "OBTAIN_CREDENTIAL": ReasonCategory.CREDENTIAL_ACCESS,
    "LATERAL_MOVE": ReasonCategory.LATERAL_MOVEMENT,
    "ACCESS_SENSITIVE_ASSET": ReasonCategory.COLLECTION,
    "COLLECT_DATA": ReasonCategory.COLLECTION,
    "EXFILTRATE_SIMULATED_DATA": ReasonCategory.EXFILTRATION,
    "MONITOR": ReasonCategory.MONITORING,
    "INVESTIGATE_ALERT": ReasonCategory.INVESTIGATION,
    "BLOCK_SOURCE": ReasonCategory.CONTAINMENT,
    "DISABLE_SERVICE": ReasonCategory.CONTAINMENT,
    "ISOLATE_HOST": ReasonCategory.CONTAINMENT,
    "RESET_CREDENTIAL": ReasonCategory.HARDENING,
    "PATCH_SIMULATED_VULNERABILITY": ReasonCategory.HARDENING,
    "INCREASE_LOGGING": ReasonCategory.MONITORING,
    "RESTORE_SERVICE": ReasonCategory.RECOVERY,
    "MARK_INCIDENT": ReasonCategory.INCIDENT_MANAGEMENT,
}


def reason_category(action_type: str) -> ReasonCategory:
    return _REASON_MAP.get(action_type, ReasonCategory.OTHER)


def expected_outcome(action_type: str) -> str:
    """Deterministic action-intent description; not a prediction by the LLM."""
    descriptions = {
        "DISCOVER_HOST": "discover an authorized simulated host if reachable",
        "DISCOVER_SERVICE": "discover services on the authorized simulated target",
        "ENUMERATE_PORT": "enumerate ports on the authorized simulated target",
        "ATTEMPT_ACCESS": "attempt the authorized simulated access operation",
        "EXPLOIT_SIMULATED_VULNERABILITY": "attempt the modeled vulnerability transition",
        "OBTAIN_CREDENTIAL": "attempt to obtain a modeled credential",
        "LATERAL_MOVE": "attempt authorized simulated lateral movement",
        "ACCESS_SENSITIVE_ASSET": "access the modeled sensitive asset",
        "COLLECT_DATA": "collect the modeled asset data",
        "EXFILTRATE_SIMULATED_DATA": "complete the modeled data exfiltration objective",
        "MONITOR": "observe without applying a defensive state change",
        "INVESTIGATE_ALERT": "inspect the selected simulated alert evidence",
        "BLOCK_SOURCE": "block the selected simulated source",
        "DISABLE_SERVICE": "disable the selected simulated service",
        "ISOLATE_HOST": "isolate the selected simulated host",
        "RESET_CREDENTIAL": "reset the selected simulated credential",
        "PATCH_SIMULATED_VULNERABILITY": "patch the selected modeled vulnerability",
        "INCREASE_LOGGING": "increase simulated logging coverage",
        "RESTORE_SERVICE": "restore the selected simulated service or isolation state",
        "MARK_INCIDENT": "record the selected simulated incident",
    }
    return descriptions.get(action_type, "complete the authorized simulated action")


def build_trace(*, trace_id: int, episode_id: str, scenario_id: str,
                observation: RedObservation | BlueObservation, action: Any,
                result: ActionResult, timestamp: str, authorized: bool,
                provider: str | None = None, model: str | None = None,
                decision_latency_seconds: float | None = None) -> DecisionTrace:
    action_type = getattr(getattr(action, "action_type", None), "value", "INVALID")
    rationale = str(getattr(action, "rationale", ""))
    return DecisionTrace(
        trace_id=trace_id,
        episode_id=episode_id,
        scenario_id=scenario_id,
        step=observation.step,
        role=result.role,
        timestamp=timestamp,
        observation=observation_dict(observation),
        evidence=extract_evidence(observation),
        action={
            "action_type": action_type,
            "target": getattr(action, "target", "invalid"),
            "parameters": dict(getattr(action, "parameters", {})),
            "authorized": authorized,
        },
        rationale=rationale,
        reason_category=reason_category(action_type),
        expected_outcome=expected_outcome(action_type),
        actual_outcome=result.outcome.value,
        success=result.success,
        state_change_count=len(result.state_changes),
        event_ids=list(result.event_ids),
        provider=provider,
        model=model,
        decision_latency_seconds=decision_latency_seconds,
    )
