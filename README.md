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

The public landing page and read-only research dashboard are a React + TypeScript application built with Vite. From PowerShell, run `cd C:\AegisAI\frontend`, `npm ci`, then `npm run dev` and open `http://localhost:5174/` on your computer. Vite prints a LAN URL for viewing on a phone connected to the same Wi-Fi; this development server is for a trusted local network only and may require a Private-network firewall permission. The dashboard is at `/dashboard.html`. The static release build is produced with `npm run build` from `frontend/`, then `python scripts/build_static_site.py --output dist/aegisai-release` from the repository root. Publish only the strict allowlisted output directory. See [frontend/README.md](frontend/README.md) and [docs/PHASE4_RELEASE_HARDENING_AND_DEPLOYMENT.md](docs/PHASE4_RELEASE_HARDENING_AND_DEPLOYMENT.md) for details.

The frontend remains read-only: it displays reviewed synthetic data, reads selected local assessment files in the browser, and compares fixed published samples. It does not run the simulator, scan visitor-provided URLs, or upload files.

The proposed future private-platform architecture, capability inventory, threat model, and phased roadmap are documented in [docs/PLATFORM_VISION_PHASE0_ARCHITECTURE.md](docs/PLATFORM_VISION_PHASE0_ARCHITECTURE.md). It does not change the public V1 boundary or authorize client connectivity.

## Local synthetic operations prototype

The separate Phase 1 CLI analyzes only schema-validated synthetic event fixtures and produces a labeled JSON incident report. It does not process client telemetry, run real detections, or execute response actions. Run `python scripts/run_platform_prototype.py` from the repository root. Scope, schema, policy, and cleanup details are in [docs/PHASE1_LOCAL_SYNTHETIC_SECURITY_OPS_PROTOTYPE.md](docs/PHASE1_LOCAL_SYNTHETIC_SECURITY_OPS_PROTOTYPE.md). The CLI and fixtures are excluded from the public static publisher allowlist.

The separate Phase 2 local API serves only persisted, validated synthetic reports over loopback with ephemeral development bearer tokens. Start it with `python scripts/run_private_api.py`; routes, token handling, tenant isolation, SQLite storage, audit behavior, and limitations are documented in [docs/PHASE2_PRIVATE_BACKEND_FOUNDATION.md](docs/PHASE2_PRIVATE_BACKEND_FOUNDATION.md). It is not connected to the public website, simulator Controller, or any client system.

The local API is development-only: it refuses non-local `AEGISAI_ENV` modes, keeps its bearer token in process memory, and binds only to loopback. Its authenticated liveness/readiness checks, request bounds, and token rotation guidance are documented in [docs/PHASE7A_LOCAL_DASHBOARD.md](docs/PHASE7A_LOCAL_DASHBOARD.md). It is not a production deployment configuration.

Phase 8 documents the deployment boundary: only the reviewed nine-file static artifact is a current deployment candidate; the private API, dashboard, and SQLite-backed workflows remain local prototypes. See [docs/PHASE8_DEPLOYMENT_ARCHITECTURE.md](docs/PHASE8_DEPLOYMENT_ARCHITECTURE.md). No deployment target was configured or published.

Phase 3 adds a bounded local scheduler for the fixed synthetic telemetry fixture, deterministic versioned rules, tenant-scoped SQLite findings/reports, and authenticated read-only telemetry routes. It has no HTTP ingestion route and remains separate from the static frontend and simulator Controller. See [docs/PHASE3_READ_ONLY_TELEMETRY_AND_DETECTION.md](docs/PHASE3_READ_ONLY_TELEMETRY_AND_DETECTION.md) for schemas, rules, scheduler limits, retention, and limitations. It does not process client telemetry or prove real-world detection accuracy.

Phase 4 adds an on-demand local replay CLI for the fixed hand-labeled synthetic scenario library. It reuses the Phase 3 detector, reports per-rule TP/FP/TN/FN, nullable precision/recall/F1, evidence completeness, and scenario coverage, and never writes to the scheduler database or runs from the website. See [docs/PHASE4_ISOLATED_REPLAY_AND_DETECTION_GAP_ANALYSIS.md](docs/PHASE4_ISOLATED_REPLAY_AND_DETECTION_GAP_ANALYSIS.md). The Phase 3 telemetry run/report and finding-observation history is now bounded by the documented local retention policy; audit rows and original assessment artifacts are not pruned.

Phase 5A adds a separate local-only CLI for one fixed, checked-in synthetic website access/error-log fixture: `python scripts/ingest_local_website_telemetry.py`. It reuses Phase 3 validation, detection, tenant-scoped SQLite persistence, deduplication, and audit records. It does not read live website logs or expose an ingestion API. See [docs/PHASE5A_LOCAL_WEBSITE_TELEMETRY_INTEGRATION.md](docs/PHASE5A_LOCAL_WEBSITE_TELEMETRY_INTEGRATION.md).

Phase 5B adds a separate loopback-only telemetry test website at `127.0.0.1:8767`, a fixed harmless traffic generator, and a bounded live-log ingestion CLI. It reads only its generated JSONL logs under the ignored `.aegisai-local/website-telemetry/` directory and reuses Phase 3's synthetic detector/store. See [docs/PHASE5B_LOCAL_LIVE_TELEMETRY_VALIDATION.md](docs/PHASE5B_LOCAL_LIVE_TELEMETRY_VALIDATION.md).

Phase 5C documents bounded replay recovery for live synthetic logs, a fixed three-generation rotation window, idempotent SQLite processing, and an authenticated read-only source-status view. The additive schema-v3 status table reports a snapshot fingerprint, counters, and sanitized error categories; it is not a durable archive or lossless checkpoint. See [docs/PHASE5C_TELEMETRY_RELIABILITY_AND_RECOVERY.md](docs/PHASE5C_TELEMETRY_RELIABILITY_AND_RECOVERY.md).

Phase 6A adds a separate versioned, synthetic evaluation dataset with explicit ground truth for the existing five detection rules. It covers positive, benign, boundary, duplicate, insufficient-evidence, malformed, and conflicting-input cases; it does not produce aggregate detection-accuracy metrics. See [docs/PHASE6A_EVALUATION_DATASET_AND_GROUND_TRUTH.md](docs/PHASE6A_EVALUATION_DATASET_AND_GROUND_TRUTH.md).

Phase 6B adds `python scripts/run_detection_evaluation.py`, a deterministic local evaluator for the fixed Phase 6A synthetic dataset. It reports scenario-by-rule confusion counts, nullable metrics, evidence diagnostics, and invalid-input outcomes separately; it does not alter rules or use the application database. The default JSON report is created under `results/evaluation/` without overwriting existing files. See [docs/PHASE6B_DETECTION_METRICS_AND_EVALUATION.md](docs/PHASE6B_DETECTION_METRICS_AND_EVALUATION.md); the synthetic metrics do not establish real-world accuracy.

Phase 6C audits the Phase 6B counts, adds a versioned synthetic robustness behavior suite, merges evidence across duplicate same-rule findings without inflating counts, and makes evaluator failures fail closed. It does not change the Phase 6A labels or detection rules. See [docs/PHASE6C_DETECTION_ROBUSTNESS_AND_REGRESSION.md](docs/PHASE6C_DETECTION_ROBUSTNESS_AND_REGRESSION.md).

Phase 7A adds a separate local React dashboard at `http://localhost:5174/local-dashboard.html` for authenticated read-only views of the existing synthetic API, including the `reports:read` Detection Lab summary. Phase 3 extends the existing Phase 6 evaluator with specificity, explicit scenario/rule coverage, ATT&CK coverage gaps, and opt-in bounded run history. See [docs/PHASE7A_LOCAL_DASHBOARD.md](docs/PHASE7A_LOCAL_DASHBOARD.md) and [docs/DETECTION_ENGINEERING_AND_EVALUATION.md](docs/DETECTION_ENGINEERING_AND_EVALUATION.md). The API still binds to loopback and allows browser CORS only from the two fixed local Vite origins. The strict public static publisher allowlist remains unchanged and excludes this dashboard and evaluation artifacts.

The investigation case layer adds tenant-scoped cases, verified references to existing telemetry evidence, explicitly labeled inferred relationships and analyst notes, bounded chronological history, and optional assessment/evaluation run context. Case writes require the opt-in local `investigations:write` token scope (`python scripts/run_private_api.py --enable-investigation-writes`); no AI assistant or response action is included. Details and limits: [docs/PHASE4_INVESTIGATION_CASES_AND_MEMORY.md](docs/PHASE4_INVESTIGATION_CASES_AND_MEMORY.md).

Phase 5 adds preview-first, explicitly authorized synthetic scenarios for the fixed loopback website. The catalog contains a health baseline and three empty-body requests to the site's harmless rejection route. Scenario reports link observed telemetry evidence, detection rules, applicable assessment check IDs, and telemetry reports; bounded schema-v6 history compares runs. See [docs/PHASE5_SAFE_PURPLE_TEAM_VALIDATION.md](docs/PHASE5_SAFE_PURPLE_TEAM_VALIDATION.md). Results do not establish real-world control effectiveness.

Phase 10 records release scope, verification evidence, deployment boundaries, and remaining approval gates in [docs/PHASE10_RELEASE_CANDIDATE.md](docs/PHASE10_RELEASE_CANDIDATE.md). Current release status is **BLOCKED** for production; no deployment or publication was performed.

The current repository and test baseline is documented in [docs/IMPLEMENTATION_BASELINE_AUDIT.md](docs/IMPLEMENTATION_BASELINE_AUDIT.md). It distinguishes recorded checks from unverified deployment and security work.
