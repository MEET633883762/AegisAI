# AegisAI project handoff

> Historical snapshot from 2026-10-24. Product descriptions below record that handoff and may predate later work. Runnable examples were refreshed for explicit Python 3.11 and repository-relative paths. For current behavior and verification, use [CURRENT_STATUS.md](../CURRENT_STATUS.md), the [documentation index](../README.md), and [development guide](../DEVELOPMENT.md).

Updated 2026-10-24. Inspect `git status` and current files before relying on this note.

## Product and architecture

AegisAI is a controlled simulator-first Red/Blue cybersecurity research project. Agents propose typed actions; the Controller validates and authorizes them before the deterministic synthetic environment applies them. The repository includes telemetry, audit/XAI traces, adaptive-memory validation, offline threat-intelligence retrieval, experiment tooling, and a local-only website header demo. A successful test suite is not evidence of real-world security effectiveness.

The public V1 direction is a static, read-only research/demo website using reviewed precomputed synthetic examples. It is not a hosted SaaS or general vulnerability scanner. The Python simulator, Controller, experiments, LLM providers, and local website checker are not part of the public static build.

The longer-term private-platform vision is still proposed. Its verified capability matrix, trust-boundary design, threat model, open decisions, and gated roadmap are in [docs/PLATFORM_VISION_PHASE0_ARCHITECTURE.md](../PLATFORM_VISION_PHASE0_ARCHITECTURE.md). No client-facing backend, real telemetry collection, or production response is implemented or authorized by that proposal.

The Phase 1 local synthetic operations CLI is documented in [docs/PHASE1_LOCAL_SYNTHETIC_SECURITY_OPS_PROTOTYPE.md](../PHASE1_LOCAL_SYNTHETIC_SECURITY_OPS_PROTOTYPE.md). It uses bounded Pydantic validation, deterministic synthetic-event correlation, and an independent simulation policy. It has no persistence, scheduler, network integration, or real response; its files are outside the public static publish allowlist.

The Phase 2 local private API is documented in [docs/PHASE2_PRIVATE_BACKEND_FOUNDATION.md](../PHASE2_PRIVATE_BACKEND_FOUNDATION.md). It binds only to `127.0.0.1`, uses random expiring development tokens mapped server-side to read-only tenant principals, and persists only validated synthetic fixture reports in ignored local SQLite storage. It has no registration, write routes, client integrations, real response, or public frontend connection. It does not use or modify the simulator Controller.

## Frontend

The following description records the handoff. Current public pages use real reviewed episode metrics and have removed the illustrative legacy section; see [the frontend guide](../../frontend/README.md) for the current controls and page map.

The frontend now uses React + TypeScript + Vite as a multi-page app. Existing URLs remain `/`, `/dashboard.html`, and `/privacy.html`; there is no client router or service worker. The dashboard retains the precomputed Red/Blue timeline, role-scoped evidence, structured decision/authorization data, metrics/provenance, sample download, local assessment import, fixed same-origin assessment samples, comparison, and the clearly labeled illustrative legacy section.

The public browser can load only reviewed static JSON assets. It cannot run the simulator, invoke the Controller, execute simulations, scan visitor-supplied targets, upload selected reports, or call an LLM. React displays untrusted report text as text. The static publisher uses an explicit asset allowlist and copies no Python, tests, Git metadata, or original `results/` reports.

For the current local preview, run from the repository root in PowerShell. Python examples below assume reviewed dependencies are installed in Python 3.11; substitute `.\.venv\Scripts\python.exe` after the development setup when using its virtual environment:

```powershell
npm.cmd --prefix frontend ci
npm.cmd --prefix frontend run dev -- --host 127.0.0.1
```

Open `http://localhost:5174/` on the development computer. The explicit host above binds Vite to loopback. Its package default can listen on all interfaces for trusted development; public hosting must use the static publisher output. The public walkthrough is at `/dashboard.html`, while `/local-dashboard.html` is the separate operations prototype. On Windows, run frontend scripts with `npm.cmd`; if Windows Temp causes pytest access errors, use a fresh unique project-local temp base: `$pytestBase = Join-Path (Get-Location) ('.aegisai-local/test-artifacts/run-' + [guid]::NewGuid().ToString('N')); py -3.11 -m pytest -q --basetemp $pytestBase`.

For a static output build, run `npm.cmd --prefix frontend run build` from the repository root, then `py -3.11 scripts/build_static_site.py --output dist/aegisai-release`. Choose a new empty output folder; the publisher refuses populated folders. Publish only that generated allowlisted folder. No public deployment has been performed.

See [frontend/README.md](../../frontend/README.md), [docs/FRONTEND_MIGRATION_AUDIT.md](../FRONTEND_MIGRATION_AUDIT.md), and [docs/PHASE4_RELEASE_HARDENING_AND_DEPLOYMENT.md](../PHASE4_RELEASE_HARDENING_AND_DEPLOYMENT.md).

## Local website header demo

The local demo server binds to `127.0.0.1:8765`. Start it with `py -3.11 demo_site/server.py --profile baseline` or `--profile hardened`; in another terminal run `py -3.11 scripts/check_demo_site.py`. The checker only evaluates HTTP status and four configured security headers against the fixed loopback target. Baseline findings and hardened pass are expected for those two local profiles. The checker is not a general-purpose scanner.

Reports are written under `results/` as original local evidence. Do not overwrite, sanitize in place, or publish them. Reviewed public copies live under `frontend/data/` and omit machine-specific artifact paths. Regeneration commands are documented in `frontend/README.md` and `docs/PHASE4_RELEASE_HARDENING_AND_DEPLOYMENT.md`.

## Privacy and release gates

The public privacy page describes local file reading and hosting-provider request metadata. It currently has no contact form or dedicated privacy inbox. The project owner must choose and publish a real public privacy contact channel before launch; none has been invented. Manual accessibility review, browser/device coverage, hosted response-header checks, repository visibility confirmation, collaborator coordination for any history change, and deployment approval remain distinct release work. No history rewrite, push, GitHub setting change, or deployment is authorized by this handoff.

## Local telemetry prototype

Phase 3 adds a fixed, local synthetic telemetry fixture, strict bounded schema validation, UTC normalization, deterministic versioned rules, tenant-scoped SQLite persistence, and an authenticated read-only API for findings/evidence/reports/processing status. The API's single-process scheduler performs an immediate run and repeats every 600 seconds with a child-process timeout, one bounded retry, overlap prevention, and shutdown handling. There is no HTTP ingestion endpoint, external telemetry source, real-client data, scan, LLM, or defensive action. See [docs/PHASE3_READ_ONLY_TELEMETRY_AND_DETECTION.md](../PHASE3_READ_ONLY_TELEMETRY_AND_DETECTION.md). The frontend/static publisher and Phase 1 CLI behavior remain separate.

Phase 4 adds `py -3.11 scripts/run_replay_lab.py`, an on-demand replay of a fixed, reviewed synthetic scenario library using existing detector rules. It reports labeled per-scenario matches, TP/FP/TN/FN, nullable precision/recall/F1, evidence completeness, and gap-specific recommendations. It has no arbitrary input path, API execution route, persistence, network, or Controller connection and does not run in the ten-minute scheduler. The Phase 3 SQLite telemetry retention caps are 100 run/report records per tenant and 100 observations per finding; audit rows and original assessment artifacts are preserved. See [docs/PHASE4_ISOLATED_REPLAY_AND_DETECTION_GAP_ANALYSIS.md](../PHASE4_ISOLATED_REPLAY_AND_DETECTION_GAP_ANALYSIS.md).

Phase 5A adds `py -3.11 scripts/ingest_local_website_telemetry.py`, a local-only adapter for a fixed synthetic access/error log fixture under `demo_site/fixtures/`. It validates a closed schema, normalizes UTC, retains source/evidence references, and reuses Phase 3 rules and tenant-scoped persistence. It adds no HTTP ingestion route and does not read live web-server logs. It uses a fixed synthetic tenant and appends a categorical audit event. See [docs/PHASE5A_LOCAL_WEBSITE_TELEMETRY_INTEGRATION.md](../PHASE5A_LOCAL_WEBSITE_TELEMETRY_INTEGRATION.md).

Phase 5B adds a distinct harmless loopback test site (`py -3.11 demo_site/telemetry_server.py`), fixed traffic generator (`py -3.11 scripts/generate_local_website_traffic.py`), and live-log ingestion CLI (`py -3.11 scripts/ingest_live_website_telemetry.py`). The server binds only to `127.0.0.1:8767` and writes fixed, bounded JSONL access/error logs under ignored `.aegisai-local/website-telemetry/`. Ingestion accepts no caller path or tenant and reuses Phase 3 validation, deduplication, findings, audit, and SQLite retention. There is no public endpoint or external connection. See [docs/PHASE5B_LOCAL_LIVE_TELEMETRY_VALIDATION.md](../PHASE5B_LOCAL_LIVE_TELEMETRY_VALIDATION.md).

Phase 5C adds a fixed active-plus-three-rotations read window, full-snapshot replay with deterministic deduplication, and tenant-scoped operator status through an authenticated read-only API route. SQLite schema version 3 adds only source-status metadata; the fingerprint is observational, not a resume checkpoint. Records rotated out of the bounded window before ingestion remain unrecoverable. See [docs/PHASE5C_TELEMETRY_RELIABILITY_AND_RECOVERY.md](../PHASE5C_TELEMETRY_RELIABILITY_AND_RECOVERY.md).

Phase 6A adds `platform_prototype/fixtures/evaluation_dataset_v1.json`, a bounded, versioned synthetic dataset with labels separate from detector inputs. It covers accepted positives and controls, threshold cases, duplicates, insufficient evidence, malformed inputs, and ID/evidence conflicts. Its loader reuses existing event validation and does not calculate accuracy metrics or alter detection rules. See [docs/PHASE6A_EVALUATION_DATASET_AND_GROUND_TRUTH.md](../PHASE6A_EVALUATION_DATASET_AND_GROUND_TRUTH.md).

Phase 6B adds a deterministic local evaluation CLI for the fixed Phase 6A dataset. It counts scenario-by-rule pairs, keeps rejected inputs outside the confusion matrix, fingerprints dataset and detector configuration, and writes a versioned JSON report without overwriting an existing one. It does not change detection rules, write benchmark data to SQLite, or establish real-world accuracy. See [docs/PHASE6B_DETECTION_METRICS_AND_EVALUATION.md](../PHASE6B_DETECTION_METRICS_AND_EVALUATION.md).

Phase 6C adds focused robustness regression cases and audit safeguards around the Phase 6B evaluator. Duplicate findings remain binary for counts while their evidence is retained for diagnostics; invalid datasets and interrupted detector runs cannot produce a report. The Phase 6A dataset and detection thresholds are unchanged. See [docs/PHASE6C_DETECTION_ROBUSTNESS_AND_REGRESSION.md](../PHASE6C_DETECTION_ROBUSTNESS_AND_REGRESSION.md).

Phase 7A adds a separate local React dashboard at `/local-dashboard.html` that uses authenticated read-only API routes for synthetic findings, evidence, processing, fixed-source status, and the Detection Lab report (`reports:read`). Its bearer token is in-memory only. The Detection Lab extends the existing Phase 6 evaluator with specificity, explicit scenario/rule coverage, honest ATT&CK gaps, and optional 20-run local history; the fixed evaluator and rule thresholds remain unchanged. See [docs/PHASE7A_LOCAL_DASHBOARD.md](../PHASE7A_LOCAL_DASHBOARD.md) and [docs/DETECTION_ENGINEERING_AND_EVALUATION.md](../DETECTION_ENGINEERING_AND_EVALUATION.md). The API remains loopback-bound; browser CORS is restricted to localhost and 127.0.0.1 on Vite port 5174. The existing nine-file public publisher allowlist is unchanged.

The investigation case layer adds tenant-scoped case records, verified references to existing telemetry evidence, labeled inferred relationships/conclusions/hypotheses, append-only bounded history, and manually linked assessment/evaluation context. Viewing uses `investigations:read`; case writes require explicitly starting the local API with `--enable-investigation-writes`. The combined SQLite schema is now v6 after adding bounded purple-team scenario history. No AI assistant, arbitrary data query, or response action is provided. See [docs/PHASE4_INVESTIGATION_CASES_AND_MEMORY.md](../PHASE4_INVESTIGATION_CASES_AND_MEMORY.md).

Phase 5 adds a preview-first scenario runner for the fixed loopback demo website. It supports only a benign health request and three empty-body requests to the harmless synthetic rejection route, then compares fixed-source telemetry with existing detection output. Execution requires an explicit synthetic authorization flag; schema-v6 history stores bounded tenant-scoped run reports. See [docs/PHASE5_SAFE_PURPLE_TEAM_VALIDATION.md](../PHASE5_SAFE_PURPLE_TEAM_VALIDATION.md). No real-world control-effectiveness claim is made.

Phase 8 records the deployment decision in [docs/PHASE8_DEPLOYMENT_ARCHITECTURE.md](../PHASE8_DEPLOYMENT_ARCHITECTURE.md): the strict nine-file static artifact is the only current deployment candidate. The private API, dashboard, and SQLite workflows remain local synthetic prototypes; no deployment configuration or release was created.

Phase 10 release-candidate status and the recorded checks, local startup, migration/backup guidance, deployment gates, and rollback notes are in [docs/PHASE10_RELEASE_CANDIDATE.md](../PHASE10_RELEASE_CANDIDATE.md). Status: **BLOCKED** for production review; staging/publication still requires owner approval.

The historical worktree audit is in [docs/IMPLEMENTATION_BASELINE_AUDIT.md](../IMPLEMENTATION_BASELINE_AUDIT.md); the current verification summary is [CURRENT_STATUS.md](../CURRENT_STATUS.md). The earlier Phase 1 baseline predates schema v6 and the current dashboard/reporting features.
