"""Weekly reading recommendation pipeline.

Generates curated reading recommendations from trusted (allowlisted) sources,
calibrated to the user's Knowledge Profile and feedforward signals.

Run via cron weekly or manually via CLI.
"""

import logging
from datetime import UTC, date, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.config import settings
from backend.app.models.base import (
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


async def generate_readings(db: AsyncSession) -> list[ReadingRecommendation]:
    """Generate weekly reading recommendations.

    Steps:
    1. Build profile summary
    2. Get allowlist domains
    3. Gather feedforward signals
    4. Call LLM to generate recommendations
    5. Validate URLs against allowlist
    6. Store recommendations
    """
    log = ProcessingLog(
        pipeline=PipelineType.READING_GENERATION,
        status=PipelineStatus.STARTED,
    )
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

        # Feedforward signals
        all_feedback = await feedback_svc.list_all_feedback(db, limit=50)
        feedforward = [f.note for f in all_feedback if f.note]
        feedforward_text = "\n".join(f"- {n}" for n in feedforward[:10]) or "None"

        recommendation_count = settings.reading_recommendation_count

        # Generate via LLM
        prompt = reading_generation.USER_PROMPT_TEMPLATE.format(
            profile_summary=profile_summary,
            allowlist_domains=allowlist_text,
            feedforward_signals=feedforward_text,
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

        # Validate and store
        batch_date = date.today()
        created: list[ReadingRecommendation] = []

        for rec in gen_result.recommendations:
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
