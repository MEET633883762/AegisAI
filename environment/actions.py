"""Allowlisted action vocabularies, structured action schemas and the ActionResult type.

Actions are *requests*. They carry no executable content; free text is limited to `rationale`,
which the simulator never interprets.
"""
from __future__ import annotations

import re
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_ID = re.compile(r"^[a-z0-9_]{1,64}$")
_PARAM_KEY = re.compile(r"^[a-z_]{1,32}$")
_PARAM_VAL = re.compile(r"^[A-Za-z0-9_.:-]{1,64}$")
MAX_PARAMS = 8


class Role(str, Enum):
    RED = "red"
    BLUE = "blue"


class RedActionType(str, Enum):
    DISCOVER_HOST = "DISCOVER_HOST"
    DISCOVER_SERVICE = "DISCOVER_SERVICE"
    ENUMERATE_PORT = "ENUMERATE_PORT"
    ATTEMPT_ACCESS = "ATTEMPT_ACCESS"
    EXPLOIT_SIMULATED_VULNERABILITY = "EXPLOIT_SIMULATED_VULNERABILITY"
    OBTAIN_CREDENTIAL = "OBTAIN_CREDENTIAL"
    LATERAL_MOVE = "LATERAL_MOVE"
    ACCESS_SENSITIVE_ASSET = "ACCESS_SENSITIVE_ASSET"
    COLLECT_DATA = "COLLECT_DATA"
    EXFILTRATE_SIMULATED_DATA = "EXFILTRATE_SIMULATED_DATA"


class BlueActionType(str, Enum):
    MONITOR = "MONITOR"
    INVESTIGATE_ALERT = "INVESTIGATE_ALERT"
    BLOCK_SOURCE = "BLOCK_SOURCE"
    DISABLE_SERVICE = "DISABLE_SERVICE"
    ISOLATE_HOST = "ISOLATE_HOST"
    RESET_CREDENTIAL = "RESET_CREDENTIAL"
    PATCH_SIMULATED_VULNERABILITY = "PATCH_SIMULATED_VULNERABILITY"
    INCREASE_LOGGING = "INCREASE_LOGGING"
    RESTORE_SERVICE = "RESTORE_SERVICE"
    MARK_INCIDENT = "MARK_INCIDENT"


# Allowed parameter keys per action. Anything else is rejected, never silently ignored.
# Whether a key is *required* is enforced by the simulator (missing -> INVALID_PARAMETER).
_NONE: frozenset[str] = frozenset()
RED_ALLOWED_PARAMETERS: dict[RedActionType, frozenset[str]] = {
    RedActionType.DISCOVER_HOST: _NONE,
    RedActionType.DISCOVER_SERVICE: _NONE,
    RedActionType.ENUMERATE_PORT: _NONE,
    RedActionType.ATTEMPT_ACCESS: frozenset({"credential_id"}),
    RedActionType.EXPLOIT_SIMULATED_VULNERABILITY: frozenset({"service"}),
    RedActionType.OBTAIN_CREDENTIAL: _NONE,
    RedActionType.LATERAL_MOVE: frozenset({"credential_id"}),
    RedActionType.ACCESS_SENSITIVE_ASSET: frozenset({"asset_id"}),
    RedActionType.COLLECT_DATA: frozenset({"asset_id"}),
    RedActionType.EXFILTRATE_SIMULATED_DATA: frozenset({"asset_id"}),
}
BLUE_ALLOWED_PARAMETERS: dict[BlueActionType, frozenset[str]] = {
    BlueActionType.MONITOR: _NONE,
    BlueActionType.INVESTIGATE_ALERT: frozenset({"alert_id"}),
    BlueActionType.BLOCK_SOURCE: _NONE,
    BlueActionType.DISABLE_SERVICE: frozenset({"service"}),
    BlueActionType.ISOLATE_HOST: _NONE,
    BlueActionType.RESET_CREDENTIAL: frozenset({"credential_id"}),
    BlueActionType.PATCH_SIMULATED_VULNERABILITY: frozenset({"service"}),
    BlueActionType.INCREASE_LOGGING: _NONE,
    BlueActionType.RESTORE_SERVICE: frozenset({"service"}),  # omitted -> lift host isolation
    BlueActionType.MARK_INCIDENT: frozenset({"alert_id"}),
}


def unknown_parameters(action: "RedAction | BlueAction") -> list[str]:
    table = RED_ALLOWED_PARAMETERS if isinstance(action, RedAction) else BLUE_ALLOWED_PARAMETERS
    return sorted(set(action.parameters) - table[action.action_type])


class _ActionBase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    target: str
    parameters: dict[str, str] = Field(default_factory=dict)
    rationale: str = Field(default="", max_length=500)

    @field_validator("target")
    @classmethod
    def _check_target(cls, v: str) -> str:
        if not _ID.match(v):
            raise ValueError("target must match ^[a-z0-9_]{1,64}$")
        return v

    @field_validator("parameters")
    @classmethod
    def _check_params(cls, v: dict[str, str]) -> dict[str, str]:
        if len(v) > MAX_PARAMS:
            raise ValueError("too many parameters")
        for k, val in v.items():
            if not _PARAM_KEY.match(k) or not _PARAM_VAL.match(val):
                raise ValueError("parameter keys/values must be short identifiers")
        return v


class RedAction(_ActionBase):
    action_type: RedActionType

    @model_validator(mode="after")
    def _check_allowed_parameters(self) -> "RedAction":
        extra = set(self.parameters) - RED_ALLOWED_PARAMETERS[self.action_type]
        if extra:
            raise ValueError(f"unknown parameter(s) for {self.action_type.value}: {sorted(extra)}")
        return self


class BlueAction(_ActionBase):
    action_type: BlueActionType

    @model_validator(mode="after")
    def _check_allowed_parameters(self) -> "BlueAction":
        extra = set(self.parameters) - BLUE_ALLOWED_PARAMETERS[self.action_type]
        if extra:
            raise ValueError(f"unknown parameter(s) for {self.action_type.value}: {sorted(extra)}")
        return self


class Outcome(str, Enum):
    SUCCESS = "success"
    UNREACHABLE = "unreachable"
    PRECONDITION_FAILED = "precondition_failed"
    DENIED = "denied"
    INVALID_TARGET = "invalid_target"
    INVALID_PARAMETER = "invalid_parameter"
    NO_EFFECT = "no_effect"


class ActionResult(BaseModel):
    """Ground-truth record of one applied action. `state_changes` and `event_ids` are for the
    audit trail only and must never be shown to an agent (see observation_builder)."""

    model_config = ConfigDict(extra="forbid")

    role: Role
    action_type: str
    target: str
    success: bool
    outcome: Outcome
    message: str
    step: int
    state_changes: list[str] = Field(default_factory=list)
    event_ids: list[int] = Field(default_factory=list)
