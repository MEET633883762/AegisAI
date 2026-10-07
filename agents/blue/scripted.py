"""Deterministic, observation-driven Blue baseline for Phase 4.

The scripted defender receives only a BlueObservation and emits one typed BlueAction.
It has no simulator/scenario reference and never mutates environment state directly.
The policy is deliberately simple and auditable so it can serve as the baseline for
later LLM Blue experiments.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from environment.actions import BlueAction, BlueActionType
from telemetry.observation_builder import AlertView, BlueObservation


@dataclass
class ScriptedBlueAgent:
    """Deterministic Blue policy based only on defender-visible observations.

    Priority:
      1. Investigate new alerts to obtain evidence.
      2. Patch a known vulnerable service when evidence points to it.
      3. Isolate a host showing suspicious activity.
      4. Block a concrete suspicious source when one is visible.
      5. Mark an investigated alert as an incident.
      6. Increase logging on an affected host.
      7. Fall back to MONITOR.

    The policy never accesses simulator state and never executes an action itself.
    """

    _investigated_alerts: set[int] = field(default_factory=set, init=False, repr=False)
    _isolated_hosts: set[str] = field(default_factory=set, init=False, repr=False)
    _blocked_sources: set[str] = field(default_factory=set, init=False, repr=False)

    def decide(self, observation: BlueObservation) -> BlueAction:
        """Return exactly one deterministic defensive action."""
        alerts = sorted(observation.alerts, key=lambda a: (a.step, a.alert_id))

        # Evidence acquisition is always the first response to a new alert.
        for alert in alerts:
            if not alert.investigated and alert.alert_id not in self._investigated_alerts:
                self._investigated_alerts.add(alert.alert_id)
                return self._emit(
                    BlueActionType.INVESTIGATE_ALERT,
                    alert.host,
                    alert_id=str(alert.alert_id),
                )

        # Prefer patching a defender-known vulnerability once an alert has supplied
        # evidence on the affected host. The action is safe in the simulator and
        # becomes a useful baseline for the known-vulnerability scenario.
        for alert in alerts:
            if not alert.investigated:
                continue
            host = self._host(observation, alert.host)
            if host is None:
                continue
            if host.unpatched_known_vulns:
                for service in host.services:
                    if service.name == "web" and service.running:
                        return self._emit(
                            BlueActionType.PATCH_SIMULATED_VULNERABILITY,
                            host.id,
                            service=service.name,
                        )

        # Contain a host with investigated suspicious evidence. Do not repeatedly
        # isolate a host after the observation already reports it as isolated.
        for alert in alerts:
            if not alert.investigated:
                continue
            host = self._host(observation, alert.host)
            if host is None or host.status == "isolated" or host.id in self._isolated_hosts:
                continue
            if self._suspicious(alert):
                self._isolated_hosts.add(host.id)
                return self._emit(BlueActionType.ISOLATE_HOST, host.id)

        # If the telemetry exposes a concrete external/internal source, block it.
        for alert in alerts:
            if not alert.investigated:
                continue
            for event in alert.evidence:
                src = event.src
                if src and src not in observation.blocked_sources and src not in self._blocked_sources:
                    self._blocked_sources.add(src)
                    return self._emit(BlueActionType.BLOCK_SOURCE, src)

        # Record an investigated alert as an incident once containment is not required.
        for alert in alerts:
            if alert.investigated and not any(i.host == alert.host for i in observation.incidents):
                return self._emit(
                    BlueActionType.MARK_INCIDENT,
                    alert.host,
                    alert_id=str(alert.alert_id),
                )

        # Increase logging on online hosts with visible alerts to improve subsequent
        # telemetry. This is intentionally after immediate containment.
        for alert in alerts:
            host = self._host(observation, alert.host)
            if host is not None and host.status != "isolated" and host.logging_level < 2:
                return self._emit(BlueActionType.INCREASE_LOGGING, host.id)

        return self._emit(BlueActionType.MONITOR, "host_a")

    @property
    def investigated_alerts(self) -> frozenset[int]:
        return frozenset(self._investigated_alerts)

    def _emit(self, action_type: BlueActionType, target: str, **parameters: str) -> BlueAction:
        return BlueAction(
            action_type=action_type,
            target=target,
            parameters=parameters,
            rationale="deterministic scripted defender baseline policy",
        )

    @staticmethod
    def _host(observation: BlueObservation, host_id: str):
        return next((h for h in observation.hosts if h.id == host_id), None)

    @staticmethod
    def _suspicious(alert: AlertView) -> bool:
        if alert.severity.value in {"high", "critical"}:
            return True
        suspicious_types = {"NETWORK_PROBE", "SENSITIVE_DATA_ACCESS", "DATA_COLLECTION", "DATA_EXFILTRATION"}
        return any(event.type in suspicious_types for event in alert.evidence)
