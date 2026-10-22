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

Start the loopback-only demo site with `python demo_site/server.py`, then check it in another terminal with `python scripts/check_demo_site.py`. The checker preserves profile-specific JSON reports under `results/`; load one or both in the read-only frontend dashboard. See `demo_site/README.md` for the baseline/hardened workflow and limitations.

## Static frontend

The public landing page and read-only research dashboard are a React + TypeScript application built with Vite. From PowerShell, run `cd C:\AegisAI\frontend`, `npm ci`, then `npm run dev` and open `http://127.0.0.1:5173/`. The dashboard is at `/dashboard.html`. The static release build is produced with `npm run build` from `frontend/`, then `python scripts/build_static_site.py --output dist/aegisai-release` from the repository root. Publish only the strict allowlisted output directory. See [frontend/README.md](frontend/README.md) and [docs/PHASE4_RELEASE_HARDENING_AND_DEPLOYMENT.md](docs/PHASE4_RELEASE_HARDENING_AND_DEPLOYMENT.md) for details.

The frontend remains read-only: it displays reviewed synthetic data, reads selected local assessment files in the browser, and compares fixed published samples. It does not run the simulator, scan visitor-provided URLs, or upload files.
