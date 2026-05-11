#!/usr/bin/env python3
"""Repair random-weight meat/seafood size displays from declared lb ranges.

These rows already carry the food identity in the name and HTC/path. The bug is
package metadata: scraped ``size_display`` values such as ``14.28 lbs`` on a
``1.01 - 1.37 lb Tray`` make downstream audits think the package grams are
wrong even after grams are repaired. This pass keeps the SKU buyable and fixes
the package metadata in place.
"""
from __future__ import annotations

import argparse
import csv
import re
import sqlite3
from pathlib import Path

from fix_size_display_grams import parse_largest_size


ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "recipe_pricing" / "data" / "priced_products_v2.db"
LOG = ROOT / "recipe_pricing" / "random_weight_size_display_fixes.csv"

LB_TO_G = 453.59237
RANGE_RE = re.compile(
    r"(?<![\d./])(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)\s*lb\b",
    re.I,
)
MEAT_RANDOM_WEIGHT_PATH_RE = re.compile(r"^(?:Meat & Seafood|Seafood)\b", re.I)
RANDOM_WEIGHT_NAME_RE = re.compile(r"\b(?:family\s+pack|tray|steaks?|chops?|roast|ribs?)\b", re.I)


def declared_range_grams(name: str) -> tuple[float, float] | None:
    match = RANGE_RE.search(name or "")
    if not match:
        return None
    low_lb = float(match.group(1))
    high_lb = float(match.group(2))
    if low_lb <= 0 or high_lb <= 0 or low_lb > high_lb or high_lb > 20:
        return None
    return low_lb * LB_TO_G, high_lb * LB_TO_G


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    con = sqlite3.connect(str(DB))
    rows = con.execute(
        """SELECT DISTINCT upc, name, grams, cents, size_display, consensus_canonical
           FROM priced_products
           WHERE available = 1
             AND (lower(name) LIKE '% lb%' OR lower(size_display) LIKE '% lb%')"""
    ).fetchall()

    fixes: list[dict[str, object]] = []
    for upc, name, grams, cents, size_display, canonical_path in rows:
        declared = declared_range_grams(name or "")
        old_grams = float(grams or 0)
        old_display = size_display or ""
        new_grams = old_grams
        new_display = old_display
        reasons: list[str] = []

        display_g = parse_largest_size(old_display)
        low_g = high_g = 0.0
        if declared is not None:
            low_g, high_g = declared
            if old_grams <= 0 or old_grams > high_g * 1.05 or old_grams < low_g * 0.95:
                new_grams = (low_g + high_g) / 2.0
                reasons.append("grams_outside_declared_lb_range")

            if display_g is not None and (display_g > high_g * 1.05 or display_g < low_g * 0.95):
                new_display = "Random Weight"
                reasons.append("size_display_outside_declared_lb_range")
        elif (
            display_g is not None
            and old_grams > display_g * 1.5
            and MEAT_RANDOM_WEIGHT_PATH_RE.search(canonical_path or "")
            and RANDOM_WEIGHT_NAME_RE.search(name or "")
        ):
            new_display = "Random Weight"
            reasons.append("meat_random_weight_size_display_understates_package")

        if not reasons:
            continue

        fixes.append({
            "upc": upc,
            "name": name,
            "old_grams": round(old_grams, 3),
            "new_grams": round(new_grams, 3),
            "old_size_display": old_display,
            "new_size_display": new_display,
            "declared_low_g": round(low_g, 3) if low_g else "",
            "declared_high_g": round(high_g, 3) if high_g else "",
            "cents": int(cents or 0),
            "reason": ";".join(reasons),
        })

        if not args.dry_run:
            con.execute(
                """UPDATE priced_products
                   SET grams = ?,
                       cpg = CASE WHEN ? > 0 THEN CAST(cents AS REAL) / ? ELSE cpg END,
                       size_display = ?
                   WHERE upc = ?
                     AND name = ?""",
                (new_grams, new_grams, new_grams, new_display, upc, name),
            )

    if not args.dry_run:
        con.commit()
    con.close()

    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("w", newline="") as handle:
        cols = [
            "upc", "name", "old_grams", "new_grams",
            "old_size_display", "new_size_display",
            "declared_low_g", "declared_high_g", "cents", "reason",
        ]
        writer = csv.DictWriter(handle, fieldnames=cols)
        writer.writeheader()
        writer.writerows(fixes)

    mode = "would fix" if args.dry_run else "fixed"
    print(f"{mode} random-weight rows: {len(fixes)}")
    print(f"log: {LOG}")


if __name__ == "__main__":
    main()
