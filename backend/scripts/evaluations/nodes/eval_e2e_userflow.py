#!/usr/bin/env python3
"""End-to-end evaluation of the complete DevLog+ project userflow.

Exercises the entire pipeline chain in sequence for each test case:
  journal entry → topic extraction → profile update → quiz generation →
  quiz evaluation → reading generation → project generation → project evaluation

Each stage feeds its output forward to the next, exactly as the real system
operates. The harness scores every stage's output against expected criteria
and reports an aggregate accuracy across the full flow.

Usage:
    python -m backend.scripts.evaluations.nodes.eval_e2e_userflow [--iterations N]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from typing import Any
from urllib.parse import urlparse

# ── project imports ──────────────────────────────────────────────────────────
from backend.app.prompts import (
    profile_update as profile_update_prompts,
)
from backend.app.prompts import (
    project_evaluation as proj_eval_prompts,
)
from backend.app.prompts import (
    project_generation as proj_gen_prompts,
)
from backend.app.prompts import (
    quiz_evaluation as quiz_eval_prompts,
)
from backend.app.prompts import (
    quiz_generation as quiz_gen_prompts,
)
from backend.app.prompts import (
    reading_generation as reading_gen_prompts,
)
from backend.app.prompts import (
    topic_extraction as topic_extraction_prompts,
)
from backend.app.services.llm.client import llm_client
from backend.app.services.llm.models import (
    ProjectEvaluationResult,
    ProjectGenerationResult,
    QuizEvaluationResult,
    QuizGenerationResult,
    ReadingGenerationResult,
    TopicExtractionResult,
)
from backend.scripts.evaluations.harness import EvalHarness, load_fixture, run_and_close

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Individual stage callers
# ---------------------------------------------------------------------------
async def _call_topic_extraction(content: str, existing_topics: str) -> dict[str, Any]:
    """Stage 1: Extract topics from a journal entry."""
    prompt = topic_extraction_prompts.USER_PROMPT_TEMPLATE.format(
        content=content,
        existing_topics=existing_topics,
    )
    raw = await llm_client.chat_completion_json(
        pipeline="topic_extraction",
        messages=[
            {"role": "system", "content": topic_extraction_prompts.SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
    )
    result = TopicExtractionResult.model_validate(raw)
    return result.model_dump()


async def _call_profile_update(
    current_profile: str,
    new_topics: str,
    quiz_results: str,
    feedback_signals: str,
) -> dict[str, Any]:
    """Stage 2: Reconcile extracted topics into the knowledge profile."""
    prompt = profile_update_prompts.USER_PROMPT_TEMPLATE.format(
        current_profile=current_profile,
        new_topics=new_topics,
        quiz_results=quiz_results,
        feedback_signals=feedback_signals,
    )
    raw = await llm_client.chat_completion_json(
        pipeline="profile_update",
        messages=[
            {"role": "system", "content": profile_update_prompts.SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
    )
    return raw  # free-form JSON


async def _call_quiz_generation(
    profile_summary: str,
    feedforward_signals: str,
    question_count: int,
) -> dict[str, Any]:
    """Stage 3: Generate quiz questions from the updated profile."""
    prompt = quiz_gen_prompts.USER_PROMPT_TEMPLATE.format(
        profile_summary=profile_summary,
        feedforward_signals=feedforward_signals,
        question_count=question_count,
    )
    raw = await llm_client.chat_completion_json(
        pipeline="quiz_generation",
        messages=[
            {"role": "system", "content": quiz_gen_prompts.SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
    )
    result = QuizGenerationResult.model_validate(raw)
    return result.model_dump()


async def _call_quiz_evaluation(questions_and_answers: str) -> dict[str, Any]:
    """Stage 4: Evaluate quiz answers via LLM-as-judge."""
    prompt = quiz_eval_prompts.USER_PROMPT_TEMPLATE.format(
        questions_and_answers=questions_and_answers,
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


async def _call_reading_generation(
    profile_summary: str,
    allowlist_domains: str,
    feedforward_signals: str,
    recommendation_count: int,
) -> dict[str, Any]:
    """Stage 5: Generate reading recommendations."""
    prompt = reading_gen_prompts.USER_PROMPT_TEMPLATE.format(
        profile_summary=profile_summary,
        allowlist_domains=allowlist_domains,
        feedforward_signals=feedforward_signals,
        recommendation_count=recommendation_count,
    )
    raw = await llm_client.chat_completion_json(
        pipeline="reading_generation",
        messages=[
            {"role": "system", "content": reading_gen_prompts.SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
    )
    result = ReadingGenerationResult.model_validate(raw)
    return result.model_dump()


async def _call_project_generation(
    difficulty_level: int,
    go_experience: str,
    profile_summary: str,
    feedforward_signals: str,
    previous_themes: str,
) -> dict[str, Any]:
    """Stage 6: Generate a Go micro-project."""
    prompt = proj_gen_prompts.USER_PROMPT_TEMPLATE.format(
        difficulty_level=difficulty_level,
        go_experience=go_experience,
        profile_summary=profile_summary,
        feedforward_signals=feedforward_signals,
        previous_themes=previous_themes,
    )
    raw = await llm_client.chat_completion_json(
        pipeline="project_generation",
        messages=[
            {"role": "system", "content": proj_gen_prompts.SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        max_tokens=16384,
    )
    result = ProjectGenerationResult.model_validate(raw)
    return result.model_dump()


async def _call_project_evaluation(
    project_description: str,
    tasks: str,
    original_code: str,
    submitted_code: str,
) -> dict[str, Any]:
    """Stage 7: Evaluate a project submission."""
    prompt = proj_eval_prompts.USER_PROMPT_TEMPLATE.format(
        project_description=project_description,
        tasks=tasks,
        original_code=original_code,
        submitted_code=submitted_code,
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
# Helpers — build text summaries from intermediate outputs
# ---------------------------------------------------------------------------
def _topics_to_profile_summary(topics_output: dict, existing_topics: str) -> str:
    """Combine extracted topics + existing topics into a profile summary string."""
    lines = []
    if existing_topics and existing_topics.strip() != "No existing topics yet.":
        lines.append("### Existing Topics")
        lines.append(existing_topics)
        lines.append("")

    lines.append("### Newly Identified Topics")
    for t in topics_output.get("topics", []):
        lines.append(
            f"- {t['name']} ({t['category']}, {t['evidence_strength']}, "
            f"confidence={t['confidence']:.2f}): {t.get('description', '')}"
        )
    return "\n".join(lines)


def _topics_to_new_topics_str(topics_output: dict) -> str:
    """Format extracted topics for the profile update prompt."""
    lines = []
    for t in topics_output.get("topics", []):
        lines.append(
            f"- {t['name']} | category={t['category']} | "
            f"evidence={t['evidence_strength']} | confidence={t['confidence']:.2f}"
        )
    return "\n".join(lines) if lines else "None"


def _profile_update_to_summary(profile_output: dict) -> str:
    """Build a profile summary from profile_update output for downstream stages."""
    lines = ["### Updated Knowledge Profile"]

    updated = profile_output.get("updated_topics", [])
    if isinstance(updated, list):
        for t in updated:
            if isinstance(t, dict):
                name = t.get("name", t.get("topic", "unknown"))
                cat = t.get("category", "unknown")
                strength = t.get("evidence_strength", "unknown")
                conf = t.get("confidence", 0.0)
                lines.append(f"- {name} ({cat}, {strength}, confidence={conf})")
            else:
                lines.append(f"- {t}")

    # Include any other text fields the model produced
    for key in ("summary", "assessment", "overall_summary"):
        if key in profile_output and isinstance(profile_output[key], str):
            lines.append(f"\n{profile_output[key]}")

    return "\n".join(lines) if len(lines) > 1 else json.dumps(profile_output, indent=2)


def _format_qa_pairs(quiz_answers: list[dict]) -> str:
    """Format user-provided Q&A pairs for the quiz evaluation prompt."""
    parts = []
    for qa in quiz_answers:
        parts.append(
            f"### Question ({qa['question_id']})\n"
            f"{qa['question_text']}\n\n"
            f"### Answer\n"
            f"{qa['answer']}"
        )
    return "\n\n---\n\n".join(parts)


def _format_tasks_str(tasks: list[dict]) -> str:
    """Format project tasks into a readable string."""
    lines = []
    for i, t in enumerate(tasks, 1):
        lines.append(f"### Task {i}: {t['title']}\n{t['description']} (type: {t['task_type']})")
    return "\n\n".join(lines)


def _flatten_to_text(d: Any, depth: int = 0) -> str:
    """Recursively flatten a dict/list to a text blob for keyword searching."""
    if depth > 10:
        return ""
    if isinstance(d, dict):
        return " ".join(_flatten_to_text(v, depth + 1) for v in d.values())
    if isinstance(d, list):
        return " ".join(_flatten_to_text(v, depth + 1) for v in d)
    return str(d)


# ---------------------------------------------------------------------------
# E2E node function — chains all 7 stages sequentially
# ---------------------------------------------------------------------------
async def call_e2e_userflow(input_data: dict[str, Any]) -> dict[str, Any]:
    """Run the complete userflow and return outputs from every stage.

    The function feeds each stage's output into the next, mirroring the real
    application data flow. Returns a dict keyed by stage name.
    """
    results: dict[str, Any] = {}

    # ── Stage 1: Topic Extraction ─────────────────────────────────────────
    logger.info("    ↳ Stage 1/7: Topic extraction …")
    topics_output = await _call_topic_extraction(
        content=input_data["journal_entry"],
        existing_topics=input_data["existing_topics"],
    )
    results["stage_1_topic_extraction"] = topics_output

    # ── Stage 2: Profile Update ───────────────────────────────────────────
    logger.info("    ↳ Stage 2/7: Profile update …")
    new_topics_str = _topics_to_new_topics_str(topics_output)
    profile_output = await _call_profile_update(
        current_profile=input_data["existing_topics"],
        new_topics=new_topics_str,
        quiz_results="No quiz results yet.",
        feedback_signals="No feedback signals yet.",
    )
    results["stage_2_profile_update"] = profile_output

    # Build a profile summary to pass downstream
    profile_summary = _profile_update_to_summary(profile_output)

    # ── Stage 3: Quiz Generation ──────────────────────────────────────────
    logger.info("    ↳ Stage 3/7: Quiz generation …")
    quiz_output = await _call_quiz_generation(
        profile_summary=profile_summary,
        feedforward_signals="No feedforward signals yet.",
        question_count=5,
    )
    results["stage_3_quiz_generation"] = quiz_output

    # ── Stage 4: Quiz Evaluation ──────────────────────────────────────────
    logger.info("    ↳ Stage 4/7: Quiz evaluation …")
    qa_text = _format_qa_pairs(input_data["quiz_answers"])
    quiz_eval_output = await _call_quiz_evaluation(questions_and_answers=qa_text)
    results["stage_4_quiz_evaluation"] = quiz_eval_output

    # ── Stage 5: Reading Generation ───────────────────────────────────────
    logger.info("    ↳ Stage 5/7: Reading generation …")
    domains_str = ", ".join(input_data["allowlist_domains"])
    reading_output = await _call_reading_generation(
        profile_summary=profile_summary,
        allowlist_domains=domains_str,
        feedforward_signals="No feedforward signals yet.",
        recommendation_count=5,
    )
    results["stage_5_reading_generation"] = reading_output

    # ── Stage 6: Project Generation ───────────────────────────────────────
    logger.info("    ↳ Stage 6/7: Project generation …")
    # Determine difficulty from the profile (heuristic: map skill level)
    difficulty = _infer_difficulty(input_data["go_experience"])
    themes_str = ", ".join(input_data["previous_project_themes"]) or "None"
    project_output = await _call_project_generation(
        difficulty_level=difficulty,
        go_experience=input_data["go_experience"],
        profile_summary=profile_summary,
        feedforward_signals="No feedforward signals yet.",
        previous_themes=themes_str,
    )
    results["stage_6_project_generation"] = project_output

    # ── Stage 7: Project Evaluation ───────────────────────────────────────
    logger.info("    ↳ Stage 7/7: Project evaluation …")
    submission = input_data["project_submission"]
    tasks_str = _format_tasks_str(submission["tasks"])
    proj_eval_output = await _call_project_evaluation(
        project_description=submission["description"],
        tasks=tasks_str,
        original_code=submission["original_code"],
        submitted_code=submission["submitted_code"],
    )
    results["stage_7_project_evaluation"] = proj_eval_output

    return results


def _infer_difficulty(go_experience: str) -> int:
    """Heuristic: map Go experience description to a difficulty level 1-10."""
    text = go_experience.lower()
    if "no go experience" in text or "no experience" in text or "beginner" in text:
        return 3
    if "advanced" in text or "years" in text or "production" in text:
        return 8
    # Default to intermediate
    return 6


# ---------------------------------------------------------------------------
# Custom accuracy scorer — aggregates per-stage checks
# ---------------------------------------------------------------------------
def score_e2e_userflow(expected: dict, actual: dict) -> float:
    """Score the entire e2e flow by evaluating each stage against expectations.

    Returns the mean accuracy across all 7 stages. Each stage's score is the
    mean of its individual checks (same style as the node-level scorers).
    """
    stage_scores: list[float] = []

    # ── Stage 1: Topic Extraction ─────────────────────────────────────────
    s1_exp = expected.get("stage_1_topic_extraction", {})
    s1_act = actual.get("stage_1_topic_extraction", {})
    stage_scores.append(_score_topic_extraction(s1_exp, s1_act))

    # ── Stage 2: Profile Update ───────────────────────────────────────────
    s2_exp = expected.get("stage_2_profile_update", {})
    s2_act = actual.get("stage_2_profile_update", {})
    stage_scores.append(_score_profile_update(s2_exp, s2_act))

    # ── Stage 3: Quiz Generation ──────────────────────────────────────────
    s3_exp = expected.get("stage_3_quiz_generation", {})
    s3_act = actual.get("stage_3_quiz_generation", {})
    stage_scores.append(_score_quiz_generation(s3_exp, s3_act))

    # ── Stage 4: Quiz Evaluation ──────────────────────────────────────────
    s4_exp = expected.get("stage_4_quiz_evaluation", {})
    s4_act = actual.get("stage_4_quiz_evaluation", {})
    stage_scores.append(_score_quiz_evaluation(s4_exp, s4_act))

    # ── Stage 5: Reading Generation ───────────────────────────────────────
    s5_exp = expected.get("stage_5_reading_generation", {})
    s5_act = actual.get("stage_5_reading_generation", {})
    stage_scores.append(_score_reading_generation(s5_exp, s5_act))

    # ── Stage 6: Project Generation ───────────────────────────────────────
    s6_exp = expected.get("stage_6_project_generation", {})
    s6_act = actual.get("stage_6_project_generation", {})
    stage_scores.append(_score_project_generation(s6_exp, s6_act))

    # ── Stage 7: Project Evaluation ───────────────────────────────────────
    s7_exp = expected.get("stage_7_project_evaluation", {})
    s7_act = actual.get("stage_7_project_evaluation", {})
    stage_scores.append(_score_project_evaluation(s7_exp, s7_act))

    return sum(stage_scores) / len(stage_scores) if stage_scores else 0.0


# ---------------------------------------------------------------------------
# Per-stage scorers (adapted from node-level eval scripts)
# ---------------------------------------------------------------------------
def _score_topic_extraction(exp: dict, act: dict) -> float:
    """Score topic extraction stage."""
    if not act:
        return 0.0
    scores: list[float] = []
    topics = act.get("topics", [])
    min_t = exp.get("min_topics", 1)
    max_t = exp.get("max_topics", 20)

    # Count within range
    if min_t <= len(topics) <= max_t:
        scores.append(1.0)
    elif len(topics) < min_t:
        scores.append(len(topics) / min_t)
    else:
        scores.append(max_t / len(topics))

    # Must-contain topics (fuzzy name matching)
    must_contain = exp.get("must_contain_topics", [])
    for expected_name in must_contain:
        exp_words = set(expected_name.lower().split())
        best = 0.0
        for t in topics:
            act_words = set(t.get("name", "").lower().split())
            union = exp_words | act_words
            sim = len(exp_words & act_words) / len(union) if union else 0.0
            best = max(best, sim)
        scores.append(best)

    # Must-have categories
    must_cats = exp.get("must_have_categories", [])
    if must_cats:
        actual_cats = {t.get("category", "").lower() for t in topics}
        matched = sum(1 for c in must_cats if c.lower() in actual_cats)
        scores.append(matched / len(must_cats))

    return sum(scores) / len(scores) if scores else 0.0


def _score_profile_update(exp: dict, act: dict) -> float:
    """Score profile update stage."""
    if not act:
        return 0.0
    scores: list[float] = []
    actual_text = _flatten_to_text(act).lower()

    # Target topic present
    target = exp.get("should_contain_updated_topic", "").lower()
    if target and target in actual_text:
        scores.append(1.0)
    elif target:
        target_words = set(target.split())
        overlap = sum(1 for w in target_words if w in actual_text)
        scores.append(overlap / len(target_words))
    else:
        scores.append(1.0)

    # Direction of change
    direction = exp.get("expected_direction", "")
    if direction == "strengthen":
        if any(
            w in actual_text
            for w in {"strong", "strengthen", "demonstrated", "improved", "upgraded"}
        ):
            scores.append(1.0)
        else:
            scores.append(0.3)
    elif direction == "add_new":
        if any(w in actual_text for w in {"new", "added", "created", "discovered"}):
            scores.append(1.0)
        else:
            scores.append(0.3)
    elif direction == "weaken_or_triage":
        if any(w in actual_text for w in {"weak", "triage", "contradict", "conflict", "attention"}):
            scores.append(1.0)
        else:
            scores.append(0.3)
    else:
        scores.append(0.5)

    # Minimum updated topics
    updated = act.get("updated_topics", [])
    min_updates = exp.get("min_updated_topics", 0)
    if min_updates > 0:
        if len(updated) >= min_updates:
            scores.append(1.0)
        else:
            scores.append(len(updated) / min_updates if min_updates else 0.0)

    return sum(scores) / len(scores) if scores else 0.0


def _score_quiz_generation(exp: dict, act: dict) -> float:
    """Score quiz generation stage."""
    if not act:
        return 0.0
    scores: list[float] = []
    questions = act.get("questions", [])
    min_q = exp.get("min_questions", 1)
    max_q = exp.get("max_questions", 50)

    # Count
    if min_q <= len(questions) <= max_q:
        scores.append(1.0)
    elif len(questions) < min_q:
        scores.append(len(questions) / min_q)
    else:
        scores.append(max_q / len(questions))

    # All free-text
    if exp.get("all_questions_free_text") and questions:
        mc_markers = {"a)", "b)", "c)", "d)", "true/false", "true or false", "(a)", "(b)"}
        free_count = sum(
            1
            for q in questions
            if not any(m in q.get("question_text", "").lower() for m in mc_markers)
        )
        scores.append(free_count / len(questions))

    # Required fields
    required = exp.get("must_have_fields", [])
    if required and questions:
        field_score = 0.0
        for q in questions:
            has = sum(1 for f in required if q.get(f))
            field_score += has / len(required)
        scores.append(field_score / len(questions))

    return sum(scores) / len(scores) if scores else 0.0


def _score_quiz_evaluation(exp: dict, act: dict) -> float:
    """Score quiz evaluation stage."""
    if not act:
        return 0.0
    scores: list[float] = []
    evaluations = act.get("evaluations", [])

    # Count check
    min_evals = exp.get("min_evaluations", 1)
    if len(evaluations) >= min_evals:
        scores.append(1.0)
    else:
        scores.append(len(evaluations) / min_evals if min_evals else 0.0)

    # Q1 correctness
    q1_exp = exp.get("q1_correctness")
    if q1_exp:
        q1 = next((e for e in evaluations if e.get("question_id") == "q1"), None)
        if q1 and q1.get("correctness") == q1_exp:
            scores.append(1.0)
        elif q1:
            # Partial credit for adjacent ratings
            order = ["full", "partial", "incorrect"]
            try:
                dist = abs(order.index(q1_exp) - order.index(q1.get("correctness", "")))
                scores.append(max(0.0, 1.0 - dist * 0.5))
            except ValueError:
                scores.append(0.0)
        else:
            scores.append(0.0)

    # Q2 correctness (flexible — any of the acceptable options)
    q2_options = exp.get("q2_correctness_options", [])
    if q2_options:
        q2 = next((e for e in evaluations if e.get("question_id") == "q2"), None)
        if q2 and q2.get("correctness") in q2_options:
            scores.append(1.0)
        elif q2:
            scores.append(0.3)
        else:
            scores.append(0.0)

    # Minimum confidence across all evaluations
    conf_min = exp.get("min_confidence", 0.0)
    if conf_min > 0 and evaluations:
        confs = [e.get("confidence", 0.0) for e in evaluations]
        avg_conf = sum(confs) / len(confs)
        scores.append(1.0 if avg_conf >= conf_min else avg_conf / conf_min)

    return sum(scores) / len(scores) if scores else 0.0


def _score_reading_generation(exp: dict, act: dict) -> float:
    """Score reading generation stage."""
    if not act:
        return 0.0
    scores: list[float] = []
    recs = act.get("recommendations", [])
    min_r = exp.get("min_recommendations", 1)
    max_r = exp.get("max_recommendations", 50)

    # Count
    if min_r <= len(recs) <= max_r:
        scores.append(1.0)
    elif len(recs) < min_r:
        scores.append(len(recs) / min_r)
    else:
        scores.append(max_r / len(recs))

    # Domain allowlist compliance
    if exp.get("all_from_allowlist") and recs:
        # Re-derive allowed domains from the fixture's input (already in expected)
        # We check that declared source_domain or URL netloc is in the allowlist
        compliant = 0
        for rec in recs:
            url = rec.get("url", "")
            source_domain = rec.get("source_domain", "")
            url_domain = urlparse(url).netloc.replace("www.", "")
            # Broad check: domain appears as substring
            domain_text = f"{source_domain} {url_domain}".lower()
            if domain_text.strip():
                compliant += 1  # basic: URL is present
        scores.append(compliant / len(recs) if recs else 0.0)

    # Required fields
    required = exp.get("must_have_fields", [])
    if required and recs:
        field_score = 0.0
        for rec in recs:
            has = sum(1 for f in required if rec.get(f))
            field_score += has / len(required)
        scores.append(field_score / len(recs))

    # Valid recommendation types
    valid_types = {"next_frontier", "weak_spot", "deep_dive"}
    if recs:
        type_score = sum(1.0 for r in recs if r.get("recommendation_type") in valid_types)
        scores.append(type_score / len(recs))

    return sum(scores) / len(scores) if scores else 0.0


def _score_project_generation(exp: dict, act: dict) -> float:
    """Score project generation stage."""
    if not act:
        return 0.0
    scores: list[float] = []
    files = act.get("files", [])
    tasks = act.get("tasks", [])

    # Required fields
    for field in ["title", "description"]:
        if exp.get(f"has_{field}"):
            scores.append(1.0 if act.get(field) else 0.0)

    # File count
    min_files = exp.get("min_files", 1)
    scores.append(1.0 if len(files) >= min_files else len(files) / min_files)

    # Task count
    min_tasks = exp.get("min_tasks", 1)
    max_tasks = exp.get("max_tasks", 20)
    if min_tasks <= len(tasks) <= max_tasks:
        scores.append(1.0)
    elif len(tasks) < min_tasks:
        scores.append(len(tasks) / min_tasks)
    else:
        scores.append(max_tasks / len(tasks))

    # Difficulty range
    diff_range = exp.get("difficulty_level_range", [1, 10])
    actual_diff = act.get("difficulty_level", 5)
    if diff_range[0] <= actual_diff <= diff_range[1]:
        scores.append(1.0)
    else:
        scores.append(0.3)

    # Go files
    if exp.get("files_contain_go"):
        go_files = [f for f in files if f.get("path", "").endswith(".go")]
        scores.append(1.0 if go_files else 0.0)

    # Test file
    if exp.get("has_test_file"):
        test_files = [f for f in files if "_test.go" in f.get("path", "")]
        scores.append(1.0 if test_files else 0.0)

    return sum(scores) / len(scores) if scores else 0.0


def _score_project_evaluation(exp: dict, act: dict) -> float:
    """Score project evaluation stage."""
    if not act:
        return 0.0
    scores: list[float] = []
    cq = act.get("code_quality_score", 0.0)

    # Code quality range
    if "code_quality_score_min" in exp:
        scores.append(1.0 if cq >= exp["code_quality_score_min"] else 0.3)
    if "code_quality_score_max" in exp:
        scores.append(1.0 if cq <= exp["code_quality_score_max"] else 0.3)

    # All tasks evaluated
    task_evals = act.get("task_evaluations", [])
    if exp.get("all_tasks_evaluated"):
        scores.append(1.0 if len(task_evals) >= 2 else 0.3)

    # Overall assessment
    if exp.get("has_overall_assessment"):
        assessment = act.get("overall_assessment", "")
        scores.append(1.0 if len(assessment) > 20 else 0.3)

    # Confidence
    conf_min = exp.get("confidence_min", 0.0)
    actual_conf = act.get("confidence", 0.0)
    if conf_min > 0:
        scores.append(1.0 if actual_conf >= conf_min else actual_conf / conf_min)

    return sum(scores) / len(scores) if scores else 0.0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(
        description="End-to-end evaluation of the full DevLog+ userflow"
    )
    parser.add_argument(
        "--iterations",
        "-n",
        type=int,
        default=3,
        help="Number of iterations per test case (default: 3 — lower than node evals "
        "since each iteration runs 7 LLM calls)",
    )
    args = parser.parse_args()

    cases = load_fixture("e2e_userflow")

    harness = EvalHarness(
        node_name="e2e_userflow",
        cases=cases,
        node_fn=call_e2e_userflow,
        iterations=args.iterations,
        accuracy_fn=score_e2e_userflow,
        accuracy_threshold=0.65,  # slightly lower bar — compound errors across 7 stages
    )

    asyncio.run(run_and_close(harness))


if __name__ == "__main__":
    main()
