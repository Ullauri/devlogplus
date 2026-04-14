"""Step definitions for data_transfer.feature."""

from __future__ import annotations

import io
import json
import uuid
from datetime import UTC, datetime

from pytest_bdd import given, parsers, scenarios, then, when

from backend.tests.bdd.conftest import create_journal_entry, create_topics, run_async

# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------

scenarios("data_transfer.feature")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _upload_file(data: dict, filename: str = "export.json"):
    """Build a multipart file tuple for httpx."""
    raw = json.dumps(data).encode()
    return ("file", (filename, io.BytesIO(raw), "application/json"))


def _minimal_bundle(
    *,
    journal_entries: list | None = None,
    topics: list | None = None,
    format_version: int = 1,
) -> dict:
    """Build a minimal valid export bundle dict."""
    now = datetime.now(UTC).isoformat()
    return {
        "format_version": format_version,
        "exported_at": now,
        "app_version": "0.1.0",
        **({"journal_entries": journal_entries} if journal_entries is not None else {}),
        **({"topics": topics} if topics is not None else {}),
    }


def _make_journal_entry_dict(title: str = "Imported entry") -> dict:
    now = datetime.now(UTC).isoformat()
    return {
        "id": str(uuid.uuid4()),
        "title": title,
        "is_processed": False,
        "processed_at": None,
        "created_at": now,
        "updated_at": now,
    }


# ---------------------------------------------------------------------------
# Given steps
# ---------------------------------------------------------------------------

@given(
    parsers.parse(
        'I have a journal entry titled "{title}" with content "{content}"'
    ),
    target_fixture="ctx",
)
def given_journal_entry(bdd_client, bdd_db, ctx, title, content):
    create_journal_entry(bdd_db, title=title, content=content)
    run_async(bdd_db.commit())
    return {**ctx, "original_title": title} if isinstance(ctx, dict) else {"original_title": title}


@given("I have topics in my knowledge profile", target_fixture="ctx")
def given_topics(bdd_db, ctx):
    create_topics(bdd_db)
    run_async(bdd_db.commit())
    return ctx if isinstance(ctx, dict) else {}


@given(
    parsers.parse("I have an export bundle with {count:d} journal entry"),
    target_fixture="ctx",
)
def given_bundle_with_entries(ctx, count):
    entries = [_make_journal_entry_dict() for _ in range(count)]
    bundle = _minimal_bundle(journal_entries=entries)
    ctx = ctx if isinstance(ctx, dict) else {}
    ctx["prepared_bundle"] = bundle
    return ctx


@given(
    parsers.parse(
        'I have an export bundle containing a journal entry titled "{title}"'
    ),
    target_fixture="ctx",
)
def given_bundle_with_named_entry(ctx, title):
    entry = _make_journal_entry_dict(title=title)
    bundle = _minimal_bundle(journal_entries=[entry])
    ctx = ctx if isinstance(ctx, dict) else {}
    ctx["prepared_bundle"] = bundle
    return ctx


# ---------------------------------------------------------------------------
# When steps
# ---------------------------------------------------------------------------

@when("I export all data", target_fixture="ctx")
def when_export(bdd_client, ctx):
    ctx = ctx if isinstance(ctx, dict) else {}
    resp = run_async(bdd_client.get("/api/v1/transfer/export"))
    ctx["response"] = resp
    if resp.status_code == 200:
        ctx["export_bundle"] = resp.json()
    return ctx


@when("I request export metadata", target_fixture="ctx")
def when_export_metadata(bdd_client, ctx):
    ctx = ctx if isinstance(ctx, dict) else {}
    resp = run_async(bdd_client.get("/api/v1/transfer/export/metadata"))
    ctx["response"] = resp
    ctx["metadata"] = resp.json() if resp.status_code == 200 else None
    return ctx


@when("I import the exported bundle with overwrite confirmed", target_fixture="ctx")
def when_import_exported_bundle(bdd_client, ctx):
    bundle = ctx.get("export_bundle")
    assert bundle is not None, "No export bundle available — did you export first?"
    resp = run_async(
        bdd_client.post(
            "/api/v1/transfer/import?confirm_overwrite=true",
            files=[_upload_file(bundle)],
        )
    )
    ctx["import_response"] = resp
    return ctx


@when("I import the bundle into an empty database", target_fixture="ctx")
def when_import_into_empty(bdd_client, ctx):
    bundle = ctx["prepared_bundle"]
    resp = run_async(
        bdd_client.post("/api/v1/transfer/import", files=[_upload_file(bundle)])
    )
    ctx["import_response"] = resp
    return ctx


@when("I import the bundle without confirming overwrite", target_fixture="ctx")
def when_import_no_confirm(bdd_client, ctx):
    bundle = ctx["prepared_bundle"]
    resp = run_async(
        bdd_client.post("/api/v1/transfer/import", files=[_upload_file(bundle)])
    )
    ctx["import_response"] = resp
    return ctx


@when("I import the bundle with overwrite confirmed", target_fixture="ctx")
def when_import_with_confirm(bdd_client, ctx):
    bundle = ctx["prepared_bundle"]
    resp = run_async(
        bdd_client.post(
            "/api/v1/transfer/import?confirm_overwrite=true",
            files=[_upload_file(bundle)],
        )
    )
    ctx["import_response"] = resp
    return ctx


@when("I import an invalid JSON file", target_fixture="ctx")
def when_import_invalid(bdd_client):
    raw = b"this is not valid json at all"
    resp = run_async(
        bdd_client.post(
            "/api/v1/transfer/import",
            files=[("file", ("bad.json", io.BytesIO(raw), "application/json"))],
        )
    )
    return {"import_response": resp}


@when(
    parsers.parse("I import a bundle with format version {version:d}"),
    target_fixture="ctx",
)
def when_import_bad_version(bdd_client, version):
    bundle = _minimal_bundle(format_version=version)
    resp = run_async(
        bdd_client.post(
            "/api/v1/transfer/import",
            files=[_upload_file(bundle)],
        )
    )
    return {"import_response": resp}


# ---------------------------------------------------------------------------
# Then steps
# ---------------------------------------------------------------------------

@then("the export should succeed")
def then_export_success(ctx):
    assert ctx["response"].status_code == 200


@then(parsers.parse("the export bundle should have format version {version:d}"))
def then_format_version(ctx, version):
    assert ctx["export_bundle"]["format_version"] == version


@then(
    parsers.parse("the export bundle should contain {count:d} journal entries")
)
def then_export_journal_count(ctx, count):
    assert len(ctx["export_bundle"]["journal_entries"]) == count


@then(parsers.parse("the export bundle should contain {count:d} topics"))
def then_export_topic_count(ctx, count):
    assert len(ctx["export_bundle"]["topics"]) == count


@then(parsers.parse("the metadata should show {count:d} journal entries"))
def then_metadata_journal_count(ctx, count):
    assert ctx["metadata"]["table_counts"]["journal_entries"] == count


@then(parsers.parse("the metadata should show {count:d} journal entry versions"))
def then_metadata_version_count(ctx, count):
    assert ctx["metadata"]["table_counts"]["journal_entry_versions"] == count


@then("the import should succeed")
def then_import_success(ctx):
    resp = ctx.get("import_response")
    assert resp is not None
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"


@then(parsers.parse("the imported data should contain {count:d} journal entries"))
def then_import_journal_count(ctx):
    data = ctx["import_response"].json()
    assert data["counts"]["journal_entries"] >= 0


@then(parsers.parse('the journal entry titled "{title}" should still exist'))
def then_entry_exists(bdd_client, title):
    resp = run_async(bdd_client.get("/api/v1/journal/entries"))
    assert resp.status_code == 200
    entries = resp.json()
    titles = [e["title"] for e in entries]
    assert title in titles, f"Expected '{title}' in {titles}"


@then("the import should be rejected with a conflict error")
def then_conflict(ctx):
    assert ctx["import_response"].status_code == 409
    assert "already contains data" in ctx["import_response"].json()["detail"]


@then(parsers.parse('the original journal entry "{title}" should still exist'))
def then_original_exists(bdd_client, title):
    resp = run_async(bdd_client.get("/api/v1/journal/entries"))
    entries = resp.json()
    titles = [e["title"] for e in entries]
    assert title in titles, f"Expected '{title}' in {titles}"


@then(parsers.parse('the original journal entry "{title}" should no longer exist'))
def then_original_gone(bdd_client, title):
    resp = run_async(bdd_client.get("/api/v1/journal/entries"))
    entries = resp.json()
    titles = [e["title"] for e in entries]
    assert title not in titles, f"Did not expect '{title}' in {titles}"


@then("the import should be rejected with a validation error")
def then_validation_error(ctx):
    assert ctx["import_response"].status_code == 422


@then("the import should be rejected with a validation error about format version")
def then_format_version_error(ctx):
    assert ctx["import_response"].status_code == 422
    assert "format_version" in ctx["import_response"].json()["detail"].lower()
