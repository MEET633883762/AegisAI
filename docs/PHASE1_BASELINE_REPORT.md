# AegisAI Phase 1 Baseline Report

> Historical verification record from 2026-10-24. Keep the commands, counts, failures, and timings below as observations of that baseline. They are not the current test totals or setup instructions. See [CURRENT_STATUS.md](CURRENT_STATUS.md) for fresh checks and [DEVELOPMENT.md](DEVELOPMENT.md) for the explicit Python 3.11 environment.

Later source adds project-level `pytest.ini`, a schema-v6 local store, and additional frontend flows/tests. The old schema/configuration findings below are retained to explain the baseline, not to describe the present checkout.

Run on 2026-10-24 before the Phase 2 security validation engine changes.

## Worktree preservation

The repository already contained tracked modifications and untracked Phase 7B files, including the local assessment gate, API, dashboard, and tests. They were preserved. Baseline commands used temporary test databases and fixtures; the local default/presentation databases and saved report artifacts were not inspected or modified.

## Results

| Area | Command | Result |
|---|---|---|
| Relevant backend | `python -m pytest -q -p no:cacheprovider tests/unit/test_local_assessment.py tests/unit/test_local_assessment_api.py tests/unit/test_local_assessment_reporting.py tests/unit/test_run_local_assessment_cli.py tests/unit/test_private_api.py` | 51 passed in 6.58s |
| Frontend type check | `npm.cmd run typecheck` (also run as part of `npm.cmd test`) | Passed |
| Frontend production build | `npm.cmd run build` (also run as part of `npm.cmd test`) | Passed with Vite 8.3.5 |
| Frontend unit tests, default worker pool | `npm.cmd run test:unit` | Vitest failed before collecting tests: three worker startup timeouts; no test assertion failures were reported. |
| Frontend unit tests, bounded worker pool | `./node_modules/.bin/vitest.cmd run --pool=threads --maxWorkers=1` | 3 files, 42 tests passed in 77.11s |
| Static publisher release checks | `npm.cmd run test:release` | 4 passed; exact publisher allowlist and exclusion behavior checked |

The aggregate `npm.cmd test` transcript was truncated by the command session after type checking, build, and the Vitest launch. The distinct commands above provide the observed unit-test and release-test results. An attempted bounded run with `--minWorkers=1` failed because Vitest 5.0.5 does not support that option; it is not a product test failure.

## Checks and configuration discovered

- Frontend scripts available: `typecheck`, `build`, `test:unit`, `test:release`, and aggregate `test`; no lint or security-audit script is configured in `frontend/package.json`.
- No repository Ruff, Bandit, ESLint, or project-level pytest/lint configuration was found by the targeted configuration-file search. No separate security scanner was configured.
- SQLite initialization reads `PRAGMA user_version`, rejects versions newer than the application, and initializes tables transactionally. Current schema version is 4. Existing upgrade tests use temporary databases and preserve audit records; no real database was opened.
- The static publisher allowlist is exactly nine files: `_headers`, `index.html`, `dashboard.html`, `privacy.html`, `assets/app.css`, `assets/main.js`, `assets/public_demo_episode.json`, `assets/public_demo_assessment_baseline.json`, and `assets/public_demo_assessment_hardened.json`.

## Baseline caveat

The default Vitest worker startup timeout is an environment/tooling issue observed before test collection. Running with one worker completed the test assertions successfully. Keep this distinct from product test failures when assessing regressions.
