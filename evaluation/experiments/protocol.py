"""Research experiment protocol and leakage controls for AegisAI."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
from typing import Iterable


class ExperimentConfig(str, Enum):
    A = "A"
    B = "B"
    C = "C"


@dataclass(frozen=True)
class ScenarioSplit:
    train: tuple[tuple[str, int], ...]
    validation: tuple[tuple[str, int], ...]
    test: tuple[tuple[str, int], ...]

    def __post_init__(self) -> None:
        for partition in (self.train, self.validation, self.test):
            if len(partition) != len(set(partition)):
                raise ValueError("scenario splits must not contain duplicate pairs")
        sets = [set(self.train), set(self.validation), set(self.test)]
        if any(not s for s in sets):
            raise ValueError("train, validation, and test splits must be non-empty")
        if sets[0] & sets[1] or sets[0] & sets[2] or sets[1] & sets[2]:
            raise ValueError("scenario splits must be disjoint")

    @property
    def held_out(self) -> tuple[tuple[str, int], ...]:
        return self.test


@dataclass(frozen=True)
class ExperimentManifest:
    experiment_id: str
    config: ExperimentConfig
    split: ScenarioSplit
    model_provider: str
    model_name: str
    temperature: float
    seed: int
    adaptive_memory_enabled: bool

    def fingerprint(self) -> str:
        raw = repr(self).encode("utf-8")
        return sha256(raw).hexdigest()


def build_default_split(template_ids: Iterable[str], seeds: Iterable[int]) -> ScenarioSplit:
    # Freeze one-shot iterables before the Cartesian product. A seed generator must
    # cover every template, rather than silently being exhausted by the first one.
    template_values, seed_values = tuple(template_ids), tuple(seeds)
    rows = [(t, s) for t in template_values for s in seed_values]
    if len(rows) < 6:
        raise ValueError("default research split requires at least 6 scenario-seed pairs")
    # Deterministic split: template/seed pairs are sorted, then partitioned. No adaptive
    # memory is permitted to be generated from the held-out test set.
    rows = sorted(rows)
    n = len(rows)
    train_n = max(2, n // 2)
    val_n = max(2, (n - train_n) // 2)
    return ScenarioSplit(tuple(rows[:train_n]), tuple(rows[train_n:train_n + val_n]), tuple(rows[train_n + val_n:]))


def assert_memory_source_allowed(config: ExperimentConfig, scenario_pairs: Iterable[tuple[str, int]], split: ScenarioSplit) -> None:
    source = set(scenario_pairs)
    if source & set(split.test):
        raise ValueError("held-out test scenarios cannot generate adaptive memory")
    if not source <= set(split.train + split.validation):
        raise ValueError("memory-source scenarios must belong to the declared train or validation split")
    if config is ExperimentConfig.C and not source:
        raise ValueError("adaptive configuration requires explicit memory-source scenarios")


def build_template_holdout_split(
    train_template_ids: Iterable[str],
    validation_template_ids: Iterable[str],
    test_template_ids: Iterable[str],
    seeds: Iterable[int],
) -> ScenarioSplit:
    """Build a family/template hold-out split with no template overlap.

    Unlike ``build_default_split``, this intentionally holds out entire scenario templates.
    This is the preferred protocol for testing generalization to an unseen scenario family
    or attack-path variant. Seeds are reused across partitions only when their template differs.
    """
    groups = [tuple(sorted(set(group))) for group in
              (train_template_ids, validation_template_ids, test_template_ids)]
    if any(not group for group in groups):
        raise ValueError("train, validation, and test template groups must be non-empty")
    if set(groups[0]) & set(groups[1]) or set(groups[0]) & set(groups[2]) or set(groups[1]) & set(groups[2]):
        raise ValueError("template hold-out groups must be disjoint")
    seed_values = tuple(sorted(set(seeds)))
    if not seed_values:
        raise ValueError("template hold-out split requires at least one seed")

    def rows(templates: tuple[str, ...]) -> tuple[tuple[str, int], ...]:
        return tuple((template_id, seed) for template_id in templates for seed in seed_values)

    return ScenarioSplit(rows(groups[0]), rows(groups[1]), rows(groups[2]))
