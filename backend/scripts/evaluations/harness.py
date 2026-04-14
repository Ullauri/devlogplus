"""Shared evaluation harness for node-level LLM pipeline testing.

Provides:
- Test fixture loading
- Repeated trial execution with latency measurement
- Accuracy scoring against expected outputs
- Statistical p-value computation (paired t-test)
- Matplotlib chart generation (accuracy + latency)

Usage from any node eval script:

    from backend.scripts.evaluations.harness import EvalHarness, EvalCase

    cases = [EvalCase(name="...", input={...}, expected={...})]
    harness = EvalHarness(node_name="topic_extraction", cases=cases, iterations=5)
    asyncio.run(harness.run())
"""

from __future__ import annotations

import json
import logging
import statistics
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")  # headless — no display required

import matplotlib.pyplot as plt
import numpy as np
from scipy import stats

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

FIXTURES_DIR = Path(__file__).parent / "nodes" / "fixtures"
REPORTS_DIR = Path(__file__).parent / "reports"


async def run_and_close(harness: EvalHarness) -> NodeReport:
    """Run the harness and close the LLM client in the *same* event loop."""
    from backend.app.services.llm.client import llm_client  # noqa: E402

    try:
        return await harness.run()
    finally:
        await llm_client.close()


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------
@dataclass
class EvalCase:
    """A single test case for a node evaluation."""

    name: str
    input: dict[str, Any]
    expected: dict[str, Any]
    tags: list[str] = field(default_factory=list)


@dataclass
class TrialResult:
    """Result of a single trial (one invocation of the node on one case)."""

    case_name: str
    iteration: int
    latency_s: float
    accuracy: float
    raw_output: dict[str, Any] | None = None
    error: str | None = None


@dataclass
class CaseReport:
    """Aggregated statistics for all trials of a single test case."""

    case_name: str
    iterations: int
    accuracy_mean: float
    accuracy_std: float
    accuracy_scores: list[float]
    latency_mean_s: float
    latency_std_s: float
    latency_values_s: list[float]
    p_value: float | None  # one-sample t-test against H0: accuracy ≤ 0.5
    passed: bool  # True when mean accuracy ≥ threshold AND p < 0.05


@dataclass
class NodeReport:
    """Full report for a node evaluation run."""

    node_name: str
    total_cases: int
    iterations_per_case: int
    case_reports: list[CaseReport]
    overall_accuracy_mean: float
    overall_latency_mean_s: float
    chart_path: str


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------
def load_fixture(name: str) -> list[EvalCase]:
    """Load eval cases from ``fixtures/<name>.json``."""
    path = FIXTURES_DIR / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(f"Fixture not found: {path}")
    raw = json.loads(path.read_text())
    return [
        EvalCase(
            name=c["name"],
            input=c["input"],
            expected=c["expected"],
            tags=c.get("tags", []),
        )
        for c in raw["cases"]
    ]


# ---------------------------------------------------------------------------
# Default accuracy scorer
# ---------------------------------------------------------------------------
def default_accuracy_scorer(expected: dict, actual: dict) -> float:
    """Score accuracy by comparing top-level keys.

    Returns a float 0.0–1.0 representing the proportion of expected keys
    whose values match (or partially match) the actual output.
    """
    if not expected:
        return 1.0 if actual else 0.0

    scores: list[float] = []
    for key, exp_val in expected.items():
        act_val = actual.get(key)
        if act_val is None:
            scores.append(0.0)
            continue
        if isinstance(exp_val, list) and isinstance(act_val, list):
            scores.append(_list_similarity(exp_val, act_val))
        elif isinstance(exp_val, dict) and isinstance(act_val, dict):
            scores.append(default_accuracy_scorer(exp_val, act_val))
        elif isinstance(exp_val, int | float) and isinstance(act_val, int | float):
            scores.append(_numeric_closeness(exp_val, act_val))
        elif isinstance(exp_val, str) and isinstance(act_val, str):
            scores.append(_string_similarity(exp_val, act_val))
        elif exp_val == act_val:
            scores.append(1.0)
        else:
            scores.append(0.0)
    return statistics.mean(scores) if scores else 0.0


def _list_similarity(expected: list, actual: list) -> float:
    """Score list similarity by comparing element overlap + structure."""
    if not expected:
        return 1.0 if not actual else 0.5

    # For lists of dicts — match by best-pair accuracy
    if expected and isinstance(expected[0], dict):
        return _dict_list_similarity(expected, actual)

    # For lists of scalars — Jaccard-ish overlap
    exp_set = set(str(v).lower() for v in expected)
    act_set = set(str(v).lower() for v in actual)
    if not exp_set:
        return 1.0
    intersection = exp_set & act_set
    union = exp_set | act_set
    return len(intersection) / len(union) if union else 1.0


def _dict_list_similarity(expected: list[dict], actual: list[dict]) -> float:
    """Score similarity between two lists of dicts using greedy best-match."""
    if not actual:
        return 0.0
    total = 0.0
    used: set[int] = set()
    for exp_item in expected:
        best_score = 0.0
        best_idx = -1
        for idx, act_item in enumerate(actual):
            if idx in used:
                continue
            score = default_accuracy_scorer(exp_item, act_item)
            if score > best_score:
                best_score = score
                best_idx = idx
        if best_idx >= 0:
            used.add(best_idx)
        total += best_score
    # Penalise extra items in actual
    length_penalty = min(len(expected), len(actual)) / max(len(expected), len(actual))
    return (total / len(expected)) * length_penalty


def _numeric_closeness(expected: float, actual: float, tolerance: float = 0.15) -> float:
    """Score numeric closeness with a tolerance band."""
    if expected == 0:
        return 1.0 if abs(actual) < tolerance else 0.0
    relative_error = abs(expected - actual) / max(abs(expected), 1e-9)
    if relative_error <= tolerance:
        return 1.0
    return max(0.0, 1.0 - relative_error)


def _string_similarity(expected: str, actual: str) -> float:
    """Simple word-overlap similarity between two strings."""
    exp_words = set(expected.lower().split())
    act_words = set(actual.lower().split())
    if not exp_words:
        return 1.0
    intersection = exp_words & act_words
    union = exp_words | act_words
    return len(intersection) / len(union) if union else 1.0


# ---------------------------------------------------------------------------
# Evaluation harness
# ---------------------------------------------------------------------------
class EvalHarness:
    """Runs repeated trials of a node function against test cases.

    Parameters:
        node_name:      Identifier for the node (used in reports / filenames).
        cases:          List of ``EvalCase`` objects.
        node_fn:        Async callable ``(input: dict) -> dict`` that invokes
                        the LLM node and returns the parsed JSON output.
        iterations:     Number of times to run each case (default 5).
        accuracy_fn:    Optional custom scorer ``(expected, actual) -> float``.
        accuracy_threshold: Minimum acceptable mean accuracy (default 0.7).
    """

    def __init__(
        self,
        *,
        node_name: str,
        cases: list[EvalCase],
        node_fn: Callable[..., Any],
        iterations: int = 5,
        accuracy_fn: Callable[[dict, dict], float] | None = None,
        accuracy_threshold: float = 0.7,
    ) -> None:
        self.node_name = node_name
        self.cases = cases
        self.node_fn = node_fn
        self.iterations = iterations
        self.accuracy_fn = accuracy_fn or default_accuracy_scorer
        self.accuracy_threshold = accuracy_threshold

    # ----- core runner -----
    async def run(self) -> NodeReport:
        """Execute all trials and produce a report + chart."""
        logger.info(
            "=== Evaluating node: %s | %d cases × %d iterations ===",
            self.node_name,
            len(self.cases),
            self.iterations,
        )
        all_trials: list[TrialResult] = []

        for case in self.cases:
            for i in range(self.iterations):
                trial = await self._run_trial(case, i)
                all_trials.append(trial)
                status = "✓" if trial.error is None else f"✗ {trial.error[:60]}"
                logger.info(
                    "  [%s] iter %d/%d  acc=%.2f  lat=%.3fs  %s",
                    case.name,
                    i + 1,
                    self.iterations,
                    trial.accuracy,
                    trial.latency_s,
                    status,
                )

        case_reports = self._aggregate(all_trials)
        overall_acc = statistics.mean(r.accuracy_mean for r in case_reports)
        overall_lat = statistics.mean(r.latency_mean_s for r in case_reports)

        chart_path = self._generate_chart(case_reports)

        report = NodeReport(
            node_name=self.node_name,
            total_cases=len(self.cases),
            iterations_per_case=self.iterations,
            case_reports=case_reports,
            overall_accuracy_mean=overall_acc,
            overall_latency_mean_s=overall_lat,
            chart_path=str(chart_path),
        )

        self._print_summary(report)
        self._save_json_report(report)
        return report

    # ----- single trial -----
    async def _run_trial(self, case: EvalCase, iteration: int) -> TrialResult:
        try:
            start = time.perf_counter()
            raw_output = await self.node_fn(case.input)
            elapsed = time.perf_counter() - start

            accuracy = self.accuracy_fn(case.expected, raw_output)
            return TrialResult(
                case_name=case.name,
                iteration=iteration,
                latency_s=elapsed,
                accuracy=accuracy,
                raw_output=raw_output,
            )
        except Exception as exc:
            return TrialResult(
                case_name=case.name,
                iteration=iteration,
                latency_s=0.0,
                accuracy=0.0,
                error=str(exc),
            )

    # ----- aggregation + stats -----
    def _aggregate(self, trials: list[TrialResult]) -> list[CaseReport]:
        by_case: dict[str, list[TrialResult]] = {}
        for t in trials:
            by_case.setdefault(t.case_name, []).append(t)

        reports: list[CaseReport] = []
        for case_name, case_trials in by_case.items():
            accs = [t.accuracy for t in case_trials]
            lats = [t.latency_s for t in case_trials]

            p_value = None
            if len(accs) >= 3:
                # One-sample t-test: H0 = mean accuracy ≤ 0.5 (chance level)
                t_stat, two_sided_p = stats.ttest_1samp(accs, 0.5)
                # Convert to one-sided (we care about accuracy > 0.5)
                one_sided_p = two_sided_p / 2 if t_stat > 0 else 1 - two_sided_p / 2
                p_value = float(one_sided_p)

            passed = statistics.mean(accs) >= self.accuracy_threshold and (
                p_value is not None and p_value < 0.05
            )

            reports.append(
                CaseReport(
                    case_name=case_name,
                    iterations=len(case_trials),
                    accuracy_mean=statistics.mean(accs),
                    accuracy_std=statistics.stdev(accs) if len(accs) > 1 else 0.0,
                    accuracy_scores=accs,
                    latency_mean_s=statistics.mean(lats),
                    latency_std_s=statistics.stdev(lats) if len(lats) > 1 else 0.0,
                    latency_values_s=lats,
                    p_value=p_value,
                    passed=passed,
                )
            )
        return reports

    # ----- charting -----
    def _generate_chart(self, reports: list[CaseReport]) -> Path:
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)

        case_names = [r.case_name for r in reports]
        acc_means = [r.accuracy_mean for r in reports]
        acc_stds = [r.accuracy_std for r in reports]
        lat_means = [r.latency_mean_s for r in reports]
        lat_stds = [r.latency_std_s for r in reports]
        p_values = [r.p_value for r in reports]

        fig, (ax_acc, ax_lat) = plt.subplots(1, 2, figsize=(14, 6))
        fig.suptitle(
            f"Node Evaluation: {self.node_name}\n" f"({self.iterations} iterations per case)",
            fontsize=14,
            fontweight="bold",
        )

        x = np.arange(len(case_names))
        bar_width = 0.6

        # --- Accuracy subplot ---
        colors_acc = []
        for acc, p in zip(acc_means, p_values, strict=False):
            if acc >= self.accuracy_threshold and p is not None and p < 0.05:
                colors_acc.append("#2ecc71")  # green — pass
            elif acc >= self.accuracy_threshold:
                colors_acc.append("#f39c12")  # orange — high acc but p ≥ 0.05
            else:
                colors_acc.append("#e74c3c")  # red — fail

        bars_acc = ax_acc.bar(
            x,
            acc_means,
            bar_width,
            yerr=acc_stds,
            capsize=4,
            color=colors_acc,
            edgecolor="white",
            linewidth=0.8,
        )
        ax_acc.axhline(
            y=self.accuracy_threshold,
            color="#95a5a6",
            linestyle="--",
            linewidth=1,
            label=f"Threshold ({self.accuracy_threshold:.0%})",
        )
        ax_acc.set_ylabel("Accuracy")
        ax_acc.set_title("Accuracy (mean ± std)")
        ax_acc.set_xticks(x)
        ax_acc.set_xticklabels(case_names, rotation=30, ha="right", fontsize=8)
        ax_acc.set_ylim(0, 1.15)
        ax_acc.legend(fontsize=8)

        # Annotate p-values
        for i, (bar, p) in enumerate(zip(bars_acc, p_values, strict=False)):
            p_text = f"p={p:.3f}" if p is not None else "p=N/A"
            ax_acc.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + acc_stds[i] + 0.03,
                p_text,
                ha="center",
                va="bottom",
                fontsize=7,
                fontstyle="italic",
            )

        # --- Latency subplot ---
        bars_lat = ax_lat.bar(
            x,
            lat_means,
            bar_width,
            yerr=lat_stds,
            capsize=4,
            color="#3498db",
            edgecolor="white",
            linewidth=0.8,
        )
        ax_lat.set_ylabel("Latency (seconds)")
        ax_lat.set_title("Latency (mean ± std)")
        ax_lat.set_xticks(x)
        ax_lat.set_xticklabels(case_names, rotation=30, ha="right", fontsize=8)

        # Annotate latency values
        for bar, lat, std in zip(bars_lat, lat_means, lat_stds, strict=False):
            ax_lat.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + std + 0.05,
                f"{lat:.2f}s",
                ha="center",
                va="bottom",
                fontsize=7,
            )

        plt.tight_layout()
        chart_path = REPORTS_DIR / f"{self.node_name}_eval.png"
        fig.savefig(chart_path, dpi=150, bbox_inches="tight")
        plt.close(fig)

        logger.info("Chart saved → %s", chart_path)
        return chart_path

    # ----- summaries -----
    def _print_summary(self, report: NodeReport) -> None:
        print("\n" + "=" * 70)
        print(f"  NODE EVALUATION REPORT: {report.node_name}")
        print("=" * 70)
        print(
            f"  Cases: {report.total_cases}  |  "
            f"Iterations per case: {report.iterations_per_case}"
        )
        print(f"  Overall accuracy (mean): {report.overall_accuracy_mean:.2%}")
        print(f"  Overall latency  (mean): {report.overall_latency_mean_s:.3f}s")
        print("-" * 70)
        for cr in report.case_reports:
            status = "PASS ✓" if cr.passed else "FAIL ✗"
            p_str = f"{cr.p_value:.4f}" if cr.p_value is not None else "N/A"
            print(
                f"  {status}  {cr.case_name:<30}  "
                f"acc={cr.accuracy_mean:.2%}±{cr.accuracy_std:.2%}  "
                f"lat={cr.latency_mean_s:.3f}s±{cr.latency_std_s:.3f}s  "
                f"p={p_str}"
            )
        print("=" * 70)
        print(f"  Chart: {report.chart_path}")
        print("=" * 70 + "\n")

    def _save_json_report(self, report: NodeReport) -> None:
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        path = REPORTS_DIR / f"{report.node_name}_eval.json"
        data = {
            "node_name": report.node_name,
            "total_cases": report.total_cases,
            "iterations_per_case": report.iterations_per_case,
            "overall_accuracy_mean": report.overall_accuracy_mean,
            "overall_latency_mean_s": report.overall_latency_mean_s,
            "chart_path": report.chart_path,
            "cases": [
                {
                    "case_name": cr.case_name,
                    "iterations": cr.iterations,
                    "accuracy_mean": cr.accuracy_mean,
                    "accuracy_std": cr.accuracy_std,
                    "accuracy_scores": cr.accuracy_scores,
                    "latency_mean_s": cr.latency_mean_s,
                    "latency_std_s": cr.latency_std_s,
                    "latency_values_s": cr.latency_values_s,
                    "p_value": cr.p_value,
                    "passed": cr.passed,
                }
                for cr in report.case_reports
            ],
        }
        path.write_text(json.dumps(data, indent=2))
        logger.info("JSON report saved → %s", path)
