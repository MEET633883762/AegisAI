"""Paired, offline regression evidence for two observation-only defender policies.

The evaluator may inspect simulator ground truth; neither policy receives it.
No model, network target, application database, or stored episode is involved.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict
import hashlib
import json
from pathlib import Path

from agents.blue.evidence_prioritized import EvidencePrioritizedBlueAgent
from agents.blue.scripted import ScriptedBlueAgent
from agents.red.scripted import ScriptedRedAgent
from environment.actions import BlueActionType
from environment.scenarios import TEMPLATES
from evaluation.experiments.runner import EpisodeRun, run_episode
from evaluation.metrics.core import RESPONSE_ACTIONS

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SEEDS = (1, 2, 7, 9, 17)
MAX_PAIRS = 120
SOURCE_FILES = (
    "agents/blue/scripted.py", "agents/blue/evidence_prioritized.py", "agents/red/scripted.py",
    "controller/orchestrator.py", "controller/episode_manager.py", "controller/policy.py",
    "controller/validator.py", "controller/permissions.py",
    "environment/scenarios.py", "environment/simulator.py", "environment/network.py",
    "environment/state.py", "environment/actions.py", "environment/hosts.py", "environment/services.py",
    "telemetry/events.py", "telemetry/observation_builder.py", "telemetry/logger.py",
    "xai/trace.py", "xai/logger.py", "evaluation/metrics/core.py",
    "evaluation/experiments/runner.py", "evaluation/experiments/defender_benchmark.py",
)


def report_json(report: dict) -> str:
    return json.dumps(report, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False) + "\n"


def _digest(value) -> str:
    return hashlib.sha256(report_json(value).encode("utf-8")).hexdigest()


def _episode_evidence(run: EpisodeRun) -> dict:
    controller = run.controller
    audit = controller.audit_log()
    events = controller.telemetry_log().events()
    traces = {trace.trace_id: trace for trace in controller.xai_log().traces()}
    responses = []
    for record in audit:
        if record.role.value != "blue" or record.action_type not in RESPONSE_ACTIONS:
            continue
        trace = traces[record.sequence]
        responses.append({
            "sequence": record.sequence, "step": record.step, "action": record.action_type,
            "target": record.target, "authorized": record.authorized, "success": record.success,
            "outcome": record.outcome, "rationale": trace.rationale,
            "supporting_alerts": [alert for alert in trace.observation["alerts"]
                                  if alert["host"] == record.target and alert["investigated"]],
        })
    isolations = [r for r in audit if r.role.value == "blue"
                  and r.action_type == BlueActionType.ISOLATE_HOST.value and r.authorized and r.success]
    unsupported = sum(not any(event.actor == "red" and event.host == isolation.target
                             and event.step <= isolation.step for event in events)
                      for isolation in isolations)
    metrics = asdict(run.metrics)
    # Timing and generated UUID/timestamps are intentionally excluded from the
    # reproducibility contract. These are outcome comparisons, not speed claims.
    metrics.pop("decision_latency_ms")
    return {
        "metrics": metrics,
        "actions": dict(sorted(Counter(r.action_type for r in audit if r.role.value == "blue").items())),
        "successful_isolations": len(isolations),
        "isolations_without_prior_red_activity": unsupported,
        "isolated_hosts_at_end": sorted(host.id for host in controller.blue_observation().hosts
                                        if host.status == "isolated"),
        "first_successful_response_step": min((r.step for r in audit if r.role.value == "blue"
                                               and r.action_type in RESPONSE_ACTIONS and r.authorized
                                               and r.success), default=None),
        "response_records": responses,
        "audit_sha256": _digest([r.model_dump(mode="json", exclude={"timestamp"}) for r in audit]),
        "telemetry_sha256": _digest([event.model_dump(mode="json") for event in events]),
    }


def _summarize(rows: list[dict]) -> dict:
    total = len(rows)
    objectives = sum(row["metrics"]["attack_success"] for row in rows)
    return {
        "episodes": total, "attacker_objectives_reached": objectives,
        "attacker_objectives_not_reached": total - objectives,
        "attack_success_rate": objectives / total,
        "successful_isolations": sum(row["successful_isolations"] for row in rows),
        "isolations_without_prior_red_activity": sum(row["isolations_without_prior_red_activity"] for row in rows),
        "mean_isolated_hosts_at_end": sum(len(row["isolated_hosts_at_end"]) for row in rows) / total,
    }


def build_benchmark(*, template_ids: tuple[str, ...] | None = None,
                    seeds: tuple[int, ...] = DEFAULT_SEEDS) -> dict:
    templates = tuple(sorted(TEMPLATES)) if template_ids is None else tuple(template_ids)
    seeds = tuple(seeds)
    if not templates or not seeds:
        raise ValueError("at least one template and seed are required")
    if len(templates) != len(set(templates)) or len(seeds) != len(set(seeds)):
        raise ValueError("duplicate templates or seeds would inflate the paired results")
    if any(template not in TEMPLATES for template in templates):
        raise ValueError("unknown scenario template")
    if any(type(seed) is not int or not 0 <= seed <= 2**31 - 1 for seed in seeds):
        raise ValueError("seeds must be integers between 0 and 2147483647")
    if len(templates) * len(seeds) > MAX_PAIRS:
        raise ValueError(f"benchmark is bounded to {MAX_PAIRS} scenario/seed pairs")
    pairs = []
    for template in sorted(templates):
        for seed in sorted(seeds):
            # Both runs rebuild the same initial world and create fresh policies.
            baseline = _episode_evidence(run_episode(template, seed, ScriptedRedAgent(), ScriptedBlueAgent()))
            candidate = _episode_evidence(run_episode(template, seed, ScriptedRedAgent(), EvidencePrioritizedBlueAgent()))
            before, after = baseline["metrics"]["attack_success"], candidate["metrics"]["attack_success"]
            outcome = "improved" if before and not after else "regressed" if after and not before else "unchanged"
            pairs.append({"scenario_id": f"{template}:{seed}", "template_id": template,
                          "seed": seed, "paired_outcome": outcome, "baseline": baseline, "candidate": candidate})
    outcomes = Counter(pair["paired_outcome"] for pair in pairs)
    sources = {name: hashlib.sha256((ROOT / name).read_text(encoding="utf-8").replace("\r\n", "\n").encode("utf-8")).hexdigest()
               for name in SOURCE_FILES}
    return {
        "schema_version": "1.0", "artifact_type": "aegisai_synthetic_defender_benchmark",
        "protocol": {
            "synthetic": True, "offline": True, "learned_policy": False,
            "evaluation_kind": "development regression comparison; not independent held-out evaluation",
            "templates": sorted(templates), "seeds": sorted(seeds), "pairs": len(pairs),
            "red_policy": "ScriptedRedAgent", "baseline_policy": "ScriptedBlueAgent",
            "candidate_policy": "EvidencePrioritizedBlueAgent", "fresh_agents_per_episode": True,
            "primary_outcome": "simulator-recorded Red data-exfiltration objective, paired by template and seed",
            "availability_proxy": "number of isolated hosts in the final observation; no business-availability model",
            "source_sha256": sources,
        },
        "summary": {
            "baseline": _summarize([p["baseline"] for p in pairs]),
            "candidate": _summarize([p["candidate"] for p in pairs]),
            "improved_pairs": outcomes["improved"], "regressed_pairs": outcomes["regressed"],
            "unchanged_pairs": outcomes["unchanged"],
        },
        "per_template": [{"template_id": template,
                          "baseline": _summarize([p["baseline"] for p in pairs if p["template_id"] == template]),
                          "candidate": _summarize([p["candidate"] for p in pairs if p["template_id"] == template])}
                         for template in sorted(templates)],
        "pairs": pairs,
        "limitations": [
            "Small authored simulator suite with shared attack-path structure; not real-world efficacy or independent generalization evidence.",
            "Both policies and the attacker are deterministic rules; this does not measure LLM performance or learned adaptation.",
            "Not reaching the objective can reflect the fixed step budget or restricted paths; unchanged failures are not credited as candidate improvements.",
            "Isolation reduces simulated availability and has no automatic restoration; the final isolated-host count is reported as a tradeoff.",
            "Alert-based detection and mitigation metrics have policy-dependent denominators; the primary comparison uses paired objective outcomes.",
            "Source fingerprints normalize line endings; wall-clock timings, trace timestamps, and generated episode UUIDs are omitted.",
        ],
    }
