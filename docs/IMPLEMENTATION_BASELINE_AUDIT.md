# AegisAI Current Implementation Baseline Audit

**Audit date:** 2026-10-24
**Scope:** Repository structure, current worktree, architecture/configuration, test and release commands, schema initialization, and public publisher boundary. This is a documentation and source inspection report. It is not a security certification, penetration test, or live end-to-end validation.

## Baseline definition and preservation

This is a snapshot of a **modified, uncommitted worktree**, not a clean Git revision. At audit time `git status --short` showed existing modifications and untracked files across documentation, private dashboard, API/storage, evaluation, assessment, scenario runner and tests. The preceding Phase 10 release audit records the detailed status inventory. Those changes were preserved. No reset, cleanup, commit, publish, deployment, or database operation was performed for this report.

The root contains the existing simulator (`agents/`, `controller/`, `environment/`), research/evaluation (`evaluation/`, `platform_prototype/`, `llm/`, `memory/`, `threat_intelligence/`, `xai/`), local private service (`private_api/`, `local_assessment/`, `purple_team/`), fixed website demo (`demo_site/`), React/Vite frontend (`frontend/`), operational scripts (`scripts/`), and tests (`tests/`). `results/`, `dist/`, and `.aegisai-local/` are present at the root; their contents were not inspected or changed as part of this audit.

The older [Phase 1 baseline](PHASE1_BASELINE_REPORT.md) describes an earlier point in the project (schema v4 and a smaller feature set). Its results are historical and should not be treated as the current implementation baseline.

## Architecture and boundaries found

- **Public site:** React, TypeScript and Vite. Public pages are static and separate from the local operations dashboard. `scripts/build_static_site.py` publishes only the explicit nine-file allowlist: `_headers`, `index.html`, `dashboard.html`, `privacy.html`, `assets/app.css`, `assets/main.js`, `assets/public_demo_episode.json`, `assets/public_demo_assessment_baseline.json`, and `assets/public_demo_assessment_hardened.json`.
- **Local dashboard:** Vite development entry at `/local-dashboard.html`; authenticated API client uses the fixed loopback API origin. The startup bearer token is held in page memory and cleared on disconnect. The local page is not part of the static publisher output.
- **Private API:** Python standard-library HTTP server fixed to `127.0.0.1:8766`; development bearer tokens are ephemeral, scoped and held in memory. Route tenant scope is derived from the authenticated principal. CORS is restricted to fixed local dashboard origins. The API rejects non-local runtime modes; it is not a production service configuration.
- **Storage:** SQLite schema version 6. `SQLiteStore` initializes additively, rejects a database schema newer than the application, and stores tenant-scoped telemetry, assessment, evaluation history, investigations and scenario history. There is no standalone migration command or down migration. Tests use temporary databases; this audit did not open a local database.
- **Synthetic website and checks:** `demo_site/telemetry_server.py` serves the telemetry/assessment site on `127.0.0.1:8767`; separate `demo_site/server.py` uses port 8765. The assessment runner has a fixed check catalog, fixed paths and target, a separate Local Assessment Policy/Controller, and bounded request/response/time behavior. The simulator Controller is separate and unchanged by assessment authorization.
- **Configuration:** `requirements.txt` declares Pydantic, pytest and OpenAI. Frontend scripts provide `dev`, `dev:dashboard`, `typecheck`, `build`, `test:unit`, `test:release`, and aggregate `test`. `AEGISAI_ENV` is an optional local/development mode guard. `OPENAI_API_KEY` and `OPENAI_MODEL` are only for selected research/LLM harnesses and are not required for local synthetic dashboard workflows.
- **Deployment:** No Docker/Compose, cloud manifest, private API deployment, migration runner, or backup automation is configured. The documented current release boundary is public static artifact only; private application remains local-only. See [Phase 8 deployment architecture](PHASE8_DEPLOYMENT_ARCHITECTURE.md) and the [Phase 10 release record](PHASE10_RELEASE_CANDIDATE.md).

## Existing features at this baseline

The project includes a deterministic Red/Blue simulator and Controller, synthetic telemetry detection and evidence, a versioned evaluation dataset and metrics, fixed-source local website telemetry ingestion, the separate policy-gated local assessment runner, bounded purple-team scenarios, a tenant-scoped private dashboard/API, executive report builder/API/HTML export, and investigation case storage. These are local research/prototype capabilities. Passing synthetic tests does not demonstrate real-world compromise detection, control effectiveness, or operational readiness.

## Test and release baseline

Phase 11 reran the full suites on 2026-10-24. Earlier Phase 9 results are retained as historical context. The fresh Python run used a unique project-local `--basetemp` path. Commands/results are stated as observed.

| Area | Command | Result |
|---|---|---|
| Backend full suite (Phase 11) | `python -m pytest -q -p no:cacheprovider --basetemp <fresh unique project-local directory>` | **442 passed** in **31.41s**, exit code 0. |
| Frontend aggregate (Phase 11) | From `frontend/`: `npm.cmd test` | Exit code 0. Typecheck/build passed; Vitest **3 files / 48 tests**; static-release checks **4/4 tests**. |
| Python compile (Phase 11) | `python -m compileall -q private_api platform_prototype scripts tests` | Passed, exit code 0. |
| Diff whitespace (Phase 11) | `git diff --check` | Passed, exit code 0. |
| Backend full suite | `python -m pytest -q -p no:cacheprovider` | **442 passed** in 27.58 seconds. The preceding run had 441 passed and one failure in `test_invalid_stored_source_data_fails_safely`; the read-side stored-data validation error mapping was corrected, focused tests passed, and the full suite then passed. |
| Focused API regression | `python -m pytest -q -p no:cacheprovider tests/unit/test_executive_reports_api.py tests/unit/test_private_api.py` | **31 passed** after that correction. |
| Frontend aggregate | From `frontend/`: `npm.cmd test` | TypeScript typecheck passed; Vite production build passed; Vitest reported 3 files / 48 tests passed; Node static-release checks passed 4/4. |
| Python compile | `python -m compileall -q private_api platform_prototype scripts tests` | Passed. |
| Diff whitespace | `git diff --check` | Passed. Git emitted line-ending conversion warnings for existing files. |
| Python dependency consistency | `python -m pip check` | **Failed** in the active environment due to installed-package conflicts: missing Streamlit `altair`; `databases` requires older SQLAlchemy; global FastAPI requires Pydantic <2 while this project specifies Pydantic 2; FastF1 and Pyppeteer require older versions of websocket/pyee/urllib3. This is not evidence that the project requirements install cleanly in an isolated environment. |
| Static publisher | Existing Node static-release tests and publisher source inspection | Passed: exact nine-file allowlist above; private dashboard, API, database, logs and private reports are excluded. No artifact was published. |

No project lint or security-scan command is configured in the inspected package/configuration files. `bandit`, `pip_audit`, and `semgrep` were unavailable in the checked environment. The Phase 11 aggregate verifies tests/build/allowlist; it is not a security scan.

## Data and migration safety

- No default or presentation SQLite database was opened, inspected, migrated, pruned, backed up, or written for this audit.
- No assessment or telemetry ingestion CLI was run; no services or traffic generator were started.
- Current schema is v6 based on application source. Migration compatibility is tested by the existing tests using temporary databases. There is no verified production backup/restore process; the project documentation recommends stopping writers and using SQLite's backup API before a future approved schema upgrade.
- Public build and static publisher checks do not require application database access.

## Baseline gaps and safe next phase

1. The Python environment's `pip check` failure remains unresolved; validate dependencies in a clean isolated environment and identify which global conflicts are unrelated before changing dependency pins.
2. There is no configured security scanner/linter and no independent security review. Select tools and scope before treating a test pass as a security audit.
3. Private production authentication, HTTPS/proxy configuration, trusted origins, managed secrets, persistent production storage, monitoring and tested recovery are absent. Keep the API/dashboard on loopback; do not deploy them.
4. No host, hosted preview, deployed response headers, public privacy contact, or accessibility review has been verified. Static staging/publication requires owner approval and artifact/header review.
5. The README retains a historical Phase 8 LLM Red Agent title while later sections summarize the broader project; reconcile this before using it as the sole presentation overview.
6. The assessment runner intentionally rejects chunked Transfer-Encoding bodies; checks are limited to the fixed local target and catalog.

**Safe to continue?** Yes, with another small, local-only and reviewable phase using synthetic data and temporary test resources. No staging, production release, external target testing, or private-service deployment should proceed until the release gates above are addressed and explicitly approved.
