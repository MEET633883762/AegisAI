# Phase 19 — First Real LLM Integration Validation

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

Set the environment variables in the shell/session, then run:

```text
python scripts/validate_live_integration.py --live --model <model-name> --template web_exploit_lateral_exfil --seed 1
```

The Phase 19 defaults intentionally use only **4 provider calls, 2,000 total tokens, and 2 episode steps**. Increase them only after the first integration check succeeds.

To save a redacted result artifact:

```text
python scripts/validate_live_integration.py --live --model <model-name> --template web_exploit_lateral_exfil --seed 1 --output results/live_validation.json
```

## Interpreting the result

`integration_ok: true` means the single bounded episode completed and at least one provider call was accounted for.

An aborted or budget-exhausted episode is an integration diagnostic, not evidence that the research hypothesis is false.

The output explicitly marks:

```json
"research_evidence": false
```

## Provider boundary

The OpenAI Python SDK currently supports `client.responses.parse(..., text_format=YourPydanticModel)` for Responses API structured outputs. The application still performs its own Pydantic validation after parsing. See the official SDK examples and parser implementation for the current contract.
