"""The reading pipeline's selection path, end to end against a real session.

Separate from ``test_reading_candidates.py`` because these need a database;
that module is deliberately pure. Together they cover the two halves of the
fix: building an honest pool, and refusing to let the model's response
reintroduce a URL that was never in it.
"""

from datetime import date
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.config import settings
from backend.app.models.reading import ReadingAllowlist, ReadingRecommendation
from backend.app.models.settings import ProcessingLog
from backend.app.pipelines.reading_pipeline import generate_readings
from backend.app.services.reading import Candidate

pytestmark = pytest.mark.asyncio(loop_scope="session")

POOL = [
    Candidate(
        index=1,
        title="Understanding Raft",
        url="https://example.com/posts/raft",
        domain="example.com",
    ),
    Candidate(
        index=2,
        title="Vector Clocks Explained",
        url="https://example.com/posts/vector-clocks",
        domain="example.com",
    ),
]


async def _seed_allowlist(db: AsyncSession) -> None:
    db.add(ReadingAllowlist(domain="example.com", name="Example"))
    await db.flush()


def _llm_response(recommendations: list[dict]) -> dict:
    return {"recommendations": recommendations}


async def _run(db: AsyncSession, llm_payload: dict, *, pool: list[Candidate] | None = None):
    """Run the pipeline with sourcing and link-checking stubbed out."""
    with (
        patch(
            "backend.app.pipelines.reading_pipeline.llm_client.chat_completion_json",
            new_callable=AsyncMock,
            return_value=llm_payload,
        ) as mock_llm,
        patch(
            "backend.app.pipelines.reading_pipeline.reading_svc.gather_candidates",
            new_callable=AsyncMock,
            return_value=POOL if pool is None else pool,
        ),
        patch(
            "backend.app.pipelines.reading_pipeline.reading_svc.check_links",
            new_callable=AsyncMock,
            return_value={},  # empty → link verification is skipped
        ),
    ):
        created = await generate_readings(db)
    prompt = mock_llm.call_args.kwargs["messages"][1]["content"]
    return created, prompt


async def _latest_log(db: AsyncSession) -> ProcessingLog:
    rows = await db.execute(select(ProcessingLog).order_by(ProcessingLog.started_at.desc()))
    return rows.scalars().first()


async def test_selection_stores_the_pool_title_and_url_not_the_models(
    db_session: AsyncSession, monkeypatch
):
    """The model's title and URL are discarded — this is the whole fix.

    A model that writes a plausible title over a real candidate used to be
    indistinguishable from one that got it right. Now its ``title``/``url`` are
    ignored outright: identity comes from the pool.
    """
    monkeypatch.setattr(settings, "reading_use_feed_candidates", True)
    await _seed_allowlist(db_session)

    created, _ = await _run(
        db_session,
        _llm_response(
            [
                {
                    "candidate_id": 2,
                    # Both wrong on purpose, and both must be ignored.
                    "title": "A Totally Invented Title",
                    "url": "https://example.com/posts/hallucinated",
                    "description": "why this one",
                    "recommendation_type": "deep_dive",
                    "target_topic": "distributed systems",
                    "rationale": "fits the profile",
                }
            ]
        ),
    )

    assert len(created) == 1
    assert created[0].title == "Vector Clocks Explained"
    assert created[0].url == "https://example.com/posts/vector-clocks"
    assert created[0].description == "why this one"


async def test_unknown_candidate_id_is_dropped(db_session: AsyncSession, monkeypatch):
    """An id that was never in the pool is the one hallucination still possible."""
    monkeypatch.setattr(settings, "reading_use_feed_candidates", True)
    await _seed_allowlist(db_session)

    created, _ = await _run(
        db_session,
        _llm_response(
            [
                {
                    "candidate_id": 999,
                    "description": "d",
                    "recommendation_type": "deep_dive",
                    "target_topic": "t",
                    "rationale": "r",
                }
            ]
        ),
    )

    assert created == []
    log = await _latest_log(db_session)
    assert log.metadata_["skipped_unresolved"] == 1


async def test_selection_mode_ignores_a_model_supplied_url(db_session: AsyncSession, monkeypatch):
    """With a pool present, a response carrying only a URL earns nothing.

    This is the regression that matters: the old prompt shape must not quietly
    keep working, because it is exactly the shape that produced the 404s.
    """
    monkeypatch.setattr(settings, "reading_use_feed_candidates", True)
    await _seed_allowlist(db_session)

    created, _ = await _run(
        db_session,
        _llm_response(
            [
                {
                    "title": "Recalled Article",
                    "url": "https://example.com/posts/recalled",
                    "source_domain": "example.com",
                    "description": "d",
                    "recommendation_type": "deep_dive",
                    "target_topic": "t",
                    "rationale": "r",
                }
            ]
        ),
    )

    assert created == []


async def test_candidates_are_rendered_into_the_prompt(db_session: AsyncSession, monkeypatch):
    monkeypatch.setattr(settings, "reading_use_feed_candidates", True)
    await _seed_allowlist(db_session)

    _, prompt = await _run(db_session, _llm_response([]))

    assert "[1] example.com — Understanding Raft" in prompt
    assert "[2] example.com — Vector Clocks Explained" in prompt
    assert "candidate_id" in prompt


async def test_selection_mode_summarises_the_avoid_list_instead_of_listing_it(
    db_session: AsyncSession, monkeypatch
):
    """Avoided URLs are withheld from the pool, so re-listing them is waste.

    The list grows by one line per recommendation ever stored and would
    eventually dwarf the pool it is meant to constrain.
    """
    monkeypatch.setattr(settings, "reading_use_feed_candidates", True)
    await _seed_allowlist(db_session)
    db_session.add(
        ReadingRecommendation(
            title="Already Seen",
            url="https://example.com/posts/already-seen",
            source_domain="example.com",
            description=None,
            recommendation_type="deep_dive",
            batch_date=date(2026, 8, 1),
        )
    )
    await db_session.flush()

    _, prompt = await _run(db_session, _llm_response([]))

    assert "https://example.com/posts/already-seen" not in prompt
    assert "withheld from the candidate list" in prompt


async def test_recall_mode_still_lists_the_avoid_urls(db_session: AsyncSession, monkeypatch):
    """With no pool the model picks URLs itself, so it needs the actual list."""
    monkeypatch.setattr(settings, "reading_use_feed_candidates", True)
    await _seed_allowlist(db_session)
    db_session.add(
        ReadingRecommendation(
            title="Already Seen",
            url="https://example.com/posts/already-seen",
            source_domain="example.com",
            description=None,
            recommendation_type="deep_dive",
            batch_date=date(2026, 8, 1),
        )
    )
    await db_session.flush()

    _, prompt = await _run(db_session, _llm_response([]), pool=[])

    assert "https://example.com/posts/already-seen" in prompt


async def test_empty_pool_falls_back_to_recall_mode(db_session: AsyncSession, monkeypatch):
    """Every feed failing must degrade, not deadlock the queue."""
    monkeypatch.setattr(settings, "reading_use_feed_candidates", True)
    await _seed_allowlist(db_session)

    created, prompt = await _run(
        db_session,
        _llm_response(
            [
                {
                    "title": "Recalled Article",
                    "url": "https://example.com/posts/recalled",
                    "source_domain": "example.com",
                    "description": "d",
                    "recommendation_type": "deep_dive",
                    "target_topic": "t",
                    "rationale": "r",
                }
            ]
        ),
        pool=[],
    )

    assert "None available" in prompt
    assert len(created) == 1
    assert created[0].url == "https://example.com/posts/recalled"
    log = await _latest_log(db_session)
    assert log.metadata_["source_mode"] == "recall"


async def test_run_metadata_records_how_the_batch_was_sourced(
    db_session: AsyncSession, monkeypatch
):
    """A run storing nothing is ambiguous without this.

    An empty pool is a feed problem; a full pool is a selection problem, and
    the ProcessingLog is the only place that difference is visible after the
    fact — which is precisely what made the 8/16 run look like a hang.
    """
    monkeypatch.setattr(settings, "reading_use_feed_candidates", True)
    await _seed_allowlist(db_session)

    await _run(db_session, _llm_response([]))

    log = await _latest_log(db_session)
    assert log.metadata_["source_mode"] == "candidates"
    assert log.metadata_["candidate_pool_size"] == 2
    assert log.metadata_["candidate_domains"] == 1


async def test_existing_urls_are_excluded_from_the_pool_request(
    db_session: AsyncSession, monkeypatch
):
    """Pool slots must not be spent on items the storage loop would drop."""
    monkeypatch.setattr(settings, "reading_use_feed_candidates", True)
    await _seed_allowlist(db_session)
    db_session.add(
        ReadingRecommendation(
            title="Already Seen",
            url="https://example.com/posts/raft",
            source_domain="example.com",
            description=None,
            recommendation_type="deep_dive",
            batch_date=date(2026, 8, 1),
        )
    )
    await db_session.flush()

    with (
        patch(
            "backend.app.pipelines.reading_pipeline.llm_client.chat_completion_json",
            new_callable=AsyncMock,
            return_value=_llm_response([]),
        ),
        patch(
            "backend.app.pipelines.reading_pipeline.reading_svc.gather_candidates",
            new_callable=AsyncMock,
            return_value=[],
        ) as mock_gather,
        patch(
            "backend.app.pipelines.reading_pipeline.reading_svc.check_links",
            new_callable=AsyncMock,
            return_value={},
        ),
    ):
        await generate_readings(db_session)

    excluded = mock_gather.call_args.kwargs["exclude_urls"]
    assert "https://example.com/posts/raft" in excluded
