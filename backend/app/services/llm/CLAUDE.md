# LLM Integration — AI Coding Instructions

## Purpose
Everything related to calling LLMs via OpenRouter and observing those calls via Langfuse.

## Key patterns
- **Model routing**: `config.model_for_pipeline(name)` returns the model string for each pipeline. Models are configured via env vars (`LLM_MODEL_*`), never hardcoded.
- **Structured outputs**: LLM responses are parsed from JSON into Pydantic models in `models.py` using `model_validate_json`.
- **Langfuse grouping**: traces are grouped by pipeline name (profile_update, quiz_gen, quiz_eval, reading_gen, project_gen, project_eval).
- **Error handling**: LLM client raises on non-200 status. Callers (pipelines) should catch and log failures.

## Adding a new LLM call pattern
1. Define the response Pydantic model in `models.py`.
2. Write the prompt constants in `prompts/`.
3. Call `llm_client.chat_completion_json(...)` with `trace_llm_call(...)` wrapping.
