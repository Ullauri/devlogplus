"""Step definitions for journaling.feature."""

from pytest_bdd import given, parsers, scenarios, then, when

from backend.tests.bdd.conftest import run_async

# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------

scenarios("journaling.feature")


# ---------------------------------------------------------------------------
# Steps
# ---------------------------------------------------------------------------


@when(
    parsers.parse('I create a journal entry titled "{title}" with content "{content}"'),
    target_fixture="ctx",
)
def when_create_entry(bdd_client, title, content):
    resp = run_async(
        bdd_client.post("/api/v1/journal/entries", json={"title": title, "content": content})
    )
    return {"response": resp, "entry": resp.json() if resp.status_code == 201 else None}


@then("the entry should be created successfully")
def then_entry_created(ctx):
    assert ctx["response"].status_code == 201


@then(parsers.parse('the entry should have title "{title}"'))
def then_entry_title(ctx, title):
    assert ctx["entry"]["title"] == title


@then("the entry should not be processed yet")
def then_not_processed(ctx):
    assert ctx["entry"]["is_processed"] is False


# --- Edit scenario ----------------------------------------------------------


@given(
    parsers.parse('I have a journal entry titled "{title}" with content "{content}"'),
    target_fixture="ctx",
)
def given_journal_entry(bdd_client, title, content):
    resp = run_async(
        bdd_client.post("/api/v1/journal/entries", json={"title": title, "content": content})
    )
    assert resp.status_code == 201
    return {"entry": resp.json()}


@when(
    parsers.parse('I edit the entry with title "{title}" and content "{content}"'),
)
def when_edit_entry(bdd_client, ctx, title, content):
    entry_id = ctx["entry"]["id"]
    resp = run_async(
        bdd_client.put(
            f"/api/v1/journal/entries/{entry_id}",
            json={"title": title, "content": content},
        )
    )
    ctx["response"] = resp
    ctx["entry"] = resp.json()


@then(parsers.parse('the entry title should be "{title}"'))
def then_title_is(ctx, title):
    assert ctx["entry"]["title"] == title


@then(parsers.parse('the entry current content should be "{content}"'))
def then_current_content(ctx, bdd_client, content):
    entry_id = ctx["entry"]["id"]
    detail = run_async(bdd_client.get(f"/api/v1/journal/entries/{entry_id}"))
    assert detail.status_code == 200
    assert detail.json()["current_content"] == content


@then(parsers.parse("the entry should have {count:d} versions"))
def then_version_count(ctx, bdd_client, count):
    entry_id = ctx["entry"]["id"]
    detail = run_async(bdd_client.get(f"/api/v1/journal/entries/{entry_id}"))
    assert detail.status_code == 200
    assert len(detail.json()["versions"]) == count


# --- List scenario ----------------------------------------------------------


@when("I list all journal entries")
def when_list_entries(bdd_client, ctx):
    resp = run_async(bdd_client.get("/api/v1/journal/entries"))
    ctx["response"] = resp
    ctx["entries_list"] = resp.json()


@then(parsers.parse("I should see {count:d} entries in the list"))
def then_entry_count(ctx, count):
    assert len(ctx["entries_list"]) == count


# --- Delete scenario --------------------------------------------------------


@when("I delete the entry")
def when_delete_entry(bdd_client, ctx):
    entry_id = ctx["entry"]["id"]
    resp = run_async(bdd_client.delete(f"/api/v1/journal/entries/{entry_id}"))
    ctx["response"] = resp


@then("the entry should no longer exist")
def then_entry_gone(bdd_client, ctx):
    entry_id = ctx["entry"]["id"]
    resp = run_async(bdd_client.get(f"/api/v1/journal/entries/{entry_id}"))
    assert resp.status_code == 404
