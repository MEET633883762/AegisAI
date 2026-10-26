# AegisAI browser demo

The public site explains a simulated cyberattack for an audience that does not need a cybersecurity background. The guided replay shows the attacker, defender, current target, permission check, and recorded result. Technical evidence is available when viewers want to inspect how a result was produced.

## Start locally

Use Node.js 22.12 or later. From the repository root in PowerShell:

```powershell
npm.cmd --prefix frontend ci
npm.cmd --prefix frontend run dev -- --host 127.0.0.1
```

Open [http://localhost:5174/](http://localhost:5174/) or go straight to [the walkthrough](http://localhost:5174/dashboard.html). Keep the terminal running while presenting. Once dependencies are installed, the public demo needs no internet access, API key, Python service, or database.

Choose **Present demo** in the dashboard navigation to focus the exercise and enlarge the text for projection. **Exit presentation** restores the full dashboard.

The explicit host option above keeps this presentation server on the local computer. The package's default `dev` command listens on all interfaces for trusted local-network development. The fixed port is 5174; the server refuses to silently switch ports if it is occupied.

## What visitors see

- **`index.html`:** a plain-language project introduction, the roles in the exercise, and a link to the walkthrough.
- **`dashboard.html`:** six key moments from one actual simulator episode, Back/Next controls, a simplified network map, the recorded final outcome, expandable evidence and metrics, JSON downloads, and a narrow website-header comparison.
- **`privacy.html`:** how the static demo and local file reading handle data, including hosting-provider request metadata.

The walkthrough reads the reviewed episode in `data/public_demo_episode.json`. It uses scripted attacker and defender policies, with 39 recorded actions over 20 simulation steps. Its recorded outcome shows why noticing suspicious activity and stopping an attack are different measurements. The previous dashboard's invented illustrative metrics have been removed from the public experience.

The website-header comparison loads the two fixed baseline/hardened samples or reads selected local JSON files in the browser. Selected files are not uploaded. The comparison covers HTTP status and four configured headers; it does not certify a website as secure.

For a pitch, rehearsal script, and judge Q&A, see [the judges' guide](../docs/JUDGES_GUIDE.md). To confirm the displayed episode matches the current Python implementation, run [the offline preflight](../scripts/run_judging_demo.py) from the repository root:

```powershell
.\.venv\Scripts\python.exe scripts/run_judging_demo.py
```

Create the Python environment first using the [root setup instructions](../README.md) if needed. The preflight creates a new local evidence packet without overwriting previous runs. Use `--check` to verify without writing a packet.

## Public and local applications

The public pages form a static React + TypeScript application built with Vite. They fetch reviewed same-origin JSON, never call the private API, and never execute simulator actions or LLM requests.

The separate local operations dashboard is available during development at `http://localhost:5174/local-dashboard.html`. To open it directly from the repository root:

```powershell
npm.cmd --prefix frontend run dev:dashboard -- --host 127.0.0.1
```

It requires the separate loopback API and an ephemeral development token; see [the local dashboard documentation](../docs/PHASE7A_LOCAL_DASHBOARD.md). It is intentionally excluded from the public production build. Its modules and local API address are excluded from the shared public bundle as well. The static publisher independently enforces an exact allowlist of public files.

The Python simulator, experiment tooling, local website checkers, application database, original reports, and telemetry logs are outside the frontend release.

## Data validation

`src/researchArtifact.ts` validates the episode schema, bounded response size, record constraints, metric arithmetic, and role-scoped visibility. `src/assessment.ts` validates the four-header assessment format and bounded local/fetched report sizes. React renders report strings as text.

The six story moments are selected from actual action records. Explanations and the simplified map help interpret those records; they do not add intermediate events or replace the recorded results. Expand the evidence view to inspect the full action timeline, observation references, authorization, and provenance.

The episode generator is `scripts/build_public_demo_artifact.py`. Public assessment copies come from `scripts/build_public_assessment_artifacts.py`. Run generators from the repository root using the project Python environment, review changes, and preserve original evidence under `results/`. Building the frontend does not regenerate samples.

## Verify and build

From the repository root:

```powershell
npm.cmd --prefix frontend test
```

This runs strict TypeScript checking, the public production build, component/validation tests, and static-release checks. A passing test suite verifies those software behaviors; it does not establish real-world security effectiveness.

The build output is `frontend/.vite-build/`. Only `index.html`, `dashboard.html`, and `privacy.html` are production entry points. The local dashboard remains available through the development server. Build targets are Chrome/Edge 107+, Firefox 104+, and Safari 16+; these are compilation targets, not a claim of completed device coverage.

To assemble the release into a new, empty directory:

```powershell
npm.cmd --prefix frontend run build
.\.venv\Scripts\python.exe scripts/build_static_site.py --output dist/aegisai-release
```

The publisher refuses incomplete builds and non-empty destinations. Its nine-file output contains the three public HTML pages, compiled JavaScript/CSS, three reviewed JSON assets, and `_headers`. Use only that generated directory for a future static deployment.

## Hosting and privacy

`_headers` defines the same-origin Content Security Policy and response security headers. A hosting preview must be checked to confirm the provider actually applies them. No deployment is performed by the build commands.

The public site has no accounts, database, analytics, billing, contact form, scan service, or public model invocation. Its hosting provider may process connection/request metadata under its own policies. A public privacy contact remains an owner decision before launch; the demo does not invent a contact address.
