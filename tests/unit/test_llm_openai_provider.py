from types import ModuleType, SimpleNamespace
import sys

import pytest
from pydantic import BaseModel, ConfigDict

from llm.openai_provider import OpenAIResponsesProvider
from llm.provider import LLMProviderError, LLMRequest, StructuredOutputError


class Decision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: str
    target: str


class FakeResponses:
    def __init__(self, parsed=None, error=None):
        self.parsed = parsed
        self.error = error
        self.calls = []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return SimpleNamespace(
            output_parsed=self.parsed,
            usage=SimpleNamespace(input_tokens=11, output_tokens=7, total_tokens=18),
        )


class FakeClient:
    def __init__(self, responses):
        self.responses = responses


def test_openai_provider_uses_responses_structured_parse_without_network():
    responses = FakeResponses(SimpleNamespace(action="DISCOVER_HOST", target="host_a"))
    # Use a real Pydantic instance so application-level validation is explicit.
    responses.parsed = Decision(action="DISCOVER_HOST", target="host_a")
    provider = OpenAIResponsesProvider(
        model="test-model",
        client=FakeClient(responses),
        timeout_seconds=12,
    )

    result = provider.generate_structured(
        LLMRequest(system_prompt="role", user_content="observation"), Decision
    )

    assert result.output.action == "DISCOVER_HOST"
    assert result.provider == "openai"
    assert result.model == "test-model"
    assert result.usage == {"input_tokens": 11, "output_tokens": 7, "total_tokens": 18}
    assert len(responses.calls) == 1
    call = responses.calls[0]
    assert call["model"] == "test-model"
    assert call["instructions"] == "role"
    assert call["input"] == "observation"
    assert call["text_format"] is Decision
    assert call["temperature"] == 0.0
    assert call["max_output_tokens"] == 1024
    assert call["timeout"] == 12


def test_openai_provider_rejects_missing_parsed_output():
    responses = FakeResponses(None)
    provider = OpenAIResponsesProvider(model="test-model", client=FakeClient(responses))

    with pytest.raises(StructuredOutputError):
        provider.generate_structured(LLMRequest(), Decision)


def test_openai_provider_wraps_transport_failures():
    responses = FakeResponses(error=RuntimeError("network down"))
    provider = OpenAIResponsesProvider(model="test-model", client=FakeClient(responses))

    with pytest.raises(LLMProviderError, match="request failed"):
        provider.generate_structured(LLMRequest(), Decision)


def test_openai_provider_requires_api_key_when_no_client(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(LLMProviderError, match="OPENAI_API_KEY"):
        OpenAIResponsesProvider(model="test-model")


def test_openai_provider_accepts_api_key_from_environment(monkeypatch):
    # Inject a local SDK stub so this test never depends on the installed package
    # and never creates a network-capable client.
    monkeypatch.setenv("OPENAI_API_KEY", "test-placeholder-key")
    module = ModuleType("openai")

    class StubOpenAI:
        def __init__(self, *, api_key):
            self.api_key = api_key
            self.responses = SimpleNamespace()

    module.OpenAI = StubOpenAI
    monkeypatch.setitem(sys.modules, "openai", module)

    provider = OpenAIResponsesProvider(model="test-model")
    assert provider.provider_name == "openai"
    assert provider.model == "test-model"
    assert provider._client.api_key == "test-placeholder-key"


def test_openai_provider_validates_timeout_bounds():
    with pytest.raises(ValueError):
        OpenAIResponsesProvider(model="test-model", client=FakeClient(FakeResponses()), timeout_seconds=0)
    with pytest.raises(ValueError):
        OpenAIResponsesProvider(model="test-model", client=FakeClient(FakeResponses()), timeout_seconds=301)
