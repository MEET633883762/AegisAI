# Phase 16 Changelog — OpenAI Responses Provider

## Added

- `llm/openai_provider.py`
  - OpenAI Responses API adapter.
  - Pydantic structured-output parsing through `responses.parse(..., text_format=...)`.
  - Application-level Pydantic re-validation.
  - Bounded per-request timeout.
  - Environment-based API-key configuration.
  - Provider errors mapped to AegisAI `LLMProviderError`.
  - Missing parsed output mapped to `StructuredOutputError`.
  - Token usage extraction.
  - No provider-side retries.

- `tests/unit/test_llm_openai_provider.py`
  - Offline fake Responses client.
  - Structured-output contract tests.
  - Missing-output test.
  - Transport-error test.
  - API-key configuration tests.
  - Timeout-bound tests.

- `docs/PHASE16_OPENAI_PROVIDER.md`
- Updated `llm/README.md`.
- Declared `openai>=1.78,<2` in `requirements.txt`.

## Safety boundary

The adapter does not import or receive `Simulator` or `Controller` objects. It only converts an `LLMRequest` into a typed model result. Execution remains outside the provider boundary.

## Verification

```text
190 passed
```

No live OpenAI API call is made by the test suite.
