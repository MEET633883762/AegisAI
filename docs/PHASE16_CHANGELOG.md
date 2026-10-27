# Phase 16 Changelog — OpenAI Responses Provider

Implementation record for this milestone. Historical verification totals below are preserved; use the [development guide](DEVELOPMENT.md) for Python 3.11 setup and [current status](CURRENT_STATUS.md) for fresh project checks. The public browser walkthrough uses scripted agents and is separate from opt-in provider experiments.

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
  - No adapter-level retry loop; underlying SDK retry settings remain separate.

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
