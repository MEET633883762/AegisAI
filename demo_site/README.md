# AegisAI local website demo

This self-contained static site provides a first, controlled target for AegisAI's defensive website integration work. It uses only the Python standard library and listens on `127.0.0.1:8765`; it does not accept writes or connect to external services. The `baseline` profile intentionally omits four response headers so the checker has findings to report. It has no exploitable application features.

Use the project's Python 3.11 environment from [the development guide](../docs/DEVELOPMENT.md). The PowerShell commands below select 3.11 explicitly and assume its reviewed dependencies are installed; substitute `.\.venv\Scripts\python.exe` when using that virtual environment. On Linux, use `.venv/bin/python`. `.python-version` records the project version but does not change an existing `python` command on `PATH`.

## Run it

In PowerShell, from the repository root, start the server:

```powershell
py -3.11 demo_site/server.py --profile baseline
```

Open `http://127.0.0.1:8765/` in your browser. Keep the server window open. Stop it with `Ctrl+C`.

In a second PowerShell window, check the baseline and inspect the structured findings:

```powershell
py -3.11 scripts/check_demo_site.py
```

The checker writes a profile-specific report to `results/demo_site_assessment_baseline.json` or `results/demo_site_assessment_hardened.json`, so the before and after evidence are preserved. The baseline check reports four header findings and exits with code `1`, which is expected. Stop the server with `Ctrl+C`, then start the hardened profile:

```powershell
py -3.11 demo_site/server.py --profile hardened
```

Run `py -3.11 scripts/check_demo_site.py` again. It should report `"ok": true`, zero findings, and exit with code `0`. The page also displays the active profile. To compare the original reports, start the frontend from the repository root in another terminal:

```powershell
npm.cmd --prefix frontend ci
npm.cmd --prefix frontend run dev -- --host 127.0.0.1
```

Open [the header comparison](http://localhost:5174/dashboard.html#assessment), expand **Inspect the header reports**, and select the baseline and hardened JSON files. The browser validates and reads them locally; it does not upload them. Do not open the frontend HTML with `file://`. The **Load published baseline and hardened samples** button compares fixed reviewed copies instead of your newly generated local files. See [the frontend guide](../frontend/README.md) for page boundaries.

The checker is fixed to this loopback URL; it is not a general-purpose scanner. A passing result checks only the listed HTTP headers and HTTP status. It does not establish that a website is secure.

This header-demo server uses port **8765**. The separate telemetry test website uses **8767**, and the private operations API uses **8766**; their fixtures, output, and assessment workflows are distinct. See [the current project status](../docs/CURRENT_STATUS.md) and [telemetry validation guide](../docs/PHASE5B_LOCAL_LIVE_TELEMETRY_VALIDATION.md).

## Current limits

- Static content only; there is no login, database, form processing, or application API.
- The check covers a small set of response headers, not application vulnerabilities.
- This is a local development target, not a production server.
