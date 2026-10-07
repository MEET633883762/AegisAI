from agents.blue.scripted import ScriptedBlueAgent
from agents.red.scripted import ScriptedRedAgent
from evaluation.experiments.runner import run_episode, run_experiment
from evaluation.metrics.core import aggregate_metrics


def test_single_episode_metrics_are_grounded_in_telemetry():
    run = run_episode("credential_reuse_known_vuln", 1, ScriptedRedAgent(), ScriptedBlueAgent())
    m = run.metrics
    assert m.scenario_id == "credential_reuse_known_vuln:1"
    assert m.total_alerts == len(run.controller.telemetry_log().alerts())
    assert 0.0 <= m.detection_rate <= 1.0
    assert 0.0 <= m.mitigation_success_rate <= 1.0
    assert 0.0 <= m.false_positive_rate <= 1.0
    assert m.decision_latency_ms is not None


def test_runner_is_reproducible_for_episode_outcomes():
    kwargs = dict(
        experiment_id="baseline-repro",
        template_ids=("web_exploit_lateral_exfil", "credential_reuse_known_vuln"),
        seeds=(1, 2),
        red_agent_factory=ScriptedRedAgent,
        blue_agent_factory=ScriptedBlueAgent,
    )
    a = run_experiment(**kwargs)
    b = run_experiment(**kwargs)
    assert [x.attack_success for x in a.episodes] == [x.attack_success for x in b.episodes]
    assert [x.detection_rate for x in a.episodes] == [x.detection_rate for x in b.episodes]
    assert [x.mitigation_success_rate for x in a.episodes] == [x.mitigation_success_rate for x in b.episodes]
    assert a.aggregate.episodes == 4


def test_fresh_agents_prevent_cross_episode_state_leakage():
    run = run_experiment(
        experiment_id="fresh-agents",
        template_ids=("web_exploit_lateral_exfil",),
        seeds=(1, 2, 3),
        red_agent_factory=ScriptedRedAgent,
        blue_agent_factory=ScriptedBlueAgent,
    )
    assert len(run.episodes) == 3


def test_aggregate_rejects_empty_results():
    import pytest
    with pytest.raises(ValueError):
        aggregate_metrics([])
