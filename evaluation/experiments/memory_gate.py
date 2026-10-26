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
    current_length = 0
    for patch in patches:
        if patch.status.value != "validated":
            continue
        evidence_pairs = set()
        invalid_source = not patch.evidence_scenario_ids
        for scenario_id in patch.evidence_scenario_ids:
            template, separator, raw_seed = scenario_id.rpartition(":")
            # Every reference must resolve, including mixed valid/malformed lists.
            # Require the same canonical template:integer format as scenario IDs
            # emitted by the Controller instead of accepting partial provenance.
            try:
                seed = int(raw_seed)
            except ValueError:
                invalid_source = True
                break
            if not separator or not template or str(seed) != raw_seed:
                invalid_source = True
                break
            evidence_pairs.add((template, seed))
        if invalid_source or not evidence_pairs or not evidence_pairs <= allowed:
            continue
        text = patch.context_text()
        next_length = current_length + len(text) + (1 if chunks else 0)
        if next_length > max_chars:
            break
        chunks.append(text)
        current_length = next_length
    return "\n".join(chunks)
