"""In-memory telemetry sink for reproducible episodes.

Telemetry is evidence/data, never executable instructions.  The logger keeps a
controller-facing copy of simulator events and alerts without exposing hidden
fields to agents.  It is intentionally persistence-free in Phase 5; database
storage belongs to a later phase.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from telemetry.events import Alert, TelemetryEvent


@dataclass
class TelemetryLogger:
    """Append-only telemetry sink with deterministic query helpers."""

    _events: dict[int, TelemetryEvent] = field(default_factory=dict)
    _alerts: dict[int, Alert] = field(default_factory=dict)

    def ingest(self, events: list[TelemetryEvent], alerts: list[Alert]) -> None:
        """Ingest new simulator records. Duplicate IDs are rejected."""
        for event in events:
            if event.event_id in self._events:
                raise ValueError(f"duplicate telemetry event id: {event.event_id}")
        for alert in alerts:
            if alert.alert_id in self._alerts:
                raise ValueError(f"duplicate alert id: {alert.alert_id}")
        self._events.update({e.event_id: e.model_copy(deep=True) for e in events})
        self._alerts.update({a.alert_id: a.model_copy(deep=True) for a in alerts})

    def events(self) -> tuple[TelemetryEvent, ...]:
        return tuple(self._events[k] for k in sorted(self._events))

    def alerts(self) -> tuple[Alert, ...]:
        return tuple(self._alerts[k] for k in sorted(self._alerts))

    def events_for_step(self, step: int) -> tuple[TelemetryEvent, ...]:
        return tuple(e for e in self.events() if e.step == step)

    def alerts_for_step(self, step: int) -> tuple[Alert, ...]:
        return tuple(a for a in self.alerts() if a.step == step)

    def event(self, event_id: int) -> TelemetryEvent | None:
        return self._events.get(event_id)

    def alert(self, alert_id: int) -> Alert | None:
        return self._alerts.get(alert_id)

    def clear(self) -> None:
        self._events.clear()
        self._alerts.clear()
