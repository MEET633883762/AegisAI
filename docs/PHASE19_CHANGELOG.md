# Phase 19 Changelog

- Added `evaluation.live.validation.validate_single_live_episode`.
- Added fail-closed single-episode live integration CLI.
- Added strict defaults: 4 provider calls, 2,000 total tokens, 2 episode steps, 30s request timeout, 120s wall-clock budget.
- Added redacted JSON result artifact support.
- Added tests for explicit live authorization, preflight gating, and bounded execution.
- Explicitly separated integration validation from research evidence.
