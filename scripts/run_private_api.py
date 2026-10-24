"""Start AegisAI's loopback-only API over synthetic fixture data."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from platform_prototype.pipeline import build_report, read_batch_file
from private_api.auth import DEFAULT_READ_SCOPES, LocalTokenRegistry
from private_api.scheduler import LocalTelemetryScheduler
from private_api.server import ApiApplication, create_local_server
from private_api.store import SQLiteStore

DEFAULT_FIXTURE = ROOT / "platform_prototype" / "fixtures" / "synthetic_events_v1.json"
DEFAULT_TELEMETRY_FIXTURE = ROOT / "platform_prototype" / "fixtures" / "synthetic_telemetry_v1.json"
DEFAULT_DATABASE = ROOT / ".aegisai-local" / "private_api.sqlite3"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the loopback local synthetic API.")
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE,
                        help="local SQLite file (synthetic records only)")
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE,
                        help="Phase 1 schema-validated synthetic event JSON")
    parser.add_argument("--tenant", action="append", default=None,
                        help="synthetic tenant to bootstrap; repeat for more than one")
    parser.add_argument("--port", type=int, default=8766, help="loopback port (default: 8766)")
    parser.add_argument("--token-ttl-seconds", type=int, default=8 * 60 * 60,
                        help="development token lifetime, 1 to 86400 seconds")
    parser.add_argument("--enable-investigation-writes", action="store_true",
                        help="grant the local token scoped case and analyst-note write permission")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    runtime_mode = os.environ.get("AEGISAI_ENV", "local").strip().lower()
    if runtime_mode not in {"local", "development"}:
        print("startup failed: unsupported_runtime_mode", file=sys.stderr)
        return 2
    tenant_ids = args.tenant or ["synthetic-org-demo"]
    if len(tenant_ids) != len(set(tenant_ids)):
        parser.error("tenant IDs must be unique")
    if not 1 <= len(tenant_ids) <= 5:
        parser.error("use between one and five local synthetic tenants")
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")
    try:
        batch = read_batch_file(args.fixture)
        report = build_report(batch)
        tokens = LocalTokenRegistry()
        token_scopes = DEFAULT_READ_SCOPES | ({"investigations:write"} if args.enable_investigation_writes else set())
        issued: list[tuple[str, str]] = []
        for tenant_id in tenant_ids:
            issued.append((tenant_id, tokens.issue_development_token(
                tenant_id, scopes=frozenset(token_scopes), ttl_seconds=args.token_ttl_seconds,
            )))
        store = SQLiteStore(args.database)
        for tenant_id, _ in issued:
            store.seed_tenant(tenant_id, report)
        scheduler = LocalTelemetryScheduler(
            database=args.database, fixture=DEFAULT_TELEMETRY_FIXTURE, tenant_ids=tenant_ids, store=store,
        )
        server = create_local_server(
            ApiApplication(store, tokens, scheduler_status=lambda: scheduler.state), port=args.port,
        )
    except Exception as exc:
        print(f"startup failed: {exc.__class__.__name__}", file=sys.stderr)
        return 2

    print(f"AegisAI local synthetic API listening at http://127.0.0.1:{server.server_address[1]}")
    print("Synthetic fixture data only. No client systems, external targets, or response actions are connected.")
    if scheduler.start():
        print("Local telemetry scheduler started: immediate bounded run, then every 600 seconds.")
    else:
        print("A scheduler already owns this local database; this API instance will not start another.")
    for tenant_id, token in issued:
        print(f"Development bearer token for {tenant_id} (expires in {args.token_ttl_seconds}s): {token}")
    print("Treat these startup tokens as secrets; they are never written to the database or audit log.")
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        print("Stopping local API.")
    finally:
        scheduler.stop()
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
