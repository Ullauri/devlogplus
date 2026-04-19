"""Weekly reading recommendation pipeline.

Generates curated reading recommendations from trusted (allowlisted) sources,
calibrated to the user's Knowledge Profile and feedforward signals.

Run via cron weekly or manually via CLI.
"""

import logging
import uuid
from collections import Counter
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.config import settings
from backend.app.models.base import (
    FeedbackTargetType,
    PipelineStatus,
    PipelineType,
    ReadingRecommendationType,
)
from backend.app.models.reading import ReadingRecommendation
from backend.app.models.settings import ProcessingLog
from backend.app.prompts import reading_generation
from backend.app.services import feedback as feedback_svc
from backend.app.services import profile as profile_svc
from backend.app.services import reading as reading_svc
from backend.app.services.llm.client import llm_client
from backend.app.services.llm.models import ReadingGenerationResult

logger = logging.getLogger(__name__)


async def _load_reading_lookup(
    db: AsyncSession, ids: set[uuid.UUID]
) -> dict[uuid.UUID, ReadingRecommendation]:
    """Fetch reading rows by id for context building."""
    if not ids:
        return {}
    stmt = select(ReadingRecommendation).where(ReadingRecommendation.id.in_(ids))
    result = await db.execute(stmt)
    return {r.id: r for r in result.scalars().all()}


def _format_feedforward(
    feedback_items,
    reading_lookup: dict[uuid.UUID, ReadingRecommendation],
    max_items: int = 10,
) -> str:
    """Build a context-rich feedforward bullet list for the LLM prompt."""
    lines: list[str] = []
    for fb in feedback_items:
        if not fb.note:
            continue
        if fb.target_type == FeedbackTargetType.READING:
            reading = reading_lookup.get(fb.target_id)
            if reading is not None:
                descriptor = f'reading "{reading.title}" ({reading.source_domain})'
            else:
                descriptor = "reading (removed)"
            reaction = f", {fb.reaction.value}" if fb.reaction else ""
            lines.append(f"- ({descriptor}{reaction}) {fb.note}")
        else:
            # general / cross-cutting feedforward note
            lines.append(f"- {fb.note}")
        if len(lines) >= max_items:
            break
    return "\n".join(lines) or "None"


async def generate_readings(
    db: AsyncSession,
    *,
    run_id: uuid.UUID | None = None,
) -> list[ReadingRecommendation]:
    """Generate weekly reading recommendations.

    Args:
        db: Async session.
        run_id: Optional pre-generated id for the ``ProcessingLog`` row.

    Steps:
    1. Build profile summary
    2. Get allowlist domains
    3. Gather feedforward signals
    4. Call LLM to generate recommendations
    5. Validate URLs against allowlist
    6. Store recommendations
    """
    log_kwargs: dict = {
        "pipeline": PipelineType.READING_GENERATION,
        "status": PipelineStatus.STARTED,
    }
    if run_id is not None:
        log_kwargs["id"] = run_id
    log = ProcessingLog(**log_kwargs)
    db.add(log)
    await db.flush()

    try:
        # Build context
        profile = await profile_svc.get_knowledge_profile(db)
        profile_summary = profile.model_dump_json(indent=2)

        # Get allowlist
        allowlist = await reading_svc.list_allowlist(db)
        allowlist_text = "\n".join(f"- {e.domain} ({e.name})" for e in allowlist)
        allowed_domains = {e.domain for e in allowlist}

        # Gather thumbs-down readings: exclude their URLs, downrank their domains.
        disliked_reading_ids = await feedback_svc.list_disliked_target_ids(
            db, FeedbackTargetType.READING
        )
        disliked_lookup = await _load_reading_lookup(db, disliked_reading_ids)
        disliked_urls = {r.url for r in disliked_lookup.values()}
        domain_dislike_counts = Counter(r.source_domain for r in disliked_lookup.values())
        downranked_domains = {d for d, n in domain_dislike_counts.items() if n >= 2}

        avoid_urls_text = "\n".join(f"- {u}" for u in sorted(disliked_urls)) or "None"
        downrank_text = (
            "\n".join(
                f"- {d} ({domain_dislike_counts[d]} rejections)" for d in sorted(downranked_domains)
            )
            or "None"
        )

        # Feedforward signals — scoped to readings + general notes,
        # and contextualised with the item they reference.
        relevant_feedback = await feedback_svc.list_feedback_by_target_types(
            db, [FeedbackTargetType.READING], limit=50
        )
        # Also pull in recent cross-cutting notes from other target types that
        # may carry useful steering (e.g. "more backend content").
        other_feedback = await feedback_svc.list_all_feedback(db, limit=50)
        seen_ids = {f.id for f in relevant_feedback}
        for fb in other_feedback:
            if fb.id not in seen_ids and fb.note:
                relevant_feedback.append(fb)
        # Enrich with reading titles where possible
        note_reading_ids = {
            fb.target_id for fb in relevant_feedback if fb.target_type == FeedbackTargetType.READING
        }
        note_reading_lookup = await _load_reading_lookup(db, note_reading_ids)
        feedforward_text = _format_feedforward(relevant_feedback, note_reading_lookup)

        recommendation_count = settings.reading_recommendation_count

        # Generate via LLM
        prompt = reading_generation.USER_PROMPT_TEMPLATE.format(
            profile_summary=profile_summary,
            allowlist_domains=allowlist_text,
            feedforward_signals=feedforward_text,
            avoid_urls=avoid_urls_text,
            downranked_domains=downrank_text,
            recommendation_count=recommendation_count,
        )

        raw_result = await llm_client.chat_completion_json(
            pipeline="reading_generation",
            messages=[
                {"role": "system", "content": reading_generation.SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        )

        gen_result = ReadingGenerationResult.model_validate(raw_result)

        # ── URL reachability validation ──────────────────────────────
        # The LLM sometimes hallucinates plausible URLs that 404 (seen most
        # often on martinfowler.com and thoughtworks.com article slugs).
        # Before persisting, probe each URL and drop the dead ones.
        url_status: dict[str, tuple[bool, str | None]] = {}
        if settings.reading_validate_urls:
            candidate_urls = [rec.url for rec in gen_result.recommendations]
            url_status = await reading_svc.validate_urls(
                candidate_urls,
                timeout=settings.reading_url_validation_timeout,
            )

        # Validate and store
        batch_date = date.today()
        created: list[ReadingRecommendation] = []
        skipped_disliked = 0
        skipped_unreachable: list[dict[str, str]] = []

        for rec in gen_result.recommendations:
            # Hard filter: never re-recommend a URL the user has already
            # thumbs-down'd, even if the LLM proposes it.
            if rec.url in disliked_urls:
                logger.info("Skipping previously-disliked recommendation: %s", rec.url)
                skipped_disliked += 1
                continue

            # Validate domain is on allowlist
            domain_ok = any(
                rec.source_domain == d or rec.url.startswith(f"https://{d}")
                for d in allowed_domains
            )
            if not domain_ok:
                logger.warning(
                    "Skipping recommendation from non-allowed domain: %s",
                    rec.source_domain,
                )
                continue

            # Validate URL actually resolves
            if settings.reading_validate_urls:
                reachable, reason = url_status.get(rec.url, (True, None))
                if not reachable:
                    logger.warning(
                        "Skipping unreachable recommendation (%s): %s",
                        reason,
                        rec.url,
                    )
                    skipped_unreachable.append({"url": rec.url, "reason": reason or "unknown"})
                    continue

            try:
                rec_type = ReadingRecommendationType(rec.recommendation_type)
            except ValueError:
                rec_type = ReadingRecommendationType.DEEP_DIVE

            reading = ReadingRecommendation(
                title=rec.title,
                url=rec.url,
                source_domain=rec.source_domain,
                description=rec.description,
                recommendation_type=rec_type,
                batch_date=batch_date,
            )
            db.add(reading)
            created.append(reading)

        await db.flush()

        log.status = PipelineStatus.COMPLETED
        log.completed_at = datetime.now(UTC)
        log.metadata_ = {
            "generated": len(gen_result.recommendations),
            "stored": len(created),
            "skipped_disliked": skipped_disliked,
            "skipped_unreachable": skipped_unreachable,
            "batch_date": str(batch_date),
        }
        await db.flush()

        logger.info(
            "Readings generated: %d stored of %d generated",
            len(created),
            len(gen_result.recommendations),
        )
        return created

    except Exception as e:
        log.status = PipelineStatus.FAILED
        log.error = str(e)
        log.completed_at = datetime.now(UTC)
        await db.flush()
        raise
