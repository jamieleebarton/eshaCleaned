#!/usr/bin/env python3
"""Add an HTC code to every row in our priced_products_tagged.db.

Runs the same encoder over each product's `name` field. Result: every priced
product carries an HTC code (group/family/form/processing/ptype). Cost matching
can then enforce HTC compatibility between recipe ingredient and package.

Adds columns to priced_products_tagged:
  htc_code       — 8-char positional code from name
  htc_group      — single char (D/P/S/B/K/F/M/L/R/W/Y/E/N/0)
  htc_confidence — float 0.2-0.9
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from htc.encoder import encode  # noqa: E402

DB = "/Users/jamiebarton/Desktop/esha_audit_bundle/recipe_pricing/data/priced_products_tagged.db"


def main() -> int:
    con = sqlite3.connect(DB)
    cur = con.cursor()

    # Add columns if missing
    cols = {r[1] for r in cur.execute("PRAGMA table_info(priced_products_tagged)")}
    for col, ddl in [
        ("htc_code", "ALTER TABLE priced_products_tagged ADD COLUMN htc_code TEXT"),
        ("htc_group", "ALTER TABLE priced_products_tagged ADD COLUMN htc_group TEXT"),
        ("htc_confidence", "ALTER TABLE priced_products_tagged ADD COLUMN htc_confidence REAL"),
    ]:
        if col not in cols:
            cur.execute(ddl)
            print(f"  added column: {col}")
    con.commit()

    # Tag every row
    rows = cur.execute("SELECT rowid, name FROM priced_products_tagged").fetchall()
    print(f"  tagging {len(rows):,} priced products...")

    updates = []
    for rowid, name in rows:
        h = encode(category="", description=name or "")
        updates.append((h.code, h.group, h.confidence, rowid))

    cur.executemany(
        "UPDATE priced_products_tagged SET htc_code=?, htc_group=?, htc_confidence=? WHERE rowid=?",
        updates,
    )
    con.commit()

    # Build an index on htc_group for filtering
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_htc_group ON priced_products_tagged(htc_group)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_htc_code  ON priced_products_tagged(htc_code)"
    )
    con.commit()

    # Coverage stats
    print()
    print("=== HTC coverage ===")
    for r in cur.execute(
        "SELECT htc_group, COUNT(*) FROM priced_products_tagged GROUP BY htc_group ORDER BY 2 DESC"
    ):
        print(f"  {r[0]}: {r[1]:,}")

    print()
    print("=== sample rows ===")
    for r in cur.execute("""
        SELECT htc_code, htc_group, source, substr(name,1,45), grams, cents, sr28_fdc_id
        FROM priced_products_tagged
        WHERE quality IN (1,2) AND non_food_drop=0
        LIMIT 12
    """):
        print(f"  {r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
