# Phase 6 — Metrics and Experiment Runner

Metrics are derived from controller-owned telemetry and audit evidence. Agents do not supply or alter metric values.

The Phase 6 runner executes deterministic scripted Red + Blue baseline trials with explicit scenario templates and seeds. Each episode creates fresh agent instances to prevent state leakage between trials.

Implemented metrics:
- Attack Success Rate
- Detection Rate
- Mean Detection Time
- Mitigation Success Rate
- False Positive Rate
- Decision Latency

Phase 6 intentionally does not add LLMs, databases, adaptive memory, RAG, or a frontend.
