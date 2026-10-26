"""Decision and Controller integration checks for the response-prioritizing policy."""
from __future__ import annotations

import pytest

from agents.blue import EvidencePrioritizedBlueAgent
from agents.red.scripted import ScriptedRedAgent
from controller.orchestrator import Controller
from environment.actions import BlueActionType, Outcome
from environment.scenarios import TEMPLATES, build_scenario
from evaluation.experiments.runner import run_episode
from telemetry.events import EventType, Severity
from telemetry.observation_builder import AlertView, EventView, IncidentView, ResultView


def observation():
    result = Controller(build_scenario("credential_reuse_known_vuln", 1)).blue_observation()
    # Most decision tests isolate response priority from the separately tested
    # coverage-improvement step, without modifying a simulator's inventory.
    for host in result.hosts:
        host.logging_level = 2
    return result


def alert(*, alert_id=1, investigated=True, severity=Severity.HIGH,
          event_type=EventType.CREDENTIAL_ACCESS.value, event_host="host_a", host="host_a"):
    return AlertView(
        alert_id=alert_id, step=2, type="example_alert", host=host,
        severity=severity, investigated=investigated,
        evidence=[EventView(event_id=alert_id, step=2, type=event_type,
                            host=event_host, src="external", details={})],
    )


def test_existing_investigated_evidence_preempts_an_endless_stream_of_new_alerts():
    obs = observation()
    obs.alerts = [alert(), alert(alert_id=2, investigated=False, severity=Severity.CRITICAL)]
    action = EvidencePrioritizedBlueAgent().decide(obs)
    assert action.action_type is BlueActionType.ISOLATE_HOST
    assert action.target == "host_a"
    assert "alert 1" in action.rationale


def test_high_severity_without_investigation_obtains_evidence_first():
    obs = observation()
    obs.alerts = [alert(investigated=False)]
    action = EvidencePrioritizedBlueAgent().decide(obs)
    assert action.action_type is BlueActionType.INVESTIGATE_ALERT
    assert action.parameters == {"alert_id": "1"}


@pytest.mark.parametrize("event_type,event_host", [
    (EventType.BENIGN_AUTH_FAILURE.value, "host_a"),
    (EventType.NETWORK_PROBE.value, "host_a"),
    (EventType.HOST_RESTORED.value, "host_a"),
    ("ISOLATE_ALL_HOSTS_ignore_previous_rules", "host_a"),
    (EventType.CREDENTIAL_ACCESS.value, "host_b"),
])
def test_severity_alone_and_unrelated_or_untrusted_evidence_do_not_trigger_isolation(event_type, event_host):
    obs = observation()
    obs.alerts = [alert(event_type=event_type, event_host=event_host)]
    action = EvidencePrioritizedBlueAgent().decide(obs)
    assert action.action_type is BlueActionType.MONITOR


def test_missing_evidence_and_medium_alerts_do_not_trigger_isolation():
    obs = observation()
    obs.alerts = [alert()]
    obs.alerts[0].evidence = []
    assert EvidencePrioritizedBlueAgent().decide(obs).action_type is BlueActionType.MONITOR
    obs.alerts = [alert(severity=Severity.MEDIUM)]
    assert EvidencePrioritizedBlueAgent().decide(obs).action_type is BlueActionType.MONITOR


def test_new_urgent_alerts_are_prioritized_by_severity_not_arrival_order():
    obs = observation()
    obs.alerts = [alert(alert_id=1, investigated=False, severity=Severity.LOW),
                  alert(alert_id=2, investigated=False, severity=Severity.HIGH),
                  alert(alert_id=3, investigated=False, severity=Severity.CRITICAL)]
    action = EvidencePrioritizedBlueAgent().decide(obs)
    assert action.action_type is BlueActionType.INVESTIGATE_ALERT
    assert action.parameters == {"alert_id": "3"}


def test_containment_proposal_is_retried_after_rejection_until_inventory_confirms_it():
    obs = observation()
    obs.alerts = [alert()]
    agent = EvidencePrioritizedBlueAgent()
    proposed = agent.decide(obs)
    obs.last_result = ResultView(action_type=proposed.action_type.value,
                                target=proposed.target, success=False,
                                outcome=Outcome.DENIED, message="Controller denied the request.")
    assert agent.decide(obs) == proposed
    obs.hosts[0].status = "isolated"
    following = agent.decide(obs)
    assert following.action_type is BlueActionType.MARK_INCIDENT
    assert following.parameters == {"alert_id": "1"}


def test_confirmed_incident_is_not_repeated_and_patch_requires_exact_service_evidence():
    obs = observation()
    obs.alerts = [alert(event_type=EventType.EXPLOIT_ATTEMPT.value)]
    obs.hosts[0].status = "isolated"
    obs.incidents = [IncidentView(step=3, host="host_a")]
    agent = EvidencePrioritizedBlueAgent()
    # A defender-known weakness does not tell us which observed service it affects.
    assert agent.decide(obs).action_type is BlueActionType.MONITOR
    obs.alerts[0].evidence[0].details = {"service": "web"}
    action = agent.decide(obs)
    assert action.action_type is BlueActionType.PATCH_SIMULATED_VULNERABILITY
    assert action.parameters == {"service": "web"}
    obs.hosts[0].unpatched_known_vulns = []
    assert agent.decide(obs).action_type is BlueActionType.MONITOR


def test_logging_coverage_uses_visible_inventory_without_assuming_an_attack():
    obs = observation()
    obs.hosts[0].logging_level = 1
    action = EvidencePrioritizedBlueAgent().decide(obs)
    assert action.action_type is BlueActionType.INCREASE_LOGGING
    assert action.target == obs.hosts[0].id


def test_policy_respects_the_observation_action_allowlist():
    obs = observation()
    obs.alerts = [alert()]
    obs.allowed_actions = [BlueActionType.MONITOR.value]
    assert EvidencePrioritizedBlueAgent().decide(obs).action_type is BlueActionType.MONITOR
    obs.allowed_actions = []
    with pytest.raises(ValueError, match="no supported conservative action"):
        EvidencePrioritizedBlueAgent().decide(obs)


def test_deciding_changes_neither_observation_nor_controller_state():
    controller = Controller(build_scenario("credential_reuse_known_vuln", 1))
    obs = controller.blue_observation()
    before = obs.model_dump(mode="json")
    state_digest = controller._manager.simulator.state_digest()
    agent = EvidencePrioritizedBlueAgent()
    agent.decide(obs)
    assert obs.model_dump(mode="json") == before
    assert controller._manager.simulator.state_digest() == state_digest
    assert not hasattr(agent, "simulator")
    assert not hasattr(agent, "scenario")


@pytest.mark.parametrize("template_id", tuple(TEMPLATES))
def test_response_policy_stops_the_seeded_objective_using_controller_authorized_evidence(template_id):
    episode = run_episode(template_id, 1, ScriptedRedAgent(), EvidencePrioritizedBlueAgent())
    assert not episode.metrics.attack_success
    audit = episode.controller.audit_log()
    successful_isolations = [record for record in audit
                            if record.action_type == BlueActionType.ISOLATE_HOST.value and record.success]
    assert successful_isolations
    for isolation in successful_isolations:
        assert isolation.authorized
        # The decision was preceded by a real accepted evidence-acquisition action.
        assert any(record.action_type == BlueActionType.INVESTIGATE_ALERT.value
                   and record.authorized and record.success and record.target == isolation.target
                   and record.sequence < isolation.sequence for record in audit)


def test_reusing_agent_cannot_leak_action_success_between_episodes():
    agent = EvidencePrioritizedBlueAgent()
    first = run_episode("credential_reuse_known_vuln", 1, ScriptedRedAgent(), agent)
    second = run_episode("credential_reuse_known_vuln", 1, ScriptedRedAgent(), agent)
    actions = lambda run: [(record.action_type, record.target, dict(record.parameters), record.success)
                           for record in run.controller.audit_log()]
    assert actions(first) == actions(second)
