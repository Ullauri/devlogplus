"""Re-export all models so Alembic and the app can import from one place."""

from backend.app.models.base import Base
from backend.app.models.feedback import Feedback
from backend.app.models.journal import JournalEntry, JournalEntryVersion
from backend.app.models.project import ProjectEvaluation, ProjectTask, WeeklyProject
from backend.app.models.quiz import (
    QuizAnswer,
    QuizEvaluation,
    QuizQuestion,
    QuizSession,
)
from backend.app.models.reading import ReadingAllowlist, ReadingRecommendation
from backend.app.models.settings import (
    OnboardingState,
    ProcessingLog,
    ProfileSnapshot,
    UserSettings,
)
from backend.app.models.topic import Topic, TopicRelationship
from backend.app.models.triage import TriageItem

__all__ = [
    "Base",
    "Feedback",
    "JournalEntry",
    "JournalEntryVersion",
    "OnboardingState",
    "ProcessingLog",
    "ProfileSnapshot",
    "ProjectEvaluation",
    "ProjectTask",
    "QuizAnswer",
    "QuizEvaluation",
    "QuizQuestion",
    "QuizSession",
    "ReadingAllowlist",
    "ReadingRecommendation",
    "Topic",
    "TopicRelationship",
    "TriageItem",
    "UserSettings",
    "WeeklyProject",
]
