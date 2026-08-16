# ADR 0008 — TrueCourse analysis baseline, refreshed on main and committed

**Date:** 2026-08-16
**Status:** Accepted

## Context

`make test-arch` enforces the layered DAG from ADR 0001, and Ruff and ESLint
cover style. Neither reaches the class of defect that only shows up across
files: missing transactions around multi-write service calls, unhandled
promises, cognitive complexity, god modules, hardcoded secrets. Those get found
by whoever happens to read the file.

[TrueCourse](https://github.com/truecourse-ai/truecourse) runs ~1,200
deterministic tree-sitter rules over the repo and writes its findings to
`.truecourse/`. The first deterministic run on this repo found 922 active
findings — 1 critical, 90 high — across 15 distinct rules at high severity or
above. That is a real backlog, and it needs somewhere to live that is not a
terminal window.

Three things had to be decided: when the analysis runs, where its output lives,
and whether it can fail a build.

## Decision

**Run it on `main` only, after the merge.** `.github/workflows/truecourse.yml`
triggers on `push` to `main` (plus `workflow_dispatch`), runs
`truecourse analyze --no-llm --no-stash --no-skills`, and commits the refreshed
`.truecourse/LATEST.json` back to `main` with the `GITHUB_TOKEN`.

**Commit `LATEST.json`; ignore everything else under `.truecourse/`.**
`LATEST.json` is the materialised current-state view and is TrueCourse's own
designated committable baseline — `analyze --diff` and the optional pre-commit
hook both diff against it, so a tracked copy means fresh clones and worktrees
inherit the baseline through git with no cold start. `.truecourse/.gitignore`
(written by the tool) excludes `analyses/`, `history.json`, `diff.json`,
`logs/` and the rest, which are per-checkout.

**Never refresh the baseline from a feature branch.** Two PRs both regenerating
a 1.7 MB generated JSON conflict on every merge, and a baseline that moves per
branch cannot answer "is this finding new". Branches may *read* it — that is
what `truecourse analyze --diff` is for — but only the workflow writes it.

**Deterministic rules only.** TrueCourse's LLM rules need either a signed-in
`claude` binary or a provider API key. CI has neither, and a baseline whose
contents depend on whether a secret happened to be present is not a baseline.
`--no-llm` makes that explicit rather than incidental.

**It is a signal, not a gate.** The workflow runs after the merge has already
happened and does not fail on findings. Adding a severity gate to a repo with
90 open high-severity findings would block every PR on day one; the backlog has
to come down first, through work that is filed and prioritised.

**Pin the tool to a patch range** (`truecourse@~0.7.4`). Rule keys are the
identity downstream consumers deduplicate on. A minor bump that renames or
splits a rule silently re-files work that is already tracked, so the minor moves
deliberately, with a look at the diff.

## Consequences

- **+** Findings are durable and versioned. `git log -- .truecourse/LATEST.json`
  shows when the count moved and which merge moved it.
- **+** The baseline is a machine-readable signal any consumer can act on
  without running the tool. The knowledgebase repo sweeps it (`kb sweep
  truecourse --project devlogplus`) and files one proposed task per rule key,
  deduplicating against tasks already on file.
- **+** `truecourse analyze --diff` works on a fresh clone or a new worktree
  immediately, because the baseline arrived with the checkout.
- **+** No secrets, no API cost, no external service. The run is ~1 minute.
- **−** A ~1.7 MB generated JSON is tracked, and it churns on most merges. It
  is one file, it is never hand-edited, and nothing merges it (only the
  workflow writes it), so the churn is confined to `git log` noise.
- **−** Every merge to `main` produces a second, automated commit. The commit is
  authored by `github-actions[bot]` and pushes with `GITHUB_TOKEN`, which by
  design does not re-trigger workflows, so it cannot loop.
- **−** The 922-finding backlog is now visible and unaddressed. That is the
  point — it was there before, and it was invisible.
- **−** LLM rules and the `spec`/`guard` business-logic-drift track are not set
  up. Both need an LLM transport and, for guard, a curated spec corpus; they are
  separate decisions.
