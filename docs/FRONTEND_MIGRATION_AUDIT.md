# Frontend migration audit and compatibility record

Date: 2026-10-22. This record describes the local frontend migration only. It does not authorize a public deployment or claim production readiness.

## Verified baseline before edits

- Active checkout: branch `main`, commit `8c20e2d1d982f40aa15651b1b92a7041fc30b166`; no staged, unstaged, or untracked files before dependency installation or code edits.
- Existing backup `AegisAI-review-backup-20261021-201450` matched all tracked files and assessment report hashes, but its recorded Codex refs were stale. It was left intact.
- Fresh recovery mirror: `C:\Users\MEETVE~1\AppData\Local\Temp\AegisAI-integrity-audit-backup-20261022-092230`. It mirrors the five active refs, passes `git fsck --full --no-reflogs`, and includes a hash-verified copy of all 39 ignored `dist/` files. All 147 tracked source files and three assessment reports matched the active checkout when backed up. The permission-restricted `.pytest_cache` was not copied; it is disposable test cache, not application state.
- Baseline frontend tests: 23 passed. Baseline Python tests: 200 passed in 1.89 seconds, with one `PytestCacheWarning` because Windows denied writing `.pytest_cache`.
- No frontend `package.json`, lockfile, bundler, TypeScript configuration, CI workflow, or browser automation configuration existed at baseline. The app was plain HTML/CSS/JavaScript and the release publisher copied a 13-file explicit allowlist.

## Baseline routes and user-facing behavior

| Route | Existing behavior preserved in the React app |
|---|---|
| `/` (`index.html`) | AegisAI landing page; research and safety anchors; Explore demo links; synthetic/read-only caveats; feature summary; privacy and dashboard navigation. |
| `/dashboard.html` | Precomputed Red/Blue episode; status/provenance/limitations; timeline selection; role-scoped evidence; structured action, validation, Controller decision, recorded result; metric values/denominators/definitions; sample report download. |
| `/dashboard.html` assessment section | Fixed same-origin sanitized sample loading; local file selection without upload; schema/size validation; header cards and findings; baseline/hardened resolution comparison; JSON downloads. The check remains limited to status and four headers. |
| `/dashboard.html` illustrative disclosure | Collapsible legacy metrics, event timeline, trace, adaptive knowledge, and threat-intelligence example remain labeled illustrative and not artifact-backed. |
| `/privacy.html` | No-account/static-data disclosure; browser-local assessment file handling; hosting request metadata disclosure; sample limitations. A real public contact channel remains an owner decision before launch. |

Repository-only workflows remain in Python: simulator and Controller execution, offline/live experiment tooling, artifact generation, loopback-only demo server/checker, and Python tests. None is imported into the Vite frontend.

## Framework decision and output boundaries

React + TypeScript + Vite was selected for the interactive dashboard's validated artifact state, timeline selection, import/error states, and typed report/episode contracts. The site remains multi-page with the existing three `.html` URLs; a client router, PWA service worker, backend, analytics, and external requests were not added. CSS remains local and responsive.

Vite targets Chrome/Edge 107+, Firefox 104+, and Safari 16+. This is an explicit compilation target, not evidence of a test pass on those browser/device combinations. The Vite build emits a same-origin JavaScript bundle and CSS file. The static publisher retains an explicit allowlist for the three pages, two compiled assets, three reviewed JSON files, and `_headers`; Python, tests, Git metadata, source evidence, and development files remain excluded.

Dependency impact: React and React DOM are production dependencies. Vite, TypeScript, React types/plugin, Vitest, jsdom, and React Testing Library are development dependencies. `package-lock.json` pins the resolved dependency graph. No package is used by the Python simulator or controller.

The response policy remains `script-src 'self'`, `style-src 'self'`, and `connect-src 'self'`. UI strings use React text rendering; no raw HTML insertion was added. Episode/sample JSON requests use bundled same-origin asset URLs. Local assessment files are bounded before reading and never uploaded.

## Verification map

- `npm run typecheck`: strict TypeScript checks application and test source.
- `npm run build`: production multi-page Vite build; no source maps.
- `npm run test:unit`: component and validator tests for landing/dashboard/privacy, role scope, provenance, malformed/unsupported/oversized JSON, injection, stream limits, local import, comparison, and fixed same-origin sample loading.
- `npm run test:release`: CSP/build-asset checks, sanitized public artifact checks, and exact static publisher allowlist test.
- `python -m pytest -q`: simulator, Controller, research, and security regression suite.
- `git diff --check`: whitespace check.

Manual browser checks must still distinguish the browser and device actually used. Automated DOM tests do not replace keyboard, assistive-technology, zoom/reflow, mobile touch, or real-browser network/CSP checks.

## Rollback and preservation

The fresh backup above is outside the repository and was verified before edits. It contains the active Git refs and source history; its ignored `dist/` copy is preserved beside the mirror. To recover the baseline, make a separate recovery checkout from that mirror and copy only the verified pre-migration frontend/publisher/docs files as needed. Do not reset or rewrite the active repository as a rollback shortcut. The original assessment files under `results/` were not edited.

## Final local verification

Verified on 2026-10-22:

- `npm test` from `frontend/`: TypeScript type-check passed; Vite production build passed; 20 Vitest tests passed; 3 Node static-release tests passed (23 tests total).
- `python -m pytest -q` from the repository root: 200 passed in 1.88 seconds. One `PytestCacheWarning` remains because Windows denied creation of `.pytest_cache/v/cache/nodeids`; it did not affect the test result.
- `git diff --check`: passed. Git printed line-ending normalization warnings for modified text files (`LF will be replaced by CRLF`), with no whitespace errors.
- `python scripts/build_static_site.py --output dist/aegisai-react-release-review-20261022`: emitted exactly the nine entries in `scripts/build_static_site.py`'s allowlist. This output is an ignored local review artifact, not a deployment.
- The active assessment files have CRLF worktree line endings (`core.autocrlf=true`); after normalizing CRLF to LF, their SHA-256 digests match the committed and backup blobs. No report content was edited.
- A browser inventory check found no enabled browser surfaces in this environment. Manual browser, keyboard, screen-reader, touch, zoom/reflow, and response-header checks therefore remain pending; automated DOM tests are not substitutes for them.
