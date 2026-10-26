"""Compare real Controller runs, preserve evidence, and expose response costs."""
import json
from pathlib import Path

import pytest

from evaluation.experiments.defender_benchmark import build_benchmark, report_json
from scripts.run_defender_benchmark import main


def test_full_regression_report_matches_reviewed_evidence():
    report = build_benchmark()
    reference = Path(__file__).resolve().parents[2] / "results/evaluation/defender_benchmark_v1.json"
    assert report == json.loads(reference.read_text(encoding="utf-8"))
    assert report["protocol"]["pairs"] == 30
    summary = report["summary"]
    assert summary["improved_pairs"] + summary["regressed_pairs"] + summary["unchanged_pairs"] == 30
    assert summary["regressed_pairs"] == 0
    assert summary["improved_pairs"] > 0
    assert summary["candidate"]["isolations_without_prior_red_activity"] == 0
    assert summary["candidate"]["mean_isolated_hosts_at_end"] > 0
    for pair in report["pairs"]:
        for policy in ("baseline", "candidate"):
            metrics = pair[policy]["metrics"]
            assert metrics["scenario_id"] == pair["scenario_id"]
            assert "decision_latency_ms" not in metrics
        if pair["paired_outcome"] == "improved":
            assert pair["baseline"]["metrics"]["attack_success"]
            assert not pair["candidate"]["metrics"]["attack_success"]
        for response in pair["candidate"]["response_records"]:
            if response["action"] == "ISOLATE_HOST":
                assert response["authorized"] and response["success"]
                assert any(alert["host"] == response["target"] and alert["investigated"]
                           and alert["severity"] in ("high", "critical")
                           and any(event["host"] == response["target"] for event in alert["evidence"])
                           for alert in response["supporting_alerts"])


def test_report_is_reproducible_without_timing_or_generated_episode_identifiers():
    kwargs = {"template_ids": ("credential_reuse_known_vuln",), "seeds": (1,)}
    assert report_json(build_benchmark(**kwargs)) == report_json(build_benchmark(**kwargs))


@pytest.mark.parametrize("kwargs", [
    {"template_ids": ()}, {"seeds": ()}, {"seeds": (1, 1)},
    {"template_ids": ("unknown",)}, {"seeds": (True,)}, {"seeds": (-1,)},
    {"seeds": tuple(range(121))},
])
def test_invalid_or_inflated_comparisons_are_rejected(kwargs):
    with pytest.raises(ValueError):
        build_benchmark(**kwargs)


def test_cli_preserves_existing_reports_and_writes_structured_evidence(tmp_path, capsys):
    path = tmp_path / "benchmark.json"
    args = ["--templates", "credential_reuse_known_vuln", "--seeds", "1", "--output", str(path)]
    assert main(args) == 0
    original = path.read_bytes()
    assert json.loads(original)["summary"]["improved_pairs"] == 1
    assert "mean isolated hosts" in capsys.readouterr().out
    assert main(args) == 1
    assert path.read_bytes() == original


def test_stdout_mode_emits_only_valid_json(capsys):
    assert main(["--templates", "credential_reuse_known_vuln", "--seeds", "1", "--stdout"]) == 0
    assert json.loads(capsys.readouterr().out)["protocol"]["pairs"] == 1
