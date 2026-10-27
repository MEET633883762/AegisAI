# Phase 15 — Scenario Library and Unseen-Template Evaluation

Implementation record for this milestone. Historical verification totals below are preserved; use the [development guide](DEVELOPMENT.md) for Python 3.11 setup and [current status](CURRENT_STATUS.md) for fresh project checks. The public browser walkthrough uses scripted agents and is separate from opt-in provider experiments.

## Goal

Expand the deterministic cyber environment so experiments can distinguish seed variation from variation across authored scenario templates, while keeping the Red/Blue observation boundary unchanged.

## Scenario templates

| Template | Family | Attack pattern | Main variation |
|---|---|---|---|
| `web_exploit_lateral_exfil` | `web_exploit` | web vulnerability → credential pivot | baseline, basic logging |
| `web_exploit_high_noise` | `web_exploit` | web vulnerability → credential pivot | verbose logging + higher benign noise |
| `web_exploit_restricted_lateral` | `web_exploit` | web vulnerability → restricted service pivot | DMZ → internal access limited to port 8443; pivot is `host_d` |
| `credential_reuse_known_vuln` | `credential_reuse` | known vulnerability + credential pivot | verbose logging + moderate noise |
| `credential_reuse_workstation` | `credential_reuse` | known vulnerability → workstation pivot | credential valid on `host_c` |
| `credential_reuse_service` | `credential_reuse` | known vulnerability → service pivot | basic logging + higher noise |

Every `(template_id, seed)` pair is deterministic.

## Metadata

`ScenarioMetadata` records:

- scenario family
- attack pattern
- difficulty
- defender knowledge condition
- telemetry profile

Metadata is experiment/reporting data. It is **not** included in Red or Blue observations.

## Evaluation split

Phase 13's `build_default_split()` remains available for backward compatibility and seed-level partitioning.

Phase 15 adds `build_template_holdout_split()`. It requires disjoint train/validation/test template groups and therefore supports a stronger generalization test: the held-out test set contains scenario templates that are not present in training.

This is the preferred split when evaluating adaptation to held-out authored templates. The six templates share a general web-entry/credential-pivot structure; holding one out does not establish generalization to independent attack families or real networks. The [current paired defender comparison](DEFENDER_COMPARISON.md) uses all six templates and five seeds as development-regression evidence rather than held-out efficacy evidence.

## Security properties

- No real exploit execution.
- No network access.
- No agent access to `EnterpriseState`.
- Scenario metadata is not exposed through role observations.
- Unknown scenario templates fail closed with `KeyError`.
- Deterministic construction is preserved.

## Historical Phase 15 verification

Phase 15 tests:

```text
8 passed
```

Full regression after Phase 15:

```text
184 passed
```

A six-template scripted smoke experiment also completed successfully with 6 episodes. Its aggregate attack-success result is an engineering smoke-test result, not scientific evidence.
