"""Run an offline preflight for AegisAI's controlled live LLM path."""
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
from evaluation.live.preflight import run_preflight


def main() -> int:
    parser = argparse.ArgumentParser(description="Offline AegisAI live-LLM preflight")
    parser.add_argument("--model", default=os.getenv("OPENAI_MODEL", ""))
    args = parser.parse_args()
    if not args.model.strip():
        print(json.dumps({"ready_for_live_call": False, "error": "OPENAI_MODEL is not configured"}, indent=2))
        return 2

    config = LiveExperimentConfig(model=args.model)
    result = run_preflight(config)
    print(json.dumps({
        "ready_for_live_call": result.ready_for_live_call,
        "api_key_configured": result.api_key_configured,
        "model_configured": result.model_configured,
        "openai_sdk_installed": result.openai_sdk_installed,
        "openai_sdk_version": result.openai_sdk_version,
        "config_valid": result.config_valid,
    }, indent=2))
    return 0 if result.ready_for_live_call else 2


if __name__ == "__main__":
    raise SystemExit(main())
