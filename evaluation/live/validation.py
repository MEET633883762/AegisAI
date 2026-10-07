"""Single-episode live integration validation with explicit safety gates."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from llm.provider import LLMProvider

from .config import LiveExperimentConfig
from .preflight import run_preflight
from .runner import LiveEpisodeResult, run_live_episode


@dataclass(frozen=True)
class LiveValidationResult:
    """Redacted validation result suitable for saving as an experiment artifact."""

    preflight_ready: bool
    live_attempted: bool
    integration_ok: bool
    status: str
    episode: LiveEpisodeResult | None
    message: str


def validate_single_live_episode(
    template_id: str,
    seed: int,
    config: LiveExperimentConfig,
    provider_factory: Callable[[str], LLMProvider],
    *,
    allow_live: bool = False,
) -> LiveValidationResult:
    """Run at most one explicitly authorized live episode.

    The default is fail-closed. Preflight occurs before provider construction, and
    the episode itself inherits all Phase 17 budgets.
    """
    if not allow_live:
        return LiveValidationResult(
            preflight_ready=False,
            live_attempted=False,
            integration_ok=False,
            status="refused",
            episode=None,
            message="live validation requires explicit allow_live=True",
        )

    preflight = run_preflight(config)
    if not preflight.ready_for_live_call:
        return LiveValidationResult(
            preflight_ready=False,
            live_attempted=False,
            integration_ok=False,
            status="preflight_failed",
            episode=None,
            message="live preflight failed; no provider call was attempted",
        )

    episode = run_live_episode(template_id, seed, config, provider_factory)
    # A completed episode is the strongest integration signal. An aborted episode
    # can still prove that the provider boundary was reached, but is not a successful
    # end-to-end validation because the controller/simulator path did not complete.
    integration_ok = episode.status == "completed" and episode.provider_usage.calls > 0
    message = (
        "single live episode completed successfully"
        if integration_ok
        else "provider path was attempted but the controlled episode did not complete"
    )
    return LiveValidationResult(
        preflight_ready=True,
        live_attempted=True,
        integration_ok=integration_ok,
        status=episode.status,
        episode=episode,
        message=message,
    )
