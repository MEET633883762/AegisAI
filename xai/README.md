# Controller-owned decision evidence

`DecisionTrace` records structured explanations grounded in role-visible observations. An agent-generated rationale is distinct from Controller authorization and factual simulator outcomes; hidden chain-of-thought is not recorded.

## Trace contents

A trace includes episode/scenario/step identity, role-visible observation, extracted evidence, the structured proposed action, rationale when supplied, deterministic reason/intent fields, authorization and actual outcome, state-change/event references, and optional provider/model/latency metadata. A post-hoc lesson field supports later evidence-based analysis; it does not itself validate adaptive memory.

Agents do not receive the logger, simulator, or Controller internals. [`logger.py`](logger.py) rejects duplicate trace IDs and stores copied traces in memory; its explicit `clear()` resets the store. This is not durable append-only storage or a production audit service.

## Public evidence versus internal traces

The public walkthrough exports a reviewed synthetic subset with role-scoped evidence and no internal state-change/event-reference fields. Its searchable timeline, action detail panel, provenance, metrics, and JSON download help viewers inspect recorded decisions; selecting a step does not execute an action. The internal `DecisionTrace` schema remains more detailed than that public artifact.

Use the Python 3.11 [development environment](../docs/DEVELOPMENT.md). From the repository root on Windows, with dependencies installed:

```powershell
py -3.11 -m pytest -q tests/unit/test_xai.py
```

See [adaptive memory](../memory/README.md) for the separate validation lifecycle and [current status](../docs/CURRENT_STATUS.md) for fresh project checks. Phase 9 identifies this trace layer's implementation history.
