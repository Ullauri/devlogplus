# ADR 0002 — OpenRouter as LLM Gateway

**Date:** 2026-04-19  
**Status:** Accepted

## Context

The application uses LLMs for multiple distinct pipelines (topic extraction,
profile update, quiz generation, quiz evaluation, reading recommendations, project
generation, project evaluation). Each pipeline may benefit from a different
model — e.g. a cheaper/faster model for extraction vs a more capable one for
evaluation.

Options considered:
1. Call provider APIs directly (Anthropic, OpenAI, etc.) per pipeline.
2. Use a single gateway that normalises the API surface across providers.

## Decision

Use **OpenRouter** (`https://openrouter.ai/api/v1`) as the single LLM gateway.
Each pipeline has its own model configured independently via an env var
(e.g. `LLM_MODEL_TOPIC_EXTRACTION`, `LLM_MODEL_QUIZ_EVALUATION`), all pointing at
OpenRouter.

## Consequences

- **+** Single API key and base URL to manage regardless of which provider/model
  is in use.
- **+** Model swaps require only a `.env` change — no code change needed.
- **+** Easy to route different pipelines to different cost/quality tiers.
- **+** Provider failover and routing logic is delegated to OpenRouter.
- **−** Adds a third-party dependency in the critical path; OpenRouter outages
  affect all pipelines simultaneously.
- **−** OpenRouter has a markup over direct provider pricing.
- **−** Some provider-specific features (fine-tuning, function-call schemas) may
  not be fully exposed through the gateway.
