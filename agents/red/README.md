# Red agents

The simulator provides scripted policies in [`scripted.py`](scripted.py) and the provider-backed `LLMRedAgent` in [`llm.py`](llm.py). The public browser walkthrough and the paired defender benchmark use scripted agents; they do not call an AI model.

## Decision boundary

`LLMRedAgent` receives a `RedObservation`, serializes that role-visible observation into provider context, requests one structured `RedAction`, and returns the validated proposal. It has no Simulator or Controller reference and does not execute actions. The Controller still validates structure, role permissions, turn order, and rate limits before the simulator applies a move.

Temperature, output-token count, and agent retry count are bounded by the constructor. A provider failure is raised after the allowed attempts; it is not converted into an invented executable fallback. The deterministic `FakeLLMProvider` supports offline tests without a key or external service.

## Setup and verification

Use the Python 3.11 environment in the [development guide](../../docs/DEVELOPMENT.md). On Windows, `.python-version` records the reviewed interpreter but does not change an existing `python` command or `PATH`.

From the repository root after installing dependencies:

```powershell
py -3.11 -m pytest -q tests/unit/test_llm_red.py tests/unit/test_llm_provider.py
```

For the separate opt-in provider path, see the [LLM layer](../../llm/README.md) and [bounded integration guide](../../docs/PHASE19_LIVE_INTEGRATION_VALIDATION.md). See [current status](../../docs/CURRENT_STATUS.md) for fresh project verification; the Phase 8 label describes this agent's implementation history.
