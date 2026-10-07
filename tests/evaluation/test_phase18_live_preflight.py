from evaluation.live.config import LiveExperimentConfig
from evaluation.live.preflight import run_preflight


def test_preflight_never_requires_network(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-used")
    result = run_preflight(LiveExperimentConfig(model="test-model"))
    assert result.api_key_configured is True
    assert result.model_configured is True
    assert result.config_valid is True
    assert isinstance(result.openai_sdk_installed, bool)


def test_preflight_reports_missing_key_without_exposing_secret(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    result = run_preflight(LiveExperimentConfig(model="test-model"))
    assert result.api_key_configured is False
    assert result.ready_for_live_call is False


def test_preflight_does_not_call_provider(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    calls = []
    monkeypatch.setattr("evaluation.live.preflight.version", lambda name: calls.append(name) or "test")
    result = run_preflight(LiveExperimentConfig(model="test-model"))
    assert result.ready_for_live_call is False
    assert calls == ["openai"]
