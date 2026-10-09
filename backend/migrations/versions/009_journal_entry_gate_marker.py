"""Add ``gate_skipped`` and ``gate_p_yes`` to ``journal_entries``.

The profile-update pipeline now asks a cheap yes/no classifier (Jev) whether
an entry is worth a topic-extraction call, and marks the ones it is not as
processed without making it. ``is_processed`` alone would hide those entries
behind the same flag as extracted ones, so a later threshold change could not
find them again. ``gate_skipped`` says the entry was processed by being
skipped; ``gate_p_yes`` keeps the probability the decision was made on.

Revision ID: 009
Revises: 008
Create Date: 2026-10-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "009"
down_revision: str | None = "008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "journal_entries",
        sa.Column("gate_skipped", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "journal_entries",
        sa.Column("gate_p_yes", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("journal_entries", "gate_p_yes")
    op.drop_column("journal_entries", "gate_skipped")
