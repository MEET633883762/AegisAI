from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from platform_prototype.pipeline import build_report, read_batch_file
from private_api.auth import LocalTokenRegistry
from private_api.server import ApiApplication
from private_api.store import SQLiteStore
from private_api.telemetry import (
    MAX_INPUT_BYTES,
    SyntheticTelemetryBatch,
    TelemetryConflictError,
    TelemetryEventType,
    TelemetryInputError,
    detect_findings,
    load_telemetry_bytes,
    normalize_and_deduplicate,
    read_telemetry_file,
)

ROOT = Path(__file__).parents[2]
TELEMETRY_FIXTURE = ROOT / "platform_prototype" / "fixtures" / "synthetic_telemetry_v1.json"
PHASE1_FIXTURE = ROOT / "platform_prototype" / "fixtures" / "synthetic_events_v1.json"
TENANT = "synthetic-org-telemetry-test"


def _batch_bytes() -> bytes:
    return TELEMETRY_FIXTURE.read_bytes()


def _start_run(store: SQLiteStore, run_id: str, source_id: str) -> None:
    store.start_telemetry_run(
        run_id=run_id, tenant_id=TENANT, source_id=source_id,
        scheduled_at_utc=datetime(2026, 10, 22, tzinfo=timezone.utc).isoformat(), attempt=1,
    )


def _seed_store(store: SQLiteStore) -> None:
    phase1 = build_report(read_batch_file(PHASE1_FIXTURE))
    store.seed_tenant(TENANT, phase1)


def test_fixture_schema_normalizes_timezone_and_deduplicates_exact_replay():
    batch = load_telemetry_bytes(_batch_bytes())
    events, duplicate_count = normalize_and_deduplicate(batch)
    assert len(batch.events) == 10
    assert len(events) == 9
    assert duplicate_count == 1
    assert all(event.occurred_at.utcoffset().total_seconds() == 0 for event in events)
    assert {event.event_type for event in events} == set(TelemetryEventType) - {
        TelemetryEventType.HTTP_ACCESS, TelemetryEventType.APPLICATION_ERROR,
    }


def test_non_utc_aware_timestamps_are_normalized_at_schema_boundary():
    payload = json.loads(_batch_bytes())
    payload["generated_at"] = "2026-10-22T12:00:00+05:30"
    payload["events"][0]["occurred_at"] = "2026-10-22T12:00:00+05:30"
    batch = SyntheticTelemetryBatch.model_validate(payload)
    assert batch.generated_at.isoformat() == "2026-10-22T06:30:00+00:00"
    assert batch.events[0].occurred_at.isoformat() == "2026-10-22T06:30:00+00:00"


@pytest.mark.parametrize("mutation", [
    lambda data: data.update(schema_version="9.0"),
    lambda data: data.update(data_classification="client"),
    lambda data: data["events"][0].update(occurred_at="2026-10-22T10:00:00"),
    lambda data: data["events"][5].pop("request_count"),
    lambda data: data["events"][6].update(activity_code="run arbitrary command"),
    lambda data: data["events"][0].update(token="synthetic-token-value"),
])
def test_malformed_or_untrusted_telemetry_is_rejected(mutation):
    payload = json.loads(_batch_bytes())
    mutation(payload)
    with pytest.raises(TelemetryInputError):
        load_telemetry_bytes(json.dumps(payload).encode())


def test_oversized_telemetry_is_rejected_before_parse():
    with pytest.raises(TelemetryInputError, match="1 MiB"):
        load_telemetry_bytes(b" " * (MAX_INPUT_BYTES + 1))


def test_conflicting_event_ids_and_ambiguous_evidence_are_rejected():
    payload = json.loads(_batch_bytes())
    payload["events"][-1]["asset_ref"] = "synthetic-altered-asset"
    with pytest.raises(TelemetryConflictError, match="conflicting content"):
        normalize_and_deduplicate(SyntheticTelemetryBatch.model_validate(payload))
    payload = json.loads(_batch_bytes())
    payload["events"][1]["evidence_ref"] = payload["events"][0]["evidence_ref"]
    with pytest.raises(TelemetryConflictError, match="multiple event IDs"):
        normalize_and_deduplicate(SyntheticTelemetryBatch.model_validate(payload))


def test_rules_cover_auth_rate_activity_vulnerability_and_configuration():
    batch = load_telemetry_bytes(_batch_bytes())
    events, _ = normalize_and_deduplicate(batch)
    findings = detect_findings(events, tenant_id=TENANT)
    assert {item.rule_id for item in findings} == {"AUTH-001", "WEB-001", "APP-001", "VULN-001", "CONFIG-001"}
    assert all(item.rule_version == "1.0" for item in findings)
    assert all(item.first_seen_utc <= item.last_seen_utc for item in findings)
    assert all(item.asset_ref.startswith("synthetic-") and item.evidence_refs for item in findings)
    assert all(item.confidence_factors and item.explanation for item in findings)
    assert next(item for item in findings if item.rule_id == "WEB-001").severity.value == "high"
    auth = next(item for item in findings if item.rule_id == "AUTH-001")
    assert auth.confidence == 0.9
    assert auth.status == "open"


def test_additive_sqlite_migration_preserves_phase2_rows_and_sets_schema_version(tmp_path):
    store = SQLiteStore(tmp_path / "private.sqlite3")
    _seed_store(store)
    before = store.list_findings(TENANT)
    # Simulate an existing version-2 database before the additive source-status migration.
    with sqlite3.connect(store.path) as connection:
        connection.execute("DROP TABLE telemetry_source_status")
        connection.execute("PRAGMA user_version = 2")
    migrated = SQLiteStore(store.path)
    after = migrated.list_findings(TENANT)
    assert [item.finding_id for item in before] == [item.finding_id for item in after]
    with sqlite3.connect(store.path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 3
        assert connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'telemetry_source_status'"
        ).fetchone()[0] == "telemetry_source_status"
        existing_tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"incidents", "findings", "audit_events", "telemetry_events", "telemetry_runs"}.issubset(existing_tables)
    with sqlite3.connect(store.path) as connection:
        connection.execute("PRAGMA user_version = 1")
    SQLiteStore(store.path)
    with sqlite3.connect(store.path) as connection:
        indexes = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='index'")}
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 3
    assert "telemetry_observations_by_finding" in indexes


def test_cycle_persists_findings_evidence_and_report_idempotently(tmp_path):
    store = SQLiteStore(tmp_path / "private.sqlite3")
    _seed_store(store)
    batch = read_telemetry_file(TELEMETRY_FIXTURE)
    _start_run(store, "trun-0000000000000001", batch.source_id)
    first = store.complete_telemetry_cycle(
        run_id="trun-0000000000000001", tenant_id=TENANT, source_id=batch.source_id, batch=batch,
    )
    assert first.accepted_event_count == 9 and first.duplicate_event_count == 1
    assert len(first.findings) == 5
    assert store.latest_telemetry_run(TENANT)["status"] == "completed"
    finding = next(item for item in first.findings if item.rule_id == "AUTH-001")
    evidence = store.list_telemetry_evidence(TENANT, finding.finding_id)
    assert len(evidence) == 5

    _start_run(store, "trun-0000000000000002", batch.source_id)
    second = store.complete_telemetry_cycle(
        run_id="trun-0000000000000002", tenant_id=TENANT, source_id=batch.source_id, batch=batch,
    )
    assert second.accepted_event_count == 0 and second.duplicate_event_count == 10
    assert {item.finding_id for item in first.findings} == {item.finding_id for item in second.findings}
    with sqlite3.connect(store.path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM telemetry_events WHERE tenant_id = ?", (TENANT,)).fetchone()[0] == 9
        assert connection.execute("SELECT COUNT(*) FROM telemetry_finding_observations WHERE tenant_id = ?", (TENANT,)).fetchone()[0] == 5
    assert store.latest_telemetry_report(TENANT).run_id == "trun-0000000000000002"


def test_retention_keeps_newest_runs_reports_and_bounded_observations(tmp_path, monkeypatch):
    import private_api.store as store_module

    monkeypatch.setattr(store_module, "MAX_RETAINED_RUNS_PER_TENANT", 2)
    monkeypatch.setattr(store_module, "MAX_RETAINED_OBSERVATIONS_PER_FINDING", 2)
    store = SQLiteStore(tmp_path / "private.sqlite3")
    _seed_store(store)
    batch = read_telemetry_file(TELEMETRY_FIXTURE)
    for index in range(1, 4):
        run_id = f"trun-{index:016d}"
        _start_run(store, run_id, batch.source_id)
        store.complete_telemetry_cycle(run_id=run_id, tenant_id=TENANT,
                                       source_id=batch.source_id, batch=batch)
    store.record_audit(tenant_id=TENANT, event_type="protected_operation", method="GET",
                       route="telemetry.findings", outcome="success", details_code="test")
    with sqlite3.connect(store.path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM telemetry_runs WHERE tenant_id = ?", (TENANT,)).fetchone()[0] == 2
        assert connection.execute("SELECT COUNT(*) FROM telemetry_reports WHERE tenant_id = ?", (TENANT,)).fetchone()[0] == 2
        newest_runs = {row[0] for row in connection.execute(
            "SELECT run_id FROM telemetry_runs WHERE tenant_id = ? ORDER BY run_id", (TENANT,)
        )}
        assert newest_runs == {"trun-0000000000000002", "trun-0000000000000003"}
        finding_id = connection.execute(
            "SELECT finding_id FROM telemetry_findings WHERE tenant_id = ? LIMIT 1", (TENANT,)
        ).fetchone()[0]
        for index in range(3):
            connection.execute(
                "INSERT INTO telemetry_finding_observations VALUES (?, ?, ?, ?, ?)",
                (TENANT, finding_id, f"manual-{index}", f"2026-10-22T00:00:0{index}+00:00", "{}"),
            )
        store._prune_telemetry_history(connection, TENANT)
        remaining = connection.execute(
            "SELECT observation_hash FROM telemetry_finding_observations WHERE tenant_id = ? AND finding_id = ?",
            (TENANT, finding_id),
        ).fetchall()
        assert len(remaining) <= 2
        assert connection.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0] == 1


def test_conflicting_replay_rolls_back_and_preserves_original_event(tmp_path):
    store = SQLiteStore(tmp_path / "private.sqlite3")
    _seed_store(store)
    batch = read_telemetry_file(TELEMETRY_FIXTURE)
    first_event = batch.events[0]
    _start_run(store, "trun-0000000000000003", batch.source_id)
    one_event_batch = batch.model_copy(update={"events": [first_event]})
    store.complete_telemetry_cycle(
        run_id="trun-0000000000000003", tenant_id=TENANT, source_id=batch.source_id, batch=one_event_batch,
    )
    changed = first_event.model_copy(update={"actor_ref": "synthetic-altered-actor"})
    _start_run(store, "trun-0000000000000004", batch.source_id)
    with pytest.raises(TelemetryConflictError):
        store.complete_telemetry_cycle(
            run_id="trun-0000000000000004", tenant_id=TENANT, source_id=batch.source_id,
            batch=batch.model_copy(update={"events": [changed]}),
        )
    store.fail_telemetry_run("trun-0000000000000004", "conflicting_event")
    with sqlite3.connect(store.path) as connection:
        original = json.loads(connection.execute(
            "SELECT event_json FROM telemetry_events WHERE tenant_id = ? AND event_id = ?",
            (TENANT, first_event.event_id),
        ).fetchone()[0])
    assert original["actor_ref"] == first_event.actor_ref
    assert store.latest_telemetry_run(TENANT)["status"] == "failed"


def test_authenticated_telemetry_api_is_read_only_and_returns_scoped_data(tmp_path):
    store = SQLiteStore(tmp_path / "private.sqlite3")
    _seed_store(store)
    batch = read_telemetry_file(TELEMETRY_FIXTURE)
    _start_run(store, "trun-0000000000000005", batch.source_id)
    store.complete_telemetry_cycle(
        run_id="trun-0000000000000005", tenant_id=TENANT, source_id=batch.source_id, batch=batch,
    )
    tokens = LocalTokenRegistry()
    token = tokens.issue_development_token(TENANT)
    app = ApiApplication(store, tokens, scheduler_status=lambda: "running")
    findings = app.handle(method="GET", target="/api/telemetry/findings",
                          authorization=f"Bearer {token}")
    assert findings.status == 200
    assert findings.payload["tenant_id"] == TENANT
    assert len(findings.payload["findings"]) == 5
    finding_id = findings.payload["findings"][0]["finding_id"]
    evidence = app.handle(method="GET", target=f"/api/telemetry/findings/{finding_id}/evidence",
                          authorization=f"Bearer {token}")
    assert evidence.status == 200 and evidence.payload["evidence"]
    latest = app.handle(method="GET", target="/api/telemetry/reports/latest",
                        authorization=f"Bearer {token}")
    assert latest.status == 200
    assert latest.payload["report"]["tenant_id"] == TENANT
    status = app.handle(method="GET", target="/api/processing", authorization=f"Bearer {token}")
    assert status.status == 200
    assert status.payload["scheduler_state"] == "running"
    assert status.payload["latest_run"]["status"] == "completed"

    denied = app.handle(method="POST", target="/api/telemetry/ingest", authorization=None)
    assert denied.status == 401
    no_ingestion_route = app.handle(method="POST", target="/api/telemetry/ingest",
                                   authorization=f"Bearer {token}")
    assert no_ingestion_route.status == 405

    other_tenant = "synthetic-org-telemetry-other"
    other_token = tokens.issue_development_token(other_tenant)
    other_findings = app.handle(method="GET", target="/api/telemetry/findings",
                                authorization=f"Bearer {other_token}")
    assert other_findings.status == 200
    assert other_findings.payload["findings"] == []
    cross_tenant_evidence = app.handle(
        method="GET", target=f"/api/telemetry/findings/{finding_id}/evidence",
        authorization=f"Bearer {other_token}",
    )
    assert cross_tenant_evidence.status == 404
    cross_tenant_report = app.handle(
        method="GET", target="/api/telemetry/reports/latest", authorization=f"Bearer {other_token}"
    )
    assert cross_tenant_report.status == 404

