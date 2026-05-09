"""Tests for the data transfer (export / import) API endpoints."""

import io
import json
import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.base import (
    EvidenceStrength,
    QuizQuestionType,
    QuizSessionStatus,
    TopicCategory,
)
from backend.app.models.journal import JournalEntry, JournalEntryVersion
from backend.app.models.quiz import QuizQuestion, QuizSession
from backend.app.models.settings import OnboardingState, UserSettings
from backend.app.models.topic import Topic

pytestmark = pytest.mark.asyncio(loop_scope="session")


# ---------------------------------------------------------------------------
# Helpers — seed data for a realistic round-trip
# ---------------------------------------------------------------------------
async def _seed_journal(db: AsyncSession) -> JournalEntry:
    entry = JournalEntry(title="Learned Go interfaces")
    db.add(entry)
    await db.flush()

    version = JournalEntryVersion(
        entry_id=entry.id,
        content="Today I learned about Go interfaces and how they differ from Java.",
        version_number=1,
        is_current=True,
    )
    db.add(version)
    await db.commit()
    await db.refresh(entry)
    return entry


async def _seed_topic(db: AsyncSession, name: str = "Go interfaces") -> Topic:
    topic = Topic(
        name=name,
        description="Implicit interface satisfaction in Go",
        category=TopicCategory.CURRENT_FRONTIER,
        evidence_strength=EvidenceStrength.DEVELOPING,
        confidence=0.7,
    )
    db.add(topic)
    await db.commit()
    await db.refresh(topic)
    return topic


async def _seed_quiz(db: AsyncSession, *, num_questions: int = 2) -> QuizSession:
    session = QuizSession(status=QuizSessionStatus.PENDING, question_count=num_questions)
    db.add(session)
    await db.flush()
    for i in range(num_questions):
        db.add(
            QuizQuestion(
                session_id=session.id,
                question_text=f"What is concept {i + 1}?",
                question_type=QuizQuestionType.REINFORCEMENT,
                order_index=i,
            )
        )
    await db.commit()
    await db.refresh(session)
    return session


async def _seed_settings(db: AsyncSession) -> UserSettings:
    settings = UserSettings(key="quiz_question_count", value={"value": 15})
    db.add(settings)
    await db.commit()
    await db.refresh(settings)
    return settings


async def _seed_onboarding(db: AsyncSession) -> OnboardingState:
    state = OnboardingState(
        completed=True,
        completed_at=datetime.now(UTC),
        self_assessment={"go": "intermediate"},
        go_experience_level="intermediate",
    )
    db.add(state)
    await db.commit()
    await db.refresh(state)
    return state


def _upload_file(data: dict | bytes, filename: str = "export.json"):
    """Create a (filename, file-like, content-type) tuple for httpx multipart."""
    raw = json.dumps(data).encode() if isinstance(data, dict) else data
    return ("file", (filename, io.BytesIO(raw), "application/json"))


# ---------------------------------------------------------------------------
# Export — empty DB
# ---------------------------------------------------------------------------
async def test_export_empty_db(client: AsyncClient):
    """Exporting an empty database returns a valid bundle with zero rows."""
    resp = await client.get("/api/v1/transfer/export")
    assert resp.status_code == 200
    data = resp.json()
    assert data["format_version"] == 1
    assert data["app_version"] == "0.1.0"
    assert data["journal_entries"] == []
    assert data["topics"] == []
    assert data["quiz_sessions"] == []


# ---------------------------------------------------------------------------
# Export metadata
# ---------------------------------------------------------------------------
async def test_export_metadata_empty(client: AsyncClient):
    """Metadata endpoint on empty DB returns all-zero counts."""
    resp = await client.get("/api/v1/transfer/export/metadata")
    assert resp.status_code == 200
    data = resp.json()
    assert data["format_version"] == 1
    assert all(v == 0 for v in data["table_counts"].values())


async def test_export_metadata_with_data(client: AsyncClient, db_session: AsyncSession):
    """Metadata reflects actual row counts after seeding."""
    await _seed_journal(db_session)
    await _seed_topic(db_session)

    resp = await client.get("/api/v1/transfer/export/metadata")
    assert resp.status_code == 200
    counts = resp.json()["table_counts"]
    assert counts["journal_entries"] == 1
    assert counts["journal_entry_versions"] == 1
    assert counts["topics"] == 1


# ---------------------------------------------------------------------------
# Export — populated DB
# ---------------------------------------------------------------------------
async def test_export_with_data(client: AsyncClient, db_session: AsyncSession):
    """Export includes all seeded rows with correct field shapes."""
    entry = await _seed_journal(db_session)
    topic = await _seed_topic(db_session)
    quiz = await _seed_quiz(db_session)

    resp = await client.get("/api/v1/transfer/export")
    assert resp.status_code == 200
    data = resp.json()

    assert len(data["journal_entries"]) == 1
    assert data["journal_entries"][0]["id"] == str(entry.id)
    assert data["journal_entries"][0]["title"] == "Learned Go interfaces"

    assert len(data["journal_entry_versions"]) == 1

    assert len(data["topics"]) == 1
    assert data["topics"][0]["name"] == topic.name

    assert len(data["quiz_sessions"]) == 1
    assert data["quiz_sessions"][0]["id"] == str(quiz.id)
    assert len(data["quiz_questions"]) == 2


# ---------------------------------------------------------------------------
# Round-trip: export → import into empty DB
# ---------------------------------------------------------------------------
async def test_round_trip_export_import(client: AsyncClient, db_session: AsyncSession):
    """Data exported from one DB can be imported into a fresh one identically."""
    # 1. Seed some data
    entry = await _seed_journal(db_session)
    topic = await _seed_topic(db_session)
    quiz = await _seed_quiz(db_session)
    settings = await _seed_settings(db_session)
    onboarding = await _seed_onboarding(db_session)

    # 2. Export
    export_resp = await client.get("/api/v1/transfer/export")
    assert export_resp.status_code == 200
    bundle = export_resp.json()

    # Sanity-check the export
    assert len(bundle["journal_entries"]) == 1
    assert len(bundle["topics"]) == 1
    assert len(bundle["quiz_sessions"]) == 1
    assert len(bundle["user_settings"]) == 1
    assert len(bundle["onboarding_state"]) == 1

    # 3. Import (into the same DB — needs confirm_overwrite)
    import_resp = await client.post(
        "/api/v1/transfer/import?confirm_overwrite=true",
        files=[_upload_file(bundle)],
    )
    assert import_resp.status_code == 200
    result = import_resp.json()
    assert result["counts"]["journal_entries"] == 1
    assert result["counts"]["topics"] == 1
    assert result["counts"]["quiz_sessions"] == 1
    assert result["counts"]["quiz_questions"] == 2
    assert result["counts"]["user_settings"] == 1
    assert result["counts"]["onboarding_state"] == 1

    # 4. Verify the data survived the round-trip
    verify_export = await client.get("/api/v1/transfer/export")
    verify = verify_export.json()
    assert verify["journal_entries"][0]["id"] == str(entry.id)
    assert verify["journal_entries"][0]["title"] == "Learned Go interfaces"
    assert verify["topics"][0]["name"] == topic.name
    assert verify["quiz_sessions"][0]["id"] == str(quiz.id)
    assert verify["user_settings"][0]["key"] == settings.key
    assert verify["onboarding_state"][0]["id"] == str(onboarding.id)

    # 5. Verify data is accessible via the normal API too
    journal_resp = await client.get("/api/v1/journal/entries")
    assert journal_resp.status_code == 200
    journal_body = journal_resp.json()
    assert len(journal_body["items"]) == 1
    assert journal_body["items"][0]["id"] == str(entry.id)


# ---------------------------------------------------------------------------
# Import into empty DB (no confirm_overwrite needed)
# ---------------------------------------------------------------------------
async def test_import_into_empty_db(client: AsyncClient):
    """Importing into an empty database should succeed without confirm_overwrite."""
    bundle = {
        "format_version": 1,
        "exported_at": datetime.now(UTC).isoformat(),
        "app_version": "0.1.0",
        "journal_entries": [
            {
                "id": str(uuid.uuid4()),
                "title": "Fresh entry",
                "is_processed": False,
                "processed_at": None,
                "created_at": datetime.now(UTC).isoformat(),
                "updated_at": datetime.now(UTC).isoformat(),
            }
        ],
    }
    resp = await client.post(
        "/api/v1/transfer/import",
        files=[_upload_file(bundle)],
    )
    assert resp.status_code == 200
    assert resp.json()["counts"]["journal_entries"] == 1


# ---------------------------------------------------------------------------
# Overwrite guard — 409 Conflict
# ---------------------------------------------------------------------------
async def test_import_rejects_overwrite_without_flag(client: AsyncClient, db_session: AsyncSession):
    """Importing into a populated DB without confirm_overwrite returns 409."""
    await _seed_journal(db_session)

    bundle = {
        "format_version": 1,
        "exported_at": datetime.now(UTC).isoformat(),
        "app_version": "0.1.0",
        "journal_entries": [],
    }
    resp = await client.post(
        "/api/v1/transfer/import",
        files=[_upload_file(bundle)],
    )
    assert resp.status_code == 409
    assert "already contains data" in resp.json()["detail"]


async def test_import_allows_overwrite_with_flag(client: AsyncClient, db_session: AsyncSession):
    """Importing into a populated DB with confirm_overwrite=true succeeds."""
    await _seed_journal(db_session)

    bundle = {
        "format_version": 1,
        "exported_at": datetime.now(UTC).isoformat(),
        "app_version": "0.1.0",
        "journal_entries": [],
    }
    resp = await client.post(
        "/api/v1/transfer/import?confirm_overwrite=true",
        files=[_upload_file(bundle)],
    )
    assert resp.status_code == 200
    # The old journal entry should be gone now
    assert resp.json()["counts"]["journal_entries"] == 0

    journal_resp = await client.get("/api/v1/journal/entries")
    assert len(journal_resp.json()["items"]) == 0


# ---------------------------------------------------------------------------
# Import validation errors
# ---------------------------------------------------------------------------
async def test_import_empty_file(client: AsyncClient):
    """Uploading an empty file returns 400."""
    resp = await client.post(
        "/api/v1/transfer/import",
        files=[("file", ("empty.json", io.BytesIO(b""), "application/json"))],
    )
    assert resp.status_code == 400
    assert "empty" in resp.json()["detail"].lower()


async def test_import_invalid_json(client: AsyncClient):
    """Uploading invalid JSON returns 422."""
    resp = await client.post(
        "/api/v1/transfer/import",
        files=[_upload_file(b"this is not json")],
    )
    assert resp.status_code == 422


async def test_import_missing_required_fields(client: AsyncClient):
    """A JSON object missing required bundle fields returns 422."""
    resp = await client.post(
        "/api/v1/transfer/import",
        files=[_upload_file({"some_random_key": 123})],
    )
    assert resp.status_code == 422


async def test_import_unsupported_format_version(client: AsyncClient):
    """A bundle with an unsupported format_version returns 422."""
    bundle = {
        "format_version": 999,
        "exported_at": datetime.now(UTC).isoformat(),
        "app_version": "99.0.0",
    }
    resp = await client.post(
        "/api/v1/transfer/import",
        files=[_upload_file(bundle)],
    )
    assert resp.status_code == 422
    assert "format_version" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# UUID preservation
# ---------------------------------------------------------------------------
async def test_import_preserves_uuids(client: AsyncClient):
    """Imported rows keep the exact UUIDs from the export bundle."""
    entry_id = str(uuid.uuid4())
    topic_id = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()

    bundle = {
        "format_version": 1,
        "exported_at": now,
        "app_version": "0.1.0",
        "journal_entries": [
            {
                "id": entry_id,
                "title": "UUID test",
                "is_processed": False,
                "processed_at": None,
                "created_at": now,
                "updated_at": now,
            }
        ],
        "journal_entry_versions": [
            {
                "id": str(uuid.uuid4()),
                "entry_id": entry_id,
                "content": "UUID check content",
                "version_number": 1,
                "is_current": True,
                "created_at": now,
            }
        ],
        "topics": [
            {
                "id": topic_id,
                "name": "UUID topic",
                "description": None,
                "category": "current_frontier",
                "evidence_strength": "limited",
                "confidence": 0.5,
                "evidence_summary": None,
                "parent_topic_id": None,
                "created_at": now,
                "updated_at": now,
            }
        ],
    }
    resp = await client.post(
        "/api/v1/transfer/import",
        files=[_upload_file(bundle)],
    )
    assert resp.status_code == 200

    # Verify UUIDs are preserved via the normal API
    entry_resp = await client.get(f"/api/v1/journal/entries/{entry_id}")
    assert entry_resp.status_code == 200
    assert entry_resp.json()["id"] == entry_id

    profile_resp = await client.get("/api/v1/profile")
    assert profile_resp.status_code == 200


# ---------------------------------------------------------------------------
# Import replaces (not merges) data
# ---------------------------------------------------------------------------
async def test_import_replaces_not_merges(client: AsyncClient, db_session: AsyncSession):
    """Import clears old data — original entries should be gone after import."""
    # Seed an entry directly
    original = await _seed_journal(db_session)
    original_id = str(original.id)

    # Import a bundle with a DIFFERENT entry
    new_id = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()
    bundle = {
        "format_version": 1,
        "exported_at": now,
        "app_version": "0.1.0",
        "journal_entries": [
            {
                "id": new_id,
                "title": "Replacement entry",
                "is_processed": False,
                "processed_at": None,
                "created_at": now,
                "updated_at": now,
            }
        ],
        "journal_entry_versions": [
            {
                "id": str(uuid.uuid4()),
                "entry_id": new_id,
                "content": "Replacement content",
                "version_number": 1,
                "is_current": True,
                "created_at": now,
            }
        ],
    }
    resp = await client.post(
        "/api/v1/transfer/import?confirm_overwrite=true",
        files=[_upload_file(bundle)],
    )
    assert resp.status_code == 200

    # The original entry should be gone
    old_resp = await client.get(f"/api/v1/journal/entries/{original_id}")
    assert old_resp.status_code == 404

    # Only the new entry should exist
    list_resp = await client.get("/api/v1/journal/entries")
    entries = list_resp.json()["items"]
    assert len(entries) == 1
    assert entries[0]["id"] == new_id


# ---------------------------------------------------------------------------
# Topic self-referential parent_topic_id
# ---------------------------------------------------------------------------
async def test_import_topic_with_parent(client: AsyncClient):
    """Topics with parent_topic_id referencing another imported topic work."""
    parent_id = str(uuid.uuid4())
    child_id = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()

    bundle = {
        "format_version": 1,
        "exported_at": now,
        "app_version": "0.1.0",
        "topics": [
            {
                "id": parent_id,
                "name": "Parent topic",
                "description": "I am the parent",
                "category": "demonstrated_strength",
                "evidence_strength": "strong",
                "confidence": 0.9,
                "evidence_summary": None,
                "parent_topic_id": None,
                "created_at": now,
                "updated_at": now,
            },
            {
                "id": child_id,
                "name": "Child topic",
                "description": "I am the child",
                "category": "current_frontier",
                "evidence_strength": "limited",
                "confidence": 0.4,
                "evidence_summary": None,
                "parent_topic_id": parent_id,
                "created_at": now,
                "updated_at": now,
            },
        ],
    }
    resp = await client.post(
        "/api/v1/transfer/import",
        files=[_upload_file(bundle)],
    )
    assert resp.status_code == 200
    assert resp.json()["counts"]["topics"] == 2

    # Verify both topics exist
    profile_resp = await client.get("/api/v1/profile")
    assert profile_resp.status_code == 200
    assert profile_resp.json()["total_topics"] == 2


# ---------------------------------------------------------------------------
# Suggestion fixes
# ---------------------------------------------------------------------------


async def test_export_metadata_uses_count_queries_not_full_export(
    client: AsyncClient,
    db_session: AsyncSession,
):
    """GET /export/metadata must return correct counts without loading all rows.

    The fix replaces the full export_all() call with per-table COUNT(*) queries.
    We verify correctness here; the absence of a full row-load is enforced by
    checking that export_all is not invoked.
    """
    from unittest.mock import AsyncMock, patch

    await _seed_journal(db_session)
    await _seed_topic(db_session)

    # export_all must NOT be called — metadata uses COUNT queries only
    with patch(
        "backend.app.routers.transfer.transfer_service.export_all",
        new=AsyncMock(side_effect=AssertionError("export_all must not be called for metadata")),
    ):
        resp = await client.get("/api/v1/transfer/export/metadata")

    assert resp.status_code == 200
    data = resp.json()
    assert data["table_counts"]["journal_entries"] >= 1
    assert data["table_counts"]["topics"] >= 1


async def test_to_model_logs_dropped_unknown_keys():
    """_to_model must log at DEBUG level when import data contains unknown keys."""
    from unittest.mock import patch

    from backend.app.models.journal import JournalEntry
    from backend.app.services.transfer import _to_model

    entry_id = uuid.uuid4()
    data = {
        "id": str(entry_id),
        "title": "Test entry",
        "is_processed": False,
        "unknown_future_column": "some_value",
        "another_unknown": 42,
    }

    with patch("backend.app.services.transfer.logger") as mock_logger:
        _to_model(JournalEntry, data)

    mock_logger.debug.assert_called_once()
    call_args = str(mock_logger.debug.call_args)
    assert "unknown_future_column" in call_args or "another_unknown" in call_args
