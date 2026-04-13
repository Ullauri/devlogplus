"""Nightly profile update pipeline.

Processes new journal entries → extracts topics → updates Knowledge Profile.
This is the core pipeline that keeps the user's profile current.

Run via cron nightly or manually via CLI.
"""

import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.base import (
    EvidenceStrength,
    PipelineStatus,
    PipelineType,
    TopicCategory,
    TriageSeverity,
    TriageSource,
)
from backend.app.models.journal import JournalEntry, JournalEntryVersion
from backend.app.models.settings import ProcessingLog
from backend.app.models.topic import Topic
from backend.app.models.triage import TriageItem
from backend.app.prompts import topic_extraction
from backend.app.services import profile as profile_svc
from backend.app.services import triage as triage_svc
from backend.app.services.llm.client import llm_client
from backend.app.services.llm.models import ExtractedTopic, TopicExtractionResult

logger = logging.getLogger(__name__)


async def run_profile_update(db: AsyncSession) -> dict:
    """Execute the full nightly profile update pipeline.

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
    log = ProcessingLog(
        pipeline=PipelineType.PROFILE_UPDATE,
        status=PipelineStatus.STARTED,
    )
    db.add(log)
    await db.flush()

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
        existing_topics_text = (
            "\n".join(
                f"- {t.name} ({t.category.value}, {t.evidence_strength.value}, "
                f"confidence={t.confidence})"
                for t in existing_topics
            )
            or "No existing topics yet."
        )

        # Step 4: Extract topics from each entry
        all_extracted: list[ExtractedTopic] = []
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
            entry.is_processed = True
            entry.processed_at = datetime.now(UTC)

        # Step 5: Upsert topics into the database
        topics_created = 0
        topics_updated = 0
        for et in all_extracted:
            existing = None
            for t in existing_topics:
                if t.name.lower() == et.name.lower():
                    existing = t
                    break

            if existing:
                # Update existing topic with new evidence
                try:
                    existing.evidence_strength = EvidenceStrength(et.evidence_strength)
                    existing.category = TopicCategory(et.category)
                except ValueError:
                    pass
                existing.confidence = max(existing.confidence, et.confidence)
                if et.description:
                    existing.description = et.description
                topics_updated += 1
            else:
                # Create new topic
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
                    topics_created += 1
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

        await db.flush()

        # Step 6: Save profile snapshot
        profile = await profile_svc.get_knowledge_profile(db)
        await profile_svc.create_snapshot(db, profile, trigger="nightly_update")

        # Step 7: Complete processing log
        log.status = PipelineStatus.COMPLETED
        log.completed_at = datetime.now(UTC)
        log.metadata_ = {
            "entries_processed": len(entries),
            "topics_extracted": len(all_extracted),
            "topics_created": topics_created,
            "topics_updated": topics_updated,
        }
        await db.flush()

        summary = {
            "status": "completed",
            "entries_processed": len(entries),
            "topics_extracted": len(all_extracted),
            "topics_created": topics_created,
            "topics_updated": topics_updated,
        }
        logger.info("Profile update complete: %s", summary)
        return summary

    except Exception as e:
        log.status = PipelineStatus.FAILED
        log.error = str(e)
        log.completed_at = datetime.now(UTC)
        await db.flush()
        logger.exception("Profile update pipeline failed")
        raise
