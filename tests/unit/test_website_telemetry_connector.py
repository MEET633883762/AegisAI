from __future__ import annotations

import json
from datetime import timezone
from pathlib import Path

import pytest

from private_api.store import SQLiteStore
from private_api.telemetry import MAX_INPUT_BYTES, TelemetryConflictError, detect_findings, normalize_and_deduplicate
from private_api.website_connector import (
    FIXTURE_DIR,
    WEBSITE_LOG_FIXTURE,
    WEBSITE_SOURCE_REF,
    WebsiteLogFile,
    WebsiteLogInputError,
    _read_approved_file,
    _validate_bytes,
    read_website_log_fixture,
    to_telemetry_batch,
)
from private_api.website_ingestion import FIXED_TENANT_ID, ingest_local_website_sample


ROOT = Path(__file__).parents[2]


def _payload() -> dict:
    return json.loads(WEBSITE_LOG_FIXTURE.read_text(encoding="utf-8"))


def test_fixed_sample_maps_access_auth_rate_and_error_to_synthetic_utc_events():
    logs = read_website_log_fixture()
    batch = to_telemetry_batch(logs)
    events, duplicates = normalize_and_deduplicate(batch)
    assert logs.source_id == "synthetic_demo_site_access_error_logs_v1"
    assert len(events) == 8 and duplicates == 0
    assert all(event.occurred_at.tzinfo == timezone.utc for event in events)
    assert {event.event_type.value for event in events} == {
        "synthetic_http_access", "auth_failure", "request_rate_indicator", "synthetic_application_error",
    }
    assert all(event.source_ref == WEBSITE_SOURCE_REF for event in events)
    assert all(event.evidence_ref.startswith("synthetic-website-evidence-") for event in events)
    findings = detect_findings(events, tenant_id=FIXED_TENANT_ID)
    assert {finding.rule_id for finding in findings} == {"AUTH-001", "WEB-001"}
    assert all(set(finding.evidence_refs).issubset({event.evidence_ref for event in events}) for finding in findings)


@pytest.mark.parametrize("mutation", [
    lambda data: data.update(schema_version="9.0"),
    lambda data: data.update(data_classification="client"),
    lambda data: data["records"][0].update(method="TRACE"),
    lambda data: data["records"][0].update(route_code="https://example.invalid"),
    lambda data: data["records"][0].update(occurred_at="2026-10-22T11:00:00"),
    lambda data: data["records"][0].update(token="do-not-store"),
    lambda data: data["records"][0].update(actor_ref="real-person@example.com"),
    lambda data: data["records"][0].update(status_code=700),
    lambda data: data["records"][0].update(record_type="arbitrary_file_read"),
    lambda data: data["records"][0].update(status_code=404, error_code="arbitrary"),
])
def test_bad_log_schema_codes_lengths_or_semantics_are_rejected(mutation):
    payload = _payload()
    mutation(payload)
    with pytest.raises(WebsiteLogInputError, match="validation failed"):
        _validate_bytes(json.dumps(payload).encode())


def test_size_and_record_count_are_bounded_before_unbounded_processing():
    with pytest.raises(WebsiteLogInputError, match="1 MiB"):
        _validate_bytes(b" " * (MAX_INPUT_BYTES + 1))
    payload = _payload()
    payload["records"] *= 63
    with pytest.raises(WebsiteLogInputError, match="validation failed"):
        _validate_bytes(json.dumps(payload).encode())
    with pytest.raises(WebsiteLogInputError, match="validation failed"):
        _validate_bytes(b"{\"records\":[")


def test_conflicting_record_or_ambiguous_evidence_is_rejected_by_existing_deduplicator():
    payload = _payload()
    payload["records"].append(dict(payload["records"][0]))
    logs = WebsiteLogFile.model_validate(payload)
    events, duplicates = normalize_and_deduplicate(to_telemetry_batch(logs))
    assert len(events) == 8 and duplicates == 1
    payload["records"][-1]["status_code"] = 404
    with pytest.raises(TelemetryConflictError, match="conflicting content"):
        normalize_and_deduplicate(to_telemetry_batch(WebsiteLogFile.model_validate(payload)))
    payload = _payload()
    payload["records"][1]["evidence_id"] = payload["records"][0]["evidence_id"]
    with pytest.raises(TelemetryConflictError, match="multiple event IDs"):
        normalize_and_deduplicate(to_telemetry_batch(WebsiteLogFile.model_validate(payload)))


def test_fixed_reader_refuses_symlink_and_reports_missing_source_safely(tmp_path):
    approved = tmp_path / "approved"
    approved.mkdir()
    outside = tmp_path / "outside.json"
    outside.write_text("{}", encoding="utf-8")
    link = approved / "sample.json"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation is unavailable")
    with pytest.raises(WebsiteLogInputError, match="outside the approved fixture"):
        _read_approved_file(link, approved)
    with pytest.raises(WebsiteLogInputError, match="unavailable: FileNotFoundError"):
        _read_approved_file(approved / "missing.json", approved)
    with pytest.raises(WebsiteLogInputError, match="not an approved regular file"):
        _read_approved_file(approved, approved.parent)
    assert "tmp_path" not in str(WebsiteLogInputError("unavailable"))


def test_ingestion_is_fixed_tenant_audited_and_idempotent(tmp_path):
    store = SQLiteStore(tmp_path / "private.sqlite3")
    first = ingest_local_website_sample(store)
    second = ingest_local_website_sample(store)
    assert first.tenant_id == second.tenant_id == FIXED_TENANT_ID
    assert (first.accepted_event_count, first.duplicate_event_count) == (8, 0)
    assert (second.accepted_event_count, second.duplicate_event_count) == (0, 8)
    assert {item.rule_id for item in store.list_telemetry_findings(FIXED_TENANT_ID)} == {"AUTH-001", "WEB-001"}
    audit = store.audit_snapshot()
    assert len(audit) == 2
    assert all(row["route"] == "website_telemetry.ingest" and row["outcome"] == "completed" for row in audit)
    assert all("token" not in row["details_code"].lower() for row in audit)


def test_source_and_storage_failures_are_categorical_and_audited(tmp_path, monkeypatch):
    import private_api.website_ingestion as ingestion

    store = SQLiteStore(tmp_path / "private.sqlite3")
    monkeypatch.setattr(
        ingestion, "read_website_log_fixture",
        lambda: (_ for _ in ()).throw(WebsiteLogInputError("fixture malformed")),
    )
    with pytest.raises(RuntimeError, match="local synthetic website telemetry ingestion failed"):
        ingestion.ingest_local_website_sample(store)
    assert store.latest_telemetry_run(FIXED_TENANT_ID)["error_code"] == "source_invalid"
    assert store.audit_snapshot()[-1]["details_code"] == "source_invalid"

    monkeypatch.setattr(ingestion, "read_website_log_fixture", read_website_log_fixture)
    monkeypatch.setattr(
        store, "complete_telemetry_cycle",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("sensitive local detail")),
    )
    with pytest.raises(RuntimeError, match="local synthetic website telemetry ingestion failed") as error:
        ingestion.ingest_local_website_sample(store)
    assert "sensitive local detail" not in str(error.value)
    assert store.latest_telemetry_run(FIXED_TENANT_ID)["error_code"] == "processing_error"
    assert store.audit_snapshot()[-1]["details_code"] == "processing_error"


def test_no_http_ingestion_route_is_added(tmp_path):
    from private_api.auth import LocalTokenRegistry
    from private_api.server import ApiApplication

    store = SQLiteStore(tmp_path / "unused.sqlite3")
    tokens = LocalTokenRegistry()
    token = tokens.issue_development_token(FIXED_TENANT_ID)
    response = ApiApplication(store, tokens).handle(
        method="POST", target="/api/website-telemetry/ingest", authorization=f"Bearer {token}",
    )
    assert response.status == 405
