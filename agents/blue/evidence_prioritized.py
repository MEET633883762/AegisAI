"""An observation-only defender that prevents investigation from starving response.

This is a deterministic simulator policy, not an AI model or a production response
system. It preserves the original ScriptedBlueAgent as a comparison baseline.
Only the Controller can execute the typed requests returned here.
"""
from __future__ import annotations

from environment.actions import BlueAction, BlueActionType
from telemetry.events import EventType, Severity
from telemetry.observation_builder import AlertView, BlueHostView, BlueObservation


_SEVERITY_ORDER = {
    Severity.CRITICAL: 0,
    Severity.HIGH: 1,
    Severity.MEDIUM: 2,
    Severity.LOW: 3,
}
_URGENT_SEVERITIES = frozenset({Severity.HIGH, Severity.CRITICAL})
_THREAT_EVENTS = frozenset({
    EventType.EXPLOIT_ATTEMPT.value,
    EventType.CREDENTIAL_ACCESS.value,
    EventType.LATERAL_MOVEMENT.value,
    EventType.SENSITIVE_DATA_ACCESS.value,
    EventType.DATA_COLLECTION.value,
    EventType.DATA_EXFILTRATION.value,
})


class EvidencePrioritizedBlueAgent:
    """Contain investigated urgent evidence before accepting more investigation.

    Uninvestigated alerts are prioritized by severity, then oldest first. Neither
    an alert label nor a high severity alone authorizes this policy's isolation
    recommendation: an investigated alert must expose a recognized threat event
    on the same host. Benign authentication failures and probes do not qualify.

    The policy has no action-success cache. The next observation must actually
    report isolation before containment is considered complete. A rejected
    proposal therefore remains eligible; separate episodes cannot share state.
    Isolation is deliberately disruptive in this toy environment, so paired
    evaluation should report its availability cost as well as attack outcomes.
    """

    def decide(self, observation: BlueObservation) -> BlueAction:
        if not observation.hosts:
            raise ValueError("BlueObservation must contain at least one host")

        hosts = {host.id: host for host in observation.hosts}
        alerts = sorted(
            observation.alerts,
            key=lambda alert: (_SEVERITY_ORDER[alert.severity], alert.step, alert.alert_id),
        )
        urgent_evidence = [
            alert for alert in alerts
            if alert.investigated
            and alert.severity in _URGENT_SEVERITIES
            and alert.host in hosts
            and any(event.host == alert.host and event.type in _THREAT_EVENTS
                    for event in alert.evidence)
        ]

        # This order is the material change from the baseline: do not investigate
        # another new warning while already-investigated urgent evidence needs a
        # response. Inventory, rather than proposal issuance, confirms completion.
        if self._allowed(observation, BlueActionType.ISOLATE_HOST):
            for alert in urgent_evidence:
                if hosts[alert.host].status != "isolated":
                    return self._emit(
                        BlueActionType.ISOLATE_HOST, alert.host,
                        f"Contain investigated {alert.severity.value} alert {alert.alert_id}; "
                        "same-host threat evidence is visible and inventory is not isolated.",
                    )

        if self._allowed(observation, BlueActionType.INVESTIGATE_ALERT):
            for alert in alerts:
                if not alert.investigated and alert.severity in _URGENT_SEVERITIES and alert.host in hosts:
                    return self._investigate(alert)

        if self._allowed(observation, BlueActionType.MARK_INCIDENT):
            incident_hosts = {incident.host for incident in observation.incidents}
            for alert in urgent_evidence:
                if alert.host not in incident_hosts:
                    return self._emit(
                        BlueActionType.MARK_INCIDENT, alert.host,
                        f"Record the investigated threat evidence from alert {alert.alert_id}.",
                        alert_id=str(alert.alert_id),
                    )

        # Patch only a known, unpatched vulnerability on the exact running web
        # service named in investigated evidence. This is follow-up hardening,
        # not a claim that patching removes an existing foothold.
        if self._allowed(observation, BlueActionType.PATCH_SIMULATED_VULNERABILITY):
            for alert in urgent_evidence:
                host = hosts[alert.host]
                if self._known_web_exploit(host, alert):
                    return self._emit(
                        BlueActionType.PATCH_SIMULATED_VULNERABILITY, host.id,
                        f"Harden the defender-known web weakness evidenced by alert {alert.alert_id}.",
                        service="web",
                    )

        # Better logging changes only simulator observability and uses visible
        # inventory, not knowledge of which host the attacker will exploit.
        if self._allowed(observation, BlueActionType.INCREASE_LOGGING):
            for host in sorted(observation.hosts, key=lambda host: host.id):
                if host.status != "isolated" and host.logging_level < 2:
                    return self._emit(
                        BlueActionType.INCREASE_LOGGING, host.id,
                        "Visible inventory reports incomplete logging; improve observation coverage.",
                    )

        if self._allowed(observation, BlueActionType.INVESTIGATE_ALERT):
            for alert in alerts:
                if not alert.investigated and alert.host in hosts:
                    return self._investigate(alert)

        if self._allowed(observation, BlueActionType.MONITOR):
            return self._emit(
                BlueActionType.MONITOR, min(hosts),
                "No unresolved evidence-supported response is available in the current observation.",
            )
        raise ValueError("BlueObservation offers no supported conservative action")

    @staticmethod
    def _allowed(observation: BlueObservation, action: BlueActionType) -> bool:
        return action.value in observation.allowed_actions

    @staticmethod
    def _known_web_exploit(host: BlueHostView, alert: AlertView) -> bool:
        return bool(host.unpatched_known_vulns) and any(
            service.name == "web" and service.running for service in host.services
        ) and any(
            event.host == host.id
            and event.type == EventType.EXPLOIT_ATTEMPT.value
            and event.details.get("service") == "web"
            for event in alert.evidence
        )

    def _investigate(self, alert: AlertView) -> BlueAction:
        return self._emit(
            BlueActionType.INVESTIGATE_ALERT, alert.host,
            f"Inspect alert {alert.alert_id}, prioritized by observed severity then age.",
            alert_id=str(alert.alert_id),
        )

    @staticmethod
    def _emit(action: BlueActionType, target: str, rationale: str, **parameters: str) -> BlueAction:
        return BlueAction(action_type=action, target=target, parameters=parameters, rationale=rationale)
