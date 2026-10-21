"""Build the reviewed, static single-episode research demo artifact.

This is a maintainer-side offline export helper. It runs existing deterministic
scripted agents through the existing Controller; the public website only fetches
the resulting committed JSON and never imports or executes this Python code.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
OUTPUT = ROOT / "frontend" / "data" / "public_demo_episode.json"
SCENARIO_TEMPLATE = "credential_reuse_known_vuln"
SCENARIO_SEED = 1
ARTIFACT_SCHEMA_VERSION = "1.0"


def build_artifact() -> dict:
    from agents.blue.scripted import ScriptedBlueAgent
    from agents.red.scripted import ScriptedRedAgent
    from controller.orchestrator import Controller
    from environment.scenarios import build_scenario
    from evaluation.metrics.core import calculate_episode_metrics
    from controller.validator import validate_blue_action, validate_red_action

    scenario = build_scenario(SCENARIO_TEMPLATE, SCENARIO_SEED)
    controller = Controller(scenario, episode_id="public-demo-credential-reuse-seed-1")
    red_agent = ScriptedRedAgent()
    blue_agent = ScriptedBlueAgent()
    records: list[dict] = []

    def record_action(role: str, action, validator, submit) -> None:
        validation = validator(action)
        result = submit(action)
        audit = controller.audit_log()[-1]
        trace = controller.xai_log().trace(audit.sequence)
        if trace is None:
            raise RuntimeError("Controller did not produce its structured decision trace")
        if audit.role.value != role or trace.role.value != role:
            raise RuntimeError("Controller audit and XAI role did not match the submitted action")

        evidence = [item.model_dump(mode="json") for item in trace.evidence]
        expected_source = f"{role}_observation"
        if any(item["source"] != expected_source for item in evidence):
            raise RuntimeError("Role-scoped evidence source did not match the action role")

        records.append({
            "id": f"trace-{audit.sequence}",
            "sequence": audit.sequence,
            "step": audit.step,
            "role": role,
            "visibility_scope": role,
            "validation": {"accepted": validation.valid, "reason": validation.reason},
            "authorization": {
                "authorized": audit.authorized,
                "policy_reason": audit.policy_reason,
            },
            "action": {
                "type": audit.action_type,
                "target": audit.target,
                "parameters": dict(audit.parameters),
                "reason_category": trace.reason_category.value,
                "expected_outcome": trace.expected_outcome,
            },
            "result": {
                "outcome": result.action_result.outcome.value,
                "success": result.action_result.success,
                "message": result.action_result.message,
            },
            # XAI evidence is copied from the role-specific pre-action observation.
            # Internal event IDs and state_changes from the audit are intentionally omitted.
            "evidence": evidence,
        })

    while not controller.done:
        red_action = red_agent.decide(controller.red_observation())
        record_action("red", red_action, validate_red_action, controller.submit_red)
        if controller.done:
            break

        blue_action = blue_agent.decide(controller.blue_observation())
        record_action("blue", blue_action, validate_blue_action, controller.submit_blue)
        if not controller.done:
            controller.advance()

    metrics_result = calculate_episode_metrics(controller)
    metrics = []
    metric_specs = (
        (
            "detection_rate", "Detected malicious alerts", metrics_result.detection_rate,
            metrics_result.detected_malicious_alerts, metrics_result.malicious_alerts,
            "alerts", "Detected malicious alerts divided by malicious alerts in this episode.",
        ),
        (
            "mitigation_success_rate", "Mitigated response-required alerts",
            metrics_result.mitigation_success_rate, metrics_result.mitigated_alerts,
            metrics_result.response_required_alerts, "alerts",
            "Alerts followed by an authorized successful mitigation divided by malicious high/critical alerts.",
        ),
    )
    for metric_id, label, value, numerator, denominator, unit, definition in metric_specs:
        if denominator:
            metrics.append({
                "id": metric_id,
                "label": label,
                "value": value,
                "numerator": numerator,
                "denominator": denominator,
                "unit": unit,
                "definition": definition,
            })

    return {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "artifact_type": "aegisai_public_research_episode",
        "labels": {
            "display": "Synthetic local research demo",
            "synthetic": True,
            "precomputed": True,
            "public_execution": False,
        },
        "provenance": {
            "episode_id": controller.episode_id,
            "scenario_id": metrics_result.scenario_id,
            "scenario_template": metrics_result.template_id,
            "seed": metrics_result.seed,
            "research_split": "training sample (experiment split: credential_reuse_known_vuln seed 1)",
            "red_policy": "ScriptedRedAgent",
            "blue_policy": "ScriptedBlueAgent",
            "generator": "scripts/build_public_demo_artifact.py",
            "generation_mode": "one offline deterministic simulator episode through Controller",
            "recorded_steps": len({record["step"] for record in records}),
        },
        "objective_result": {
            "achieved": metrics_result.attack_success,
            "definition": "True only when the simulator records a Red DATA_EXFILTRATION event.",
            "episode_count": 1,
        },
        "metrics": metrics,
        "records": records,
        "limitations": [
            "One deterministic synthetic episode with scripted policies; it is not representative evidence of real-world security effectiveness.",
            "The scenario/seed is a training sample from the experiment split, not held-out evaluation evidence.",
            "Decision latency was not collected for this export and is omitted.",
            "Evidence is limited to the role-specific pre-action observations recorded by the XAI trace.",
            "This public page replays static JSON and does not run the simulator or perform network activity.",
        ],
    }


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    artifact = build_artifact()
    OUTPUT.write_text(json.dumps(artifact, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT.relative_to(ROOT)} with {len(artifact['records'])} recorded actions")


if __name__ == "__main__":
    main()
