"""Reading service — recommendations and allowlist management."""

import asyncio
import logging
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from html.parser import HTMLParser
from urllib.parse import urlsplit

import httpx
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.functions import count

from backend.app.models.reading import ReadingAllowlist, ReadingRecommendation
from backend.app.schemas.reading import (
    AllowlistEntryCreate,
    AllowlistEntryUpdate,
    ReadingRecommendationUpdate,
)

logger = logging.getLogger(__name__)


def normalize_url(url: str) -> str:
    """Normalize a URL for deduplication.

    Lowercases, drops the fragment, strips a leading ``www.`` and any trailing
    slash. The fragment matters: ``/manage-resources-containers/`` and
    ``/manage-resources-containers/#requests-and-limits`` are the same page,
    and both were once stored as separate recommendations because the original
    implementation compared raw strings.
    """
    parts = urlsplit(url.strip().lower())
    if not parts.scheme:
        # Not a URL we can parse structurally — fall back to string handling.
        return url.strip().lower().split("#")[0].rstrip("/")
    host = (parts.netloc or "").removeprefix("www.")
    rebuilt = f"{parts.scheme}://{host}{parts.path}"
    if parts.query:
        rebuilt = f"{rebuilt}?{parts.query}"
    return rebuilt.rstrip("/")


# ---------------------------------------------------------------------------
# Allowlist matching
# ---------------------------------------------------------------------------
def allowlist_match(url: str, allowed_domains: set[str]) -> str | None:
    """Return the allowlist entry a URL genuinely belongs to, else ``None``.

    Matching is done against the URL's actual host (and path prefix, for
    entries such as ``go.dev/blog``) — never against a model-supplied
    ``source_domain`` field. The pipeline previously accepted a recommendation
    when *either* the claimed ``source_domain`` or the URL matched, which meant
    a correct-looking label admitted any URL at all: ``blog.langchain.dev`` was
    stored under ``thenewstack.io``, and ``docs.anthropic.com`` under
    ``anthropic.com/news``. Neither host is on the allowlist.

    Subdomains do not inherit their parent's entry: ``anthropic.com/news`` does
    not authorise ``docs.anthropic.com``. A ``www.`` prefix is ignored.
    """
    parts = urlsplit(url.strip())
    host = (parts.hostname or "").lower().removeprefix("www.")
    if not host:
        return None
    path = parts.path or "/"

    for entry in allowed_domains:
        candidate = entry.strip().lower().removeprefix("www.").rstrip("/")
        if not candidate:
            continue
        if "/" in candidate:
            entry_host, entry_path = candidate.split("/", 1)
            entry_path = "/" + entry_path
            if host == entry_host and (path == entry_path or path.startswith(entry_path + "/")):
                return entry
        elif host == candidate:
            return entry
    return None


# ---------------------------------------------------------------------------
# Link verification
# ---------------------------------------------------------------------------
# The model that generates these recommendations has no web access — it emits
# URLs from memory across ~70 allowlisted domains. When it does not know a real
# article slug it produces something plausible, and the *shape* of that guess
# determines whether the old reachability-only check caught it:
#
#   a specific-but-invented slug  ->  404  ->  dropped
#   the domain's landing page     ->  200  ->  kept
#
# So the previous check actively selected for landing pages: it filtered out
# wrong-and-specific guesses while waving through wrong-and-generic ones. That
# is the "title says article, link is a site index" failure users reported
# repeatedly through feedforward notes.
#
# Reachability therefore is not enough. We fetch the page and check that it is
# (a) not an index/listing page and (b) actually about what the recommendation
# claims, by comparing the claimed title against the page's own title.
#
# Kept here — rather than in the pipeline layer — because it is a reusable
# piece of "reading" domain logic and is easier to unit-test in isolation.

# Browser-ish UA: some sites (notably martinfowler.com CDN) return 403 for
# bare httpx/<ver> user agents.
_URL_VALIDATION_UA = "Mozilla/5.0 (compatible; DevLogPlus-LinkCheck/1.0; +https://github.com/)"

# Only parse the head of the document — titles live near the top and some of
# these pages are megabytes of prose.
_HTML_PARSE_LIMIT = 200_000

# A final path segment drawn from this set means the URL addresses a listing,
# not an article. These are the exact shapes that kept reaching users:
# research.google/blog/, anthropic.com/news, thoughtworks.com/insights/blog.
_INDEX_SEGMENTS = frozenset(
    {
        "all",
        "archive",
        "archives",
        "article",
        "articles",
        "blog",
        "blogs",
        "categories",
        "category",
        "docs",
        "documentation",
        "feed",
        "home",
        "index",
        "index.html",
        "insights",
        "latest",
        "library",
        "news",
        "post",
        "posts",
        "research",
        "resources",
        "tag",
        "tags",
        "topics",
    }
)

# Dropped before comparing titles: too common to carry meaning, and present in
# both real matches and coincidental ones.
_TITLE_STOPWORDS = frozenset(
    {
        "and",
        "are",
        "article",
        "blog",
        "docs",
        "documentation",
        "for",
        "guide",
        "home",
        "how",
        "index",
        "intro",
        "introduction",
        "news",
        "official",
        "page",
        "part",
        "site",
        "the",
        "their",
        "them",
        "this",
        "using",
        "what",
        "when",
        "why",
        "with",
        "you",
        "your",
    }
)

_TOKEN_SPLIT_RE = re.compile(r"[^a-z0-9]+")

# Calibrated against the 30 recommendations already on file, scored by hand.
# The genuinely-wrong links all sit at or below 0.20 (a docs section titled
# "19.3. Connections and Authentication" sold as "Patterns for Managing
# Database Connections at Scale"); the correct-but-paraphrased ones start at
# 0.29 ("What is connection pooling, and why should you care?" offered as
# "Database Connection Pooling: Best Practices and Common Pitfalls"). 0.25
# sits in that gap. Mirrored by ``Settings.reading_min_title_overlap``; the
# service layer may not import config, so the test suite asserts they agree.
DEFAULT_MIN_TITLE_OVERLAP = 0.25


@dataclass(frozen=True)
class LinkCheck:
    """The observed facts about one fetched URL.

    Deliberately holds *facts*, not a verdict — ``judge_link`` turns these into
    an accept/reject so the judgement can be unit-tested without a network.
    """

    url: str
    reachable: bool
    reason: str | None = None
    final_url: str | None = None
    page_titles: tuple[str, ...] = ()


class _TitleParser(HTMLParser):
    """Pull ``<title>``, ``og:title`` and the first ``<h1>`` out of a document.

    All three are collected because no single one is reliable: some sites give
    every page the same generic ``<title>`` and put the real headline in
    ``og:title``, and JS-rendered pages sometimes carry only ``og:title``.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title: str | None = None
        self.og_title: str | None = None
        self.h1: str | None = None
        self._capturing: str | None = None
        self._buffer: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "meta" and self.og_title is None:
            attr = dict(attrs)
            key = (attr.get("property") or attr.get("name") or "").lower()
            if key in ("og:title", "twitter:title") and attr.get("content"):
                self.og_title = attr["content"]
        elif tag == "title" and self.title is None:
            self._capturing, self._buffer = "title", []
        elif tag == "h1" and self.h1 is None:
            self._capturing, self._buffer = "h1", []

    def handle_endtag(self, tag: str) -> None:
        if self._capturing != tag:
            return
        text = "".join(self._buffer).strip()
        if tag == "title":
            self.title = text or None
        else:
            self.h1 = text or None
        self._capturing, self._buffer = None, []

    def handle_data(self, data: str) -> None:
        if self._capturing:
            self._buffer.append(data)


def extract_titles(html: str) -> tuple[str, ...]:
    """Return the candidate titles found in a document, most specific first."""
    parser = _TitleParser()
    try:
        parser.feed(html[:_HTML_PARSE_LIMIT])
    except Exception:  # noqa: BLE001 — malformed markup must not fail a batch
        logger.debug("HTML title extraction failed", exc_info=True)
    candidates = (parser.og_title, parser.title, parser.h1)
    seen: list[str] = []
    for c in candidates:
        cleaned = re.sub(r"\s+", " ", c).strip() if c else ""
        if cleaned and cleaned not in seen:
            seen.append(cleaned)
    return tuple(seen)


def _path_segments(url: str) -> list[str]:
    return [s for s in urlsplit(url).path.split("/") if s]


def is_index_url(url: str) -> bool:
    """True when the URL addresses a site index or listing rather than an article."""
    segments = _path_segments(url)
    if not segments:
        # Bare domain — https://blog.langchain.dev with an article's title on it.
        return True
    return segments[-1].lower() in _INDEX_SEGMENTS


def redirect_shallowed(requested_url: str, final_url: str) -> bool:
    """True when a deep URL redirected to a shallower one — a soft 404.

    Sites that do not return a real 404 bounce unknown article paths up to a
    section index or the homepage. The response is a 200, so reachability alone
    reads it as success.
    """
    requested = _path_segments(requested_url)
    final = _path_segments(final_url)
    return len(requested) >= 2 and len(final) < len(requested)


def _title_tokens(text: str) -> set[str]:
    return {
        tok
        for tok in _TOKEN_SPLIT_RE.split(text.lower())
        if len(tok) > 2 and tok not in _TITLE_STOPWORDS
    }


def title_overlap(claimed: str, actual: str) -> float:
    """Score how much a claimed title is supported by the page's own, ``0.0..1.0``.

    A genuine match is often lopsided — martinfowler.com/bliki/CQRS.html is
    titled just "CQRS", which covers little of a longer claimed title — so a
    page title *fully contained* in the claim scores 1.0. Otherwise the score
    is the share of the claim the page supports.

    Containment rather than a symmetric ratio, because a symmetric measure is
    fooled by short unrelated titles: "What is Amazon Aurora?" shares one of
    its two tokens with "Aurora Failover: Understanding the Mechanics of High
    Availability" and would score 0.5 on the page's side despite being a
    different page. Requiring the page title to be *entirely* accounted for
    separates the two cases.

    Returns ``1.0`` when either side has no usable tokens — an unjudgeable
    title is not evidence of a mismatch, and the index checks remain the
    primary net.
    """
    claimed_tokens = _title_tokens(claimed)
    actual_tokens = _title_tokens(actual)
    if not claimed_tokens or not actual_tokens:
        return 1.0
    if actual_tokens <= claimed_tokens:
        return 1.0
    return len(claimed_tokens & actual_tokens) / len(claimed_tokens)


def judge_link(
    claimed_title: str,
    check: LinkCheck,
    *,
    min_title_overlap: float = DEFAULT_MIN_TITLE_OVERLAP,
) -> tuple[bool, str | None]:
    """Decide whether a fetched link may be shown, and why not if it may not.

    Pure and network-free so every branch is directly testable.
    """
    if not check.reachable:
        return False, check.reason or "unreachable"

    final_url = check.final_url or check.url
    if is_index_url(final_url):
        return False, f"landing page: {final_url}"
    if redirect_shallowed(check.url, final_url):
        return False, f"redirected to a shallower page: {final_url}"

    if not check.page_titles:
        # Non-HTML (a PDF) or a page we could not parse. Structure already
        # cleared it; refusing here would drop legitimate results.
        return True, None

    best = max(title_overlap(claimed_title, actual) for actual in check.page_titles)
    if best < min_title_overlap:
        return False, f"title mismatch (overlap {best:.2f}): page is {check.page_titles[0]!r}"
    return True, None


async def _fetch_one(
    client: httpx.AsyncClient,
    url: str,
    *,
    timeout: float,  # noqa: ASYNC109 — passed to httpx, not asyncio.timeout
) -> LinkCheck:
    """Fetch a single URL and report what was found. Never raises."""
    headers = {"User-Agent": _URL_VALIDATION_UA}
    try:
        # GET rather than HEAD: the body is required to compare titles, so a
        # HEAD-first probe would only add a round trip.
        resp = await client.get(url, follow_redirects=True, timeout=timeout, headers=headers)
        if not 200 <= resp.status_code < 400:
            return LinkCheck(url, False, f"HTTP {resp.status_code}", str(resp.url))
        titles: tuple[str, ...] = ()
        if "html" in resp.headers.get("content-type", "").lower():
            titles = extract_titles(resp.text)
        return LinkCheck(url, True, None, str(resp.url), titles)
    except httpx.TimeoutException:
        return LinkCheck(url, False, "timeout")
    except httpx.HTTPError as exc:
        return LinkCheck(url, False, f"{type(exc).__name__}: {exc}")


async def check_links(
    urls: list[str],
    *,
    timeout: float = 5.0,  # noqa: ASYNC109 — passed to httpx, not asyncio.timeout
    concurrency: int = 8,
) -> dict[str, LinkCheck]:
    """Concurrently fetch a batch of URLs and report what each one actually is.

    Returns a mapping ``{url: LinkCheck}``. Never raises — network failures
    become ``reachable=False`` entries.
    """
    if not urls:
        return {}

    sem = asyncio.Semaphore(concurrency)
    # Unique list while preserving order so repeats don't get fetched twice.
    unique: list[str] = list(dict.fromkeys(urls))

    async with httpx.AsyncClient() as client:

        async def _bounded(u: str) -> LinkCheck:
            async with sem:
                return await _fetch_one(client, u, timeout=timeout)

        results = await asyncio.gather(*(_bounded(u) for u in unique))

    return {check.url: check for check in results}


# ---------------------------------------------------------------------------
# Reading recommendations
# ---------------------------------------------------------------------------
async def list_recommendations(
    db: AsyncSession,
    *,
    batch_date: date | None = None,
    active_only: bool = False,
    offset: int = 0,
    limit: int = 20,
) -> list[ReadingRecommendation]:
    """List reading recommendations, optionally filtered by batch date.

    When ``active_only`` is ``True`` the result is restricted to the "active
    list" — items the user might still care about: the latest batch plus any
    prior-batch items they explicitly saved, excluding anything dismissed.
    Dismissed items never appear in the active list regardless of batch.
    """
    stmt = select(ReadingRecommendation).order_by(
        ReadingRecommendation.batch_date.desc(),
        ReadingRecommendation.created_at.desc(),
    )
    if batch_date is not None:
        stmt = stmt.where(ReadingRecommendation.batch_date == batch_date)
    if active_only:
        latest = await get_latest_batch_date(db)
        stmt = stmt.where(ReadingRecommendation.dismissed_at.is_(None))
        if latest is not None:
            stmt = stmt.where(
                or_(
                    ReadingRecommendation.batch_date == latest,
                    ReadingRecommendation.saved_at.is_not(None),
                )
            )
    stmt = stmt.offset(offset).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def count_recommendations(
    db: AsyncSession,
    *,
    batch_date: date | None = None,
    active_only: bool = False,
) -> int:
    """Return the total number of reading recommendations matching the filter."""
    stmt = select(count(ReadingRecommendation.id))
    if batch_date is not None:
        stmt = stmt.where(ReadingRecommendation.batch_date == batch_date)
    if active_only:
        latest = await get_latest_batch_date(db)
        stmt = stmt.where(ReadingRecommendation.dismissed_at.is_(None))
        if latest is not None:
            stmt = stmt.where(
                or_(
                    ReadingRecommendation.batch_date == latest,
                    ReadingRecommendation.saved_at.is_not(None),
                )
            )
    result = await db.execute(stmt)
    return int(result.scalar_one())


async def get_latest_batch_date(db: AsyncSession) -> date | None:
    """Return the most recent batch date."""
    stmt = (
        select(ReadingRecommendation.batch_date)
        .order_by(ReadingRecommendation.batch_date.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_all_recommendation_urls(db: AsyncSession) -> set[str]:
    """Return normalized URLs that have ever been recommended.

    Used by the reading-generation pipeline to prevent the same link from
    being surfaced again in a later batch, regardless of whether the user
    has reacted to it.  URLs are normalized via ``normalize_url`` so that
    case differences and trailing slashes don't defeat the check.
    """
    stmt = select(ReadingRecommendation.url)
    result = await db.execute(stmt)
    return {normalize_url(u) for u in result.scalars().all()}


async def get_recommendation(
    db: AsyncSession, recommendation_id: uuid.UUID
) -> ReadingRecommendation | None:
    """Fetch a single recommendation by id."""
    stmt = select(ReadingRecommendation).where(ReadingRecommendation.id == recommendation_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def update_recommendation_state(
    db: AsyncSession,
    recommendation_id: uuid.UUID,
    data: ReadingRecommendationUpdate,
) -> ReadingRecommendation | None:
    """Apply a partial state update (read / saved / dismissed) to a recommendation.

    Semantics:

    * ``True`` stamps the corresponding ``*_at`` column with ``now()``,
      *preserving* any prior value (idempotent — re-marking read does not
      reset the timestamp).
    * ``False`` clears the column back to ``NULL``.
    * ``None`` leaves it untouched.

    Cross-field invariants (applied after explicit updates):

    * Dismissing an item clears ``saved_at`` — dismissed trumps saved.
    * Saving an item clears ``dismissed_at`` — un-dismisses.
    """
    rec = await get_recommendation(db, recommendation_id)
    if rec is None:
        return None

    now = datetime.now(UTC)

    if data.read is True and rec.read_at is None:
        rec.read_at = now
    elif data.read is False:
        rec.read_at = None

    if data.saved is True and rec.saved_at is None:
        rec.saved_at = now
    elif data.saved is False:
        rec.saved_at = None

    if data.dismissed is True and rec.dismissed_at is None:
        rec.dismissed_at = now
    elif data.dismissed is False:
        rec.dismissed_at = None

    # Invariants
    if data.dismissed is True:
        rec.saved_at = None
    if data.saved is True:
        rec.dismissed_at = None

    await db.flush()
    # ``updated_at`` is refreshed server-side via ``onupdate=func.now()``;
    # eagerly reload it so the response schema can access it without
    # triggering lazy IO during Pydantic serialization.
    await db.refresh(rec)
    return rec


# ---------------------------------------------------------------------------
# Allowlist
# ---------------------------------------------------------------------------
async def list_allowlist(db: AsyncSession) -> list[ReadingAllowlist]:
    """Return all allowlist entries."""
    stmt = select(ReadingAllowlist).order_by(ReadingAllowlist.name)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def add_allowlist_entry(db: AsyncSession, data: AllowlistEntryCreate) -> ReadingAllowlist:
    """Add a new domain to the allowlist."""
    entry = ReadingAllowlist(
        domain=data.domain,
        name=data.name,
        description=data.description,
        is_default=False,
    )
    db.add(entry)
    await db.flush()
    return entry


async def update_allowlist_entry(
    db: AsyncSession, entry_id: uuid.UUID, data: AllowlistEntryUpdate
) -> ReadingAllowlist | None:
    """Update an allowlist entry."""
    stmt = select(ReadingAllowlist).where(ReadingAllowlist.id == entry_id)
    result = await db.execute(stmt)
    entry = result.scalar_one_or_none()
    if entry is None:
        return None
    if data.name is not None:
        entry.name = data.name
    if data.description is not None:
        entry.description = data.description
    await db.flush()
    return entry


async def delete_allowlist_entry(db: AsyncSession, entry_id: uuid.UUID) -> bool:
    """Remove a domain from the allowlist."""
    stmt = select(ReadingAllowlist).where(ReadingAllowlist.id == entry_id)
    result = await db.execute(stmt)
    entry = result.scalar_one_or_none()
    if entry is None:
        return False
    await db.delete(entry)
    await db.flush()
    return True


# ---------------------------------------------------------------------------
# Default allowlist seeding
# ---------------------------------------------------------------------------
DEFAULT_ALLOWLIST = [
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
    # Batch 2 — added in migration 005
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
        "Security vulnerability research and zero-day disclosures from Google's elite security team.",  # noqa: E501
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


async def seed_default_allowlist(db: AsyncSession) -> int:
    """Insert default allowlist entries if they don't already exist. Returns count added."""
    existing = await list_allowlist(db)
    existing_domains = {e.domain for e in existing}
    count = 0
    for domain, name, description in DEFAULT_ALLOWLIST:
        if domain not in existing_domains:
            entry = ReadingAllowlist(
                domain=domain, name=name, description=description, is_default=True
            )
            db.add(entry)
            count += 1
    if count:
        await db.flush()
    return count
