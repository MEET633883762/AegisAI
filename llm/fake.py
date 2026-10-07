"""Deterministic in-process provider used only for contract/integration tests.

It has no network access and does not execute actions. Test code supplies the response payload.
"""
from __future__ import annotations

from typing import Any, Generic, TypeVar

from .provider import BaseProviderAdapter, LLMRequest, LLMResponse
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class FakeLLMProvider(BaseProviderAdapter, Generic[T]):
    """Small deterministic provider for testing future LLM agents without an API."""

    def __init__(self, response: Any, *, model: str = "fake-model") -> None:
        super().__init__(model=model, provider_name="fake")
        self.response = response
        self.calls = 0
        self.last_request: LLMRequest | None = None

    def generate_structured(
        self,
        request: LLMRequest,
        response_model: type[T],
    ) -> LLMResponse[T]:
        self.calls += 1
        self.last_request = request
        from time import monotonic
        started = monotonic()
        return self._wrap(self.response, response_model, started)
