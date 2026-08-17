"""Pure-function tests for reading link verification.

These live apart from ``test_reading.py`` because that module applies a
session-scoped asyncio mark to everything in it; the checks here are
synchronous and network-free by design — that is the point of splitting
fetching (``check_links``) from judging (``judge_link``).
"""

import pytest

from backend.app.services import reading as reading_svc


def test_allowlist_match_prefers_the_most_specific_entry():
    """Overlapping entries must not resolve by set-iteration order.

    ``go.dev`` and ``go.dev/blog`` are both on the seeded allowlist, so a blog
    post matches both. The answer feeds ``source_domain``, which domain-level
    dislike counts group by — an unstable one splits a publisher's rejections
    across two buckets.
    """
    for _ in range(50):
        assert (
            reading_svc.allowlist_match("https://go.dev/blog/generics", {"go.dev", "go.dev/blog"})
            == "go.dev/blog"
        )


def test_allowlist_match_still_falls_back_to_the_bare_host():
    assert (
        reading_svc.allowlist_match("https://go.dev/doc/effective_go", {"go.dev", "go.dev/blog"})
        == "go.dev"
    )


# ---------------------------------------------------------------------------
# Title extraction
# ---------------------------------------------------------------------------
def test_extract_titles_prefers_og_title_then_title_then_h1():
    html = (
        "<html><head><title>Generic Site Name</title>"
        '<meta property="og:title" content="The Specific Article">'
        "</head><body><h1>Article Heading</h1></body></html>"
    )
    assert reading_svc.extract_titles(html) == (
        "The Specific Article",
        "Generic Site Name",
        "Article Heading",
    )


def test_extract_titles_collapses_whitespace_and_dedupes():
    html = "<html><head><title>  Spread   Out\n Title </title></head><body><h1>Spread Out Title</h1></body></html>"  # noqa: E501
    assert reading_svc.extract_titles(html) == ("Spread Out Title",)


def test_extract_titles_on_markup_without_titles():
    assert reading_svc.extract_titles("<html><body><p>nothing</p></body></html>") == ()


# ---------------------------------------------------------------------------
# Index / landing page detection
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "url",
    [
        "https://research.google/blog/",
        "https://anthropic.com/news",
        "https://thoughtworks.com/insights/blog",
        "https://blog.langchain.dev",
        "https://example.com/tag",
        "https://example.com/docs/",
    ],
)
def test_is_index_url_rejects_listings(url):
    """The exact shapes that reached users as if they were articles."""
    assert reading_svc.is_index_url(url) is True


@pytest.mark.parametrize(
    "url",
    [
        "https://martinfowler.com/bliki/CQRS.html",
        "https://research.google/blog/some-specific-post/",
        "https://kubernetes.io/docs/tasks/run-application/horizontal-pod-autoscale",
        "https://go.dev/doc/effective_go",
    ],
)
def test_is_index_url_accepts_articles(url):
    assert reading_svc.is_index_url(url) is False


def test_redirect_shallowed_detects_soft_404():
    """A deep path bounced up to a section index is a soft 404."""
    assert (
        reading_svc.redirect_shallowed(
            "https://ex.example.com/blog/2024/deep-article",
            "https://ex.example.com/blog",
        )
        is True
    )


def test_redirect_shallowed_ignores_same_depth_and_fragments():
    assert (
        reading_svc.redirect_shallowed(
            "https://ex.example.com/a/b#frag", "https://ex.example.com/a/b"
        )
        is False
    )


# ---------------------------------------------------------------------------
# Title comparison
# ---------------------------------------------------------------------------
def test_title_overlap_scores_landing_page_near_zero():
    """The thoughtworks failure: article title against a section index title."""
    score = reading_svc.title_overlap(
        "Consumer-Driven Contracts with Pact: A Practical Introduction",
        "Insights | Thoughtworks",
    )
    assert score < reading_svc.DEFAULT_MIN_TITLE_OVERLAP


def test_title_overlap_accepts_lopsided_but_genuine_match():
    """martinfowler.com/bliki/CQRS.html is titled just "CQRS" — a real match."""
    score = reading_svc.title_overlap(
        "CQRS and Event Sourcing: Patterns for Data Synchronization", "CQRS"
    )
    assert score == 1.0


def test_title_overlap_rejects_short_title_sharing_one_token():
    """A symmetric ratio scored this 0.5; containment scores it low."""
    score = reading_svc.title_overlap(
        "Aurora Failover: Understanding the Mechanics of High Availability",
        "What is Amazon Aurora?",
    )
    assert score < reading_svc.DEFAULT_MIN_TITLE_OVERLAP


def test_title_overlap_accepts_a_paraphrased_but_correct_title():
    """A real article whose title the model reworded must survive.

    This pair scored 0.29 against the stored recommendations and is why the
    threshold sits at 0.25 rather than 0.4.
    """
    score = reading_svc.title_overlap(
        "Database Connection Pooling: Best Practices and Common Pitfalls",
        "What is connection pooling, and why should you care?",
    )
    assert score >= reading_svc.DEFAULT_MIN_TITLE_OVERLAP


def test_default_title_overlap_matches_settings():
    """The threshold is stated in two layers; they must not drift apart."""
    from backend.app.config import settings

    assert settings.reading_min_title_overlap == reading_svc.DEFAULT_MIN_TITLE_OVERLAP


def test_title_overlap_is_unjudgeable_when_tokens_are_empty():
    """No usable tokens is not evidence of a mismatch."""
    assert reading_svc.title_overlap("The How And Why", "a") == 1.0


# ---------------------------------------------------------------------------
# judge_link — the accept/reject decision
# ---------------------------------------------------------------------------
def test_judge_link_rejects_unreachable():
    check = reading_svc.LinkCheck("https://x.example.com/a", reachable=False, reason="HTTP 404")
    ok, reason = reading_svc.judge_link("Anything", check)
    assert ok is False
    assert "404" in reason


def test_judge_link_rejects_landing_page_even_when_reachable():
    """The core regression: a 200 landing page must no longer pass."""
    check = reading_svc.LinkCheck(
        "https://anthropic.com/news",
        reachable=True,
        final_url="https://anthropic.com/news",
        page_titles=("Anthropic News",),
    )
    ok, reason = reading_svc.judge_link("Structured Outputs and Tool Use", check)
    assert ok is False
    assert "landing page" in reason


def test_judge_link_rejects_title_mismatch_on_deep_url():
    check = reading_svc.LinkCheck(
        "https://martinfowler.com/articles/patterns-of-distributed-systems/",
        reachable=True,
        final_url="https://martinfowler.com/articles/patterns-of-distributed-systems/",
        page_titles=("Patterns of Distributed Systems",),
    )
    ok, reason = reading_svc.judge_link(
        "Scaling Up vs. Scaling Out: A Practical Guide to Database Growth", check
    )
    assert ok is False
    assert "title mismatch" in reason


def test_judge_link_accepts_genuine_article():
    check = reading_svc.LinkCheck(
        "https://martinfowler.com/bliki/CQRS.html",
        reachable=True,
        final_url="https://martinfowler.com/bliki/CQRS.html",
        page_titles=("CQRS",),
    )
    assert reading_svc.judge_link("CQRS and Event Sourcing Patterns", check) == (True, None)


def test_judge_link_accepts_unparseable_page():
    """A page we could not read a title from is not rejected on that basis."""
    check = reading_svc.LinkCheck(
        "https://ex.example.com/papers/x.pdf",
        reachable=True,
        final_url="https://ex.example.com/papers/x.pdf",
        page_titles=(),
    )
    assert reading_svc.judge_link("Some Paper", check) == (True, None)


def test_judge_link_respects_disabled_title_threshold():
    """min_title_overlap=0 keeps the structural checks but drops title matching."""
    check = reading_svc.LinkCheck(
        "https://ex.example.com/a/specific-post",
        reachable=True,
        final_url="https://ex.example.com/a/specific-post",
        page_titles=("Completely Unrelated",),
    )
    assert reading_svc.judge_link("Nothing Alike", check, min_title_overlap=0.0) == (True, None)


# ---------------------------------------------------------------------------
# Allowlist matching
# ---------------------------------------------------------------------------
def test_allowlist_match_accepts_exact_host():
    assert reading_svc.allowlist_match("https://infoq.com/articles/x", {"infoq.com"}) == "infoq.com"


def test_allowlist_match_honours_path_scoped_entries():
    allowed = {"postgresql.org/docs"}
    assert (
        reading_svc.allowlist_match("https://www.postgresql.org/docs/current/x.html", allowed)
        == "postgresql.org/docs"
    )
    assert reading_svc.allowlist_match("https://postgresql.org/about", allowed) is None


def test_allowlist_match_rejects_subdomain_of_allowed_entry():
    """docs.anthropic.com was stored under the anthropic.com/news entry."""
    assert (
        reading_svc.allowlist_match(
            "https://docs.anthropic.com/en/docs/build-with-claude/tool-use/overview",
            {"anthropic.com/news"},
        )
        is None
    )


def test_allowlist_match_ignores_a_claimed_source_domain():
    """blog.langchain.dev was stored labelled thenewstack.io."""
    assert reading_svc.allowlist_match("https://blog.langchain.dev", {"thenewstack.io"}) is None


# ---------------------------------------------------------------------------
# URL normalization
# ---------------------------------------------------------------------------
def test_normalize_url_strips_fragment():
    """These two were stored as separate recommendations a month apart."""
    base = "https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/"
    assert reading_svc.normalize_url(base) == reading_svc.normalize_url(
        base + "#requests-and-limits"
    )


def test_normalize_url_strips_www_and_case():
    assert reading_svc.normalize_url("https://WWW.Example.com/A/") == "https://example.com/a"


def test_normalize_url_preserves_query():
    assert reading_svc.normalize_url("https://ex.com/a?p=1") == "https://ex.com/a?p=1"
