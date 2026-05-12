#!/usr/bin/env python3
"""Reorder columns in every htc-tagged file so the code group sits right next
to its description. Audit-friendly layout:

    [id, title]
    htc_code, htc_sku_code, htc_full_code      ← the codes
    retail_leaf_path                            ← what the code IS (description)
    canonical_path
    product_identity_fixed
    [...facets, claims, etc...]
    [...remaining columns...]

Idempotent — re-running just produces the same layout.
"""
from __future__ import annotations

import csv
import shutil
import sys
from pathlib import Path

csv.field_size_limit(sys.maxsize)

ROOT = Path(__file__).resolve().parents[1]

# Columns to pull to the front, in this order. Missing ones are skipped.
PRIORITY = [
    "fdc_id", "item", "title", "source", "corpus", "retail_type",
    "htc_code", "htc_sku_code", "htc_full_code",
    "retail_leaf_path", "retail_leaf_source",
    "canonical_path", "canonical_label",
    "product_identity_fixed",
    "variant", "flavor", "form_texture_cut", "processing_storage",
    "claims", "modifier",
    "htc_group", "htc_family", "htc_food",
    "htc_form", "htc_processing", "htc_ptype", "htc_check",
    "htc_confidence", "htc_source",
    "match_method", "match_confidence",
    "fndds_code", "sr28_code", "esha_code",
]

TARGETS = [
    ROOT / "recipe_mapper" / "v1" / "output" / "consensus_htc_tagged.csv",
    ROOT / "recipe_mapper" / "v1" / "output" / "recipe_ingredient_htc_tagged.csv",
    ROOT / "recipe_pricing" / "output" / "api_cache_htc_tagged.csv",
    ROOT / "recipe_pricing" / "output" / "api_cache_taxonomy_v2.csv",
    ROOT / "recipe_pricing" / "output" / "sr28_fndds_taxonomy_v2.csv",
    ROOT / "recipe_mapper" / "v1" / "output" / "recipe_ingredient_taxonomy_v2.csv",
    ROOT / "recipe_mapper" / "v1" / "output" / "ingredient_full_audit.csv",
    ROOT / "retail_mapper" / "v2" / "consensus_full_corpus_audit.csv",
]


def reorder(path: Path) -> int:
    if not path.exists():
        print(f"  skip missing: {path}", file=sys.stderr)
        return 0
    tmp = path.with_suffix(".csv.tmp")
    n = 0
    with path.open(newline="") as fin, tmp.open("w", newline="") as fout:
        reader = csv.DictReader(fin)
        original = reader.fieldnames or []
        # Front: priority columns that exist
        front = [c for c in PRIORITY if c in original]
        # Back: anything not already in front, preserving original order
        back = [c for c in original if c not in front]
        new_order = front + back
        writer = csv.DictWriter(fout, fieldnames=new_order)
        writer.writeheader()
        for row in reader:
            n += 1
            writer.writerow(row)
    shutil.move(str(tmp), str(path))
    return n


def main() -> int:
    for path in TARGETS:
        n = reorder(path)
        print(f"  {path.name}: {n:,} rows reordered", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
