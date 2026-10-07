"""Hard boundary between training/validation evidence and held-out experiment scenarios."""
from __future__ import annotations

from memory.knowledge_patch import KnowledgePatch
from evaluation.experiments.protocol import ExperimentConfig, ScenarioSplit, assert_memory_source_allowed


def build_validated_memory_context(
    patches: tuple[KnowledgePatch, ...],
    *,
    source_pairs: tuple[tuple[str, int], ...],
    split: ScenarioSplit,
    max_chars: int = 8_000,
) -> str:
    """Render only validated patches whose evidence is outside the held-out test split."""
    assert_memory_source_allowed(ExperimentConfig.C, source_pairs, split)
    if max_chars < 1:
        raise ValueError("max_chars must be positive")
    allowed = set(source_pairs)
    chunks: list[str] = []
    for patch in patches:
        if patch.status.value != "validated":
            continue
        evidence_pairs = set()
        for scenario_id in patch.evidence_scenario_ids:
            if ":" in scenario_id:
                template, raw_seed = scenario_id.rsplit(":", 1)
                try:
                    evidence_pairs.add((template, int(raw_seed)))
                except ValueError:
                    continue
        # A patch without a resolvable source pair is not silently trusted.
        if evidence_pairs and not evidence_pairs <= allowed:
            continue
        if patch.evidence_scenario_ids and not evidence_pairs:
            continue
        text = patch.context_text()
        if sum(map(len, chunks)) + len(text) + 1 > max_chars:
            break
        chunks.append(text)
    return "\n".join(chunks)
