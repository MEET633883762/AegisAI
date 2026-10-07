"""Controller-side validation of already-typed agent actions.

This module deliberately does not execute actions. It answers one question only:
"Is this typed request structurally admissible for the current controller phase?"
Semantic preconditions remain simulator concerns so that Red does not receive an
existence oracle for hidden state.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from environment.actions import BlueAction, RedAction


class TurnPhase(str, Enum):
    RED = "red"
    BLUE = "blue"
    COMPLETE = "complete"


@dataclass(frozen=True)
class ValidationDecision:
    valid: bool
    reason: str


def validate_red_action(action: object) -> ValidationDecision:
    if not isinstance(action, RedAction):
        return ValidationDecision(False, "red action must be a RedAction")
    return ValidationDecision(True, "accepted")


def validate_blue_action(action: object) -> ValidationDecision:
    if not isinstance(action, BlueAction):
        return ValidationDecision(False, "blue action must be a BlueAction")
    return ValidationDecision(True, "accepted")
