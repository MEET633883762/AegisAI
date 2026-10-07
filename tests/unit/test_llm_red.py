import pytest
from pydantic import ValidationError

from agents.red import LLMRedAgent
from controller import Controller
from environment.actions import RedAction
from environment.scenarios import build_scenario
from llm.fake import FakeLLMProvider
from llm.provider import LLMProviderError, StructuredOutputError


def observation():
    return Controller(build_scenario("web_exploit_lateral_exfil", 1)).red_observation()


def valid_action():
    return RedAction(
        action_type="ENUMERATE_PORT",
        target="host_a",
        parameters={},
        rationale="enumerate the visible web host",
    )


def test_llm_red_returns_typed_action_from_provider():
    provider = FakeLLMProvider(valid_action())
    agent = LLMRedAgent(provider)
    action = agent.decide(observation())
    assert isinstance(action, RedAction)
    assert action.action_type.value == "ENUMERATE_PORT"
    assert provider.calls == 1


def test_llm_red_sends_only_role_specific_observation():
    provider = FakeLLMProvider(valid_action())
    agent = LLMRedAgent(provider)
    obs = observation()
    agent.decide(obs)
    request = provider.last_request
    assert request is not None
    assert "BEGIN RED OBSERVATION" in request.user_content
    assert "host_a" in request.user_content
    assert "initial_state" not in request.user_content
    assert "vulnerabilities" not in request.user_content
    assert "credentials" in request.user_content
    assert "system_prompt" not in request.user_content


def test_llm_red_uses_red_action_schema_validation():
    provider = FakeLLMProvider({
        "action_type": "ENUMERATE_PORT",
        "target": "host_a",
        "parameters": {"bogus": "value"},
        "rationale": "bad output",
    })
    agent = LLMRedAgent(provider, max_retries=0)
    with pytest.raises(StructuredOutputError):
        agent.decide(observation())
    assert provider.calls == 1


def test_llm_red_retries_provider_schema_failure_once():
    class SequenceProvider(FakeLLMProvider):
        def __init__(self):
            super().__init__({"bad": "output"})
            self.responses = [
                {"bad": "output"},
                valid_action().model_dump(mode="json"),
            ]

        def generate_structured(self, request, response_model):
            self.response = self.responses.pop(0)
            return super().generate_structured(request, response_model)

    provider = SequenceProvider()
    agent = LLMRedAgent(provider, max_retries=1)
    action = agent.decide(observation())
    assert action == valid_action()
    assert provider.calls == 2
    assert provider.last_request is not None
    assert "Previous response was rejected" in provider.last_request.user_content


def test_llm_red_does_not_fabricate_fallback_on_provider_failure():
    class FailingProvider(FakeLLMProvider):
        def generate_structured(self, request, response_model):
            self.calls += 1
            raise LLMProviderError("provider unavailable")

    provider = FailingProvider(valid_action())
    agent = LLMRedAgent(provider, max_retries=1)
    with pytest.raises(LLMProviderError):
        agent.decide(observation())
    assert provider.calls == 2


def test_llm_red_has_no_controller_or_simulator_reference():
    agent = LLMRedAgent(FakeLLMProvider(valid_action()))
    assert not hasattr(agent, "controller")
    assert not hasattr(agent, "simulator")


def test_llm_red_action_is_not_executed_by_agent():
    controller = Controller(build_scenario("web_exploit_lateral_exfil", 1))
    provider = FakeLLMProvider(valid_action())
    agent = LLMRedAgent(provider)
    before = controller.step
    action = agent.decide(controller.red_observation())
    assert controller.step == before
    assert controller.phase.value == "red"
    assert action.target == "host_a"
    assert len(controller.audit_log()) == 0


def test_llm_red_can_feed_typed_action_to_controller():
    controller = Controller(build_scenario("web_exploit_lateral_exfil", 1))
    provider = FakeLLMProvider(valid_action())
    agent = LLMRedAgent(provider)
    action = agent.decide(controller.red_observation())
    result = controller.submit_red(action)
    assert result.accepted
    assert controller.phase.value == "blue"
    assert controller.audit_log()[-1].authorized is True


def test_llm_red_rejects_invalid_configuration():
    with pytest.raises(ValueError):
        LLMRedAgent(FakeLLMProvider(valid_action()), temperature=2.1)
    with pytest.raises(ValueError):
        LLMRedAgent(FakeLLMProvider(valid_action()), max_output_tokens=0)
    with pytest.raises(ValueError):
        LLMRedAgent(FakeLLMProvider(valid_action()), max_retries=3)
