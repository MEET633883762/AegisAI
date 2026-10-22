"""Ingest the fixed synthetic local website log sample into local SQLite."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from private_api.store import SQLiteStore
from private_api.website_ingestion import DEFAULT_DATABASE, ingest_local_website_sample


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)
    try:
        report = ingest_local_website_sample(SQLiteStore(DEFAULT_DATABASE))
    except Exception as exc:
        print(f"local website telemetry ingestion failed: {exc.__class__.__name__}", file=sys.stderr)
        return 2
    sys.stdout.write(report.model_dump_json(indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
