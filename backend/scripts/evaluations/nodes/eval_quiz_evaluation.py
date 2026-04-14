#!/usr/bin/env python3
"""Standalone evaluation script for the **quiz_evaluation** node.

Runs the LLM-as-judge quiz evaluation call against curated test cases,
measures accuracy and latency, computes p-values, and generates a chart.

Usage:
    python -m backend.scripts.evaluations.nodes.eval_quiz_evaluation [--iterations N]
"""

from __future__ import annotations

import argparse
import asyncio
from typing import Any

from backend.app.prompts import quiz_evaluation as quiz_eval_prompts
from backend.app.services.llm.client import llm_client
from backend.app.services.llm.models import QuizEvaluationResult
from backend.scripts.evaluations.harness import EvalHarness, load_fixture, run_and_close


# ---------------------------------------------------------------------------
# Node function
# ---------------------------------------------------------------------------
async def call_quiz_evaluation(input_data: dict[str, Any]) -> dict[str, Any]:
    """Invoke the quiz_evaluation node and return parsed output."""
    prompt = quiz_eval_prompts.USER_PROMPT_TEMPLATE.format(
        questions_and_answers=input_data["questions_and_answers"],
    )

    raw = await llm_client.chat_completion_json(
        pipeline="quiz_evaluation",
        messages=[
            {"role": "system", "content": quiz_eval_prompts.SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
    )
    result = QuizEvaluationResult.model_validate(raw)
    return result.model_dump()


# ---------------------------------------------------------------------------
# Custom accuracy scorer
# ---------------------------------------------------------------------------
def score_quiz_evaluation(expected: dict, actual: dict) -> float:
    """Score quiz evaluation accuracy.

    Checks:
    1. Correct number of evaluations returned
    2. Correctness ratings match expected (full/partial/incorrect)
    3. Confidence scores meet minimum thresholds
    4. Each evaluation has required fields
    """
    scores: list[float] = []
    evaluations = actual.get("evaluations", [])
    exp_evals = expected.get("evaluations", [])

    # 1. Count check
    min_evals = expected.get("min_evaluations", len(exp_evals))
    if len(evaluations) >= min_evals:
        scores.append(1.0)
    else:
        scores.append(len(evaluations) / min_evals if min_evals else 0.0)

    # 2–3. Per-evaluation matching
    for exp_ev in exp_evals:
        # Find matching evaluation by question_id
        match = None
        for act_ev in evaluations:
            if act_ev.get("question_id") == exp_ev.get("question_id"):
                match = act_ev
                break

        if match is None:
            scores.append(0.0)
            continue

        ev_scores: list[float] = []

        # Correctness match
        if match.get("correctness") == exp_ev.get("correctness"):
            ev_scores.append(1.0)
        else:
            # Partial credit for adjacent ratings
            order = ["full", "partial", "incorrect"]
            try:
                exp_idx = order.index(exp_ev["correctness"])
                act_idx = order.index(match.get("correctness", ""))
                distance = abs(exp_idx - act_idx)
                ev_scores.append(1.0 - distance * 0.5)
            except ValueError:
                ev_scores.append(0.0)

        # Confidence threshold
        conf_min = exp_ev.get("confidence_min", 0.0)
        if match.get("confidence", 0) >= conf_min:
            ev_scores.append(1.0)
        else:
            ev_scores.append(match.get("confidence", 0) / conf_min if conf_min else 0.0)

        # Has explanation
        if match.get("explanation"):
            ev_scores.append(1.0)
        else:
            ev_scores.append(0.0)

        scores.append(sum(ev_scores) / len(ev_scores) if ev_scores else 0.0)

    return sum(scores) / len(scores) if scores else 0.0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate the quiz_evaluation node")
    parser.add_argument(
        "--iterations",
        "-n",
        type=int,
        default=5,
        help="Number of iterations per test case (default: 5)",
    )
    args = parser.parse_args()

    cases = load_fixture("quiz_evaluation")

    harness = EvalHarness(
        node_name="quiz_evaluation",
        cases=cases,
        node_fn=call_quiz_evaluation,
        iterations=args.iterations,
        accuracy_fn=score_quiz_evaluation,
    )

    asyncio.run(run_and_close(harness))


if __name__ == "__main__":
    main()
