# DECISIONS

> Historical architecture decisions, grouped by the simulator milestone in which each was recorded. Statements such as "deferred" or "not added in this phase" describe that milestone. See [CURRENT_STATUS.md](../CURRENT_STATUS.md), the [documentation index](../README.md), and [development setup](../DEVELOPMENT.md) for current implementation and runtime guidance.

Interpretations made where the spec was silent. None change the approved architecture.

| # | Decision | Reason |
|---|----------|--------|
| D1 | Packages live at repo root (`environment/`, `telemetry/`), per spec §15. | Matches target structure. |
| D2 | Observation *models + builders* live in `telemetry/observation_builder.py` (spec §15 file). Builders are called by the environment/Controller side only. | Spec §6: agents never build their own observations. |
| D3 | `ENUMERATE_PORT` = reveal reachable open ports; `DISCOVER_SERVICE` = identify services on already-enumerated ports. `EXPLOIT_*` requires the service to be identified first. | Gives the spec's two discovery actions distinct, ordered meanings. |
| D4 | `ATTEMPT_ACCESS` may originate from any Red foothold (incl. outside). `LATERAL_MOVE` must originate from a *different* compromised host. | Separates initial access from lateral movement for telemetry/ATT&CK later. |
| D5 | Unknown, undiscovered and unreachable hosts all return the same "no response" result to Red. | Avoids giving Red an existence oracle for hidden hosts. |
| D6 | `RESTORE_SERVICE` with `service` re-enables it; without `service` it lifts host isolation. | Spec lists no separate un-isolate action. |
| D7 | Detection is rule-based per event type and host logging level (basic/verbose); events below the level are recorded as ground truth but invisible to Blue and not retroactive. Seeded benign events produce false-positive alerts. | Makes `INCREASE_LOGGING` meaningful and false-positive rate measurable. |
| D8 | Background noise is derived from `Random(f"{seed}:{step}")`, not a stateful RNG. | Replayable regardless of action history. |
| D9 | `PATCH_SIMULATED_VULNERABILITY` only works on vulnerabilities in `blue_known_vulns` (scenario-defined). | Lets templates model zero-day-like vs known flaws. |
| D10 | MITRE ATT&CK technique IDs are **not** attached to actions yet. | Spec §10 requires verified mappings; deferred to the phase that adds them, not guessed. |
| D11 | Only 2 scenario templates in Phase 1 (registry supports the 10-15 target). | Smallest foundation that proves the template+seed mechanism. |
| D12 | Venv/pip used for Phase 1; PostgreSQL/SQLAlchemy/FastAPI deferred to their phases. | Spec §14 ordering. |
| D13 | `advance_time()` raises `EpisodeCompleteError` once the episode is done (goal reached or `step >= max_steps`) and changes nothing. `apply_*` keep returning non-mutating failure results. | Time advance is controller-driven, so misuse is a programming error and should be loud. The Controller must check `is_done()` before advancing. |
| D14 | Each action has a declared allowed-parameter set (`RED_/BLUE_ALLOWED_PARAMETERS`); unknown keys are rejected at schema level, and re-checked in the simulator for unvalidated objects. Required-ness is still enforced by the simulator (`INVALID_PARAMETER`). | No silently ignored parameters. |

## Phase 2 — Central Controller

Implemented a controller-gated execution boundary around the Phase 1 simulator.

- Agents submit typed `RedAction` / `BlueAction` requests to `Controller`.
- Controller enforces Red → Blue turn ordering and one action per role per step.
- Invalid/wrong-role/phase actions are rejected without simulator mutation and are audited.
- The simulator remains deterministic and contains no LLM/external execution path.
- Role-specific observations are generated from environment state and returned by the controller.
- Structured audit records capture authorization, outcome, state-change references, and telemetry IDs without storing hidden chain-of-thought.
- Episode termination is fail-closed at the controller boundary.
- No database, API, LLM, RAG, Docker sandbox, or adaptive memory was added in this phase.

## Phase 4 — Scripted Blue Baseline

- Blue receives only `BlueObservation` and emits one typed `BlueAction`.
- Blue never receives a simulator or scenario reference and cannot mutate environment state directly.
- Defensive priority is deterministic: investigate new alert → patch known vulnerability when applicable → isolate suspicious host → block visible source → mark incident → increase logging → monitor.
- The scripted Blue agent is a baseline for later LLM Blue evaluation, not an autonomous production defender.

## Phase 8 — LLM Red Agent

- `LLMRedAgent` receives only `RedObservation` and returns one typed `RedAction`.
- The provider receives bounded, serialized role-specific observation data; no Scenario, Simulator,
  Controller, or hidden environment state is passed to the agent.
- Provider output is validated as `RedAction` before the agent returns it.
- Invalid provider output may be retried at most twice; there is no fabricated fallback action.
- The agent never executes actions. The Controller remains the sole authorization/execution gate.
- No real LLM API or external network dependency is required in Phase 8; `FakeLLMProvider` is used
  for deterministic tests. A concrete provider adapter can be plugged in later.

## Phase 9 — XAI Decision Traces

- Explainability is implemented as structured observation → evidence → decision → outcome data.
- Agent rationale is stored separately from controller/environment facts.
- Hidden chain-of-thought is neither requested nor stored.
- Evidence is extracted only from the role-specific observation available before the action.
- The controller owns the XAI logger; agents never receive it.
- Expected outcome is a deterministic description of action intent, not an LLM prediction.
- Post-hoc lessons remain empty until the validated adaptive-memory phase.

## Phase 10 — Adaptive Memory
- Adaptive learning uses evidence-grounded, versioned knowledge patches rather than automatic model-weight retraining.
- Candidate lessons are derived only from role-visible XAI traces.
- Candidate patches require trace, episode, scenario, and step references.
- Validation is an explicit experiment gate; this MVP requires held-out validation and a configurable minimum improvement threshold.
- Only validated patches can be rendered into future agent context.
- Rejection and revocation preserve version history; memory never executes actions or bypasses the Controller.

## Phase 11 — Threat Intelligence + RAG
- Use a deterministic lexical retriever for the MVP; no internet dependency and no vector database yet.
- Treat all retrieved content as untrusted data, never executable instructions.
- Keep ingestion, normalization, storage, retrieval, and context rendering separate.
- Preserve externally verified MITRE/CVE identifiers when supplied; do not invent mappings.
- Keep RAG context provider-independent and outside the simulator/controller execution boundary.

## Phase 12 — Dashboard
- Added a dependency-free read-only dashboard prototype for metrics, Red/Blue timeline, XAI traces, adaptive memory, and threat-intelligence context.
- Frontend cannot execute actions; the controller remains the sole execution gatekeeper.
- Threat-intelligence content is treated as untrusted and HTML-escaped before DOM insertion.
- Local deterministic demo data is used. Backend API/database integration remains deferred.
- The eventual production frontend can be migrated to the preferred React/Vite stack without changing the data contracts.

## Phase 13 — Research Experiments

- Added an explicit A/B/C experiment protocol: A = Scripted Red + Scripted Blue; B = LLM Red + LLM Blue without adaptive memory; C = LLM Red + LLM Blue with validated adaptive memory.
- Added an observation-driven `LLMBlueAgent` using the existing provider abstraction. The provider remains a decision service; the Controller remains the sole executor.
- Added deterministic train/validation/held-out scenario splitting and a hard rule that held-out test scenarios cannot generate adaptive memory.
- Added immutable experiment manifests with provider/model/temperature/seed/split configuration and a reproducible fingerprint.
- Added a bounded validated-memory context gate. Unvalidated, malformed, or test-derived patches are not supplied to the adaptive agent.
- Added a research comparison harness and JSON report serializer. Offline tests use a clearly labeled policy test-double; this is not claimed as scientific LLM evidence.
- Scientific runs must use a real provider adapter with fixed model/version/configuration and repeatable seeds; the offline test-double exists only to verify experiment plumbing.

## Phase 14 — Security Testing

- Security testing is implemented as a dedicated `tests/security/` suite rather than as a claim of formal security proof.
- The suite verifies the simulator/controller security boundary, fail-closed structured-output handling, observation isolation, telemetry/RAG prompt-injection handling, adaptive-memory poisoning/leakage controls, bounded experiment termination, auditability of denied actions, and absence of direct command/network execution primitives in application modules.
- Retrieved threat intelligence, telemetry, and agent-generated text remain untrusted data.
- No real-world exploitation, production connectivity, arbitrary shell execution, or live CTI dependency is introduced.

## Phase 16 — Concrete OpenAI provider boundary

- Added `OpenAIResponsesProvider` as a concrete adapter behind the existing `LLMProvider` contract.
- Use the OpenAI Responses API structured-output parser with caller-supplied Pydantic models.
- Keep retries in the agent layer rather than duplicating them in the provider adapter.
- Require `OPENAI_API_KEY` for live construction; never store credentials in source files.
- Keep the provider free of simulator/controller/tool execution dependencies.
- Keep all Phase 16 tests offline through dependency/client injection.
