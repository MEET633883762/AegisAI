import pytest
from pydantic import ValidationError

from controller import Controller, ControllerPolicy, TurnPhase
from environment.actions import BlueAction, RedAction
from environment.scenarios import build_scenario
from tests.unit.conftest import blue, chain, red


def test_controller_starts_in_red_phase_and_exposes_only_role_observations():
    c = Controller(build_scenario("web_exploit_lateral_exfil", 1))
    assert c.phase is TurnPhase.RED
    assert not c.done
    ro = c.red_observation()
    bo = c.blue_observation()
    assert ro.known_hosts and bo.hosts
    assert not hasattr(ro, "state") and not hasattr(bo, "state")


def test_red_then_blue_then_advance_is_the_only_normal_turn_order():
    c = Controller(build_scenario("web_exploit_lateral_exfil", 1))
    rr = c.submit_red(red("ENUMERATE_PORT", "host_a"))
    assert rr.accepted and c.phase is TurnPhase.BLUE
    br = c.submit_blue(blue("MONITOR", "host_a"))
    assert br.accepted and c.phase is TurnPhase.BLUE
    c.advance()
    assert c.phase is TurnPhase.RED and c.step == 1


def test_blue_cannot_act_before_red():
    c = Controller(build_scenario("web_exploit_lateral_exfil", 1))
    before = c.step
    result = c.submit_blue(blue("MONITOR", "host_a"))
    assert not result.accepted
    assert result.action_result.outcome.value == "denied"
    assert c.step == before
    assert c.audit_log()[-1].authorized is False


def test_red_cannot_submit_twice_in_one_turn():
    c = Controller(build_scenario("web_exploit_lateral_exfil", 1))
    assert c.submit_red(red("ENUMERATE_PORT", "host_a")).accepted
    rejected = c.submit_red(red("DISCOVER_SERVICE", "host_a"))
    assert not rejected.accepted
    assert "phase" in rejected.action_result.message.lower()
    assert len(c.audit_log()) == 2


def test_controller_rejects_wrong_runtime_types_without_mutation():
    c = Controller(build_scenario("web_exploit_lateral_exfil", 1))
    digest = c._manager.simulator.state_digest()
    result = c.submit_red(blue("MONITOR", "host_a"))  # type: ignore[arg-type]
    assert not result.accepted
    assert c._manager.simulator.state_digest() == digest


def test_controller_never_bypasses_pydantic_action_validation():
    with pytest.raises(ValidationError):
        RedAction(action_type="ENUMERATE_PORT", target="host_a", parameters={"bogus": "x"})
    with pytest.raises(ValidationError):
        BlueAction(action_type="MONITOR", target="host_a", parameters={"bogus": "x"})


def test_policy_rate_limit_is_enforced():
    c = Controller(build_scenario("web_exploit_lateral_exfil", 1), ControllerPolicy(max_red_actions_per_step=1))
    assert c.submit_red(red("ENUMERATE_PORT", "host_a")).accepted
    assert not c.submit_red(red("DISCOVER_SERVICE", "host_a")).accepted


def test_rejected_action_does_not_mutate_state_or_generate_events():
    c = Controller(build_scenario("web_exploit_lateral_exfil", 1))
    c.submit_blue(blue("MONITOR", "host_a"))
    digest = c._manager.simulator.state_digest()
    n_events = len(c._manager.simulator.state.events)
    c.submit_blue(blue("MONITOR", "host_a"))
    assert c._manager.simulator.state_digest() == digest
    assert len(c._manager.simulator.state.events) == n_events


def test_controller_is_only_normal_path_to_simulator_state_change():
    c = Controller(build_scenario("web_exploit_lateral_exfil", 1))
    # Controller owns the simulator; agents receive observations, not the simulator.
    assert "_manager" not in c.red_observation().__dict__
    assert "_manager" not in c.blue_observation().__dict__
    assert not hasattr(c.red_observation(), "state")
    assert not hasattr(c.blue_observation(), "state")


def test_run_turn_advances_exactly_one_step_when_live():
    c = Controller(build_scenario("web_exploit_lateral_exfil", 1))
    rr, br = c.run_turn(red("ENUMERATE_PORT", "host_a"), blue("MONITOR", "host_a"))
    assert rr.accepted and br.accepted
    assert c.step == 1 and c.phase is TurnPhase.RED


def test_controller_finishes_without_blue_turn_when_red_reaches_goal():
    c = Controller(build_scenario("credential_reuse_known_vuln", 1))
    for i, action in enumerate(chain("host_d")):
        rr = c.submit_red(action)
        assert rr.accepted
        if c.done:
            break
        # A minimal Blue action is required for normal turn progression.
        br = c.submit_blue(blue("MONITOR", "host_a"))
        assert br.accepted
        if not c.done:
            c.advance()
    assert c.done and c.phase is TurnPhase.COMPLETE


def test_actions_after_episode_completion_are_rejected_and_audited():
    c = Controller(build_scenario("credential_reuse_known_vuln", 1))
    for action in chain("host_d"):
        rr = c.submit_red(action)
        assert rr.accepted
        if c.done:
            break
        assert c.submit_blue(blue("MONITOR", "host_a")).accepted
        if not c.done:
            c.advance()
    assert c.done
    before = c._manager.simulator.state_digest()
    rejected = c.submit_red(red("DISCOVER_HOST", "host_a"))
    assert not rejected.accepted
    assert c._manager.simulator.state_digest() == before
    assert c.audit_log()[-1].authorized is False


def test_audit_contains_no_rationale_or_hidden_state():
    c = Controller(build_scenario("web_exploit_lateral_exfil", 1))
    c.submit_red(red("ENUMERATE_PORT", "host_a"))
    entry = c.audit_log()[0]
    data = entry.model_dump(mode="json")
    assert "rationale" not in data
    assert "hosts" not in data
    assert "credentials" not in data
    assert data["authorized"] is True
