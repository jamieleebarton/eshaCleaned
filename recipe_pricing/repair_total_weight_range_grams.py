#!/usr/bin/env python3
"""Repair total-weight range rows that kept the parser's lower-bound grams.

Example:
  "6 boneless skinless chicken breasts, about 1.5 to 2 pounds total"

The parser captured the quantity as 1.5, but left unit blank and kept
grams_resolved at one-half pound. In these rows grams_blob already contains
the intended total weight. Restore grams_resolved from grams_blob.
"""
from __future__ import annotations

import argparse
import csv
import os
import re
import sys
import tempfile
from pathlib import Path

csv.field_size_limit(2**30)

ROOT = Path(__file__).resolve().parents[1]
RECIPES = ROOT / "recipe_mapper" / "v1" / "output" / "recipes_unified.csv"
LOG = ROOT / "recipe_pricing" / "repair_total_weight_range_grams_log.csv"
SOURCE = "total_weight_range_restored"

TOTAL_WEIGHT_RANGE_RE = re.compile(
    r"\b(?:about|approximately|approx\.?|around)?\s*"
    r"\d+(?:\.\d+)?\s*(?:to|[-–—])\s*\d+(?:\.\d+)?\s*"
    r"(?:lb|lbs|pound|pounds|oz|ounces|kg|kilograms|g|grams)\s+total\b",
    re.I,
)


def as_float(value: str | None) -> float | None:
    try:
        return float(value or "")
    except (TypeError, ValueError):
        return None


def should_repair(row: dict[str, str]) -> bool:
    display = row.get("display") or ""
    if not TOTAL_WEIGHT_RANGE_RE.search(display):
        return False
    blob = as_float(row.get("grams_blob"))
    resolved = as_float(row.get("grams_resolved"))
    if blob is None or resolved is None or blob <= 0 or resolved <= 0:
        return False
    if (row.get("grams_source") or "") not in {"range_lower_bound", "blob"}:
        return False
    return resolved < blob * 0.65 or resolved > blob * 1.65


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    changed = 0
    rows_seen = 0
    samples: list[dict[str, str]] = []

    if args.dry_run:
        with RECIPES.open(encoding="utf-8", errors="replace") as f:
            for row in csv.DictReader(f):
                rows_seen += 1
                if should_repair(row):
                    changed += 1
                    if len(samples) < 25:
                        samples.append({
                            "recipe_id": row.get("recipe_id", ""),
                            "display": row.get("display", ""),
                            "old_g": row.get("grams_resolved", ""),
                            "new_g": row.get("grams_blob", ""),
                        })
        print(f"rows scanned: {rows_seen:,}")
        print(f"would repair total-weight ranges: {changed:,}")
        for sample in samples:
            print(f"  rid={sample['recipe_id']} {sample['old_g']}g -> {sample['new_g']}g  {sample['display'][:90]}")
        return

    out_dir = RECIPES.parent
    tmp_fd, tmp_path = tempfile.mkstemp(prefix=".unified_total_weight_", suffix=".csv", dir=str(out_dir))
    os.close(tmp_fd)
    try:
        with RECIPES.open(encoding="utf-8", errors="replace") as f_in, open(tmp_path, "w", encoding="utf-8", newline="") as f_out:
            reader = csv.DictReader(f_in)
            writer = csv.DictWriter(f_out, fieldnames=reader.fieldnames)
            writer.writeheader()
            for row in reader:
                rows_seen += 1
                if should_repair(row):
                    old_g = row.get("grams_resolved", "")
                    row["grams_resolved"] = f"{float(row['grams_blob']):.2f}"
                    row["grams_source"] = SOURCE
                    changed += 1
                    if len(samples) < 25:
                        samples.append({
                            "recipe_id": row.get("recipe_id", ""),
                            "display": row.get("display", ""),
                            "old_g": old_g,
                            "new_g": row["grams_resolved"],
                        })
                writer.writerow(row)
        os.replace(tmp_path, RECIPES)
    except Exception:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise

    with LOG.open("w", encoding="utf-8", newline="") as f:
        fieldnames = ["recipe_id", "display", "old_g", "new_g"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(samples)

    print(f"rows scanned: {rows_seen:,}")
    print(f"total-weight range repairs: {changed:,}")
    print(f"log: {LOG}")


if __name__ == "__main__":
    main()
