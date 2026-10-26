"""Research comparisons must not lose cases or admit untraceable memory."""
import pytest

from evaluation.experiments.memory_gate import build_validated_memory_context
from evaluation.experiments.protocol import (
    ExperimentConfig, ScenarioSplit, assert_memory_source_allowed, build_default_split,
)
from memory.knowledge_patch import KnowledgePatch
from memory.validator import MemoryValidator


def test_default_split_keeps_cartesian_product_for_one_shot_iterators():
    templates, seeds = ("alpha", "beta"), (1, 2, 3, 4)
    split = build_default_split(iter(templates), iter(seeds))
    assert split == build_default_split(templates, seeds)
    assert set(split.train + split.validation + split.test) == {(t, s) for t in templates for s in seeds}


def test_duplicate_pairs_cannot_inflate_a_research_split():
    with pytest.raises(ValueError, match="duplicate pairs"):
        ScenarioSplit((("a", 1), ("a", 1)), (("a", 2),), (("a", 3),))
    with pytest.raises(ValueError, match="duplicate pairs"):
        build_default_split(("a", "a"), (1, 2, 3, 4))


def test_memory_cannot_use_undeclared_source_pairs():
    split = ScenarioSplit((("a", 1),), (("a", 2),), (("a", 3),))
    with pytest.raises(ValueError, match="declared train or validation"):
        assert_memory_source_allowed(ExperimentConfig.C, (("outside", 1),), split)


def _validated_patch():
    patch = KnowledgePatch.candidate(
        patch_id="provenance-test", version=1, role="blue", lesson="Contain confirmed activity",
        recommendation="Use the visible evidence", trace_ids=(1,), episode_ids=("e1",),
        scenario_ids=("a:1",), steps=(1,), outcomes=("success",),
    )
    return MemoryValidator().evaluate(
        patch, validation_id="v1", metric="score", baseline_value=.2,
        candidate_value=.4, held_out=True,
    )


@pytest.mark.parametrize("references", [(), ("a:1", "broken"), ("a:1", "a:nan"), ("a:1", "a:3"), ("a:1", "a:03"), (":1",), ("a:-1",)])
def test_memory_context_fails_closed_on_any_unresolvable_or_held_out_reference(references):
    split = ScenarioSplit((("a", 1),), (("a", 2),), (("a", 3),))
    patch = _validated_patch().model_copy(update={"evidence_scenario_ids": references})
    assert build_validated_memory_context((patch,), source_pairs=split.train, split=split) == ""


def test_known_valid_sources_remain_available_with_bounded_context():
    split = ScenarioSplit((("a", 1),), (("a", 2),), (("a", 3),))
    patch = _validated_patch()
    context = build_validated_memory_context((patch,), source_pairs=split.train, split=split)
    assert "Contain confirmed activity" in context
    assert build_validated_memory_context((patch,), source_pairs=split.train, split=split, max_chars=5) == ""


def test_context_budget_counts_all_separators_and_allows_an_exact_fit():
    split = ScenarioSplit((("a", 1),), (("a", 2),), (("a", 3),))
    patch = _validated_patch()
    text = patch.context_text()
    assert build_validated_memory_context((patch,), source_pairs=split.train, split=split,
                                          max_chars=len(text)) == text
    patches = tuple(patch.model_copy(update={"patch_id": f"p{i}"}) for i in range(4))
    limit = len(text) * 4 + 2  # Four chunks need three newline separators.
    rendered = build_validated_memory_context(patches, source_pairs=split.train, split=split,
                                             max_chars=limit)
    assert rendered == "\n".join([text] * 3)
    assert len(rendered) <= limit
