#!/usr/bin/env python3
"""Standalone evaluation script for the **project_generation** node.

Runs the Go project generation LLM call against curated test cases,
measures accuracy and latency, computes p-values, and generates a chart.

Usage:
    python -m backend.scripts.evaluations.nodes.eval_project_generation [--iterations N]
"""

from __future__ import annotations

import argparse
import asyncio
from typing import Any

from backend.app.prompts import project_generation
from backend.app.services.llm.client import llm_client
from backend.app.services.llm.models import ProjectGenerationResult
from backend.scripts.evaluations.harness import EvalHarness, load_fixture, run_and_close


# ---------------------------------------------------------------------------
# Node function
# ---------------------------------------------------------------------------
async def call_project_generation(input_data: dict[str, Any]) -> dict[str, Any]:
    """Invoke the project_generation node and return parsed output."""
    prompt = project_generation.USER_PROMPT_TEMPLATE.format(
        difficulty_level=input_data["difficulty_level"],
        go_experience=input_data["go_experience"],
        profile_summary=input_data["profile_summary"],
        feedforward_signals=input_data["feedforward_signals"],
        previous_themes=input_data["previous_themes"],
    )

    raw = await llm_client.chat_completion_json(
        pipeline="project_generation",
        messages=[
            {"role": "system", "content": project_generation.SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        max_tokens=16384,
    )
    result = ProjectGenerationResult.model_validate(raw)
    return result.model_dump()


# ---------------------------------------------------------------------------
# Custom accuracy scorer
# ---------------------------------------------------------------------------
def score_project_generation(expected: dict, actual: dict) -> float:
    """Score project generation accuracy.

    Checks:
    1. Has title, description, readme
    2. File count meets minimum
    3. Task count within range
    4. Difficulty level within expected range
    5. Contains Go source files and test files
    """
    scores: list[float] = []
    files = actual.get("files", [])
    tasks = actual.get("tasks", [])

    # 1. Required fields
    for field in ["title", "description", "readme_content"]:
        if expected.get(f"has_{field.split('_')[0]}", False):
            scores.append(1.0 if actual.get(field) else 0.0)

    # 2. File count
    min_files = expected.get("min_files", 1)
    if len(files) >= min_files:
        scores.append(1.0)
    else:
        scores.append(len(files) / min_files if min_files else 0.0)

    # 3. Task count
    min_tasks = expected.get("min_tasks", 1)
    max_tasks = expected.get("max_tasks", 20)
    if min_tasks <= len(tasks) <= max_tasks:
        scores.append(1.0)
    elif len(tasks) < min_tasks:
        scores.append(len(tasks) / min_tasks)
    else:
        scores.append(max_tasks / len(tasks))

    # 4. Difficulty range
    diff_range = expected.get("difficulty_level_range", [1, 10])
    actual_diff = actual.get("difficulty_level", 5)
    if diff_range[0] <= actual_diff <= diff_range[1]:
        scores.append(1.0)
    else:
        scores.append(0.3)

    # 5. Go files present
    if expected.get("files_contain_go"):
        go_files = [f for f in files if f.get("path", "").endswith(".go")]
        scores.append(1.0 if go_files else 0.0)

    # 6. Test file present
    if expected.get("has_test_file"):
        test_files = [f for f in files if "_test.go" in f.get("path", "")]
        scores.append(1.0 if test_files else 0.0)

    return sum(scores) / len(scores) if scores else 0.0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate the project_generation node")
    parser.add_argument(
        "--iterations",
        "-n",
        type=int,
        default=5,
        help="Number of iterations per test case (default: 5)",
    )
    args = parser.parse_args()

    cases = load_fixture("project_generation")

    harness = EvalHarness(
        node_name="project_generation",
        cases=cases,
        node_fn=call_project_generation,
        iterations=args.iterations,
        accuracy_fn=score_project_generation,
    )

    asyncio.run(run_and_close(harness))


if __name__ == "__main__":
    main()
