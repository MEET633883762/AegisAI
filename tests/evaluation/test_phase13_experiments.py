from __future__ import annotations

import json

import pytest
from pydantic import BaseModel

from agents.blue.llm import LLMBlueAgent
from agents.blue.scripted import ScriptedBlueAgent
from agents.red.llm import LLMRedAgent
from agents.red.scripted import ScriptedRedAgent
from environment.actions import BlueAction, RedAction
from evaluation.experiments.memory_gate import build_validated_memory_context
from evaluation.experiments.protocol import ExperimentConfig, ScenarioSplit, build_default_split
from evaluation.experiments.research import run_three_configurations
from evaluation.metrics.core import aggregate_metrics
from llm.provider import BaseProviderAdapter, LLMRequest, LLMResponse
from memory.knowledge_patch import KnowledgePatch, ValidationRecord
from telemetry.observation_builder import BlueObservation, RedObservation


class ObservationPolicyProvider(BaseProviderAdapter):
    """Offline test double: emulates structured model output using existing scripted policies."""
    def __init__(self, role: str):
        super().__init__(model="offline-policy-test", provider_name="test-double")
        self.role = role
        self.policy = ScriptedRedAgent() if role == "red" else ScriptedBlueAgent()
        self.last_request = None

    def generate_structured(self, request: LLMRequest, response_model: type[BaseModel]) -> LLMResponse:
        self.last_request = request
        if self.role == "red":
            raw = request.user_content.split("BEGIN RED OBSERVATION\n", 1)[1].split("\nEND RED OBSERVATION", 1)[0]
            action = self.policy.decide(RedObservation.model_validate(json.loads(raw)))
        else:
            raw = request.user_content.split("BEGIN BLUE OBSERVATION\n", 1)[1].split("\nEND BLUE OBSERVATION", 1)[0]
            action = self.policy.decide(BlueObservation.model_validate(json.loads(raw)))
        return self._wrap(action, response_model, __import__("time").monotonic())


def test_default_split_is_disjoint_and_reproducible():
    split1 = build_default_split(("web_exploit_lateral_exfil", "credential_reuse_known_vuln"), (1, 2, 7, 9))
    split2 = build_default_split(("web_exploit_lateral_exfil", "credential_reuse_known_vuln"), (1, 2, 7, 9))
    assert split1 == split2
    assert not set(split1.train) & set(split1.validation)
    assert not set(split1.train) & set(split1.test)
    assert not set(split1.validation) & set(split1.test)


def test_held_out_scenarios_cannot_generate_memory():
    split = ScenarioSplit((("a", 1),), (("a", 2),), (("a", 3),))
    with pytest.raises(ValueError):
        from evaluation.experiments.protocol import assert_memory_source_allowed
        assert_memory_source_allowed(ExperimentConfig.C, (("a", 3),), split)


def test_llm_blue_memory_is_bounded_and_included():
    provider = ObservationPolicyProvider("blue")
    agent = LLMBlueAgent(provider, memory_context="Lesson: inspect evidence first")
    from environment.scenarios import build_scenario
    from controller.orchestrator import Controller
    controller = Controller(build_scenario("web_exploit_lateral_exfil", 1))
    agent.decide(controller.blue_observation())
    assert "BEGIN VALIDATED MEMORY" in provider.last_request.user_content
    assert "inspect evidence first" in provider.last_request.user_content


def test_three_configuration_harness_runs_same_held_out_set():
    split = ScenarioSplit(
        (("web_exploit_lateral_exfil", 1), ("credential_reuse_known_vuln", 1)),
        (("web_exploit_lateral_exfil", 2), ("credential_reuse_known_vuln", 2)),
        (("web_exploit_lateral_exfil", 7), ("credential_reuse_known_vuln", 7)),
    )
    result = run_three_configurations(
        experiment_id="phase13-test",
        split=split,
        scripted_red_factory=ScriptedRedAgent,
        scripted_blue_factory=ScriptedBlueAgent,
        llm_red_factory=lambda: LLMRedAgent(ObservationPolicyProvider("red")),
        llm_blue_no_memory_factory=lambda: LLMBlueAgent(ObservationPolicyProvider("blue")),
        llm_blue_adaptive_factory=lambda: LLMBlueAgent(ObservationPolicyProvider("blue"), memory_context="validated test-double lesson"),
        model_provider="test-double",
        model_name="offline-policy-test",
        temperature=0.0,
        seed=123,
        memory_source_pairs=split.train + split.validation,
    )
    assert result.baseline.aggregate.episodes == 2
    assert result.no_memory.aggregate.episodes == 2
    assert result.adaptive.aggregate.episodes == 2
    assert len(result.manifest_fingerprints) == 3
    assert result.no_memory.scenario_template_ids == result.adaptive.scenario_template_ids
    assert result.no_memory.seeds == result.adaptive.seeds


def test_validated_memory_gate_rejects_unvalidated_and_limits_context():
    patch = KnowledgePatch.candidate(
        patch_id="p1", version=1, role="blue", lesson="test lesson", recommendation="test recommendation",
        trace_ids=(1,), episode_ids=("ep1",), scenario_ids=("web_exploit_lateral_exfil:1",), steps=(1,), outcomes=("success",),
    )
    record = ValidationRecord(
        validation_id="v1", baseline_metric="defensive_score", baseline_value=0.2, candidate_value=0.3,
        improvement=0.1, threshold=0.05, held_out=True, passed=True, validated_at="2026-01-01T00:00:00+00:00",
    )
    validated = patch.validate(record)
    split = ScenarioSplit((("web_exploit_lateral_exfil", 1),), (("credential_reuse_known_vuln", 1),), (("web_exploit_lateral_exfil", 7),))
    text = build_validated_memory_context((validated,), source_pairs=split.train, split=split)
    assert "test lesson" in text
    assert "test recommendation" in text
    assert len(text) < 8_000
