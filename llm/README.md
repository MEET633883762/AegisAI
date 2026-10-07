# LLM Layer

AegisAI treats LLMs as bounded decision services rather than executors.

## Providers

- `FakeLLMProvider`: deterministic, offline test double.
- `OpenAIResponsesProvider`: concrete OpenAI Responses API adapter with Pydantic structured output.

The common contract lives in `llm/provider.py`.

## Live provider

Set `OPENAI_API_KEY` in the process environment and construct `OpenAIResponsesProvider` with an explicit model name.

The adapter does not execute tools or simulator actions. Its output must still pass through the normal agent/controller validation and authorization path.
