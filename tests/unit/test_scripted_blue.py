from __future__ import annotations

from agents.blue.scripted import ScriptedBlueAgent
from controller.orchestrator import Controller
from environment.actions import BlueActionType
from environment.scenarios import build_scenario


def test_blue_agent_is_observation_only() -> None:
    agent = ScriptedBlueAgent()
    assert not hasattr(agent, "simulator")
    assert not hasattr(agent, "scenario")


def test_blue_agent_emits_typed_allowlisted_action() -> None:
    controller = Controller(build_scenario("credential_reuse_known_vuln", 1))
    action = ScriptedBlueAgent().decide(controller.blue_observation())
    assert action.action_type in BlueActionType


def test_blue_investigates_new_alert_after_red_action() -> None:
    controller = Controller(build_scenario("credential_reuse_known_vuln", 1))
    red = controller.red_observation()
    # Use the existing scripted Red baseline to generate an observable action.
    from agents.red.scripted import ScriptedRedAgent
    red_action = ScriptedRedAgent().decide(red)
    result = controller.submit_red(red_action)
    assert result.accepted
    blue = ScriptedBlueAgent()
    action = blue.decide(result.observation)
    if result.observation.alerts:
        assert action.action_type is BlueActionType.INVESTIGATE_ALERT


def test_blue_does_not_mutate_controller_state() -> None:
    controller = Controller(build_scenario("credential_reuse_known_vuln", 1))
    blue = ScriptedBlueAgent()
    observation = controller.blue_observation()
    digest_before = controller._manager.simulator.state_digest()
    blue.decide(observation)
    digest_after = controller._manager.simulator.state_digest()
    assert digest_before == digest_after


def test_blue_policy_can_complete_a_defensive_turn_without_direct_execution() -> None:
    from agents.red.scripted import ScriptedRedAgent
    controller = Controller(build_scenario("web_exploit_lateral_exfil", 1))
    red = ScriptedRedAgent()
    blue = ScriptedBlueAgent()
    action = red.decide(controller.red_observation())
    red_result = controller.submit_red(action)
    assert red_result.accepted
    if controller.done:
        return
    blue_action = blue.decide(red_result.observation)
    blue_result = controller.submit_blue(blue_action)
    assert blue_result.accepted
    assert blue_result.action_result.role.value == "blue"
