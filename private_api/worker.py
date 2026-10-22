"""One bounded telemetry worker process; invoked only by the local scheduler."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from private_api.store import SQLiteStore
from private_api.telemetry import read_telemetry_file


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--tenant", required=True)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args(argv)
    try:
        batch = read_telemetry_file(args.fixture)
        store = SQLiteStore(args.database)
        store.complete_telemetry_cycle(
            run_id=args.run_id, tenant_id=args.tenant, source_id=batch.source_id, batch=batch,
        )
    except Exception:
        # The parent records a categorical worker failure; do not print fixture or DB details.
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
