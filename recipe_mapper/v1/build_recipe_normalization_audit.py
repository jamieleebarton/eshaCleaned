#!/usr/bin/env python3
"""Apply the recipe normalizer to every recipe ingredient and emit an audit CSV.

For each unique recipe ingredient (from recipe_ingredient_taxonomy_v2.csv):
  - Run through the normalizer
  - Show original → canonical_text + extracted facets
  - Group by canonical_text — duplicates that should collapse

Output:
  recipe_mapper/v1/output/recipe_normalization_audit.csv
"""
from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path

csv.field_size_limit(sys.maxsize)

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from recipe_mapper.v1.normalizer.normalize import normalize_ingredient

TAX = ROOT / "recipe_mapper" / "v1" / "output" / "recipe_ingredient_taxonomy_v2.csv"
AUDIT = ROOT / "recipe_mapper" / "v1" / "output" / "ingredient_full_audit.csv"
OUT = ROOT / "recipe_mapper" / "v1" / "output" / "recipe_normalization_audit.csv"


def main() -> int:
    counts = {}
    if AUDIT.exists():
        with AUDIT.open() as f:
            for row in csv.DictReader(f):
                counts[row["item"].lower()] = int(row.get("recipe_count", "0") or 0)

    rows = []
    with TAX.open() as f:
        for row in csv.DictReader(f):
            rows.append(row)
    print(f"recipe ingredients: {len(rows):,}", file=sys.stderr)

    by_canonical: defaultdict[str, list[dict]] = defaultdict(list)
    out_rows = []
    for row in rows:
        title = row.get("title", "")
        n = normalize_ingredient(title)
        canonical_text = n.canonical_text
        out_rows.append({
            "original_title": title,
            "canonical_text": canonical_text,
            "user_claims": " | ".join(n.user_claims),
            "form_facets": " | ".join(n.form_facets),
            "processing_facets": " | ".join(n.processing_facets),
            "identity_phrase": n.identity_phrase or "",
            "raw_quantity": n.raw_quantity,
            "current_canonical_path": row.get("canonical_path", ""),
            "current_htc_code": row.get("htc_code", ""),
            "recipe_count": counts.get(title.lower(), 0),
        })
        if canonical_text:
            by_canonical[canonical_text].append(row)

    # Sort: canonical with most rows first (biggest collapses surface)
    out_rows.sort(key=lambda r: (-len(by_canonical.get(r["canonical_text"], [])),
                                 -r["recipe_count"]))
    with OUT.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=[
            "original_title", "canonical_text", "user_claims",
            "form_facets", "processing_facets", "identity_phrase",
            "raw_quantity", "current_canonical_path", "current_htc_code",
            "recipe_count",
        ])
        w.writeheader()
        w.writerows(out_rows)

    # Summary
    distinct_originals = len(rows)
    distinct_canonicals = len(by_canonical)
    collapse_groups = sum(1 for v in by_canonical.values() if len(v) > 1)
    collapse_rows = sum(len(v) for v in by_canonical.values() if len(v) > 1)
    print(f"distinct original titles:    {distinct_originals:,}", file=sys.stderr)
    print(f"distinct canonical texts:    {distinct_canonicals:,}", file=sys.stderr)
    print(f"collapsed groups (>=2 originals same canonical): {collapse_groups:,}", file=sys.stderr)
    print(f"  rows in those groups: {collapse_rows:,}", file=sys.stderr)
    print(f"  → {OUT}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
