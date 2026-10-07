import pytest

from controller import Controller
from environment.scenarios import build_scenario
from xai import XAILogger, ReasonCategory
from tests.unit.conftest import blue, red


def test_controller_creates_structured_xai_trace_for_authorized_red_and_blue_actions():
    c = Controller(build_scenario("web_exploit_lateral_exfil", 1), episode_id="ep-test")
    rr = c.submit_red(red("ENUMERATE_PORT", "host_a"))
    assert rr.accepted
    br = c.submit_blue(blue("MONITOR", "host_a"))
    assert br.accepted

    traces = c.xai_log().traces()
    assert len(traces) == 2
    assert [t.role.value for t in traces] == ["red", "blue"]
    assert all(t.episode_id == "ep-test" for t in traces)
    assert all(t.scenario_id == "web_exploit_lateral_exfil:1" for t in traces)
    assert traces[0].action["action_type"] == "ENUMERATE_PORT"
    assert traces[0].reason_category is ReasonCategory.RECONNAISSANCE
    assert traces[0].rationale == ""
    assert traces[0].actual_outcome == "success"
    assert traces[0].success is True
    assert traces[0].observation["known_hosts"]
    assert traces[1].reason_category is ReasonCategory.MONITORING


def test_xai_trace_captures_rejected_action_without_hidden_state():
    c = Controller(build_scenario("web_exploit_lateral_exfil", 1), episode_id="ep-reject")
    result = c.submit_blue(blue("MONITOR", "host_a"))
    assert not result.accepted
    trace = c.xai_log().traces()[0]
    assert trace.action["authorized"] is False
    assert trace.actual_outcome == "denied"
    dumped = trace.model_dump(mode="json")
    assert "hosts" not in dumped.get("action", {})
    assert "state" not in dumped["observation"]


def test_xai_evidence_is_limited_to_role_visible_observation():
    c = Controller(build_scenario("credential_reuse_known_vuln", 2), episode_id="ep-evidence")
    c.submit_red(red("ENUMERATE_PORT", "host_a"))
    c.submit_blue(blue("MONITOR", "host_a"))
    red_trace = c.xai_log().traces_for_role("red")[0]
    assert all(e.source == "red_observation" for e in red_trace.evidence)
    assert all("vulnerability" not in e.reference.lower() for e in red_trace.evidence)


def test_xai_logger_is_append_only_and_returns_deep_copies():
    logger = XAILogger()
    c = Controller(build_scenario("web_exploit_lateral_exfil", 3), xai=logger)
    c.submit_red(red("ENUMERATE_PORT", "host_a"))
    original = logger.trace(1)
    assert original is not None
    modified = original.model_copy(deep=True)
    modified.observation["tampered"] = True
    assert "tampered" not in logger.trace(1).observation
    with pytest.raises(ValueError):
        logger.append(original)


def test_xai_trace_links_controller_outcome_events_and_excludes_hidden_state():
    c = Controller(build_scenario("web_exploit_lateral_exfil", 7), episode_id="ep-events")
    rr = c.submit_red(red("ENUMERATE_PORT", "host_a"))
    assert rr.accepted
    trace = c.xai_log().traces()[0]
    assert trace.event_ids == rr.action_result.event_ids
    assert trace.state_change_count == len(rr.action_result.state_changes)
    text = str(trace.model_dump(mode="json"))
    assert "initial_state" not in text
    assert "_manager" not in text


def test_llm_red_rationale_is_preserved_as_agent_generated_text():
    from agents.red.llm import LLMRedAgent
    from llm.fake import FakeLLMProvider

    c = Controller(build_scenario("web_exploit_lateral_exfil", 9), episode_id="ep-llm")
    obs = c.red_observation()
    provider = FakeLLMProvider({"action_type": "ENUMERATE_PORT", "target": "host_a",
                                "parameters": {}, "rationale": "The visible host has not been enumerated."})
    action = LLMRedAgent(provider=provider, max_retries=0).decide(obs)
    result = c.submit_red(action)
    trace = c.xai_log().traces()[0]
    assert result.accepted
    assert trace.rationale == "The visible host has not been enumerated."
    assert trace.provider is None  # provider metadata is intentionally not fabricated by Controller
