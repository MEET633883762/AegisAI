# Research experiment protocol

The A/B/C protocol evaluates three configurations on the same held-out scenario/seed pairs:

| Configuration | Agents |
|---|---|
| A | Scripted Red and scripted Blue baseline. |
| B | Provider-backed Red and Blue without adaptive memory. |
| C | Provider-backed Red and Blue with validated adaptive-memory context. |

A provider-backed interface can be backed by an offline test double. Such a run verifies wiring and isolation; it is not evidence of real LLM performance. The public browser demo and the paired defender benchmark both use scripted policies.

## Leakage control and reproducibility

[`protocol.py`](protocol.py) rejects duplicate or overlapping train/validation/test pairs. Held-out test pairs cannot be adaptive-memory sources; declared source pairs must belong to training or validation. [`memory_gate.py`](memory_gate.py) renders only validated patches with complete, permitted scenario provenance into a bounded character budget.

The default split partitions scenario/seed pairs. `build_template_holdout_split()` instead holds out whole authored templates; this tests variation beyond seeds but still does not establish performance on independent real-world attack families. Each manifest records configuration, split, provider, model, temperature, seed, and whether memory is enabled; its SHA-256 fingerprint identifies that complete manifest.

The comparison exports adaptation and generalization improvement using a bounded defensive score derived from detection, mitigation, and attack-success rates. In the current implementation, both improvement fields represent the same held-out C-minus-B score difference; they are not independent experimental measurements.

## Offline harness check

Use the Python 3.11 environment in the [development guide](../../docs/DEVELOPMENT.md). From the repository root on Windows:

```powershell
py -3.11 scripts/run_offline_research.py
```

This script uses a deterministic test-double provider and writes `results/offline_research_result.json`. It overwrites that fixed file if it already exists, so preserve an earlier report first when needed. It makes no live provider call. Scientific B/C comparisons require a separately defined real-provider protocol, recorded limits, and repeatable evidence; the [single live validation](../../docs/PHASE19_LIVE_INTEGRATION_VALIDATION.md) is an integration check, not such a comparison.

The separate [`defender_benchmark.py`](defender_benchmark.py) compares two scripted defender policies and preserves paired outcomes and disruption evidence. See the [comparison guide](../../docs/DEFENDER_COMPARISON.md) and [current verification](../../docs/CURRENT_STATUS.md).
