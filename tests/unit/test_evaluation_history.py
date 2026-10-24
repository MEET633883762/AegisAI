from __future__ import annotations

from datetime import datetime, timedelta, timezone

from platform_prototype.evaluation import evaluate_dataset
from platform_prototype.evaluation_dataset import load_evaluation_dataset_bytes
from platform_prototype.evaluation_history import MAX_HISTORY_RUNS, read_evaluation_history, record_evaluation_run
from private_api.telemetry import detect_findings


def dataset():
    from pathlib import Path

    path = Path(__file__).parents[2] / "platform_prototype" / "fixtures" / "evaluation_dataset_v1.json"
    return load_evaluation_dataset_bytes(path.read_bytes())


def test_history_compares_runs_and_retains_only_bounded_summaries(tmp_path):
    source = dataset()
    baseline = evaluate_dataset(source)
    target = next(item for item in source.scenarios if item.scenario_id == "p6a-app-suspicious-code")
    target_ids = {record["event_id"] for record in target.detector_input}

    def suppress_target_rule(events, *, tenant_id):
        findings = detect_findings(events, tenant_id=tenant_id)
        return [item for item in findings if not (
            item.rule_id == "APP-001" and any(event.event_id in target_ids for event in events)
        )]

    changed = evaluate_dataset(source, detector=suppress_target_rule)
    origin = datetime(2026, 10, 24, tzinfo=timezone.utc)
    path = tmp_path / "evaluation-history.sqlite3"
    record_evaluation_run(path, baseline, generated_at_utc=origin.isoformat(),
                          run_id="00000000-0000-0000-0000-000000000001")
    changed_run = record_evaluation_run(path, changed, generated_at_utc=(origin + timedelta(minutes=1)).isoformat(),
                                        run_id="00000000-0000-0000-0000-000000000002")
    assert changed_run.comparison is not None
    assert changed_run.comparison.newly_failing_scenario_ids == ["p6a-app-suspicious-code"]
    assert changed_run.comparison.resolved_scenario_ids == []
    resolved_run = record_evaluation_run(path, baseline, generated_at_utc=(origin + timedelta(minutes=2)).isoformat(),
                                         run_id="00000000-0000-0000-0000-000000000003")
    assert resolved_run.comparison is not None
    assert resolved_run.comparison.resolved_scenario_ids == ["p6a-app-suspicious-code"]

    latest, history = read_evaluation_history(path)
    assert latest is not None and latest.scenarios[0].status == "pass"
    assert [item.run_id for item in history] == [
        "00000000-0000-0000-0000-000000000003",
        "00000000-0000-0000-0000-000000000002",
        "00000000-0000-0000-0000-000000000001",
    ]
    assert history[0].comparison.resolved_scenario_ids == ["p6a-app-suspicious-code"]
    assert history[1].comparison.newly_failing_scenario_ids == ["p6a-app-suspicious-code"]
    assert history[2].comparison is None
    assert history[0].report_sha256 == history[2].report_sha256


def test_history_retention_is_bounded_to_twenty_runs(tmp_path):
    report = evaluate_dataset(dataset())
    path = tmp_path / "bounded-history.sqlite3"
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for index in range(MAX_HISTORY_RUNS + 2):
        record_evaluation_run(
            path, report,
            generated_at_utc=(start + timedelta(minutes=index)).isoformat(),
            run_id=f"00000000-0000-0000-0000-{index:012x}",
        )
    latest, history = read_evaluation_history(path)
    assert latest is not None
    assert len(history) == MAX_HISTORY_RUNS
    assert history[0].run_id.endswith(f"{MAX_HISTORY_RUNS + 1:012x}")
