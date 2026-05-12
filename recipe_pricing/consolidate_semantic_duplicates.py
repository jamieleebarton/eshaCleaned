#!/usr/bin/env python3
"""Apply pid consolidations from pid_semantic_duplicate_groups.csv.

For each (canonical_pid, variant_pid) pair:
  - In priced_products_v2.db: update all products with consensus_pid=variant
    to consensus_pid=canonical AND consensus_canonical=canonical_path_of_canonical
  - Same for api_cache_taxonomy_v2.csv (product_identity_fixed, canonical_path)
  - Same for recipe_ingredient_taxonomy_v2.csv

Also propagate canonical_path changes to recipe_ingredient_htc_tagged.csv
(the recipe-side equivalent).

This is the structural one-identity-one-path fix.

Backups: *.before_semantic_consolidation
"""
from __future__ import annotations

import csv
import shutil
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

csv.field_size_limit(sys.maxsize)

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "recipe_pricing" / "data" / "priced_products_v2.db"
API = ROOT / "recipe_pricing" / "output" / "api_cache_taxonomy_v2.csv"
ING = ROOT / "recipe_mapper" / "v1" / "output" / "recipe_ingredient_taxonomy_v2.csv"
DUP_FILE = ROOT / "recipe_pricing" / "pid_semantic_duplicate_groups.csv"


def main() -> int:
    if not DUP_FILE.exists():
        raise SystemExit(f"missing {DUP_FILE} — run find_semantic_duplicate_pids.py first")

    # 1. Load duplicate pairs
    print("loading duplicate groups...", file=sys.stderr)
    pairs: list[dict] = []
    with DUP_FILE.open() as f:
        for row in csv.DictReader(f):
            pairs.append(row)
    print(f"  {len(pairs):,} (canonical, variant) pairs", file=sys.stderr)

    # 2. For each pair, look up the canonical_pid's dominant canonical_path
    #    in priced_products
    con = sqlite3.connect(str(DB))
    cur = con.cursor()
    pid_to_canonical_path: dict[str, str] = {}
    for p in pairs:
        canonical_pid = p["canonical_pid"]
        if canonical_pid in pid_to_canonical_path:
            continue
        cur.execute("""
            SELECT consensus_canonical, COUNT(*) FROM priced_products
            WHERE consensus_pid = ? AND available = 1 AND grams > 0 AND cents > 0
              AND consensus_canonical NOT LIKE 'Non-Food%'
            GROUP BY consensus_canonical ORDER BY 2 DESC LIMIT 1
        """, (canonical_pid,))
        row = cur.fetchone()
        if row:
            pid_to_canonical_path[canonical_pid] = row[0]

    # Build the variant_pid → (canonical_pid, canonical_path) remap
    remap: dict[str, tuple[str, str]] = {}
    for p in pairs:
        cp = pid_to_canonical_path.get(p["canonical_pid"])
        if cp:
            remap[p["variant_pid"]] = (p["canonical_pid"], cp)
    print(f"  built remap for {len(remap):,} variant pids", file=sys.stderr)

    # 3. Apply to priced_products_v2.db
    backup = DB.with_suffix(".db.before_semantic_consolidation")
    if not backup.exists():
        print(f"\n  backup → {backup}", file=sys.stderr)
        shutil.copy(str(DB), str(backup))
    n_db = 0
    for variant, (canonical, cp) in remap.items():
        cur.execute("""
            UPDATE priced_products
            SET consensus_pid = ?, consensus_canonical = ?
            WHERE consensus_pid = ?
        """, (canonical, cp, variant))
        n_db += cur.rowcount
    con.commit()
    print(f"  priced_products: updated {n_db:,} rows", file=sys.stderr)

    # 4. Apply to CSV files
    def update_csv(path: Path, pif_field: str = "product_identity_fixed",
                   cp_field: str = "canonical_path") -> int:
        if not path.exists():
            print(f"  missing {path}; skipping", file=sys.stderr)
            return 0
        backup = path.with_suffix(path.suffix + ".before_semantic_consolidation")
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
                pif = (row.get(pif_field) or "").strip()
                if pif in remap:
                    canonical, cp = remap[pif]
                    row[pif_field] = canonical
                    row[cp_field] = cp
                    n_updates += 1
                writer.writerow(row)
        shutil.move(str(tmp), str(path))
        print(f"  {path.name}: updated {n_updates:,} rows", file=sys.stderr)
        return n_updates

    print(f"\n=== api_cache_taxonomy_v2.csv ===", file=sys.stderr)
    n_api = update_csv(API)
    print(f"\n=== recipe_ingredient_taxonomy_v2.csv ===", file=sys.stderr)
    n_ing = update_csv(ING)

    print(f"\n=== TOTAL ===", file=sys.stderr)
    print(f"  priced_products db:    {n_db:,}", file=sys.stderr)
    print(f"  api_cache CSV:         {n_api:,}", file=sys.stderr)
    print(f"  recipe_ingredient CSV: {n_ing:,}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
