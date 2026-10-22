"""Replay the fixed reviewed synthetic scenario library and print its evaluation report."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from platform_prototype.replay import evaluate_scenario_library, read_scenario_library, report_json

DEFAULT_LIBRARY = ROOT / "platform_prototype" / "fixtures" / "replay_scenarios_v1.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, help="write JSON to a new path; existing files are never overwritten")
    args = parser.parse_args(argv)
    try:
        library = read_scenario_library(DEFAULT_LIBRARY)
        output = report_json(evaluate_scenario_library(library))
        if args.report:
            with args.report.open("x", encoding="utf-8", newline="\n") as destination:
                destination.write(output)
            print(f"Wrote synthetic detection-gap report to {args.report}")
        else:
            sys.stdout.write(output)
        return 0
    except FileExistsError:
        print("report output already exists; choose a new path", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"replay failed: {exc.__class__.__name__}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
