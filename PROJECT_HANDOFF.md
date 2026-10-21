# AegisAI Project Handoff

Paste this document into a new ChatGPT conversation to provide project context. It summarizes the repository and the work completed in the current session. Always inspect the current checkout before relying on these details.

## Project overview

AegisAI is a controlled, simulator-first Red-vs-Blue cybersecurity research project. Simulated agents propose structured actions; the Controller validates and authorizes actions before the deterministic synthetic environment applies them. The repository also contains telemetry, audit/XAI traces, adaptive-memory validation, deterministic threat-intelligence retrieval, experiment tooling, and a read-only dashboard.

Main areas include `agents/`, `controller/`, `environment/`, `telemetry/`, `xai/`, `memory/`, `threat_intelligence/`, `evaluation/`, `llm/`, `frontend/`, `security/`, `tests/`, and `scripts/`.

The primary research question is whether validated, versioned adaptive memory can improve Blue Team performance on held-out simulated scenarios without fine-tuning. This is a hypothesis; software tests or small demonstration runs do not prove research effectiveness.

## Important architecture and safety boundaries

- Keep the action flow as **agent proposal → schema validation → Controller authorization → simulator execution**.
- Agents must not directly mutate simulator state or receive observations beyond their role's permissions.
- Treat provider responses, retrieved material, and memory candidates as untrusted until validated.
- Keep the simulator deterministic where practical and preserve held-out evaluation isolation.
- The current website demo is local-only and binds to `127.0.0.1`. Do not turn its fixed-target checker into an unrestricted scanner or point it at systems without authorization.
- Label synthetic, offline/test-double, and live-provider evidence accurately. A passing test suite does not establish real-world security.
- Never put API keys or other secrets in source, logs, reports, or Git.

## Current repository state

The existing dashboard is a dependency-free, static frontend with simulator demo data. It has no backend/database integration. A small local website security demo was added to begin a controlled defensive integration workflow.

### Local demo website

- `demo_site/server.py` serves a static site using only Python's standard library at `http://127.0.0.1:8765/`.
- It accepts a `--profile baseline|hardened` option. The baseline profile intentionally omits four response security headers. The hardened profile adds them. The site has no login, database, user-submitted data, or intentionally exploitable application features.
- `scripts/check_demo_site.py` only checks the fixed loopback URL. It checks HTTP 200 and these headers: Content-Security-Policy, X-Content-Type-Options, Referrer-Policy, and Permissions-Policy.
- The checker produces structured JSON with schema version, timestamp, profile, header evidence, findings, remediation guidance, and limitations. By default, reports are preserved separately as `results/demo_site_assessment_baseline.json` and `results/demo_site_assessment_hardened.json`.
- Baseline findings produce exit code `1` intentionally. A hardened pass produces exit code `0`. Connection/configuration errors produce exit code `2`.
- The checker is not a general-purpose vulnerability scanner. Its scope is the four headers and HTTP status only.

### Dashboard integration

- `frontend/index.html` includes a **Website Header Assessment** section.
- `frontend/website_assessment.js` lets the user select one report or both profile reports from the local file picker. It validates the report version/type/fixed loopback URL, escapes displayed values, and summarizes findings resolved between baseline and hardened reports.
- `frontend/website_assessment.css` styles that section.
- The dashboard only displays evidence; it does not execute remediation or make network requests for this report import.

### Current generated evidence

The checkout currently contains profile-specific JSON artifacts:

- `results/demo_site_assessment_baseline.json`: HTTP 200, four missing-header findings.
- `results/demo_site_assessment_hardened.json`: HTTP 200, all four checked headers present, zero findings.
- `results/demo_site_assessment.json`: an older single-report artifact from an earlier checker version; profile-specific filenames are now the defaults.

These findings demonstrate the configured header difference between two local profiles. They do not demonstrate that the website is comprehensively secure.

## How to run the demo and compare profiles

From `C:\AegisAi`, use two PowerShell terminals.

1. Start the baseline server in terminal 1:

   ```powershell
   python demo_site/server.py --profile baseline
   ```

2. With the server running, run in terminal 2:

   ```powershell
   python scripts/check_demo_site.py
   ```

   This writes `results/demo_site_assessment_baseline.json`; four findings and exit code `1` are expected.

3. Stop the baseline server with Ctrl+C. Start the hardened profile in terminal 1:

   ```powershell
   python demo_site/server.py --profile hardened
   ```

4. Run the checker again in terminal 2. It writes `results/demo_site_assessment_hardened.json`; zero findings and exit code `0` are expected.

5. Open `frontend/index.html` in a browser, refresh it, and in **Website Header Assessment** select both JSON files. Use Ctrl in the file picker to select the second report. The page should summarize how many baseline findings were resolved.

Keep the server terminal open while checking. Stop the server with Ctrl+C when done.

## Test status

The user ran `python -m pytest -q` before the website-demo additions and shared output showing **200 passed in 2.29s**. That result applies to the earlier checkout only. The newer website checker, report import, and comparison changes have not had the full test suite rerun in this session. Do not describe the newer changes as regression-tested until the command is run again.

## Working-tree state at handoff

The following local website/dashboard integration changes and generated report artifacts are currently uncommitted. Check `git status --short` before editing, staging, or committing:

- Modified: `README.md`, `demo_site/README.md`, `frontend/README.md`, `frontend/index.html`, `scripts/check_demo_site.py`.
- New: `frontend/website_assessment.css`, `frontend/website_assessment.js`, and the three `results/demo_site_assessment*.json` report artifacts.
- Do not overwrite unrelated user changes or stage/commit unless explicitly requested.

## Recommended next steps

1. Visually load both saved reports in the dashboard and confirm the comparison summary appears.
2. Run the current test suite (`python -m pytest -q`) and address any regressions. Add focused tests for the fixed-target checker/report schema if this integration is being maintained as product code.
3. Decide whether generated assessment reports should be committed, ignored, or stored elsewhere; preserve the baseline and hardened evidence if retaining the comparison workflow.
4. For further website-security work, agree on a narrowly scoped local-only check before adding it. Keep the current report language explicit about what was and was not checked.

## Reference paths

- Overall project: `README.md`
- Demo usage and limits: `demo_site/README.md`
- Dashboard usage: `frontend/README.md`
- Local server: `demo_site/server.py`
- Fixed-target checker: `scripts/check_demo_site.py`
- Dashboard assessment import/comparison: `frontend/website_assessment.js`
