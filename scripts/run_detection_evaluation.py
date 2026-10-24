"""Evaluate the fixed Phase 6A synthetic dataset without touching application storage."""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from platform_prototype.evaluation import evaluate_dataset, report_json
from platform_prototype.evaluation_history import record_evaluation_run
from platform_prototype.evaluation_dataset import (
    MAX_EVALUATION_DATASET_BYTES,
    load_evaluation_dataset_bytes,
)

DATASET_PATH = ROOT / "platform_prototype" / "fixtures" / "evaluation_dataset_v1.json"
DEFAULT_REPORT_PATH = ROOT / "results" / "evaluation" / "phase6b_detection_evaluation_v1.json"
DEFAULT_HISTORY_PATH = ROOT / ".aegisai-local" / "detection_evaluation_history.sqlite3"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--stdout", action="store_true",
        help="print the deterministic report instead of creating the default report file",
    )
    parser.add_argument(
        "--record-history", action="store_true",
        help="append this run to the bounded local evaluation history (independent of the application database)",
    )
    args = parser.parse_args(argv)
    try:
        with DATASET_PATH.open("rb") as source:
            raw_dataset = source.read(MAX_EVALUATION_DATASET_BYTES + 1)
        dataset = load_evaluation_dataset_bytes(raw_dataset)
        report = evaluate_dataset(dataset)
        output = report_json(report)
        if args.record_history:
            run = record_evaluation_run(DEFAULT_HISTORY_PATH, report)
            if args.stdout:
                sys.stdout.write(output)
            else:
                print(f"Recorded synthetic evaluation run {run.run_id} in bounded local history")
        elif args.stdout:
            sys.stdout.write(output)
        else:
            DEFAULT_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
            with DEFAULT_REPORT_PATH.open("x", encoding="utf-8", newline="\n") as destination:
                destination.write(output)
            print(f"Wrote deterministic synthetic evaluation report to {DEFAULT_REPORT_PATH}")
        return 0
    except FileExistsError:
        print("evaluation report already exists; it was not overwritten", file=sys.stderr)
        return 2
    except (OSError, ValueError, sqlite3.Error) as exc:
        print(f"evaluation failed: {exc.__class__.__name__}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
