# AegisAI local website demo

This self-contained static site provides a first, controlled target for AegisAI's defensive website integration work. It uses only the Python standard library and listens on `127.0.0.1:8765`; it does not accept writes or connect to external services. The `baseline` profile intentionally omits four response headers so the checker has findings to report. It has no exploitable application features.

## Run it

In PowerShell, from the repository root, start the server:

```powershell
python demo_site/server.py --profile baseline
```

Open `http://127.0.0.1:8765/` in your browser. Keep the server window open. Stop it with `Ctrl+C`.

In a second PowerShell window, check the baseline and inspect the structured findings:

```powershell
python scripts/check_demo_site.py
```

The checker writes a profile-specific report to `results/demo_site_assessment_baseline.json` or `results/demo_site_assessment_hardened.json`, so the before and after evidence are preserved. The baseline check reports four header findings and exits with code `1`, which is expected. Stop the server with `Ctrl+C`, then start the hardened profile:

```powershell
python demo_site/server.py --profile hardened
```

Run `python scripts/check_demo_site.py` again. It should report `"ok": true`, zero findings, and exit with code `0`. The page also displays the active profile. Open `frontend/index.html` and select both JSON reports in its **Website Header Assessment** section to compare findings resolved by hardening.

The checker is fixed to this loopback URL; it is not a general-purpose scanner. A passing result checks only the listed HTTP headers and HTTP status. It does not establish that a website is secure.

## Current limits

- Static content only; there is no login, database, form processing, or application API.
- The check covers a small set of response headers, not application vulnerabilities.
- This is a local development target, not a production server.
