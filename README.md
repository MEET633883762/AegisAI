# AegisAI — see the attack, understand the defense

AegisAI is a controlled cybersecurity research lab. It shows how a simulated attacker gets into a fictional network, what a defender notices, and whether the defender stops the attack.

The browser demo tells that story in six key moments, with a network map, plain-language explanations, and the actual recorded outcome. Expand any action to inspect the evidence and permission checks behind it.

**The key insight:** noticing a threat does not always mean stopping it. In the current example, the defender detects 8 of 9 malicious alerts but mitigates 0 of 6 response-required alerts, and the attacker reaches its simulated goal. Showing that failure gives researchers a clear target for improving defensive decisions.

**Current setup and verification:** [the 2026-10-27 implementation snapshot](docs/CURRENT_STATUS.md) records the supported runtime, all three browser routes, and fresh test results. Use Python 3.11 for the backend; an unqualified `python` may still select an older installation.

**Presenting to judges?** Start with the [judges' guide](docs/JUDGES_GUIDE.md), open the [public demo](http://localhost:5174/), and follow the recorded exercise. The [documentation index](docs/README.md) points to the architecture, evidence, setup, and local operations prototype.

## Improve and measure the defense

The engine now includes `EvidencePrioritizedBlueAgent`, a second defender that responds to investigated urgent threat evidence before taking on more alerts. It confirms containment from the next observation instead of assuming a requested action succeeded. The historical baseline remains available for comparison.

Run a fresh paired comparison from the repository root:

```powershell
py -3.11 scripts/run_defender_benchmark.py
```

Across the six checked-in templates and five fixed seeds, the baseline allowed the attacker to reach its objective in **3 of 30** runs; the new policy allowed **0 of 30**. There were **3 improved pairs, 0 regressions, and 27 unchanged pairs**. The candidate isolates the simulated website, so it has an availability cost: mean final isolated hosts increased from **0.83 to 1.00**. These authored development cases share an attack structure; they do not establish independent or real-world effectiveness.

The [comparison report and method](docs/DEFENDER_COMPARISON.md) explain the paired evidence, disruption cost, and limitations. The full Python suite reruns the benchmark and checks it against the reviewed report.

## Try the demo

From the repository root in PowerShell, install the frontend dependencies and start the local server:

```powershell
npm.cmd --prefix frontend ci
npm.cmd --prefix frontend run dev -- --host 127.0.0.1
```

Open **[http://localhost:5174/](http://localhost:5174/)**, then choose the walkthrough. The direct demo URL is **[http://localhost:5174/dashboard.html](http://localhost:5174/dashboard.html)**. Use **Next moment** to follow the story, then compare the baseline and hardened website-header samples.

Choose **Present demo** in the dashboard navigation to focus the exercise and enlarge the text for projection. Choose **Exit presentation** or **Esc** to return to the full dashboard. Focus the player to use Left/Right and Home/End. The evidence panel supports role filters and search; the landing page includes a research FAQ.

This browser demo needs Node.js 22.12 or later. After dependencies are installed, it works without internet access, an API key, or the Python backend. It replays reviewed output from scripted simulator agents; it does not run an AI model in the browser.

## Open the local operations dashboard

This is a separate synthetic prototype with findings, Detection Lab, scenarios, assessments, executive reports, cases, and system health. After the Python setup below, start its API in another terminal:

```powershell
.\.venv\Scripts\python.exe scripts/run_private_api.py
```

With the Vite server running, open [http://localhost:5174/local-dashboard.html](http://localhost:5174/local-dashboard.html) and enter the API's current startup bearer token. If the dependencies are already installed directly in Python 3.11, `py -3.11 scripts/run_private_api.py` is an explicit Windows alternative. The token stays in page memory; the private API and dashboard are excluded from the public static package. See [the local dashboard guide](docs/PHASE7A_LOCAL_DASHBOARD.md) and the [Python version-mismatch fix](docs/DEVELOPMENT.md#python-version-mismatch-strenum).

## Verify the work behind the demo

The Python engine generates the evidence shown in the browser. From the repository root, create an isolated Python 3.11 environment and run the offline demo checks:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-demo.txt
.\.venv\Scripts\python.exe scripts/run_judging_demo.py
```

The [demo preflight](scripts/run_judging_demo.py) reruns the simulator and fixed synthetic detection evaluation, checks that repeated runs match, and verifies the published episode against the current code. It creates a fresh evidence packet under `.aegisai-local/judging-demo/` without overwriting previous runs. Use `--check` to verify without creating a packet.

For a presentation pitch, suggested walkthrough, likely questions, and rehearsal checklist, see the **[judges' guide](docs/JUDGES_GUIDE.md)**.

For pinned Windows/Linux setup and the automated verification workflow, see [DEVELOPMENT.md](docs/DEVELOPMENT.md). Local validation has been run on Windows; hosted CI results must be checked after the workflow is pushed.

## How it works

| Part | What it does |
|---|---|
| Attacker (Red) | Proposes a simulated action using the evidence it can see. |
| Defender (Blue) | Investigates alerts and proposes defensive actions. |
| Controller | Checks action structure, role permissions, turn order, and submission limits before execution. |
| Simulator | Applies permitted actions to a fictional network and records what happened. |
| Evidence and evaluation | Connect decisions to observations, authorization, and outcomes; make experiments repeatable. |
| Browser walkthrough | Explains the recorded exercise and lets viewers inspect its supporting evidence. |

The repository also contains structured LLM-agent adapters and experiment tools, plus a separate local synthetic operations prototype with telemetry, findings, investigations, and reports. The public walkthrough uses scripted policies for repeatability. Synthetic demonstrations and test passes do not establish real-world detection accuracy or production readiness.

## Check and build

```powershell
$pytestBase = Join-Path (Get-Location) ('.aegisai-local/test-artifacts/run-' + [guid]::NewGuid().ToString('N'))
.\.venv\Scripts\python.exe -m pytest -q --basetemp $pytestBase
npm.cmd --prefix frontend test
```

To assemble the reviewed static website into a new, empty output directory:

```powershell
npm.cmd --prefix frontend run build
.\.venv\Scripts\python.exe scripts/build_static_site.py --output dist/aegisai-release
```

The static publisher includes only the public pages, compiled assets, and reviewed sample files. The private operations dashboard and API remain local development tools. See [frontend/README.md](frontend/README.md) for page behavior and build boundaries.

## Find your way around

| Location | Purpose |
|---|---|
| `frontend/` | Public landing page, recorded walkthrough, and the separate local operations UI. |
| `agents/`, `controller/`, `environment/` | Agent policies, permission checks, and the synthetic network simulator. |
| `evaluation/`, `telemetry/`, `xai/` | Reproducible experiments, observations, and decision evidence. |
| `platform_prototype/`, `private_api/` | Separate local synthetic operations backend and authenticated API. |
| `demo_site/`, `local_assessment/`, `purple_team/` | Fixed local website demonstrations and validation tools. |
| `llm/`, `memory/`, `threat_intelligence/`, `security/` | Provider adapters, validated memory, offline retrieval, and policy checks. |
| `scripts/`, `tests/` | Runnable workflows and regression checks. |
| `docs/`, `results/` | Presentation guides, architecture, and preserved research evidence. |
| `.aegisai-local/`, `dist/` | Ignored local runs, databases, test artifacts, and generated release packages. |

Python packages retain their existing import paths. Historical handoff notes and decisions are in [docs/history/](docs/history/README.md); the [documentation index](docs/README.md) is the current entry point. Generated test folders belong under `.aegisai-local/test-artifacts/`, keeping the project root focused on source and configuration.

<details>
<summary>Implementation history and detailed subsystem documentation</summary>

## Historical simulator milestone: Phase 8 LLM Red Agent

Phase 8 added an observation-driven LLM Red agent on top of the provider abstraction from Phase 7.
The agent receives only `RedObservation`, requests one structured `RedAction`, and returns it to the
caller. The Controller remains the sole execution and authorization boundary.

Phase 8 does not require a real LLM API. Tests use `FakeLLMProvider` so behavior is deterministic.
No shell commands or real network targets are available to the agent; simulator mutations pass through the Controller.

## Phase 9 — XAI

Phase 9 adds controller-owned `DecisionTrace` records and an append-only `XAILogger`. Every
submitted Red/Blue action, including rejected actions, gets a structured trace containing the
role-visible observation, evidence, selected action, rationale, reason category, expected intent,
and factual environment outcome. Hidden chain-of-thought is never captured.

## Phase 11
Threat-intelligence/RAG foundation added under `threat_intelligence/`. It is deterministic, offline, bounded, and treats retrieved material as untrusted data.

## Local website security demo

Start the loopback-only demo site with `py -3.11 demo_site/server.py`, then check it in another terminal with `py -3.11 scripts/check_demo_site.py`. The checker preserves profile-specific JSON reports under `results/`; load one or both in the read-only frontend dashboard. See `demo_site/README.md` for the baseline/hardened workflow and limitations.

## Static frontend

The public landing page and read-only research dashboard are a React + TypeScript application built with Vite. Use the repository-relative startup and build commands above. The dashboard is at `/dashboard.html`. Publish only the strict allowlisted output directory. See [frontend/README.md](frontend/README.md) and [docs/PHASE4_RELEASE_HARDENING_AND_DEPLOYMENT.md](docs/PHASE4_RELEASE_HARDENING_AND_DEPLOYMENT.md) for details.

The frontend remains read-only: it displays reviewed synthetic data, reads selected local assessment files in the browser, and compares fixed published samples. It does not run the simulator, scan visitor-provided URLs, or upload files.

The proposed future private-platform architecture, capability inventory, threat model, and phased roadmap are documented in [docs/PLATFORM_VISION_PHASE0_ARCHITECTURE.md](docs/PLATFORM_VISION_PHASE0_ARCHITECTURE.md). It does not change the public V1 boundary or authorize client connectivity.

## Local synthetic operations prototype

The separate Phase 1 CLI analyzes only schema-validated synthetic event fixtures and produces a labeled JSON incident report. It does not process client telemetry, run real detections, or execute response actions. Run `py -3.11 scripts/run_platform_prototype.py` from the repository root. Scope, schema, policy, and cleanup details are in [docs/PHASE1_LOCAL_SYNTHETIC_SECURITY_OPS_PROTOTYPE.md](docs/PHASE1_LOCAL_SYNTHETIC_SECURITY_OPS_PROTOTYPE.md). The CLI and fixtures are excluded from the public static publisher allowlist.

The separate Phase 2 local API serves only persisted, validated synthetic reports over loopback with ephemeral development bearer tokens. Start it with `py -3.11 scripts/run_private_api.py`; routes, token handling, tenant isolation, SQLite storage, audit behavior, and limitations are documented in [docs/PHASE2_PRIVATE_BACKEND_FOUNDATION.md](docs/PHASE2_PRIVATE_BACKEND_FOUNDATION.md). It is not connected to the public website, simulator Controller, or any client system.

The local API is development-only: it refuses non-local `AEGISAI_ENV` modes, keeps its bearer token in process memory, and binds only to loopback. Its authenticated liveness/readiness checks, request bounds, and token rotation guidance are documented in [docs/PHASE7A_LOCAL_DASHBOARD.md](docs/PHASE7A_LOCAL_DASHBOARD.md). It is not a production deployment configuration.

Phase 8 documents the deployment boundary: only the reviewed nine-file static artifact is a current deployment candidate; the private API, dashboard, and SQLite-backed workflows remain local prototypes. See [docs/PHASE8_DEPLOYMENT_ARCHITECTURE.md](docs/PHASE8_DEPLOYMENT_ARCHITECTURE.md). No deployment target was configured or published.

Phase 3 adds a bounded local scheduler for the fixed synthetic telemetry fixture, deterministic versioned rules, tenant-scoped SQLite findings/reports, and authenticated read-only telemetry routes. It has no HTTP ingestion route and remains separate from the static frontend and simulator Controller. See [docs/PHASE3_READ_ONLY_TELEMETRY_AND_DETECTION.md](docs/PHASE3_READ_ONLY_TELEMETRY_AND_DETECTION.md) for schemas, rules, scheduler limits, retention, and limitations. It does not process client telemetry or prove real-world detection accuracy.

Phase 4 adds an on-demand local replay CLI for the fixed hand-labeled synthetic scenario library. It reuses the Phase 3 detector, reports per-rule TP/FP/TN/FN, nullable precision/recall/F1, evidence completeness, and scenario coverage, and never writes to the scheduler database or runs from the website. See [docs/PHASE4_ISOLATED_REPLAY_AND_DETECTION_GAP_ANALYSIS.md](docs/PHASE4_ISOLATED_REPLAY_AND_DETECTION_GAP_ANALYSIS.md). The Phase 3 telemetry run/report and finding-observation history is now bounded by the documented local retention policy; audit rows and original assessment artifacts are not pruned.

Phase 5A adds a separate local-only CLI for one fixed, checked-in synthetic website access/error-log fixture: `py -3.11 scripts/ingest_local_website_telemetry.py`. It reuses Phase 3 validation, detection, tenant-scoped SQLite persistence, deduplication, and audit records. It does not read live website logs or expose an ingestion API. See [docs/PHASE5A_LOCAL_WEBSITE_TELEMETRY_INTEGRATION.md](docs/PHASE5A_LOCAL_WEBSITE_TELEMETRY_INTEGRATION.md).

Phase 5B adds a separate loopback-only telemetry test website at `127.0.0.1:8767`, a fixed harmless traffic generator, and a bounded live-log ingestion CLI. It reads only its generated JSONL logs under the ignored `.aegisai-local/website-telemetry/` directory and reuses Phase 3's synthetic detector/store. See [docs/PHASE5B_LOCAL_LIVE_TELEMETRY_VALIDATION.md](docs/PHASE5B_LOCAL_LIVE_TELEMETRY_VALIDATION.md).

Phase 5C documents bounded replay recovery for live synthetic logs, a fixed three-generation rotation window, idempotent SQLite processing, and an authenticated read-only source-status view. The additive schema-v3 status table reports a snapshot fingerprint, counters, and sanitized error categories; it is not a durable archive or lossless checkpoint. See [docs/PHASE5C_TELEMETRY_RELIABILITY_AND_RECOVERY.md](docs/PHASE5C_TELEMETRY_RELIABILITY_AND_RECOVERY.md).

Phase 6A adds a separate versioned, synthetic evaluation dataset with explicit ground truth for the existing five detection rules. It covers positive, benign, boundary, duplicate, insufficient-evidence, malformed, and conflicting-input cases; it does not produce aggregate detection-accuracy metrics. See [docs/PHASE6A_EVALUATION_DATASET_AND_GROUND_TRUTH.md](docs/PHASE6A_EVALUATION_DATASET_AND_GROUND_TRUTH.md).

Phase 6B adds `py -3.11 scripts/run_detection_evaluation.py`, a deterministic local evaluator for the fixed Phase 6A synthetic dataset. It reports scenario-by-rule confusion counts, nullable metrics, evidence diagnostics, and invalid-input outcomes separately; it does not alter rules or use the application database. The default JSON report is created under `results/evaluation/` without overwriting existing files. See [docs/PHASE6B_DETECTION_METRICS_AND_EVALUATION.md](docs/PHASE6B_DETECTION_METRICS_AND_EVALUATION.md); the synthetic metrics do not establish real-world accuracy.

Phase 6C audits the Phase 6B counts, adds a versioned synthetic robustness behavior suite, merges evidence across duplicate same-rule findings without inflating counts, and makes evaluator failures fail closed. It does not change the Phase 6A labels or detection rules. See [docs/PHASE6C_DETECTION_ROBUSTNESS_AND_REGRESSION.md](docs/PHASE6C_DETECTION_ROBUSTNESS_AND_REGRESSION.md).

Phase 7A adds a separate local React dashboard at `http://localhost:5174/local-dashboard.html` for authenticated read-only views of the existing synthetic API, including the `reports:read` Detection Lab summary. The Detection Lab extends the existing Phase 6 evaluator with specificity, explicit scenario/rule coverage, ATT&CK coverage gaps, and opt-in bounded run history. See [docs/PHASE7A_LOCAL_DASHBOARD.md](docs/PHASE7A_LOCAL_DASHBOARD.md) and [docs/DETECTION_ENGINEERING_AND_EVALUATION.md](docs/DETECTION_ENGINEERING_AND_EVALUATION.md). The API still binds to loopback and allows browser CORS only from the two fixed local Vite origins. The strict public static publisher allowlist remains unchanged and excludes this dashboard and evaluation artifacts.

The investigation case layer adds tenant-scoped cases, verified references to existing telemetry evidence, explicitly labeled inferred relationships and analyst notes, bounded chronological history, and optional assessment/evaluation run context. Case writes require the opt-in local `investigations:write` token scope (`py -3.11 scripts/run_private_api.py --enable-investigation-writes`); no AI assistant or response action is included. Details and limits: [docs/PHASE4_INVESTIGATION_CASES_AND_MEMORY.md](docs/PHASE4_INVESTIGATION_CASES_AND_MEMORY.md).

Phase 5 adds preview-first, explicitly authorized synthetic scenarios for the fixed loopback website. The catalog contains a health baseline and three empty-body requests to the site's harmless rejection route. Scenario reports link observed telemetry evidence, detection rules, applicable assessment check IDs, and telemetry reports; bounded schema-v6 history compares runs. See [docs/PHASE5_SAFE_PURPLE_TEAM_VALIDATION.md](docs/PHASE5_SAFE_PURPLE_TEAM_VALIDATION.md). Results do not establish real-world control effectiveness.

Phase 10 records release scope, verification evidence, deployment boundaries, and remaining approval gates in [docs/PHASE10_RELEASE_CANDIDATE.md](docs/PHASE10_RELEASE_CANDIDATE.md). Current release status is **BLOCKED** for production; no deployment or publication was performed.

The current repository and test baseline is documented in [docs/IMPLEMENTATION_BASELINE_AUDIT.md](docs/IMPLEMENTATION_BASELINE_AUDIT.md). It distinguishes recorded checks from unverified deployment and security work.

</details>
