"""One bounded telemetry worker process; invoked only by the local scheduler."""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from private_api.store import SQLiteStore
from private_api.telemetry import TelemetryConflictError, read_telemetry_file

EXIT_OK = 0
EXIT_SOURCE_INVALID = 2
EXIT_STORE_ERROR = 3
EXIT_PROCESSING_ERROR = 4
EXIT_EVENT_CONFLICT = 5
EXIT_MODEL_VALIDATION_ERROR = 6
EXIT_STATE_ERROR = 7


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--tenant", required=True)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args(argv)
    try:
        batch = read_telemetry_file(args.fixture)
    except Exception:
        # Return only a fixed category; never send input contents to stderr.
        return EXIT_SOURCE_INVALID
    try:
        store = SQLiteStore(args.database)
    except Exception:
        return EXIT_STORE_ERROR
    try:
        store.complete_telemetry_cycle(
            run_id=args.run_id, tenant_id=args.tenant, source_id=batch.source_id, batch=batch,
        )
    except sqlite3.Error:
        return EXIT_STORE_ERROR
    except TelemetryConflictError:
        return EXIT_EVENT_CONFLICT
    except ValidationError:
        return EXIT_MODEL_VALIDATION_ERROR
    except ValueError:
        return EXIT_STATE_ERROR
    except Exception:
        return EXIT_PROCESSING_ERROR
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
