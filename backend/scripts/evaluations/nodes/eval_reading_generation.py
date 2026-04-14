#!/usr/bin/env python3
"""Standalone evaluation script for the **reading_generation** node.

Runs the reading recommendation LLM call against curated test cases,
measures accuracy and latency, computes p-values, and generates a chart.

Usage:
    python -m backend.scripts.evaluations.nodes.eval_reading_generation [--iterations N]
"""

from __future__ import annotations

import argparse
import asyncio
from typing import Any
from urllib.parse import urlparse

from backend.app.prompts import reading_generation
from backend.app.services.llm.client import llm_client
from backend.app.services.llm.models import ReadingGenerationResult
from backend.scripts.evaluations.harness import EvalHarness, load_fixture, run_and_close


# ---------------------------------------------------------------------------
# Node function
# ---------------------------------------------------------------------------
async def call_reading_generation(input_data: dict[str, Any]) -> dict[str, Any]:
    """Invoke the reading_generation node and return parsed output."""
    prompt = reading_generation.USER_PROMPT_TEMPLATE.format(
        profile_summary=input_data["profile_summary"],
        allowlist_domains=input_data["allowlist_domains"],
        feedforward_signals=input_data["feedforward_signals"],
        recommendation_count=input_data["recommendation_count"],
    )

    raw = await llm_client.chat_completion_json(
        pipeline="reading_generation",
        messages=[
            {"role": "system", "content": reading_generation.SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
    )
    result = ReadingGenerationResult.model_validate(raw)
    return result.model_dump()


# ---------------------------------------------------------------------------
# Custom accuracy scorer
# ---------------------------------------------------------------------------
def score_reading_generation(expected: dict, actual: dict) -> float:
    """Score reading generation accuracy.

    Checks:
    1. Recommendation count within expected range
    2. All URLs are from the allowlist domains
    3. Each recommendation has required fields
    4. Recommendation types are valid
    """
    scores: list[float] = []
    recs = actual.get("recommendations", [])
    min_r = expected.get("min_recommendations", 1)
    max_r = expected.get("max_recommendations", 50)
    allowed = set(expected.get("allowed_domains", []))

    # 1. Count
    if min_r <= len(recs) <= max_r:
        scores.append(1.0)
    elif len(recs) < min_r:
        scores.append(len(recs) / min_r)
    else:
        scores.append(max_r / len(recs))

    # 2. Domain allowlist compliance
    if expected.get("all_from_allowlist") and recs and allowed:
        compliant = 0
        for rec in recs:
            url = rec.get("url", "")
            source_domain = rec.get("source_domain", "")
            # Check both the declared source_domain and the actual URL
            url_domain = urlparse(url).netloc.replace("www.", "")
            if source_domain in allowed or url_domain in allowed:
                compliant += 1
            elif any(d in url_domain for d in allowed):
                compliant += 0.5  # subdomain match
        scores.append(compliant / len(recs))
    elif not recs:
        scores.append(0.0)

    # 3. Required fields
    required = expected.get("must_have_fields", [])
    if required and recs:
        field_score = 0.0
        for rec in recs:
            has = sum(1 for f in required if rec.get(f))
            field_score += has / len(required)
        scores.append(field_score / len(recs))

    # 4. Valid recommendation types
    valid_types = {"next_frontier", "weak_spot", "deep_dive"}
    if recs:
        type_score = sum(1.0 for r in recs if r.get("recommendation_type") in valid_types)
        scores.append(type_score / len(recs))

    return sum(scores) / len(scores) if scores else 0.0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate the reading_generation node")
    parser.add_argument(
        "--iterations",
        "-n",
        type=int,
        default=5,
        help="Number of iterations per test case (default: 5)",
    )
    args = parser.parse_args()

    cases = load_fixture("reading_generation")

    harness = EvalHarness(
        node_name="reading_generation",
        cases=cases,
        node_fn=call_reading_generation,
        iterations=args.iterations,
        accuracy_fn=score_reading_generation,
    )

    asyncio.run(run_and_close(harness))


if __name__ == "__main__":
    main()
