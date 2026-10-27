# AegisAI documentation

Start with the public demo to understand the research question, then use the evidence and architecture guides to inspect the implementation.

## Present and reproduce

| Guide | Use it for |
|---|---|
| [Judges' guide](JUDGES_GUIDE.md) | The pitch, suggested walkthrough, evidence to explain, and likely questions. |
| [Development setup](DEVELOPMENT.md) | Pinned Windows/Linux setup, checks, builds, and repeatable benchmarks. |
| [Defender comparison](DEFENDER_COMPARISON.md) | The paired 30-case experiment, measured improvement, availability cost, and limits. |
| [Frontend guide](../frontend/README.md) | Page routes, assessment samples, static builds, and publication boundaries. |
| [Reviewed evaluation evidence](../results/evaluation/) | Checked-in defender benchmark and synthetic detection reports. |

## Choose the right experience

| Experience | Open locally | What it shows |
|---|---|---|
| Public landing page | `http://localhost:5174/` | The project story and a clear path into the exercise. |
| Public walkthrough | `http://localhost:5174/dashboard.html` | A recorded synthetic attack, role-visible evidence, outcomes, presentation mode, and a fixed header comparison. Works without a backend after frontend setup. |
| Local operations dashboard | `http://localhost:5174/local-dashboard.html` | Authenticated local synthetic findings, Detection Lab, scenarios, assessments, reports, and cases. Requires the separate loopback API and its development token. |

Start Vite with `npm.cmd --prefix frontend run dev -- --host 127.0.0.1` from the repository root. The public walkthrough is the simplest judging route. The local dashboard is a separate prototype and is excluded from the public static package; [its guide](PHASE7A_LOCAL_DASHBOARD.md) explains startup and scope.

## Understand the engineering

| Topic | Reference |
|---|---|
| Controller, simulator, and research evaluation | [Main project overview](../README.md#how-it-works), [evaluation guide](../evaluation/README.md), [Red agent guide](../agents/red/README.md) |
| Local telemetry and deterministic rules | [Telemetry foundation](PHASE3_READ_ONLY_TELEMETRY_AND_DETECTION.md), [detection engineering](DETECTION_ENGINEERING_AND_EVALUATION.md) |
| Synthetic operations and private API | [Local prototype](PHASE1_LOCAL_SYNTHETIC_SECURITY_OPS_PROTOTYPE.md), [backend foundation](PHASE2_PRIVATE_BACKEND_FOUNDATION.md) |
| Investigations and scenario validation | [Investigation cases](PHASE4_INVESTIGATION_CASES_AND_MEMORY.md), [safe purple-team validation](PHASE5_SAFE_PURPLE_TEAM_VALIDATION.md) |
| LLM provider and experiment harness | [Provider boundary](PHASE16_OPENAI_PROVIDER.md), [live experiment harness](PHASE17_LIVE_EXPERIMENT_HARNESS.md) |
| Trust boundaries and release scope | [Product boundary](PHASE1_PRODUCT_BOUNDARY_AND_THREAT_MODEL.md), [deployment architecture](PHASE8_DEPLOYMENT_ARCHITECTURE.md), [release candidate](PHASE10_RELEASE_CANDIDATE.md) |

## Repository conventions

- Source packages stay at the repository root to preserve Python imports and script entry points.
- `frontend/data/` contains reviewed public samples; `results/` retains original research evidence.
- `.aegisai-local/` contains ignored local state, judging packets, databases, and test artifacts. Old root-level `.pytest-*` folders are preserved under `.aegisai-local/test-artifacts/legacy/`.
- `dist/` contains generated, allowlisted public packages. It is not source.
- [Historical decisions and handoff](history/README.md) preserve earlier implementation context. Phase reports describe the work and checks recorded at that time; current source and fresh verification take precedence.

The public demonstration and authored synthetic evaluations do not establish production readiness or real-world cybersecurity effectiveness.
