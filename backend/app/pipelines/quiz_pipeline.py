"""Weekly quiz generation and evaluation pipeline.

Generates a set of free-text quiz questions based on the Knowledge Profile,
and evaluates completed quiz answers using an LLM judge.

Run via cron weekly or manually via CLI.
"""

import logging
import uuid
from datetime import UTC, datetime
from difflib import get_close_matches

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.config import settings
from backend.app.models.base import (
    FeedbackTargetType,
    PipelineStatus,
    PipelineType,
    QuizCorrectness,
    QuizQuestionType,
    QuizSessionStatus,
    TriageSeverity,
    TriageSource,
)
from backend.app.models.quiz import QuizEvaluation, QuizQuestion, QuizSession
from backend.app.models.settings import ProcessingLog
from backend.app.models.topic import Topic
from backend.app.models.triage import TriageItem
from backend.app.prompts import quiz_evaluation, quiz_generation
from backend.app.services import feedback as feedback_svc
from backend.app.services import profile as profile_svc
from backend.app.services.llm.client import llm_client
from backend.app.services.llm.models import QuizEvaluationResult, QuizGenerationResult

logger = logging.getLogger(__name__)


async def _load_question_lookup(
    db: AsyncSession, ids: set[uuid.UUID]
) -> dict[uuid.UUID, QuizQuestion]:
    if not ids:
        return {}
    stmt = select(QuizQuestion).where(QuizQuestion.id.in_(ids))
    result = await db.execute(stmt)
    return {q.id: q for q in result.scalars().all()}


def _truncate(text: str, n: int = 140) -> str:
    text = text.strip().replace("\n", " ")
    return text if len(text) <= n else text[: n - 1] + "…"


async def _load_topic_name_lookup(db: AsyncSession) -> dict[str, uuid.UUID]:
    """Return a case-insensitive ``{topic_name: topic_id}`` map of all topics."""
    stmt = select(Topic.id, Topic.name)
    result = await db.execute(stmt)
    return {name.casefold(): tid for tid, name in result.all()}


def _resolve_topic_id(
    target_topic: str | None,
    topic_lookup: dict[str, uuid.UUID],
) -> uuid.UUID | None:
    """Best-effort match of an LLM-supplied topic label to a known Topic.id.

    Strategy:
    1. Exact case-insensitive match.
    2. Fuzzy match via :func:`difflib.get_close_matches` (cutoff 0.75).
    Returns ``None`` if no acceptable match exists.
    """
    if not target_topic or not topic_lookup:
        return None
    needle = target_topic.strip().casefold()
    if not needle:
        return None
    if needle in topic_lookup:
        return topic_lookup[needle]
    matches = get_close_matches(needle, topic_lookup.keys(), n=1, cutoff=0.75)
    if matches:
        return topic_lookup[matches[0]]
    return None


def _format_quiz_feedforward(
    feedback_items,
    question_lookup: dict[uuid.UUID, QuizQuestion],
    max_items: int = 10,
) -> str:
    lines: list[str] = []
    for fb in feedback_items:
        if not fb.note:
            continue
        if fb.target_type == FeedbackTargetType.QUIZ_QUESTION:
            q = question_lookup.get(fb.target_id)
            descriptor = (
                f'question "{_truncate(q.question_text, 80)}"' if q else "question (removed)"
            )
            reaction = f", {fb.reaction.value}" if fb.reaction else ""
            lines.append(f"- ({descriptor}{reaction}) {fb.note}")
        else:
            lines.append(f"- {fb.note}")
        if len(lines) >= max_items:
            break
    return "\n".join(lines) or "None"


def _format_liked_question_directions(
    liked_questions: list[QuizQuestion],
    max_items: int = 10,
) -> str:
    """Summarise thumbs-up'd questions as positive *directional* signals.

    We surface topic + question_type + a truncated stem so the LLM can lean
    toward the same flavour of question without re-asking the literal one
    (the literal text is added to the hard avoid list separately).
    """
    if not liked_questions:
        return "None"
    sorted_likes = sorted(liked_questions, key=lambda q: q.created_at or datetime.min, reverse=True)
    lines: list[str] = []
    for q in sorted_likes[:max_items]:
        topic = q.topic_name or "?"
        q_type = q.question_type.value if q.question_type else "?"
        lines.append(f'- [{topic} / {q_type}] "{_truncate(q.question_text, 100)}"')
    return "\n".join(lines)


async def generate_quiz(
    db: AsyncSession,
    *,
    run_id: uuid.UUID | None = None,
) -> QuizSession:
    """Generate a new weekly quiz session with questions.

    Args:
        db: Async session.
        run_id: Optional pre-generated id for the ``ProcessingLog`` row.

    Steps:
    1. Build profile summary for context
    2. Gather feedforward signals
    3. Call LLM to generate questions
    4. Store session and questions
    """
    log_kwargs: dict = {
        "pipeline": PipelineType.QUIZ_GENERATION,
        "status": PipelineStatus.STARTED,
    }
    if run_id is not None:
        log_kwargs["id"] = run_id
    log = ProcessingLog(**log_kwargs)
    db.add(log)
    await db.flush()

    try:
        # Build profile context
        profile = await profile_svc.get_knowledge_profile(db)
        profile_summary = profile.model_dump_json(indent=2)

        # Gather thumbs-down questions — asked before and rejected. Surface
        # their texts to the LLM so near-duplicates are avoided.
        disliked_q_ids = await feedback_svc.list_disliked_target_ids(
            db, FeedbackTargetType.QUIZ_QUESTION
        )
        disliked_q_lookup = await _load_question_lookup(db, disliked_q_ids)
        disliked_q_texts = {q.question_text.strip() for q in disliked_q_lookup.values()}

        # Gather thumbs-up questions — positive *directional* signal.
        # We hard-block the exact question texts (re-asking a question the
        # user already engaged with positively yields little new signal) but
        # surface topic + question_type so the LLM can lean in the same
        # direction with NEW questions.
        liked_q_ids = await feedback_svc.list_liked_target_ids(db, FeedbackTargetType.QUIZ_QUESTION)
        liked_q_lookup = await _load_question_lookup(db, liked_q_ids)
        liked_questions = list(liked_q_lookup.values())
        liked_q_texts = {q.question_text.strip() for q in liked_questions}

        # Combined hard-avoid set: disliked + already-liked question texts.
        # Both are dead-ends for re-asking, just for opposite reasons.
        avoid_q_texts = disliked_q_texts | liked_q_texts
        avoid_questions_text = (
            "\n".join(f"- {_truncate(t)}" for t in sorted(avoid_q_texts)) or "None"
        )
        liked_directions_text = _format_liked_question_directions(liked_questions)

        # Contextualised feedforward, scoped to quiz questions + general notes.
        relevant_feedback = await feedback_svc.list_feedback_by_target_types(
            db, [FeedbackTargetType.QUIZ_QUESTION], limit=50
        )
        other_feedback = await feedback_svc.list_all_feedback(db, limit=50)
        seen_ids = {f.id for f in relevant_feedback}
        for fb in other_feedback:
            if fb.id not in seen_ids and fb.note:
                relevant_feedback.append(fb)
        note_q_ids = {
            fb.target_id
            for fb in relevant_feedback
            if fb.target_type == FeedbackTargetType.QUIZ_QUESTION
        }
        note_q_lookup = await _load_question_lookup(db, note_q_ids)
        feedforward_text = _format_quiz_feedforward(relevant_feedback, note_q_lookup)

        question_count = settings.quiz_question_count

        # Generate questions via LLM
        prompt = quiz_generation.USER_PROMPT_TEMPLATE.format(
            profile_summary=profile_summary,
            feedforward_signals=feedforward_text,
            avoid_questions=avoid_questions_text,
            liked_directions=liked_directions_text,
            question_count=question_count,
        )

        raw_result = await llm_client.chat_completion_json(
            pipeline="quiz_generation",
            messages=[
                {"role": "system", "content": quiz_generation.SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        )

        gen_result = QuizGenerationResult.model_validate(raw_result)

        # Build a lookup so we can resolve LLM-supplied `target_topic` labels
        # back to Knowledge Profile Topic.id values.
        topic_lookup = await _load_topic_name_lookup(db)

        # Create quiz session
        session = QuizSession(
            status=QuizSessionStatus.PENDING,
            question_count=len(gen_result.questions),
        )
        db.add(session)
        await db.flush()

        # Create questions, applying hard-avoid + diversity gates as a
        # belt-and-braces enforcement on top of the prompt instructions.
        skipped_disliked = 0
        skipped_already_liked = 0
        skipped_duplicate_topic = 0
        seen_topics: set[str] = set()
        stored_count = 0

        for q in gen_result.questions:
            text_key = q.question_text.strip()

            # Hard filter: never re-ask a question the user has already
            # reacted to. Thumbs-down → they rejected it; thumbs-up → they
            # already engaged with it, so re-asking yields little new signal.
            if text_key in disliked_q_texts:
                logger.info("Skipping previously-disliked question: %s", _truncate(text_key))
                skipped_disliked += 1
                continue
            if text_key in liked_q_texts:
                logger.info("Skipping already-liked question: %s", _truncate(text_key))
                skipped_already_liked += 1
                continue

            # Diversity guard: refuse a second question targeting the same
            # topic in this session. The prompt asks for distinct topics;
            # this enforces it so a single hot topic can't dominate the
            # quiz even if the LLM ignores the instruction.
            topic_key = (q.target_topic or "").strip().lower()
            if topic_key and topic_key in seen_topics:
                logger.info(
                    "Skipping duplicate-topic question (topic=%s): %s",
                    q.target_topic,
                    _truncate(text_key),
                )
                skipped_duplicate_topic += 1
                continue

            try:
                q_type = QuizQuestionType(q.question_type)
            except ValueError:
                q_type = QuizQuestionType.REINFORCEMENT

            resolved_topic_id = _resolve_topic_id(q.target_topic, topic_lookup)
            if q.target_topic and resolved_topic_id is None:
                logger.info(
                    "Quiz question target_topic %r did not match any known topic",
                    q.target_topic,
                )

            question = QuizQuestion(
                session_id=session.id,
                question_text=q.question_text,
                question_type=q_type,
                reference_answer=(q.reference_answer.strip() or None)
                if q.reference_answer
                else None,
                topic_id=resolved_topic_id,
                order_index=stored_count,
            )
            db.add(question)
            stored_count += 1
            if topic_key:
                seen_topics.add(topic_key)

        # Reflect the actual stored count on the session so downstream
        # consumers (UI progress, evaluation pipeline) see the truth.
        session.question_count = stored_count

        await db.flush()

        log.status = PipelineStatus.COMPLETED
        log.completed_at = datetime.now(UTC)
        log.metadata_ = {
            "session_id": str(session.id),
            "generated": len(gen_result.questions),
            "stored": stored_count,
            "skipped_disliked": skipped_disliked,
            "skipped_already_liked": skipped_already_liked,
            "skipped_duplicate_topic": skipped_duplicate_topic,
            "distinct_topics": len(seen_topics),
            # Kept for backwards-compat with anything reading the old key.
            "question_count": stored_count,
        }
        await db.flush()

        logger.info(
            "Quiz generated: session=%s stored=%d of %d generated",
            session.id,
            stored_count,
            len(gen_result.questions),
        )
        return session

    except Exception as e:
        log.status = PipelineStatus.FAILED
        log.error = str(e)
        log.completed_at = datetime.now(UTC)
        await db.flush()
        raise


async def evaluate_quiz(db: AsyncSession, session_id) -> dict:
    """Evaluate all answers in a completed quiz session.

    Steps:
    1. Load session with all questions and answers
    2. Send to LLM for evaluation
    3. Store evaluations
    4. Create triage items if needed
    """
    from backend.app.services import quiz as quiz_svc

    log = ProcessingLog(
        pipeline=PipelineType.QUIZ_EVALUATION,
        status=PipelineStatus.STARTED,
    )
    db.add(log)
    await db.flush()

    try:
        session = await quiz_svc.get_session(db, session_id)
        if session is None:
            raise ValueError(f"Quiz session {session_id} not found")

        # Build Q&A pairs
        qa_pairs = []
        for q in session.questions:
            answer_text = q.answer.answer_text if q.answer else "(no answer submitted)"
            qa_pairs.append(
                {
                    "question_id": str(q.id),
                    "question": q.question_text,
                    "answer": answer_text,
                }
            )

        qa_text = "\n\n".join(
            f"### Question {i + 1} (ID: {qa['question_id']})\n"
            f"**Q:** {qa['question']}\n**A:** {qa['answer']}"
            for i, qa in enumerate(qa_pairs)
        )

        prompt = quiz_evaluation.USER_PROMPT_TEMPLATE.format(
            questions_and_answers=qa_text,
        )

        raw_result = await llm_client.chat_completion_json(
            pipeline="quiz_evaluation",
            messages=[
                {"role": "system", "content": quiz_evaluation.SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        )

        eval_result = QuizEvaluationResult.model_validate(raw_result)

        # Store evaluations
        for ev in eval_result.evaluations:
            try:
                correctness = QuizCorrectness(ev.correctness)
            except ValueError:
                correctness = QuizCorrectness.PARTIAL

            evaluation = QuizEvaluation(
                question_id=ev.question_id,
                correctness=correctness,
                depth_assessment=ev.depth_assessment,
                explanation=ev.explanation,
                confidence=ev.confidence,
                raw_llm_output=ev.model_dump(),
            )
            db.add(evaluation)

        # Create triage items
        for ti in eval_result.triage_items:
            triage = TriageItem(
                source=TriageSource.QUIZ_EVALUATION,
                title=ti.get("title", "Quiz evaluation issue"),
                description=ti.get("description", ""),
                context=ti,
                severity=TriageSeverity(ti.get("severity", "low")),
            )
            db.add(triage)

        # Update session status
        session.status = QuizSessionStatus.EVALUATED
        await db.flush()

        log.status = PipelineStatus.COMPLETED
        log.completed_at = datetime.now(UTC)
        log.metadata_ = {
            "session_id": str(session_id),
            "evaluations": len(eval_result.evaluations),
            "triage_items": len(eval_result.triage_items),
        }
        await db.flush()

        return {
            "status": "completed",
            "evaluations": len(eval_result.evaluations),
            "triage_items": len(eval_result.triage_items),
        }

    except Exception as e:
        log.status = PipelineStatus.FAILED
        log.error = str(e)
        log.completed_at = datetime.now(UTC)
        await db.flush()
        raise
