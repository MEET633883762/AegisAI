import json

import pytest

from controller.orchestrator import Controller
from environment.scenarios import TEMPLATES, build_scenario


def test_phase15_expands_scenario_library():
    assert len(TEMPLATES) >= 6
    assert {"web_exploit_lateral_exfil", "credential_reuse_known_vuln"} <= set(TEMPLATES)
    assert {"web_exploit_high_noise", "web_exploit_restricted_lateral", "credential_reuse_workstation", "credential_reuse_service"} <= set(TEMPLATES)


def test_phase15_scenario_metadata_is_deterministic_and_serializable():
    a = build_scenario("web_exploit_high_noise", 7)
    b = build_scenario("web_exploit_high_noise", 7)
    assert a.metadata == b.metadata
    assert json.dumps(a.model_dump(mode="json"), sort_keys=True) == json.dumps(b.model_dump(mode="json"), sort_keys=True)


def test_phase15_templates_are_not_duplicate_worlds():
    worlds = []
    for template_id in TEMPLATES:
        scenario = build_scenario(template_id, 7)
        worlds.append(json.dumps(scenario.initial_state.model_dump(mode="json"), sort_keys=True))
    assert len(set(worlds)) >= 4


def test_phase15_metadata_does_not_leak_into_agent_observations():
    controller = Controller(build_scenario("web_exploit_high_noise", 7))
    red = controller.red_observation().model_dump(mode="json")
    blue = controller.blue_observation().model_dump(mode="json")
    assert "metadata" not in red
    assert "metadata" not in blue
    assert "attack_pattern" not in json.dumps(red)
    assert "attack_pattern" not in json.dumps(blue)


def test_phase15_unknown_template_still_fails_closed():
    with pytest.raises(KeyError):
        build_scenario("does_not_exist", 1)
