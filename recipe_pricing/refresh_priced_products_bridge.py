#!/usr/bin/env python3
"""Refresh priced_products_v2.db with current htc codes and add the missing
columns the strict-then-relaxed pricing matcher needs.

The bridge was built from an earlier encoder run; many rows have stale
htc_code / consensus_canonical values. This script joins each priced product
to its current row in api_cache_taxonomy_v2.csv (by UPC, extracted from
the v2's fdc_id which is `KR-<upc>` or `WM-<upc>`) and refreshes:

  - htc_code, htc_full_code, retail_leaf_path
  - consensus_canonical, consensus_pid, consensus_modifier
  - canonical_label

Adds columns if they don't exist.
Idempotent — running twice produces the same result.
"""
from __future__ import annotations

import csv
import sqlite3
import sys
from pathlib import Path

csv.field_size_limit(sys.maxsize)

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "recipe_pricing" / "data" / "priced_products_v2.db"
V2 = ROOT / "recipe_pricing" / "output" / "api_cache_taxonomy_v2.csv"


def main() -> int:
    if not DB.exists():
        print(f"missing {DB}", file=sys.stderr)
        return 2
    if not V2.exists():
        print(f"missing {V2}", file=sys.stderr)
        return 2

    # 1. Load v2 taxonomy keyed by UPC (extracted from fdc_id)
    v2_by_upc: dict[str, dict] = {}
    with V2.open() as f:
        for row in csv.DictReader(f):
            fid = (row.get("fdc_id") or "").strip()
            if "-" in fid:
                upc = fid.split("-", 1)[1]
            else:
                upc = fid
            if upc:
                v2_by_upc[upc] = row
    print(f"v2 taxonomy by UPC: {len(v2_by_upc):,}", file=sys.stderr)

    con = sqlite3.connect(str(DB))
    cur = con.cursor()

    # 2. Add missing columns
    cur.execute("PRAGMA table_info(priced_products)")
    existing_cols = {r[1] for r in cur.fetchall()}
    for col, sqltype in [
        ("htc_full_code", "TEXT"),
        ("retail_leaf_path", "TEXT"),
        ("canonical_label", "TEXT"),
    ]:
        if col not in existing_cols:
            cur.execute(f"ALTER TABLE priced_products ADD COLUMN {col} {sqltype}")
            print(f"  added column: {col}", file=sys.stderr)
    con.commit()

    # 3. Update each row from v2
    cur.execute("SELECT rowid, upc FROM priced_products")
    rows = cur.fetchall()
    print(f"priced_products rows: {len(rows):,}", file=sys.stderr)

    updates: list[tuple] = []
    matched = 0
    for rowid, upc in rows:
        if not upc:
            continue
        # try exact, then with leading-zero variants common in UPCs
        v2 = v2_by_upc.get(upc) or v2_by_upc.get(upc.lstrip("0")) or v2_by_upc.get("0" + upc)
        if not v2:
            continue
        matched += 1
        updates.append((
            v2.get("htc_code", ""),
            v2.get("htc_full_code", ""),
            v2.get("retail_leaf_path", ""),
            v2.get("canonical_path", ""),
            v2.get("canonical_label", ""),
            v2.get("product_identity_fixed", ""),
            v2.get("modifier", ""),
            rowid,
        ))

    cur.executemany("""
        UPDATE priced_products
        SET htc_code = ?, htc_full_code = ?, retail_leaf_path = ?,
            consensus_canonical = ?, canonical_label = ?,
            consensus_pid = ?, consensus_modifier = ?
        WHERE rowid = ?
    """, updates)
    con.commit()
    con.close()

    print(f"  refreshed: {matched:,} rows ({matched/max(len(rows),1):.1%})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
