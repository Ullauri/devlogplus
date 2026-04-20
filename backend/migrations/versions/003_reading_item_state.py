"""Add per-item user state to reading_recommendations.

Adds three nullable ``timestamptz`` columns — ``read_at``, ``saved_at``,
``dismissed_at`` — so users can track engagement with individual reading
recommendations across batches (mark read, save for later, dismiss).

The active recommendations view becomes:
``dismissed_at IS NULL AND (batch_date = latest_batch OR saved_at IS NOT NULL)``
letting unread/saved items persist beyond their originating batch.

Revision ID: 003
Revises: 002
Create Date: 2026-04-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "003"
down_revision: str | None = "002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "reading_recommendations",
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "reading_recommendations",
        sa.Column("saved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "reading_recommendations",
        sa.Column("dismissed_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Partial indexes that speed up the "active list" query — skip rows that
    # don't carry the flag at all (overwhelmingly the common case).
    op.create_index(
        "ix_reading_recommendations_saved_at",
        "reading_recommendations",
        ["saved_at"],
        postgresql_where=sa.text("saved_at IS NOT NULL"),
    )
    op.create_index(
        "ix_reading_recommendations_dismissed_at",
        "reading_recommendations",
        ["dismissed_at"],
        postgresql_where=sa.text("dismissed_at IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_reading_recommendations_dismissed_at", "reading_recommendations")
    op.drop_index("ix_reading_recommendations_saved_at", "reading_recommendations")
    op.drop_column("reading_recommendations", "dismissed_at")
    op.drop_column("reading_recommendations", "saved_at")
    op.drop_column("reading_recommendations", "read_at")
