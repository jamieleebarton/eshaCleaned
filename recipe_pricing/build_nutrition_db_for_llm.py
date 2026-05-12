#!/usr/bin/env python3
"""Adapt SR28 and FNDDS food descriptions into the run_full_csv_parallel.py
input shape so they go through the same prompt/encoder pipeline as the
145k Walmart/Kroger + recipe ingredient batch.

Output: recipe_pricing/data/nutrition_db_for_llm.csv

Each row carries fdc_id (synthetic prefix to disambiguate), title, and
branded_food_category (using each source's existing category column as a
proxy). compact_source_row() will forward only the populated fields.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

csv.field_size_limit(sys.maxsize)

ROOT = Path(__file__).resolve().parents[1]
SR28 = ROOT / "data" / "sr28_csv" / "food.csv"
FNDDS = ROOT / "data" / "fndds" / "MainFoodDesc16.csv"
OUTPUT = ROOT / "recipe_pricing" / "data" / "nutrition_db_for_llm.csv"

OUT_FIELDS = [
    "fdc_id", "gtin_upc", "title", "branded_food_category", "source", "_corpus",
]


def main() -> int:
    n_sr28 = 0
    n_fndds = 0
    rows_out = []

    # SR28 — sr_legacy_food rows from food.csv (data_type == sr_legacy_food).
    if SR28.exists():
        with SR28.open() as f:
            for row in csv.DictReader(f):
                if (row.get("data_type") or "").strip() != "sr_legacy_food":
                    continue
                fid = (row.get("fdc_id") or "").strip()
                desc = (row.get("description") or "").strip()
                cat_id = (row.get("food_category_id") or "").strip()
                if not fid or not desc:
                    continue
                rows_out.append({
                    "fdc_id": f"SR28-{fid}",
                    "gtin_upc": "",
                    "title": desc,
                    "branded_food_category": cat_id,  # numeric food category id
                    "source": "sr28",
                    "_corpus": "nutrition_db",
                })
                n_sr28 += 1

    # FNDDS — MainFoodDesc16
    if FNDDS.exists():
        with FNDDS.open() as f:
            for row in csv.DictReader(f):
                code = (row.get("Food code") or "").strip()
                desc = (row.get("Main food description") or "").strip()
                wweia = (row.get("WWEIA Category description") or "").strip()
                if not code or not desc:
                    continue
                rows_out.append({
                    "fdc_id": f"FNDDS-{code}",
                    "gtin_upc": "",
                    "title": desc,
                    "branded_food_category": wweia,
                    "source": "fndds",
                    "_corpus": "nutrition_db",
                })
                n_fndds += 1

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=OUT_FIELDS)
        w.writeheader()
        w.writerows(rows_out)

    print(f"wrote {len(rows_out):,} rows -> {OUTPUT}")
    print(f"  SR28:  {n_sr28:,}")
    print(f"  FNDDS: {n_fndds:,}")
    print(f"  size:  {OUTPUT.stat().st_size / 1024:.1f} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
