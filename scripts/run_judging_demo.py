"""Prepare a fresh, reproducible offline demo packet without keys or network access.

This command exercises the real Controller and detector with fixed synthetic
inputs. It never starts a server, modifies published samples, or opens the
application database. Each preparation creates a new ignored local directory.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from platform_prototype.evaluation import evaluate_dataset, report_json
from platform_prototype.evaluation_dataset import (
    MAX_EVALUATION_DATASET_BYTES,
    load_evaluation_dataset_bytes,
)
from scripts.build_public_demo_artifact import build_artifact

DATASET_PATH = ROOT / "platform_prototype" / "fixtures" / "evaluation_dataset_v1.json"
PUBLISHED_EPISODE_PATH = ROOT / "frontend" / "data" / "public_demo_episode.json"
OUTPUT_ROOT = ROOT / ".aegisai-local" / "judging-demo"


def _canonical_json(value: dict) -> str:
    return json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + "\n"


def _fingerprint(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def run_checks() -> tuple[dict, str, dict]:
    """Run offline work twice and return measured results plus explicit checks."""
    episode = build_artifact()
    episode_json = _canonical_json(episode)
    second_episode_json = _canonical_json(build_artifact())
    with DATASET_PATH.open("rb") as source:
        dataset = load_evaluation_dataset_bytes(source.read(MAX_EVALUATION_DATASET_BYTES + 1))
    evaluation = evaluate_dataset(dataset)
    evaluation_json = report_json(evaluation)
    second_evaluation_json = report_json(evaluate_dataset(dataset))
    published_episode = json.loads(PUBLISHED_EPISODE_PATH.read_text(encoding="utf-8"))

    diagnostics = evaluation.scenarios + evaluation.rejected_inputs
    failed_scenarios = [row.scenario_id for row in diagnostics if row.status != "pass"]
    checks = [
        {
            "name": "Controller replay is reproducible",
            "passed": episode_json == second_episode_json,
            "detail": "Two fresh runs of the fixed scripted episode produce identical exported JSON.",
        },
        {
            "name": "Published replay matches the current Controller",
            "passed": episode == published_episode,
            "detail": "The browser sample matches a freshly executed episode."
            if episode == published_episode else
            "Published sample is stale. Review and regenerate it with python scripts/build_public_demo_artifact.py.",
        },
        {
            "name": "Detection evaluation is reproducible",
            "passed": evaluation_json == second_evaluation_json,
            "detail": "Two fresh evaluations produce identical reports and configuration fingerprints.",
        },
        {
            "name": "Ground truth and evidence checks pass",
            "passed": not failed_scenarios,
            "detail": f"All {len(diagnostics)} authored scenarios match their labels and evidence requirements."
            if not failed_scenarios else "Failed scenarios: " + ", ".join(failed_scenarios),
        },
    ]
    verification = {
        "schema_version": "1.0",
        "report_type": "aegisai_offline_judging_preflight",
        "label": "SYNTHETIC OFFLINE DEMO - NOT REAL SECURITY PERFORMANCE",
        "status": "passed" if all(row["passed"] for row in checks) else "failed",
        "checks": checks,
        "episode": {
            "scenario_template": episode["provenance"]["scenario_template"],
            "seed": episode["provenance"]["seed"],
            "recorded_actions": len(episode["records"]),
            "recorded_steps": episode["provenance"]["recorded_steps"],
            "sha256": _fingerprint(episode_json),
        },
        "evaluation": {
            "accepted_scenarios": evaluation.valid_scenario_count,
            "rejected_scenarios": evaluation.rejected_scenario_count,
            "rules": len(evaluation.per_rule),
            "counts": evaluation.counts.model_dump(mode="json"),
            "metrics": evaluation.metrics.model_dump(mode="json"),
            "counting_unit": evaluation.counting_unit,
            "evidence_summary": evaluation.evidence_summary,
            "dataset_sha256": evaluation.dataset_sha256,
            "detector_config_sha256": evaluation.detector_config_sha256,
            "sha256": _fingerprint(evaluation_json),
        },
        "limitations": [
            "The episode uses scripted policies; no real LLM is called or measured.",
            "The detection results describe a small authored synthetic dataset, not real-world accuracy.",
            "This preflight checks the offline demo core; it does not replace the full test suite or browser checks.",
            "The public dashboard replays reviewed samples and does not execute this Python code.",
        ],
    }
    return episode, evaluation_json, verification


def _browser_instructions() -> str:
    npm = "npm.cmd" if sys.platform == "win32" else "npm"
    lines = ["From the repository root:"]
    if not (ROOT / "frontend" / "node_modules").is_dir():
        lines.append(f"  {npm} --prefix frontend ci  (first setup; internet required)")
    lines.extend([
        f"  {npm} --prefix frontend run dev -- --host 127.0.0.1",
        "  Open http://127.0.0.1:5174/",
        "  Replay: http://127.0.0.1:5174/dashboard.html",
        "Rehearse once before judging. After dependencies are installed, the demo works offline.",
    ])
    if shutil.which(npm) is None:
        lines.append("Node.js/npm is missing from PATH; install it before running the browser demo.")
    return "\n".join(lines)


def write_packet(episode: dict, evaluation_json: str, verification: dict) -> Path:
    """Create a new local packet; previous demo results are never overwritten."""
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    prefix = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-")
    output = Path(tempfile.mkdtemp(prefix=prefix, dir=OUTPUT_ROOT))
    (output / "episode.json").write_text(_canonical_json(episode), encoding="utf-8", newline="\n")
    (output / "detection-evaluation.json").write_text(evaluation_json, encoding="utf-8", newline="\n")
    (output / "verification.json").write_text(_canonical_json(verification), encoding="utf-8", newline="\n")
    (output / "guide.txt").write_text(
        "AEGISAI OFFLINE JUDGING DEMO\n\n"
        "These files were freshly generated from the checked-in synthetic fixtures.\n"
        "verification.json records reproducibility, ground-truth and published-sample checks.\n"
        "The browser uses the published samples; this packet is independent verification evidence.\n\n"
        + _browser_instructions() + "\n\n"
        + "\n".join(verification["limitations"]) + "\n",
        encoding="utf-8", newline="\n",
    )
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="run checks without writing a demo packet")
    args = parser.parse_args(argv)
    try:
        episode, evaluation_json, verification = run_checks()
        output = None if args.check else write_packet(episode, evaluation_json, verification)
    except (OSError, ValueError, RuntimeError) as error:
        print(f"Offline demo preparation failed: {error}", file=sys.stderr)
        return 1

    print("AEGISAI | OFFLINE JUDGING PREFLIGHT")
    print("Synthetic inputs, scripted agents, no API keys or external network calls.\n")
    for check in verification["checks"]:
        print(f"[{'PASS' if check['passed'] else 'FAIL'}] {check['name']}")
        if not check["passed"]:
            print(f"       {check['detail']}")
    episode_summary = verification["episode"]
    evaluation_summary = verification["evaluation"]
    counts = evaluation_summary["counts"]
    print(f"\nReplay: {episode_summary['recorded_actions']} actions across {episode_summary['recorded_steps']} steps.")
    print(
        f"Evaluation: {evaluation_summary['accepted_scenarios']} accepted + "
        f"{evaluation_summary['rejected_scenarios']} rejected synthetic scenarios; "
        f"{evaluation_summary['rules']} rules."
    )
    print(
        f"Scenario/rule counts: TP={counts['true_positives']}, FP={counts['false_positives']}, "
        f"TN={counts['true_negatives']}, FN={counts['false_negatives']}."
    )
    print("These small synthetic results do not establish real-world accuracy.")
    if output is not None:
        print(f"\nFresh evidence packet: {output}")
    print("\n" + _browser_instructions())
    return 0 if verification["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
