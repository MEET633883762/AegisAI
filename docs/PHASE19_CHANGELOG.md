# Phase 19 Changelog

Implementation record for this milestone. Historical verification totals below are preserved; use the [development guide](DEVELOPMENT.md) for Python 3.11 setup and [current status](CURRENT_STATUS.md) for fresh project checks. The public browser walkthrough uses scripted agents and is separate from opt-in provider experiments.

- Added `evaluation.live.validation.validate_single_live_episode`.
- Added fail-closed single-episode live integration CLI.
- Added defaults: 4 AegisAI provider invocations, a 2,000 reported-token threshold, 2 episode steps, 30s request timeout, and a 120s wall-clock budget. [Accounting limits](PHASE17_LIVE_EXPERIMENT_HARNESS.md#limits-and-accounting) distinguish these checks from transport/spend/process caps.
- Added redacted JSON result artifact support.
- Added tests for explicit live authorization, preflight gating, and bounded execution.
- Explicitly separated integration validation from research evidence.
