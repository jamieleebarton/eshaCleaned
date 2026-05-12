#!/usr/bin/env python3
"""Build sr28_nutrient_lookup.csv keyed by NDB_number with macros per 100g.

Joins:
  sr_legacy_food.csv  (fdc_id ↔ NDB_number)
  food_nutrient.csv   (fdc_id, nutrient_id → amount)
  nutrient.csv        (nutrient_id → name)

Output: data/sr28/sr28_nutrient_lookup.csv
columns: ndb, energy_kcal, protein_g, fat_g, carbs_g, fiber_g, sugar_g, sodium_mg
"""
from __future__ import annotations
import csv, sys
from pathlib import Path
csv.field_size_limit(2**30)

ROOT = Path(__file__).resolve().parents[1]
SR_DIR = ROOT / "data" / "sr28_csv"
OUT_DIR = ROOT / "data" / "sr28"
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT = OUT_DIR / "sr28_nutrient_lookup.csv"

# Nutrient IDs (USDA SR/FoodData Central standard)
NUTRIENT_IDS = {
    "energy_kcal": {"1008"},   # Energy (kcal)
    "protein_g":   {"1003"},
    "fat_g":       {"1004"},
    "carbs_g":     {"1005"},
    "fiber_g":     {"1079"},
    "sugar_g":     {"2000", "1063"},
    "sodium_mg":   {"1093"},
}


def main():
    print("loading sr_legacy_food → ndb↔fdc bridge…", file=sys.stderr)
    fdc_to_ndb: dict[str, str] = {}
    with (SR_DIR / "sr_legacy_food.csv").open() as f:
        for row in csv.DictReader(f):
            fdc = row["fdc_id"]; ndb = row["NDB_number"]
            if fdc and ndb: fdc_to_ndb[fdc] = ndb
    print(f"  {len(fdc_to_ndb):,} fdc → ndb", file=sys.stderr)

    print("scanning food_nutrient.csv (this is large)…", file=sys.stderr)
    # ndb → {field → amount}
    out: dict[str, dict] = {}
    target_nuts = {nid for ids in NUTRIENT_IDS.values() for nid in ids}
    with (SR_DIR / "food_nutrient.csv").open() as f:
        rd = csv.DictReader(f)
        for row in rd:
            nid = row["nutrient_id"]
            if nid not in target_nuts: continue
            fdc = row["fdc_id"]
            ndb = fdc_to_ndb.get(fdc)
            if not ndb: continue
            try: amt = float(row["amount"] or 0)
            except: continue
            d = out.setdefault(ndb, {})
            for field, ids in NUTRIENT_IDS.items():
                if nid in ids:
                    # Take max if multiple sources (sugar has 2000 + 1063)
                    if d.get(field, 0.0) < amt:
                        d[field] = amt
                    break

    print(f"  {len(out):,} ndb codes with at least one macro", file=sys.stderr)

    cols = ["ndb","energy_kcal","protein_g","fat_g","carbs_g","fiber_g","sugar_g","sodium_mg"]
    with OUT.open("w", newline="") as f:
        w = csv.writer(f); w.writerow(cols)
        for ndb, d in out.items():
            w.writerow([ndb] + [round(d.get(c, 0.0), 3) for c in cols[1:]])
    print(f"\n→ {OUT}  ({OUT.stat().st_size/1024:.0f} KB)", file=sys.stderr)


if __name__ == "__main__":
    main()
