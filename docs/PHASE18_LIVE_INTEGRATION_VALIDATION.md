# Phase 18 — First Live Integration Validation

Phase 18 adds an **offline preflight gate** for the real-LLM path. It does not contact OpenAI and it does not consume API credits.

## Purpose

Before any live experiment, verify that the local machine has:

- a configured `OPENAI_MODEL`
- a configured `OPENAI_API_KEY`
- the OpenAI SDK installed
- a valid `LiveExperimentConfig`

The preflight never prints or returns the API key itself.

## Offline check

```text
python scripts/live_preflight.py --model <model-name>
```

A missing key or model produces a non-zero exit status. No network request is made.

## Live episode

Only after the offline preflight succeeds should a user explicitly request one live episode:

```text
python scripts/run_live_episode.py --live --template web_exploit_lateral_exfil --seed 1 --model <model-name>
```

The live runner remains bounded by provider-call, token, step, retry, timeout, and wall-clock limits. The LLM never receives the simulator object and never executes actions directly.

## Research rule

The first real run is an **integration validation**, not a research result. Do not include it in A/B/C statistical comparisons unless the experiment manifest records the exact model, configuration, seed, scenario template, provider usage, and result status.
