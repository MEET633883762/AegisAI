# LLM decision services

AegisAI treats LLMs as bounded decision services. The public browser walkthrough and paired defender comparison use scripted agents and need no API key or live model.

## Provider contract

[`provider.py`](provider.py) defines the common request/response and validation boundary. Available adapters are:

- [`FakeLLMProvider`](fake.py): deterministic offline test double.
- [`OpenAIResponsesProvider`](openai_provider.py): OpenAI Responses adapter requesting Pydantic structured output and revalidating it at the application boundary.

The adapter does not execute tools or simulator actions and receives no Simulator or Controller object. Proposals still pass through agent/schema checks and Controller authorization before simulated execution.

## Environment and offline checks

Prepare the Python 3.11 environment from [DEVELOPMENT.md](../docs/DEVELOPMENT.md). The reviewed dependency file pins the OpenAI SDK; installation does not require configuring an API key. On Windows, use `py -3.11` or the explicit virtual-environment interpreter because `.python-version` does not switch `PATH`.

From the repository root after setup:

```powershell
py -3.11 -m pytest -q tests/unit/test_llm_provider.py tests/unit/test_llm_red.py tests/unit/test_llm_openai_provider.py
```

These tests inject offline responses and do not call a provider. See [current status](../docs/CURRENT_STATUS.md) for the fresh full-project verification.

## Separate live integration path

A live adapter needs an explicit model and `OPENAI_API_KEY` supplied through the process environment or constructor. Never commit a key or include it in a report. The [offline preflight](../docs/PHASE18_LIVE_INTEGRATION_VALIDATION.md) checks configuration without contacting OpenAI; [single-episode validation](../docs/PHASE19_LIVE_INTEGRATION_VALIDATION.md) additionally requires explicit `--live` and bounded calls, tokens, steps, timeout, and wall-clock duration.

The AegisAI adapter adds no retry loop of its own. Its underlying SDK client has separate retry behavior, and the current constructor does not override the SDK's `max_retries`. A harness provider-call count therefore must not be described as an exact HTTP-attempt count or an exact spend limit. The agent's bounded retry loop is another distinct layer. A successful single live validation demonstrates integration only, not model efficacy or scientific A/B/C evidence.
