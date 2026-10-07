import pytest
from pydantic import BaseModel, ConfigDict

from llm import FakeLLMProvider, LLMProvider, LLMRequest, StructuredOutputError


class Decision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: str
    target: str


def test_request_is_strict_and_bounded():
    req = LLMRequest(system_prompt="role", user_content="observation")
    assert req.temperature == 0.0
    with pytest.raises(Exception):
        LLMRequest(unknown="x")


def test_fake_provider_returns_validated_typed_output():
    provider = FakeLLMProvider({"action": "DISCOVER_HOST", "target": "host_a"})
    response = provider.generate_structured(
        LLMRequest(user_content="observation"), Decision
    )
    assert isinstance(response.output, Decision)
    assert response.output.action == "DISCOVER_HOST"
    assert response.provider == "fake"
    assert response.model == "fake-model"
    assert provider.calls == 1


def test_provider_rejects_invalid_structured_output():
    provider = FakeLLMProvider({"action": "DISCOVER_HOST", "unexpected": "x"})
    with pytest.raises(StructuredOutputError):
        provider.generate_structured(LLMRequest(), Decision)


def test_json_string_output_is_validated():
    provider = FakeLLMProvider('{"action":"MONITOR","target":"host_a"}')
    response = provider.generate_structured(LLMRequest(), Decision)
    assert response.output.target == "host_a"


def test_provider_has_no_controller_or_simulator_dependency():
    provider = FakeLLMProvider({"action": "MONITOR", "target": "host_a"})
    assert not hasattr(provider, "simulator")
    assert not hasattr(provider, "controller")


def test_base_validation_rejects_extra_fields():
    with pytest.raises(StructuredOutputError):
        LLMProvider.validate_output(
            {"action": "MONITOR", "target": "host_a", "extra": "bad"},
            Decision,
        )
