"""Provider-independent structured-output interface.

The provider is a decision service, not an executor. Provider responses are treated as
untrusted data and are validated against the caller-supplied Pydantic model before being
returned. No provider implementation is coupled to AegisAI's simulator or controller.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from time import monotonic
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T", bound=BaseModel)


class LLMProviderError(RuntimeError):
    """Base error for provider or transport failures."""


class StructuredOutputError(LLMProviderError):
    """Raised when a provider response cannot satisfy the requested schema."""


class LLMRequest(BaseModel):
    """Safe, provider-neutral request envelope.

    `system_prompt` and `user_content` are context only. They are never interpreted as
    executable instructions by this layer. Provider-specific SDK options are intentionally
    excluded from the MVP contract.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    system_prompt: str = Field(default="", max_length=20_000)
    user_content: str = Field(default="", max_length=100_000)
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    max_output_tokens: int = Field(default=1_024, ge=1, le=16_384)


@dataclass(frozen=True)
class LLMResponse(Generic[T]):
    """Validated model output plus minimal operational metadata."""

    output: T
    provider: str
    model: str
    latency_seconds: float
    usage: dict[str, int] = field(default_factory=dict)


class LLMProvider(ABC):
    """Minimal synchronous contract shared by future provider adapters.

    Implementations must return an instance of `response_model` and must not execute tools,
    commands, network actions, or simulator mutations. The controller remains the execution gate.
    """

    provider_name: str = "unknown"

    @abstractmethod
    def generate_structured(
        self,
        request: LLMRequest,
        response_model: type[T],
    ) -> LLMResponse[T]:
        """Generate and validate one structured response."""
        raise NotImplementedError

    @staticmethod
    def validate_output(raw_output: Any, response_model: type[T]) -> T:
        """Validate untrusted provider output using the requested Pydantic schema."""
        try:
            if isinstance(raw_output, response_model):
                return raw_output
            if isinstance(raw_output, str):
                return response_model.model_validate_json(raw_output)
            return response_model.model_validate(raw_output)
        except Exception as exc:  # Pydantic may raise several validation/JSON errors.
            raise StructuredOutputError(
                f"provider output failed {response_model.__name__} validation"
            ) from exc


class BaseProviderAdapter(LLMProvider):
    """Convenience base for concrete SDK adapters added in a later phase."""

    def __init__(self, *, model: str, provider_name: str | None = None) -> None:
        if not model or len(model) > 200:
            raise ValueError("model must be a non-empty string of at most 200 characters")
        self.model = model
        if provider_name:
            self.provider_name = provider_name

    def _wrap(self, raw_output: Any, response_model: type[T], started: float,
              usage: dict[str, int] | None = None) -> LLMResponse[T]:
        output = self.validate_output(raw_output, response_model)
        return LLMResponse(
            output=output,
            provider=self.provider_name,
            model=self.model,
            latency_seconds=max(0.0, monotonic() - started),
            usage=dict(usage or {}),
        )
