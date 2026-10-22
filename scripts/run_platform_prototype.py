"""Run the local, synthetic-only AegisAI operations prototype."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from platform_prototype.models import ActionRequest
from platform_prototype.pipeline import PrototypeInputError, read_batch_file, report_json, build_report

DEFAULT_FIXTURE = ROOT / "platform_prototype" / "fixtures" / "synthetic_events_v1.json"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Analyze a labeled synthetic event fixture locally.")
    parser.add_argument("--input", type=Path, default=DEFAULT_FIXTURE, help="synthetic event JSON (max 1 MiB)")
    parser.add_argument("--report", type=Path, help="write JSON report to a new file; existing files are not overwritten")
    parser.add_argument(
        "--simulate-action", nargs=2, action="append", metavar=("ACTION", "FINDING_ID"), default=[],
        help="request a policy-checked simulation (allowlist: increase_monitoring, create_review_task)",
    )
    parser.add_argument(
        "--confirm-simulation", action="store_true",
        help="explicitly confirm that requested outcomes are simulations and never execute system actions",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.simulate_action and not args.confirm_simulation:
        parser.error("--simulate-action requires --confirm-simulation")
    if args.confirm_simulation and not args.simulate_action:
        parser.error("--confirm-simulation requires at least one --simulate-action")

    try:
        batch = read_batch_file(args.input)
        requests = [ActionRequest(action_type=action, finding_id=finding) for action, finding in args.simulate_action]
        report = build_report(batch, actions=requests)
        content = report_json(report)
        if args.report:
            with args.report.open("x", encoding="utf-8", newline="\n") as destination:
                destination.write(content)
        else:
            sys.stdout.write(content)
    except PrototypeInputError as exc:
        print(f"input rejected: {exc}", file=sys.stderr)
        return 2
    except FileExistsError:
        print("report output already exists; choose a new path", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"report output failed: {exc.__class__.__name__}", file=sys.stderr)
        return 2
    except Exception as exc:
        # Keep unexpected errors concise without printing fixture contents.
        print(f"prototype failed: {exc.__class__.__name__}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
