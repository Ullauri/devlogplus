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

# Both quiz calls return one JSON object whose size scales with the number of
# questions in play, so the client's 4096 default is a fixed budget for a
# variable-length response. Observed failures: a 10-question generation run
# stopped at finish_reason=length with ~13k characters emitted and the array
# still open, and an evaluation run stopped mid-`triage_items` at ~11.7k. A
# truncated object loses the *whole* response rather than degrading — there is
# no closing brace for the parser to work with — so budget per item instead.
#
# The budget scales rather than sitting at a flat constant because
# `quiz_question_count` is configurable up to 50: a constant sized for the
# default of 10 reintroduces this the moment someone raises it.
_QUIZ_MAX_TOKENS_CEILING = 32000

# Each generated question carries question_text, difficulty_rationale and a
# reference_answer; the reference answers dominate and run well past 1k tokens
# apiece. Measured at roughly 1200 tokens per question, so 1600 leaves room for
# a verbose answer without inviting one.
_QUIZ_GENERATION_BASE_TOKENS = 2048
_QUIZ_GENERATION_TOKENS_PER_QUESTION = 1600

# Each evaluation carries depth_assessment, explanation and topic_signals, with
# a shared triage_items array appended at the end.
_QUIZ_EVALUATION_BASE_TOKENS = 2048
_QUIZ_EVALUATION_TOKENS_PER_ANSWER = 1200

# How many recent sessions count as "already asked".
#
# Feedback is the wrong signal for this on its own: it only covers the handful
# of questions someone bothered to rate, so a quiz answered start to finish
# without a single thumbs-up left no trace and the next run re-derived the same
# topics from the same profile. Quizzes are weekly, so six sessions is about a
# month and a half — long enough that a topic does not come back before the
# user has forgotten the last question on it, short enough that a modest
# profile still has somewhere to go.
_RECENT_SESSION_WINDOW = 6

# Ceilings on what these signals contribute to the prompt, so raising
# `quiz_question_count` cannot grow the blocks without bound.
_MAX_AVOID_QUESTIONS_IN_PROMPT = 60
_MAX_RECENT_TOPICS_IN_PROMPT = 25


def _budgeted_max_tokens(base: int, per_item: int, item_count: int) -> int:
    """Scale a token budget with the item count, clamped to a sane ceiling.

    The ceiling keeps a large ``quiz_question_count`` from requesting more than
    the model will actually honour.
    """
    return min(base + per_item * max(item_count, 1), _QUIZ_MAX_TOKENS_CEILING)


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


async def _load_recent_questions(
    db: AsyncSession, *, session_window: int = _RECENT_SESSION_WINDOW
) -> list[QuizQuestion]:
    """Questions from the most recent sessions, newest session first.

    These are the questions the user has already *been asked*, regardless of
    whether they reacted to any of them — the signal the avoid-list was
    missing.
    """
    recent_session_ids = (
        select(QuizSession.id)
        .where(QuizSession.questions.any())
        .order_by(QuizSession.created_at.desc())
        .limit(session_window)
        .scalar_subquery()
    )
    stmt = (
        select(QuizQuestion)
        .join(QuizSession, QuizQuestion.session_id == QuizSession.id)
        .where(QuizQuestion.session_id.in_(recent_session_ids))
        .order_by(QuizSession.created_at.desc(), QuizQuestion.order_index)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


def _format_recent_topics(
    recent_questions: list[QuizQuestion],
    max_items: int = _MAX_RECENT_TOPICS_IN_PROMPT,
) -> str:
    """List the topics recent quizzes already covered, most recent first.

    Steering, not a ban. The observed failure was topical rather than literal
    — the same ground reworded — but hard-refusing every recent topic would
    starve a small profile, and a generation run that returns nothing is worse
    than one that repeats itself.
    """
    seen: list[str] = []
    lowered: set[str] = set()
    for q in recent_questions:
        name = (q.topic_name or "").strip()
        key = name.casefold()
        if not name or key in lowered:
            continue
        lowered.add(key)
        seen.append(name)
        if len(seen) >= max_items:
            break
    return "\n".join(f"- {name}" for name in seen) or "None"


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
) -> QuizSession | None:
    """Generate a new weekly quiz session with questions.

    Args:
        db: Async session.
        run_id: Optional pre-generated id for the ``ProcessingLog`` row.

    Steps:
    1. Build profile summary for context
    2. Gather feedforward signals
    3. Call LLM to generate questions
    4. Store session and questions

    Returns the new session, or ``None`` when no questions survived the
    filters (no session is created in that case) or the run failed.
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

        # Questions from recent sessions — asked already, reacted to or not.
        # Without these the avoid-list saw only rated questions, so a quiz the
        # user answered in full and never rated taught the next run nothing.
        recent_questions = await _load_recent_questions(db)
        recent_q_texts = {q.question_text.strip() for q in recent_questions}
        recent_topics_text = _format_recent_topics(recent_questions)

        # Three hard-avoid sets — disliked, already-liked, recently asked — all
        # dead-ends for re-asking, for different reasons. The filter below
        # checks each in full; only this prompt listing is capped.
        #
        # Rated questions are listed first and never dropped by the cap:
        # rating one is a deliberate act, the sets are small, and truncating a
        # sorted union would have discarded them alphabetically. Recent
        # questions fill whatever budget is left, newest session first.
        rated_avoid = sorted(disliked_q_texts | liked_q_texts)
        recent_avoid: list[str] = []
        listed: set[str] = disliked_q_texts | liked_q_texts
        for q in recent_questions:
            text = q.question_text.strip()
            if text not in listed:
                listed.add(text)
                recent_avoid.append(text)
        budget = max(_MAX_AVOID_QUESTIONS_IN_PROMPT - len(rated_avoid), 0)
        avoid_questions_text = (
            "\n".join(f"- {_truncate(t)}" for t in rated_avoid + recent_avoid[:budget]) or "None"
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
            recent_topics=recent_topics_text,
            liked_directions=liked_directions_text,
            question_count=question_count,
        )

        raw_result = await llm_client.chat_completion_json(
            pipeline="quiz_generation",
            messages=[
                {"role": "system", "content": quiz_generation.SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            max_tokens=_budgeted_max_tokens(
                _QUIZ_GENERATION_BASE_TOKENS,
                _QUIZ_GENERATION_TOKENS_PER_QUESTION,
                question_count,
            ),
            # A quiz is a long JSON object, so it is the most exposed to a
            # single malformed key, and a failure here costs the user their
            # whole weekly quiz with nothing on the page to say why.
            json_retries=1,
        )

        gen_result = QuizGenerationResult.model_validate(raw_result)
        if not gen_result.questions:
            # ``questions`` defaults to [], so a response shaped differently
            # than asked parses cleanly into zero questions. Saying so here
            # separates "the model returned none" from "the filters took them".
            logger.warning(
                "Quiz generation returned no questions at all (top-level keys: %s)",
                sorted(raw_result) or "<empty object>",
            )

        # Build a lookup so we can resolve LLM-supplied `target_topic` labels
        # back to Knowledge Profile Topic.id values.
        topic_lookup = await _load_topic_name_lookup(db)

        # Apply the hard-avoid + diversity gates *before* creating the session,
        # as belt-and-braces enforcement on top of the prompt instructions.
        #
        # The gates run first so a run that filters everything out leaves no
        # session behind. An empty session is not merely useless: it counts as
        # an unfinished quiz, which used to displace the real one the user was
        # part-way through.
        skipped_disliked = 0
        skipped_already_liked = 0
        skipped_recently_asked = 0
        skipped_duplicate_topic = 0
        seen_topics: set[str] = set()
        accepted: list[dict] = []

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

            # Verbatim repeat of something a recent quiz already asked. Only
            # catches exact text — the reworded case is the prompt's job.
            if text_key in recent_q_texts:
                logger.info("Skipping recently-asked question: %s", _truncate(text_key))
                skipped_recently_asked += 1
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

            accepted.append(
                {
                    "question_text": q.question_text,
                    "question_type": q_type,
                    "reference_answer": (q.reference_answer.strip() or None)
                    if q.reference_answer
                    else None,
                    "topic_id": resolved_topic_id,
                    "order_index": len(accepted),
                }
            )
            if topic_key:
                seen_topics.add(topic_key)

        stored_count = len(accepted)

        if stored_count == 0:
            logger.warning(
                "Quiz generation stored no questions (generated=%d) — no session created",
                len(gen_result.questions),
            )
            log.status = PipelineStatus.COMPLETED
            log.completed_at = datetime.now(UTC)
            log.metadata_ = {
                "session_id": None,
                "generated": len(gen_result.questions),
                "stored": 0,
                "skipped_disliked": skipped_disliked,
                "skipped_already_liked": skipped_already_liked,
                "skipped_recently_asked": skipped_recently_asked,
                "skipped_duplicate_topic": skipped_duplicate_topic,
                "distinct_topics": 0,
                "question_count": 0,
            }
            await db.flush()
            return None

        # question_count reflects the actual stored count so downstream
        # consumers (UI progress, evaluation pipeline) see the truth.
        session = QuizSession(
            status=QuizSessionStatus.PENDING,
            question_count=stored_count,
        )
        db.add(session)
        await db.flush()

        for kwargs in accepted:
            db.add(QuizQuestion(session_id=session.id, **kwargs))

        await db.flush()

        log.status = PipelineStatus.COMPLETED
        log.completed_at = datetime.now(UTC)
        log.metadata_ = {
            "session_id": str(session.id),
            "generated": len(gen_result.questions),
            "stored": stored_count,
            "skipped_disliked": skipped_disliked,
            "skipped_already_liked": skipped_already_liked,
            "skipped_recently_asked": skipped_recently_asked,
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
        logger.exception("Quiz generation pipeline failed")


async def evaluate_quiz(
    db: AsyncSession,
    session_id,
    *,
    run_id: uuid.UUID | None = None,
) -> dict:
    """Evaluate all answers in a completed quiz session.

    Args:
        db: Async session.
        session_id: The quiz session to evaluate.
        run_id: Optional pre-generated id for the ``ProcessingLog`` row.
            When provided (e.g. from the manual-trigger router), the log
            row carries the same id that was already returned to the HTTP
            client, so the UI can correlate the 202 response to a log entry.

    Steps:
    1. Load session with all questions and answers
    2. Send to LLM for evaluation
    3. Store evaluations
    4. Create triage items if needed
    """
    from backend.app.services import quiz as quiz_svc

    log_kwargs: dict = {
        "pipeline": PipelineType.QUIZ_EVALUATION,
        "status": PipelineStatus.STARTED,
    }
    if run_id is not None:
        log_kwargs["id"] = run_id
    log = ProcessingLog(**log_kwargs)
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
            max_tokens=_budgeted_max_tokens(
                _QUIZ_EVALUATION_BASE_TOKENS,
                _QUIZ_EVALUATION_TOKENS_PER_ANSWER,
                len(qa_pairs),
            ),
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
        logger.exception("Quiz evaluation pipeline failed")
