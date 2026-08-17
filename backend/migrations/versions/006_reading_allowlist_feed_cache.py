"""Cache each allowlist domain's discovered RSS/Atom feed.

The reading pipeline used to ask the LLM to recall article URLs from memory.
It cannot: 14 of the 19 recommendations rejected between 2026-08-15 and
2026-08-16 were plain HTTP 404s on invented slugs. The pipeline now builds a
pool of *real* articles by reading each allowlisted domain's feed and has the
model select from it.

Feed discovery costs up to a dozen requests per domain, so the result is cached
on the allowlist row. ``feed_checked_at`` is set on every probe, including the
ones that find nothing — that is what stops the ~20 feedless domains from being
re-probed on every run.

Revision ID: 006
Revises: 005
Create Date: 2026-08-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "006"
down_revision: str | None = "005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("reading_allowlist", sa.Column("feed_url", sa.Text(), nullable=True))
    op.add_column(
        "reading_allowlist",
        sa.Column("feed_checked_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("reading_allowlist", "feed_checked_at")
    op.drop_column("reading_allowlist", "feed_url")
