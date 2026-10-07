"""Controller-owned append-only XAI trace sink."""
from __future__ import annotations

from dataclasses import dataclass, field

from xai.trace import DecisionTrace


@dataclass
class XAILogger:
    """Append-only, deep-copying trace store with deterministic query helpers."""

    _traces: dict[int, DecisionTrace] = field(default_factory=dict)

    def append(self, trace: DecisionTrace) -> None:
        if trace.trace_id in self._traces:
            raise ValueError(f"duplicate XAI trace id: {trace.trace_id}")
        self._traces[trace.trace_id] = trace.model_copy(deep=True)

    def traces(self) -> tuple[DecisionTrace, ...]:
        return tuple(self._traces[k] for k in sorted(self._traces))

    def trace(self, trace_id: int) -> DecisionTrace | None:
        item = self._traces.get(trace_id)
        return None if item is None else item.model_copy(deep=True)

    def traces_for_episode(self, episode_id: str) -> tuple[DecisionTrace, ...]:
        return tuple(t for t in self.traces() if t.episode_id == episode_id)

    def traces_for_step(self, step: int) -> tuple[DecisionTrace, ...]:
        return tuple(t for t in self.traces() if t.step == step)

    def traces_for_role(self, role: str) -> tuple[DecisionTrace, ...]:
        return tuple(t for t in self.traces() if t.role.value == role)

    def clear(self) -> None:
        self._traces.clear()
