"""Profile service — Knowledge Profile queries and snapshot management."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.base import TopicCategory
from backend.app.models.settings import ProfileSnapshot
from backend.app.models.topic import Topic
from backend.app.schemas.topic import KnowledgeProfileResponse, TopicResponse


async def get_knowledge_profile(db: AsyncSession) -> KnowledgeProfileResponse:
    """Build the Knowledge Profile view by querying all topics grouped by category."""
    stmt = select(Topic).order_by(Topic.name)
    result = await db.execute(stmt)
    topics = list(result.scalars().all())

    profile = KnowledgeProfileResponse(total_topics=len(topics))

    for topic in topics:
        tr = TopicResponse.model_validate(topic)
        match topic.category:
            case TopicCategory.DEMONSTRATED_STRENGTH:
                profile.strengths.append(tr)
            case TopicCategory.WEAK_SPOT:
                profile.weak_spots.append(tr)
            case TopicCategory.CURRENT_FRONTIER:
                profile.current_frontier.append(tr)
            case TopicCategory.NEXT_FRONTIER:
                profile.next_frontier.append(tr)
            case TopicCategory.RECURRING_THEME:
                profile.recurring_themes.append(tr)
            case TopicCategory.UNRESOLVED:
                profile.unresolved.append(tr)

    # Last updated = most recent topic update
    if topics:
        profile.last_updated = max(t.updated_at for t in topics)

    return profile


async def create_snapshot(
    db: AsyncSession, profile: KnowledgeProfileResponse, trigger: str = "nightly_update"
) -> ProfileSnapshot:
    """Persist a point-in-time snapshot of the Knowledge Profile."""
    snapshot = ProfileSnapshot(
        snapshot_data=profile.model_dump(mode="json"),
        trigger=trigger,
    )
    db.add(snapshot)
    await db.flush()
    return snapshot


async def list_snapshots(
    db: AsyncSession, *, offset: int = 0, limit: int = 20
) -> list[ProfileSnapshot]:
    """List profile snapshots (most recent first)."""
    stmt = (
        select(ProfileSnapshot)
        .order_by(ProfileSnapshot.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())
