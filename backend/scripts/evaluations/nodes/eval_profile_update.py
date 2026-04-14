#!/usr/bin/env python3
"""Standalone evaluation script for the **profile_update** node.

Runs the profile reconciliation LLM call against curated test cases,
measures accuracy and latency, computes p-values, and generates a chart.

Usage:
    python -m backend.scripts.evaluations.nodes.eval_profile_update [--iterations N]
"""

from __future__ import annotations

import argparse
import asyncio
from typing import Any

from backend.app.prompts import profile_update as profile_update_prompts
from backend.app.services.llm.client import llm_client
from backend.scripts.evaluations.harness import EvalHarness, load_fixture, run_and_close


# ---------------------------------------------------------------------------
# Node function
# ---------------------------------------------------------------------------
async def call_profile_update(input_data: dict[str, Any]) -> dict[str, Any]:
    """Invoke the profile_update node and return parsed output."""
    prompt = profile_update_prompts.USER_PROMPT_TEMPLATE.format(
        current_profile=input_data["current_profile"],
        new_topics=input_data["new_topics"],
        quiz_results=input_data["quiz_results"],
        feedback_signals=input_data["feedback_signals"],
    )

    raw = await llm_client.chat_completion_json(
        pipeline="profile_update",
        messages=[
            {"role": "system", "content": profile_update_prompts.SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
    )
    return raw  # free-form JSON from this node


# ---------------------------------------------------------------------------
# Custom accuracy scorer
# ---------------------------------------------------------------------------
def score_profile_update(expected: dict, actual: dict) -> float:
    """Score profile update accuracy.

    Checks:
    1. The target topic appears in the updated output
    2. Direction of change matches (strengthen / weaken / add)
    3. Triage items created when expected
    4. Number of updated topics meets minimum
    """
    scores: list[float] = []

    # Flatten all actual topics from various possible output keys
    actual_text = _flatten_to_text(actual).lower()

    # 1. Target topic present
    target = expected.get("should_contain_updated_topic", "").lower()
    if target and target in actual_text:
        scores.append(1.0)
    elif target:
        # Partial word match
        target_words = set(target.split())
        overlap = sum(1 for w in target_words if w in actual_text)
        scores.append(overlap / len(target_words))
    else:
        scores.append(1.0)

    # 2. Direction of change
    direction = expected.get("expected_direction", "")
    if direction == "strengthen":
        # Look for signals of strengthening
        strength_words = {"strong", "strengthen", "demonstrated", "improved", "upgraded"}
        if any(w in actual_text for w in strength_words):
            scores.append(1.0)
        else:
            scores.append(0.3)
    elif direction == "weaken_or_triage":
        weakness_words = {"weak", "triage", "contradict", "conflict", "attention", "downgrade"}
        if any(w in actual_text for w in weakness_words):
            scores.append(1.0)
        else:
            scores.append(0.3)
    elif direction == "add_new":
        new_words = {"new", "added", "created", "discovered"}
        if any(w in actual_text for w in new_words):
            scores.append(1.0)
        else:
            scores.append(0.3)
    else:
        scores.append(0.5)

    # 3. Triage items
    triage_items = actual.get("triage_items", [])
    if expected.get("min_triage_items"):
        if len(triage_items) >= expected["min_triage_items"]:
            scores.append(1.0)
        else:
            scores.append(0.0)
    elif expected.get("should_not_flag_triage"):
        scores.append(1.0 if len(triage_items) == 0 else 0.5)

    # 4. Minimum updated topics
    updated = actual.get("updated_topics", [])
    min_updates = expected.get("min_updated_topics", 0)
    if min_updates > 0:
        if len(updated) >= min_updates:
            scores.append(1.0)
        else:
            scores.append(len(updated) / min_updates if min_updates else 0.0)

    return sum(scores) / len(scores) if scores else 0.0


def _flatten_to_text(d: Any, depth: int = 0) -> str:
    """Recursively flatten a dict/list to a text blob for searching."""
    if depth > 10:
        return ""
    if isinstance(d, dict):
        return " ".join(_flatten_to_text(v, depth + 1) for v in d.values())
    if isinstance(d, list):
        return " ".join(_flatten_to_text(v, depth + 1) for v in d)
    return str(d)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate the profile_update node")
    parser.add_argument(
        "--iterations",
        "-n",
        type=int,
        default=5,
        help="Number of iterations per test case (default: 5)",
    )
    args = parser.parse_args()

    cases = load_fixture("profile_update")

    harness = EvalHarness(
        node_name="profile_update",
        cases=cases,
        node_fn=call_profile_update,
        iterations=args.iterations,
        accuracy_fn=score_profile_update,
    )

    asyncio.run(run_and_close(harness))


if __name__ == "__main__":
    main()
