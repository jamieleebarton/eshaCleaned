#!/usr/bin/env python3
"""F2 — Whipped cream grams override.

Symptom: lines like "1 cup cream, sweetened and whipped" → grams_resolved=240
because the parser falls back to the generic "1 cup liquid" default. Whipped
cream is mostly air; per SR28 1054 ('Cream, whipped, cream topping,
pressurized') it's ~60g/cup.

Fix: for any line where ingredient_item == "whipped cream" AND unit is
cup/tbsp/tsp/fl_oz, scale grams_resolved using whipped-cream densities:
  cup   = 60g
  tbsp  = 3g
  tsp   = 1g
  fl_oz = 7.5g

Idempotent. Atomic file replace.

Usage:
  python3 recipe_pricing/fix_whipped_cream_grams.py [--dry-run]
"""
from __future__ import annotations
import argparse, csv, os, sys, tempfile
from pathlib import Path

csv.field_size_limit(2**30)
ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "recipe_mapper" / "v1" / "output" / "recipes_unified.csv"

# Whipped (aerated) cream densities, per SR28 1054
WHIPPED_GRAMS_PER_UNIT = {
    "cup": 60.0,
    "tbsp": 3.0,
    "tsp": 1.0,
    "fl_oz": 7.5,
}

UNIT_NORMALIZE = {
    "cup": "cup", "cups": "cup", "c": "cup",
    "tablespoon": "tbsp", "tablespoons": "tbsp", "tbsp": "tbsp", "tbs": "tbsp", "T": "tbsp",
    "teaspoon": "tsp", "teaspoons": "tsp", "tsp": "tsp", "t": "tsp",
    "fluid ounce": "fl_oz", "fluid ounces": "fl_oz", "fl oz": "fl_oz", "fl_oz": "fl_oz",
}

INGREDIENT_KEYS = {"whipped cream"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    src = CSV_PATH
    if not src.exists():
        print(f"missing {src}", file=sys.stderr); sys.exit(1)

    rows_seen = 0; fixed = 0
    samples = []

    if args.dry_run:
        with src.open() as f:
            r = csv.DictReader(f)
            for row in r:
                rows_seen += 1
                ing = (row.get("ingredient_item") or "").lower().strip()
                if ing not in INGREDIENT_KEYS: continue
                unit_raw = (row.get("unit") or "").strip().lower()
                unit = UNIT_NORMALIZE.get(unit_raw)
                if not unit or unit not in WHIPPED_GRAMS_PER_UNIT: continue
                try: qty = float(row.get("qty") or 0)
                except: continue
                if qty <= 0: continue
                old = float(row.get("grams_resolved") or 0)
                new = qty * WHIPPED_GRAMS_PER_UNIT[unit]
                if abs(old - new) < 0.5: continue
                fixed += 1
                if len(samples) < 10:
                    samples.append((row["recipe_id"], (row.get("display","") or "")[:60], old, new))
        print(f"\nscanned {rows_seen:,} rows", file=sys.stderr)
        print(f"would fix {fixed:,} rows", file=sys.stderr)
        for s in samples:
            print(f"  rid={s[0]:>6}  '{s[1]}'  {s[2]:.0f}g → {s[3]:.0f}g", file=sys.stderr)
        return

    out_dir = src.parent
    tmp_fd, tmp_path = tempfile.mkstemp(prefix=".unified_patch_", suffix=".csv", dir=str(out_dir))
    os.close(tmp_fd)
    try:
        with src.open() as f_in, open(tmp_path, "w", newline="") as f_out:
            r = csv.DictReader(f_in)
            w = csv.DictWriter(f_out, fieldnames=r.fieldnames)
            w.writeheader()
            for row in r:
                rows_seen += 1
                ing = (row.get("ingredient_item") or "").lower().strip()
                if ing in INGREDIENT_KEYS:
                    unit_raw = (row.get("unit") or "").strip().lower()
                    unit = UNIT_NORMALIZE.get(unit_raw)
                    if unit and unit in WHIPPED_GRAMS_PER_UNIT:
                        try: qty = float(row.get("qty") or 0)
                        except: qty = 0
                        if qty > 0:
                            new = qty * WHIPPED_GRAMS_PER_UNIT[unit]
                            try: old = float(row.get("grams_resolved") or 0)
                            except: old = 0
                            if abs(old - new) >= 0.5:
                                fixed += 1
                                if len(samples) < 10:
                                    samples.append((row["recipe_id"], (row.get("display","") or "")[:60], old, new))
                                row["grams_resolved"] = f"{new:.2f}"
                                row["grams_source"] = "whipped_density_override"
                w.writerow(row)
        os.replace(tmp_path, src)
    except Exception:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise

    print(f"\npatched {fixed:,} rows in {src}", file=sys.stderr)
    for s in samples:
        print(f"  rid={s[0]:>6}  '{s[1]}'  {s[2]:.0f}g → {s[3]:.0f}g", file=sys.stderr)


if __name__ == "__main__":
    main()
