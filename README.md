# AegisAI — Phase 8: LLM Red Agent

Controlled, simulator-first Red-vs-Blue research platform.

Phase 8 adds an observation-driven LLM Red agent on top of the provider abstraction from Phase 7.
The agent receives only `RedObservation`, requests one structured `RedAction`, and returns it to the
caller. The Controller remains the sole execution and authorization boundary.

## Run

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
pytest
```

Phase 8 does not require a real LLM API. Tests use `FakeLLMProvider` so behavior is deterministic and
safe. No shell commands, real network targets, or simulator mutations are available to the agent.

## Phase 9 — XAI

Phase 9 adds controller-owned `DecisionTrace` records and an append-only `XAILogger`. Every
submitted Red/Blue action, including rejected actions, gets a structured trace containing the
role-visible observation, evidence, selected action, rationale, reason category, expected intent,
and factual environment outcome. Hidden chain-of-thought is never captured.

## Phase 11
Threat-intelligence/RAG foundation added under `threat_intelligence/`. It is deterministic, offline, bounded, and treats retrieved material as untrusted data.

## Local website security demo

Start the loopback-only demo site with `python demo_site/server.py`, then check its security-header baseline in another terminal with `python scripts/check_demo_site.py`. See `demo_site/README.md` for scope and limitations.
