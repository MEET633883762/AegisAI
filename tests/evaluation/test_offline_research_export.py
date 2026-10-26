"""The offline research CLI must preserve inspectable, machine-readable evidence."""

import json

from scripts import run_offline_research


def test_offline_research_exports_nested_metrics_instead_of_object_repr(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(run_offline_research, "ROOT", tmp_path)

    run_offline_research.main()

    report = json.loads((tmp_path / "results" / "offline_research_result.json").read_text(encoding="utf-8"))
    for name in ("baseline", "no_memory", "adaptive_memory"):
        run = report[name]
        assert isinstance(run, dict)
        assert run["aggregate"]["episodes"] == 2
        assert len(run["episodes"]) == 2
        assert [episode["scenario_id"] for episode in run["episodes"]] == [
            f"{template}:{seed}" for template, seed in report["split"]["test"]
        ]
        assert all(isinstance(episode["attack_success"], bool) for episode in run["episodes"])
        assert isinstance(run["aggregate"]["detection_rate"], float)

    assert report["adaptation_improvement"] == 0.0
    assert report["generalization_improvement"] == 0.0
    assert len(report["manifest_fingerprints"]) == 3
    assert "NOT evidence of real LLM performance" in report["important_note"]
    assert "EXPERIMENT COMPLETE" in capsys.readouterr().out
