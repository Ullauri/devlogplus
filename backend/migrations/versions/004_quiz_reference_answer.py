"""Add reference_answer column to quiz_questions.

Stores an LLM-generated model/expected answer for each quiz question so
the user can compare their submitted answer against a strong reference
after the evaluation pipeline runs.

Nullable because questions generated before this field was introduced
will not have one, and because the LLM may occasionally omit it.

Revision ID: 004
Revises: 003
Create Date: 2026-04-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "004"
down_revision: str | None = "003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "quiz_questions",
        sa.Column("reference_answer", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("quiz_questions", "reference_answer")
