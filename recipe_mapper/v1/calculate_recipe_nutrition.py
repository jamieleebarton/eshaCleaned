#!/usr/bin/env python3
"""Calculate nutrition for sample recipes end-to-end via HTC → SR-28.

Pipeline per recipe ingredient line:
  1. line.htc_code  →  list of SR-28 NDB codes (from htc_gram_weights.csv,
                       which already aggregated SR codes per HTC via the
                       consensus retail bridge)
  2. NDB code        →  fdc_id (sr_legacy_food.csv)
  3. fdc_id + nutrient_id  →  amount per 100 g (food_nutrient.csv)
  4. multiply by (line.grams / 100)  → per-line nutrient
  5. sum per recipe

Targets the 8 macros most recipes care about. Picks 5 representative
recipes, prints the full ingredient breakdown + per-recipe totals.
"""
from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path

csv.field_size_limit(sys.maxsize)

ROOT = Path(__file__).resolve().parents[2]
SR28 = ROOT / "data" / "sr28_csv"
HERE = Path(__file__).resolve().parent
LINES = HERE / "output" / "recipes_unified.csv"
ING_SR_MAP = HERE / "output" / "ingredient_to_sr28.csv"

# SR-28 nutrient IDs we care about (per SR_28 nutrient.csv)
NUTRIENTS = {
    "1008": ("Calories",   "kcal"),
    "1003": ("Protein",    "g"),
    "1005": ("Carbs",      "g"),
    "1004": ("Total Fat",  "g"),
    "1258": ("Sat Fat",    "g"),
    "1079": ("Fiber",      "g"),
    "2000": ("Sugar",      "g"),
    "1093": ("Sodium",     "mg"),
}


def load_ndb_to_fdc() -> dict[str, str]:
    out = {}
    with (SR28 / "sr_legacy_food.csv").open() as f:
        for row in csv.DictReader(f):
            out[row["NDB_number"]] = row["fdc_id"]
    return out


def load_food_descriptions() -> dict[str, str]:
    out = {}
    with (SR28 / "food.csv").open() as f:
        for row in csv.DictReader(f):
            if row.get("data_type") == "sr_legacy_food":
                out[row["fdc_id"]] = row.get("description", "")
    return out


def load_ingredient_to_fdc() -> dict[str, tuple[str, str]]:
    """item -> (fdc_id, sr_description) — direct ingredient→SR-28 map."""
    out: dict[str, tuple[str, str]] = {}
    with ING_SR_MAP.open() as f:
        for row in csv.DictReader(f):
            fdc = row.get("fdc_id") or ""
            if fdc:
                out[row["item"]] = (fdc, row.get("sr_description", ""))
    return out


def load_nutrients(target_fdcs: set[str]) -> dict[str, dict[str, float]]:
    """fdc_id -> {nutrient_id: amount per 100g}, filtered to target fdcs only."""
    out: dict[str, dict[str, float]] = defaultdict(dict)
    with (SR28 / "food_nutrient.csv").open() as f:
        for row in csv.DictReader(f):
            fdc = row["fdc_id"]
            nut = row["nutrient_id"]
            if fdc not in target_fdcs or nut not in NUTRIENTS:
                continue
            try:
                amt = float(row["amount"])
                out[fdc][nut] = amt
            except (ValueError, KeyError):
                pass
    return out


def pick_recipe_ids(target_titles: list[str]) -> list[tuple[int, str]]:
    """Pick the first matching recipe_id for each target title."""
    found: list[tuple[int, str]] = []
    seen_titles: set[str] = set()
    with LINES.open() as f:
        r = csv.DictReader(f)
        for row in r:
            t = row["recipe_title"]
            if t in seen_titles:
                continue
            for tt in target_titles:
                if tt.lower() in t.lower():
                    found.append((int(row["recipe_id"]), t))
                    seen_titles.add(t)
                    break
            if len(found) >= len(target_titles):
                break
    return found


def main() -> int:
    print("loading SR-28 lookups...")
    desc = load_food_descriptions()
    item_to_fdc = load_ingredient_to_fdc()
    print(f"  {len(desc):,} sr_legacy descriptions, "
          f"{len(item_to_fdc):,} ingredient→fdc mappings")

    targets = [
        "Best Lemonade",
        "Low-Fat Berry Blue Frozen Dessert",
        "Chicken Biryani with Saffron",
        "Banana Bread",
        "Caesar Salad",
    ]
    print(f"\npicking 5 recipes from titles: {targets}")
    chosen = pick_recipe_ids(targets)
    print(f"  found: {[t for _,t in chosen]}\n")
    if not chosen:
        return 1
    chosen_ids = {rid for rid, _ in chosen}

    print("collecting all SR-28 fdcs we'll need...")
    needed_fdcs: set[str] = {fdc for fdc, _ in item_to_fdc.values() if fdc}
    print(f"  {len(needed_fdcs):,} fdc_ids in scope")

    print("loading nutrient data (filtering to scoped fdcs)...")
    nutrients = load_nutrients(needed_fdcs)
    print(f"  {len(nutrients):,} fdcs have macro nutrient data\n")

    # collect lines for chosen recipes
    print("scanning recipes_unified.csv for chosen recipes...")
    by_recipe: dict[int, list[dict]] = defaultdict(list)
    with LINES.open() as f:
        r = csv.DictReader(f)
        for row in r:
            try:
                rid = int(row["recipe_id"])
            except ValueError:
                continue
            if rid in chosen_ids:
                by_recipe[rid].append(row)

    for rid, title in chosen:
        lines = by_recipe.get(rid, [])
        print(f"\n{'=' * 78}")
        print(f"  RECIPE #{rid}: {title}")
        print(f"  {len(lines)} ingredient lines")
        print(f"{'=' * 78}")
        totals = {nid: 0.0 for nid in NUTRIENTS}
        n_resolved = 0
        for line in lines:
            item = line["ingredient_item"]
            disp = line["display"]
            grams_raw = line.get("grams_resolved") or ""
            try:
                grams = float(grams_raw) if grams_raw else 0.0
            except ValueError:
                grams = 0.0
            code = line["htc_code"]
            # Direct ingredient→SR-28 lookup (much more accurate than HTC→SR aggregation)
            fdc_pair = item_to_fdc.get(item.lower())
            sr_fdc = fdc_pair[0] if fdc_pair else None
            sr_label = fdc_pair[1][:40] if fdc_pair else ""
            line_nutrients = {}
            if sr_fdc and sr_fdc in nutrients and grams > 0:
                scale = grams / 100.0
                for nid in NUTRIENTS:
                    amt = nutrients.get(sr_fdc, {}).get(nid)
                    if amt is not None:
                        v = amt * scale
                        line_nutrients[nid] = v
                        totals[nid] += v
                if line_nutrients:
                    n_resolved += 1
            kcal = line_nutrients.get("1008") or 0.0
            prot = line_nutrients.get("1003") or 0.0
            carb = line_nutrients.get("1005") or 0.0
            fat  = line_nutrients.get("1004") or 0.0
            tag = sr_fdc if sr_fdc else "—"
            line_str = (
                f"  {item[:28]:<28} {grams:>6.1f}g  "
                f"SR={tag:<7}{sr_label:<32} "
                f"kcal={kcal:>6.1f} P={prot:>5.1f} C={carb:>5.1f} F={fat:>5.1f}"
            )
            if not line_nutrients:
                line_str = (f"  {item[:28]:<28} {grams:>6.1f}g  "
                            f"SR={tag:<7}{sr_label:<32}  [no nutrient data]")
            print(line_str)
        print(f"\n  {'─' * 70}")
        print(f"  TOTAL  ({n_resolved}/{len(lines)} lines resolved):")
        for nid, (label, unit) in NUTRIENTS.items():
            print(f"    {label:<12} {totals[nid]:>10.1f} {unit}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
