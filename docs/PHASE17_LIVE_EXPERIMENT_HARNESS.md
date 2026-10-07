# Phase 17 — Controlled Live LLM Experiment Harness

Phase 17 adds a bounded execution harness for testing real provider-backed Red/Blue agents against the deterministic AegisAI simulator.

## Safety boundary

The live harness does **not** give an LLM access to the simulator, Controller internals, shell, filesystem, or network execution. Agents still produce typed `RedAction`/`BlueAction` objects; the Controller remains the sole execution and authorization boundary.

## Hard limits

Each episode has explicit bounds for:

- maximum simulator steps (at most 30)
- maximum provider calls
- maximum aggregate provider tokens
- provider request timeout (configured by the OpenAI adapter)
- maximum wall-clock episode duration
- bounded agent retries

Budget exhaustion or provider failure aborts the episode and records a structured status rather than silently fabricating an action.

## Research accounting

The harness records provider calls and token counters returned by the provider. It intentionally does not invent dollar costs because pricing is model/provider/version dependent; cost conversion can be added later from a pinned pricing manifest.

## Live API use

A live run requires `OPENAI_API_KEY`. Tests never require a key and use local test doubles. Do not commit keys to the repository.

## Explicit live command

From the project root, the command below is intentionally blocked unless `--live` is supplied:

```text
python scripts/run_live_episode.py --live --template web_exploit_lateral_exfil --seed 1
```

The API key must already be present in `OPENAI_API_KEY`. The script runs one episode only and prints structured status, metrics, and provider usage.

## Explicit live command

From the project root, the command below is intentionally blocked unless `--live` is supplied:

```text
python scripts/run_live_episode.py --live --template web_exploit_lateral_exfil --seed 1
```

The API key must already be present in `OPENAI_API_KEY`. The script runs one episode only and prints structured status, metrics, and provider usage.
