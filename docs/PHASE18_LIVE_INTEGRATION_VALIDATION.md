# Phase 18 — First Live Integration Validation

Implementation record for this milestone. Historical verification totals below are preserved; use the [development guide](DEVELOPMENT.md) for Python 3.11 setup and [current status](CURRENT_STATUS.md) for fresh project checks. The public browser walkthrough uses scripted agents and is separate from opt-in provider experiments.

Phase 18 adds an **offline preflight gate** for the real-LLM path. It does not contact OpenAI and it does not consume API credits.

## Purpose

Before any live experiment, verify that the local machine has:

- a configured `OPENAI_MODEL`
- a configured `OPENAI_API_KEY`
- the OpenAI SDK installed
- a valid `LiveExperimentConfig`

The preflight never prints or returns the API key itself.

## Offline check

```powershell
py -3.11 scripts/live_preflight.py --model "$env:OPENAI_MODEL"
```

These PowerShell examples assume dependencies are installed in Python 3.11 and `OPENAI_MODEL`/`OPENAI_API_KEY` are configured in the process environment. An explicit `.\.venv\Scripts\python.exe` also works after the [development setup](DEVELOPMENT.md); on Linux use `.venv/bin/python` and `"$OPENAI_MODEL"`.

A missing key or model produces a non-zero exit status. No network request is made. Passing this check confirms local configuration only; it does not authenticate the key, contact the model, or verify model access.

## Live episode

Only after the offline preflight succeeds should a user explicitly request one live episode:

```powershell
py -3.11 scripts/run_live_episode.py --live --template web_exploit_lateral_exfil --seed 1 --model "$env:OPENAI_MODEL"
```

The live runner applies the [documented invocation, reported-token, step, retry, timeout, and deadline controls](PHASE17_LIVE_EXPERIMENT_HARNESS.md#limits-and-accounting). Those controls do not preempt an in-flight request or establish a strict spend cap. The LLM never receives the simulator object and never executes actions directly.

## Research rule

The first real run is an **integration validation**, not a research result. Do not include it in A/B/C statistical comparisons unless the experiment manifest records the exact model, configuration, seed, scenario template, provider usage, and result status.
