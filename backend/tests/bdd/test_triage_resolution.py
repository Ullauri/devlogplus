"""Step definitions for triage_resolution.feature."""

from pytest_bdd import given, parsers, scenarios, then, when

from backend.tests.bdd.conftest import create_triage_item, run_async

# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------

scenarios("triage_resolution.feature")


# ---------------------------------------------------------------------------
# Steps
# ---------------------------------------------------------------------------


@given(
    parsers.parse('there is a pending triage item with severity "{severity}"'),
    target_fixture="ctx",
)
def given_triage_item(bdd_db, severity):
    item = create_triage_item(bdd_db, severity=severity)
    run_async(bdd_db.commit())
    return {"triage_item": item, "triage_items": [item]}


@given("there is a critical unresolved triage item")
def given_critical_triage(bdd_db, ctx):
    item = create_triage_item(bdd_db, severity="critical")
    run_async(bdd_db.commit())
    ctx["triage_item"] = item
    ctx.setdefault("triage_items", []).append(item)


@when(
    parsers.parse('I resolve the triage item with action "{action}" and text "{text}"'),
)
def when_resolve_triage(bdd_client, ctx, action, text):
    triage = ctx["triage_item"]
    item_id = str(triage["id"] if isinstance(triage, dict) else triage.id)
    resp = run_async(
        bdd_client.post(
            f"/api/v1/triage/{item_id}/resolve",
            json={"action": action, "resolution_text": text},
        )
    )
    ctx["resolve_response"] = resp
    ctx["resolved_item"] = resp.json()


@then(parsers.parse('the triage item should have status "{status}"'))
def then_triage_status(ctx, status):
    assert ctx["resolved_item"]["status"] == status


@then(parsers.parse('the triage item should have resolution text "{text}"'))
def then_resolution_text(ctx, text):
    assert ctx["resolved_item"]["resolution_text"] == text


# --- Blocking scenario ------------------------------------------------------


@when("I check for blocking triage items")
def when_check_blocking(bdd_client, ctx):
    resp = run_async(bdd_client.get("/api/v1/triage/blocking"))
    assert resp.status_code == 200
    ctx["blocking_response"] = resp.json()


@then("the system should report blocking triage")
def then_blocking(ctx):
    assert ctx["blocking_response"]["blocking"] is True


@when(
    parsers.parse('I resolve the critical triage item with action "{action}" and text "{text}"'),
)
def when_resolve_critical(bdd_client, ctx, action, text):
    item_id = str(ctx["triage_item"].id)
    resp = run_async(
        bdd_client.post(
            f"/api/v1/triage/{item_id}/resolve",
            json={"action": action, "resolution_text": text},
        )
    )
    ctx["resolve_response"] = resp
    ctx["resolved_item"] = resp.json()


@then("the system should report no blocking triage")
def then_not_blocking(ctx):
    assert ctx["blocking_response"]["blocking"] is False


# --- Filter scenario --------------------------------------------------------


@when(parsers.parse('I list triage items filtered by severity "{severity}"'))
def when_filter_triage(bdd_client, ctx, severity):
    resp = run_async(bdd_client.get(f"/api/v1/triage?severity={severity}"))
    assert resp.status_code == 200
    ctx["filtered_items"] = resp.json()["items"]


@then("I should see only critical triage items")
def then_only_critical(ctx):
    assert len(ctx["filtered_items"]) > 0
    for item in ctx["filtered_items"]:
        assert item["severity"] == "critical"
