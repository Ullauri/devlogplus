# Node Evaluation Scripts

Standalone evaluation scripts for each LLM pipeline node. Each script:

1. Loads curated test fixtures for that specific node
2. Calls the real LLM endpoint multiple times per test case
3. Scores accuracy against expected outputs using domain-specific heuristics
4. Computes statistical **p-values** (one-sample t-test, H₀: accuracy ≤ 0.5)
5. Generates a **chart** (PNG) showing accuracy and latency with error bars

## Prerequisites

Install the extra dependencies (not required by the main app):

```bash
pip install matplotlib numpy scipy
```

Ensure your `.env` file has a valid `OPENROUTER_API_KEY`.

## Directory Structure

```
backend/scripts/evaluations/
├── harness.py                      # Shared evaluation harness
├── run_all.py                      # Run all (or one) node evaluations
├── reports/                        # Generated charts + JSON reports
│   ├── topic_extraction_eval.png
│   ├── topic_extraction_eval.json
│   └── ...
└── nodes/
    ├── fixtures/                   # Test data per node
    │   ├── topic_extraction.json
    │   ├── profile_update.json
    │   ├── quiz_generation.json
    │   ├── quiz_evaluation.json
    │   ├── reading_generation.json
    │   ├── project_generation.json
    │   └── project_evaluation.json
    ├── eval_topic_extraction.py
    ├── eval_profile_update.py
    ├── eval_quiz_generation.py
    ├── eval_quiz_evaluation.py
    ├── eval_reading_generation.py
    ├── eval_project_generation.py
    └── eval_project_evaluation.py
```

## Usage

### Run a single node evaluation

```bash
# From the project root:
python -m backend.scripts.evaluations.nodes.eval_topic_extraction --iterations 5
python -m backend.scripts.evaluations.nodes.eval_quiz_evaluation -n 10
```

### Run all node evaluations

```bash
python -m backend.scripts.evaluations.run_all
python -m backend.scripts.evaluations.run_all --iterations 10
python -m backend.scripts.evaluations.run_all --node quiz_generation -n 7
```

## Output

Each run produces two artefacts in `backend/scripts/evaluations/reports/`:

| File | Description |
|------|-------------|
| `<node>_eval.png` | Bar chart with accuracy (colour-coded pass/fail + p-value) and latency (mean ± std) |
| `<node>_eval.json` | Machine-readable report with per-case scores, latencies, and p-values |

### Chart colour coding

| Colour | Meaning |
|--------|---------|
| 🟢 Green | Accuracy ≥ threshold **and** p < 0.05 |
| 🟠 Orange | Accuracy ≥ threshold but p ≥ 0.05 (not statistically significant) |
| 🔴 Red | Accuracy below threshold |

## How it works

### Accuracy scoring

Each node has a **custom scorer** tailored to its output schema:

| Node | Key checks |
|------|-----------|
| `topic_extraction` | Topic count in range, expected topics present, categories match, confidence thresholds met |
| `profile_update` | Target topic present, change direction correct, triage items created when expected |
| `quiz_generation` | Question count, all free-text, required fields present, type mix (reinforcement/exploration) |
| `quiz_evaluation` | Evaluation count, correctness ratings match (full/partial/incorrect), confidence thresholds |
| `reading_generation` | Recommendation count, domain allowlist compliance, required fields, valid types |
| `project_generation` | Has title/description/readme, file count, task count, difficulty range, Go + test files present |
| `project_evaluation` | Code quality score range, tasks evaluated, difficulty adjustment direction, assessment quality |

### Statistical testing

- Each test case is run **N** times (default 5, configurable with `--iterations`)
- A **one-sample t-test** checks whether mean accuracy is significantly > 0.5 (chance level)
- The reported **p-value** is one-sided (right tail)
- A case **passes** when: mean accuracy ≥ 0.7 **and** p < 0.05

## Adding new test cases

Edit the JSON fixture files in `nodes/fixtures/`. Each fixture follows this schema:

```json
{
  "node": "<node_name>",
  "description": "...",
  "cases": [
    {
      "name": "descriptive_case_name",
      "tags": ["optional", "tags"],
      "input": { ... },
      "expected": { ... }
    }
  ]
}
```

- `input` matches the fields expected by the node's prompt template
- `expected` defines the criteria the custom scorer checks against

## Cost

> **2026-04-13:** Running the full evaluation suite across all 7 nodes with `ITERS=3` cost approximately **$3 USD** in OpenRouter tokens (model: `anthropic/claude-sonnet-4`). Budget accordingly when increasing iterations or adding test cases.
