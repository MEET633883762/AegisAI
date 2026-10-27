# Current implementation and verification

Updated **2026-10-27** for the local Windows workspace. This page describes the working tree verified on that date, including uncommitted changes. It is not a tagged release, a hosted CI result, or a production readiness assessment. Older phase reports retain their original verification evidence.

## Start with the right runtime

The reviewed environment is **Python 3.11** and **Node 24.14.1**, recorded in `.python-version` and `.node-version`. The API rejects Python versions below 3.11 before importing application dependencies. An existing `python` command can still resolve to Python 3.10; the version file does not change Windows `PATH`.

Follow [the development setup](DEVELOPMENT.md) to create a Python 3.11 virtual environment and install `requirements-demo.txt`. From the repository root on Windows:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-demo.txt
.\.venv\Scripts\python.exe --version
npm.cmd --prefix frontend ci
```

For an existing virtual environment, check its version first. If it uses an older interpreter, create a separate Python 3.11 environment as explained in the [version-mismatch guide](DEVELOPMENT.md#python-version-mismatch-strenum). Linux setup and commands are in the same guide.

## Choose an experience

| Experience | Local URL | Requirements and behavior |
|---|---|---|
| Public overview | `http://localhost:5174/` | Indigo/navy research overview, conceptual architecture diagram, recorded results, paired benchmark summary, and research FAQ. |
| Public walkthrough | `http://localhost:5174/dashboard.html` | Six recorded moments, keyboard navigation, presentation mode, searchable action evidence, role filters, metric definitions, JSON downloads, and four-header comparison. No Python API or model call. |
| Local operations dashboard | `http://localhost:5174/local-dashboard.html` | Eight views: Overview, Findings, Detection Lab, Scenario Validation, Assessment, Executive Reports, Cases, and System Health. Requires the separate local API and its startup token. |

Start the public frontend in a terminal:

```powershell
npm.cmd --prefix frontend run dev -- --host 127.0.0.1
```

For local operations, start the API in another terminal after Python setup:

```powershell
.\.venv\Scripts\python.exe scripts/run_private_api.py
```

If dependencies are already installed directly in Python 3.11, `py -3.11 scripts/run_private_api.py` is an explicit Windows alternative. The API defaults to `127.0.0.1:8766`. Paste its ephemeral startup token into the local dashboard; the browser retains it only in page memory. Section URLs contain view names, never the token. Scoped case writes require the separate `--enable-investigation-writes` startup option. [The local dashboard guide](PHASE7A_LOCAL_DASHBOARD.md) describes its limits.

The two website demonstrations are separate: `demo_site/server.py` uses port **8765** for the baseline/hardened header example; `demo_site/telemetry_server.py` uses **8767** for bounded synthetic telemetry and local assessment/scenario work. See [the website guide](../demo_site/README.md).

## Reproduced evidence

- The public baseline replay contains **39 actions across 20 steps**. It records **8/9 malicious alerts detected**, **0/6 response-required alerts mitigated**, and an achieved simulated attacker objective.
- The deterministic defender comparison contains **30 matched pairs / 60 episodes** across six templates and five seeds. Baseline attacker objectives: **3/30**; candidate: **0/30**. There are **3 improved, 0 regressed, and 27 unchanged pairs**. Mean final isolated hosts rise from **0.83 to 1.00**; containment has an availability cost. [Method and evidence](DEFENDER_COMPARISON.md).
- The separate detection evaluation covers **15 accepted synthetic scenarios**, **4 rejected-input cases**, and **5 rules**. Its 75 scenario/rule pairs produce **TP=9, FP=0, TN=66, FN=0**. These authored regression cases are separate from the replay's alert metrics.
- The public website sample compares HTTP status and **four configured headers**. Its fixed hardened sample resolves four missing settings; this is not a general website security assessment.

These experiments use synthetic inputs. The public replay and paired policy benchmark use scripted agents. Separate LLM adapters and research harnesses exist; the figures above do not measure an AI model, learned adaptation, or real-world cybersecurity effectiveness.

## Fresh verification on 2026-10-27

Commands ran from the repository root with installed **Python 3.11.9** and **Node v24.14.1**. No dependency installation or clean-environment reconstruction was performed during this verification.

| Check | Command or method | Observed result |
|---|---|---|
| Full Python regression suite | `py -3.11 -m pytest -q --basetemp <fresh directory under .aegisai-local/test-artifacts/>` | **503 passed in 28.70s**. The default pytest cache plugin remained enabled. |
| Frontend aggregate | `npm.cmd --prefix frontend test` | Typecheck and production build passed; **65 Vitest tests in four files**, plus **4/4 static-release tests**. |
| Judging preflight | `py -3.11 scripts/run_judging_demo.py --check` | Reproducible replay and detection evaluation; published replay matches current Controller output; evidence/ground-truth checks pass. |
| Python dependency consistency | `py -3.11 -m pip check` | **No broken requirements found** in that interpreter's installed environment. |
| API startup regression | Included in the full Python suite | Unsupported Python receives actionable instructions; supported Python loads the API entry point. An earlier isolated Python 3.11 startup smoke check also returned authenticated HTTP 200 from `/health` and `/ready`. |

Fresh commands for a project virtual environment are in [DEVELOPMENT.md](DEVELOPMENT.md). Older audit counts and dependency conflicts describe their recorded dates/interpreters and should not replace this dated snapshot. Test passes establish software behavior on these fixtures; they are not a security audit or completed browser/device review.

## Files, packages, and release scope

Source packages retain their existing Python import paths. The public frontend is split into page, replay, evidence, assessment, and shared-chrome components; [its source map](../frontend/README.md#frontend-source-map) explains them.

Generated local state, SQLite databases, judging packets, and test artifacts belong under the ignored `.aegisai-local/` directory. The former root `.pytest-*` folders are preserved under `.aegisai-local/test-artifacts/legacy/`; 169 previously tracked temporary files were removed from the source tree and retained in that local archive. Historical decisions and the earlier handoff live in [docs/history/](history/README.md).

The Vite public build is `frontend/.vite-build/`. The static publisher accepts a new or empty output directory and emits exactly **nine allowlisted files**: three public HTML pages, compiled JavaScript/CSS, three reviewed JSON files, and `_headers`. It excludes the local dashboard, private API, database, logs, and original research reports.

No hosting target was deployed or published during this work. Hosted headers, browser/device coverage, public privacy contact, production authentication, operational recovery, and broader external evaluation remain unverified or incomplete. The private API remains a local synthetic prototype. [Deployment scope](PHASE8_DEPLOYMENT_ARCHITECTURE.md) and the [historical release review](PHASE10_RELEASE_CANDIDATE.md) explain the boundary.

Use [the judges' guide](JUDGES_GUIDE.md) to rehearse and [the documentation index](README.md) to find subsystem and historical records.
