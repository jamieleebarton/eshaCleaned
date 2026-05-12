#!/usr/bin/env python3
"""Add normalized identity columns to recipe_ingredient_taxonomy_v2.csv.

For each recipe ingredient row, run the normalizer and add:
  - normalized_canonical_text   (Bucket 3 + core tokens, no facet adjectives)
  - normalized_user_claims      (Bucket 1 — preference facets)
  - normalized_form_facets      (Bucket 2 — culinary form/cut)
  - normalized_processing_facets(Bucket 2 — cooking / preservation)
  - normalized_identity_phrase  (Bucket 3 phrase if matched)

The original title and the LLM-emitted canonical_path/htc_code are kept as-is.
Downstream (the planner) can join on normalized_canonical_text + facets to
collapse synonyms and project user preferences at runtime.

Idempotent — re-running overwrites the columns.
"""
from __future__ import annotations

import csv
import shutil
import sys
from pathlib import Path

csv.field_size_limit(sys.maxsize)

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from recipe_mapper.v1.normalizer.normalize import normalize_ingredient

TAX = ROOT / "recipe_mapper" / "v1" / "output" / "recipe_ingredient_taxonomy_v2.csv"
HTC = ROOT / "recipe_mapper" / "v1" / "output" / "recipe_ingredient_htc_tagged.csv"
AUDIT = ROOT / "recipe_mapper" / "v1" / "output" / "ingredient_full_audit.csv"

NEW_COLS = [
    "normalized_canonical_text",
    "normalized_user_claims",
    "normalized_form_facets",
    "normalized_processing_facets",
    "normalized_identity_phrase",
]


def enrich_csv(path: Path, name_field: str = "title") -> int:
    if not path.exists():
        print(f"missing {path}", file=sys.stderr)
        return 0
    tmp = path.with_suffix(".csv.tmp")
    n = 0
    with path.open(newline="") as fin, tmp.open("w", newline="") as fout:
        reader = csv.DictReader(fin)
        fieldnames = list(reader.fieldnames or [])
        for col in NEW_COLS:
            if col not in fieldnames:
                fieldnames.append(col)
        writer = csv.DictWriter(fout, fieldnames=fieldnames)
        writer.writeheader()
        for row in reader:
            n += 1
            t = (row.get(name_field) or "").strip()
            r = normalize_ingredient(t)
            row["normalized_canonical_text"] = r.canonical_text
            row["normalized_user_claims"] = " | ".join(r.user_claims)
            row["normalized_form_facets"] = " | ".join(r.form_facets)
            row["normalized_processing_facets"] = " | ".join(r.processing_facets)
            row["normalized_identity_phrase"] = r.identity_phrase or ""
            writer.writerow(row)
    shutil.move(str(tmp), str(path))
    print(f"  {path.name}: {n:,} rows enriched", file=sys.stderr)
    return n


def main() -> int:
    enrich_csv(TAX, name_field="title")
    enrich_csv(HTC, name_field="item")
    enrich_csv(AUDIT, name_field="item")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
