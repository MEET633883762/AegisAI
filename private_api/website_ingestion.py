"""Internal local-only operation for the one approved synthetic website log sample."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

from platform_prototype.pipeline import build_report, read_batch_file
from private_api.store import SQLiteStore
from private_api.telemetry import TelemetryReport
from private_api.website_connector import (
    SOURCE_ID,
    WebsiteLogInputError,
    read_website_log_fixture,
    to_telemetry_batch,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE = ROOT / ".aegisai-local" / "private_api.sqlite3"
PHASE1_FIXTURE = ROOT / "platform_prototype" / "fixtures" / "synthetic_events_v1.json"
FIXED_TENANT_ID = "synthetic-org-demo"


def ingest_local_website_sample(store: SQLiteStore) -> TelemetryReport:
    """Ingest only the fixed synthetic fixture into its fixed local synthetic tenant."""
    phase1_report = build_report(read_batch_file(PHASE1_FIXTURE))
    store.seed_tenant(FIXED_TENANT_ID, phase1_report)
    run_id = f"trun-{uuid.uuid4().hex[:16]}"
    scheduled_at = datetime.now(timezone.utc).isoformat()
    store.start_telemetry_run(
        run_id=run_id, tenant_id=FIXED_TENANT_ID, source_id=SOURCE_ID,
        scheduled_at_utc=scheduled_at, attempt=1,
    )
    try:
        logs = read_website_log_fixture()
        batch = to_telemetry_batch(logs)
        report = store.complete_telemetry_cycle(
            run_id=run_id, tenant_id=FIXED_TENANT_ID, source_id=SOURCE_ID, batch=batch,
        )
    except Exception as exc:
        store.fail_telemetry_run(run_id, "source_invalid" if isinstance(exc, WebsiteLogInputError) else "processing_error")
        store.record_audit(
            tenant_id=FIXED_TENANT_ID, event_type="protected_operation", method="CLI",
            route="website_telemetry.ingest", outcome="failed",
            details_code="source_invalid" if isinstance(exc, WebsiteLogInputError) else "processing_error",
        )
        raise RuntimeError("local synthetic website telemetry ingestion failed") from None
    store.record_audit(
        tenant_id=FIXED_TENANT_ID, event_type="protected_operation", method="CLI",
        route="website_telemetry.ingest", outcome="completed", details_code="synthetic_sample",
    )
    return report
