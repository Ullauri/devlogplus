# Scripts — AI Coding Instructions

## Purpose
Standalone utility scripts and batch tooling that live outside the main application server.  These are run manually or via cron — never imported by `backend.app`.

## Directory layout
```
backend/scripts/
  evaluations/          — Node-level LLM evaluation framework
    harness.py          — Shared eval engine (trials, stats, charting)
    run_all.py          — Runner for all / single node evaluations
    reports/            — Generated charts (PNG) + JSON reports (gitignored)
    nodes/              — One eval script per pipeline node
      fixtures/         — Curated test data (JSON) per node
```

## Conventions
- Scripts are invoked as modules: `python -m backend.scripts.evaluations.nodes.eval_<node>`.
- They must work **without** a running database — they only need the LLM client + prompts.
- Extra dependencies (matplotlib, scipy) are eval-only — not in the main app deps.
- All generated artefacts go to `evaluations/reports/` (gitignored).
