#!/usr/bin/env python3
"""One-shot: prefix htc_code (and htc_sku_code) with `~` in every output CSV
so Excel doesn't auto-interpret values like "100E0000" as scientific notation.

Idempotent — already-prefixed values are skipped.
"""
from __future__ import annotations

import csv
import shutil
import sys
from pathlib import Path

csv.field_size_limit(sys.maxsize)

ROOT = Path(__file__).resolve().parents[1]
PREFIX = "~"

TARGETS = [
    ROOT / "recipe_mapper" / "v1" / "output" / "consensus_htc_tagged.csv",
    ROOT / "recipe_mapper" / "v1" / "output" / "recipe_ingredient_htc_tagged.csv",
    ROOT / "recipe_pricing" / "output" / "api_cache_htc_tagged.csv",
    ROOT / "recipe_pricing" / "output" / "api_cache_taxonomy_v2.csv",
    ROOT / "recipe_pricing" / "output" / "sr28_fndds_taxonomy_v2.csv",
    ROOT / "recipe_mapper" / "v1" / "output" / "recipe_ingredient_taxonomy_v2.csv",
    ROOT / "recipe_mapper" / "v1" / "output" / "ingredient_full_audit.csv",
]

CODE_FIELDS = ("htc_code", "htc_sku_code")


def prefix_one(path: Path) -> tuple[int, int]:
    """Returns (rows_processed, codes_prefixed)."""
    if not path.exists():
        print(f"  skip missing: {path}", file=sys.stderr)
        return 0, 0
    tmp = path.with_suffix(".csv.tmp")
    n = prefixed = 0
    with path.open(newline="") as fin, tmp.open("w", newline="") as fout:
        reader = csv.DictReader(fin)
        fieldnames = reader.fieldnames or []
        present_code_fields = [f for f in CODE_FIELDS if f in fieldnames]
        if not present_code_fields:
            print(f"  no code fields in: {path}", file=sys.stderr)
            return 0, 0
        writer = csv.DictWriter(fout, fieldnames=fieldnames)
        writer.writeheader()
        for row in reader:
            n += 1
            for field in present_code_fields:
                v = (row.get(field) or "").strip()
                if v and not v.startswith(PREFIX):
                    row[field] = PREFIX + v
                    prefixed += 1
            writer.writerow(row)
    shutil.move(str(tmp), str(path))
    return n, prefixed


def main() -> int:
    total_rows = 0
    total_prefixed = 0
    for path in TARGETS:
        n, p = prefix_one(path)
        total_rows += n
        total_prefixed += p
        print(f"  {path.name}: {n:,} rows, {p:,} codes prefixed", file=sys.stderr)
    print(f"total: {total_rows:,} rows, {total_prefixed:,} codes prefixed", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
