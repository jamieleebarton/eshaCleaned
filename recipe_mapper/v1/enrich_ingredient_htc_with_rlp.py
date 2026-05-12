#!/usr/bin/env python3
"""Enrich recipe_ingredient_htc_tagged.csv from recipe_ingredient_taxonomy_v2.csv.

The legacy `tag_ingredients_with_htc.py` only sees the item string and produces
htc_codes that DO NOT match FDC because they're not derived from canonical_path
+ product_identity. The v2 taxonomy has the correct codes (computed via
cleanup_llm_output.py::derive_htc against canonical_path + facets, joining
properly to FDC's consensus_htc_tagged.csv).

This enricher overwrites the legacy file's:
  - htc_code, htc_sku_code, htc_full_code
  - htc_group, htc_family, htc_food, htc_form, htc_processing, htc_ptype, htc_check
  - canonical_path, retail_leaf_path
With the values from the v2 taxonomy, joined on `item`.

Result: same identity → same code across all four corpora (FDC retail, Walmart/
Kroger, SR28/FNDDS, recipe ingredients).
"""
from __future__ import annotations

import csv
import shutil
import sys
from pathlib import Path

csv.field_size_limit(sys.maxsize)

HERE = Path(__file__).resolve().parent
LEGACY = HERE / "output" / "recipe_ingredient_htc_tagged.csv"
V2 = HERE / "output" / "recipe_ingredient_taxonomy_v2.csv"


def main() -> int:
    if not LEGACY.exists():
        print(f"missing {LEGACY}", file=sys.stderr)
        return 2
    if not V2.exists():
        print(f"missing {V2}", file=sys.stderr)
        return 2

    # Fields to copy from v2 to legacy. Codes + paths so legacy matches FDC.
    COPY_FIELDS = (
        "htc_code", "htc_sku_code", "htc_full_code",
        "htc_group", "htc_family", "htc_food",
        "htc_form", "htc_processing", "htc_ptype", "htc_check",
        "canonical_path", "retail_leaf_path",
    )

    # item (lowercased) → dict of v2 fields
    ing_meta: dict[str, dict[str, str]] = {}
    with V2.open() as f:
        for row in csv.DictReader(f):
            key = (row.get("title") or row.get("item") or "").strip().lower()
            if not key:
                continue
            ing_meta[key] = {fld: (row.get(fld) or "").strip() for fld in COPY_FIELDS}

    print(f"v2 lookup: {len(ing_meta):,} items", file=sys.stderr)

    tmp = LEGACY.with_suffix(".csv.tmp")
    enriched = unmatched = 0
    with LEGACY.open(newline="") as fin, tmp.open("w", newline="") as fout:
        reader = csv.DictReader(fin)
        fieldnames = list(reader.fieldnames or [])
        # Make sure every field we want to copy exists in the legacy schema
        anchor = "htc_code" if "htc_code" in fieldnames else None
        for fld in COPY_FIELDS:
            if fld not in fieldnames:
                if anchor and fld in ("canonical_path", "retail_leaf_path", "htc_sku_code", "htc_full_code"):
                    fieldnames.insert(fieldnames.index(anchor) + 1, fld)
                else:
                    fieldnames.append(fld)
        writer = csv.DictWriter(fout, fieldnames=fieldnames)
        writer.writeheader()
        for row in reader:
            item = (row.get("item") or "").strip().lower()
            v2_data = ing_meta.get(item)
            if v2_data:
                # Overwrite with v2 (the authoritative codes)
                for fld in COPY_FIELDS:
                    if v2_data.get(fld):
                        row[fld] = v2_data[fld]
                enriched += 1
            else:
                for fld in COPY_FIELDS:
                    row.setdefault(fld, "")
                unmatched += 1
            writer.writerow(row)

    shutil.move(str(tmp), str(LEGACY))
    print(f"  enriched: {enriched:,}", file=sys.stderr)
    print(f"  unmatched (no v2 row): {unmatched:,}", file=sys.stderr)
    print(f"  → {LEGACY}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
