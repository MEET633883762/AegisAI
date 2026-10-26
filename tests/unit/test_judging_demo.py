"""Judge-demo preparation must measure fresh results and fail visibly on drift."""

from __future__ import annotations

import hashlib
import json

from scripts import run_judging_demo as cli


def test_real_preflight_replays_current_controller_and_evaluation():
    episode, evaluation_json, verification = cli.run_checks()
    evaluation = json.loads(evaluation_json)
    assert verification["status"] == "passed"
    assert all(check["passed"] for check in verification["checks"])
    assert verification["episode"]["recorded_actions"] == len(episode["records"])
    assert verification["evaluation"]["accepted_scenarios"] == evaluation["valid_scenario_count"]
    assert verification["evaluation"]["counts"] == evaluation["counts"]
    assert verification["evaluation"]["dataset_sha256"] == evaluation["dataset_sha256"]


def test_preflight_fails_when_published_browser_sample_is_stale(tmp_path, monkeypatch, capsys):
    published = tmp_path / "stale.json"
    published.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(cli, "PUBLISHED_EPISODE_PATH", published)
    monkeypatch.setattr(cli, "OUTPUT_ROOT", tmp_path / "must-not-write")
    assert cli.main(["--check"]) == 1
    output = capsys.readouterr().out
    assert "[FAIL] Published replay" in output
    assert "build_public_demo_artifact.py" in output
    assert not cli.OUTPUT_ROOT.exists()


def test_preflight_detects_nondeterministic_episode(monkeypatch):
    real_build = cli.build_artifact
    calls = 0

    def inconsistent_build():
        nonlocal calls
        calls += 1
        episode = real_build()
        episode["provenance"]["seed"] = calls
        return episode

    monkeypatch.setattr(cli, "build_artifact", inconsistent_build)
    _, _, verification = cli.run_checks()
    assert verification["status"] == "failed"
    assert not verification["checks"][0]["passed"]


def test_each_preparation_preserves_previous_packet(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "OUTPUT_ROOT", tmp_path)
    episode, evaluation_json, verification = cli.run_checks()
    first = cli.write_packet(episode, evaluation_json, verification)
    previous_bytes = {path.name: path.read_bytes() for path in first.iterdir()}
    second = cli.write_packet(episode, evaluation_json, verification)
    assert first != second
    assert {path.name: path.read_bytes() for path in first.iterdir()} == previous_bytes
    assert set(previous_bytes) == {"episode.json", "detection-evaluation.json", "verification.json", "guide.txt"}
    assert json.loads((second / "verification.json").read_text(encoding="utf-8"))["status"] == "passed"
    assert hashlib.sha256((second / "episode.json").read_bytes()).hexdigest() == verification["episode"]["sha256"]
    assert hashlib.sha256((second / "detection-evaluation.json").read_bytes()).hexdigest() == verification["evaluation"]["sha256"]


def test_missing_fixture_fails_with_actionable_message(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "DATASET_PATH", tmp_path / "missing-fixture.json")
    assert cli.main(["--check"]) == 1
    assert "missing-fixture.json" in capsys.readouterr().err
