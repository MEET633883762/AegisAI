from __future__ import annotations

from local_assessment.models import (
    AssessmentDecision, AssessmentObservation, AssessmentReport, AssessmentResult, CheckId,
)
from private_api.auth import LocalTokenRegistry
from private_api.server import ApiApplication
from private_api.store import SQLiteStore


def _report() -> AssessmentReport:
    decision = AssessmentDecision(
        check_id=CheckId.HEALTH_STATUS, target_origin="http://127.0.0.1:8767",
        allowed=True, reason_code="approved",
    )
    observation = AssessmentObservation(
        check_id=CheckId.HEALTH_STATUS, decision=decision, outcome="observed",
        duration_ms=5, facts={"status": 200}, evidence=None,
    )
    return AssessmentReport.from_result(AssessmentResult(decisions=(decision,), observations=(observation,)))


def _request(app: ApiApplication, token: str | None, path: str = "/api/assessment/reports/latest"):
    return app.handle(method="GET", target=path,
                      authorization=f"Bearer {token}" if token else None)


def test_assessment_report_api_is_authenticated_read_only_and_tenant_scoped(tmp_path):
    store = SQLiteStore(tmp_path / "assessment-api.sqlite3")
    store.save_assessment_report("synthetic-org-alpha", _report())
    tokens = LocalTokenRegistry()
    alpha = tokens.issue_development_token("synthetic-org-alpha")
    beta = tokens.issue_development_token("synthetic-org-beta")
    app = ApiApplication(store, tokens)

    assert _request(app, None).status == 401
    visible = _request(app, alpha)
    assert visible.status == 200
    assert visible.payload["tenant_id"] == "synthetic-org-alpha"
    assert visible.payload["report"]["raw_observations"][0]["check_id"] == "health_status_v1"
    assert len(visible.payload["history"]) == 1
    assert visible.payload["history"][0]["report_id"] == visible.payload["report"]["report_id"]
    absent = _request(app, beta)
    assert absent.status == 200
    assert absent.payload == {
        "data_classification": "synthetic", "label": "LOCAL SYNTHETIC WEBSITE ASSESSMENT",
        "tenant_id": "synthetic-org-beta", "report": None, "history": [],
    }
    forged = _request(app, alpha, "/api/assessment/reports/latest?tenant_id=synthetic-org-beta")
    assert forged.status == 400
    assert "report" not in forged.payload

    restricted = LocalTokenRegistry()
    findings_only = restricted.issue_development_token("synthetic-org-alpha", scopes=frozenset({"findings:read"}))
    assert _request(ApiApplication(store, restricted), findings_only).status == 403

    events = store.audit_snapshot()
    assert any(item["event_type"] == "authentication_failure" for item in events)
    assert any(item["event_type"] == "access_denial" and item["details_code"] == "insufficient_scope" for item in events)
    assert any(item["route"] == "assessment.report" and item["outcome"] == "success" for item in events)
