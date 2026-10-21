# Phase 4 — Release hardening and deployment preparation

## Release boundary

The public V1 is a static, read-only research demo. The deployable file set is the explicit `STATIC_ALLOWLIST` in `scripts/build_static_site.py`. Run `python scripts/build_static_site.py` to copy those files into `dist/aegisai-static/`. The build refuses a non-empty output directory and verifies that its contents exactly match the allowlist. Only that generated directory is a deployment candidate; do not select the repository root, `frontend/` itself, or `results/` as the publish directory.

The allowlist includes the landing page, dashboard, privacy disclosure, local CSS/JavaScript, Cloudflare Pages `_headers`, and three reviewed JSON samples. It excludes Python source, the simulator, Controller, local checker, tests, original assessment artifacts, experiment data, environment files, Git metadata, and documentation.

`scripts/build_public_assessment_artifacts.py` reads the original baseline/hardened reports and writes sanitized copies under `frontend/data/`. It removes the local `artifact` path and adds publication labels. The source evidence under `results/` must remain untouched. Review any regenerated public copy before release.

## Public behavior and data policy

- Static pages replay one reviewed, deterministic synthetic episode and the two reviewed, synthetic local-header assessment reports.
- The episode report is precomputed. Public pages do not start the Python simulator, invoke the Controller, run experiments, call an LLM, or contact user-supplied targets.
- The local assessment file chooser reads selected files in the visitor's browser. It does not upload them. A separate button loads only two fixed same-origin public sample paths.
- There are no site accounts, database, analytics, billing, or first-party visitor-profile storage.
- The hosting provider necessarily serves requests and may process connection/request metadata under its own terms and retention policies. This is described on `frontend/privacy.html`; recheck the selected provider's current privacy and logging documentation before publication.
- All examples are synthetic and limited. The header assessment covers HTTP status and four configured response headers only.

## Hosting configuration

Cloudflare Pages is the recommended initial host for this output. Use a static Pages project with no build command and no Pages Functions/Workers. For a source-connected workflow, the build command must run `python scripts/build_static_site.py` and the Pages output directory must be `dist/aegisai-static`; alternatively, upload only this generated directory using the provider's Direct Upload workflow. Never upload the repository root.

The frontend `_headers` file defines a same-origin CSP and response security headers. Cloudflare Pages parses `_headers` as configuration rather than serving it as a normal asset. Verify the deployed HTML, scripts, stylesheets, JSON responses, and downloads after configuring the host. The local Python preview does not interpret `_headers`, so it cannot verify production response headers.

As checked 2026-10-21, Cloudflare documents free static asset requests on Pages and free Universal SSL for activated domains. The chosen custom domain is additional; current `.com` registration and renewal are listed at $10.46 USD/year by Cloudflare Registrar, while other TLDs and applicable taxes differ. Hosting tiers, limits, domain prices, and provider terms can change; recheck before launch. See [Pages static asset pricing](https://developers.cloudflare.com/pages/functions/pricing/), [Pages headers](https://developers.cloudflare.com/pages/configuration/headers/), [Universal SSL](https://developers.cloudflare.com/ssl/edge-certificates/universal-ssl/), and [Registrar prices](https://pricing.registrar.cloudflare.com/).

## Release procedure (not yet performed)

1. Confirm the source repository's visibility and confirm the reviewed public copy contains no local paths or secrets. The origin URL alone does not establish whether a repository is public.
2. Run the release checks below and inspect `git status --short` and the full diff.
3. Build the allowlisted output with `python scripts/build_static_site.py`. If the output directory already exists, inspect it and choose a new empty output path; the builder will not overwrite a populated directory.
4. Review the exact output tree. Confirm it contains only the allowlisted static files and no source, evidence, credentials, or development configuration.
5. In a Cloudflare Pages preview deployment, verify navigation, artifact loading, both JSON downloads, sample baseline/hardened comparison, and local-file import behavior. Inspect response headers and browser console/network errors.
6. Complete the manual accessibility checklist: keyboard-only operation, focus visibility/order, screen-reader status/details, contrast, zoom/reflow, and mobile viewport behavior.
7. Publish only after owner review. Record the Pages deployment identifier and the reviewed Git commit. Keep the previous successful production deployment as the rollback target. Cloudflare Pages supports rollback to a previous successful production deployment through its Deployments controls.

To roll back, select the last known-good successful production deployment in Pages → Deployments and choose **Rollback to this deployment**. Confirm the live site and its security headers after rollback.

## Verification commands

From the repository root in PowerShell:

```powershell
node --test tests/frontend/public_shell.test.js tests/frontend/research_demo.test.js tests/frontend/static_release.test.js
node --check frontend/app.js
node --check frontend/website_assessment.js
node --check frontend/research_demo.js
python -m py_compile scripts/build_public_demo_artifact.py scripts/build_public_assessment_artifacts.py scripts/build_static_site.py
python -m pytest -q
git diff --check
python scripts/build_public_assessment_artifacts.py
python scripts/build_static_site.py
Get-ChildItem dist/aegisai-static -Recurse -File | Select-Object -ExpandProperty FullName
```

For the local browser smoke check, run `python -m http.server 8765 --bind 127.0.0.1 --directory dist/aegisai-static` and visit `http://127.0.0.1:8765/`. This verifies content behavior only; it does not apply Cloudflare `_headers` or substitute for checking the deployed host.

## Current known limitations

- The repository visibility could not be resolved from unauthenticated GitHub metadata during Phase 4 audit (GitHub returned 404; that response can mean a private repository or an unavailable path). Confirm visibility in the authenticated GitHub settings before release.
- Manual browser accessibility and hosted-header verification remain release gates.
- No public deployment has been made as part of Phase 4.
- This release plan does not claim production readiness, security certification, or real-world research effectiveness.
