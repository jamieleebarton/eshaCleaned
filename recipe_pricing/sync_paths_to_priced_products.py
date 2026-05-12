#!/usr/bin/env python3
"""STRUCTURAL FIX: sync canonical_path in api_cache_taxonomy_v2.csv and
recipe_ingredient_taxonomy_v2.csv to match priced_products_v2.db.

For each row, look up its product_identity_fixed in priced_products and
use the DOMINANT canonical_path for that pid. This eliminates stale paths
across files — they now all agree.

After this, build_buy_form_lookup picks paths that priced_products
actually has products at.

priced_products is the AUTHORITY because:
  - It has the most consolidated paths after today's structural fixes
  - The calculator queries priced_products at runtime
  - Path mismatches between sources cause lookup failures

Backups:
  *.before_path_sync

Outputs:
  recipe_pricing/path_sync_log.csv  (every change)
"""
from __future__ import annotations

import csv
import shutil
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

csv.field_size_limit(sys.maxsize)

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "recipe_pricing" / "data" / "priced_products_v2.db"
API = ROOT / "recipe_pricing" / "output" / "api_cache_taxonomy_v2.csv"
ING = ROOT / "recipe_mapper" / "v1" / "output" / "recipe_ingredient_taxonomy_v2.csv"
LOG = ROOT / "recipe_pricing" / "path_sync_log.csv"


def build_pid_to_path_authority() -> dict[str, str]:
    """For each consensus_pid in priced_products, return the DOMINANT
    canonical_path (the one with the most products).

    Special handling: when a pid has products at multiple paths, prefer the
    one with most products. This is the canonical authority — every other
    file should align here.
    """
    print("building pid → dominant_path authority from priced_products...", file=sys.stderr)
    con = sqlite3.connect(str(DB))
    cur = con.cursor()
    cur.execute("""
        SELECT consensus_pid, consensus_canonical, COUNT(*)
        FROM priced_products
        WHERE consensus_pid IS NOT NULL AND consensus_pid != ''
          AND consensus_canonical IS NOT NULL AND consensus_canonical != ''
          AND available = 1 AND grams > 0 AND cents > 0
          AND consensus_canonical NOT LIKE 'Non-Food%'
        GROUP BY consensus_pid, consensus_canonical
    """)
    pid_paths: defaultdict[str, Counter] = defaultdict(Counter)
    for pid, cp, n in cur.fetchall():
        pid_paths[pid.lower().strip()][cp] += n
    authority: dict[str, str] = {}
    for pid, cp_counts in pid_paths.items():
        authority[pid] = cp_counts.most_common(1)[0][0]
    print(f"  {len(authority):,} pid → path mappings (authority)", file=sys.stderr)
    return authority


def sync_csv(path: Path, authority: dict[str, str], log_writer) -> int:
    """For each row, if its pid maps to a different canonical_path in
    priced_products' authority, update."""
    if not path.exists():
        print(f"  missing {path}", file=sys.stderr)
        return 0
    backup = path.with_suffix(path.suffix + ".before_path_sync")
    if not backup.exists():
        print(f"  backup → {backup}", file=sys.stderr)
        shutil.copy(str(path), str(backup))
    tmp = path.with_suffix(".csv.tmp")
    n_updated = 0
    with path.open(newline="") as fin, tmp.open("w", newline="") as fout:
        reader = csv.DictReader(fin)
        writer = csv.DictWriter(fout, fieldnames=reader.fieldnames)
        writer.writeheader()
        for row in reader:
            pif = (row.get("product_identity_fixed") or "").lower().strip()
            old_cp = (row.get("canonical_path") or "").strip()
            if pif and pif in authority:
                new_cp = authority[pif]
                if new_cp != old_cp:
                    row["canonical_path"] = new_cp
                    n_updated += 1
                    log_writer.writerow({
                        "file": path.name,
                        "product_identity_fixed": pif,
                        "old_path": old_cp,
                        "new_path": new_cp,
                    })
            writer.writerow(row)
    shutil.move(str(tmp), str(path))
    print(f"  {path.name}: {n_updated:,} rows updated", file=sys.stderr)
    return n_updated


def main() -> int:
    authority = build_pid_to_path_authority()
    with LOG.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=[
            "file", "product_identity_fixed", "old_path", "new_path",
        ])
        w.writeheader()
        print("\nsyncing api_cache_taxonomy_v2.csv:", file=sys.stderr)
        n_api = sync_csv(API, authority, w)
        print("\nsyncing recipe_ingredient_taxonomy_v2.csv:", file=sys.stderr)
        n_ing = sync_csv(ING, authority, w)

    print(f"\n=== TOTAL ===", file=sys.stderr)
    print(f"  api_cache:          {n_api:,} rows synced", file=sys.stderr)
    print(f"  recipe_ingredient:  {n_ing:,} rows synced", file=sys.stderr)
    print(f"  total:              {n_api + n_ing:,}", file=sys.stderr)
    print(f"  → {LOG}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
