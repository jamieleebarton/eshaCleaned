#!/usr/bin/env python3
"""Run Hestia's sparse cascade planner from this bundle's local tensor cache."""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List

from pricing_guard import assert_no_default_priced_ingredients


ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "implementation" / "output" / "sparse_cascade_planner"
DEFAULT_HESTIA_API = Path("/Users/jamiebarton/Desktop/Hestia/api")
DEFAULT_RECIPES_CSV = OUT_DIR / "recipe_qa_calculator_native.csv"
DEFAULT_PACKAGE_DB = OUT_DIR / "food_packages_calculator_native.db"
DEFAULT_INGREDIENT_META = OUT_DIR / "ingredient_meta.json"
DEFAULT_TENSOR_CACHE_DIR = OUT_DIR / "tensor_cache"
DEFAULT_OUT_JSON = OUT_DIR / "local_sparse_plan.smoke.json"
DEFAULT_OUT_CSV = OUT_DIR / "local_sparse_plan.smoke.meals.csv"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hestia-api", type=Path, default=DEFAULT_HESTIA_API)
    parser.add_argument("--recipes-csv", type=Path, default=DEFAULT_RECIPES_CSV)
    parser.add_argument("--package-db", type=Path, default=DEFAULT_PACKAGE_DB)
    parser.add_argument("--ingredient-meta", type=Path, default=DEFAULT_INGREDIENT_META)
    parser.add_argument("--tensor-cache-dir", type=Path, default=DEFAULT_TENSOR_CACHE_DIR)
    parser.add_argument("--out-json", type=Path, default=DEFAULT_OUT_JSON)
    parser.add_argument("--out-csv", type=Path, default=DEFAULT_OUT_CSV)
    parser.add_argument("--weeks", type=int, default=1)
    parser.add_argument("--k", type=int, default=32)
    parser.add_argument("--purchase-limit", type=int, default=30)
    parser.add_argument("--device", default="cpu")
    parser.add_argument(
        "--scoring-preset",
        choices=("budget", "balanced", "high_protein"),
        default="budget",
    )
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


def meal_rows(week: int, selections: Iterable[Any]) -> List[Dict[str, Any]]:
    meal_names = ["breakfast", "lunch", "dinner"]
    day_names = [
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
        "Sunday",
    ]
    rows: List[Dict[str, Any]] = []
    for slot, selection in enumerate(selections):
        values = list(selection)
        day_idx = slot // 3
        meal_idx = slot % 3
        if len(values) >= 10:
            main_id, side_id, side2_id, main_name, side_name, side2_name, meal_cost = values[:7]
        else:
            main_id, side_id, main_name, side_name, meal_cost = values[:5]
            side2_id, side2_name = 0, ""
        rows.append(
            {
                "week": week,
                "slot": slot,
                "day": day_names[day_idx] if day_idx < len(day_names) else str(day_idx + 1),
                "meal": meal_names[meal_idx] if meal_idx < len(meal_names) else str(meal_idx),
                "main_id": int(main_id or 0),
                "main_name": str(main_name or ""),
                "side_id": int(side_id or 0),
                "side_name": str(side_name or ""),
                "side2_id": int(side2_id or 0),
                "side2_name": str(side2_name or ""),
                "meal_cost": round(float(meal_cost or 0.0), 4),
            }
        )
    return rows


def top_purchases(result: Dict[str, Any], ingredient_index, package_index, limit: int = 30) -> List[Dict[str, Any]]:
    purchases = result.get("ingredient_purchases")
    if purchases is None:
        return []
    purchases_cpu = purchases.detach().cpu()
    sizes_cpu = package_index._gpu_sizes.detach().cpu()
    prices_cpu = package_index._gpu_prices.detach().cpu()

    rows = []
    for idx, package_count in enumerate(purchases_cpu.tolist()):
        if package_count <= 0:
            continue
        key = ingredient_index.idx_to_fpid.get(idx, "")
        packages = float(package_count)
        rows.append(
            {
                "ingredient_key": key,
                "packages": packages,
                "grams": round(packages * float(sizes_cpu[idx]), 2),
                "cost": round(packages * float(prices_cpu[idx]), 2),
            }
        )
    rows.sort(key=lambda row: row["cost"], reverse=True)
    return rows[:limit]


def tensor_mass_kg(tensor: Any) -> float:
    if tensor is None:
        return 0.0
    return float(tensor.detach().cpu().sum().item()) / 1000.0


def main() -> None:
    args = parse_args()
    hestia_api = args.hestia_api.expanduser().resolve()
    recipes_csv = args.recipes_csv.expanduser().resolve()
    package_db = args.package_db.expanduser().resolve()
    ingredient_meta = args.ingredient_meta.expanduser().resolve()
    cache_dir = args.tensor_cache_dir.expanduser().resolve()
    out_json = args.out_json.expanduser().resolve()
    out_csv = args.out_csv.expanduser().resolve()

    for label, path in {
        "Hestia API": hestia_api,
        "recipes CSV": recipes_csv,
        "package DB": package_db,
        "ingredient meta": ingredient_meta,
        "tensor cache": cache_dir / "recipe_db_tensors.pt",
    }.items():
        if not path.exists():
            raise FileNotFoundError(f"{label} not found: {path}")

    os.environ["HESTIA_RECIPES_CSV"] = str(recipes_csv)
    os.environ["HESTIA_PACKAGES_DB"] = str(package_db)
    os.environ["HESTIA_INGREDIENT_META_JSON"] = str(ingredient_meta)
    os.environ["HESTIA_TENSOR_CACHE_DIR"] = str(cache_dir)
    os.environ.setdefault("HESTIA_SKIP_TENSOR_STALENESS_CHECK", "1")
    sys.path.insert(0, str(hestia_api))

    import torch
    import hestia.sparse_cascade as sparse_cascade
    from hestia.data_structures import PackageIndex
    from hestia.plate_builder import PlateBuilder
    from hestia.scoring_config import ScoringConfig

    sparse_cascade.BASE_PATH = str(ROOT)
    device = torch.device(args.device)

    plate_builder = PlateBuilder(templates_dir=str(hestia_api / "assets" / "plate_templates"))
    recipe_db = sparse_cascade.SparseRecipeDatabase.from_cache(device, plate_builder=plate_builder)

    package_index = PackageIndex(packages_db=str(package_db))
    assert_no_default_priced_ingredients(
        recipe_db.ingredient_index,
        package_index,
        context="Local sparse planner run",
    )
    package_index.build_gpu_tensors(recipe_db.ingredient_index, device)

    if args.scoring_preset == "balanced":
        scoring_config = ScoringConfig.balanced()
    elif args.scoring_preset == "high_protein":
        scoring_config = ScoringConfig.high_protein()
    else:
        scoring_config = ScoringConfig.budget()

    planner = sparse_cascade.SparseCascadePlanner(
        recipe_db=recipe_db,
        package_index=package_index,
        device=device,
        K=args.k,
        scoring_config=scoring_config,
        verbose=args.verbose,
    )

    pantry = torch.zeros(recipe_db.ingredient_index.num_ingredients, device=device)
    pantry_ttl = None
    pantry_frozen = None
    leftovers = None
    historical: List[int] = []

    all_meals: List[Dict[str, Any]] = []
    weeks: List[Dict[str, Any]] = []
    for week in range(1, args.weeks + 1):
        result = planner.start_session(
            initial_pantry=pantry,
            historical_banned_ids=historical,
            initial_leftovers=leftovers,
            week_number=week - 1,
            initial_pantry_ttl=pantry_ttl,
            initial_pantry_frozen=pantry_frozen,
        ).plan_next_week()

        rows = meal_rows(week, result.get("selections", []))
        all_meals.extend(rows)
        historical.extend(int(rid) for rid in result.get("used_recipe_ids", []))
        historical = historical[-120:]
        pantry = result.get("final_pantry", pantry).to(device)
        pantry_ttl = result.get("final_pantry_ttl", pantry_ttl)
        pantry_frozen = result.get("final_pantry_frozen", pantry_frozen)
        leftovers = result.get("final_leftovers", leftovers)

        weeks.append(
            {
                "week": week,
                "total_cost": round(float(result.get("total_cost", 0.0)), 4),
                "cal_compliance": round(float(result.get("cal_compliance", 0.0)), 4),
                "prot_compliance": round(float(result.get("prot_compliance", 0.0)), 4),
                "vegetables_g": round(float(result.get("vegetables_g", 0.0)), 2),
                "fruits_g": round(float(result.get("fruits_g", 0.0)), 2),
                "protein_pct": round(float(result.get("protein_pct", 0.0)), 4),
                "carbs_pct": round(float(result.get("carbs_pct", 0.0)), 4),
                "fat_pct": round(float(result.get("fat_pct", 0.0)), 4),
                "elapsed_seconds": round(float(result.get("elapsed_seconds", 0.0)), 4),
                "pantry_kg_after": round(tensor_mass_kg(pantry), 4),
                "top_purchases": top_purchases(
                    result,
                    recipe_db.ingredient_index,
                    package_index,
                    limit=args.purchase_limit,
                ),
            }
        )

    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(
        json.dumps(
            {
                "settings": {
                    "weeks": args.weeks,
                    "k": args.k,
                    "device": args.device,
                    "scoring_preset": args.scoring_preset,
                    "recipes_csv": str(recipes_csv),
                    "package_db": str(package_db),
                    "tensor_cache_dir": str(cache_dir),
                },
                "recipe_db": {
                    "recipes": int(recipe_db.num_recipes),
                    "ingredient_keys": int(recipe_db.ingredient_index.num_ingredients),
                },
                "weeks": weeks,
                "meals": all_meals,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    with out_csv.open("w", encoding="utf-8", newline="") as handle:
        fieldnames = [
            "week",
            "slot",
            "day",
            "meal",
            "main_id",
            "main_name",
            "side_id",
            "side_name",
            "side2_id",
            "side2_name",
            "meal_cost",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_meals)

    print(json.dumps({"out_json": str(out_json), "out_csv": str(out_csv), "weeks": weeks}, indent=2))


if __name__ == "__main__":
    main()
