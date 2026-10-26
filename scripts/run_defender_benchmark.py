"""Compare defensive policies on matched synthetic episodes, including disruption cost."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evaluation.experiments.defender_benchmark import DEFAULT_SEEDS, build_benchmark, report_json


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", nargs="+", type=int, default=DEFAULT_SEEDS)
    parser.add_argument("--templates", nargs="+", default=None)
    output = parser.add_mutually_exclusive_group()
    output.add_argument("--stdout", action="store_true", help="print the JSON report without writing files")
    output.add_argument("--output", type=Path, help="write to a new file; never overwrite existing evidence")
    args = parser.parse_args(argv)
    try:
        report = build_benchmark(template_ids=None if args.templates is None else tuple(args.templates), seeds=tuple(args.seeds))
        content = report_json(report)
        if args.stdout:
            sys.stdout.write(content)
            return 0
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        path = args.output or ROOT / ".aegisai-local" / "benchmarks" / f"defender-{stamp}-{uuid4().hex[:8]}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8", newline="\n") as destination:
            destination.write(content)
    except (OSError, ValueError, RuntimeError) as error:
        print(f"Defender benchmark failed: {error}", file=sys.stderr)
        return 1
    summary = report["summary"]
    total = report["protocol"]["pairs"]
    print(f"AEGISAI | PAIRED SYNTHETIC DEFENDER BENCHMARK ({total} matched pairs)")
    print("Same scenarios, seeds, attacker and Controller; fresh defender in each run.")
    for key in ("baseline", "candidate"):
        row = summary[key]
        print(f"{key.title()}: attacker objective reached {row['attacker_objectives_reached']}/{total}; "
              f"mean isolated hosts at end {row['mean_isolated_hosts_at_end']:.2f}.")
    print(f"Improved: {summary['improved_pairs']}; regressed: {summary['regressed_pairs']}; unchanged: {summary['unchanged_pairs']}.")
    print("Isolation has an availability cost. These authored regression cases do not establish real-world effectiveness.")
    print(f"Evidence: {path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
