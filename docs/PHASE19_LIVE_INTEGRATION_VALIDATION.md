# Phase 19 — First Real LLM Integration Validation

Implementation record for this milestone. Historical verification totals below are preserved; use the [development guide](DEVELOPMENT.md) for Python 3.11 setup and [current status](CURRENT_STATUS.md) for fresh project checks. The public browser walkthrough uses scripted agents and is separate from opt-in provider experiments.

Phase 19 provides a fail-closed command for **one** tightly bounded live LLM episode.

## Purpose

This phase answers one engineering question:

> Can the configured real provider produce schema-valid Red/Blue decisions that travel through the existing Controller and deterministic simulator under hard limits?

This is **not** a research experiment and must not be included in A/B/C statistical results.

## Safety gates

The command requires all of the following:

- explicit `--live`
- valid Phase 18 preflight
- configured model
- configured API key
- bounded provider calls
- bounded total tokens
- bounded episode steps
- bounded request timeout
- bounded wall-clock time

The API key is never printed or written to the result artifact.

## Recommended first run

Prepare the Python 3.11 environment in [DEVELOPMENT.md](DEVELOPMENT.md), configure `OPENAI_MODEL` and `OPENAI_API_KEY` in the process environment, then run from the repository root in PowerShell. This command makes a real provider call only with explicit `--live`:

```powershell
py -3.11 scripts/validate_live_integration.py --live --model "$env:OPENAI_MODEL" --template web_exploit_lateral_exfil --seed 1
```

The Phase 19 defaults are **4 AegisAI provider invocations, 2,000 reported aggregate tokens, 2 episode steps, a 30-second request timeout, and a 120-second wall-clock budget**. The token threshold is checked after each returned response; the deadline does not interrupt an in-flight SDK request, and SDK transport retries are separate. These are not strict HTTP-attempt or spend caps; see [limits and accounting](PHASE17_LIVE_EXPERIMENT_HARNESS.md#limits-and-accounting).

Use `.\.venv\Scripts\python.exe` instead of `py -3.11` for the prepared Windows virtual environment. On Linux, use `.venv/bin/python` and `"$OPENAI_MODEL"`.

To save a redacted result artifact:

```powershell
py -3.11 scripts/validate_live_integration.py --live --model "$env:OPENAI_MODEL" --template web_exploit_lateral_exfil --seed 1 --output .aegisai-local/live-validation/first-run.json
```

The CLI creates the parent directory and overwrites the chosen output file if it exists. Choose a new path when preserving earlier results. The JSON excludes the API-key configuration and is labeled as integration evidence, not a research comparison.

## Interpreting the result

`integration_ok: true` means the single bounded episode completed and at least one provider call was accounted for.

An aborted or budget-exhausted episode is an integration diagnostic, not evidence that the research hypothesis is false.

The output explicitly marks:

```json
"research_evidence": false
```

## Provider boundary

The checked-in adapter uses `client.responses.parse(..., text_format=YourPydanticModel)` with the reviewed SDK dependency. The application performs its own Pydantic validation after parsing. The wrapper adds no retry loop, but the constructor does not override the underlying SDK retry configuration. See [the local adapter](../llm/openai_provider.py) and [provider guide](../llm/README.md) for the implemented boundary.
