"""Seed default reading allowlist entries.

Populates the `reading_allowlist` table with a curated set of default
trusted domains so the reading-generation pipeline has allowed sources
out of the box. Idempotent — existing domains are left untouched.

Revision ID: 002
Revises: 001
Create Date: 2026-04-19
"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "002"
down_revision: str | None = "001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Mirrors backend/app/services/reading.py::DEFAULT_ALLOWLIST.
# Kept duplicated here intentionally so the migration is self-contained
# and stable against future code refactors.
DEFAULT_ALLOWLIST: list[tuple[str, str, str]] = [
    # Official language / framework / cloud documentation
    ("go.dev", "Go Official", "Go language documentation and blog"),
    ("go.dev/blog", "Go Blog", "Official Go blog"),
    ("docs.python.org", "Python Docs", "Official Python documentation"),
    ("developer.mozilla.org", "MDN", "Mozilla Developer Network"),
    ("docs.aws.amazon.com", "AWS Docs", "Amazon Web Services documentation"),
    ("postgresql.org/docs", "PostgreSQL Docs", "Official PostgreSQL documentation"),
    ("learn.microsoft.com", "Microsoft Learn", "Microsoft technical documentation"),
    ("martinfowler.com", "Martin Fowler", "Software architecture and design"),
    ("thoughtworks.com", "Thoughtworks", "Technology radar and engineering insights"),
    ("pkg.go.dev", "Go Packages", "Go package documentation"),
    ("kubernetes.io/docs", "Kubernetes Docs", "Official Kubernetes documentation"),
    ("redis.io/docs", "Redis Docs", "Official Redis documentation"),
    ("docker.com/blog", "Docker Blog", "Docker engineering blog"),
    ("engineering.fb.com", "Meta Engineering", "Meta engineering blog"),
    ("netflixtechblog.com", "Netflix Tech Blog", "Netflix engineering blog"),
    ("blog.golang.org", "Go Blog (legacy)", "Legacy Go blog URL"),
    # Personal blogs from respected practitioners
    ("joelonsoftware.com", "Joel on Software", "Joel Spolsky on software engineering"),
    ("blog.codinghorror.com", "Coding Horror", "Jeff Atwood on programming"),
    ("danluu.com", "Dan Luu", "Deep dives on performance, hardware, and engineering culture"),
    ("lethain.com", "Irrational Exuberance", "Will Larson on engineering leadership"),
    ("overreacted.io", "Overreacted", "Dan Abramov on React and JavaScript"),
    (
        "blog.pragmaticengineer.com",
        "The Pragmatic Engineer",
        "Gergely Orosz on software engineering practice",
    ),
    ("allthingsdistributed.com", "All Things Distributed", "Werner Vogels on distributed systems"),
    # Company engineering blogs
    ("stackoverflow.blog", "Stack Overflow Blog", "Stack Overflow engineering and community"),
    ("github.blog", "GitHub Blog", "GitHub product and engineering updates"),
    ("stripe.com/blog", "Stripe Blog", "Stripe engineering and product"),
    ("shopify.engineering", "Shopify Engineering", "Shopify engineering blog"),
    ("slack.engineering", "Slack Engineering", "Slack engineering blog"),
    ("eng.uber.com", "Uber Engineering", "Uber engineering blog"),
    ("blog.cloudflare.com", "Cloudflare Blog", "Cloudflare engineering and security"),
    ("fly.io/blog", "Fly.io Blog", "Fly.io engineering and infrastructure"),
    ("jepsen.io", "Jepsen", "Distributed systems correctness analyses"),
    # Research and reference
    ("research.google", "Google Research", "Google Research publications and blog"),
    ("highscalability.com", "High Scalability", "Architecture case studies at scale"),
    ("rust-lang.org", "Rust Lang", "Official Rust language site"),
    ("doc.rust-lang.org", "Rust Docs", "Official Rust documentation"),
    ("typescriptlang.org/docs", "TypeScript Docs", "Official TypeScript documentation"),
    # Learning / tutorials
    ("geeksforgeeks.org", "GeeksforGeeks", "Tutorials, practice problems, and CS fundamentals"),
]


def upgrade() -> None:
    bind = op.get_bind()

    # Reflect a lightweight table handle; avoids importing ORM models
    # (Alembic migrations should not depend on app code).
    allowlist = sa.table(
        "reading_allowlist",
        sa.column("id", sa.dialects.postgresql.UUID(as_uuid=True)),
        sa.column("domain", sa.Text()),
        sa.column("name", sa.Text()),
        sa.column("description", sa.Text()),
        sa.column("is_default", sa.Boolean()),
    )

    # Find which default domains are already present so we only insert missing ones.
    existing = {
        row[0]
        for row in bind.execute(
            sa.text("SELECT domain FROM reading_allowlist WHERE domain = ANY(:domains)"),
            {"domains": [d for d, _, _ in DEFAULT_ALLOWLIST]},
        ).all()
    }

    rows = [
        {
            "id": uuid.uuid4(),
            "domain": domain,
            "name": name,
            "description": description,
            "is_default": True,
        }
        for domain, name, description in DEFAULT_ALLOWLIST
        if domain not in existing
    ]

    if rows:
        op.bulk_insert(allowlist, rows)


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "DELETE FROM reading_allowlist " "WHERE is_default = true AND domain = ANY(:domains)"
        ),
        {"domains": [d for d, _, _ in DEFAULT_ALLOWLIST]},
    )
