# AegisAI external capability audit and implementation plan

> Historical audit dated 2026-10-24. Vendor descriptions, capability judgments, code inventory, and worktree observations below record that audit and have not been revalidated as a new vendor comparison. For the current repository and fresh local checks, use [CURRENT_STATUS.md](CURRENT_STATUS.md), [development setup](DEVELOPMENT.md), and the [documentation index](README.md).

**Implementation since the audit:** the local store now initializes schema version 6; investigations and bounded scenario history are available. `.github/workflows/verify.yml` provides Windows/Linux validation and local static packaging, not a hosting/deployment pipeline. The public frontend now uses a guided recorded replay with searchable role-filtered evidence; the private operations dashboard remains a separate loopback API client. Historical statements about schema version 4, missing CI, or older README content below describe the audit date.

**Audit date:** 2026-10-24  
**Scope:** Phase 0 repository and public-source audit only. This document does not authorize client connectivity, production actions, release publication, or deployment.

## Executive summary

AegisAI already contains a substantial simulator and local synthetic operations prototype. It includes a deterministic environment, Red/Blue agents behind a simulator Controller, telemetry rules, scenario replay and evaluation, a loopback-only private API backed by SQLite, live logs from a dedicated local test site, a separate fixed-check local assessment policy/controller, and a local React dashboard with findings, assessment, Detection Lab, System Health, and Executive Reports views.

These capabilities are not a hosted security service. The private API uses ephemeral local development bearer tokens and synthetic tenant records; the private API, website source, and fixed assessment are loopback/local workflows. Detection and benchmark results are authored from synthetic fixtures and do not demonstrate real-world accuracy. The existing simulator Controller authorizes simulator actions only. A separate `LocalAssessmentPolicy`/`LocalAssessmentController` handles its narrow HTTP observations.

The external product pages support high-level capability themes, not a basis for reproducing vendor implementations. AttackIQ describes ATT&CK-mapped adversary emulation, control validation, repeatable scenarios, reporting, and readiness measurement. SENTRYFORGE advertises concurrent AI Red/Blue/research agents, sandboxed tool use, adaptive memory, timestamped scoring, and reports; its own public page says the service is in core development and invites waitlist access. MITRE's accessible CyberLayer page describes a high-fidelity digital-twin simulation for experimentation, training, and AI development/evaluation. These statements are vendor/organization descriptions, not independent verification of product behavior. The supplied CyberLayer capture returned HTTP 403; no private implementation was accessed or inferred.

**Recommended first product increment:** reconcile the stale project summaries, then add only provenance-backed, versioned MITRE ATT&CK metadata for existing synthetic scenarios/rules where mappings can be reviewed. Keep it explanatory and evaluation-only. Do not add external target execution, autonomous remediation, customer telemetry, or an LLM investigation path as part of that increment.

## Repository and implementation facts

### Structure and stack

- Python simulator and domain model: `environment/`, `controller/`, `agents/`, `telemetry/`, and `xai/`.
- Synthetic security operations and evaluation: `platform_prototype/`, `evaluation/`, `memory/`, and `threat_intelligence/`.
- Local private service: `private_api/`, `local_assessment/`, and local CLI scripts under `scripts/`.
- Frontend: React + TypeScript + Vite under `frontend/`; public entries are `/`, `/dashboard.html`, and `/privacy.html`. `/local-dashboard.html` is a separate local development entry.
- Tests: pytest suites under `tests/unit/`, `tests/evaluation/`, and `tests/security/`; Vitest tests under `frontend/tests/`; Node static-release checks under `tests/frontend/`.
- Python dependencies declared in `requirements.txt` include Pydantic, pytest, and OpenAI. Frontend dependencies are declared in `frontend/package.json` and lockfile. No additional dependency is proposed here.
- The private API is implemented with Python's standard-library HTTP server rather than a web framework. `private_api/store.py` owns SQLite setup and migrations; the current schema sets `PRAGMA user_version = 4`.
- The static publishing script `scripts/build_static_site.py` declares a strict nine-file allowlist. The local dashboard, backend, local databases, telemetry, and evaluation/report artifacts are outside that allowlist.
- No Docker, Compose, Procfile, hosting-platform, or infrastructure-as-code deployment configuration was found in the repository file inventory. The static publisher is a local build step, not a complete deployment pipeline.

### Current routes, identity, and data boundaries

`scripts/run_private_api.py` accepts a local SQLite path, fixture, synthetic tenant bootstrap values, and port. It starts the API on `127.0.0.1:8766`, issues random expiring development bearer tokens, and starts the local telemetry scheduler. `private_api/auth.py` stores token digests in process memory and produces a `Principal` containing tenant ID and read-only scopes. API operations derive tenant scope from that principal. There is no public registration flow or browser-controlled tenant authorization.

Registered route families in `private_api/server.py` are health; findings/evidence and incidents/reports; telemetry findings/evidence/reports; processing and fixed website-source status; assessment report; evaluation summary; and executive report. The evaluation, assessment, and executive report reads require `reports:read`. The route for the evaluation report reads a bounded, fixed report file and projects summary data; it does not run the evaluator. The executive report builder consumes tenant-filtered findings/evidence. The assessment API route reads a stored report; the assessment CLI is a separate operator-invoked action and has no caller-provided URL/path.

The local assessment catalog permits only three versioned check IDs against `http://127.0.0.1:8767`, using fixed paths and explicit policy authorization. It has bounded requests, timeouts/deadline, response limits, and redirect rejection. Its observations are not general vulnerability scanning. Telemetry ingestion reads a fixed local JSONL source; caller-supplied paths, tenant IDs, and target URLs are not accepted by the fixed integration.

The frontend API client uses the fixed loopback API origin and Authorization header. The dashboard token is held in memory and cleared on disconnect. Executive report HTML is generated from the validated in-memory response with HTML escaping and a restricted filename. The public static pages remain a separate experience.

Environment configuration found in the code is limited to the optional research/live-LLM harness (`OPENAI_API_KEY`, `OPENAI_MODEL`) and explicit CLI arguments such as database path. The local private API/dashboard/assessment workflow does not need an LLM. A real API key must never be placed in frontend assets or synthetic telemetry.

### Existing uncommitted work and documentation drift

At audit start, the worktree contained modified tracked files and untracked Phase 7B and report-integration files. The full existing state is preserved; this audit adds one document only. The current README and `docs/history/PROJECT_HANDOFF.md` still describe the dashboard as lacking the later evaluation/report integration and do not fully describe Assessment/Executive Reports. `docs/PHASE7B_LOCAL_ASSESSMENT_GATE.md` says API/dashboard report integration is a future step, although current source includes the authenticated assessment report route and view. The Phase 0 architecture document also describes the earlier pre-Phase-2 system. These are documentation consistency issues, not evidence that the code paths are absent.

## Research inputs and evidence quality

The three supplied JSON captures were present in the user's Downloads folder and reviewed by filename, page metadata, status, and structured capture fields:

| Capture | Captured page result | Use in this audit |
|---|---|---|
| `AttackIQ.json` | AttackIQ homepage, HTTP 200 | Discovery/reference capture only. Product capabilities below are checked against AttackIQ's public pages. |
| `MITRE CyberLayer.json` | MITRE CyberLayer page, HTTP 403, title “Access Denied” | Confirms the supplied capture did not retrieve the page. It provides no basis for claims about private implementation. |
| `SENTRYFORGE.json` | SENTRYFORGE homepage, HTTP 200 | Discovery/reference capture only. Public capability statements remain advertised claims, not independent test results. |

Accessible public references reviewed on 2026-10-24:

- [AttackIQ: Adversary Emulation](https://www.attackiq.com/solutions/adversary-emulation/) — describes ATT&CK-mapped testing, repeatable scenarios, control-gap analysis, and reporting. These are AttackIQ's claims.
- [AttackIQ: What We Do](https://www.attackiq.com/what-we-do/) — describes automated control validation and ATT&CK alignment. These are AttackIQ's claims.
- [MITRE: CyberLayer](https://www.mitre.org/our-impact/intellectual-property/cyberlayer) — public summary describes a high-fidelity cyber digital twin for experimentation, training, and AI development/evaluation. It does not disclose the private implementation.
- [MITRE ATT&CK](https://attack.mitre.org/) — public knowledge base of tactics and techniques based on real-world observations; use its published identifiers only when a mapping is explicitly reviewed.
- [SENTRYFORGE homepage](https://sentryforge.org/) and [AI Transparency Notice](https://sentryforge.org/legal/ai-transparency) — describe concurrent AI agents, sandboxing, memory, timestamped scoring, reporting, model-provider use, and stated limitations. They also indicate the offering is still in development. Claims are not independently verified here.

No proprietary source, private API, restricted service, or undocumented competitor implementation was accessed. No vendor code, assets, or algorithms are proposed for copying.

## Capability matrix

“Public reference” means the linked party publicly describes the capability; it is not a claim that AegisAI reproduced or independently validated that vendor feature. AegisAI status is based on the checked-in source and documentation, not on product-name matching.

| Capability | Public reference/platform | Current AegisAI implementation and classification | Gap and original AegisAI proposal | Security implications | Required tests | Deployment impact |
|---|---|---|---|---|---|---|
| Security-control validation | AttackIQ publicly describes ATT&CK-mapped control validation and repeatable testing. | **Partially implemented:** fixed local website header checks and the separate Phase 7B policy-gated HTTP observation catalog; synthetic telemetry checks. Fixed loopback target only. | Improve evidence/provenance and stable control/check IDs for the existing local and synthetic checks. No arbitrary target support. | Keep exact target/path allowlists, explicit policy authorization, redirect denial, budgets, and no response actions. | Policy allow/deny, zero-request-on-deny, redirect, timeout, limits, evidence, and repeatability tests. | Local-only; no new public routes or deployment requirements. |
| Adversary emulation and scenario testing | AttackIQ describes repeatable ATT&CK-mapped emulation; SENTRYFORGE advertises adaptive sandboxed Red/Blue rounds. | **Implemented for synthetic research / partial versus these advertised products:** deterministic simulator, typed Red/Blue proposals, Controller authorization, scripted and LLM-backed simulation agents, and replay scenarios. The simulator uses its own environment and action catalog. | Expand only reviewed synthetic scenarios and measurement; do not translate vendor playbooks or enable real targets. | Keep agents proposal-only; Controller remains the simulator execution gate. No live exploit tooling or production credentials. | Action-schema, authorization, no-mutation-on-denial, determinism, scenario-boundary, and security tests. | Existing Python CLI/tests only; preserve public static separation. |
| Detection engineering | AttackIQ describes control-failure analysis and ATT&CK-oriented detection/tuning data. | **Partially implemented:** deterministic synthetic telemetry rules with versioned IDs, evidence, correlation, dataset ground truth, metrics, and robustness regressions. These do not operate on client telemetry. | Improve rule documentation and map a rule only when its behavior and reference are reviewed; keep thresholds unchanged absent evidence. | Preserve input validation, deduplication, provenance, tenant isolation, bounded processing, and the statement that synthetic results are not real detection accuracy. | Positive/negative/boundary tests, evidence tests, malformed/conflicting data, deterministic evaluator and regression checks. | Local synthetic processing; no external source needed. |
| MITRE ATT&CK mapping | AttackIQ advertises ATT&CK mapping; MITRE publishes ATT&CK identifiers and definitions. | **Missing as a verified AegisAI product mapping:** `docs/history/DECISIONS.md` explicitly defers technique IDs; existing threat-intelligence metadata can hold curated IDs but does not establish mappings for current rules/actions. | First proposed increment: an independently reviewed, versioned mapping catalog for existing synthetic scenarios/rules, with source URL, ATT&CK version, rationale, and “unmapped” allowed. No inferred IDs. | Incorrect mappings can mislead analysts; every mapping needs provenance and review. Treat retrieved references as untrusted content. | Schema validation, valid-ID fixtures, source/version provenance, unmapped case, and no fabricated mapping tests. | Local data/doc addition; no new dependency or runtime service. |
| Performance and control measurement | AttackIQ describes readiness, control performance, and exposure trends; SENTRYFORGE advertises timestamped rubric scoring. | **Partially implemented:** simulator metrics and Phase 6B scenario-rule confusion metrics with denominators and invalid inputs separated. No production control telemetry or service-level/performance benchmarking. | Clarify metric definitions and extend synthetic per-control effectiveness/trend measures only where denominators and evidence exist. | Avoid false precision; report missing/unscorable values explicitly and never call synthetic metrics operational effectiveness. | Hand-calculated denominators, zero-denominator, repeated run determinism, invalid-input, and regression tests. | Bounded local evaluation; no production infrastructure. |
| Scenario-based validation and regression | AttackIQ and SENTRYFORGE publicly describe repeatable scenarios; SENTRYFORGE advertises memory across rounds. | **Implemented for synthetic data:** versioned replay/evaluation dataset and robustness suite; adaptive-memory research tooling exists separately. | Continue independent scenario authoring and explicit change rationale. Avoid automatic threshold tuning from benchmark labels. | Keep ground truth outside detector input; bound resources; never run evaluation data in the normal tenant database. | Dataset integrity, duplicate IDs, ground-truth separation, deterministic ordering/fingerprint, incomplete-run, and behavior-baseline tests. | Local CLI and test additions only. |
| AI-assisted investigation | SENTRYFORGE advertises a research agent and external intelligence synthesis; its notice describes model use and probabilistic limitations. | **Partially implemented in a different scope:** LLM-backed agents propose simulator actions; offline threat-intelligence retrieval exists. There is no LLM investigation of private API findings or client evidence. Executive reports are deterministic templates. | Defer AI investigation. If later approved, start with synthetic-only, evidence-bounded summaries, explicit provenance, opt-in provider use, evaluation, and human review. | Model output is untrusted; external calls may disclose data. No client data, execution tools, credentials, or autonomous decisions should enter this path. | Prompt-injection-as-data, hallucination/unsupported-claim, redaction, deterministic fallback, and provider-disabled tests. | Requires provider/data-handling review; no expansion in current phase. |
| Evidence-backed reporting | AttackIQ and SENTRYFORGE advertise structured/executive or timestamped reporting. | **Implemented for synthetic sources:** incident reports, telemetry evidence, assessment observations, evaluation summaries, authenticated tenant-scoped executive report, and client-side escaped HTML export. “Confirmed findings” remains empty where sources support only inferred risks. | Improve report schema versioning and provenance review; preserve observations vs inferred risk vs confirmed claims. | Escape browser/export text, omit secrets/raw bodies, authorize by tenant and `reports:read`, and fail safely on incomplete evidence. | Schema, evidence-reference validation, cross-tenant denial, escaping, safe filename, empty/unavailable, and report determinism tests. | Existing private API and local dashboard; no public publishing. |
| Purple-team orchestration and continuity | SENTRYFORGE advertises simultaneous autonomous agents, checkpoints, and automatic recovery; AttackIQ advertises continuous testing. | **Partially implemented:** deterministic turn-based simulator Controller and a single-process local telemetry scheduler. No concurrent autonomous operational Red/Blue service, distributed scheduler, or client deployment. | Keep simulator turns unchanged. Any future multi-instance scheduling requires explicit coordination design and operational ownership. | Prevent overlap and action bypass; maintain shutdown/deadline/retry bounds; no public job trigger. | Scheduler overlap/restart/shutdown/retry/timeout/idempotency tests; simulator behavior regressions. | Local scheduler only; distributed service deployment is a separate project. |
| Private identity, tenancy, and production integrations | Public vendor pages imply enterprise/platform operation but do not provide AegisAI implementation details. | **Partially implemented for a local prototype:** synthetic tenants, in-memory expiring local tokens, scopes, server-derived tenant IDs, tenant-scoped SQLite readers, audit events. No production IdP, customer enrollment/authorization registry, secret manager, or real connector. | Before any pilot, define identity/tenant lifecycle, written scope authorization, data governance, key custody, deployment, monitoring, and incident response. | Current local bearer model is not production identity. No real customer data or credentials. | Tenant isolation, expiry, unauthorized access, audit, secret-handling, migration, backup/restore, and abuse cases. | Requires a separate security/operations architecture and approvals; current API is not deployable SaaS. |
| MITRE CyberLayer-style simulation environment | MITRE's public summary describes a high-fidelity digital twin for experimentation, training, and AI evaluation. | **Partially similar only at a broad research level:** AegisAI has a deterministic synthetic network simulator and evaluation/replay tools. No evidence establishes CyberLayer equivalence or comparable fidelity. | Treat CyberLayer only as a reference for the general value of bounded, reproducible cyber simulation. Do not claim parity or infer private capabilities from the 403 capture. | Keep lab/simulator isolated from production and use synthetic state. | Environment invariants, deterministic runs, role visibility, action authorization, resource bounds. | Local research capability; no deployment change. |
| Release and hosting | Public static research/demo product direction documented by AegisAI. | **Partially implemented:** Vite public pages and a strict nine-file static publisher exist; local dashboard and private API are separate. No hosting/CI/infrastructure deployment configuration was found. | Keep public release static and allowlisted. Add hosting automation only after choosing provider, secret handling, privacy contact, review, and rollback requirements. | Never publish private dashboard/API/database/reports or credentials; review every artifact. | Exact publisher allowlist, generated-file inventory, secret/path scan, public-entry tests, and hosted header/accessibility checks. | Public static output can be prepared locally; production deployment is not configured or authorized. |

## Staged implementation plan

This is a proposal for later approval, not authorization to begin these phases.

### Stage 0 — Reconcile and freeze the current baseline

1. Keep all current worktree changes intact and review the current `git diff` before any future feature work.
2. Update stale summaries (`README.md`, `docs/history/PROJECT_HANDOFF.md`, `docs/PLATFORM_VISION_PHASE0_ARCHITECTURE.md`, and affected Phase 7 notes) to match the current source without rewriting historical claims.
3. Record reproducible commands, supported Python/Node versions, migration behavior, local-only boundaries, and which test suites were actually run.
4. Run focused tests after each approved change; run release gates only when safe and relevant. Preserve the static allowlist exactly unless separately approved.

### Stage 1 — Provenance-backed ATT&CK references

1. Inventory existing synthetic scenario and rule semantics; do not map actions or detections by name alone.
2. Add only mappings reviewed against the public ATT&CK version/reference. Store technique ID, name, version, source URL, rationale, and review state; allow unmapped entries.
3. Keep mappings as metadata. Do not alter simulator actions, detection thresholds, or findings based solely on a mapping.
4. Add schema, provenance, invalid-ID, unmapped, and UI/API non-leakage tests. Show the mapping as context, not as validation proof.

Potential files, subject to architecture review: `platform_prototype/` mapping metadata/model, focused `tests/unit/` coverage, and a small documentation update. No public frontend change is required for the first increment.

### Stage 2 — Better synthetic control-validation evidence

1. Represent the existing approved checks and synthetic detector scenarios with stable control/check identifiers, expected observation, actual observation, evidence references, and explicit not-run/incomplete/denied states.
2. Evaluate each scenario against its declared synthetic expectation. Keep invalid inputs out of ordinary detection metrics and state the counting unit/denominators.
3. Preserve fixed loopback check catalog, policy reauthorization, redirect rejection, request/body/deadline limits, and no-response-action behavior.
4. Add reproducibility, denied-no-request, failure recovery, evidence completeness, and policy-boundary tests.

### Stage 3 — Evidence and investigation improvements (synthetic only)

1. Continue deterministic correlation and report improvements first, with observed evidence distinct from inferred risk and confirmed findings.
2. If an AI summary is later approved, run it only on a minimal synthetic evidence packet; show model/provider provenance and uncertainty; validate against deterministic expectations; require human review.
3. Do not let any model call the Controller, assessment runner, shell, arbitrary URL, or real response integration.

### Stage 4 — Separate production-readiness decision

Do not graduate the local prototype into a customer pilot until identity/tenant enrollment, signed authorization and scope, secret management, approved telemetry connectors, data retention/privacy, hardened storage/audit, scheduler coordination, network policy, observability, incident response, backup/restore, and independent security review are designed and tested. None of those controls can be inferred from a passing synthetic test suite.

## Cross-cutting security gates

- Keep the public static pages and private local dashboard/API separate; publish only the explicit allowlist.
- Synthetic fixtures remain the only data source until a distinct authorization, privacy, and connector review approves otherwise.
- Derive tenant identity from the authenticated principal, never from browser input.
- Treat telemetry, reports, model output, and retrieved threat-intelligence as untrusted data.
- No arbitrary target URLs or paths, public ingestion, production scans, credential collection, automatic remediation, or direct agent-to-Controller invocation.
- Use deterministic detection and report templates by default. Model usage remains explicit research-only and must not receive real client data.
- Preserve audit/evidence provenance and make unsupported, missing, or ambiguous results visibly incomplete rather than successful.

## Open decisions

1. Is the next approved objective public static research demonstration quality, local research quality, or a future private pilot? They have different security and deployment requirements.
2. Which existing synthetic rules/scenarios have enough source evidence for ATT&CK mapping, and who reviews those mappings?
3. Is the current local dashboard strictly a developer tool, or does it need a packaged local deployment model?
4. Which hosting provider, public privacy contact, repository visibility, and release/rollback controls would be approved for the static public site?
5. Is any external LLM use wanted for synthetic investigation, and what reproducible quality threshold would be required before showing it?

## Audit limitations

This is a repository/source and public-documentation review, not a penetration test, code-signing review, hosted release validation, independent vendor product test, or production-readiness assessment. External product pages are self-published descriptions. No MITRE CyberLayer private implementation was accessed. No application services, assessment/ingestion commands, database contents, or deployment targets were exercised as part of this audit.
