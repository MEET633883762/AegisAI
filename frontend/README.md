# AegisAI static research demo

The public frontend is a React + TypeScript multi-page application built with Vite. It remains a static, read-only site with no backend and no public simulator execution. Vite compiles the three existing page URLs; the site does not use a client-side router or PWA service worker.

## Pages and preserved behavior

- `index.html`: research landing page, project boundaries, navigation to the demo.
- `dashboard.html`: reviewed, precomputed Red/Blue episode, role-scoped evidence and decision detail, metric provenance, sample downloads, local assessment file import, fixed same-origin sample loading, baseline/hardened comparison, and the explicitly illustrative legacy dashboard section.
- `privacy.html`: current data-handling disclosure. The public contact channel is still an owner decision required before launch; no address is invented here.

The Python simulator, Controller, experiment tooling, local-only header checker, artifact generators, and original `results/` evidence remain outside the frontend build. The public UI reads only the reviewed JSON files under `frontend/data/`. Selected local report files are read in the browser and are not uploaded. The sample loader uses fixed same-origin assets only.

## Local development

Use Node.js 22.12 or later and npm. From PowerShell:

```powershell
cd C:\AegisAI\frontend
npm ci
npm run dev
```

Open `http://127.0.0.1:5173/`; the dashboard and privacy pages are available at `/dashboard.html` and `/privacy.html`. Vite binds to loopback by default. The separate Python demo server still runs independently using `python demo_site/server.py` from the repository root.

## Data and safety checks

`src/researchArtifact.ts` enforces the versioned episode contract, bounds streamed response content to 1 MB before buffering, checks role visibility and record/metric constraints, and rejects unsupported data. `src/assessment.ts` validates the four-header assessment format, caps local and fetched report sizes, and computes baseline/hardened comparison values. React renders all artifact strings as text nodes; neither component uses raw HTML insertion.

The episode sample is generated locally by `python scripts/build_public_demo_artifact.py`; it is not regenerated during the public build. Assessment public copies are created by `python scripts/build_public_assessment_artifacts.py`. Review generated copies before release and preserve originals under `results/`.

## Tests and production build

From `frontend/`:

```powershell
npm test
```

This runs strict TypeScript checking, a production Vite build, React component/security regression tests, and the static release test. Run the full simulator/research suite from the repository root with `python -m pytest -q`.

Vite writes its production output to `frontend/.vite-build/`. It targets Chrome/Edge 107+, Firefox 104+, and Safari 16+; this is a build target, not a claim that every browser/device combination has been tested. The target is intended to cover current stable desktop and mobile browsers without a legacy-browser polyfill bundle.

From the repository root, publish the explicit allowlist into a new empty directory:

```powershell
python scripts/build_static_site.py --output dist/aegisai-release
```

The publisher copies only the three HTML pages, compiled JS/CSS, three reviewed JSON assets, and Cloudflare Pages `_headers`. It refuses to publish from an incomplete Vite build or into a non-empty output directory. Publish only the generated directory; never publish the repository root, `frontend/`, or `results/`.

## Security and privacy

`frontend/_headers` applies a same-origin Content Security Policy and the configured response security headers. The CSP allows external same-origin bundle files and fixed same-origin JSON requests; it does not allow inline script/style execution, external origins, frames, or forms. Verify the actual headers on a deployment preview before any public release.

The site has no accounts, database, analytics, billing, contact form, public scan service, or public LLM call. The hosting provider may process connection/request metadata under its own terms. The privacy page accurately discloses this and still requires the project owner to choose a public privacy contact channel before launch.
