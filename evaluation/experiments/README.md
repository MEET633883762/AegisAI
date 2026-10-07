# Phase 13 — Experiments

Phase 13 provides the research experiment protocol for AegisAI.

## Configurations

- **A:** Scripted Red + Scripted Blue baseline.
- **B:** LLM Red + LLM Blue without adaptive memory.
- **C:** LLM Red + LLM Blue with validated adaptive memory.

All three configurations use the same held-out scenario/seed set for the comparison.

## Leakage control

Scenario/seed pairs are partitioned into train, validation, and held-out test sets. Test pairs are
never permitted as adaptive-memory sources. Memory is rendered only from validated patches whose
evidence can be traced to permitted non-test source pairs.

## Reproducibility

Each experiment manifest records experiment ID, configuration, split, provider, model, temperature,
and seed. A SHA-256 fingerprint identifies the complete manifest.

## Metrics

The existing metrics runner supplies attack success rate, detection rate, mean detection time,
mitigation success rate, false-positive rate, and decision latency. Phase 13 adds comparison-level
adaptation/generalization improvement based on a bounded defensive score.

## Important limitation

The repository's offline test-double is **not** a real LLM and must not be presented as experimental
LLM evidence. Scientific B/C runs require a real provider adapter implementing the existing
provider-neutral interface. The test-double only proves that LLM-agent wiring, experiment isolation,
and leakage controls work without network access.
