#!/usr/bin/env python3
"""A1 — Unit-conversion audit.

For each (qty, unit, ingredient_item) tuple in recipes_unified.csv, compare
our parser's grams_resolved against Hestia's per-ingredient portion table
(ingredient_lookup.json:portions_fndds — keyed by ingredient name).

A "real bug" is a (ingredient, unit) pair where ratio (ours/hestia) is
> 1.25 or < 0.80 with > 50 affected lines. Idempotent. Read-only.

Outputs:
  recipe_pricing/audit_unit_conversions.csv — top divergences
"""
from __future__ import annotations
import csv, json, sys
from collections import defaultdict
from pathlib import Path

csv.field_size_limit(2**30)
ROOT = Path(__file__).resolve().parents[1]
RECIPES = ROOT / "recipe_mapper" / "v1" / "output" / "recipes_unified.csv"
ILU = Path("/Users/jamiebarton/Desktop/Hestia/api/data/ingredient_lookup.json")
OUT = ROOT / "recipe_pricing" / "audit_unit_conversions.csv"

# Units we test (Hestia's portions_fndds keys + common variants we map onto them)
UNIT_NORMALIZE = {
    "cup": "cup", "cups": "cup", "c": "cup",
    "tablespoon": "tbsp", "tablespoons": "tbsp", "tbsp": "tbsp", "tbs": "tbsp", "T": "tbsp",
    "teaspoon": "tsp", "teaspoons": "tsp", "tsp": "tsp", "t": "tsp",
    "fluid ounce": "fl_oz", "fluid ounces": "fl_oz", "fl oz": "fl_oz", "fl_oz": "fl_oz",
}


def main():
    print("loading ingredient_lookup…", file=sys.stderr)
    ilu = json.loads(ILU.read_text())
    print(f"  {len(ilu):,} ingredients", file=sys.stderr)

    # ingredient_item.lower() → portions_fndds dict
    ing_portions: dict[str, dict] = {}
    for k, v in ilu.items():
        p = v.get("portions_fndds") or {}
        if p:
            ing_portions[k.lower().strip()] = p

    # Aggregate per (ingredient, unit): count + sum of ratios
    agg: dict[tuple[str, str], dict] = defaultdict(
        lambda: {"n": 0, "sum_our_g": 0.0, "sum_hes_g": 0.0,
                  "sum_qty": 0.0, "samples": []})

    rows_seen = 0; rows_matched = 0
    with RECIPES.open() as f:
        r = csv.DictReader(f)
        for row in r:
            rows_seen += 1
            if rows_seen % 500_000 == 0:
                print(f"  {rows_seen:,} lines processed", file=sys.stderr)
            unit_raw = (row.get("unit") or "").strip().lower()
            unit = UNIT_NORMALIZE.get(unit_raw)
            if not unit: continue
            try: qty = float(row.get("qty") or 0)
            except: continue
            if qty <= 0: continue
            try: our_g = float(row.get("grams_resolved") or 0)
            except: continue
            if our_g <= 0: continue
            ing = (row.get("ingredient_item") or "").lower().strip()
            if not ing: continue
            portions = ing_portions.get(ing)
            if not portions or unit not in portions: continue
            hes_per_unit = float(portions[unit])
            hes_g = qty * hes_per_unit
            if hes_g <= 0: continue
            rows_matched += 1
            key = (ing, unit)
            d = agg[key]
            d["n"] += 1
            d["sum_our_g"] += our_g
            d["sum_hes_g"] += hes_g
            d["sum_qty"] += qty
            if len(d["samples"]) < 3:
                d["samples"].append(f"{row.get('recipe_id','?')}: '{(row.get('display','') or '')[:50]}' our={our_g:.1f}g vs hes={hes_g:.1f}g")

    print(f"\nrows seen: {rows_seen:,}", file=sys.stderr)
    print(f"matched (have portion + grams + ingredient): {rows_matched:,}", file=sys.stderr)

    # Output: rows where (avg_our / avg_hes) is off-target with significant n
    out_rows = []
    for (ing, unit), d in agg.items():
        if d["n"] < 20: continue   # not enough signal
        avg_our = d["sum_our_g"] / d["n"]
        avg_hes = d["sum_hes_g"] / d["n"]
        if avg_hes <= 0: continue
        ratio = avg_our / avg_hes
        gram_delta_kg = (d["sum_our_g"] - d["sum_hes_g"]) / 1000.0
        if 0.80 <= ratio <= 1.25 and abs(gram_delta_kg) < 50:
            continue   # within tolerance
        out_rows.append({
            "ingredient": ing, "unit": unit,
            "n_lines": d["n"], "avg_qty": round(d["sum_qty"]/d["n"], 2),
            "avg_our_g": round(avg_our, 1),
            "avg_hes_g": round(avg_hes, 1),
            "ratio": round(ratio, 2),
            "gram_delta_kg": round(gram_delta_kg, 2),
            "sample": d["samples"][0] if d["samples"] else "",
        })

    out_rows.sort(key=lambda r: -abs(r["gram_delta_kg"]))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    if out_rows:
        with OUT.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(out_rows[0].keys()))
            w.writeheader()
            for r in out_rows[:100]: w.writerow(r)

    print(f"\n→ {OUT}  ({len(out_rows[:100])} divergences with n≥20 outside ±20% tolerance)", file=sys.stderr)


if __name__ == "__main__":
    main()
