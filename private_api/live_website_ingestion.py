"""Internal ingestion operation for fixed loopback website logs."""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone

from private_api.store import SQLiteStore
from private_api.telemetry import TelemetryReport
from private_api.website_connector import WebsiteLogInputError
from private_api.live_website_connector import read_live_website_log_snapshot
from private_api.website_ingestion import FIXED_TENANT_ID
from platform_prototype.pipeline import build_report, read_batch_file
from private_api.website_ingestion import PHASE1_FIXTURE


def ingest_live_local_website_logs(store: SQLiteStore) -> TelemetryReport:
    """Read the fixed loopback log paths and persist only under the fixed synthetic tenant."""
    store.seed_tenant(FIXED_TENANT_ID, build_report(read_batch_file(PHASE1_FIXTURE)))
    run_id = f"trun-{uuid.uuid4().hex[:16]}"
    scheduled_at = datetime.now(timezone.utc).isoformat()
    source_id = "local_synthetic_fixture_v1"
    store.start_telemetry_run(
        run_id=run_id, tenant_id=FIXED_TENANT_ID, source_id=source_id,
        scheduled_at_utc=scheduled_at, attempt=1,
    )
    store.start_live_source_attempt(FIXED_TENANT_ID)
    snapshot = None
    try:
        snapshot = read_live_website_log_snapshot()
        report = store.complete_telemetry_cycle(
            run_id=run_id, tenant_id=FIXED_TENANT_ID, source_id=source_id, batch=snapshot.batch,
            live_source_position_sha256=snapshot.position_sha256,
            live_source_position_bytes=snapshot.position_bytes,
        )
    except Exception as exc:
        if isinstance(exc, WebsiteLogInputError):
            code = "source_invalid"
        elif isinstance(exc, sqlite3.Error):
            code = "store_error"
        else:
            code = "processing_error"
        store.fail_telemetry_run(run_id, code)
        store.finish_live_source_attempt(
            FIXED_TENANT_ID, status="failed", rejected_count=1 if code == "source_invalid" else 0,
            position_sha256=snapshot.position_sha256 if snapshot else None,
            position_bytes=snapshot.position_bytes if snapshot else 0, error_code=code,
        )
        store.record_audit(
            tenant_id=FIXED_TENANT_ID, event_type="protected_operation", method="CLI",
            route="live_website_telemetry.ingest", outcome="failed", details_code=code,
        )
        raise RuntimeError("live local website telemetry ingestion failed") from None
    store.record_audit(
        tenant_id=FIXED_TENANT_ID, event_type="protected_operation", method="CLI",
        route="live_website_telemetry.ingest", outcome="completed", details_code="loopback_log_sample",
    )
    return report
