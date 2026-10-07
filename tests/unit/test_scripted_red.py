from agents.red import ScriptedRedAgent
from controller import Controller
from environment.actions import RedActionType
from environment.scenarios import build_scenario
from tests.unit.conftest import blue


def test_scripted_red_emits_only_typed_allowlisted_actions():
    controller = Controller(build_scenario("web_exploit_lateral_exfil", 1))
    agent = ScriptedRedAgent()
    action = agent.decide(controller.red_observation())
    assert action.action_type in RedActionType
    assert action.rationale


def test_scripted_red_never_receives_or_mutates_simulator():
    controller = Controller(build_scenario("web_exploit_lateral_exfil", 1))
    agent = ScriptedRedAgent()
    before = controller._manager.simulator.state_digest()
    action = agent.decide(controller.red_observation())
    after = controller._manager.simulator.state_digest()
    assert before == after
    assert not hasattr(agent, "simulator")
    assert not hasattr(agent, "scenario")
    assert action.action_type is RedActionType.ENUMERATE_PORT


def test_scripted_red_can_complete_standard_scenario_through_controller():
    controller = Controller(build_scenario("web_exploit_lateral_exfil", 1))
    agent = ScriptedRedAgent()
    blue_action = blue("MONITOR", "host_a")

    for _ in range(30):
        if controller.done:
            break
        red_action = agent.decide(controller.red_observation())
        red_result = controller.submit_red(red_action)
        assert red_result.accepted, red_result.action_result.message
        if controller.done:
            break
        blue_result = controller.submit_blue(blue_action)
        assert blue_result.accepted, blue_result.action_result.message
        if not controller.done:
            controller.advance()

    assert controller.done
    assert controller._manager.simulator.red_goal_achieved()


def test_scripted_red_is_deterministic_for_same_observation():
    controller = Controller(build_scenario("web_exploit_lateral_exfil", 1))
    observation = controller.red_observation()
    a = ScriptedRedAgent().decide(observation)
    b = ScriptedRedAgent().decide(observation)
    assert a == b
