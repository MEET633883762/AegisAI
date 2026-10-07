# AegisAI XAI — Phase 9

Phase 9 adds structured, evidence-grounded explainability traces.

## Design

Every controller decision produces a `DecisionTrace` containing:

- episode/scenario/step identity
- agent role
- role-visible observation snapshot
- concise evidence extracted from that observation
- structured selected action
- agent-generated rationale, when present
- deterministic reason category
- deterministic expected action intent
- factual environment outcome and success/failure
- state-change/event references
- optional provider/model/latency metadata
- optional post-hoc lesson field for later adaptive-memory work

The trace deliberately does **not** store hidden chain-of-thought. Explanations are treated as
agent-generated rationale and are kept separate from controller/environment facts.

## Security boundary

XAI is controller-owned. Agents do not receive the XAI logger, simulator, or controller internals.
Evidence is derived only from the same role-specific observation supplied to the agent.

## Later phases

Phase 10 may populate `post_hoc_lesson` only after explicit evidence-based failure analysis and
validation. Phase 9 itself does not create adaptive memory or modify model weights.
