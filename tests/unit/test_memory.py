import pytest

from controller import Controller
from environment.scenarios import build_scenario
from memory import FailureAnalyzer, KnowledgePatch, KnowledgeRepository, MemoryValidator, PatchStatus
from tests.unit.conftest import blue, red


def _failure_traces():
    c = Controller(build_scenario("web_exploit_lateral_exfil", 11), episode_id="ep-memory")
    assert c.submit_red(red("ENUMERATE_PORT", "host_a")).accepted
    # MONITOR is accepted but has no state change, giving the analyzer a conservative failure signal.
    assert c.submit_blue(blue("MONITOR", "host_a")).accepted
    return c.xai_log().traces()


def test_failure_analyzer_creates_evidence_grounded_candidate():
    candidates = FailureAnalyzer().analyze(_failure_traces())
    assert len(candidates) == 1
    patch = candidates[0]
    assert patch.status is PatchStatus.CANDIDATE
    assert patch.role == "blue"
    assert patch.evidence_trace_ids == (1, 2)
    assert patch.evidence_episode_ids == ("ep-memory",)
    assert patch.evidence_scenario_ids == ("web_exploit_lateral_exfil:11",)
    assert patch.evidence_steps == (0,)


def test_candidate_requires_evidence_and_validated_context_cannot_use_unvalidated_patch():
    with pytest.raises(ValueError):
        KnowledgePatch.candidate(
            patch_id="bad", version=1, role="blue", lesson="x", recommendation="y",
            trace_ids=(), episode_ids=("e",), scenario_ids=("s",), steps=(0,), outcomes=("success",)
        )
    patch = FailureAnalyzer().analyze(_failure_traces())[0]
    with pytest.raises(ValueError):
        patch.context_text()


def test_validator_requires_held_out_improvement():
    patch = FailureAnalyzer().analyze(_failure_traces())[0]
    validator = MemoryValidator(minimum_improvement=0.05)
    rejected = validator.evaluate(
        patch, validation_id="v1", metric="defensive_score", baseline_value=0.80,
        candidate_value=0.90, held_out=False
    )
    assert rejected.status is PatchStatus.REJECTED
    assert rejected.validation and not rejected.validation.passed


def test_validator_accepts_only_held_out_threshold_improvement():
    patch = FailureAnalyzer().analyze(_failure_traces())[0]
    validated = MemoryValidator(minimum_improvement=0.05).evaluate(
        patch, validation_id="v2", metric="defensive_score", baseline_value=0.80,
        candidate_value=0.90, held_out=True
    )
    assert validated.status is PatchStatus.VALIDATED
    assert validated.validation and validated.validation.passed
    assert "Lesson:" in validated.context_text()


def test_repository_preserves_versions_and_deep_copy_isolation():
    patch = FailureAnalyzer().analyze(_failure_traces())[0]
    repo = KnowledgeRepository()
    repo.add_candidate(patch)
    fetched = repo.get(patch.patch_id)
    assert fetched is not patch
    assert repo.versions(patch.patch_id)[0].version == 1
    validated = MemoryValidator().evaluate(
        patch, validation_id="v3", metric="defensive_score", baseline_value=0.5,
        candidate_value=0.6, held_out=True
    )
    # Store validated state as a new immutable version.
    validated_v2 = validated.model_copy(update={"version": 2})
    repo.update(validated_v2)
    assert repo.get(patch.patch_id).status is PatchStatus.VALIDATED
    assert [p.version for p in repo.versions(patch.patch_id)] == [1, 2]
    assert len(repo.validated("blue")) == 1


def test_revoke_is_reversible_and_never_deletes_history():
    patch = FailureAnalyzer().analyze(_failure_traces())[0]
    validated = MemoryValidator().evaluate(
        patch, validation_id="v4", metric="defensive_score", baseline_value=0.5,
        candidate_value=0.6, held_out=True
    )
    repo = KnowledgeRepository()
    repo.add_candidate(patch)
    repo.update(validated.model_copy(update={"version": 2}))
    revoked = repo.revoke(patch.patch_id)
    assert revoked.status is PatchStatus.REVOKED
    assert [p.version for p in repo.versions(patch.patch_id)] == [1, 2, 3]
    assert repo.validated("blue") == ()
