# Phase 15 Change Log

Implementation record for this milestone. Historical verification totals below are preserved; use the [development guide](DEVELOPMENT.md) for Python 3.11 setup and [current status](CURRENT_STATUS.md) for fresh project checks. The public browser walkthrough uses scripted agents and is separate from opt-in provider experiments.

- Added deterministic `ScenarioMetadata`.
- Expanded scenario library from 2 to 6 templates.
- Added experiment-side metadata without changing Red/Blue observation schemas.
- Added template-level holdout split builder for unseen-template evaluation.
- Added scenario diversity and metadata-leakage tests.
- Preserved existing Phase 1–14 behavior and APIs.
