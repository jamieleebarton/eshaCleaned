#!/usr/bin/env python3
"""Block random-weight meat SKUs whose grams field stores the per-serving
weight (always 113g = 4 oz) instead of the actual primal weight.

These are unpriceable as-is: a "4-6 lb pork butt" with grams=113 leads the
picker to buy 17 packages × $23.46 = $400. Marking available=0 lets the
sibling-path fallback pick a real SKU instead.

Identifies suspects by:
  - canonical_path LIKE 'Meat & Seafood%'
  - name contains 'random weight' (case-insensitive)
  - grams <= 227 (8 oz — smaller than any reasonable primal)

Backs up to priced_products_v2.before_meat_block.db. Logs each blocked
SKU's identity so we can re-scrape later.
"""
from __future__ import annotations
import shutil, sqlite3, sys, csv
from pathlib import Path

ROOT = Path("/Users/jamiebarton/Desktop/esha_audit_bundle")
DB   = ROOT / "recipe_pricing" / "data" / "priced_products_v2.db"
BAK  = DB.with_name("priced_products_v2.before_meat_block.db")
LOG  = ROOT / "recipe_pricing" / "blocked_random_weight_meat.csv"


def main():
    if not BAK.exists():
        print(f"backing up DB → {BAK.name}", file=sys.stderr)
        shutil.copy(str(DB), str(BAK))

    con = sqlite3.connect(str(DB))
    cur = con.cursor()

    # Find suspects (DISTINCT UPCs)
    cur.execute("""SELECT DISTINCT upc, name, grams, cents, consensus_canonical
        FROM priced_products
        WHERE consensus_canonical LIKE 'Meat & Seafood%'
          AND LOWER(name) LIKE '%random weight%'
          AND grams <= 227 AND available = 1""")
    suspects = cur.fetchall()
    print(f"random-weight suspects to block: {len(suspects)}", file=sys.stderr)

    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["upc","name","grams_stored","cents","canonical_path","reason"])
        for s in suspects:
            w.writerow(list(s) + ["serving-weight-as-grams; needs re-scrape"])
    print(f"  → log: {LOG}", file=sys.stderr)

    # Set available=0 across ALL duplicate rows for these UPCs
    n_total = 0
    for upc, name, grams, cents, cp in suspects:
        cur.execute("UPDATE priced_products SET available=0 WHERE upc = ?", (upc,))
        n_total += cur.rowcount
        print(f"  [{cur.rowcount} rows]  upc={upc}  {name[:60]}", file=sys.stderr)
    con.commit()
    print(f"\nblocked {n_total} rows ({len(suspects)} unique UPCs)", file=sys.stderr)
    print(f"rollback via: cp {BAK} {DB}", file=sys.stderr)


if __name__ == "__main__":
    main()
