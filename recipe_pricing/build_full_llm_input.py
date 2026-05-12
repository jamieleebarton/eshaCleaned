#!/usr/bin/env python3
"""Build the full 145k input CSV combining:
  - 70,351 unique Walmart/Kroger products (already deduped)
  - 74,624 unique recipe ingredients

into a single CSV in the shape run_full_csv_parallel.py expects.
"""
from __future__ import annotations

import csv
import hashlib
import sys
from pathlib import Path

csv.field_size_limit(sys.maxsize)

ROOT = Path(__file__).resolve().parents[1]
WMT_KR_INPUT = ROOT / "recipe_pricing" / "data" / "walmart_kroger_for_llm.csv"
RECIPE_ITEMS = ROOT / "recipe_mapper" / "v1" / "output" / "recipe_ingredient_items.csv"
OUTPUT = ROOT / "recipe_pricing" / "data" / "full_llm_input.csv"

OUTPUT_FIELDS = [
    "fdc_id", "gtin_upc", "title", "branded_food_category",
    "source", "_corpus",
]


def main() -> int:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    n_wmt = 0
    n_ing = 0
    with OUTPUT.open("w", newline="") as out:
        w = csv.DictWriter(out, fieldnames=OUTPUT_FIELDS)
        w.writeheader()

        with WMT_KR_INPUT.open() as f:
            for row in csv.DictReader(f):
                w.writerow({
                    "fdc_id": row["fdc_id"],
                    "gtin_upc": row.get("gtin_upc", ""),
                    "title": row["title"],
                    "branded_food_category": row.get("branded_food_category", ""),
                    "source": row.get("source", ""),
                    "_corpus": "walmart_kroger",
                })
                n_wmt += 1

        with RECIPE_ITEMS.open() as f:
            for row in csv.DictReader(f):
                item = (row.get("item") or "").strip()
                if not item:
                    continue
                fid = f"RI-{hashlib.md5(item.encode()).hexdigest()[:10]}"
                w.writerow({
                    "fdc_id": fid,
                    "gtin_upc": "",
                    "title": item,
                    "branded_food_category": "",
                    "source": "recipe",
                    "_corpus": "recipe_ingredient",
                })
                n_ing += 1

    total = n_wmt + n_ing
    print(f"wrote {total:,} rows -> {OUTPUT}")
    print(f"  walmart/kroger:    {n_wmt:,}")
    print(f"  recipe ingredients: {n_ing:,}")
    print(f"  size: {OUTPUT.stat().st_size / 1024 / 1024:.1f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
