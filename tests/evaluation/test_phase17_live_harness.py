from types import SimpleNamespace

import pytest
from pydantic import BaseModel, ConfigDict

from evaluation.live.budget import BudgetedProvider, LiveBudgetExceeded
from evaluation.live.config import LiveExperimentConfig
from evaluation.live.runner import run_live_episode
from llm.provider import BaseProviderAdapter, LLMRequest


class Decision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: str


class FixedProvider(BaseProviderAdapter):
    def __init__(self, *, fail=False, usage=None):
        super().__init__(model="fixed", provider_name="fixed")
        self.fail = fail
        self.usage = usage or {"input_tokens": 2, "output_tokens": 3, "total_tokens": 5}
        self.calls = 0

    def generate_structured(self, request: LLMRequest, response_model):
        self.calls += 1
        if self.fail:
            from llm.provider import LLMProviderError
            raise LLMProviderError("provider failure")
        return self._wrap({"value": "ok"}, response_model, 0.0, self.usage)


def test_live_config_has_hard_bounds():
    with pytest.raises(ValueError):
        LiveExperimentConfig(model="x", max_episode_steps=31)
    with pytest.raises(ValueError):
        LiveExperimentConfig(model="x", max_provider_calls=0)


def test_budgeted_provider_counts_usage_and_calls():
    inner = FixedProvider()
    wrapped = BudgetedProvider(inner, max_calls=2, max_total_tokens=10)
    request = LLMRequest()
    wrapped.generate_structured(request, Decision)
    wrapped.generate_structured(request, Decision)
    assert wrapped.usage.calls == 2
    assert wrapped.usage.total_tokens == 10
    with pytest.raises(LiveBudgetExceeded):
        wrapped.generate_structured(request, Decision)


def test_budgeted_provider_rejects_token_overrun_without_accepting_usage():
    inner = FixedProvider(usage={"total_tokens": 11})
    wrapped = BudgetedProvider(inner, max_calls=2, max_total_tokens=10)
    with pytest.raises(LiveBudgetExceeded):
        wrapped.generate_structured(LLMRequest(), Decision)
    assert wrapped.usage.total_tokens == 0


def test_live_episode_aborts_cleanly_on_provider_failure():
    config = LiveExperimentConfig(model="fixed", max_retries=0, max_provider_calls=2)
    result = run_live_episode("web_exploit_lateral_exfil", 1, config,
                              lambda model: FixedProvider(fail=True))
    assert result.status == "aborted"
    assert result.error is not None
    assert result.provider_usage.calls == 1
    assert result.metrics.scenario_id == "web_exploit_lateral_exfil:1"
