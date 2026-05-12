"""Run sparse_cascade for one week (household=4) and dump:
- selections: list of (recipe_id, recipe_name, meal_slot, meal_cost)
- per recipe: fndds_grams_dict from recipes2.csv
- per fndds_code: candidate packages from food_packages_final.db (name, brand, upc, weight, prices, ingredients)

Output: implementation/output/ruvs/real_plan/plan.json
"""
from __future__ import annotations
import ast
import csv
import json
import os
import sqlite3
import sys
from pathlib import Path

HESTIA_API = "/Users/jamiebarton/Desktop/Hestia/api"
sys.path.insert(0, HESTIA_API)
os.environ.setdefault("BASE_PATH", HESTIA_API)
os.chdir(HESTIA_API)  # planner uses relative paths to data/

OUT_DIR = Path("/Users/jamiebarton/Desktop/esha_audit_bundle/implementation/output/ruvs/real_plan")
OUT_DIR.mkdir(parents=True, exist_ok=True)
RECIPES_CSV = Path(HESTIA_API) / "data" / "recipes2.csv"
PACKAGES_DB = Path(HESTIA_API) / "data" / "food_packages_final.db"


def run_planner():
    """Mirror run_sparse_cascade() setup but capture the result dict."""
    import torch
    from hestia.data_loader import load_recipes
    from hestia.data_structures import IngredientIndex, PackageIndex
    from hestia.plate_builder import PlateBuilder
    from hestia.sparse_cascade import SparseRecipeDatabase, SparseCascadePlanner

    print("Loading recipes...", flush=True, file=sys.stderr)
    recipe_pool = load_recipes("recipes2.csv")

    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print(f"Device: {device}  recipes: {len(recipe_pool):,}", flush=True, file=sys.stderr)

    ingredient_index = IngredientIndex(device)
    ingredient_index.build_from_recipes(recipe_pool)

    plate_builder = PlateBuilder()
    plate_builder.index_recipes(recipe_pool)

    package_index = PackageIndex()
    recipe_db = SparseRecipeDatabase(recipe_pool, ingredient_index, plate_builder, device)

    pantry_file = f'{HESTIA_API}/pantry_state.json'
    initial_pantry = torch.zeros(ingredient_index.num_ingredients, device=device)
    try:
        with open(pantry_file) as f:
            pantry_dict = json.load(f)
        for fpid, grams in pantry_dict.items():
            idx = ingredient_index.fpid_to_idx.get(fpid)
            if idx is not None:
                initial_pantry[idx] = grams
        print(f"Pantry seeded with {len(pantry_dict)} ingredients", file=sys.stderr)
    except FileNotFoundError:
        print("No pantry file; starting empty", file=sys.stderr)

    try:
        with open(f"{HESTIA_API}/recent_recipes.json") as f:
            historical = list(json.load(f))
    except FileNotFoundError:
        historical = []

    planner = SparseCascadePlanner(
        recipe_db=recipe_db, package_index=package_index, device=device,
        K=200, verbose=False,
    )
    print("Running plan...", flush=True, file=sys.stderr)
    result = planner.start_session(
        initial_pantry=initial_pantry,
        historical_banned_ids=historical,
    ).plan_next_week()
    return result, ingredient_index


def load_recipes_index() -> dict[int, dict]:
    """recipe_id -> {name, fndds_grams_dict}."""
    out: dict[int, dict] = {}
    with RECIPES_CSV.open(encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                rid = int(row["recipeNum"])
            except (ValueError, KeyError):
                continue
            try:
                grams = ast.literal_eval(row["fndds_grams_dict"]) if row.get("fndds_grams_dict") else {}
            except (ValueError, SyntaxError):
                grams = {}
            out[rid] = {"name": row.get("recipeName", ""), "fndds_grams_dict": grams}
    return out


def packages_for(conn: sqlite3.Connection, fndds_code: str) -> list[dict]:
    """Pull all package candidates for a given fndds_code."""
    rows = conn.execute(
        "SELECT fndds_code, food_description, package_weight_grams, "
        "walmart_price_cents, kroger_price_cents, source, product_meta, confidence_tier "
        "FROM packages WHERE fndds_code = ? ORDER BY confidence_tier DESC, package_weight_grams",
        (str(fndds_code),),
    ).fetchall()
    out = []
    for r in rows:
        meta = {}
        try:
            meta = json.loads(r[6]) if r[6] else {}
        except (json.JSONDecodeError, TypeError):
            pass
        out.append({
            "fndds_code": r[0],
            "food_description": r[1],
            "package_weight_grams": r[2],
            "walmart_price_cents": r[3],
            "kroger_price_cents": r[4],
            "source": r[5],
            "confidence_tier": r[7],
            "name": meta.get("name") or meta.get("walmart_name", ""),
            "brand": meta.get("brand") or meta.get("walmart_brand", ""),
            "upc": meta.get("upc", ""),
            "categories": meta.get("categories", []),
            "ingredient_statement": meta.get("ingredient_statement", ""),
        })
    return out


def normalize_selection(sel) -> dict:
    """Unpack the planner's tuple format (10-tuple new fmt or 7-tuple old)."""
    if len(sel) >= 10:
        return {
            "main_id": int(sel[0]) if sel[0] else None,
            "side_id": int(sel[1]) if sel[1] else None,
            "side2_id": int(sel[2]) if sel[2] else None,
            "main_name": sel[3], "side_name": sel[4], "side2_name": sel[5],
            "meal_cost": float(sel[6]),
        }
    return {
        "main_id": int(sel[0]) if sel[0] else None,
        "side_id": int(sel[1]) if sel[1] else None,
        "side2_id": None,
        "main_name": sel[2], "side_name": sel[3], "side2_name": "",
        "meal_cost": float(sel[4]),
    }


def main() -> int:
    result, ingredient_index = run_planner()
    selections = result["selections"]
    total_cost = float(result["total_cost"])

    recipes = load_recipes_index()
    print(f"Indexed {len(recipes):,} recipes from recipes2.csv", file=sys.stderr)

    conn = sqlite3.connect(PACKAGES_DB)
    days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
    meals = ['breakfast', 'lunch', 'dinner']

    plan = {"total_cost_usd": total_cost, "household": 4, "weeks": 1, "meals": []}
    used_recipe_ids: set[int] = set()
    for i, sel in enumerate(selections):
        s = normalize_selection(sel)
        day = days[i // 3]
        meal = meals[i % 3]
        for slot in ("main_id", "side_id", "side2_id"):
            rid = s.get(slot)
            if rid:
                used_recipe_ids.add(rid)
        plan["meals"].append({"day": day, "meal": meal, **s})

    # Resolve ingredients per used recipe + candidate packages per fndds_code
    fndds_seen: set[str] = set()
    plan["recipes"] = {}
    for rid in sorted(used_recipe_ids):
        rec = recipes.get(rid)
        if not rec:
            plan["recipes"][str(rid)] = {"name": "(not found in recipes2.csv)", "ingredients": {}}
            continue
        ingredients_resolved: dict[str, dict] = {}
        for fndds_code, grams in rec["fndds_grams_dict"].items():
            fndds_str = str(fndds_code)
            fndds_seen.add(fndds_str)
            ingredients_resolved[fndds_str] = {
                "grams": float(grams),
                "candidates": packages_for(conn, fndds_str),
            }
        plan["recipes"][str(rid)] = {"name": rec["name"], "ingredients": ingredients_resolved}

    # Quick stats
    n_recipes = len(plan["recipes"])
    n_fndds = len(fndds_seen)
    n_with_candidates = sum(1 for r in plan["recipes"].values()
                            for ing in r["ingredients"].values() if ing["candidates"])
    n_without = sum(1 for r in plan["recipes"].values()
                    for ing in r["ingredients"].values() if not ing["candidates"])
    plan["stats"] = {
        "n_distinct_recipes": n_recipes,
        "n_distinct_fndds_codes": n_fndds,
        "n_ingredient_lines_with_candidates": n_with_candidates,
        "n_ingredient_lines_without_candidates": n_without,
    }

    out_path = OUT_DIR / "plan.json"
    out_path.write_text(json.dumps(plan, indent=2))
    print(f"\nWrote {out_path}")
    print(json.dumps(plan["stats"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
