"""Rename the ``nightly_update`` snapshot trigger to ``profile_update``.

Nothing in DevLog+ runs on a schedule — the profile pipeline runs when the
user presses a button — so a snapshot labelled ``nightly_update`` names a
cron job that never existed. The value is descriptive metadata: it is
written by ``profile_update``, exported by the transfer bundle and shown
through the snapshot API, and no code branches on it. So the rename is a
straight relabel of history plus a new column default.

Revision ID: 007
Revises: 006
Create Date: 2026-08-16
"""

from collections.abc import Sequence

from alembic import op

revision: str = "007"
down_revision: str | None = "006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("profile_snapshots", "trigger", server_default="profile_update")
    op.execute(
        "UPDATE profile_snapshots SET trigger = 'profile_update' "
        "WHERE trigger = 'nightly_update'"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE profile_snapshots SET trigger = 'nightly_update' "
        "WHERE trigger = 'profile_update'"
    )
    op.alter_column("profile_snapshots", "trigger", server_default="nightly_update")
