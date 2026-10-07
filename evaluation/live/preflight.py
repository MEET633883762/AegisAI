"""Offline preflight checks for a controlled AegisAI live-LLM run."""
from __future__ import annotations

import os
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version

from .config import LiveExperimentConfig


@dataclass(frozen=True)
class LivePreflight:
    api_key_configured: bool
    model_configured: bool
    openai_sdk_installed: bool
    openai_sdk_version: str | None
    config_valid: bool

    @property
    def ready_for_live_call(self) -> bool:
        return (
            self.api_key_configured
            and self.model_configured
            and self.openai_sdk_installed
            and self.config_valid
        )


def run_preflight(config: LiveExperimentConfig) -> LivePreflight:
    """Check local live-run prerequisites without contacting any external service."""
    key = os.getenv("OPENAI_API_KEY", "").strip()
    try:
        sdk_version = version("openai")
        sdk_installed = True
    except PackageNotFoundError:
        sdk_version = None
        sdk_installed = False

    return LivePreflight(
        api_key_configured=bool(key),
        model_configured=bool(config.model.strip()),
        openai_sdk_installed=sdk_installed,
        openai_sdk_version=sdk_version,
        config_valid=True,
    )
