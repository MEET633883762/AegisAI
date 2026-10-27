# AegisAI browser demo

For the dated implementation inventory and fresh checks, see [current status](../docs/CURRENT_STATUS.md); for a fresh machine, use [the development setup](../docs/DEVELOPMENT.md).

The public site explains a simulated cyberattack for an audience that does not need a cybersecurity background. The guided replay shows the attacker, defender, current target, permission check, and recorded result. Technical evidence is available when viewers want to inspect how a result was produced.

## Start locally

Use Node.js 22.12 or later. From the repository root in PowerShell:

```powershell
npm.cmd --prefix frontend ci
npm.cmd --prefix frontend run dev -- --host 127.0.0.1
```

Open [http://localhost:5174/](http://localhost:5174/) or go straight to [the walkthrough](http://localhost:5174/dashboard.html). Keep the terminal running while presenting. Once dependencies are installed, the public demo needs no internet access, API key, Python service, or database.

Choose **Present demo** in the dashboard navigation to focus the exercise and enlarge the text for projection. **Exit presentation** or **Esc** restores the full dashboard. Use **Next moment** to advance through the six recorded moments; **Back** revisits an earlier moment. At the final moment, **Restart walkthrough** returns to the beginning without reloading the page and moves focus back to the first moment. Focus the player and use **Left/Right** to step through moments, or **Home/End** to jump to the first/last moment. These shortcuts apply only inside the player.

For a short judging demo, start with the research question on the landing page, then present the six-moment walkthrough. Show the recorded outcome and open **Look under the hood** for the evidence behind it. Exit presentation to compare the website-header samples. In **Look under the hood**, filter by attacker/defender or search actions, hosts, results, and evidence. Filters leave the selected action unchanged, so you can compare its details with the matching timeline. **Clear action filters** restores the full list. These controls change the displayed record; they do not run an attack or call a model.

The explicit host option above keeps this presentation server on the local computer. The package's default `dev` command listens on all interfaces for trusted local-network development. The fixed port is 5174; the server refuses to silently switch ports if it is occupied.

## What visitors see

- **`index.html`:** the project question, a diagram of the controlled lab, reviewed baseline results, the paired defender-comparison summary, a research FAQ, and a link to the walkthrough.
- **`dashboard.html`:** six key moments from one actual simulator episode, Back/Next/Restart controls, presentation mode, a simplified network map, the recorded final outcome, expandable evidence and metrics, JSON downloads, and a narrow website-header comparison. A failed episode load offers **Retry sample**.
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

Start the separate loopback API in another terminal using the Python 3.11 environment from [the development setup](../docs/DEVELOPMENT.md). On Windows, from the repository root:

```powershell
.\.venv\Scripts\python.exe scripts/run_private_api.py
```

If its dependencies are already installed directly in Python 3.11, `py -3.11 scripts/run_private_api.py` also works. On Linux, use `.venv/bin/python scripts/run_private_api.py`. An unqualified `python` can select an older installation; `.python-version` does not change Windows `PATH`. A `StrEnum` import error means Python is too old; see [the version-mismatch fix](../docs/DEVELOPMENT.md#python-version-mismatch-strenum).

The dashboard requires the API's ephemeral development token; see [the local dashboard documentation](../docs/PHASE7A_LOCAL_DASHBOARD.md). It is intentionally excluded from the public production build. Its modules and local API address are excluded from the shared public bundle as well. The static publisher independently enforces an exact allowlist of public files.

Local sections have their own URL fragments, such as `local-dashboard.html#findings`; browser Back/Forward restores the section. Selecting a recent finding opens its evidence in the Findings queue. Search and severity/type/status filters include a clear action and explicit empty states. The session token stays only in page memory and is never written to these links.

The Python simulator, experiment tooling, local website checkers, application database, original reports, and telemetry logs are outside the frontend release.

## Frontend source map

`src/main.tsx` mounts the public application. `src/App.tsx` selects its page from the HTML entry's `data-page` attribute; page content is split into small modules:

| Module | Responsibility |
|---|---|
| [`src/LandingPage.tsx`](src/LandingPage.tsx) | Project story, research diagram, reviewed results, and public-demo boundaries. |
| [`src/DashboardPage.tsx`](src/DashboardPage.tsx) | Walkthrough page, exercise brief, and presentation mode with Escape exit. |
| [`src/ResearchDemo.tsx`](src/ResearchDemo.tsx) | Episode loading/retry, selected record, section deep links, and report download. |
| [`src/EpisodeEvidence.tsx`](src/EpisodeEvidence.tsx) | Searchable timeline, role filters, selected-action details, provenance, and metric definitions. |
| [`src/EpisodeWalkthrough.tsx`](src/EpisodeWalkthrough.tsx) | Six-moment navigation, simplified network, restart control, and final episode outcome. |
| [`src/WebsiteAssessment.tsx`](src/WebsiteAssessment.tsx) | Published header comparison, local report selection, validated report display, and downloads. |
| [`src/PrivacyPage.tsx`](src/PrivacyPage.tsx) | Static-site and browser-local file-handling disclosures. |
| [`src/SiteChrome.tsx`](src/SiteChrome.tsx) | Shared brand and footer. |

`src/episodeStory.ts` maps recorded actions to plain-language explanations and selects the key moments. `landing.css` contains the shared public-page base and scoped landing styles; `src/demo.css` styles the walkthrough. `styles.css` and `website_assessment.css` supply the detailed evidence/report layouts.

The local operations dashboard has its own entry, `src/localDashboard.tsx`, with its screen, API client, response types, export helper, and stylesheet under `src/localDashboard/`. Public page modules do not import it.

## Data validation

`src/researchArtifact.ts` validates the episode schema, bounded response size, record constraints, metric arithmetic, and role-scoped visibility. `src/assessment.ts` validates the four-header assessment format and bounded local/fetched report sizes. React renders report strings as text.

The six story moments are selected from actual action records. Explanations and the simplified map help interpret those records; they do not add intermediate events or replace the recorded results. Expand the evidence view to inspect the full action timeline, observation references, authorization, and provenance.

The episode generator is `scripts/build_public_demo_artifact.py`. Public assessment copies come from `scripts/build_public_assessment_artifacts.py`. Run generators from the repository root using the project Python environment, review changes, and preserve original evidence under `results/`. Building the frontend does not regenerate samples.

## Verify and build

From the repository root:

```powershell
npm.cmd --prefix frontend test
```

The 2026-10-27 check passed 65 component/validation tests across four files and four static-release tests, along with typecheck and build. These are dated counts; rerun the command after changes.

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
