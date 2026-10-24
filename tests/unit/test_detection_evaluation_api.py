from __future__ import annotations

from pathlib import Path

from platform_prototype.evaluation import evaluate_dataset, report_json
from platform_prototype.evaluation_dataset import load_evaluation_dataset_bytes
from private_api.auth import LocalTokenRegistry
from private_api.server import ApiApplication
from private_api.store import SQLiteStore


def call(app: ApiApplication, token: str | None, path: str = "/api/evaluation/reports/latest"):
    return app.handle(method="GET", target=path,
                      authorization=f"Bearer {token}" if token else None)


def test_authenticated_reports_scope_returns_only_benchmark_summary(tmp_path, monkeypatch):
    import private_api.server as server

    dataset_path = Path(__file__).parents[2] / "platform_prototype" / "fixtures" / "evaluation_dataset_v1.json"
    dataset = load_evaluation_dataset_bytes(dataset_path.read_bytes())
    report_path = tmp_path / "phase6b_report.json"
    report_path.write_text(report_json(evaluate_dataset(dataset)), encoding="utf-8")
    monkeypatch.setattr(server, "EVALUATION_REPORT_PATH", report_path)
    monkeypatch.setattr(server, "EVALUATION_HISTORY_DATABASE_PATH", tmp_path / "history.sqlite3")
    store = SQLiteStore(tmp_path / "api.sqlite3")
    tokens = LocalTokenRegistry()
    alpha = tokens.issue_development_token("synthetic-org-alpha")
    beta = tokens.issue_development_token("synthetic-org-beta")
    app = ApiApplication(store, tokens)

    response = call(app, alpha)
    assert response.status == 200
    body = response.payload
    assert body["tenant_id"] == "synthetic-org-alpha"
    assert body["data_classification"] == "synthetic"
    assert body["label"] == "SYNTHETIC EVALUATION - NOT REAL SECURITY PERFORMANCE"
    report = body["report"]
    assert report["report_type"] == "aegisai_synthetic_detection_evaluation_report"
    counts = report["counts"]
    assert report["total_evaluated_pairs"] == sum(counts[key] for key in (
        "true_positives", "true_negatives", "false_positives", "false_negatives"))
    assert report["per_rule"]
    assert report["dataset_sha256"] and report["detector_config_sha256"]
    assert report["rejected_scenario_count"] >= 0
    assert report["metrics"]["specificity"]["value"] == 1.0
    assert report["coverage_status"] == "partial"
    assert report["scenario_rule_mapping"]
    assert report["untested_techniques"][0]["technique_id"] == "T1110"
    assert report["history"] == []
    assert "scenarios" not in report and "rejected_inputs" not in report and "evidence_summary" not in report

    beta_response = call(app, beta)
    assert beta_response.status == 200
    assert beta_response.payload["tenant_id"] == "synthetic-org-beta"
    assert beta_response.payload["report"] == report  # fixed public-to-this-private-service benchmark, no tenant data
    assert store.audit_snapshot()[-1]["tenant_id"] == "synthetic-org-beta"


def test_evaluation_report_requires_authentication_and_reports_scope(tmp_path, monkeypatch):
    import private_api.server as server

    monkeypatch.setattr(server, "EVALUATION_HISTORY_DATABASE_PATH", tmp_path / "history.sqlite3")
    store = SQLiteStore(tmp_path / "api.sqlite3")
    tokens = LocalTokenRegistry()
    read_findings_only = tokens.issue_development_token(
        "synthetic-org-alpha", scopes=frozenset({"findings:read"}))
    app = ApiApplication(store, tokens)
    assert call(app, None).status == 401
    denied = call(app, read_findings_only)
    assert denied.status == 403
    assert denied.payload["error"] == "forbidden"
    assert store.audit_snapshot()[-1]["details_code"] == "insufficient_scope"


def test_missing_report_is_reported_without_path_details(tmp_path, monkeypatch):
    import private_api.server as server

    monkeypatch.setattr(server, "EVALUATION_REPORT_PATH", tmp_path / "missing-report.json")
    monkeypatch.setattr(server, "EVALUATION_HISTORY_DATABASE_PATH", tmp_path / "missing-history.sqlite3")
    store = SQLiteStore(tmp_path / "api.sqlite3")
    tokens = LocalTokenRegistry()
    token = tokens.issue_development_token("synthetic-org-alpha")
    response = call(ApiApplication(store, tokens), token)
    assert response.status == 503
    assert response.payload == {
        "error": "temporarily_unavailable",
        "message": "The synthetic evaluation report is temporarily unavailable.",
    }


def test_legacy_report_gets_derived_specificity_without_invented_coverage(tmp_path, monkeypatch):
    import json
    import private_api.server as server

    report = evaluate_dataset(load_evaluation_dataset_bytes(
        (Path(__file__).parents[2] / "platform_prototype" / "fixtures" / "evaluation_dataset_v1.json").read_bytes()
    )).model_dump(mode="json")
    report["schema_version"] = "1.0"
    for metric_set in [report["metrics"], *(item["metrics"] for item in report["per_rule"])]:
        metric_set.pop("specificity")
    for field in (
        "rule_catalog_version", "detector_rule_version", "scenario_rule_mapping_version",
        "attack_mapping_catalog_version", "rule_event_mapping", "scenario_rule_mapping",
        "technique_coverage", "untested_techniques", "coverage_status", "warnings",
    ):
        report.pop(field)
    path = tmp_path / "legacy.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    monkeypatch.setattr(server, "EVALUATION_REPORT_PATH", path)
    monkeypatch.setattr(server, "EVALUATION_HISTORY_DATABASE_PATH", tmp_path / "history.sqlite3")
    tokens = LocalTokenRegistry()
    token = tokens.issue_development_token("synthetic-org-demo")
    response = call(ApiApplication(SQLiteStore(tmp_path / "api.sqlite3"), tokens), token)
    assert response.status == 200
    summary = response.payload["report"]
    assert summary["metrics"]["specificity"]["value"] == 1.0
    assert summary["coverage_status"] == "legacy_unavailable"
    assert summary["scenario_rule_mapping"] == []


def test_authenticated_api_returns_bounded_history_and_run_comparison(tmp_path, monkeypatch):
    import private_api.server as server
    from platform_prototype.evaluation_history import record_evaluation_run

    dataset_path = Path(__file__).parents[2] / "platform_prototype" / "fixtures" / "evaluation_dataset_v1.json"
    dataset = load_evaluation_dataset_bytes(dataset_path.read_bytes())
    baseline = evaluate_dataset(dataset)
    target = next(item for item in dataset.scenarios if item.scenario_id == "p6a-app-suspicious-code")
    event_ids = {item["event_id"] for item in target.detector_input}
    from private_api.telemetry import detect_findings

    def missing_rule(events, *, tenant_id):
        return [item for item in detect_findings(events, tenant_id=tenant_id)
                if not (item.rule_id == "APP-001" and any(event.event_id in event_ids for event in events))]

    changed = evaluate_dataset(dataset, detector=missing_rule)
    history_path = tmp_path / "history.sqlite3"
    record_evaluation_run(history_path, baseline, generated_at_utc="2026-10-24T00:00:00Z",
                          run_id="00000000-0000-0000-0000-000000000001")
    record_evaluation_run(history_path, changed, generated_at_utc="2026-10-24T00:01:00Z",
                          run_id="00000000-0000-0000-0000-000000000002")
    monkeypatch.setattr(server, "EVALUATION_HISTORY_DATABASE_PATH", history_path)
    store = SQLiteStore(tmp_path / "api.sqlite3")
    tokens = LocalTokenRegistry()
    token = tokens.issue_development_token("synthetic-org-demo")
    response = call(ApiApplication(store, tokens), token)
    assert response.status == 200
    report = response.payload["report"]
    assert report["counts"]["false_negatives"] == 1
    assert report["history"][0]["comparison"]["newly_failing_scenario_ids"] == ["p6a-app-suspicious-code"]
