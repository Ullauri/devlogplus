"""Step definitions for onboarding.feature."""

from pytest_bdd import parsers, scenarios, then, when

from backend.tests.bdd.conftest import run_async

# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------

scenarios("onboarding.feature")


# ---------------------------------------------------------------------------
# Steps
# ---------------------------------------------------------------------------


@when("I check the onboarding status", target_fixture="ctx")
def when_check_status(bdd_client):
    resp = run_async(bdd_client.get("/api/v1/onboarding/status"))
    return {"response": resp, "status_body": resp.json()}


@then("onboarding should not be completed")
def then_not_completed(ctx):
    assert ctx["status_body"]["completed"] is False


@when("I complete onboarding with the following details:", target_fixture="ctx")
def when_complete_onboarding(bdd_client, datatable):
    # datatable is a list of rows; each row has cells.
    # Build kwargs from the two-column table.
    data = {}
    for row in datatable:
        key = row[0].strip()
        value = row[1].strip()
        data[key] = value

    payload = {
        "self_assessment": {
            "primary_languages": [
                lang.strip() for lang in data.get("primary_languages", "").split(",")
            ],
            "years_experience": int(data.get("years_experience", 5)),
            "primary_domain": data.get("primary_domain", "backend"),
        },
        "go_experience": {
            "level": data.get("go_level", "beginner"),
        },
        "topic_interests": [t.strip() for t in data.get("topic_interests", "").split(",")],
    }

    resp = run_async(bdd_client.post("/api/v1/onboarding/complete", json=payload))
    return {"response": resp, "onboarding": resp.json()}


@then("onboarding should be completed")
def then_completed(ctx):
    assert ctx["response"].status_code == 200
    assert ctx["onboarding"]["completed"] is True


@then(parsers.parse('the onboarding state should have go experience level "{level}"'))
def then_go_level(ctx, level):
    assert ctx["onboarding"]["go_experience_level"] == level
