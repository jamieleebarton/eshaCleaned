#!/usr/bin/env python3
"""Apply path consolidation rules from duplicate_canonical_paths.csv.

For each duplicate group, the canonical path is the one with the most uses.
All non-canonical variants get rewritten to the canonical across all four
golden files.

Backups:
  *.before_path_consolidation

Outputs:
  recipe_pricing/path_consolidation_log.csv
"""
from __future__ import annotations

import csv
import shutil
import sqlite3
import sys
from pathlib import Path

csv.field_size_limit(sys.maxsize)

ROOT = Path(__file__).resolve().parents[1]
DUPS = ROOT / "recipe_pricing" / "duplicate_canonical_paths.csv"
DB = ROOT / "recipe_pricing" / "data" / "priced_products_v2.db"
API = ROOT / "recipe_pricing" / "output" / "api_cache_taxonomy_v2.csv"
ING = ROOT / "recipe_mapper" / "v1" / "output" / "recipe_ingredient_taxonomy_v2.csv"
CONSENSUS = ROOT / "retail_mapper" / "v2" / "consensus_full_corpus_audit.csv"
LOG = ROOT / "recipe_pricing" / "path_consolidation_log.csv"


def main() -> int:
    if not DUPS.exists():
        raise SystemExit(f"missing {DUPS}")

    # Build remap: variant_path → canonical_path
    remap: dict[str, str] = {}
    with DUPS.open() as f:
        for row in csv.DictReader(f):
            variant = row["canonical_path"]
            canonical = row["canonical_path_chosen"]
            if variant != canonical:
                remap[variant] = canonical
    print(f"path remap rules: {len(remap):,}", file=sys.stderr)

    # Apply to priced_products
    backup_db = DB.with_suffix(".db.before_path_consolidation")
    if not backup_db.exists():
        print(f"backup → {backup_db}", file=sys.stderr)
        shutil.copy(str(DB), str(backup_db))
    con = sqlite3.connect(str(DB))
    cur = con.cursor()
    n_db = 0
    for variant, canonical in remap.items():
        cur.execute("UPDATE priced_products SET consensus_canonical = ? WHERE consensus_canonical = ?",
                    (canonical, variant))
        n_db += cur.rowcount
    con.commit()
    print(f"priced_products: {n_db:,} rows updated", file=sys.stderr)

    # Apply to CSVs
    def update_csv(path: Path, cp_field: str = "canonical_path") -> int:
        if not path.exists():
            print(f"  missing {path}", file=sys.stderr)
            return 0
        backup = path.with_suffix(path.suffix + ".before_path_consolidation")
        if not backup.exists():
            print(f"  backup → {backup}", file=sys.stderr)
            shutil.copy(str(path), str(backup))
        tmp = path.with_suffix(".csv.tmp")
        n = 0
        with path.open(newline="") as fin, tmp.open("w", newline="") as fout:
            reader = csv.DictReader(fin)
            writer = csv.DictWriter(fout, fieldnames=reader.fieldnames)
            writer.writeheader()
            for row in reader:
                cp = (row.get(cp_field) or "").strip()
                if cp in remap:
                    row[cp_field] = remap[cp]
                    n += 1
                writer.writerow(row)
        shutil.move(str(tmp), str(path))
        print(f"  {path.name}: {n:,} rows updated", file=sys.stderr)
        return n

    print(f"\napi_cache:", file=sys.stderr)
    n_api = update_csv(API)
    print(f"\nrecipe_ingredient_taxonomy:", file=sys.stderr)
    n_ing = update_csv(ING)
    print(f"\nconsensus_full_corpus_audit:", file=sys.stderr)
    n_consensus = update_csv(CONSENSUS)

    # Log
    with LOG.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["variant_path", "canonical_path"])
        w.writeheader()
        for variant, canonical in remap.items():
            w.writerow({"variant_path": variant, "canonical_path": canonical})

    print(f"\n=== TOTAL ===", file=sys.stderr)
    print(f"  priced_products:    {n_db:,}", file=sys.stderr)
    print(f"  api_cache:          {n_api:,}", file=sys.stderr)
    print(f"  recipe_ingredient:  {n_ing:,}", file=sys.stderr)
    print(f"  consensus_full:     {n_consensus:,}", file=sys.stderr)
    print(f"  total rows updated: {n_db + n_api + n_ing + n_consensus:,}", file=sys.stderr)
    print(f"  → {LOG}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
