# AegisAI project handoff

Updated 2026-10-22. Inspect `git status` and current files before relying on this note.

## Product and architecture

AegisAI is a controlled simulator-first Red/Blue cybersecurity research project. Agents propose typed actions; the Controller validates and authorizes them before the deterministic synthetic environment applies them. The repository includes telemetry, audit/XAI traces, adaptive-memory validation, offline threat-intelligence retrieval, experiment tooling, and a local-only website header demo. A successful test suite is not evidence of real-world security effectiveness.

The public V1 direction is a static, read-only research/demo website using reviewed precomputed synthetic examples. It is not a hosted SaaS or general vulnerability scanner. The Python simulator, Controller, experiments, LLM providers, and local website checker are not part of the public static build.

## Frontend

The frontend now uses React + TypeScript + Vite as a multi-page app. Existing URLs remain `/`, `/dashboard.html`, and `/privacy.html`; there is no client router or service worker. The dashboard retains the precomputed Red/Blue timeline, role-scoped evidence, structured decision/authorization data, metrics/provenance, sample download, local assessment import, fixed same-origin assessment samples, comparison, and the clearly labeled illustrative legacy section.

The public browser can load only reviewed static JSON assets. It cannot run the simulator, invoke the Controller, execute simulations, scan visitor-supplied targets, upload selected reports, or call an LLM. React displays untrusted report text as text. The static publisher uses an explicit asset allowlist and copies no Python, tests, Git metadata, or original `results/` reports.

Run locally in PowerShell:

```powershell
cd C:\AegisAI\frontend
npm ci
npm run dev
```

Open `http://127.0.0.1:5173/`. The dashboard is at `/dashboard.html`. For verification, run `npm test` from `frontend/` and `python -m pytest -q` from the repository root.

For a static output build, run `npm run build` from `frontend/`, then `python scripts/build_static_site.py --output dist/aegisai-release` from the repository root. Choose a new empty output folder; the publisher refuses populated folders. Publish only that generated allowlisted folder. No public deployment has been performed.

See [frontend/README.md](frontend/README.md), [docs/FRONTEND_MIGRATION_AUDIT.md](docs/FRONTEND_MIGRATION_AUDIT.md), and [docs/PHASE4_RELEASE_HARDENING_AND_DEPLOYMENT.md](docs/PHASE4_RELEASE_HARDENING_AND_DEPLOYMENT.md).

## Local website header demo

The local demo server binds to `127.0.0.1:8765`. Start it with `python demo_site/server.py --profile baseline` or `--profile hardened`; in another terminal run `python scripts/check_demo_site.py`. The checker only evaluates HTTP status and four configured security headers against the fixed loopback target. Baseline findings and hardened pass are expected for those two local profiles. The checker is not a general-purpose scanner.

Reports are written under `results/` as original local evidence. Do not overwrite, sanitize in place, or publish them. Reviewed public copies live under `frontend/data/` and omit machine-specific artifact paths. Regeneration commands are documented in `frontend/README.md` and `docs/PHASE4_RELEASE_HARDENING_AND_DEPLOYMENT.md`.

## Privacy and release gates

The public privacy page describes local file reading and hosting-provider request metadata. It currently has no contact form or dedicated privacy inbox. The project owner must choose and publish a real public privacy contact channel before launch; none has been invented. Manual accessibility review, browser/device coverage, hosted response-header checks, repository visibility confirmation, collaborator coordination for any history change, and deployment approval remain distinct release work. No history rewrite, push, GitHub setting change, or deployment is authorized by this handoff.
