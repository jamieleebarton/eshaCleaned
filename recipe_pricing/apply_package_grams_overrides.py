#!/usr/bin/env python3
"""Apply reviewed package-gram corrections to priced_products.

These are data repairs for rows whose SKU identity/path is correct but whose
stored package grams are clearly wrong. This pass does not quarantine or
blocklist the SKU.
"""
from __future__ import annotations

import csv
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "recipe_pricing" / "data" / "priced_products_v2.db"
OVERRIDES = ROOT / "recipe_pricing" / "package_grams_overrides.csv"
LOG = ROOT / "recipe_pricing" / "package_grams_overrides_applied.csv"


def main() -> None:
    con = sqlite3.connect(str(DB))
    cur = con.cursor()
    applied: list[dict] = []

    with OVERRIDES.open(newline="") as handle:
        for row in csv.DictReader(handle):
            upc = (row.get("upc") or "").strip()
            name_contains = (row.get("name_contains") or "").strip()
            new_grams = float(row.get("new_grams") or 0)
            reason = (row.get("reason") or "").strip()
            if not upc or not name_contains or new_grams <= 0:
                continue

            matches = cur.execute(
                """SELECT DISTINCT upc, name, grams, cents
                   FROM priced_products
                   WHERE upc = ?
                     AND name LIKE ?""",
                (upc, f"%{name_contains}%"),
            ).fetchall()
            for upc_v, name, old_grams, cents in matches:
                old_grams = float(old_grams or 0)
                cents = int(cents or 0)
                if old_grams <= 0:
                    continue
                if abs(old_grams - new_grams) <= 0.01:
                    continue
                cur.execute(
                    """UPDATE priced_products
                       SET grams = ?,
                           cpg = CAST(cents AS REAL) / ?
                       WHERE upc = ?
                         AND name = ?""",
                    (new_grams, new_grams, upc_v, name),
                )
                applied.append({
                    "upc": upc_v,
                    "name": name,
                    "old_grams": round(old_grams, 3),
                    "new_grams": round(new_grams, 3),
                    "cents": cents,
                    "reason": reason,
                    "rows_updated": cur.rowcount,
                })

    con.commit()
    con.close()

    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("w", newline="") as handle:
        cols = [
            "upc", "name", "old_grams", "new_grams", "cents",
            "reason", "rows_updated",
        ]
        writer = csv.DictWriter(handle, fieldnames=cols)
        writer.writeheader()
        writer.writerows(applied)

    print(f"applied package gram overrides: {len(applied)}")
    print(f"log: {LOG}")


if __name__ == "__main__":
    main()
