from dataclasses import dataclass

from evaluation.live.config import LiveExperimentConfig
from evaluation.live.validation import validate_single_live_episode
from llm.provider import LLMProvider, LLMRequest, LLMResponse
from environment.actions import RedAction, RedActionType, BlueAction, BlueActionType


@dataclass
class FakeProvider(LLMProvider):
    calls: int = 0
    provider_name: str = "fake"

    def generate_structured(self, request: LLMRequest, response_model):
        self.calls += 1
        if response_model is RedAction:
            output = RedAction(
                action_type=RedActionType.DISCOVER_HOST,
                target="external",
                parameters={"host": "host_a"},
                rationale="discover the visible host",
            )
        else:
            output = BlueAction(
                action_type=BlueActionType.MONITOR,
                target="host_a",
                parameters={},
                rationale="monitor the simulated host",
            )
        return LLMResponse(output=output, provider="fake", model="test", latency_seconds=0.0)


def test_validation_is_fail_closed_without_explicit_allow():
    config = LiveExperimentConfig(model="test-model")
    result = validate_single_live_episode(
        "web_exploit_lateral_exfil", 1, config, lambda _: FakeProvider(), allow_live=False
    )
    assert result.status == "refused"
    assert result.live_attempted is False


def test_preflight_failure_prevents_provider_factory_call(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    config = LiveExperimentConfig(model="test-model")
    created = []

    def factory(_):
        created.append(True)
        return FakeProvider()

    result = validate_single_live_episode(
        "web_exploit_lateral_exfil", 1, config, factory, allow_live=True
    )
    assert result.status == "preflight_failed"
    assert result.live_attempted is False
    assert created == []


def test_single_validation_uses_bounded_episode(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-used")
    monkeypatch.setattr("evaluation.live.preflight.version", lambda name: "test-sdk")
    config = LiveExperimentConfig(
        model="test-model", max_provider_calls=4, max_total_tokens=100, max_episode_steps=2
    )
    providers = []

    def factory(_):
        provider = FakeProvider()
        providers.append(provider)
        return provider

    result = validate_single_live_episode(
        "web_exploit_lateral_exfil", 1, config, factory, allow_live=True
    )
    assert result.live_attempted is True
    assert result.episode is not None
    assert result.episode.provider_usage.calls <= 4
    assert providers and providers[0].calls <= 4
