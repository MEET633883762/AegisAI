# AegisAI Phase 14 — Security Testing

Phase 14 validates the security boundaries required by the AegisAI research prototype.

## Scope

The security suite tests:

- LLM output/schema validation and fail-closed behavior
- controller authorization, role separation, turn ordering, and rate limits
- role-specific observation isolation and mutation safety
- prompt-injection handling in telemetry and retrieved threat intelligence
- adaptive-memory poisoning and held-out-data leakage controls
- bounded RAG context and untrusted-data labeling
- bounded experiment execution / termination behavior
- absence of direct command-execution primitives in the application source
- audit/XAI trace generation for denied actions

The tests do **not** prove that an arbitrary third-party LLM, OS, browser, network, or
production deployment is secure. They verify the controls implemented in this simulator-first
prototype.

## Security invariant

`LLM proposal -> structured schema -> controller validation -> policy/permission -> simulator`

The LLM is never an executor and never receives a simulator reference as part of the agent API.

## Out of scope

No real exploitation, production-system connectivity, arbitrary shell execution, or live CTI
network dependency is introduced by this phase.
