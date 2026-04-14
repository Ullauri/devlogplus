#!/usr/bin/env python3
"""Standalone evaluation script for the **quiz_generation** node.

Runs the quiz generation LLM call against curated test cases, measures
accuracy and latency, computes p-values, and generates a chart.

Usage:
    python -m backend.scripts.evaluations.nodes.eval_quiz_generation [--iterations N]
"""

from __future__ import annotations

import argparse
import asyncio
from typing import Any

from backend.app.prompts import quiz_generation
from backend.app.services.llm.client import llm_client
from backend.app.services.llm.models import QuizGenerationResult
from backend.scripts.evaluations.harness import EvalHarness, load_fixture, run_and_close


# ---------------------------------------------------------------------------
# Node function
# ---------------------------------------------------------------------------
async def call_quiz_generation(input_data: dict[str, Any]) -> dict[str, Any]:
    """Invoke the quiz_generation node and return parsed output."""
    prompt = quiz_generation.USER_PROMPT_TEMPLATE.format(
        profile_summary=input_data["profile_summary"],
        feedforward_signals=input_data["feedforward_signals"],
        question_count=input_data["question_count"],
    )

    raw = await llm_client.chat_completion_json(
        pipeline="quiz_generation",
        messages=[
            {"role": "system", "content": quiz_generation.SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
    )
    result = QuizGenerationResult.model_validate(raw)
    return result.model_dump()


# ---------------------------------------------------------------------------
# Custom accuracy scorer
# ---------------------------------------------------------------------------
def score_quiz_generation(expected: dict, actual: dict) -> float:
    """Score quiz generation accuracy.

    Checks:
    1. Question count within expected range
    2. All questions are free-text (no multiple choice markers)
    3. Questions have required fields
    4. Mix of question types (reinforcement / exploration) when expected
    """
    scores: list[float] = []
    questions = actual.get("questions", [])
    min_q = expected.get("min_questions", 1)
    max_q = expected.get("max_questions", 50)

    # 1. Count
    if min_q <= len(questions) <= max_q:
        scores.append(1.0)
    elif len(questions) < min_q:
        scores.append(len(questions) / min_q)
    else:
        scores.append(max_q / len(questions))

    # 2. All free-text
    if expected.get("all_questions_free_text"):
        mc_markers = {
            "a)",
            "b)",
            "c)",
            "d)",
            "true/false",
            "true or false",
            "(a)",
            "(b)",
            "(c)",
            "(d)",
        }
        free_text_count = 0
        for q in questions:
            text = q.get("question_text", "").lower()
            if not any(m in text for m in mc_markers):
                free_text_count += 1
        scores.append(free_text_count / len(questions) if questions else 0.0)

    # 3. Required fields
    required = expected.get("questions_must_have_fields", [])
    if required and questions:
        field_score = 0.0
        for q in questions:
            has = sum(1 for f in required if q.get(f))
            field_score += has / len(required)
        scores.append(field_score / len(questions))

    # 4. Question type mix
    must_have = expected.get("must_have_types", [])
    if must_have and questions:
        actual_types = {q.get("question_type", "").lower() for q in questions}
        matched = sum(1 for t in must_have if t.lower() in actual_types)
        scores.append(matched / len(must_have))

    return sum(scores) / len(scores) if scores else 0.0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate the quiz_generation node")
    parser.add_argument(
        "--iterations",
        "-n",
        type=int,
        default=5,
        help="Number of iterations per test case (default: 5)",
    )
    args = parser.parse_args()

    cases = load_fixture("quiz_generation")

    harness = EvalHarness(
        node_name="quiz_generation",
        cases=cases,
        node_fn=call_quiz_generation,
        iterations=args.iterations,
        accuracy_fn=score_quiz_generation,
    )

    asyncio.run(run_and_close(harness))


if __name__ == "__main__":
    main()
