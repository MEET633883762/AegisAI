"""Provider-level accounting and hard budgets for live experiments."""
from __future__ import annotations

from dataclasses import dataclass
from time import monotonic
from typing import Any, TypeVar

from pydantic import BaseModel

from llm.provider import LLMProvider, LLMProviderError, LLMRequest, LLMResponse

T = TypeVar("T", bound=BaseModel)


class LiveBudgetExceeded(LLMProviderError):
    """Raised before a provider call when a hard live-experiment budget is exhausted."""


@dataclass
class ProviderUsage:
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0


class BudgetedProvider(LLMProvider):
    """Wrap any provider and enforce call/token/wall-clock limits."""

    def __init__(self, inner: LLMProvider, *, max_calls: int, max_total_tokens: int,
                 deadline: float | None = None) -> None:
        if max_calls < 1 or max_total_tokens < 1:
            raise ValueError("provider budgets must be positive")
        self.inner = inner
        self.provider_name = inner.provider_name
        self.max_calls = max_calls
        self.max_total_tokens = max_total_tokens
        self.deadline = deadline
        self.usage = ProviderUsage()

    def generate_structured(self, request: LLMRequest, response_model: type[T]) -> LLMResponse[T]:
        if self.deadline is not None and monotonic() >= self.deadline:
            raise LiveBudgetExceeded("live episode wall-clock budget exhausted")
        if self.usage.calls >= self.max_calls:
            raise LiveBudgetExceeded("live provider-call budget exhausted")
        self.usage.calls += 1
        response = self.inner.generate_structured(request, response_model)
        usage = response.usage
        total = usage.get("total_tokens", 0)
        if not isinstance(total, int) or total < 0:
            total = 0
        projected = self.usage.total_tokens + total
        if projected > self.max_total_tokens:
            raise LiveBudgetExceeded("live token budget exhausted")
        self.usage.input_tokens += max(0, int(usage.get("input_tokens", 0)))
        self.usage.output_tokens += max(0, int(usage.get("output_tokens", 0)))
        self.usage.total_tokens = projected
        return response
