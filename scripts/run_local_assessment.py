"""Run the bounded, read-only assessment against the fixed loopback test site."""

from __future__ import annotations

import json
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from local_assessment.runner import LocalAssessmentRunner
from private_api.store import SQLiteStore


DEFAULT_DATABASE = ROOT / ".aegisai-local" / "private_api.sqlite3"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database", type=Path, default=DEFAULT_DATABASE,
        help="local SQLite file for the tenant-scoped assessment report",
    )
    args = parser.parse_args(argv)
    report = LocalAssessmentRunner().run_and_store(SQLiteStore(args.database))
    print(json.dumps(report.model_dump(mode="json"), indent=2))
    complete = all(
        observation.decision.allowed and observation.error_category is None
        and observation.outcome not in {"denied", "not_run_deadline", "response_too_large", "redirect_denied_out_of_scope"}
        and observation.facts.get("status_matches_expectation", True)
        for observation in report.raw_observations
    )
    return 0 if complete else 1


if __name__ == "__main__":
    raise SystemExit(main())
