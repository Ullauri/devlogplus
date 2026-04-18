# Prompts — AI Coding Instructions

## Purpose
Version-controlled LLM prompt constants.  All prompt text lives here, **never** inline in services or pipelines.

## Convention
Each file exports two constants:
- `SYSTEM_PROMPT: str` — sets the LLM's role/persona.
- `USER_PROMPT_TEMPLATE: str` — a Python `.format()` template with `{placeholder}` variables.

## Guidelines
- Keep prompts precise and well-structured.
- Include explicit output format instructions (JSON schema) in each prompt.
- Confidence scoring must be requested where applicable.
- When modifying a prompt, test against controlled scenarios.
- Templates use `.format(**kwargs)` — not f-strings. Variables are `{placeholder}` style; any literal braces in JSON examples must be escaped as `{{` / `}}`.
