import pytest
from pydantic import ValidationError

from environment.actions import BlueAction, BlueActionType, RedAction, RedActionType


def test_allowlists_match_spec():
    assert len(RedActionType) == 10 and len(BlueActionType) == 10


@pytest.mark.parametrize("bad", [
    {"action_type": "RUN_SHELL", "target": "host_a"},               # not allowlisted
    {"action_type": "DISCOVER_HOST", "target": "host_a; rm -rf /"},  # injection-shaped target
    {"action_type": "DISCOVER_HOST", "target": "Host A"},
    {"action_type": "DISCOVER_HOST", "target": "host_a", "extra": 1},  # unknown field
    {"action_type": "DISCOVER_HOST", "target": "host_a", "parameters": {"k": "a b c"}},
    {"action_type": "DISCOVER_HOST", "target": "host_a", "parameters": {"k": "$(id)"}},
    {"action_type": "DISCOVER_HOST", "target": "host_a", "rationale": "x" * 501},
    {"action_type": "DISCOVER_HOST", "target": "host_a",
     "parameters": {f"k{i}": "v" for i in range(9)}},
])
def test_red_rejects_bad_input(bad):
    with pytest.raises(ValidationError):
        RedAction(**bad)


def test_blue_cannot_use_red_action_and_vice_versa():
    with pytest.raises(ValidationError):
        BlueAction(action_type="EXFILTRATE_SIMULATED_DATA", target="host_a")
    with pytest.raises(ValidationError):
        RedAction(action_type="ISOLATE_HOST", target="host_a")


def test_valid_action_roundtrips():
    a = RedAction(action_type="LATERAL_MOVE", target="host_c", parameters={"credential_id": "cred_x"})
    assert RedAction.model_validate_json(a.model_dump_json()) == a


# ---- strict per-action parameter validation ---------------------------------------------------
from environment.actions import (BLUE_ALLOWED_PARAMETERS, RED_ALLOWED_PARAMETERS,  # noqa: E402
                                 Outcome, unknown_parameters)

ALL_RED = list(RedActionType)
ALL_BLUE = list(BlueActionType)


def test_every_action_has_a_declared_parameter_set():
    assert set(RED_ALLOWED_PARAMETERS) == set(RedActionType)
    assert set(BLUE_ALLOWED_PARAMETERS) == set(BlueActionType)


@pytest.mark.parametrize("t", ALL_RED)
def test_red_rejects_unknown_parameter(t):
    with pytest.raises(ValidationError, match="unknown parameter"):
        RedAction(action_type=t, target="host_a", parameters={"bogus_key": "x"})


@pytest.mark.parametrize("t", ALL_BLUE)
def test_blue_rejects_unknown_parameter(t):
    with pytest.raises(ValidationError, match="unknown parameter"):
        BlueAction(action_type=t, target="host_a", parameters={"bogus_key": "x"})


@pytest.mark.parametrize("t", ALL_RED)
def test_red_accepts_exactly_its_declared_keys(t):
    allowed = RED_ALLOWED_PARAMETERS[t]
    RedAction(action_type=t, target="host_a", parameters={k: "v1" for k in allowed})
    for other in set().union(*RED_ALLOWED_PARAMETERS.values()) - allowed:  # keys of other actions
        with pytest.raises(ValidationError):
            RedAction(action_type=t, target="host_a", parameters={other: "v1"})


@pytest.mark.parametrize("t", ALL_BLUE)
def test_blue_accepts_exactly_its_declared_keys(t):
    allowed = BLUE_ALLOWED_PARAMETERS[t]
    BlueAction(action_type=t, target="host_a", parameters={k: "v1" for k in allowed})
    for other in set().union(*BLUE_ALLOWED_PARAMETERS.values()) - allowed:
        with pytest.raises(ValidationError):
            BlueAction(action_type=t, target="host_a", parameters={other: "v1"})


def test_extra_key_alongside_valid_key_is_rejected():
    with pytest.raises(ValidationError):
        RedAction(action_type="LATERAL_MOVE", target="host_c",
                  parameters={"credential_id": "cred_x", "asset_id": "a"})


def test_pydantic_safety_constraints_preserved():
    with pytest.raises(ValidationError):  # allowed key, unsafe value
        RedAction(action_type="LATERAL_MOVE", target="host_c", parameters={"credential_id": "$(id)"})
    with pytest.raises(ValidationError):  # allowed key, oversized value
        RedAction(action_type="LATERAL_MOVE", target="host_c", parameters={"credential_id": "a" * 65})
    with pytest.raises(ValidationError):  # extra top-level field
        RedAction(action_type="LATERAL_MOVE", target="host_c", cmd="id")


def test_simulator_rejects_unvalidated_action_with_unknown_parameter():
    """Defense in depth: an action built with model_construct (bypassing validation) is refused."""
    from environment.scenarios import build_scenario
    from environment.simulator import Simulator
    sim = Simulator(build_scenario("web_exploit_lateral_exfil", 1))
    digest = sim.state_digest()
    bad_red = RedAction.model_construct(action_type=RedActionType.ENUMERATE_PORT, target="host_a",
                                        parameters={"bogus_key": "x"}, rationale="")
    bad_blue = BlueAction.model_construct(action_type=BlueActionType.ISOLATE_HOST, target="host_a",
                                          parameters={"bogus_key": "x"}, rationale="")
    assert unknown_parameters(bad_red) == ["bogus_key"]
    assert sim.apply_red(bad_red).outcome is Outcome.INVALID_PARAMETER
    assert sim.apply_blue(bad_blue).outcome is Outcome.INVALID_PARAMETER
    assert sim.state_digest() == digest  # no state change, no telemetry
    assert not sim.state.hosts["host_a"].isolated
