# Phase 16 — OpenAI Responses Provider

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

The current agent retry loop remains the retry boundary. The OpenAI adapter deliberately performs **no internal retries**, preventing accidental multiplicative retries and uncontrolled API traffic.

## Configuration

Required for live use:

```text
OPENAI_API_KEY=<secret>
```

The key must be supplied through the environment or an explicit constructor argument. Do not commit keys to source control.

Example environment setup on Windows CMD:

```bat
set OPENAI_API_KEY=YOUR_KEY_HERE
```

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
- Existing agent retry limits remain authoritative.

## Offline testing

The Phase 16 test suite injects a fake Responses client. Therefore the full test suite does not require an API key and makes no network calls.

The OpenAI SDK is imported lazily by the adapter, so the provider layer remains importable for offline tests.
