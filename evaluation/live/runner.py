"""Bounded live-LLM episode runner; no direct execution outside Controller."""
from __future__ import annotations

from dataclasses import dataclass
from time import monotonic, perf_counter
from typing import Callable

from agents.blue.llm import LLMBlueAgent
from agents.red.llm import LLMRedAgent
from controller.orchestrator import Controller
from environment.actions import BlueAction, RedAction
from environment.scenarios import build_scenario
from evaluation.metrics.core import EpisodeMetrics, calculate_episode_metrics
from llm.provider import LLMProvider

from .budget import BudgetedProvider, LiveBudgetExceeded, ProviderUsage
from .config import LiveExperimentConfig


@dataclass(frozen=True)
class LiveEpisodeResult:
    status: str
    metrics: EpisodeMetrics
    provider_usage: ProviderUsage
    episode_id: str
    error: str | None = None


def run_live_episode(
    template_id: str,
    seed: int,
    config: LiveExperimentConfig,
    provider_factory: Callable[[str], LLMProvider],
    *,
    memory_context: str = "",
) -> LiveEpisodeResult:
    """Run one bounded real-LLM episode against the deterministic simulator.

    The provider factory receives only the configured model name. Both agents share the same
    hard provider budget, while Controller remains the sole action execution boundary.
    """
    started = monotonic()
    deadline = started + config.max_wall_seconds
    provider = BudgetedProvider(
        provider_factory(config.model),
        max_calls=config.max_provider_calls,
        max_total_tokens=config.max_total_tokens,
        deadline=deadline,
    )
    red = LLMRedAgent(provider, temperature=config.temperature,
                      max_output_tokens=config.max_output_tokens, max_retries=config.max_retries)
    blue = LLMBlueAgent(provider, memory_context=memory_context, temperature=config.temperature,
                        max_output_tokens=config.max_output_tokens, max_retries=config.max_retries)
    controller = Controller(build_scenario(template_id, seed))
    latencies_ms: list[float] = []
    status = "completed"
    error: str | None = None

    try:
        for _ in range(config.max_episode_steps):
            if controller.done:
                break
            if monotonic() >= deadline:
                raise LiveBudgetExceeded("live episode wall-clock budget exhausted")

            red_start = perf_counter()
            red_action: RedAction = red.decide(controller.red_observation())
            latencies_ms.append((perf_counter() - red_start) * 1000.0)
            red_result = controller.submit_red(red_action)
            if not red_result.accepted:
                raise RuntimeError("Controller rejected Red action: " + red_result.action_result.message)
            if controller.done:
                break

            blue_start = perf_counter()
            blue_action: BlueAction = blue.decide(controller.blue_observation())
            latencies_ms.append((perf_counter() - blue_start) * 1000.0)
            blue_result = controller.submit_blue(blue_action)
            if not blue_result.accepted:
                raise RuntimeError("Controller rejected Blue action: " + blue_result.action_result.message)
            if not controller.done:
                controller.advance()
        else:
            status = "step_budget_exhausted"
    except Exception as exc:
        status = "aborted"
        error = f"{type(exc).__name__}: {exc}"

    metrics = calculate_episode_metrics(controller, decision_latencies_ms=latencies_ms)
    return LiveEpisodeResult(
        status=status,
        metrics=metrics,
        provider_usage=provider.usage,
        episode_id=controller.episode_id,
        error=error,
    )
