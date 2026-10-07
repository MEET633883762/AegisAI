"""Run one explicitly requested real-LLM AegisAI episode.

Safety: this script refuses to make provider calls unless --live is supplied. The LLM still
only proposes typed actions; the Controller executes/authorizes them inside the simulator.
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
from evaluation.live.runner import run_live_episode
from llm.openai_provider import OpenAIResponsesProvider


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="explicitly permit an API call")
    parser.add_argument("--template", default="web_exploit_lateral_exfil")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--model", default=os.getenv("OPENAI_MODEL", ""), help="provider model name (or set OPENAI_MODEL)")
    parser.add_argument("--max-calls", type=int, default=40)
    parser.add_argument("--max-tokens", type=int, default=20_000)
    parser.add_argument("--max-steps", type=int, default=30)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--wall-seconds", type=float, default=300.0)
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

    result = run_live_episode(args.template, args.seed, config, provider_factory)
    print(json.dumps({
        "status": result.status,
        "episode_id": result.episode_id,
        "metrics": result.metrics.model_dump() if hasattr(result.metrics, "model_dump") else result.metrics.__dict__,
        "provider_usage": result.provider_usage.__dict__,
        "error": result.error,
    }, indent=2, default=str))
    return 0 if result.status == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
