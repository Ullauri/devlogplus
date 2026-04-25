"""Seed additional default reading allowlist entries (batch 2).

Adds a second batch of curated, validated trusted domains to the
`reading_allowlist` table. Covers AI research, systems engineering,
security, frontend development, cloud native, and tech journalism.
Idempotent — existing domains are left untouched.

Revision ID: 003
Revises: 002
Create Date: 2026-04-25
"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "003"
down_revision: str | None = "002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (domain, name, description)
DEFAULT_ALLOWLIST: list[tuple[str, str, str]] = [
    # AI Research & Labs
    (
        "openai.com/news",
        "OpenAI News & Research",
        "Official research announcements, model releases, and policy updates from OpenAI.",
    ),
    (
        "anthropic.com/news",
        "Anthropic News",
        "AI safety research findings, Claude updates, and product announcements from Anthropic.",
    ),
    (
        "huggingface.co/blog",
        "Hugging Face Blog",
        "Open-source ML models, datasets, papers, and community projects from Hugging Face.",
    ),
    (
        "deepmind.google/blog",
        "Google DeepMind Blog",
        "Cutting-edge AI research publications and breakthroughs from Google DeepMind.",
    ),
    (
        "pytorch.org/blog",
        "PyTorch Blog",
        "Deep learning framework updates, tutorials, and research from the PyTorch team.",
    ),
    (
        "microsoft.com/en-us/research/blog",
        "Microsoft Research Blog",
        "Research from Microsoft across AI, systems, programming languages, and more.",
    ),
    (
        "projectzero.google",
        "Google Project Zero",
        "Security vulnerability research and zero-day disclosures from Google's elite security team.",
    ),
    # Infrastructure & Systems
    (
        "developer.nvidia.com/blog",
        "NVIDIA Technical Blog",
        "GPU computing, CUDA, AI hardware, and deep learning engineering from NVIDIA.",
    ),
    (
        "databricks.com/blog",
        "Databricks Blog",
        "Data engineering, Apache Spark, Delta Lake, and ML platform insights.",
    ),
    (
        "cockroachlabs.com/blog",
        "Cockroach Labs Blog",
        "Distributed SQL, database internals, and resilient systems engineering.",
    ),
    (
        "p99conf.io/blog",
        "P99 CONF Blog",
        "High-performance systems, low-latency engineering, and infrastructure deep dives.",
    ),
    (
        "lwn.net",
        "LWN.net",
        "In-depth Linux kernel development news and open source ecosystem coverage.",
    ),
    (
        "chipsandcheese.com",
        "Chips and Cheese",
        "Deep technical dives into CPU and GPU microarchitecture and hardware analysis.",
    ),
    # Cloud Native & DevOps
    (
        "cncf.io/blog",
        "CNCF Blog",
        "Cloud native computing foundation updates, case studies, and project news.",
    ),
    (
        "vercel.com/blog",
        "Vercel Blog",
        "Frontend deployment, edge computing, and web performance engineering.",
    ),
    (
        "tailscale.com/blog",
        "Tailscale Blog",
        "Networking, VPN architecture, WireGuard, and zero-trust security.",
    ),
    # Security
    (
        "krebsonsecurity.com",
        "Krebs on Security",
        "Investigative cybersecurity journalism covering breaches, fraud, and threat actors.",
    ),
    (
        "schneier.com",
        "Schneier on Security",
        "Security technology, policy, and cryptography commentary from Bruce Schneier.",
    ),
    (
        "portswigger.net/research",
        "PortSwigger Research",
        "Web application security research, vulnerability techniques, and exploit write-ups.",
    ),
    (
        "snyk.io/blog",
        "Snyk Blog",
        "Developer-focused security, open source vulnerabilities, and secure coding practices.",
    ),
    # Software Engineering & Architecture
    (
        "architecturenotes.co",
        "Architecture Notes",
        "Accessible software architecture patterns and system design explanations.",
    ),
    (
        "infoq.com",
        "InfoQ",
        "Software development news, conference talks, and engineering best practices.",
    ),
    (
        "thenewstack.io",
        "The New Stack",
        "Cloud native, Kubernetes, microservices, and developer ecosystem news.",
    ),
    (
        "builder.io/blog",
        "Builder.io Blog",
        "Visual development, AI-assisted coding, Figma-to-code, and frontend engineering.",
    ),
    # Frontend & Web Development
    (
        "smashingmagazine.com",
        "Smashing Magazine",
        "Web design, CSS, JavaScript, UX, and frontend development articles.",
    ),
    (
        "joshwcomeau.com",
        "Josh W. Comeau",
        "Interactive, in-depth tutorials on CSS, React, and JavaScript fundamentals.",
    ),
    (
        "kentcdodds.com/blog",
        "Kent C. Dodds Blog",
        "Testing, React, JavaScript, and career advice from a prolific open source contributor.",
    ),
    # Tech Journalism & Analysis
    (
        "discord.com/blog",
        "Discord Blog",
        "Engineering deep dives, infrastructure scaling, and product updates from Discord.",
    ),
    (
        "spectrum.ieee.org",
        "IEEE Spectrum",
        "Engineering, technology, and science news from the IEEE.",
    ),
    (
        "stratechery.com",
        "Stratechery",
        "Technology business strategy and analysis by Ben Thompson.",
    ),
    (
        "wired.com/tag/backchannel",
        "WIRED Backchannel",
        "Long-form, in-depth tech journalism and investigative reporting from WIRED.",
    ),
]


def upgrade() -> None:
    bind = op.get_bind()
    allowlist = sa.table(
        "reading_allowlist",
        sa.column("id", sa.dialects.postgresql.UUID(as_uuid=True)),
        sa.column("domain", sa.Text()),
        sa.column("name", sa.Text()),
        sa.column("description", sa.Text()),
        sa.column("is_default", sa.Boolean()),
    )
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
            "DELETE FROM reading_allowlist" " WHERE is_default = true AND domain = ANY(:domains)"
        ),
        {"domains": [d for d, _, _ in DEFAULT_ALLOWLIST]},
    )
