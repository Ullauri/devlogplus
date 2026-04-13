#!/usr/bin/env python3
"""Export the OpenAPI specification from the FastAPI application.

Usage:
    python scripts/export_openapi.py              # writes docs/openapi.json
    python scripts/export_openapi.py --yaml       # writes docs/openapi.yaml
    python scripts/export_openapi.py --check      # exits 1 if spec on disk is stale
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# ── Resolve project root so imports work regardless of cwd ─────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.main import app  # noqa: E402


def _get_spec_json() -> str:
    """Return the OpenAPI spec as a pretty-printed JSON string."""
    return json.dumps(app.openapi(), indent=2, ensure_ascii=False) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Export the DevLog+ OpenAPI specification.")
    parser.add_argument(
        "--yaml",
        action="store_true",
        help="Also write a YAML version (requires PyYAML).",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check that the spec on disk is up to date (CI mode). Exit 1 if stale.",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "docs",
        help="Directory to write the spec files to (default: docs/).",
    )
    args = parser.parse_args()

    spec_json = _get_spec_json()
    json_path: Path = args.output_dir / "openapi.json"

    # ── Check mode ─────────────────────────────────────────────────────────
    if args.check:
        if not json_path.exists():
            print(f"✗ {json_path} does not exist. Run `make openapi` to generate it.")
            raise SystemExit(1)
        if json_path.read_text(encoding="utf-8") != spec_json:
            print(f"✗ {json_path} is out of date. Run `make openapi` to regenerate it.")
            raise SystemExit(1)
        print(f"✓ {json_path} is up to date.")
        return

    # ── Write JSON ─────────────────────────────────────────────────────────
    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path.write_text(spec_json, encoding="utf-8")
    print(f"✓ Wrote {json_path}  ({len(spec_json):,} bytes)")

    # ── Optionally write YAML ──────────────────────────────────────────────
    if args.yaml:
        try:
            import yaml  # type: ignore[import-untyped]
        except ImportError:
            print("⚠ PyYAML not installed — skipping YAML output.", file=sys.stderr)
            return

        yaml_path = args.output_dir / "openapi.yaml"
        spec_dict = json.loads(spec_json)
        yaml_str = yaml.dump(spec_dict, default_flow_style=False, sort_keys=False, allow_unicode=True)
        yaml_path.write_text(yaml_str, encoding="utf-8")
        print(f"✓ Wrote {yaml_path}  ({len(yaml_str):,} bytes)")


if __name__ == "__main__":
    main()
