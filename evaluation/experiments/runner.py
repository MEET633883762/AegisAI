"""Reproducible experiment runner for scripted AegisAI baselines."""
from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Protocol

from controller.orchestrator import Controller
from environment.actions import BlueAction, RedAction
from environment.scenarios import build_scenario
from evaluation.metrics.core import AggregateMetrics, EpisodeMetrics, aggregate_metrics, calculate_episode_metrics


class RedAgent(Protocol):
    def decide(self, observation) -> RedAction: ...


class BlueAgent(Protocol):
    def decide(self, observation) -> BlueAction: ...


@dataclass(frozen=True)
class EpisodeRun:
    metrics: EpisodeMetrics
    controller: Controller


@dataclass(frozen=True)
class ExperimentRun:
    """Immutable experiment result plus aggregate metrics."""

    experiment_id: str
    scenario_template_ids: tuple[str, ...]
    seeds: tuple[int, ...]
    episodes: tuple[EpisodeMetrics, ...]
    aggregate: AggregateMetrics


def run_episode(template_id: str, seed: int, red_agent: RedAgent, blue_agent: BlueAgent) -> EpisodeRun:
    controller = Controller(build_scenario(template_id, seed))
    latencies_ms: list[float] = []

    while not controller.done:
        red_start = perf_counter()
        red_action = red_agent.decide(controller.red_observation())
        latencies_ms.append((perf_counter() - red_start) * 1000.0)
        red_result = controller.submit_red(red_action)
        if not red_result.accepted:
            raise RuntimeError(f"Red baseline produced rejected action: {red_result.action_result.message}")
        if controller.done:
            break

        blue_start = perf_counter()
        blue_action = blue_agent.decide(controller.blue_observation())
        latencies_ms.append((perf_counter() - blue_start) * 1000.0)
        blue_result = controller.submit_blue(blue_action)
        if not blue_result.accepted:
            raise RuntimeError(f"Blue baseline produced rejected action: {blue_result.action_result.message}")
        if not controller.done:
            controller.advance()

    metrics = calculate_episode_metrics(controller, decision_latencies_ms=latencies_ms)
    return EpisodeRun(metrics=metrics, controller=controller)


def run_experiment(
    experiment_id: str,
    template_ids: tuple[str, ...],
    seeds: tuple[int, ...],
    red_agent_factory,
    blue_agent_factory,
) -> ExperimentRun:
    if not experiment_id.strip():
        raise ValueError("experiment_id must not be empty")
    if not template_ids:
        raise ValueError("at least one scenario template is required")
    if not seeds:
        raise ValueError("at least one seed is required")

    rows: list[EpisodeMetrics] = []
    for template_id in template_ids:
        for seed in seeds:
            # Fresh agents per episode prevents hidden state from leaking across trials.
            result = run_episode(template_id, seed, red_agent_factory(), blue_agent_factory())
            rows.append(result.metrics)

    return ExperimentRun(
        experiment_id=experiment_id,
        scenario_template_ids=template_ids,
        seeds=seeds,
        episodes=tuple(rows),
        aggregate=aggregate_metrics(rows),
    )
