"""Preview or explicitly authorize a fixed synthetic local website scenario."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from private_api.store import SQLiteStore
from purple_team.catalog import SCENARIOS
from purple_team.policy import APPROVED_ORIGIN
from purple_team.runner import LocalPurpleTeamRunner

DEFAULT_DATABASE = ROOT / ".aegisai-local" / "private_api.sqlite3"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", choices=sorted(SCENARIOS), help="fixed catalog scenario to preview or run")
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE,
                        help="local tenant-scoped SQLite store; used only during execution")
    parser.add_argument("--execute-synthetic", action="store_true",
                        help="execute the selected reviewed scenario against the fixed loopback site")
    parser.add_argument("--authorize-synthetic-execution", action="store_true",
                        help="explicitly authorize this harmless synthetic local scenario")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.execute_synthetic and not args.scenario:
        parser.error("--scenario is required with --execute-synthetic")
    if not args.execute_synthetic:
        output = LocalPurpleTeamRunner.preview(args.scenario)
        print(json.dumps({"target_origin": APPROVED_ORIGIN, "preview": output}, indent=2))
        return 0
    runner = LocalPurpleTeamRunner(SQLiteStore(args.database))
    report = runner.run(args.scenario, explicitly_authorized=args.authorize_synthetic_execution)
    print(report.model_dump_json(indent=2))
    return 0 if report.status in {"PASSED", "NOT_RUN", "NOT_APPLICABLE"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
