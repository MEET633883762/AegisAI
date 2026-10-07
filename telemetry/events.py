"""Structured telemetry events and alert rules. Telemetry is DATA, never instructions."""
from __future__ import annotations

from enum import Enum
from typing import Literal, NamedTuple

from pydantic import BaseModel, ConfigDict, Field


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class EventType(str, Enum):
    NETWORK_PROBE = "network_probe"
    AUTH_FAILURE = "auth_failure"
    AUTH_SUCCESS = "auth_success"
    EXPLOIT_ATTEMPT = "exploit_attempt"
    CREDENTIAL_ACCESS = "credential_access"
    LATERAL_MOVEMENT = "lateral_movement"
    SENSITIVE_DATA_ACCESS = "sensitive_data_access"
    DATA_COLLECTION = "data_collection"
    DATA_EXFILTRATION = "data_exfiltration"
    BENIGN_LOGIN = "benign_login"
    BENIGN_AUTH_FAILURE = "benign_auth_failure"  # source of false-positive alerts
    # Blue-side control-plane events
    SOURCE_BLOCKED = "source_blocked"
    SERVICE_DISABLED = "service_disabled"
    SERVICE_RESTORED = "service_restored"
    HOST_ISOLATED = "host_isolated"
    HOST_RESTORED = "host_restored"
    CREDENTIAL_RESET = "credential_reset"
    VULNERABILITY_PATCHED = "vulnerability_patched"
    LOGGING_INCREASED = "logging_increased"
    INCIDENT_MARKED = "incident_marked"


class EventRule(NamedTuple):
    min_level: int  # host logging level required for the event to be recorded for Blue
    alert_type: str | None
    severity: Severity | None


_NONE = EventRule(1, None, None)
EVENT_RULES: dict[EventType, EventRule] = {
    EventType.NETWORK_PROBE: EventRule(2, "scan_activity", Severity.LOW),
    EventType.AUTH_FAILURE: EventRule(1, "auth_anomaly", Severity.MEDIUM),
    EventType.AUTH_SUCCESS: _NONE,
    EventType.EXPLOIT_ATTEMPT: EventRule(2, "exploit_attempt", Severity.HIGH),
    EventType.CREDENTIAL_ACCESS: EventRule(2, "credential_access", Severity.HIGH),
    EventType.LATERAL_MOVEMENT: EventRule(1, "lateral_movement", Severity.HIGH),
    EventType.SENSITIVE_DATA_ACCESS: EventRule(1, "sensitive_data_access", Severity.HIGH),
    EventType.DATA_COLLECTION: EventRule(2, "bulk_data_read", Severity.MEDIUM),
    EventType.DATA_EXFILTRATION: EventRule(1, "data_exfiltration", Severity.CRITICAL),
    EventType.BENIGN_LOGIN: _NONE,
    EventType.BENIGN_AUTH_FAILURE: EventRule(1, "auth_anomaly", Severity.MEDIUM),
    EventType.SOURCE_BLOCKED: _NONE,
    EventType.SERVICE_DISABLED: _NONE,
    EventType.SERVICE_RESTORED: _NONE,
    EventType.HOST_ISOLATED: _NONE,
    EventType.HOST_RESTORED: _NONE,
    EventType.CREDENTIAL_RESET: _NONE,
    EventType.VULNERABILITY_PATCHED: _NONE,
    EventType.LOGGING_INCREASED: _NONE,
    EventType.INCIDENT_MARKED: _NONE,
}


class TelemetryEvent(BaseModel):
    """Ground-truth event. `actor` and `blue_visible` are internal and are stripped from any
    agent-facing view."""

    model_config = ConfigDict(extra="forbid")

    event_id: int
    step: int
    type: EventType
    host: str
    src: str | None = None
    actor: Literal["red", "blue", "benign"]
    details: dict[str, str] = Field(default_factory=dict)
    blue_visible: bool


class Alert(BaseModel):
    model_config = ConfigDict(extra="forbid")

    alert_id: int
    step: int
    type: str
    host: str
    severity: Severity
    evidence_event_ids: list[int]
    investigated: bool = False
