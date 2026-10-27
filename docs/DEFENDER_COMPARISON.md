# A measurable defensive-policy improvement

Current setup and dated regression results: [DEVELOPMENT.md](DEVELOPMENT.md) and [CURRENT_STATUS.md](CURRENT_STATUS.md). Commands below use the Windows Python 3.11 launcher with dependencies installed; a project virtual environment is preferred for a fresh setup.

The original scripted defender can spend every turn investigating new alerts. With enough incoming alerts, it never reaches its containment logic. `EvidencePrioritizedBlueAgent` adds a separate policy that responds to urgent, investigated evidence before accepting more investigation work. The original policy and public episode remain unchanged, so before/after results remain reviewable.

This is a deterministic policy improvement, not learned adaptation or a measurement of an AI model.

## Run and inspect the comparison

From the repository root with the reviewed Python dependencies installed:

```powershell
py -3.11 scripts/run_defender_benchmark.py
```

The command creates a new report under the ignored `.aegisai-local/benchmarks/` directory. Use `--stdout` for machine-readable JSON without writing files, or `--output <new-path>` for an explicit destination. Existing reports are never overwritten by the CLI.

For one small demonstration:

```powershell
py -3.11 scripts/run_defender_benchmark.py --templates credential_reuse_known_vuln --seeds 1
```

Use the virtual environment's Python instead of `py -3.11` when following [DEVELOPMENT.md](DEVELOPMENT.md).

The reviewed complete result is [defender_benchmark_v1.json](../results/evaluation/defender_benchmark_v1.json). It records every matched case, aggregate and per-template counts, defensive response records, investigated supporting alerts, final isolated hosts, and deterministic audit/telemetry fingerprints. Code fingerprints identify the relevant engine and policy source files with normalized line endings. Wall-clock timings, generated episode UUIDs and timestamps are excluded from the comparison contract.

## What changed in the defender

- Investigated high/critical alerts with recognized threat events on the same host take priority over additional investigations.
- An alert's label or severity alone does not trigger isolation; the policy first obtains its evidence.
- Inventory must confirm isolation. Rejected requests remain eligible on the next decision instead of being cached as completed.
- Logging can be improved using visible inventory. Known-service patching and incident recording follow containment.
- Each decision uses only `BlueObservation` and its advertised actions. Only the Controller executes the request.

The policy is stateless, so it carries no action-success cache between episodes. Tests cover benign and missing evidence, mismatched hosts, untrusted event strings, denied proposals, advertised permissions, and the Controller integration.

## Method and results

The benchmark runs both policies with the same scripted attacker on every combination of all six current scenario templates and seeds `(1, 2, 7, 9, 17)`. Each side gets a freshly constructed scenario, Controller and agents. This yields **30 matched pairs / 60 episodes**.

The primary outcome is whether the simulator records the attacker's data-exfiltration objective. A pair improves only when the baseline reaches that objective and the candidate does not. Cases where neither attacker reaches the objective are recorded as unchanged, rather than credited as defensive improvements.

| Scenario template | Baseline objectives reached | Candidate objectives reached |
|---|---:|---:|
| credential_reuse_known_vuln | 1 / 5 | 0 / 5 |
| credential_reuse_service | 0 / 5 | 0 / 5 |
| credential_reuse_workstation | 1 / 5 | 0 / 5 |
| web_exploit_high_noise | 1 / 5 | 0 / 5 |
| web_exploit_lateral_exfil | 0 / 5 | 0 / 5 |
| web_exploit_restricted_lateral | 0 / 5 | 0 / 5 |
| **Total** | **3 / 30** | **0 / 30** |

There are **3 improved pairs, 0 regressed pairs, and 27 unchanged pairs**. The candidate's successful isolation requests have investigated same-host evidence and Controller authorization. These counts are development-regression evidence from authored scenarios, not independent held-out evidence or real-world efficacy estimates.

## The availability cost

The candidate isolates the simulated website at step 3 in these cases and leaves it isolated through the episode. The mean number of isolated hosts at the end is **1.00** for the candidate versus **0.83** for the baseline. Some baseline cases already isolate multiple hosts; the candidate is not uniformly more disruptive in every pair.

The simulator has no business-availability model, human approval workflow for restoration, or automatic recovery in this policy. Final isolated-host count is a coarse disruption proxy, not a cost-benefit score. A next policy should compare more selective controls and verified recovery, with tests that prevent reopening the attack path.

## How to interpret the evidence

- Templates share a general web-entry/credential-pivot structure. Wider independent attack families and more defender policies are still needed.
- The fixed step budget and restricted network paths can already prevent the baseline attacker from finishing. The paired accounting preserves those unchanged outcomes.
- Detection and mitigation alert denominators change when the policy changes the course of an episode. The benchmark exports those metrics but uses matched objective outcomes as its main comparison.
- Neither policy calls an LLM. A live-provider experiment would need a separate bounded protocol, repeated runs and its own evidence.
- Software tests and synthetic results establish reproducibility of this implementation, not production readiness or security certification.

## Supporting reliability work

The same improvement pass also tightened the local prototype:

- Simulated-activity telemetry rejects unrelated HTTP/error metadata instead of accepting ambiguous event shapes.
- Scheduler shutdown stops queued tenants and retries after the active worker returns.
- Extremely long HTTP `Content-Length` values receive a structured bounded response instead of crashing integer conversion.
- Research splits preserve one-shot seed iterators and reject duplicate scenario pairs.
- Adaptive-memory context excludes undeclared or partially malformed scenario provenance and enforces the exact context-character budget, including separators.
- A pinned dependency environment and Windows/Linux verification workflow make future regressions easier to catch. Hosted workflow results must be inspected after a push; local validation was performed on Windows.
