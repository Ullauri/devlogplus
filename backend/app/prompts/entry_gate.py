"""The yes/no question asked of each journal entry before topic extraction.

Answered by Jev (``services/llm/decisions.py``), which returns P(yes) and no
text. An entry whose P(yes) falls below ``LLM_ENTRY_GATE_THRESHOLD`` is marked
processed without the topic-extraction call.
"""

QUESTION = (
    "Does this developer journal entry describe technical learning, a skill, a "
    "concept, or a problem worth adding to the developer's knowledge profile?"
)
