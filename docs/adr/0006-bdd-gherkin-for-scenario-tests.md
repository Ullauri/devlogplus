# ADR 0006 — BDD / Gherkin for End-to-End Scenario Tests

**Date:** 2026-04-19  
**Status:** Accepted

## Context

The application has several complex user-facing flows (onboarding, journal →
pipeline → quiz, project submission → evaluation). Unit and integration tests
cover individual components well but don't capture the narrative of a complete
user journey. There is also value in having tests that are readable by a
non-technical audience (or an AI assistant) without parsing Python.

## Decision

Use **pytest-bdd** with Gherkin `.feature` files (stored under
`backend/tests/features/`) for end-to-end scenario tests. These are run
separately via `make test-bdd` so they don't slow the normal `make test` loop.

## Consequences

- **+** Feature files document intended behaviour in plain English, serving as
  living specifications.
- **+** Easy to verify that a new pipeline or endpoint has a corresponding
  acceptance scenario before writing implementation code.
- **+** `make test-bdd` gives a fast pass/fail signal on user-facing flows after
  major changes.
- **−** pytest-bdd step definitions add a layer of indirection that can be
  confusing — the mapping between Gherkin steps and Python functions must be
  maintained.
- **−** BDD tests tend to be slower and more brittle than unit tests; they are
  kept in a separate suite for this reason.
