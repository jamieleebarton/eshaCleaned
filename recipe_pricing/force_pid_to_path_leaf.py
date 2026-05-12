#!/usr/bin/env python3
"""Force consensus_pid (and product_identity_fixed in CSVs) to ALWAYS equal
the leaf of canonical_path. Path is the source of truth for identity.

This eliminates the "Salad Dressing" pid at Caesar/Ranch/Italian leaves
problem, the "Salt" pid at Spice Blend path problem, and every other case
where pid and path leaf disagree.

Mutates IN PLACE with backup:
  recipe_pricing/data/priced_products_v2.db                  (consensus_pid)
  recipe_pricing/output/api_cache_taxonomy_v2.csv            (product_identity_fixed)
  recipe_mapper/v1/output/recipe_ingredient_taxonomy_v2.csv  (product_identity_fixed)

Backups:
  *.before_force_pid_to_leaf

Outputs:
  recipe_pricing/force_pid_to_leaf_log.csv  — every change

Run downstream after: rebuild buy_form lookup, re-run coverage.
"""
from __future__ import annotations

import csv
import shutil
import sqlite3
import sys
from pathlib import Path

csv.field_size_limit(sys.maxsize)

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "recipe_pricing" / "data" / "priced_products_v2.db"
API = ROOT / "recipe_pricing" / "output" / "api_cache_taxonomy_v2.csv"
ING = ROOT / "recipe_mapper" / "v1" / "output" / "recipe_ingredient_taxonomy_v2.csv"
LOG = ROOT / "recipe_pricing" / "force_pid_to_leaf_log.csv"


def fix_db() -> int:
    """Update priced_products.consensus_pid where != leaf(consensus_canonical)."""
    backup = DB.with_suffix(".db.before_force_pid_to_leaf")
    if not backup.exists():
        print(f"  backup → {backup}", file=sys.stderr)
        shutil.copy(str(DB), str(backup))
    con = sqlite3.connect(str(DB))
    cur = con.cursor()
    cur.execute("""
        SELECT rowid, consensus_pid, consensus_canonical
        FROM priced_products
        WHERE consensus_canonical IS NOT NULL AND consensus_canonical != ''
    """)
    n_updates = 0
    updates: list[tuple[int, str]] = []
    for rowid, pid, cp in cur.fetchall():
        leaf = cp.split(" > ")[-1]
        if pid != leaf:
            updates.append((rowid, leaf))
            n_updates += 1
    print(f"  priced_products: updating {n_updates:,} rows", file=sys.stderr)
    cur.executemany("UPDATE priced_products SET consensus_pid = ? WHERE rowid = ?",
                    [(leaf, rid) for rid, leaf in updates])
    con.commit()
    return n_updates


def fix_csv(path: Path, pif_field: str = "product_identity_fixed",
            cp_field: str = "canonical_path") -> int:
    if not path.exists():
        print(f"  missing {path}; skipping", file=sys.stderr)
        return 0
    backup = path.with_suffix(path.suffix + ".before_force_pid_to_leaf")
    if not backup.exists():
        print(f"  backup → {backup}", file=sys.stderr)
        shutil.copy(str(path), str(backup))
    tmp = path.with_suffix(".csv.tmp")
    n_updates = 0
    with path.open(newline="") as fin, tmp.open("w", newline="") as fout:
        reader = csv.DictReader(fin)
        writer = csv.DictWriter(fout, fieldnames=reader.fieldnames)
        writer.writeheader()
        for row in reader:
            cp = (row.get(cp_field) or "").strip()
            if not cp:
                writer.writerow(row)
                continue
            leaf = cp.split(" > ")[-1]
            old_pif = (row.get(pif_field) or "").strip()
            if old_pif != leaf:
                row[pif_field] = leaf
                n_updates += 1
            writer.writerow(row)
    shutil.move(str(tmp), str(path))
    print(f"  {path.name}: updated {n_updates:,} rows", file=sys.stderr)
    return n_updates


def main() -> int:
    print("=== priced_products_v2.db ===", file=sys.stderr)
    n_db = fix_db()
    print(f"\n=== api_cache_taxonomy_v2.csv ===", file=sys.stderr)
    n_api = fix_csv(API)
    print(f"\n=== recipe_ingredient_taxonomy_v2.csv ===", file=sys.stderr)
    n_ing = fix_csv(ING)
    print(f"\n=== TOTAL ===", file=sys.stderr)
    print(f"  priced_products db rows updated:  {n_db:,}", file=sys.stderr)
    print(f"  api_cache CSV rows updated:        {n_api:,}", file=sys.stderr)
    print(f"  recipe_ingredient CSV rows updated:{n_ing:,}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
