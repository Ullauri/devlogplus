#!/usr/bin/env python3
"""Standalone evaluation script for the **project_evaluation** node.

Runs the project evaluation LLM call against curated test cases,
measures accuracy and latency, computes p-values, and generates a chart.

Usage:
    python -m backend.scripts.evaluations.nodes.eval_project_evaluation [--iterations N]
"""

from __future__ import annotations

import argparse
import asyncio
from typing import Any

from backend.app.prompts import project_evaluation as proj_eval_prompts
from backend.app.services.llm.client import llm_client
from backend.app.services.llm.models import ProjectEvaluationResult
from backend.scripts.evaluations.harness import EvalHarness, load_fixture, run_and_close


# ---------------------------------------------------------------------------
# Node function
# ---------------------------------------------------------------------------
async def call_project_evaluation(input_data: dict[str, Any]) -> dict[str, Any]:
    """Invoke the project_evaluation node and return parsed output."""
    prompt = proj_eval_prompts.USER_PROMPT_TEMPLATE.format(
        project_description=input_data["project_description"],
        tasks=input_data["tasks"],
        original_code=input_data["original_code"],
        submitted_code=input_data["submitted_code"],
    )

    raw = await llm_client.chat_completion_json(
        pipeline="project_evaluation",
        messages=[
            {"role": "system", "content": proj_eval_prompts.SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
    )
    result = ProjectEvaluationResult.model_validate(raw)
    return result.model_dump()


# ---------------------------------------------------------------------------
# Custom accuracy scorer
# ---------------------------------------------------------------------------
def score_project_evaluation(expected: dict, actual: dict) -> float:
    """Score project evaluation accuracy.

    Checks:
    1. Code quality score within expected range
    2. All tasks evaluated
    3. Difficulty adjustment matches expected direction
    4. Has overall assessment text
    5. Confidence meets minimum threshold
    """
    scores: list[float] = []

    cq = actual.get("code_quality_score", 0.0)

    # 1. Code quality score range
    if "code_quality_score_min" in expected:
        scores.append(1.0 if cq >= expected["code_quality_score_min"] else 0.3)
    if "code_quality_score_max" in expected:
        scores.append(1.0 if cq <= expected["code_quality_score_max"] else 0.3)

    # 2. All tasks evaluated
    task_evals = actual.get("task_evaluations", [])
    if expected.get("all_tasks_evaluated"):
        # Count tasks from the input (rough count by "### Task" headers)
        scores.append(1.0 if len(task_evals) >= 2 else 0.3)
    if expected.get("tasks_incomplete") or expected.get("some_tasks_incomplete"):
        # At least one task should be marked incomplete
        incomplete = [t for t in task_evals if not t.get("completed", True)]
        scores.append(1.0 if incomplete else 0.3)

    # 3. Difficulty adjustment
    actual_adj = actual.get("difficulty_adjustment", 0)
    expected_adj = expected.get("difficulty_adjustment")
    if expected_adj is not None:
        if actual_adj == expected_adj:
            scores.append(1.0)
        elif abs(actual_adj - expected_adj) == 1:
            scores.append(0.5)
        else:
            scores.append(0.0)

    # 4. Has overall assessment
    if expected.get("has_overall_assessment"):
        assessment = actual.get("overall_assessment", "")
        scores.append(1.0 if len(assessment) > 20 else 0.3)

    # 5. Confidence
    conf_min = expected.get("confidence_min", 0.0)
    actual_conf = actual.get("confidence", 0.0)
    if conf_min > 0:
        scores.append(1.0 if actual_conf >= conf_min else actual_conf / conf_min)

    return sum(scores) / len(scores) if scores else 0.0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate the project_evaluation node")
    parser.add_argument(
        "--iterations",
        "-n",
        type=int,
        default=5,
        help="Number of iterations per test case (default: 5)",
    )
    args = parser.parse_args()

    cases = load_fixture("project_evaluation")

    harness = EvalHarness(
        node_name="project_evaluation",
        cases=cases,
        node_fn=call_project_evaluation,
        iterations=args.iterations,
        accuracy_fn=score_project_evaluation,
    )

    asyncio.run(run_and_close(harness))


if __name__ == "__main__":
    main()
