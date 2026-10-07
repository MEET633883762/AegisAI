# LLM Red Agent — Phase 8

`LLMRedAgent` is the first LLM-facing agent in AegisAI. It is deliberately thin:

1. receive `RedObservation`;
2. serialize only that observation into bounded provider context;
3. request one structured `RedAction`;
4. return the validated action to the caller.

The agent has no Simulator or Controller reference and does not execute actions. The Controller
must still validate and authorize the returned action before the simulator changes state.

Phase 8 uses the offline `FakeLLMProvider` for reproducible tests. No API key or external service
is required.
