#!/usr/bin/env python3
"""Standalone evaluation script for the **topic_extraction** node.

Runs the topic-extraction LLM call against curated test cases multiple times,
measures accuracy and latency, computes p-values, and generates a chart.

Usage:
    python -m backend.scripts.evaluations.nodes.eval_topic_extraction [--iterations N]
"""

from __future__ import annotations

import argparse
import asyncio
from typing import Any

# ── project imports ──────────────────────────────────────────────────────────
from backend.app.prompts import topic_extraction
from backend.app.services.llm.client import llm_client
from backend.app.services.llm.models import TopicExtractionResult
from backend.scripts.evaluations.harness import EvalHarness, load_fixture, run_and_close


# ---------------------------------------------------------------------------
# Node function — a thin wrapper around the real LLM call
# ---------------------------------------------------------------------------
async def call_topic_extraction(input_data: dict[str, Any]) -> dict[str, Any]:
    """Invoke the topic_extraction node and return parsed output."""
    prompt = topic_extraction.USER_PROMPT_TEMPLATE.format(
        content=input_data["content"],
        existing_topics=input_data["existing_topics"],
    )

    raw = await llm_client.chat_completion_json(
        pipeline="topic_extraction",
        messages=[
            {"role": "system", "content": topic_extraction.SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
    )
    # Validate through Pydantic
    result = TopicExtractionResult.model_validate(raw)
    return result.model_dump()


# ---------------------------------------------------------------------------
# Custom accuracy scorer — domain-specific checks
# ---------------------------------------------------------------------------
def score_topic_extraction(expected: dict, actual: dict) -> float:
    """Score topic extraction accuracy against expectations.

    Checks:
    1. Topic count within expected range (min_topics / max_topics)
    2. Expected topics are present (name fuzzy match)
    3. Categories roughly match expected values
    4. Confidence values meet minimum thresholds
    """
    scores: list[float] = []
    topics = actual.get("topics", [])
    exp_topics = expected.get("topics", [])
    min_t = expected.get("min_topics", 1)
    max_t = expected.get("max_topics", 20)

    # 1. Count within range
    if min_t <= len(topics) <= max_t:
        scores.append(1.0)
    elif len(topics) < min_t:
        scores.append(len(topics) / min_t)
    else:
        scores.append(max_t / len(topics))

    # 2–4. Per-expected-topic matching
    for exp in exp_topics:
        exp_name_lower = exp["name"].lower()
        # Find best match by name overlap
        best_score = 0.0
        for act_topic in topics:
            act_name_lower = act_topic.get("name", "").lower()
            # Check name similarity (word overlap)
            exp_words = set(exp_name_lower.split())
            act_words = set(act_name_lower.split())
            name_sim = (
                len(exp_words & act_words) / len(exp_words | act_words)
                if (exp_words | act_words)
                else 0.0
            )
            if name_sim < 0.2:
                continue

            topic_score = name_sim  # base

            # Category match
            if act_topic.get("category") == exp.get("category"):
                topic_score = (topic_score + 1.0) / 2
            else:
                topic_score = (topic_score + 0.3) / 2

            # Evidence strength match
            if act_topic.get("evidence_strength") == exp.get("evidence_strength"):
                topic_score = (topic_score + 1.0) / 2
            else:
                topic_score = (topic_score + 0.3) / 2

            # Confidence threshold
            conf_min = exp.get("confidence_min", 0.0)
            if act_topic.get("confidence", 0) >= conf_min:
                topic_score = (topic_score + 1.0) / 2
            else:
                topic_score = (topic_score + 0.4) / 2

            best_score = max(best_score, topic_score)

        scores.append(best_score)

    return sum(scores) / len(scores) if scores else 0.0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate the topic_extraction node")
    parser.add_argument(
        "--iterations",
        "-n",
        type=int,
        default=5,
        help="Number of iterations per test case (default: 5)",
    )
    args = parser.parse_args()

    cases = load_fixture("topic_extraction")

    harness = EvalHarness(
        node_name="topic_extraction",
        cases=cases,
        node_fn=call_topic_extraction,
        iterations=args.iterations,
        accuracy_fn=score_topic_extraction,
    )

    asyncio.run(run_and_close(harness))


if __name__ == "__main__":
    main()
