# Evidence-grounded adaptive memory

Adaptive memory stores versioned knowledge patches; it does not retrain model weights. Candidate lessons come from role-visible XAI evidence and are never accepted merely because a model generated them.

## Patch lifecycle

`Attack evidence → failure analysis → candidate patch → measured validation → versioned memory → later retest`

[`failure_analyzer.py`](failure_analyzer.py) creates candidates from recorded trace evidence. [`validator.py`](validator.py) takes externally supplied baseline/candidate measurements, requires a held-out result and the configured minimum improvement, and records the decision. Its metric is higher-is-better; callers must transform measures such as attacker success into an appropriate defensive score.

[`repository.py`](repository.py) maintains copied current patches and append-only version entries in memory. Revocation adds a new version and preserves earlier entries; this is not a durable database or an immutable audit service. Candidate, validated, rejected, and revoked states remain explicit.

## Context boundary

The [experiment memory gate](../evaluation/experiments/memory_gate.py) renders only validated patches whose scenario references resolve to declared non-test sources. Malformed/mixed provenance, held-out leakage, and the complete rendered character budget are checked. Context is non-executable data: it does not change Controller policy or run simulator actions.

Prepare the Python 3.11 [development environment](../docs/DEVELOPMENT.md). From the repository root on Windows, with dependencies installed:

```powershell
py -3.11 -m pytest -q tests/unit/test_memory.py tests/security/test_security_boundaries.py
```

These offline tests establish implementation behavior, not learned adaptation or generalization to real attacks. The public walkthrough uses scripted policies and does not build adaptive memory. See [current verification](../docs/CURRENT_STATUS.md) and the [A/B/C research protocol](../evaluation/experiments/README.md).
