"""Deterministic controller policy.

The policy is intentionally small in Phase 2. It enforces role/action separation,
turn ordering, and bounded action submission. It never bypasses the simulator and
never grants an action because an agent rationale says it is necessary.
"""
from __future__ import annotations

from dataclasses import dataclass

from controller.validator import TurnPhase
from environment.actions import BlueAction, BlueActionType, RedAction, RedActionType


@dataclass(frozen=True)
class ControllerPolicy:
    max_red_actions_per_step: int = 1
    max_blue_actions_per_step: int = 1

    def authorize_red(self, action: RedAction, phase: TurnPhase, red_count: int) -> tuple[bool, str]:
        if phase is not TurnPhase.RED:
            return False, "red action is not permitted in the current turn phase"
        if red_count >= self.max_red_actions_per_step:
            return False, "red action rate limit exceeded for this step"
        if action.action_type not in RedActionType:
            return False, "red action type is not allowlisted"
        return True, "authorized"

    def authorize_blue(self, action: BlueAction, phase: TurnPhase, blue_count: int) -> tuple[bool, str]:
        if phase is not TurnPhase.BLUE:
            return False, "blue action is not permitted in the current turn phase"
        if blue_count >= self.max_blue_actions_per_step:
            return False, "blue action rate limit exceeded for this step"
        if action.action_type not in BlueActionType:
            return False, "blue action type is not allowlisted"
        return True, "authorized"
