# Phase 17 Changelog

- Added `evaluation/live/config.py` for explicit live-experiment limits.
- Added `evaluation/live/budget.py` for provider-call and token accounting.
- Added `evaluation/live/runner.py` for bounded real-provider simulator episodes.
- Added `scripts/run_live_episode.py`; live calls require explicit `--live`.
- Added offline security/regression tests for budget exhaustion and provider failure.
- No simulator execution, shell execution, or real network target capability was added.
