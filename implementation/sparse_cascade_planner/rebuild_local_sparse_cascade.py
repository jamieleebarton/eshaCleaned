#!/usr/bin/env python3
"""Rebuild the local sparse-cascade planner artifacts end to end."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
IMPLEMENTATION = ROOT / "implementation"
OUT_DIR = IMPLEMENTATION / "output" / "sparse_cascade_planner"

SOURCE_INVENTORY = OUT_DIR / "source_inventory.json"
PRODUCT_BRIDGE = OUT_DIR / "product_identity_bridge.csv"
PRODUCT_BRIDGE_SUMMARY = OUT_DIR / "product_identity_bridge.summary.json"
RETAIL_BRIDGE = IMPLEMENTATION / "output" / "retail_canonical_surface_bridge.csv"
PACKAGE_DB = OUT_DIR / "food_packages_calculator_native.db"
PACKAGE_SUMMARY = OUT_DIR / "food_packages_calculator_native.summary.json"
RECIPES_CSV = OUT_DIR / "recipe_qa_calculator_native.csv"
RECIPES_SUMMARY = OUT_DIR / "recipe_qa_calculator_native.summary.json"
INGREDIENT_META = OUT_DIR / "ingredient_meta.json"
TENSOR_CACHE_DIR = OUT_DIR / "tensor_cache"
TENSOR_SUMMARY = TENSOR_CACHE_DIR / "tensor_cache.summary.json"
SMOKE_JSON = OUT_DIR / "local_sparse_plan.smoke.json"
SMOKE_CSV = OUT_DIR / "local_sparse_plan.smoke.meals.csv"
VERIFY_JSON = OUT_DIR / "local_sparse_build_verification.json"
VERIFY_MD = OUT_DIR / "local_sparse_build_verification.md"
BUILD_SUMMARY = OUT_DIR / "local_sparse_cascade_build.summary.json"


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def run_step(name: str, argv: list[str]) -> dict[str, Any]:
    print(f"\n{'=' * 72}\n{name}\n{'=' * 72}", flush=True)
    start = time.monotonic()
    subprocess.run(argv, cwd=str(ROOT), check=True)
    elapsed = round(time.monotonic() - start, 3)
    print(f"{name} finished in {elapsed}s", flush=True)
    return {"name": name, "elapsed_seconds": elapsed, "argv": argv}


def artifact_summary(steps: list[dict[str, Any]]) -> dict[str, Any]:
    product_bridge = load_json(PRODUCT_BRIDGE_SUMMARY)
    package_summary = load_json(PACKAGE_SUMMARY)
    recipe_summary = load_json(RECIPES_SUMMARY)
    tensor_summary = load_json(TENSOR_SUMMARY)
    smoke = load_json(SMOKE_JSON)
    verification = load_json(VERIFY_JSON)

    package_payload = package_summary.get("packages") or package_summary
    first_week = (smoke.get("weeks") or [{}])[0]
    return {
        "steps": steps,
        "artifacts": {
            "source_inventory": str(SOURCE_INVENTORY),
            "product_identity_bridge": str(PRODUCT_BRIDGE),
            "package_db": str(PACKAGE_DB),
            "recipes_csv": str(RECIPES_CSV),
            "ingredient_meta": str(INGREDIENT_META),
            "tensor_cache_dir": str(TENSOR_CACHE_DIR),
            "smoke_json": str(SMOKE_JSON),
            "verification_json": str(VERIFY_JSON),
            "verification_markdown": str(VERIFY_MD),
        },
        "counts": {
            "product_bridge_rows": product_bridge.get("row_count"),
            "product_bridge_keys": product_bridge.get("ingredient_keys"),
            "package_rows": package_payload.get("package_rows"),
            "package_keys": package_payload.get("ingredient_keys"),
            "recipe_rows": (recipe_summary.get("stats") or {}).get("recipes_written"),
            "recipe_source_rows": (recipe_summary.get("stats") or {}).get("recipes_seen"),
            "recipe_price_keys": recipe_summary.get("price_key_count"),
            "tensor_recipes": tensor_summary.get("tensor_recipes"),
            "tensor_ingredient_keys": tensor_summary.get("ingredient_keys"),
            "tensor_package_summary": tensor_summary.get("package_summary"),
        },
        "smoke": {
            "week_cost": first_week.get("total_cost"),
            "cal_compliance": first_week.get("cal_compliance"),
            "prot_compliance": first_week.get("prot_compliance"),
            "elapsed_seconds": first_week.get("elapsed_seconds"),
        },
        "verification": {
            "plan_passed": (verification.get("plan_gate") or {}).get("passed"),
            "priced_grams_pct": (verification.get("coverage") or {}).get("priced_grams_pct"),
            "product_leak_checks": verification.get("bad_product_checks"),
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", default=sys.executable, help="Python executable to use for child steps.")
    parser.add_argument("--hestia-api", type=Path, default=Path("/Users/jamiebarton/Desktop/Hestia/api"))
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--smoke-weeks", type=int, default=1)
    parser.add_argument("--smoke-k", type=int, default=32)
    parser.add_argument("--scoring-preset", choices=("budget", "balanced", "high_protein"), default="budget")
    parser.add_argument("--skip-source-inventory", action="store_true")
    parser.add_argument("--skip-recipe-export", action="store_true")
    parser.add_argument("--skip-tensor-cache", action="store_true")
    parser.add_argument("--skip-smoke", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    python = args.python
    hestia_api = args.hestia_api.expanduser()
    steps: list[dict[str, Any]] = []

    if not args.skip_source_inventory:
        steps.append(
            run_step(
                "source inventory",
                [python, "implementation/sparse_cascade_planner/source_inventory.py", "--out", str(SOURCE_INVENTORY)],
            )
        )

    steps.append(
        run_step(
            "product identity bridge",
            [
                python,
                "implementation/sparse_cascade_planner/build_product_identity_bridge.py",
                "--out-csv",
                str(PRODUCT_BRIDGE),
                "--out-summary",
                str(PRODUCT_BRIDGE_SUMMARY),
            ],
        )
    )

    steps.append(
        run_step(
            "package database",
            [
                python,
                "implementation/build_hestia_esha_native_artifacts.py",
                "--skip-recipes",
                "--bridge-csv",
                str(RETAIL_BRIDGE),
                "--out-package-db",
                str(PACKAGE_DB),
                "--out-package-summary",
                str(PACKAGE_SUMMARY),
                "--product-identity-bridge-csv",
                str(PRODUCT_BRIDGE),
            ],
        )
    )

    if not args.skip_recipe_export:
        steps.append(
            run_step(
                "recipe native export",
                [
                    python,
                    "implementation/sparse_cascade_planner/build_recipe_qa_native_recipes.py",
                    "--package-db",
                    str(PACKAGE_DB),
                    "--out-csv",
                    str(RECIPES_CSV),
                    "--out-summary",
                    str(RECIPES_SUMMARY),
                    "--out-meta",
                    str(INGREDIENT_META),
                ],
            )
        )

    if not args.skip_tensor_cache:
        steps.append(
            run_step(
                "tensor cache",
                [
                    python,
                    "implementation/sparse_cascade_planner/build_tensor_cache.py",
                    "--hestia-api",
                    str(hestia_api),
                    "--recipes-csv",
                    str(RECIPES_CSV),
                    "--package-db",
                    str(PACKAGE_DB),
                    "--ingredient-meta",
                    str(INGREDIENT_META),
                    "--tensor-cache-dir",
                    str(TENSOR_CACHE_DIR),
                    "--device",
                    args.device,
                ],
            )
        )

    if not args.skip_smoke:
        steps.append(
            run_step(
                "local planner smoke",
                [
                    python,
                    "implementation/sparse_cascade_planner/run_local_sparse_plan.py",
                    "--hestia-api",
                    str(hestia_api),
                    "--recipes-csv",
                    str(RECIPES_CSV),
                    "--package-db",
                    str(PACKAGE_DB),
                    "--ingredient-meta",
                    str(INGREDIENT_META),
                    "--tensor-cache-dir",
                    str(TENSOR_CACHE_DIR),
                    "--out-json",
                    str(SMOKE_JSON),
                    "--out-csv",
                    str(SMOKE_CSV),
                    "--weeks",
                    str(args.smoke_weeks),
                    "--k",
                    str(args.smoke_k),
                    "--device",
                    args.device,
                    "--scoring-preset",
                    args.scoring_preset,
                ],
            )
        )

    steps.append(run_step("verification", [python, "implementation/sparse_cascade_planner/verify_local_build.py"]))

    summary = artifact_summary(steps)
    BUILD_SUMMARY.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if (summary.get("verification") or {}).get("plan_passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
