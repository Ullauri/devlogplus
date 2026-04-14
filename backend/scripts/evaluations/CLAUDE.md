# Evaluations — AI Coding Instructions

## Purpose
Node-level evaluation framework for testing individual LLM pipeline nodes in isolation.  Each script calls the real LLM endpoint with curated test data, measures accuracy and latency across repeated trials, computes statistical significance (p-values), and generates visual reports.

## Architecture
```
harness.py              — Core engine: EvalHarness, EvalCase, trial runner, stats, charting
run_all.py              — CLI runner: all nodes or a specific one
nodes/
  eval_<node>.py        — Per-node script with: node_fn (LLM call), custom scorer, main()
  fixtures/<node>.json  — Test cases: input data + expected output criteria
reports/                — Output: <node>_eval.png (chart) + <node>_eval.json (data)
```

## Conventions
- **One script per node**: each `eval_<node>.py` is standalone and runnable independently.
- **Custom scorers**: every node has a domain-specific accuracy function — never use the generic default scorer for node evals.
- **Fixtures are declarative**: test cases define `input` (prompt template fields) and `expected` (scoring criteria), not raw LLM output.
- **No database required**: scripts import only from `backend.app.prompts`, `backend.app.services.llm`, and `backend.app.services.llm.models`.
- **Iterations configurable**: always accept `--iterations N` (default 5).  Each case is run N times.
- **Statistical pass criteria**: mean accuracy ≥ 0.7 **and** one-sided t-test p < 0.05.
- **Charts are colour-coded**: green = pass, orange = high accuracy but p ≥ 0.05, red = fail.

## Adding a new node evaluation
1. Create `nodes/fixtures/<node>.json` with test cases.
2. Create `nodes/eval_<node>.py` with a `call_<node>()` async function and a `score_<node>()` scorer.
3. Register the node name in `run_all.py`'s `NODES` list.

## Running
```bash
python -m backend.scripts.evaluations.nodes.eval_topic_extraction -n 5
python -m backend.scripts.evaluations.run_all --iterations 10
python -m backend.scripts.evaluations.run_all --node quiz_evaluation
```
