"""Research-level experiment orchestration and comparison results."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable

from evaluation.experiments.protocol import ExperimentConfig, ExperimentManifest, ScenarioSplit, assert_memory_source_allowed
from evaluation.experiments.runner import ExperimentRun, run_experiment


@dataclass(frozen=True)
class ComparisonResult:
    baseline: ExperimentRun
    no_memory: ExperimentRun
    adaptive: ExperimentRun
    adaptation_improvement: float
    generalization_improvement: float
    manifest_fingerprints: tuple[str, str, str]


def _pairs_to_groups(pairs: Iterable[tuple[str, int]]) -> dict[str, tuple[int, ...]]:
    groups: dict[str, list[int]] = {}
    for template, seed in pairs:
        groups.setdefault(template, []).append(seed)
    return {k: tuple(v) for k, v in sorted(groups.items())}


def run_three_configurations(
    *,
    experiment_id: str,
    split: ScenarioSplit,
    scripted_red_factory: Callable,
    scripted_blue_factory: Callable,
    llm_red_factory: Callable,
    llm_blue_no_memory_factory: Callable,
    llm_blue_adaptive_factory: Callable,
    model_provider: str,
    model_name: str,
    temperature: float,
    seed: int,
    memory_source_pairs: Iterable[tuple[str, int]],
) -> ComparisonResult:
    """Run A/B/C on identical held-out test scenarios.

    The adaptive factory receives only validated memory derived from non-test pairs. This function
    does not create memory from test outcomes and therefore provides a hard leakage boundary.
    """
    source_pairs = tuple(memory_source_pairs)
    assert_memory_source_allowed(ExperimentConfig.C, source_pairs, split)
    test_groups = _pairs_to_groups(split.test)
    if not test_groups:
        raise ValueError("test split must not be empty")

    def execute(eid: str, red_factory: Callable, blue_factory: Callable) -> ExperimentRun:
        episodes = []
        for template, seeds in test_groups.items():
            run = run_experiment(eid, (template,), seeds, red_factory, blue_factory)
            episodes.extend(run.episodes)
        # Preserve the existing immutable ExperimentRun contract while combining groups.
        from evaluation.metrics.core import aggregate_metrics
        return ExperimentRun(eid, tuple(test_groups), tuple(sorted(s for ss in test_groups.values() for s in ss)), tuple(episodes), aggregate_metrics(episodes))

    a = execute(experiment_id + "-A", scripted_red_factory, scripted_blue_factory)
    b = execute(experiment_id + "-B", llm_red_factory, llm_blue_no_memory_factory)
    c = execute(experiment_id + "-C", llm_red_factory, llm_blue_adaptive_factory)

    # Higher defensive score is better: detection + mitigation, while lower attack success is better.
    b_score = (b.aggregate.detection_rate + b.aggregate.mitigation_success_rate + (1.0 - b.aggregate.attack_success_rate)) / 3.0
    c_score = (c.aggregate.detection_rate + c.aggregate.mitigation_success_rate + (1.0 - c.aggregate.attack_success_rate)) / 3.0
    improvement = c_score - b_score
    # Generalization is measured on the same held-out set; this is deliberately separate from
    # training/validation patch generation.
    generalization = improvement

    manifests = tuple(
        ExperimentManifest(experiment_id + suffix, config, split, model_provider, model_name,
                           temperature, seed, config is ExperimentConfig.C).fingerprint()
        for suffix, config in (("-A", ExperimentConfig.A), ("-B", ExperimentConfig.B), ("-C", ExperimentConfig.C))
    )
    return ComparisonResult(a, b, c, improvement, generalization, manifests)
