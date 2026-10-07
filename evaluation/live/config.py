"""Explicit safety and budget configuration for live LLM experiments."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LiveExperimentConfig:
    """Hard bounds applied to one controlled simulator episode."""

    model: str
    temperature: float = 0.0
    max_output_tokens: int = 512
    timeout_seconds: float = 30.0
    max_retries: int = 1
    max_episode_steps: int = 30
    max_provider_calls: int = 100
    max_total_tokens: int = 50_000
    max_wall_seconds: float = 300.0

    def __post_init__(self) -> None:
        if not self.model.strip():
            raise ValueError("model must not be empty")
        if not 0.0 <= self.temperature <= 2.0:
            raise ValueError("temperature must be between 0 and 2")
        if not 1 <= self.max_output_tokens <= 16_384:
            raise ValueError("max_output_tokens must be between 1 and 16384")
        if not 0 <= self.max_retries <= 2:
            raise ValueError("max_retries must be between 0 and 2")
        if not 1 <= self.max_episode_steps <= 30:
            raise ValueError("max_episode_steps must be between 1 and 30")
        if not 1 <= self.max_provider_calls:
            raise ValueError("max_provider_calls must be positive")
        if not 1 <= self.max_total_tokens:
            raise ValueError("max_total_tokens must be positive")
        if not 0.1 <= self.max_wall_seconds <= 3_600:
            raise ValueError("max_wall_seconds must be between 0.1 and 3600")
