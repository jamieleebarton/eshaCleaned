#!/usr/bin/env python3
"""Repair parser rows where water temperature was captured as quantity.

Examples:
  "1 cup water (70-80°F)" became qty=70 cup.
  "1/3 cup water (70 to 80°F)" became qty=70 cup.

The original grams_blob is correct on these rows, so restore grams_resolved
from grams_blob and reset qty from water density when possible.
"""
from __future__ import annotations

import csv
import os
import re
import sys
import tempfile
from pathlib import Path

csv.field_size_limit(2**30)

ROOT = Path(__file__).resolve().parents[1]
RECIPES = ROOT / "recipe_mapper" / "v1" / "output" / "recipes_unified.csv"
LOG = ROOT / "recipe_pricing" / "repair_temperature_quantity_grams_log.csv"
SOURCE = "temperature_quantity_restored"

TEMP_RANGE_RE = re.compile(
    r"\b(?:70|75|80|85|90|95|100|105|110|115|120)\s*(?:-|to|–|—)\s*"
    r"(?:70|75|80|85|90|95|100|105|110|115|120)\s*°?\s*f\b",
    re.I,
)

WATER_UNIT_GRAMS = {
    "cup": 240.0,
    "cups": 240.0,
    "tbsp": 15.0,
    "tablespoon": 15.0,
    "tablespoons": 15.0,
    "tsp": 5.0,
    "teaspoon": 5.0,
    "teaspoons": 5.0,
}


def as_float(value: str | None) -> float | None:
    try:
        return float(value or "")
    except (TypeError, ValueError):
        return None


def should_repair(row: dict[str, str]) -> bool:
    item = (row.get("ingredient_item") or "").strip().lower()
    display = (row.get("display") or "").strip().lower()
    unit = (row.get("unit") or "").strip().lower()
    qty = as_float(row.get("qty"))
    blob = as_float(row.get("grams_blob"))
    resolved = as_float(row.get("grams_resolved"))
    if item != "water" or unit not in WATER_UNIT_GRAMS:
        return False
    if qty is None or qty < 50 or blob is None or blob <= 0:
        return False
    if not TEMP_RANGE_RE.search(display):
        return False
    return resolved is None or resolved > blob * 3


def main() -> None:
    if not RECIPES.exists():
        print(f"missing {RECIPES}", file=sys.stderr)
        sys.exit(1)

    changed = 0
    rows_seen = 0
    samples: list[dict] = []
    out_dir = RECIPES.parent
    tmp_fd, tmp_path = tempfile.mkstemp(prefix=".unified_temp_repair_", suffix=".csv", dir=str(out_dir))
    os.close(tmp_fd)
    try:
        with RECIPES.open() as f_in, open(tmp_path, "w", newline="") as f_out:
            reader = csv.DictReader(f_in)
            writer = csv.DictWriter(f_out, fieldnames=reader.fieldnames)
            writer.writeheader()
            for row in reader:
                rows_seen += 1
                if should_repair(row):
                    old_qty = row.get("qty", "")
                    old_g = row.get("grams_resolved", "")
                    unit = (row.get("unit") or "").strip().lower()
                    blob = float(row["grams_blob"])
                    row["qty"] = f"{blob / WATER_UNIT_GRAMS[unit]:.6g}"
                    row["grams_resolved"] = f"{blob:.2f}"
                    row["grams_source"] = SOURCE
                    changed += 1
                    if len(samples) < 25:
                        samples.append({
                            "recipe_id": row.get("recipe_id", ""),
                            "display": row.get("display", ""),
                            "old_qty": old_qty,
                            "new_qty": row["qty"],
                            "old_g": old_g,
                            "new_g": row["grams_resolved"],
                        })
                writer.writerow(row)
                if rows_seen % 500_000 == 0:
                    print(f"  {rows_seen:,} rows scanned", file=sys.stderr)
        os.replace(tmp_path, RECIPES)
    except Exception:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise

    with LOG.open("w", newline="") as f:
        if samples:
            writer = csv.DictWriter(f, fieldnames=list(samples[0].keys()))
            writer.writeheader()
            writer.writerows(samples)

    print(f"rows scanned: {rows_seen:,}", file=sys.stderr)
    print(f"temperature quantity repairs: {changed:,}", file=sys.stderr)
    print(f"log: {LOG}", file=sys.stderr)


if __name__ == "__main__":
    main()
