"""Serializable research experiment report."""
from __future__ import annotations

import json
from dataclasses import asdict
from evaluation.experiments.research import ComparisonResult


def comparison_to_dict(result: ComparisonResult) -> dict:
    def agg(run):
        return {
            "experiment_id": run.experiment_id,
            "episodes": run.aggregate.episodes,
            "attack_success_rate": run.aggregate.attack_success_rate,
            "detection_rate": run.aggregate.detection_rate,
            "mean_detection_time": run.aggregate.mean_detection_time,
            "mitigation_success_rate": run.aggregate.mitigation_success_rate,
            "false_positive_rate": run.aggregate.false_positive_rate,
            "mean_decision_latency_ms": run.aggregate.mean_decision_latency_ms,
        }
    return {
        "config_A_scripted_baseline": agg(result.baseline),
        "config_B_llm_without_memory": agg(result.no_memory),
        "config_C_llm_with_adaptive_memory": agg(result.adaptive),
        "adaptation_improvement": result.adaptation_improvement,
        "generalization_improvement": result.generalization_improvement,
        "manifest_fingerprints": list(result.manifest_fingerprints),
    }


def to_json(result: ComparisonResult) -> str:
    return json.dumps(comparison_to_dict(result), indent=2, sort_keys=True)
