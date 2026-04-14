#!/usr/bin/env python3
"""Run all node evaluations (or a specific one).

Usage:
    # Run ALL node evaluations (5 iterations each):
    python -m backend.scripts.evaluations.run_all

    # Run a specific node:
    python -m backend.scripts.evaluations.run_all --node topic_extraction

    # Override iteration count:
    python -m backend.scripts.evaluations.run_all --iterations 10
"""

from __future__ import annotations

import argparse
import subprocess
import sys

NODES = [
    "topic_extraction",
    "profile_update",
    "quiz_generation",
    "quiz_evaluation",
    "reading_generation",
    "project_generation",
    "project_evaluation",
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Run node evaluation scripts")
    parser.add_argument(
        "--node",
        choices=NODES,
        default=None,
        help="Run only this node evaluation (default: all)",
    )
    parser.add_argument(
        "--iterations",
        "-n",
        type=int,
        default=5,
        help="Number of iterations per test case (default: 5)",
    )
    args = parser.parse_args()

    targets = [args.node] if args.node else NODES

    results: dict[str, bool] = {}
    for node in targets:
        print(f"\n{'='*70}")
        print(f"  Running evaluation: {node}")
        print(f"{'='*70}\n")

        module = f"backend.scripts.evaluations.nodes.eval_{node}"
        ret = subprocess.run(
            [sys.executable, "-m", module, "--iterations", str(args.iterations)],
            cwd=str(_project_root()),
            check=False,
        )
        results[node] = ret.returncode == 0

    # Summary
    print(f"\n{'='*70}")
    print("  EVALUATION SUMMARY")
    print(f"{'='*70}")
    for node, success in results.items():
        icon = "✓" if success else "✗"
        print(f"  {icon}  {node}")
    print(f"{'='*70}\n")

    if not all(results.values()):
        sys.exit(1)


def _project_root():
    from pathlib import Path

    return Path(__file__).resolve().parents[3]


if __name__ == "__main__":
    main()
