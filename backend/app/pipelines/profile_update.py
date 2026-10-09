"""Profile update pipeline.

Processes new journal entries → extracts topics → updates Knowledge Profile.
This is the core pipeline that keeps the user's profile current.

Runs only when a user asks for it, via ``POST /pipelines/profile-update/run``.
There is no schedule and no CLI entrypoint.
"""

import logging
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.config import settings
from backend.app.models.base import (
    EvidenceStrength,
    PipelineStatus,
    PipelineType,
    TopicCategory,
    TriageSeverity,
    TriageSource,
)
from backend.app.models.journal import JournalEntry, JournalEntryVersion
from backend.app.models.topic import Topic
from backend.app.models.triage import TriageItem
from backend.app.prompts import entry_gate, topic_extraction
from backend.app.services import pipelines as pipelines_svc
from backend.app.services import profile as profile_svc
from backend.app.services import triage as triage_svc
from backend.app.services.llm.client import llm_client
from backend.app.services.llm.decisions import decisions_client
from backend.app.services.llm.models import ExtractedTopic, TopicExtractionResult

logger = logging.getLogger(__name__)


def _format_existing_topics(existing_topics: list[Topic]) -> str:
    return (
        "\n".join(
            f"- {t.name} ({t.category.value}, {t.evidence_strength.value}, "
            f"confidence={t.confidence})"
            for t in existing_topics
        )
        or "No existing topics yet."
    )


@dataclass
class GateCounts:
    """What the entry gate decided across one run."""

    skipped_by_gate: int = 0
    gate_no_opinion: int = 0
    gate_passed: int = 0


async def _gate_skips(entry: JournalEntry, content: str, counts: GateCounts) -> bool:
    """Ask the entry gate about *content*; True when extraction should be skipped.

    Records the probability on the entry. No opinion lets the entry through,
    so the gate can only ever remove calls, never lose an entry to an outage.
    """
    decision = await decisions_client.ask_noul(
        pipeline="entry_gate", state=content, question=entry_gate.QUESTION
    )
    if decision is None:
        counts.gate_no_opinion += 1
        entry.gate_p_yes = None
        return False
    entry.gate_p_yes = decision.p_yes
    if decision.p_yes < settings.llm_entry_gate_threshold:
        counts.skipped_by_gate += 1
        return True
    counts.gate_passed += 1
    return False


async def _extract_topics(
    db: AsyncSession, entries: list[JournalEntry], existing_topics_text: str
) -> tuple[list[ExtractedTopic], GateCounts]:
    """Extract topics from each entry, marking each one it read as processed.

    With the entry gate on, an entry the gate judges trivial is marked
    processed and ``gate_skipped`` without the extraction call.
    """
    all_extracted: list[ExtractedTopic] = []
    counts = GateCounts()
    for entry in entries:
        # Get current version content
        version_stmt = select(JournalEntryVersion).where(
            JournalEntryVersion.entry_id == entry.id,
            JournalEntryVersion.is_current == True,  # noqa: E712
        )
        version_result = await db.execute(version_stmt)
        current_version = version_result.scalar_one_or_none()
        if current_version is None:
            continue

        if settings.llm_entry_gate and await _gate_skips(entry, current_version.content, counts):
            entry.gate_skipped = True
            entry.is_processed = True
            entry.processed_at = datetime.now(UTC)
            continue

        prompt = topic_extraction.USER_PROMPT_TEMPLATE.format(
            content=current_version.content,
            existing_topics=existing_topics_text,
        )

        raw_result = await llm_client.chat_completion_json(
            pipeline="topic_extraction",
            messages=[
                {"role": "system", "content": topic_extraction.SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        )

        extraction = TopicExtractionResult.model_validate(raw_result)
        all_extracted.extend(extraction.topics)

        # Mark entry as processed
        entry.gate_skipped = False
        entry.is_processed = True
        entry.processed_at = datetime.now(UTC)
    return all_extracted, counts


def _find_topic(topics: list[Topic], name: str) -> Topic | None:
    """The first topic whose name matches *name*, case-insensitively."""
    for t in topics:
        if t.name.lower() == name.lower():
            return t
    return None


def _update_topic(existing: Topic, et: ExtractedTopic) -> None:
    """Update an existing topic with new evidence."""
    try:
        existing.evidence_strength = EvidenceStrength(et.evidence_strength)
        existing.category = TopicCategory(et.category)
    except ValueError:
        pass
    existing.confidence = max(existing.confidence, et.confidence)
    if et.description:
        existing.description = et.description


def _create_topic(db: AsyncSession, et: ExtractedTopic, existing_topics: list[Topic]) -> bool:
    """Create a new topic, or a triage item if its classification is invalid.

    Returns True if a topic was created.
    """
    try:
        new_topic = Topic(
            name=et.name,
            description=et.description,
            category=TopicCategory(et.category),
            evidence_strength=EvidenceStrength(et.evidence_strength),
            confidence=et.confidence,
            evidence_summary={"reasoning": et.reasoning},
        )
        db.add(new_topic)
        # Must also join the reconciliation pool: when two entries
        # in the same batch propose the same new topic, the second
        # has to land in the update branch of _upsert_topics — a second insert
        # violates topics_name_key and aborts the whole run.
        existing_topics.append(new_topic)
        return True
    except ValueError:
        logger.warning("Invalid enum value for topic %s — creating triage", et.name)
        triage = TriageItem(
            source=TriageSource.PROFILE_UPDATE,
            title=f"Invalid topic classification: {et.name}",
            description=f"LLM returned invalid classification for topic '{et.name}'",
            context=et.model_dump(),
            severity=TriageSeverity.LOW,
        )
        db.add(triage)
        return False


def _upsert_topics(
    db: AsyncSession, all_extracted: list[ExtractedTopic], existing_topics: list[Topic]
) -> tuple[int, int]:
    """Upsert extracted topics into the database: ``(created, updated)``."""
    topics_created = 0
    topics_updated = 0
    for et in all_extracted:
        existing = _find_topic(existing_topics, et.name)
        if existing:
            _update_topic(existing, et)
            topics_updated += 1
        elif _create_topic(db, et, existing_topics):
            topics_created += 1
    return topics_created, topics_updated


async def run_profile_update(
    db: AsyncSession,
    *,
    run_id: uuid.UUID | None = None,
) -> dict:
    """Execute the full profile update pipeline.

    Args:
        db: Async session used for all reads/writes.
        run_id: Optional pre-generated id for the ``ProcessingLog`` row.
            Manual triggers pass this so the HTTP response can reference the
            run id before the pipeline has even started executing.

    Steps:
    1. Check for blocking triage items
    2. Find unprocessed journal entries
    3. Extract topics from each entry via LLM
    4. Reconcile with existing profile
    5. Create triage items for contradictions/uncertainties
    6. Save profile snapshot
    7. Mark entries as processed

    Returns:
        Summary dict with counts and status.
    """
    # Start processing log
    log = await pipelines_svc.open_run_log(db, PipelineType.PROFILE_UPDATE, run_id)

    try:
        # Step 1: Check for blocking triage
        if await triage_svc.has_blocking_triage(db):
            logger.warning("Blocking triage items exist — skipping profile update")
            log.status = PipelineStatus.FAILED
            log.error = "Blocked by unresolved high/critical triage items"
            log.completed_at = datetime.now(UTC)
            await db.flush()
            return {"status": "blocked", "reason": "unresolved_triage"}

        # Step 2: Find unprocessed entries
        stmt = (
            select(JournalEntry)
            .where(JournalEntry.is_processed == False)  # noqa: E712
            .order_by(JournalEntry.created_at)
        )
        result = await db.execute(stmt)
        entries = list(result.scalars().all())

        if not entries:
            logger.info("No unprocessed entries — skipping profile update")
            log.status = PipelineStatus.COMPLETED
            log.completed_at = datetime.now(UTC)
            log.metadata_ = {"entries_processed": 0}
            await db.flush()
            return {"status": "no_new_entries", "entries_processed": 0}

        # Step 3: Get existing topics for context
        existing_stmt = select(Topic).order_by(Topic.name)
        existing_result = await db.execute(existing_stmt)
        existing_topics = list(existing_result.scalars().all())
        existing_topics_text = _format_existing_topics(existing_topics)

        # Step 4: Extract topics from each entry
        all_extracted, gate_counts = await _extract_topics(db, entries, existing_topics_text)

        # Step 5: Upsert topics into the database
        topics_created, topics_updated = _upsert_topics(db, all_extracted, existing_topics)

        await db.flush()

        # Step 6: Save profile snapshot
        profile = await profile_svc.get_knowledge_profile(db)
        await profile_svc.create_snapshot(db, profile, trigger="profile_update")

        # Step 7: Complete processing log
        log.status = PipelineStatus.COMPLETED
        log.completed_at = datetime.now(UTC)
        log.metadata_ = {
            "entries_processed": len(entries),
            "topics_extracted": len(all_extracted),
            "topics_created": topics_created,
            "topics_updated": topics_updated,
            "entry_gate": settings.llm_entry_gate,
            **asdict(gate_counts),
        }
        await db.flush()

        summary = {
            "status": "completed",
            "entries_processed": len(entries),
            "topics_extracted": len(all_extracted),
            "topics_created": topics_created,
            "topics_updated": topics_updated,
            **asdict(gate_counts),
        }
        logger.info("Profile update complete: %s", summary)
        return summary

    except Exception as e:
        log.status = PipelineStatus.FAILED
        log.error = str(e)
        log.completed_at = datetime.now(UTC)
        await db.flush()
        logger.exception("Profile update pipeline failed")
