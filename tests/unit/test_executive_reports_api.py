from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from platform_prototype.pipeline import build_report, read_batch_file
from private_api.auth import LocalTokenRegistry
from private_api.models import EvidenceReferenceResponse
from private_api.server import ApiApplication
from private_api.store import SQLiteStore
from private_api.telemetry import TelemetryEventType, TelemetryFinding, read_telemetry_file


ROOT = Path(__file__).parents[2]
TELEMETRY_FIXTURE = ROOT / "platform_prototype" / "fixtures" / "synthetic_telemetry_v1.json"
PHASE1_FIXTURE = ROOT / "platform_prototype" / "fixtures" / "synthetic_events_v1.json"
ALPHA = "synthetic-org-executive-alpha"
BETA = "synthetic-org-executive-beta"


def _seed_tenant(store: SQLiteStore, tenant_id: str) -> None:
    store.seed_tenant(tenant_id, build_report(read_batch_file(PHASE1_FIXTURE)))


def _seed_telemetry(store: SQLiteStore, tenant_id: str, run_suffix: str) -> None:
    batch = read_telemetry_file(TELEMETRY_FIXTURE)
    run_id = f"trun-{run_suffix:0>16}"
    store.start_telemetry_run(
        run_id=run_id, tenant_id=tenant_id, source_id=batch.source_id,
        scheduled_at_utc=datetime(2026, 10, 22, tzinfo=timezone.utc).isoformat(), attempt=1,
    )
    store.complete_telemetry_cycle(
        run_id=run_id, tenant_id=tenant_id, source_id=batch.source_id, batch=batch,
    )


def _app(store: SQLiteStore, *, tenants=(ALPHA, BETA), scopes=None):
    tokens = LocalTokenRegistry()
    issued = {
        tenant: tokens.issue_development_token(
            tenant, scopes=frozenset(scopes) if scopes is not None else frozenset({"reports:read"}),
        )
        for tenant in tenants
    }
    return ApiApplication(store, tokens), issued


def _call(app: ApiApplication, token: str | None):
    return app.handle(
        method="GET", target="/api/reports/executive/latest",
        authorization=f"Bearer {token}" if token else None,
    )


@pytest.fixture
def populated_store(tmp_path):
    store = SQLiteStore(tmp_path / "executive-api.sqlite3")
    _seed_tenant(store, ALPHA)
    _seed_tenant(store, BETA)
    _seed_telemetry(store, ALPHA, "0000000000000001")
    _seed_telemetry(store, BETA, "0000000000000002")
    return store


def test_authorized_report_uses_authenticated_tenant_and_preserves_inferred_status(populated_store):
    app, tokens = _app(populated_store)
    response = _call(app, tokens[ALPHA])

    assert response.status == 200
    assert response.payload["tenant_id"] == ALPHA
    assert response.payload["data_classification"] == "synthetic"
    report = response.payload["report"]
    assert report["report_type"] == "aegisai_executive_incident_report"
    assert len(report["inferred_risks"]) == 5
    assert report["confirmed_findings"] == []
    assert all(row["classification"] == "inferred_risk" for row in report["inferred_risks"])
    assert all(row["evidence_refs"] for row in report["inferred_risks"])
    assert populated_store.audit_snapshot()[-1]["event_type"] == "protected_operation"


def test_authentication_and_reports_scope_are_required(populated_store):
    app, _ = _app(populated_store)
    assert _call(app, None).status == 401
    reports_missing = _app(populated_store, tenants=(ALPHA,), scopes={"findings:read"})
    response = _call(reports_missing[0], reports_missing[1][ALPHA])
    assert response.status == 403
    assert populated_store.audit_snapshot()[-1]["details_code"] == "insufficient_scope"


def test_other_tenant_data_is_not_included_in_report(populated_store):
    app, tokens = _app(populated_store)
    alpha = _call(app, tokens[ALPHA]).payload["report"]
    beta = _call(app, tokens[BETA]).payload["report"]

    alpha_ids = {item["finding_id"] for item in alpha["inferred_risks"]}
    beta_ids = {item["finding_id"] for item in beta["inferred_risks"]}
    assert alpha_ids.isdisjoint(beta_ids)
    assert {ref for item in alpha["observations"] for ref in item["related_finding_ids"]} == alpha_ids
    assert {ref for item in beta["observations"] for ref in item["related_finding_ids"]} == beta_ids


def test_missing_evidence_returns_safe_unavailable_response(populated_store, monkeypatch):
    app, tokens = _app(populated_store, tenants=(ALPHA,))
    monkeypatch.setattr(populated_store, "list_telemetry_evidence", lambda tenant, finding: None)

    response = _call(app, tokens[ALPHA])
    assert response.status == 503
    assert response.payload == {
        "error": "temporarily_unavailable",
        "message": "The executive report is temporarily unavailable.",
    }


def test_invalid_stored_source_data_fails_safely(populated_store, monkeypatch):
    app, tokens = _app(populated_store, tenants=(ALPHA,))

    def invalid_source(_tenant):
        TelemetryFinding.model_validate({})

    monkeypatch.setattr(populated_store, "list_telemetry_findings", invalid_source)
    response = _call(app, tokens[ALPHA])
    assert response.status == 500
    assert response.payload == {
        "error": "internal_error",
        "message": "The service could not complete the request.",
    }


def test_empty_findings_returns_a_valid_empty_report(tmp_path):
    store = SQLiteStore(tmp_path / "empty-executive-api.sqlite3")
    _seed_tenant(store, ALPHA)
    app, tokens = _app(store, tenants=(ALPHA,))

    response = _call(app, tokens[ALPHA])
    assert response.status == 200
    assert response.payload["report"]["inferred_risks"] == []
    assert response.payload["report"]["observations"] == []
    assert response.payload["report"]["timeline"] == []
    assert response.payload["report"]["finding_counts"]["by_severity"] == {
        "low": 0, "medium": 0, "high": 0, "critical": 0,
    }


@pytest.mark.parametrize("event_type", list(TelemetryEventType))
def test_existing_telemetry_evidence_event_types_pass_response_validation(event_type):
    evidence = EvidenceReferenceResponse(
        evidence_ref="synthetic-evidence-api-test", event_id="syn-api-test",
        event_type=event_type.value, occurred_at_utc=datetime(2026, 10, 22, tzinfo=timezone.utc),
        asset_ref="synthetic-asset", actor_ref="synthetic-actor", source_ref="synthetic-source",
    )
    assert evidence.event_type == event_type.value
