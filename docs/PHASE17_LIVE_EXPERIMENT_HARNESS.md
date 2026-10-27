# Phase 17 — Controlled Live LLM Experiment Harness

Implementation record for this milestone. Use the [development guide](DEVELOPMENT.md) for Python 3.11 setup and [current status](CURRENT_STATUS.md) for fresh project checks. The public browser walkthrough uses scripted agents and is separate from opt-in provider experiments.

This harness runs provider-backed Red/Blue decision agents against the deterministic simulator. Agents return typed proposals; the Controller retains execution and authorization. They receive no simulator, Controller internals, shell, filesystem, or direct network execution capability.

## Limits and accounting

The configuration bounds simulator steps (at most 30), AegisAI provider invocations, agent retries, request timeout, reported aggregate tokens, and a wall-clock deadline. Budget exhaustion or provider failure records a structured aborted result rather than inventing an action.

These limits have practical boundaries. Call count is enforced before each provider invocation. Token usage is checked after the response, using counters supplied by the provider; a response that crosses the threshold has already consumed tokens and is rejected before further use. The deadline is checked before calls and simulator turns and does not interrupt an in-flight synchronous SDK request. The SDK's own retry behavior is separate from both the AegisAI agent retry loop and the harness call counter. These mechanisms are not an exact HTTP-attempt count, dollar-cost cap, or preemptive process-duration limit.

The harness records provider-reported usage and does not invent prices. The current CLI defaults are 40 provider invocations, 20,000 reported tokens, 30 episode steps, a 30-second request timeout, and a 300-second wall-clock budget. For the tighter first integration check, use the [Phase 19 command](PHASE19_LIVE_INTEGRATION_VALIDATION.md) instead.

## Opt-in command

After installing the Python 3.11 dependencies, configure `OPENAI_MODEL` and `OPENAI_API_KEY` in the process environment. Do not commit or publish the key. From the repository root in PowerShell:

```powershell
py -3.11 scripts/live_preflight.py --model "$env:OPENAI_MODEL"
```

This preflight is offline. Only when explicitly choosing to make a real provider call, run:

```powershell
py -3.11 scripts/run_live_episode.py --live --model "$env:OPENAI_MODEL" --template web_exploit_lateral_exfil --seed 1
```

Without `--live`, the runner refuses provider calls. On Linux after setup, replace `py -3.11` with `.venv/bin/python` and use `"$OPENAI_MODEL"` for the model argument. The runner prints one episode's structured status, metrics, and accounted usage; it does not write a report file itself.

Offline tests use local test doubles. A real single episode demonstrates integration only; claims about A/B/C adaptation or generalization need the separately defined experiment protocol, provenance, repeated runs, and limits described in the [research guide](../evaluation/experiments/README.md).
