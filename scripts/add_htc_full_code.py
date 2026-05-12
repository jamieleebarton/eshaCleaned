#!/usr/bin/env python3
"""One-shot: add htc_full_code column to all 7 corpus CSVs.

For each row, compose the full code from htc_code + canonical_path +
retail_leaf_path + claims (and modifier where claims is empty). Idempotent —
running twice rewrites the existing column.

Format: ~GFFOPTC-VVVVVV-KKKK
  bucket  : 8-char htc_code (with `~` prefix)
  variant : 6-hex hash of retail_leaf_path SUFFIX
  claims  : 4-hex bitfield of canonical claim flags
"""
from __future__ import annotations

import csv
import shutil
import sys
from pathlib import Path

csv.field_size_limit(sys.maxsize)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "recipe_mapper" / "v1"))
from htc.full_code import compose_full_code  # noqa: E402

TARGETS = [
    ROOT / "recipe_mapper" / "v1" / "output" / "consensus_htc_tagged.csv",
    ROOT / "recipe_mapper" / "v1" / "output" / "recipe_ingredient_htc_tagged.csv",
    ROOT / "recipe_pricing" / "output" / "api_cache_htc_tagged.csv",
    ROOT / "recipe_pricing" / "output" / "api_cache_taxonomy_v2.csv",
    ROOT / "recipe_pricing" / "output" / "sr28_fndds_taxonomy_v2.csv",
    ROOT / "recipe_mapper" / "v1" / "output" / "recipe_ingredient_taxonomy_v2.csv",
    ROOT / "recipe_mapper" / "v1" / "output" / "ingredient_full_audit.csv",
]


def enrich_one(path: Path) -> tuple[int, int]:
    if not path.exists():
        print(f"  skip missing: {path}", file=sys.stderr)
        return 0, 0
    tmp = path.with_suffix(".csv.tmp")
    n = composed = 0
    with path.open(newline="") as fin, tmp.open("w", newline="") as fout:
        reader = csv.DictReader(fin)
        fieldnames = list(reader.fieldnames or [])
        if "htc_code" not in fieldnames:
            print(f"  skip no htc_code: {path}", file=sys.stderr)
            return 0, 0
        if "htc_full_code" not in fieldnames:
            # Insert right after htc_sku_code if present, else after htc_code
            anchor = "htc_sku_code" if "htc_sku_code" in fieldnames else "htc_code"
            fieldnames.insert(fieldnames.index(anchor) + 1, "htc_full_code")
        writer = csv.DictWriter(fout, fieldnames=fieldnames)
        writer.writeheader()
        for row in reader:
            n += 1
            htc = (row.get("htc_code") or "").strip()
            cp = (row.get("canonical_path") or "").strip()
            rlp = (row.get("retail_leaf_path") or "").strip()
            claims = (row.get("claims") or row.get("modifier") or "").strip()
            if htc:
                row["htc_full_code"] = compose_full_code(htc, cp, rlp, claims)
                composed += 1
            else:
                row["htc_full_code"] = ""
            writer.writerow(row)
    shutil.move(str(tmp), str(path))
    return n, composed


def main() -> int:
    total_n = total_c = 0
    for path in TARGETS:
        n, c = enrich_one(path)
        total_n += n
        total_c += c
        print(f"  {path.name}: {n:,} rows, {c:,} full_codes composed", file=sys.stderr)
    print(f"total: {total_n:,} rows, {total_c:,} codes composed", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
