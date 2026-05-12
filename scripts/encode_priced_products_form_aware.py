#!/usr/bin/env python3
"""Re-encode every SKU in priced_products_v2.db with identity_mode=False.

Writes the result into a new column `htc_form_code` so the recipe pipeline can
match form-aware HTCs against form-aware SKUs (whole vs sliced ham, whole vs
skim milk, ground vs whole cinnamon, etc.).

This is additive — keeps existing htc_code/htc_full_code unchanged.
"""
from __future__ import annotations
import sqlite3, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from recipe_mapper.v1.htc.encoder import encode

DB = ROOT / "recipe_pricing" / "data" / "priced_products_v2.db"


def main():
    con = sqlite3.connect(str(DB))
    cur = con.cursor()

    # Add column if missing
    cols = {r[1] for r in cur.execute("PRAGMA table_info(priced_products)").fetchall()}
    if "htc_form_code" not in cols:
        print("adding htc_form_code column…", file=sys.stderr)
        cur.execute("ALTER TABLE priced_products ADD COLUMN htc_form_code TEXT")
        con.commit()

    cur.execute("""
        SELECT rowid, name, consensus_canonical, consensus_pid, category_path
        FROM priced_products
    """)
    rows = cur.fetchall()
    print(f"encoding {len(rows):,} SKUs…", file=sys.stderr)

    updates = []
    t0 = time.time()
    for i, (rowid, name, cp, pid, cat) in enumerate(rows, 1):
        try:
            h = encode(
                cat or "",
                description=name or "",
                food_name=pid or "",
                canonical_path=cp or "",
                identity_mode=False,
            )
            updates.append((h.code, rowid))
        except Exception:
            updates.append(("", rowid))
        if i % 25000 == 0:
            elapsed = time.time() - t0
            rate = i / elapsed
            print(f"  {i:>7,}/{len(rows):,}  ({rate:.0f}/s, ~{(len(rows)-i)/rate:.0f}s left)",
                  file=sys.stderr)

    print("writing back…", file=sys.stderr)
    cur.executemany("UPDATE priced_products SET htc_form_code = ? WHERE rowid = ?", updates)
    con.commit()

    cur.execute("CREATE INDEX IF NOT EXISTS idx_priced_form ON priced_products(htc_form_code)")
    con.commit()

    cur.execute("""
        SELECT COUNT(DISTINCT htc_form_code) FROM priced_products
        WHERE htc_form_code != '' AND grams>0 AND cents>0 AND available=1
    """)
    n = cur.fetchone()[0]
    print(f"\nDONE. {n:,} distinct htc_form_codes (avail+priced+grams)", file=sys.stderr)


if __name__ == "__main__":
    main()
