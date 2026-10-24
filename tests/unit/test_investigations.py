from __future__ import annotations

import json
import sqlite3
from types import SimpleNamespace
from datetime import datetime, timezone
from pathlib import Path

from platform_prototype.pipeline import build_report, read_batch_file
from private_api.auth import LocalTokenRegistry
from private_api.server import ApiApplication
from private_api.store import SQLiteStore
from private_api.telemetry import read_telemetry_file

ROOT = Path(__file__).parents[2]
TENANT = "synthetic-org-case-alpha"
OTHER = "synthetic-org-case-beta"
TELEMETRY = ROOT / "platform_prototype" / "fixtures" / "synthetic_telemetry_v1.json"
BASE = ROOT / "platform_prototype" / "fixtures" / "synthetic_events_v1.json"


def _seed(store: SQLiteStore, tenant: str) -> None:
    store.seed_tenant(tenant, build_report(read_batch_file(BASE)))
    batch = read_telemetry_file(TELEMETRY)
    run_id = "trun-" + ("0000000000000001" if tenant == TENANT else "0000000000000002")
    store.start_telemetry_run(run_id=run_id, tenant_id=tenant, source_id=batch.source_id,
                              scheduled_at_utc=datetime(2026, 10, 24, tzinfo=timezone.utc).isoformat(), attempt=1)
    store.complete_telemetry_cycle(run_id=run_id, tenant_id=tenant, source_id=batch.source_id, batch=batch)


def _app(tmp_path: Path):
    store = SQLiteStore(tmp_path / "cases.sqlite3")
    _seed(store, TENANT)
    _seed(store, OTHER)
    tokens = LocalTokenRegistry()
    analyst = tokens.issue_development_token(
        TENANT, scopes=frozenset({"investigations:read", "investigations:write"}),
    )
    reader = tokens.issue_development_token(TENANT, scopes=frozenset({"investigations:read"}))
    other = tokens.issue_development_token(
        OTHER, scopes=frozenset({"investigations:read", "investigations:write", "telemetry:read"}),
    )
    return ApiApplication(store, tokens), store, analyst, reader, other


def _call(app, token, path, *, method="GET", payload=None):
    body = json.dumps(payload).encode() if payload is not None else b""
    return app.handle(method=method, target=path, authorization=f"Bearer {token}",
                      body=body, body_length=len(body))


def test_case_links_notes_timeline_recommendations_and_audit_are_typed_and_scoped(tmp_path):
    app, store, analyst, reader, other = _app(tmp_path)
    assert _call(app, reader, "/api/investigations/cases", method="POST", payload={"title": "Case A"}).status == 403
    created = _call(app, analyst, "/api/investigations/cases", method="POST", payload={"title": "Synthetic auth review"})
    assert created.status == 201
    case_id = created.payload["case_id"]
    finding = store.list_telemetry_findings(TENANT)[0]
    assert _call(app, other, f"/api/investigations/cases/{case_id}").status == 404
    assert _call(app, analyst, f"/api/investigations/cases/{case_id}/findings", method="POST", payload={
        "finding_id": finding.finding_id, "relationship": "inferred_relationship",
        "rationale": "Rule output may be associated with this activity; verify independently.",
    }).status == 200
    evidence = store.list_telemetry_evidence(TENANT, finding.finding_id)[0]
    assert _call(app, analyst, f"/api/investigations/cases/{case_id}/evidence", method="POST", payload={
        "finding_id": finding.finding_id, "evidence_ref": evidence.evidence_ref,
        "rationale": "Reference to an existing stored event.",
    }).status == 200
    prior_history_count = len(store.get_investigation_case(TENANT, case_id)["history"])
    assert _call(app, analyst, f"/api/investigations/cases/{case_id}/evidence", method="POST", payload={
        "finding_id": finding.finding_id, "evidence_ref": evidence.evidence_ref,
        "rationale": "Reference to an existing stored event.",
    }).status == 200
    assert len(store.get_investigation_case(TENANT, case_id)["history"]) == prior_history_count
    assert _call(app, analyst, f"/api/investigations/cases/{case_id}/notes", method="POST", payload={
        "classification": "unresolved_hypothesis", "text": "Possible shared actor; not confirmed.",
    }).status == 200
    assert _call(app, analyst, f"/api/investigations/cases/{case_id}/status", method="POST", payload={"status": "under_review"}).status == 200
    detail = _call(app, analyst, f"/api/investigations/cases/{case_id}")
    assert detail.status == 200
    case = detail.payload["case"]
    assert case["status"] == "under_review"
    assert case["findings"][0]["relationship"] == "inferred_relationship"
    assert case["evidence"][0]["evidence_ref"] == evidence.evidence_ref
    assert case["notes"][0]["classification"] == "unresolved_hypothesis"
    assert {item["classification"] for item in case["timeline"]} >= {
        "verified_evidence", "inferred_relationship", "unresolved_hypothesis", "case_activity",
    }
    assert any(item["category"] == "finding" for item in case["timeline"])
    assert sum(item["category"] == "evidence" for item in case["timeline"]) == len(finding.evidence_refs)
    assert case["recommendations"] and case["recommendations"][0]["supporting_finding_ids"] == [finding.finding_id]
    listed = _call(app, analyst, "/api/investigations/cases?q=auth&status=under_review")
    assert [item["case_id"] for item in listed.payload["cases"]] == [case_id]
    assert all(row["route"].startswith("investigations.") for row in store.audit_snapshot()
               if row["event_type"] == "protected_operation")


def test_cross_tenant_finding_and_evidence_cannot_be_linked(tmp_path):
    app, _, analyst, _, other = _app(tmp_path)
    case_id = _call(app, analyst, "/api/investigations/cases", method="POST", payload={"title": "Alpha"}).payload["case_id"]
    foreign_finding = _call(app, other, "/api/telemetry/findings").payload["findings"][0]["finding_id"]
    rejected = _call(app, analyst, f"/api/investigations/cases/{case_id}/findings", method="POST", payload={
        "finding_id": foreign_finding, "relationship": "analyst_conclusion", "rationale": "Cross tenant test.",
    })
    assert rejected.status == 404
    assert _call(app, analyst, f"/api/investigations/cases/{case_id}").payload["case"]["findings"] == []
    assert [item["case_id"] for item in _call(app, analyst, "/api/investigations/cases").payload["cases"]] == [case_id]
    assert _call(app, analyst, "/api/investigations/cases").payload["tenant_id"] == TENANT
    assert _call(app, other, "/api/investigations/cases").payload["cases"] == []


def test_invalid_payloads_and_search_filters_fail_closed(tmp_path):
    app, store, analyst, _, _ = _app(tmp_path)
    assert _call(app, analyst, "/api/investigations/cases", method="POST", payload={"title": "x", "tenant_id": OTHER}).status == 400
    assert _call(app, analyst, "/api/investigations/cases?tenant_id=" + TENANT).status == 400
    assert _call(app, analyst, "/api/investigations/cases?status=unknown").status == 400
    case_id = _call(app, analyst, "/api/investigations/cases", method="POST", payload={"title": "Context test"}).payload["case_id"]
    assert _call(app, analyst, f"/api/investigations/cases/{case_id}/context", method="POST", payload={
        "source_type": "assessment_report", "source_id": "assessment-report-0000000000000000",
    }).status == 404
    assessment_id = "assessment-report-1111111111111111"
    with store._connect() as connection:
        connection.execute(
            "INSERT INTO website_assessment_reports VALUES (?, ?, ?, ?)",
            (TENANT, assessment_id, "2026-10-23T12:00:00+00:00", json.dumps({"report_id": assessment_id})),
        )
    evaluation_id = "11111111-1111-4111-8111-111111111111"
    app.detection_evaluation = SimpleNamespace(history=[SimpleNamespace(
        run_id=evaluation_id, generated_at_utc=datetime(2026, 10, 23, 13, tzinfo=timezone.utc),
    )])
    for source_type, source_id in (("assessment_report", assessment_id), ("evaluation_run", evaluation_id)):
        assert _call(app, analyst, f"/api/investigations/cases/{case_id}/context", method="POST", payload={
            "source_type": source_type, "source_id": source_id,
        }).status == 200
    contexts = _call(app, analyst, f"/api/investigations/cases/{case_id}").payload["case"]["context"]
    assert {item["source_type"] for item in contexts} == {"assessment_report", "evaluation_run"}
    assert _call(app, analyst, f"/api/investigations/cases/{case_id}/notes", method="POST", payload={
        "classification": "analyst_conclusion", "text": "Bearer abcdefghijklmnop",
    }).status == 400
    assert _call(app, analyst, f"/api/investigations/cases/{case_id}").payload["case"]["notes"] == []


def test_schema_v4_upgrades_additively_in_temporary_database(tmp_path):
    path = tmp_path / "upgrade.sqlite3"
    store = SQLiteStore(path)
    with sqlite3.connect(path) as connection:
        for table in ("purple_team_scenario_locks", "purple_team_scenario_runs", "investigation_case_context", "investigation_case_evidence", "investigation_case_findings",
                      "investigation_case_history", "investigation_cases"):
            connection.execute(f"DROP TABLE {table}")
        connection.execute("PRAGMA user_version=5")
    upgraded = SQLiteStore(path)
    assert upgraded.ping()
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 6
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"investigation_cases", "investigation_case_history", "investigation_case_findings",
                "investigation_case_evidence", "investigation_case_context"}.issubset(tables)
        assert "purple_team_scenario_runs" in tables
        assert "purple_team_scenario_locks" in tables


def test_case_write_scope_is_opt_in_at_api_startup():
    from scripts.run_private_api import build_parser

    default_args = build_parser().parse_args([])
    analyst_args = build_parser().parse_args(["--enable-investigation-writes"])
    assert default_args.enable_investigation_writes is False
    assert analyst_args.enable_investigation_writes is True
