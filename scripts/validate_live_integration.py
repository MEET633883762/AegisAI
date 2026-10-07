"""Run one tightly bounded real-LLM integration validation.

This is an integration check, not a research experiment. It refuses to run unless
--live is supplied and the Phase 18 offline preflight succeeds.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evaluation.live.config import LiveExperimentConfig
from evaluation.live.validation import validate_single_live_episode
from llm.openai_provider import OpenAIResponsesProvider


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="explicitly permit one API-backed episode")
    parser.add_argument("--template", default="web_exploit_lateral_exfil")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--model", default=os.getenv("OPENAI_MODEL", ""))
    parser.add_argument("--max-calls", type=int, default=4)
    parser.add_argument("--max-tokens", type=int, default=2_000)
    parser.add_argument("--max-steps", type=int, default=2)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--wall-seconds", type=float, default=120.0)
    parser.add_argument("--output", type=Path, default=None, help="optional JSON artifact path")
    args = parser.parse_args()

    if not args.live:
        parser.error("refusing to call a live provider; pass --live explicitly")

    config = LiveExperimentConfig(
        model=args.model,
        max_provider_calls=args.max_calls,
        max_total_tokens=args.max_tokens,
        max_episode_steps=args.max_steps,
        timeout_seconds=args.timeout,
        max_wall_seconds=args.wall_seconds,
    )

    def provider_factory(model: str):
        return OpenAIResponsesProvider(model=model, timeout_seconds=config.timeout_seconds)

    result = validate_single_live_episode(
        args.template,
        args.seed,
        config,
        provider_factory,
        allow_live=True,
    )

    payload = {
        "validation_type": "single_live_integration",
        "research_evidence": False,
        "preflight_ready": result.preflight_ready,
        "live_attempted": result.live_attempted,
        "integration_ok": result.integration_ok,
        "status": result.status,
        "message": result.message,
    }
    if result.episode is not None:
        payload["episode"] = {
            "episode_id": result.episode.episode_id,
            "metrics": result.episode.metrics.model_dump(),
            "provider_usage": result.episode.provider_usage.__dict__,
            "error": result.episode.error,
        }

    rendered = json.dumps(payload, indent=2, default=str)
    print(rendered)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")

    return 0 if result.integration_ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
