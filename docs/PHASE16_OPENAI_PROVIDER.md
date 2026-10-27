# Phase 16 — OpenAI Responses Provider

Implementation record for this milestone. Historical verification totals below are preserved; use the [development guide](DEVELOPMENT.md) for Python 3.11 setup and [current status](CURRENT_STATUS.md) for fresh project checks. The public browser walkthrough uses scripted agents and is separate from opt-in provider experiments.

## Purpose

Phase 16 adds a concrete OpenAI Responses API adapter while preserving AegisAI's provider-neutral contract.

The adapter is a **decision service only**. It receives an `LLMRequest`, requests a Pydantic structured output, validates that output again at the application boundary, and returns an `LLMResponse`. It has no simulator, controller, shell, tool, or execution access.

## Design

```text
LLMRedAgent / LLMBlueAgent
          |
          v
    LLMProvider contract
          |
          +---- FakeLLMProvider (offline tests)
          |
          +---- OpenAIResponsesProvider
                    |
                    v
             OpenAI Responses API
                    |
                    v
          Pydantic structured output
                    |
                    v
             Controller gate
```

The AegisAI adapter adds no retry loop. The agent retry count and the underlying SDK client's retry behavior are separate layers: the current `OpenAI(api_key=key)` constructor does not override SDK `max_retries`. A harness provider-call count must not be treated as an exact HTTP-attempt count or strict spend limit.

## Configuration

Required for live use:

```text
OPENAI_API_KEY=<secret>
```

The key must be supplied through the environment or an explicit constructor argument. Do not commit keys to source control.

Configure `OPENAI_API_KEY` in the shell/process environment through your normal secret-management workflow. Select a model explicitly or set `OPENAI_MODEL` for the CLI; avoid putting a real key into documentation, source files, screenshots, or shared command output.

Use a model explicitly when constructing the provider; do not hard-code a research result around one model name.

## Structured output

The adapter uses the OpenAI Python SDK's Responses API `parse(..., text_format=...)` path for Pydantic structured output. The SDK's parsed result is still passed through AegisAI's own Pydantic validation boundary.

## Safety properties

- No direct `Simulator` dependency.
- No direct `Controller` dependency.
- No tools enabled by the adapter.
- No shell/command execution.
- No fallback action on provider failure.
- Bounded request timeout.
- Provider failures become `LLMProviderError`.
- Missing structured output becomes `StructuredOutputError`.
- Agent retry limits bound AegisAI agent attempts; SDK transport retry settings remain separate.

## Offline testing

The Phase 16 provider tests inject a fake Responses client and make no external provider call or API-key requirement. The full project suite also exercises its own loopback HTTP services; that is separate from live-provider access.

From the repository root after Python 3.11 setup:

```powershell
py -3.11 -m pytest -q tests/unit/test_llm_openai_provider.py
```

The OpenAI SDK is imported lazily by the adapter, so the provider layer remains importable for offline tests.
