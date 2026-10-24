from datetime import datetime, timezone

from private_api.auth import LocalTokenRegistry
from private_api.server import ApiApplication
from private_api.store import SQLiteStore
from purple_team.models import ScenarioExecutionReport, ScenarioPolicyDecision


def _run() -> ScenarioExecutionReport:
    now = datetime.now(timezone.utc)
    return ScenarioExecutionReport(
        scenario_id="local-health-baseline", scenario_version="1.0", status="PASSED",
        started_at_utc=now, completed_at_utc=now,
        policy_decision=ScenarioPolicyDecision(
            scenario_id="local-health-baseline", target_origin="http://127.0.0.1:8767",
            allowed=True, reason_code="approved", maximum_requests=1,
        ),
        expected_telemetry_type="synthetic_http_access", expected_route_code="health",
        expected_status=200, expected_count=1, observed_http_statuses=(200,),
        observed_telemetry=(), expected_detection_rule_ids=(), observed_findings=(),
        assessment_check_ids=("health_status_v1",), limitations=("Synthetic test report.",),
    )


def test_scenario_history_is_authenticated_bounded_and_tenant_scoped(tmp_path):
    store = SQLiteStore(tmp_path / "scenario-history.sqlite3")
    store.save_purple_scenario_run("synthetic-org-alpha", _run())
    tokens = LocalTokenRegistry()
    alpha = tokens.issue_development_token("synthetic-org-alpha")
    beta = tokens.issue_development_token("synthetic-org-beta")
    app = ApiApplication(store, tokens)

    assert app.handle(method="GET", target="/api/purple-team/scenarios/runs", authorization=None).status == 401
    visible = app.handle(method="GET", target="/api/purple-team/scenarios/runs", authorization=f"Bearer {alpha}")
    assert visible.status == 200
    assert visible.payload["tenant_id"] == "synthetic-org-alpha"
    assert visible.payload["runs"][0]["scenario_id"] == "local-health-baseline"
    hidden = app.handle(method="GET", target="/api/purple-team/scenarios/runs", authorization=f"Bearer {beta}")
    assert hidden.status == 200
    assert hidden.payload["tenant_id"] == "synthetic-org-beta"
    assert hidden.payload["runs"] == []
    forged = app.handle(method="GET", target="/api/purple-team/scenarios/runs?tenant_id=synthetic-org-alpha",
                        authorization=f"Bearer {beta}")
    assert forged.status == 400

    restricted = LocalTokenRegistry()
    token = restricted.issue_development_token("synthetic-org-alpha", scopes=frozenset({"findings:read"}))
    assert ApiApplication(store, restricted).handle(
        method="GET", target="/api/purple-team/scenarios/runs", authorization=f"Bearer {token}"
    ).status == 403
