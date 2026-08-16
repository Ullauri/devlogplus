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

**Deterministic rules only in the pipeline; LLM rules on demand.** The
committed baseline is produced by `--no-llm`.

Not because the LLM rules are unreachable. TrueCourse's `api` transport takes a
`--base-url`, documented for gateways and naming OpenRouter among them, and its
cost table is keyed by OpenRouter model ids — so the same OpenRouter account
that already powers all seven pipelines drives the LLM rules too:

```
truecourse config llm setup --transport api --provider openai \
  --base-url https://openrouter.ai/api/v1 \
  --model anthropic/claude-sonnet-5 --api-key-env OPENROUTER_API_KEY
```

`make truecourse-llm-setup` is that command, and `make truecourse-llm` is the
run. Three reasons that stays a manual target rather than a step in this
workflow:

- **Cost, on every merge, forever.** ~100 LLM rules over the repo per merge.
  This repo already quarantines LLM spend deliberately — `make eval` is kept out
  of the normal test loop for exactly this reason — and a pipeline that bills on
  every merge is a bigger commitment than the value of a slightly deeper
  baseline.
- **A baseline's job is answering "is this finding new".** Deterministic rules
  answer that exactly: same code, same findings. LLM rules can flap on unchanged
  code, which puts churn in `git log -- .truecourse/LATEST.json` that is not a
  code change. (This does not affect consumers that deduplicate on rule key —
  the LLM rule keys are a fixed set — but it does degrade the baseline's own
  claim.)
- **Source egress.** Deterministic rules never leave the runner. LLM rules ship
  source to a third party on every merge, which is a different posture from the
  pipelines sending journal text, and deserves a deliberate yes rather than
  arriving as a side effect of a CI change.

An earlier draft of this ADR argued instead that "CI has neither a `claude`
binary nor a key, and a baseline whose contents depend on whether a secret
happened to be present is not a baseline". The premise is wrong: an
`OPENROUTER_API_KEY` repository secret would be reliably present. The reasons
above are the ones that actually hold.

The gateway wiring is confirmed: run against OpenRouter with a deliberately
invalid key, the probe comes back with OpenRouter's own `User not found` and
refuses to save. The request was built, routed and parsed by OpenRouter — only
auth failed, so a real key takes that path to completion.

One thing remains unverified, and it is not auth. TrueCourse's `generateObject`
path submits strict `json_schema` structured outputs and **throws rather than
degrading** when a schema cannot be enforced — its transport says so explicitly:
"there is no silent degradation". OpenRouter forwards `response_format` to
underlying providers whose support for strict schemas varies by route. If a rule
fails that way it will fail loudly on the first real `make truecourse-llm`, which
costs nothing but the run. Should it happen, `--model` is the knob:
`make truecourse-llm TRUECOURSE_MODEL=openai/gpt-4o` picks a route with
first-class structured-output support.

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
- **+** No secrets, no API cost, no external service in the pipeline. The run is
  ~1 minute.
- **+** The deeper pass is still one command away when it is wanted:
  `make truecourse-llm`, on the existing OpenRouter account, at a cost that is
  incurred deliberately rather than per merge.
- **−** A ~1.7 MB generated JSON is tracked, and it churns on most merges. It
  is one file, it is never hand-edited, and nothing merges it (only the
  workflow writes it), so the churn is confined to `git log` noise.
- **−** Every merge to `main` produces a second, automated commit. The commit is
  authored by `github-actions[bot]` and pushes with `GITHUB_TOKEN`, which by
  design does not re-trigger workflows, so it cannot loop.
- **−** The 922-finding backlog is now visible and unaddressed. That is the
  point — it was there before, and it was invisible.
- **−** A local `make truecourse` or `make truecourse-llm` rewrites the tracked
  `.truecourse/LATEST.json`, so it shows as dirty and could be committed from a
  branch by accident. `make truecourse-restore` puts it back, and both targets
  print that as their last line.
- **−** The `spec`/`guard` business-logic-drift track is not set up. It needs a
  curated spec corpus on top of the LLM transport, and is a separate decision.
