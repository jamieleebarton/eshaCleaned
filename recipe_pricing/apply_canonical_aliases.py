#!/usr/bin/env python3
"""Apply canonical_path aliases to priced_products_v2.db.

Reads recipe_pricing/canonical_path_aliases.csv (curated). For each row,
updates priced_products WHERE consensus_canonical = old_path SET
consensus_canonical = new_path. Preserves backups.
"""
from __future__ import annotations
import csv, shutil, sqlite3, sys
from pathlib import Path

ROOT = Path("/Users/jamiebarton/Desktop/esha_audit_bundle")
DB = ROOT / "recipe_pricing" / "data" / "priced_products_v2.db"
BAK = DB.with_name("priced_products_v2.before_aliases.db")
ALIAS = ROOT / "recipe_pricing" / "canonical_path_aliases.csv"


def main():
    if not BAK.exists():
        print(f"backing up DB → {BAK.name}", file=sys.stderr)
        shutil.copy(str(DB), str(BAK))
    aliases = list(csv.DictReader(ALIAS.open()))
    print(f"loaded {len(aliases)} aliases", file=sys.stderr)

    con = sqlite3.connect(str(DB))
    cur = con.cursor()
    n_total = 0
    for a in aliases:
        old = a["old_path"]
        new = a["new_path"]
        if not old or not new or old == new: continue
        cur.execute("UPDATE priced_products SET consensus_canonical = ? "
                    "WHERE consensus_canonical = ?", (new, old))
        if cur.rowcount > 0:
            n_total += cur.rowcount
            print(f"  {cur.rowcount:>4} rows: {old} → {new}", file=sys.stderr)
    con.commit()
    print(f"\ntotal rows updated: {n_total}", file=sys.stderr)


if __name__ == "__main__":
    main()
