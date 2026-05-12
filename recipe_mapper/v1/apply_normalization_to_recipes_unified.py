#!/usr/bin/env python3
"""Apply the recipe-line normalizer to recipes_unified.csv per-row.

For each row, run normalize_ingredient() on `display` (with fallback to
`ingredient_item` if display is empty) and append:

  - normalized_canonical_text    (Bucket 3 + core tokens)
  - normalized_user_claims        | Bucket 1
  - normalized_form_facets        | Bucket 2 form
  - normalized_processing_facets  | Bucket 2 processing
  - normalized_identity_phrase    | Bucket 3 phrase

This is the recipe-side counterpart to apply_normalization_to_taxonomy.py
(which annotates the per-unique-item taxonomy). Together they let the planner
project user facets (organic, fat-free, etc.) onto canonical recipes at
runtime.

Idempotent: re-running overwrites the columns.
"""
from __future__ import annotations

import csv
import shutil
import sys
import time
from pathlib import Path

csv.field_size_limit(sys.maxsize)

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from recipe_mapper.v1.normalizer.normalize import normalize_ingredient

UNIFIED = ROOT / "recipe_mapper" / "v1" / "output" / "recipes_unified.csv"

NEW_COLS = [
    "normalized_canonical_text",
    "normalized_user_claims",
    "normalized_form_facets",
    "normalized_processing_facets",
    "normalized_identity_phrase",
]


def main() -> int:
    if not UNIFIED.exists():
        raise SystemExit(f"missing {UNIFIED}")

    tmp = UNIFIED.with_suffix(".csv.tmp")
    n = 0
    t0 = time.time()
    cache: dict[str, tuple[str, str, str, str, str]] = {}

    with UNIFIED.open(newline="") as fin, tmp.open("w", newline="") as fout:
        reader = csv.DictReader(fin)
        fieldnames = list(reader.fieldnames or [])
        for col in NEW_COLS:
            if col not in fieldnames:
                fieldnames.append(col)
        writer = csv.DictWriter(fout, fieldnames=fieldnames)
        writer.writeheader()

        for row in reader:
            n += 1
            text = (row.get("display") or "").strip()
            if not text:
                text = (row.get("ingredient_item") or "").strip()

            if text in cache:
                ct, uc, ff, pf, ip = cache[text]
            else:
                r = normalize_ingredient(text)
                ct = r.canonical_text
                uc = " | ".join(r.user_claims)
                ff = " | ".join(r.form_facets)
                pf = " | ".join(r.processing_facets)
                ip = r.identity_phrase or ""
                cache[text] = (ct, uc, ff, pf, ip)

            row["normalized_canonical_text"] = ct
            row["normalized_user_claims"] = uc
            row["normalized_form_facets"] = ff
            row["normalized_processing_facets"] = pf
            row["normalized_identity_phrase"] = ip
            writer.writerow(row)

            if n % 250_000 == 0:
                rate = n / (time.time() - t0)
                print(f"  {n:>9,} rows  ({rate:>7,.0f} rows/sec, cache={len(cache):,})",
                      file=sys.stderr)

    shutil.move(str(tmp), str(UNIFIED))
    print(f"\nfinished {n:,} rows in {time.time() - t0:.1f}s", file=sys.stderr)
    print(f"unique texts cached: {len(cache):,}", file=sys.stderr)
    print(f"  → {UNIFIED}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
