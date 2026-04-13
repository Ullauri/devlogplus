"""Quiz session, question, answer, and evaluation schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from backend.app.models.base import (
    QuizCorrectness,
    QuizQuestionType,
    QuizSessionStatus,
)
from backend.app.schemas.common import BaseSchema


# ---------------------------------------------------------------------------
# Quiz Evaluation
# ---------------------------------------------------------------------------
class QuizEvaluationResponse(BaseSchema):
    """LLM-generated evaluation of a quiz answer."""

    id: uuid.UUID = Field(description="Evaluation ID")
    question_id: uuid.UUID = Field(description="The question this evaluation applies to")
    correctness: QuizCorrectness = Field(
        description="Correctness verdict: full, partial, or incorrect"
    )
    depth_assessment: str | None = Field(
        description="Qualitative assessment of the answer's depth and nuance"
    )
    explanation: str = Field(
        description="Detailed explanation of why the answer was evaluated this way"
    )
    confidence: float = Field(
        description="LLM confidence in this evaluation (0.0–1.0)",
        ge=0.0,
        le=1.0,
    )
    created_at: datetime = Field(description="When the evaluation was generated")


# ---------------------------------------------------------------------------
# Quiz Answer
# ---------------------------------------------------------------------------
class QuizAnswerCreate(BaseModel):
    """Submit a free-text answer to a quiz question."""

    answer_text: str = Field(
        ...,
        min_length=1,
        description="The user's free-text answer (no multiple choice)",
        examples=["Goroutines are lightweight threads managed by the Go runtime..."],
    )


class QuizAnswerResponse(BaseSchema):
    """A recorded answer to a quiz question."""

    id: uuid.UUID = Field(description="Answer ID")
    question_id: uuid.UUID = Field(description="The question this answers")
    answer_text: str = Field(description="The submitted answer text")
    created_at: datetime = Field(description="When the answer was submitted")


# ---------------------------------------------------------------------------
# Quiz Question
# ---------------------------------------------------------------------------
class QuizQuestionResponse(BaseSchema):
    """A single quiz question with optional answer and evaluation."""

    id: uuid.UUID = Field(description="Question ID")
    session_id: uuid.UUID = Field(description="Parent quiz session ID")
    question_text: str = Field(description="The question text")
    question_type: QuizQuestionType = Field(description="Question type (always free_text)")
    topic_id: uuid.UUID | None = Field(
        description="ID of the Knowledge Profile topic this question targets"
    )
    order_index: int = Field(description="Position of the question within the session (0-based)")
    created_at: datetime = Field(description="When the question was generated")
    answer: QuizAnswerResponse | None = Field(
        None, description="The user's submitted answer, if any"
    )
    evaluation: QuizEvaluationResponse | None = Field(
        None, description="LLM evaluation of the answer, if completed"
    )


# ---------------------------------------------------------------------------
# Quiz Session
# ---------------------------------------------------------------------------
class QuizSessionResponse(BaseSchema):
    """Quiz session summary."""

    id: uuid.UUID = Field(description="Session ID")
    status: QuizSessionStatus = Field(
        description="Session status: pending, completed, or evaluated"
    )
    question_count: int = Field(description="Number of questions in this session")
    completed_at: datetime | None = Field(
        description="When all answers were submitted (null if still pending)"
    )
    created_at: datetime = Field(description="When the session was generated")
    updated_at: datetime = Field(description="Last modification timestamp")


class QuizSessionDetailResponse(QuizSessionResponse):
    """Quiz session with all questions, submitted answers, and LLM evaluations."""

    questions: list[QuizQuestionResponse] = Field(
        default=[], description="All questions in this session, ordered by index"
    )
