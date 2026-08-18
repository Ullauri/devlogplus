"""Add ``dismissed_at`` to ``processing_logs``.

The Triage page lists failed pipeline runs as things needing attention, but
a failure stays in that list forever — there was no way to say "I have seen
this one". A single-user app that runs its pipelines by hand accumulates
failures faster than it resolves them, so the list only grows and stops
being read at all.

``dismissed_at`` is an acknowledgement, not a delete: the row stays in the
processing log and the Settings run history still shows it, marked as
dismissed. Only the Triage attention list filters on it.

Revision ID: 008
Revises: 007
Create Date: 2026-08-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "008"
down_revision: str | None = "007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "processing_logs",
        sa.Column("dismissed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("processing_logs", "dismissed_at")
