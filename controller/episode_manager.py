"""Episode lifecycle and deterministic turn bookkeeping."""
from __future__ import annotations

from dataclasses import dataclass

from controller.validator import TurnPhase
from environment.simulator import EpisodeCompleteError, Simulator


@dataclass
class EpisodeManager:
    simulator: Simulator
    phase: TurnPhase = TurnPhase.RED
    red_actions_this_step: int = 0
    blue_actions_this_step: int = 0

    @property
    def step(self) -> int:
        return self.simulator.state.step

    @property
    def done(self) -> bool:
        return self.simulator.is_done()

    def sync_terminal_state(self) -> None:
        if self.simulator.is_done():
            self.phase = TurnPhase.COMPLETE

    def begin_blue(self) -> None:
        self.phase = TurnPhase.BLUE

    def begin_next_step(self) -> None:
        if self.simulator.is_done():
            self.phase = TurnPhase.COMPLETE
            return
        self.simulator.advance_time()
        self.red_actions_this_step = 0
        self.blue_actions_this_step = 0
        self.phase = TurnPhase.RED

    def finish_if_terminal(self) -> None:
        if self.simulator.is_done():
            self.phase = TurnPhase.COMPLETE
