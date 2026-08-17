"""Tests for feed-sourced reading candidates.

The reading pipeline used to ask the LLM to recall article URLs, which it
cannot do — 14 of 19 rejected recommendations over 2026-08-15/16 were plain
404s on invented slugs. It now selects from a pool built out of the allowlisted
domains' own feeds.

Everything here is pure and network-free: parsing a feed and choosing what goes
in the pool are separated from fetching precisely so they can be tested this
way. Live discovery against the real 69 domains is not something a test suite
should depend on.
"""

import dataclasses
from datetime import UTC, datetime

import pytest

from backend.app.services import reading as reading_svc
from backend.app.services.reading import Candidate, FeedItem

RSS = """<?xml version="1.0"?>
<rss version="2.0">
  <channel>
    <title>Example Blog</title>
    <item>
      <title>Understanding Raft</title>
      <link>https://example.com/posts/raft</link>
      <pubDate>Mon, 10 Aug 2026 09:00:00 GMT</pubDate>
      <description>A walk through the consensus algorithm.</description>
    </item>
    <item>
      <title>Vector Clocks</title>
      <link>https://example.com/posts/vector-clocks</link>
      <pubDate>Tue, 04 Aug 2026 12:30:00 +0000</pubDate>
    </item>
  </channel>
</rss>
"""

ATOM = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Example Atom</title>
  <entry>
    <title>Effective Go</title>
    <link rel="alternate" href="https://go.dev/doc/effective_go"/>
    <link rel="replies" href="https://go.dev/comments/1"/>
    <updated>2026-08-12T10:00:00Z</updated>
    <summary>How to write idiomatic Go.</summary>
  </entry>
</feed>
"""


# ---------------------------------------------------------------------------
# Feed parsing
# ---------------------------------------------------------------------------
def test_parse_feed_reads_rss_items():
    items = reading_svc.parse_feed(RSS.encode())
    assert [i.title for i in items] == ["Understanding Raft", "Vector Clocks"]
    assert items[0].url == "https://example.com/posts/raft"
    assert items[0].published is not None
    assert items[0].published.year == 2026
    assert items[0].summary == "A walk through the consensus algorithm."


def test_parse_feed_reads_atom_entries_ignoring_namespaces():
    items = reading_svc.parse_feed(ATOM.encode())
    assert len(items) == 1
    assert items[0].title == "Effective Go"
    assert items[0].url == "https://go.dev/doc/effective_go"


def test_parse_feed_ignores_non_alternate_atom_links():
    """``rel="replies"`` is a comment thread, not the article."""
    items = reading_svc.parse_feed(ATOM.encode())
    assert items[0].url != "https://go.dev/comments/1"


def test_parse_feed_returns_empty_on_malformed_xml():
    """One publisher serving broken XML must not sink the whole batch."""
    assert reading_svc.parse_feed(b"<rss><channel><item>oops") == []


def test_parse_feed_refuses_oversized_payloads():
    """Guards against unbounded entity expansion and archive-sized feeds."""
    oversized = b"<rss>" + b" " * (reading_svc._FEED_SIZE_LIMIT + 1)
    assert reading_svc.parse_feed(oversized) == []


def test_parse_feed_keeps_items_without_dates():
    """Several publishers omit the date; their articles are still fine."""
    feed = b"""<rss version="2.0"><channel><item>
        <title>Undated</title><link>https://example.com/posts/undated</link>
    </item></channel></rss>"""
    items = reading_svc.parse_feed(feed)
    assert len(items) == 1
    assert items[0].published is None


def test_parse_feed_skips_items_missing_a_link():
    feed = b"""<rss version="2.0"><channel><item>
        <title>No link here</title>
    </item></channel></rss>"""
    assert reading_svc.parse_feed(feed) == []


# ---------------------------------------------------------------------------
# Feed link discovery
# ---------------------------------------------------------------------------
def test_find_feed_links_resolves_relative_hrefs():
    html = (
        "<html><head>"
        '<link rel="alternate" type="application/rss+xml" href="/feed.xml">'
        "</head></html>"
    )
    assert reading_svc.find_feed_links(html, "https://example.com/blog") == [
        "https://example.com/feed.xml"
    ]


def test_find_feed_links_accepts_atom_and_absolute_hrefs():
    html = (
        '<link rel="alternate" type="application/atom+xml" '
        'href="https://cdn.example.com/atom.xml">'
    )
    assert reading_svc.find_feed_links(html, "https://example.com") == [
        "https://cdn.example.com/atom.xml"
    ]


def test_find_feed_links_ignores_stylesheets_and_icons():
    html = (
        '<link rel="stylesheet" href="/site.css">'
        '<link rel="icon" href="/favicon.ico">'
        '<link rel="alternate" type="application/json" href="/feed.json">'
    )
    assert reading_svc.find_feed_links(html, "https://example.com") == []


# ---------------------------------------------------------------------------
# Candidate selection
# ---------------------------------------------------------------------------
def _item(url: str, title: str = "T", day: int | None = None) -> FeedItem:
    published = datetime(2026, 8, day, tzinfo=UTC) if day is not None else None
    return FeedItem(title=title, url=url, published=published)


def test_select_candidates_drops_entries_off_the_allowlist():
    """A feed is not self-certifying.

    ``kubernetes.io/docs`` advertises a feed that publishes ``/blog/`` posts;
    the allowlist said docs. Those entries must not reach the pool.
    """
    pool = reading_svc.select_candidates(
        {"kubernetes.io/docs": [_item("https://kubernetes.io/blog/some-post")]},
        allowed_domains={"kubernetes.io/docs"},
        exclude_urls=set(),
        per_domain=6,
        limit=100,
    )
    assert pool == []


def test_select_candidates_drops_index_urls():
    pool = reading_svc.select_candidates(
        {"example.com": [_item("https://example.com/blog")]},
        allowed_domains={"example.com"},
        exclude_urls=set(),
        per_domain=6,
        limit=100,
    )
    assert pool == []


def test_select_candidates_drops_already_seen_urls():
    """Spending pool slots on items the storage loop would reject is waste."""
    seen = reading_svc.normalize_url("https://example.com/posts/a")
    pool = reading_svc.select_candidates(
        {
            "example.com": [
                _item("https://example.com/posts/a"),
                _item("https://example.com/posts/b"),
            ]
        },
        allowed_domains={"example.com"},
        exclude_urls={seen},
        per_domain=6,
        limit=100,
    )
    assert [c.url for c in pool] == ["https://example.com/posts/b"]


def test_select_candidates_deduplicates_within_a_feed():
    pool = reading_svc.select_candidates(
        {
            "example.com": [
                _item("https://example.com/posts/a"),
                _item("https://example.com/posts/a#section"),
            ]
        },
        allowed_domains={"example.com"},
        exclude_urls=set(),
        per_domain=6,
        limit=100,
    )
    assert len(pool) == 1


def test_select_candidates_caps_each_domain_newest_first():
    """Unbounded, redis.io/docs alone offers 2145 entries."""
    items = [_item(f"https://example.com/posts/{d}", day=d) for d in (1, 15, 8)]
    pool = reading_svc.select_candidates(
        {"example.com": items},
        allowed_domains={"example.com"},
        exclude_urls=set(),
        per_domain=2,
        limit=100,
    )
    assert [c.url for c in pool] == [
        "https://example.com/posts/15",
        "https://example.com/posts/8",
    ]


def test_select_candidates_sorts_undated_items_last():
    items = [
        _item("https://example.com/posts/undated"),
        _item("https://example.com/posts/dated", day=3),
    ]
    pool = reading_svc.select_candidates(
        {"example.com": items},
        allowed_domains={"example.com"},
        exclude_urls=set(),
        per_domain=6,
        limit=100,
    )
    assert [c.url for c in pool] == [
        "https://example.com/posts/dated",
        "https://example.com/posts/undated",
    ]


def test_select_candidates_fills_the_total_cap_round_robin():
    """The cap must cost depth, not whole publishers.

    Filling greedily by domain would let the first two alphabetical sources
    consume a 4-item pool and delete the other two entirely — which is exactly
    what the batch-diversity rule then cannot recover from.
    """
    per_domain_items = {
        d: [_item(f"https://{d}.com/posts/{n}", day=n) for n in (5, 4, 3)]
        for d in ("alpha", "beta", "gamma", "delta")
    }
    allowed = {f"{d}.com" for d in ("alpha", "beta", "gamma", "delta")}
    pool = reading_svc.select_candidates(
        per_domain_items,
        allowed_domains=allowed,
        exclude_urls=set(),
        per_domain=3,
        limit=4,
    )
    assert len(pool) == 4
    assert len({c.domain for c in pool}) == 4


def test_select_candidates_numbers_the_final_pool_contiguously():
    """``index`` is an offset into the list the model is actually shown."""
    per_domain_items = {
        "example.com": [_item(f"https://example.com/posts/{n}", day=n) for n in (5, 4, 3)]
    }
    pool = reading_svc.select_candidates(
        per_domain_items,
        allowed_domains={"example.com"},
        exclude_urls=set(),
        per_domain=3,
        limit=10,
    )
    assert [c.index for c in pool] == [1, 2, 3]


def test_select_candidates_records_the_most_specific_allowlist_entry():
    """``domain`` is the allowlist entry, not the raw host — dislike counts key on it.

    ``go.dev`` and ``go.dev/blog`` are both seeded, so this URL matches twice.
    Before ``allowlist_match`` preferred the longest match it returned whichever
    the set happened to yield first, and this assertion failed intermittently.
    """
    pool = reading_svc.select_candidates(
        {"go.dev/blog": [_item("https://go.dev/blog/generics")]},
        allowed_domains={"go.dev/blog", "go.dev"},
        exclude_urls=set(),
        per_domain=6,
        limit=10,
    )
    assert len(pool) == 1
    assert pool[0].domain == "go.dev/blog"


# ---------------------------------------------------------------------------
# Prompt rendering
# ---------------------------------------------------------------------------
def test_format_candidate_renders_id_domain_title_and_date():
    from backend.app.pipelines.reading_pipeline import _format_candidate

    line = _format_candidate(
        Candidate(
            index=7,
            title="Understanding Raft",
            url="https://example.com/posts/raft",
            domain="example.com",
            published=datetime(2026, 8, 10, tzinfo=UTC),
        )
    )
    assert line == "[7] example.com — Understanding Raft (2026-08-10)"


def test_format_candidate_omits_a_missing_date():
    from backend.app.pipelines.reading_pipeline import _format_candidate

    line = _format_candidate(
        Candidate(index=1, title="Undated", url="https://example.com/u", domain="example.com")
    )
    assert line == "[1] example.com — Undated"


def test_candidate_is_immutable():
    """The pool is read back for title/url after the model responds.

    Frozen so nothing between building the pool and storing the row can edit
    the article's identity back into something the model supplied.
    """
    candidate = Candidate(index=1, title="T", url="https://e.com/a", domain="e.com")
    with pytest.raises(dataclasses.FrozenInstanceError):
        candidate.title = "changed"  # type: ignore[misc]
