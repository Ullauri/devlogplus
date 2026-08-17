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

from backend.app.config import (
    READING_RECOMMENDATION_COUNT_MAX,
    READING_RECOMMENDATION_COUNT_MIN,
    settings,
)
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
from backend.app.services import onboarding as onboarding_svc
from backend.app.services import profile as profile_svc
from backend.app.services import reading as reading_svc
from backend.app.services.llm.client import llm_client
from backend.app.services.llm.models import GeneratedReading, ReadingGenerationResult

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
    """Build a context-rich feedforward bullet list for the LLM prompt.

    Notes are deduplicated by text before the cap is applied. The UI re-submits
    the note field on every click, so a single complaint lands as three or four
    identical rows; without this, one piece of feedback ate a third of the
    budget and genuinely different steering never reached the prompt at all.
    """
    lines: list[str] = []
    seen_notes: set[str] = set()
    for fb in feedback_items:
        if not fb.note:
            continue
        note_key = " ".join(fb.note.split()).lower()
        if note_key in seen_notes:
            continue
        seen_notes.add(note_key)
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


def _format_liked_directions(
    saved_readings: list[ReadingRecommendation],
    liked_readings: list[ReadingRecommendation],
    max_items: int = 10,
) -> str:
    """Summarise saved and thumbs-up'd readings as positive *directional* signals.

    We surface theme + domain + recommendation_type (not the URL itself
    in this block — the URL is added to the hard avoid list separately so
    the model never re-recommends the exact link).

    Saved items are listed first and labelled: saving is a deliberate act of
    keeping something, where a thumbs-up can be a passing reaction. An item
    that is both is listed once, as saved.
    """
    if not saved_readings and not liked_readings:
        return "None"

    def _recent_first(rows: list[ReadingRecommendation]) -> list[ReadingRecommendation]:
        return sorted(rows, key=lambda r: r.created_at or datetime.min, reverse=True)

    saved_ids = {r.id for r in saved_readings}
    ordered = [(r, "saved") for r in _recent_first(saved_readings)]
    ordered += [(r, "liked") for r in _recent_first(liked_readings) if r.id not in saved_ids]

    lines: list[str] = []
    for r, source in ordered[:max_items]:
        rec_type = r.recommendation_type.value if r.recommendation_type else "?"
        lines.append(f'- [{source}] "{r.title}" — {r.source_domain} ({rec_type})')
    return "\n".join(lines)


def _format_candidate(candidate: reading_svc.Candidate) -> str:
    """Render one pool entry as the single line the model selects from.

    Deliberately terse: a 200-article pool is already the bulk of this prompt,
    and the summary text most feeds carry adds little the title does not while
    multiplying the token cost several times over.
    """
    when = f" ({candidate.published:%Y-%m-%d})" if candidate.published else ""
    return f"[{candidate.index}] {candidate.domain} — {candidate.title}{when}"


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

        # Engagement state — what the user did with past items without ever
        # clicking a thumb. Dismissals count as rejections alongside
        # thumbs-down; saves are the strongest positive available.
        engagement = await reading_svc.get_engagement_signals(db)

        # Gather thumbs-down readings: exclude their URLs, downrank their domains.
        disliked_reading_ids = await feedback_svc.list_disliked_target_ids(
            db, FeedbackTargetType.READING
        )
        disliked_lookup = await _load_reading_lookup(db, disliked_reading_ids)
        disliked_urls = {reading_svc.normalize_url(r.url) for r in disliked_lookup.values()}
        # A dismissal is a rejection the user could not be bothered to
        # thumbs-down, so it carries the same weight for domain downranking.
        # Counted per reading, so an item both dismissed and thumbs-downed
        # does not register twice.
        rejected_readings = {r.id: r for r in disliked_lookup.values()}
        rejected_readings.update({r.id: r for r in engagement.dismissed})
        domain_dislike_counts = Counter(r.source_domain for r in rejected_readings.values())
        downranked_domains = {d for d, n in domain_dislike_counts.items() if n >= 2}

        # Gather thumbs-up readings: positive *directional* signal.
        # We hard-block the exact URLs (no point re-recommending what the user
        # already liked + read) but surface theme/domain/type so the LLM can
        # lean in the same direction with NEW material.
        liked_reading_ids = await feedback_svc.list_liked_target_ids(db, FeedbackTargetType.READING)
        liked_lookup = await _load_reading_lookup(db, liked_reading_ids)
        liked_readings = list(liked_lookup.values())
        liked_urls = {reading_svc.normalize_url(r.url) for r in liked_readings}

        # All URLs ever stored — regardless of feedback status.  A URL the
        # user hasn't rated is still a duplicate if it already appeared in a
        # previous batch; only the title/description would differ, not the
        # content. Using the URL as the canonical identity prevents that.
        all_stored_urls = await reading_svc.get_all_recommendation_urls(db)

        # Combined hard-avoid set: any URL already stored + disliked + liked.
        avoid_urls = all_stored_urls | disliked_urls | liked_urls

        avoid_urls_text = "\n".join(f"- {u}" for u in sorted(avoid_urls)) or "None"
        downrank_lines = [
            f"- {d} ({domain_dislike_counts[d]} rejected)" for d in sorted(downranked_domains)
        ]
        # A domain recommended repeatedly and never once opened is not landing,
        # even though the user never said so explicitly.
        downrank_lines += [
            f"- {d} ({n} recommended, none ever opened)"
            for d, n in sorted(engagement.ignored_domains.items())
            if d not in downranked_domains
        ]
        downrank_text = "\n".join(downrank_lines) or "None"
        # Saved items lead: keeping something is a deliberate act, where a
        # thumbs-up can be a passing reaction.
        liked_directions_text = _format_liked_directions(engagement.saved, liked_readings)

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

        recommendation_count = await onboarding_svc.get_int_setting(
            db,
            "reading_recommendation_count",
            settings.reading_recommendation_count,
            minimum=READING_RECOMMENDATION_COUNT_MIN,
            maximum=READING_RECOMMENDATION_COUNT_MAX,
        )

        # Build the candidate pool: real, currently-published articles read
        # from the allowlisted domains' own feeds. The model selects from this
        # rather than recalling URLs, which it cannot do — see
        # `reading_svc.gather_candidates`.
        candidates: list[reading_svc.Candidate] = []
        if settings.reading_use_feed_candidates:
            candidates = await reading_svc.gather_candidates(
                db,
                allowed_domains=allowed_domains,
                # Nothing already on file, disliked or liked can be chosen, so
                # excluding them here spends the pool on genuinely new material
                # instead of on options the storage loop would drop anyway.
                exclude_urls=avoid_urls,
                per_domain=settings.reading_feed_items_per_domain,
                limit=settings.reading_candidate_pool_size,
                timeout=settings.reading_feed_timeout,
                recheck_days=settings.reading_feed_recheck_days,
            )
        candidates_by_id = {c.index: c for c in candidates}

        if candidates:
            candidate_text = "\n".join(_format_candidate(c) for c in candidates)
            instructions = reading_generation.SELECT_INSTRUCTIONS
            # Every avoided URL was already withheld from the pool, so the model
            # cannot select one. Listing them again buys nothing and the list
            # only grows — it is one line per recommendation ever stored, which
            # would eventually dwarf the pool it is meant to constrain.
            avoid_text_for_prompt = (
                f"{len(avoid_urls)} previously-seen URLs have already been "
                "withheld from the candidate list below."
            )
        else:
            # Every feed failed, or the operator turned sourcing off. Fall back
            # to model recall and let link verification carry the weight.
            logger.warning(
                "No feed candidates available — falling back to model-recalled URLs, "
                "which are frequently invented."
            )
            candidate_text = "None available"
            instructions = reading_generation.RECALL_INSTRUCTIONS
            # In recall mode the model picks the URLs, so it needs the actual list.
            avoid_text_for_prompt = avoid_urls_text

        # Generate via LLM
        prompt = reading_generation.USER_PROMPT_TEMPLATE.format(
            profile_summary=profile_summary,
            allowlist_domains=allowlist_text,
            feedforward_signals=feedforward_text,
            avoid_urls=avoid_text_for_prompt,
            downranked_domains=downrank_text,
            liked_directions=liked_directions_text,
            candidate_articles=candidate_text,
            selection_instructions=instructions.format(recommendation_count=recommendation_count),
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

        # ── Resolve each pick to a concrete article ──────────────────
        # In selection mode the title and URL come from the candidate pool, so
        # the model's only contribution to identity is an integer it either
        # read off the list or did not.
        resolved: list[tuple[GeneratedReading, str, str]] = []
        skipped_unresolved = 0
        for rec in gen_result.recommendations:
            if candidates_by_id:
                candidate = candidates_by_id.get(rec.candidate_id or -1)
                if candidate is None:
                    logger.warning(
                        "Skipping recommendation with unknown candidate_id=%r (pool size %d)",
                        rec.candidate_id,
                        len(candidates_by_id),
                    )
                    skipped_unresolved += 1
                    continue
                resolved.append((rec, candidate.title, candidate.url))
            elif rec.url and rec.title:
                resolved.append((rec, rec.title, rec.url))
            else:
                logger.warning("Skipping recall-mode recommendation with no url/title")
                skipped_unresolved += 1

        # ── Link verification ────────────────────────────────────────
        # Still worth doing in selection mode: a feed can list an article that
        # has since moved or 404s, and the title comparison is now fair — the
        # claimed title is the publisher's own, not the model's paraphrase.
        link_checks: dict[str, reading_svc.LinkCheck] = {}
        if settings.reading_validate_urls:
            link_checks = await reading_svc.check_links(
                [url for _, _, url in resolved],
                timeout=settings.reading_url_validation_timeout,
            )

        # Validate and store
        batch_date = date.today()
        created: list[ReadingRecommendation] = []
        skipped_disliked = 0
        skipped_already_liked = 0
        skipped_duplicate_url = 0
        skipped_duplicate_topic = 0
        skipped_off_allowlist = 0
        skipped_bad_link: list[dict[str, str]] = []
        seen_topics: set[str] = set()

        for rec, rec_title, rec_url in resolved:
            norm_url = reading_svc.normalize_url(rec_url)

            # Hard filter: never re-recommend a URL the user has already
            # reacted to. Thumbs-down → they rejected it; thumbs-up → they
            # already read it, so the value of re-surfacing is zero.
            if norm_url in disliked_urls:
                logger.info("Skipping previously-disliked recommendation: %s", rec_url)
                skipped_disliked += 1
                continue
            if norm_url in liked_urls:
                logger.info("Skipping already-liked recommendation: %s", rec_url)
                skipped_already_liked += 1
                continue

            # Hard filter: skip any URL that already exists in the database,
            # even if the user hasn't reacted to it yet. The link is the same
            # resource regardless of how the LLM labels it.
            if norm_url in all_stored_urls:
                logger.info("Skipping already-recommended URL: %s", rec_url)
                skipped_duplicate_url += 1
                continue

            # Validate the URL's real host against the allowlist. The model's
            # own `source_domain` label is never trusted — it used to satisfy
            # this check on its own, which let any URL through behind a
            # correct-looking label. Candidates were filtered on the way into
            # the pool, so in selection mode this only ever fires on recall.
            matched_domain = reading_svc.allowlist_match(rec_url, allowed_domains)
            if matched_domain is None:
                logger.warning(
                    "Skipping recommendation whose URL is not on the allowlist: %s (labelled %s)",
                    rec_url,
                    rec.source_domain,
                )
                skipped_off_allowlist += 1
                continue

            # Confirm the link is the article it claims to be, not an index
            # page or an unrelated one.
            if settings.reading_validate_urls:
                # A missing entry means the URL was never fetched, which only
                # happens when the check is stubbed out. Absence of evidence is
                # not treated as a failure, matching the prior behaviour.
                check = link_checks.get(rec_url)
                if check is not None:
                    ok, reason = reading_svc.judge_link(
                        rec_title,
                        check,
                        min_title_overlap=settings.reading_min_title_overlap,
                    )
                    if not ok:
                        logger.warning(
                            "Skipping recommendation '%s' (%s): %s",
                            rec_title,
                            reason,
                            rec_url,
                        )
                        skipped_bad_link.append({"url": rec_url, "reason": reason or "unknown"})
                        continue

            # Diversity guard (final gate): refuse a second otherwise-valid rec
            # with the same target_topic in this batch. Prompt asks for distinct
            # topics; this is the belt-and-braces enforcement so a single hot
            # topic can't dominate the list even if the LLM ignores the
            # instruction. Applied AFTER domain + reachability checks so that
            # an invalid candidate doesn't "burn" a topic slot a valid candidate
            # could have used.
            topic_key = (rec.target_topic or "").strip().lower()
            if topic_key and topic_key in seen_topics:
                logger.info(
                    "Skipping duplicate-topic recommendation '%s' (topic=%s)",
                    rec_title,
                    rec.target_topic,
                )
                skipped_duplicate_topic += 1
                continue

            try:
                rec_type = ReadingRecommendationType(rec.recommendation_type)
            except ValueError:
                rec_type = ReadingRecommendationType.DEEP_DIVE

            reading = ReadingRecommendation(
                title=rec_title,
                url=rec_url,
                # The allowlist entry the URL actually belongs to, not the
                # model's label for it. Domain-level dislike counts are derived
                # from this column, so a wrong label mis-attributed rejections.
                source_domain=matched_domain,
                description=rec.description,
                recommendation_type=rec_type,
                batch_date=batch_date,
            )
            db.add(reading)
            created.append(reading)
            if topic_key:
                seen_topics.add(topic_key)

        await db.flush()

        log.status = PipelineStatus.COMPLETED
        log.completed_at = datetime.now(UTC)
        log.metadata_ = {
            "generated": len(gen_result.recommendations),
            "stored": len(created),
            "skipped_disliked": skipped_disliked,
            "skipped_already_liked": skipped_already_liked,
            "skipped_duplicate_url": skipped_duplicate_url,
            "skipped_duplicate_topic": skipped_duplicate_topic,
            "skipped_off_allowlist": skipped_off_allowlist,
            "skipped_bad_link": skipped_bad_link,
            "skipped_unresolved": skipped_unresolved,
            "batch_date": str(batch_date),
            "distinct_topics": len(seen_topics),
            # How the batch was sourced, and how much there was to choose from.
            # A run that stores nothing is ambiguous without this: an empty pool
            # is a feed problem, a full pool is a selection problem.
            "source_mode": "candidates" if candidates_by_id else "recall",
            "candidate_pool_size": len(candidates),
            "candidate_domains": len({c.domain for c in candidates}),
        }
        await db.flush()

        logger.info(
            "Readings generated: %d stored of %d generated (mode=%s, pool=%d)",
            len(created),
            len(gen_result.recommendations),
            "candidates" if candidates_by_id else "recall",
            len(candidates),
        )
        return created

    except Exception as e:
        log.status = PipelineStatus.FAILED
        log.error = str(e)
        log.completed_at = datetime.now(UTC)
        await db.flush()
        logger.exception("Reading generation pipeline failed")
