# Phase 17 Changelog

Implementation record for this milestone. Historical verification totals below are preserved; use the [development guide](DEVELOPMENT.md) for Python 3.11 setup and [current status](CURRENT_STATUS.md) for fresh project checks. The public browser walkthrough uses scripted agents and is separate from opt-in provider experiments.

- Added `evaluation/live/config.py` for explicit live-experiment limits.
- Added `evaluation/live/budget.py` for provider-call and token accounting.
- Added `evaluation/live/runner.py` for bounded real-provider simulator episodes.
- Added `scripts/run_live_episode.py`; live calls require explicit `--live`.
- Added offline security/regression tests for budget exhaustion and provider failure.
- Simulated action execution remains behind the existing Controller; no shell execution or real network target capability was added.
