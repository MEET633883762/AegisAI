"""OpenAI Responses API adapter for AegisAI structured decisions.

The adapter is intentionally narrow: it sends provider-neutral request context to the
Responses API, requests a Pydantic structured output, and returns the validated model.
It never executes actions or receives simulator/controller objects.
"""
from __future__ import annotations

import os
from time import monotonic
from typing import Any, Generic, TypeVar

from pydantic import BaseModel

from .provider import BaseProviderAdapter, LLMProviderError, LLMRequest, LLMResponse, StructuredOutputError

T = TypeVar("T", bound=BaseModel)


class OpenAIResponsesProvider(BaseProviderAdapter, Generic[T]):
    """Provider adapter using the OpenAI Responses API structured-output parser.

    The OpenAI SDK is imported lazily so importing the AegisAI provider layer does not
    require a configured API key and offline tests remain fully deterministic.
    """

    def __init__(
        self,
        *,
        model: str,
        api_key: str | None = None,
        timeout_seconds: float = 30.0,
        client: Any | None = None,
    ) -> None:
        super().__init__(model=model, provider_name="openai")
        if not 0.1 <= timeout_seconds <= 300.0:
            raise ValueError("timeout_seconds must be between 0.1 and 300")
        self.timeout_seconds = timeout_seconds

        if client is not None:
            self._client = client
            return

        key = api_key or os.getenv("OPENAI_API_KEY")
        if not key:
            raise LLMProviderError(
                "OPENAI_API_KEY is not configured; refusing to create a live provider"
            )

        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover - depends on installation
            raise LLMProviderError(
                "OpenAI provider requires the 'openai' Python package"
            ) from exc

        try:
            self._client = OpenAI(api_key=key)
        except Exception as exc:  # SDK configuration/transport setup failure
            raise LLMProviderError("failed to initialize OpenAI client") from exc

    def generate_structured(
        self,
        request: LLMRequest,
        response_model: type[T],
    ) -> LLMResponse[T]:
        """Generate exactly one structured response without provider-side retries."""
        started = monotonic()
        try:
            response = self._client.responses.parse(
                model=self.model,
                instructions=request.system_prompt,
                input=request.user_content,
                text_format=response_model,
                temperature=request.temperature,
                max_output_tokens=request.max_output_tokens,
                timeout=self.timeout_seconds,
            )
        except Exception as exc:
            raise LLMProviderError("OpenAI Responses API request failed") from exc

        parsed = getattr(response, "output_parsed", None)
        if parsed is None:
            raise StructuredOutputError(
                f"OpenAI response did not contain parsed {response_model.__name__} output"
            )

        # Keep the provider boundary authoritative: even SDK-parsed output is passed
        # through the same application-level Pydantic validation contract.
        output = self.validate_output(parsed, response_model)
        return LLMResponse(
            output=output,
            provider=self.provider_name,
            model=self.model,
            latency_seconds=max(0.0, monotonic() - started),
            usage=_extract_usage(response),
        )


def _extract_usage(response: Any) -> dict[str, int]:
    """Extract stable integer token counters without depending on SDK internals."""
    usage = getattr(response, "usage", None)
    if usage is None:
        return {}

    result: dict[str, int] = {}
    for source_name, output_name in (
        ("input_tokens", "input_tokens"),
        ("output_tokens", "output_tokens"),
        ("total_tokens", "total_tokens"),
    ):
        value = getattr(usage, source_name, None)
        if isinstance(value, int) and value >= 0:
            result[output_name] = value
    return result
