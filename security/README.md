# Security-boundary regression checks

The security suite verifies implemented boundaries in AegisAI's controlled research simulator. A test pass is not an independent security audit or production certification.

## Scope

The checks cover structured LLM output validation, fail-closed provider errors, Controller permissions and turn/rate rules, role-scoped observations, untrusted telemetry/retrieval strings, evidence-grounded memory, held-out-data leakage, bounded context/experiments, and audit traces for denied actions. Source checks also look for direct command/network execution primitives in their explicitly scoped simulator modules; separate loopback website and API tools have their own tests and boundaries.

The core invariant is:

`LLM proposal → structured schema → Controller validation → permissions → simulator`

Agents receive neither the simulator nor Controller internals. The public browser site replays reviewed synthetic files, while local operations and optional live-provider experiments are separate entry points. See the [product boundary](../docs/PHASE1_PRODUCT_BOUNDARY_AND_THREAT_MODEL.md) and [current status](../docs/CURRENT_STATUS.md) for scope.

## Run offline checks

Use the Python 3.11 environment from [DEVELOPMENT.md](../docs/DEVELOPMENT.md). From the repository root on Windows, with dependencies installed:

```powershell
py -3.11 -m pytest -q tests/security
```

Pytest's cache belongs under `.aegisai-local/pytest-cache`; use a fresh `.aegisai-local/test-artifacts/` base directory for a full local run as documented in the development guide. Do not pass these software results off as protection against arbitrary providers, operating systems, browsers, networks, or production deployments. No real exploitation or production-system connectivity is exercised by these simulator-boundary tests.
