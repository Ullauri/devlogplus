"""BDD test fixtures and helpers.

Uses ``nest_asyncio`` so that synchronous pytest-bdd step functions can call
``run_async(coro)`` to drive the async FastAPI / SQLAlchemy stack.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

import nest_asyncio
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.database import get_db
from backend.app.main import app
from backend.app.models import Base

# ---------------------------------------------------------------------------
# Patch the event loop so ``loop.run_until_complete`` can be called even when
# the loop is already running (which is the case under pytest-asyncio).
# ---------------------------------------------------------------------------
nest_asyncio.apply()


def run_async(coro):
    """Run an async coroutine from a synchronous context.

    Works because ``nest_asyncio`` has been applied above.
    """
    loop = asyncio.get_event_loop()
    return loop.run_until_complete(coro)


# ---------------------------------------------------------------------------
# Per-test async database session (mirrors the root conftest pattern)
# ---------------------------------------------------------------------------
@pytest.fixture()
def bdd_db(test_session_factory):
    """Yield a fresh DB session; truncate all tables after the test."""

    async def _make():
        session = test_session_factory()
        return session

    session: AsyncSession = run_async(_make())

    yield session

    # Cleanup: close session then truncate
    async def _cleanup():
        await session.close()
        async with test_session_factory() as cleanup:
            for table in reversed(Base.metadata.sorted_tables):
                await cleanup.execute(text(f"TRUNCATE {table.fullname} CASCADE"))
            await cleanup.commit()

    run_async(_cleanup())


@pytest.fixture()
def bdd_client(bdd_db: AsyncSession):
    """HTTPX ``AsyncClient`` wired to the test DB session."""

    async def override_get_db():
        yield bdd_db

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://test")

    yield client

    run_async(client.aclose())
    app.dependency_overrides.clear()


@pytest.fixture()
def ctx():
    """Mutable dict shared across Given / When / Then steps in a scenario."""
    return {}


# ===================================================================
# Mock LLM response factories
# ===================================================================


def make_topic_extraction_response(
    topics: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a valid ``TopicExtractionResult`` dict."""
    if topics is None:
        topics = [
            {
                "name": "Go concurrency patterns",
                "description": "Understanding goroutines, channels, and select",
                "category": "current_frontier",
                "evidence_strength": "developing",
                "confidence": 0.8,
                "reasoning": "Journal entry discusses goroutines and channels",
            },
            {
                "name": "Go mutex usage",
                "description": "Using mutex for shared state protection",
                "category": "current_frontier",
                "evidence_strength": "limited",
                "confidence": 0.6,
                "reasoning": "Brief mention of mutex in the entry",
            },
        ]
    return {"topics": topics, "relationships": []}


def make_quiz_generation_response(
    questions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if questions is None:
        questions = [
            {
                "question_text": (
                    "Explain how Go channels enable safe" " communication between goroutines."
                ),
                "question_type": "reinforcement",
                "target_topic": "Go concurrency patterns",
                "difficulty_rationale": "Tests understanding of core concurrency primitives",
            },
            {
                "question_text": (
                    "What are the trade-offs between buffered" " and unbuffered channels in Go?"
                ),
                "question_type": "exploration",
                "target_topic": "Go concurrency patterns",
                "difficulty_rationale": "Explores nuances beyond basic usage",
            },
        ]
    return {"questions": questions}


def make_quiz_evaluation_response(
    evaluations: list[dict[str, Any]] | None = None,
    *,
    question_ids: list[str] | None = None,
) -> dict[str, Any]:
    if evaluations is None:
        qid = (question_ids or ["placeholder"])[0]
        evaluations = [
            {
                "question_id": qid,
                "correctness": "full",
                "depth_assessment": "Demonstrates solid understanding",
                "explanation": "Answer correctly describes goroutines as lightweight threads.",
                "confidence": 0.9,
                "topic_signals": ["Go concurrency patterns"],
            },
        ]
    return {"evaluations": evaluations, "triage_items": []}


def make_reading_generation_response(
    recommendations: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if recommendations is None:
        recommendations = [
            {
                "title": "Effective Go — Concurrency",
                "url": "https://go.dev/doc/effective_go#concurrency",
                "source_domain": "go.dev",
                "description": "Official guide to Go concurrency patterns",
                "recommendation_type": "deep_dive",
                "target_topic": "Go concurrency patterns",
                "rationale": "Strengthens current frontier topic",
            },
            {
                "title": "Go Blog — Pipelines",
                "url": "https://blog.golang.org/pipelines",
                "source_domain": "blog.golang.org",
                "description": "Patterns for concurrent pipelines in Go",
                "recommendation_type": "next_frontier",
                "target_topic": "Go concurrency patterns",
                "rationale": "Extends understanding with practical patterns",
            },
        ]
    return {"recommendations": recommendations}


def make_project_generation_response() -> dict[str, Any]:
    return {
        "title": "Concurrent File Processor",
        "description": "Build a CLI tool that processes files concurrently",
        "readme_content": "# Concurrent File Processor\n\nA Go micro-project.",
        "files": [
            {
                "path": "main.go",
                "content": 'package main\n\nfunc main() {\n\tprintln("hello")\n}\n',
            },
            {
                "path": "processor.go",
                "content": "package main\n\n// Processor stub\n",
            },
        ],
        "tasks": [
            {
                "title": "Implement worker pool",
                "description": "Create a worker pool that processes files",
                "task_type": "feature",
            },
            {
                "title": "Fix race condition",
                "description": "Fix the shared counter race condition",
                "task_type": "bug_fix",
            },
        ],
        "difficulty_level": 3,
    }


def make_project_evaluation_response() -> dict[str, Any]:
    return {
        "code_quality_score": 0.75,
        "task_evaluations": [
            {
                "task_title": "Implement worker pool",
                "completed": True,
                "quality_notes": "Good implementation",
                "score": 0.8,
            },
        ],
        "test_results_summary": "All tests pass",
        "overall_assessment": "Solid submission demonstrating concurrency understanding",
        "confidence": 0.85,
        "difficulty_adjustment": 1,
        "triage_items": [],
    }


# ===================================================================
# Database helper factories (sync wrappers around async ORM operations)
# ===================================================================


def create_journal_entry(
    db: AsyncSession,
    title: str = "Test Entry",
    content: str = "Test content",
    *,
    is_processed: bool = False,
) -> Any:
    """Insert a JournalEntry + current version; return the entry."""
    from backend.app.models.journal import JournalEntry, JournalEntryVersion

    async def _create():
        entry = JournalEntry(title=title, is_processed=is_processed)
        db.add(entry)
        await db.flush()
        version = JournalEntryVersion(
            entry_id=entry.id,
            content=content,
            version_number=1,
            is_current=True,
        )
        db.add(version)
        await db.flush()
        return entry

    return run_async(_create())


def create_onboarding(
    db: AsyncSession,
    go_level: str = "beginner",
) -> Any:
    from backend.app.models.settings import OnboardingState

    async def _create():
        state = OnboardingState(
            completed=True,
            completed_at=datetime.now(UTC),
            self_assessment={
                "primary_languages": ["Python", "Go"],
                "years_experience": 5,
                "primary_domain": "backend",
            },
            go_experience_level=go_level,
            topic_interests={"topics": ["concurrency", "testing"]},
        )
        db.add(state)
        await db.flush()
        return state

    return run_async(_create())


def create_topics(db: AsyncSession) -> list[Any]:
    from backend.app.models.base import EvidenceStrength, TopicCategory
    from backend.app.models.topic import Topic

    async def _create():
        topics = [
            Topic(
                name="Go concurrency patterns",
                description="Goroutines, channels, select",
                category=TopicCategory.CURRENT_FRONTIER,
                evidence_strength=EvidenceStrength.DEVELOPING,
                confidence=0.8,
            ),
            Topic(
                name="Go error handling",
                description="Error wrapping, sentinel errors",
                category=TopicCategory.DEMONSTRATED_STRENGTH,
                evidence_strength=EvidenceStrength.STRONG,
                confidence=0.9,
            ),
        ]
        for t in topics:
            db.add(t)
        await db.flush()
        return topics

    return run_async(_create())


def create_quiz_session(
    db: AsyncSession,
    *,
    status: str = "pending",
    with_answers: bool = False,
) -> Any:
    from backend.app.models.base import QuizSessionStatus
    from backend.app.models.quiz import QuizAnswer, QuizQuestion, QuizSession

    async def _create():
        session = QuizSession(
            status=QuizSessionStatus(status),
            question_count=2,
        )
        db.add(session)
        await db.flush()

        q1 = QuizQuestion(
            session_id=session.id,
            question_text="Explain goroutines.",
            question_type="reinforcement",
            order_index=0,
        )
        q2 = QuizQuestion(
            session_id=session.id,
            question_text="Describe channels in Go.",
            question_type="exploration",
            order_index=1,
        )
        db.add_all([q1, q2])
        await db.flush()

        if with_answers:
            a1 = QuizAnswer(
                question_id=q1.id,
                answer_text="Goroutines are lightweight threads managed by Go runtime",
            )
            a2 = QuizAnswer(
                question_id=q2.id,
                answer_text="Channels are typed conduits for communication between goroutines",
            )
            db.add_all([a1, a2])
            await db.flush()

        return session

    return run_async(_create())


def create_project(
    db: AsyncSession,
    *,
    status: str = "issued",
    with_files: bool = False,
) -> Any:
    from backend.app.models.base import ProjectStatus
    from backend.app.models.project import ProjectTask, WeeklyProject

    async def _create():
        project = WeeklyProject(
            title="Test Project",
            description="A test Go project",
            difficulty_level=3,
            project_path="/tmp/devlogplus_test_project",
            status=ProjectStatus(status),
        )
        db.add(project)
        await db.flush()

        task = ProjectTask(
            project_id=project.id,
            title="Implement feature",
            description="Build a feature",
            task_type="feature",
            order_index=0,
        )
        db.add(task)
        await db.flush()

        if with_files:
            import os
            from pathlib import Path

            os.makedirs(project.project_path, exist_ok=True)
            Path(os.path.join(project.project_path, "main.go")).write_text(
                'package main\n\nfunc main() {\n\tprintln("hello")\n}\n'
            )

        return project

    return run_async(_create())


def create_triage_item(
    db: AsyncSession,
    severity: str = "medium",
    status: str = "pending",
) -> Any:
    from backend.app.models.base import TriageSeverity, TriageSource, TriageStatus
    from backend.app.models.triage import TriageItem

    async def _create():
        item = TriageItem(
            source=TriageSource.PROFILE_UPDATE,
            title=f"Test triage ({severity})",
            description="A test triage item",
            severity=TriageSeverity(severity),
            status=TriageStatus(status),
        )
        db.add(item)
        await db.flush()
        return item

    return run_async(_create())


def create_allowlist_entries(
    db: AsyncSession,
    domains: list[tuple[str, str]] | None = None,
) -> list[Any]:
    from backend.app.models.reading import ReadingAllowlist

    if domains is None:
        domains = [("go.dev", "Go Official"), ("blog.golang.org", "Go Blog")]

    async def _create():
        entries = []
        for domain, name in domains:
            entry = ReadingAllowlist(domain=domain, name=name)
            db.add(entry)
            entries.append(entry)
        await db.flush()
        return entries

    return run_async(_create())


def create_reading_recommendation(
    db: AsyncSession,
    *,
    url: str,
    source_domain: str,
    title: str = "A previous recommendation",
    recommendation_type: str = "deep_dive",
) -> Any:
    """Insert a single ReadingRecommendation row and return it."""
    from datetime import date

    from backend.app.models.base import ReadingRecommendationType
    from backend.app.models.reading import ReadingRecommendation

    async def _create():
        rec = ReadingRecommendation(
            title=title,
            url=url,
            source_domain=source_domain,
            description="seeded for tests",
            recommendation_type=ReadingRecommendationType(recommendation_type),
            batch_date=date.today(),
        )
        db.add(rec)
        await db.flush()
        return rec

    return run_async(_create())


def create_feedback(
    db: AsyncSession,
    *,
    target_type: str,
    target_id: Any,
    reaction: str,
    note: str | None = None,
) -> Any:
    """Insert a Feedback row and return it.

    ``target_type`` and ``reaction`` accept the enum *values*
    (e.g. ``"reading"``, ``"thumbs_up"``).
    """
    from backend.app.models.base import FeedbackReaction, FeedbackTargetType
    from backend.app.models.feedback import Feedback

    async def _create():
        fb = Feedback(
            target_type=FeedbackTargetType(target_type),
            target_id=target_id,
            reaction=FeedbackReaction(reaction),
            note=note,
        )
        db.add(fb)
        await db.flush()
        return fb

    return run_async(_create())
