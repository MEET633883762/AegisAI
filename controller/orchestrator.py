"""Central controller: the sole action authorization boundary for Phase 2.

Agents receive role-specific observations and submit typed action requests here.
The controller validates and authorizes requests before invoking the simulator.
No agent receives a simulator reference.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from controller.episode_manager import EpisodeManager
from controller.permissions import role_can_submit
from controller.policy import ControllerPolicy
from controller.validator import TurnPhase, validate_blue_action, validate_red_action
from environment.actions import ActionResult, BlueAction, RedAction, Role
from environment.scenarios import Scenario
from environment.simulator import Simulator
from telemetry.logger import TelemetryLogger
from telemetry.observation_builder import BlueObservation, RedObservation, build_blue_observation, build_red_observation
from xai.logger import XAILogger
from xai.trace import build_trace


class AuditRecord(BaseModel):
    """Structured audit entry; never stores hidden chain-of-thought."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    sequence: int
    timestamp: datetime
    step: int
    phase: TurnPhase
    role: Role
    action_type: str
    target: str
    parameters: dict[str, str] = Field(default_factory=dict)
    authorized: bool
    policy_reason: str
    outcome: str | None = None
    success: bool | None = None
    state_changes: list[str] = Field(default_factory=list)
    event_ids: list[int] = Field(default_factory=list)


@dataclass(frozen=True)
class ControllerResult:
    accepted: bool
    action_result: ActionResult
    observation: RedObservation | BlueObservation | None


class Controller:
    """Owns the simulator and mediates every agent action.

    Public methods expose observations/results, not the simulator. The private
    simulator reference is intentionally not part of the agent contract.
    """

    def __init__(self, scenario: Scenario, policy: ControllerPolicy | None = None,
                 telemetry: TelemetryLogger | None = None, xai: XAILogger | None = None,
                 episode_id: str | None = None) -> None:
        self._manager = EpisodeManager(Simulator(scenario))
        self._policy = policy or ControllerPolicy()
        self._telemetry = telemetry or TelemetryLogger()
        self._xai = xai or XAILogger()
        self._episode_id = episode_id or str(uuid4())
        self._telemetry_cursor = 0
        self._alert_cursor = 0
        self._audit: list[AuditRecord] = []
        self._sequence = 0
        self._xai_sequence = 0
        self._last_red_result: ActionResult | None = None
        self._last_blue_result: ActionResult | None = None

    @property
    def scenario(self) -> Scenario:
        return self._manager.simulator.scenario

    @property
    def step(self) -> int:
        return self._manager.step

    @property
    def done(self) -> bool:
        return self._manager.done

    @property
    def phase(self) -> TurnPhase:
        return self._manager.phase

    def audit_log(self) -> tuple[AuditRecord, ...]:
        return tuple(self._audit)

    @property
    def episode_id(self) -> str:
        return self._episode_id

    def xai_log(self) -> XAILogger:
        """Return the controller-owned structured XAI trace sink."""
        return self._xai

    def telemetry_log(self) -> TelemetryLogger:
        """Return the controller-owned telemetry sink; agents never receive it."""
        return self._telemetry

    def _sync_telemetry(self) -> None:
        events = self._manager.simulator.state.events[self._telemetry_cursor:]
        alerts = self._manager.simulator.state.alerts[self._alert_cursor:]
        if events or alerts:
            self._telemetry.ingest(events, alerts)
            self._telemetry_cursor += len(events)
            self._alert_cursor += len(alerts)

    def red_observation(self) -> RedObservation:
        return build_red_observation(
            self._manager.simulator.state,
            self.scenario,
            self._last_red_result,
        )

    def blue_observation(self) -> BlueObservation:
        return build_blue_observation(
            self._manager.simulator.state,
            self.scenario,
            self._last_blue_result,
        )

    def submit_red(self, action: RedAction) -> ControllerResult:
        phase_before = self.phase
        observation_before = self.red_observation()
        validation = validate_red_action(action)
        if not validation.valid:
            return self._reject(Role.RED, action, phase_before, validation.reason, observation_before)
        if not role_can_submit(Role.RED, Role.RED):
            return self._reject(Role.RED, action, phase_before, "role permission denied", observation_before)
        allowed, reason = self._policy.authorize_red(
            action, self.phase, self._manager.red_actions_this_step
        )
        if not allowed:
            return self._reject(Role.RED, action, phase_before, reason, observation_before)
        result = self._manager.simulator.apply_red(action)
        self._sync_telemetry()
        self._manager.red_actions_this_step += 1
        self._last_red_result = result
        self._record(Role.RED, action, phase_before, True, "authorized", result, observation_before)
        if self.done:
            self._manager.sync_terminal_state()
            return ControllerResult(True, result, self.red_observation())
        self._manager.begin_blue()
        return ControllerResult(True, result, self.blue_observation())

    def submit_blue(self, action: BlueAction) -> ControllerResult:
        phase_before = self.phase
        observation_before = self.blue_observation()
        validation = validate_blue_action(action)
        if not validation.valid:
            return self._reject(Role.BLUE, action, phase_before, validation.reason, observation_before)
        if not role_can_submit(Role.BLUE, Role.BLUE):
            return self._reject(Role.BLUE, action, phase_before, "role permission denied", observation_before)
        allowed, reason = self._policy.authorize_blue(
            action, self.phase, self._manager.blue_actions_this_step
        )
        if not allowed:
            return self._reject(Role.BLUE, action, phase_before, reason, observation_before)
        result = self._manager.simulator.apply_blue(action)
        self._sync_telemetry()
        self._manager.blue_actions_this_step += 1
        self._last_blue_result = result
        self._record(Role.BLUE, action, phase_before, True, "authorized", result, observation_before)
        self._manager.finish_if_terminal()
        return ControllerResult(True, result, self.blue_observation())

    def advance(self) -> None:
        """Complete the current Red->Blue turn and move to the next step."""
        if self.done:
            self._manager.sync_terminal_state()
            return
        if self.phase is not TurnPhase.BLUE:
            raise RuntimeError("cannot advance before the Red action has been submitted")
        self._manager.begin_next_step()
        self._sync_telemetry()
        self._last_red_result = None
        self._last_blue_result = None

    def run_turn(self, red_action: RedAction, blue_action: BlueAction) -> tuple[ControllerResult, ControllerResult]:
        """Run exactly one bounded Red->Blue turn, then advance if still live."""
        red_result = self.submit_red(red_action)
        if not red_result.accepted:
            return red_result, red_result
        if self.done:
            return red_result, red_result
        blue_result = self.submit_blue(blue_action)
        if blue_result.accepted and not self.done:
            self.advance()
        return red_result, blue_result

    def _reject(self, role: Role, action: Any, phase: TurnPhase, reason: str,
                observation_before: RedObservation | BlueObservation) -> ControllerResult:
        result = ActionResult(
            role=role,
            action_type=getattr(getattr(action, "action_type", None), "value", "INVALID"),
            target=getattr(action, "target", "invalid"),
            success=False,
            outcome="denied",
            message="Controller rejected action: " + reason,
            step=self.step,
        )
        self._record(role, action, phase, False, reason, result, observation_before)
        return ControllerResult(False, result, self.red_observation() if role is Role.RED else self.blue_observation())

    def _record(self, role: Role, action: Any, phase: TurnPhase, authorized: bool,
                reason: str, result: ActionResult,
                observation_before: RedObservation | BlueObservation) -> None:
        self._sequence += 1
        self._audit.append(AuditRecord(
            sequence=self._sequence,
            timestamp=datetime.now(timezone.utc),
            step=self.step,
            phase=phase,
            role=role,
            action_type=getattr(getattr(action, "action_type", None), "value", "INVALID"),
            target=getattr(action, "target", "invalid"),
            parameters=dict(getattr(action, "parameters", {})),
            authorized=authorized,
            policy_reason=reason,
            outcome=result.outcome.value,
            success=result.success,
            state_changes=list(result.state_changes),
            event_ids=list(result.event_ids),
        ))
        self._xai_sequence += 1
        self._xai.append(build_trace(
            trace_id=self._xai_sequence,
            episode_id=self._episode_id,
            scenario_id=self.scenario.scenario_id,
            observation=observation_before,
            action=action,
            result=result,
            timestamp=datetime.now(timezone.utc).isoformat(),
            authorized=authorized,
        ))
