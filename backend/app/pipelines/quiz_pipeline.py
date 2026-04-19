"""Weekly quiz generation and evaluation pipeline.

Generates a set of free-text quiz questions based on the Knowledge Profile,
and evaluates completed quiz answers using an LLM judge.

Run via cron weekly or manually via CLI.
"""

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.config import settings
from backend.app.models.base import (
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
from backend.app.models.triage import TriageItem
from backend.app.prompts import quiz_evaluation, quiz_generation
from backend.app.services import feedback as feedback_svc
from backend.app.services import profile as profile_svc
from backend.app.services.llm.client import llm_client
from backend.app.services.llm.models import QuizEvaluationResult, QuizGenerationResult

logger = logging.getLogger(__name__)


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

        # Gather feedforward signals from recent feedback
        all_feedback = await feedback_svc.list_all_feedback(db, limit=50)
        feedforward = [f.note for f in all_feedback if f.note]
        feedforward_text = "\n".join(f"- {n}" for n in feedforward[:10]) or "None"

        question_count = settings.quiz_question_count

        # Generate questions via LLM
        prompt = quiz_generation.USER_PROMPT_TEMPLATE.format(
            profile_summary=profile_summary,
            feedforward_signals=feedforward_text,
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

        # Create quiz session
        session = QuizSession(
            status=QuizSessionStatus.PENDING,
            question_count=len(gen_result.questions),
        )
        db.add(session)
        await db.flush()

        # Create questions
        for i, q in enumerate(gen_result.questions):
            try:
                q_type = QuizQuestionType(q.question_type)
            except ValueError:
                q_type = QuizQuestionType.REINFORCEMENT

            question = QuizQuestion(
                session_id=session.id,
                question_text=q.question_text,
                question_type=q_type,
                order_index=i,
            )
            db.add(question)

        await db.flush()

        log.status = PipelineStatus.COMPLETED
        log.completed_at = datetime.now(UTC)
        log.metadata_ = {
            "session_id": str(session.id),
            "question_count": len(gen_result.questions),
        }
        await db.flush()

        logger.info(
            "Quiz generated: session=%s questions=%d",
            session.id,
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
