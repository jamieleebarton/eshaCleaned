#!/usr/bin/env python3
"""Build a canonical_buy_form → canonical_path lookup table.

For each unique `canonical_buy_form` in the cleaned classifier output,
find the most-confident `canonical_path` to use when the planner queries
priced_products. Sources, in priority order:

  1. EXACT match in api_cache_taxonomy_v2.csv where
     LOWER(product_identity_fixed) == LOWER(canonical_buy_form)
     → take the most common canonical_path among those products
  2. EXACT match in api_cache where
     LOWER(canonical_label) == LOWER(canonical_buy_form)
  3. Plural/singular tolerance on (1) and (2)
  4. Fall back to recipe_ingredient_taxonomy_v2.csv where title matches

Output: recipe_pricing/buy_form_to_canonical_path.csv
  columns: canonical_buy_form, canonical_path, source, n_products
"""
from __future__ import annotations

import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

csv.field_size_limit(sys.maxsize)

ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "recipe_pricing" / "output" / "api_cache_taxonomy_v2.csv"
RECIPE_TAX = ROOT / "recipe_mapper" / "v1" / "output" / "recipe_ingredient_taxonomy_v2.csv"
CLEANED_CLS = ROOT / "recipe_pricing" / "buyability_classifications_cleaned.jsonl"
OUT = ROOT / "recipe_pricing" / "buy_form_to_canonical_path.csv"


def normalize(s: str) -> str:
    s = (s or "").lower().strip()
    return s


def singular(s: str) -> str:
    if s.endswith("ss") or len(s) <= 3:
        return s
    if s.endswith("ies"):
        return s[:-3] + "y"
    if s.endswith("es") and not s.endswith("oes"):
        return s[:-2]
    if s.endswith("s"):
        return s[:-1]
    return s


def main() -> int:
    # 1. Pull all unique canonical_buy_form values from the cleaned classifier
    print(f"loading canonical_buy_form values from cleaned classifier...", file=sys.stderr)
    buy_forms: Counter[str] = Counter()
    with CLEANED_CLS.open() as f:
        for line in f:
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            for c in r.get("classifications", []):
                bf = (c.get("canonical_buy_form") or "").strip()
                if bf:
                    buy_forms[normalize(bf)] += 1
    print(f"  {len(buy_forms):,} unique canonical_buy_form values", file=sys.stderr)

    # 2. Index api_cache_taxonomy_v2 by product_identity_fixed and canonical_label
    #    Each key → Counter of canonical_path → count
    print(f"indexing api_cache by pif and label...", file=sys.stderr)
    pif_index: defaultdict[str, Counter] = defaultdict(Counter)
    label_index: defaultdict[str, Counter] = defaultdict(Counter)
    n_api = 0
    with API.open() as f:
        for row in csv.DictReader(f):
            n_api += 1
            cp = (row.get("canonical_path") or "").strip()
            if not cp:
                continue
            pif = normalize(row.get("product_identity_fixed", ""))
            lbl = normalize(row.get("canonical_label", ""))
            if pif:
                pif_index[pif][cp] += 1
            if lbl and lbl != pif:
                label_index[lbl][cp] += 1
    print(f"  indexed {n_api:,} api_cache rows", file=sys.stderr)
    print(f"  unique pif keys:    {len(pif_index):,}", file=sys.stderr)
    print(f"  unique label keys:  {len(label_index):,}", file=sys.stderr)

    # 3. Index recipe_ingredient_taxonomy_v2 by title
    print(f"indexing recipe_ingredient_taxonomy_v2 by title...", file=sys.stderr)
    title_index: defaultdict[str, Counter] = defaultdict(Counter)
    with RECIPE_TAX.open() as f:
        for row in csv.DictReader(f):
            cp = (row.get("canonical_path") or "").strip()
            if not cp:
                continue
            t = normalize(row.get("title", ""))
            if t:
                title_index[t][cp] += 1
    print(f"  unique title keys:  {len(title_index):,}", file=sys.stderr)

    # 4. For each canonical_buy_form, look up its canonical_path.
    # Reject paths that are TOO SHALLOW (≤1 segment, e.g. just "Pantry")
    # since those will match too many unrelated products. Keep looking
    # for a deeper path.
    def is_too_shallow(p: str) -> bool:
        return p.count(" > ") < 1  # need at least 2 segments

    rows_out = []
    n_resolved = 0
    n_unresolved = 0
    sources: Counter[str] = Counter()
    for bf, occurrences in buy_forms.most_common():
        cp = None
        source = "unresolved"
        n_products = 0

        # try strategies in priority order; skip too-shallow paths
        attempts = [
            (pif_index, bf, "pif"),
            (label_index, bf, "label"),
            (title_index, bf, "recipe_title"),
        ]
        sing = singular(bf)
        if sing != bf:
            attempts.extend([
                (pif_index, sing, "pif_singular"),
                (label_index, sing, "label_singular"),
                (title_index, sing, "recipe_title_singular"),
            ])
        plur = bf + "s" if not bf.endswith("s") else bf
        if plur != bf:
            attempts.extend([
                (pif_index, plur, "pif_plural"),
                (label_index, plur, "label_plural"),
                (title_index, plur, "recipe_title_plural"),
            ])

        for index, key, label in attempts:
            if key not in index:
                continue
            # Try most-common path, but skip too-shallow ones — keep picking
            # the next-most-common until we get a deep enough path.
            for cp_candidate, count in index[key].most_common(10):
                if not is_too_shallow(cp_candidate):
                    cp = cp_candidate
                    n_products = count
                    source = label
                    break
            if cp:
                break

        if cp:
            n_resolved += 1
        else:
            n_unresolved += 1
        sources[source] += 1
        rows_out.append({
            "canonical_buy_form": bf,
            "canonical_path": cp or "",
            "source": source,
            "n_products": n_products,
            "buy_form_recipe_count": occurrences,
        })

    # Sort: unresolved first by occurrences (most painful gaps), then resolved by occurrences
    rows_out.sort(key=lambda r: (r["canonical_path"] != "", -r["buy_form_recipe_count"]))

    with OUT.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=[
            "canonical_buy_form", "canonical_path", "source",
            "n_products", "buy_form_recipe_count",
        ])
        w.writeheader()
        w.writerows(rows_out)

    print(f"\nresolved:    {n_resolved:,}", file=sys.stderr)
    print(f"unresolved:  {n_unresolved:,}", file=sys.stderr)
    print(f"sources distribution:", file=sys.stderr)
    for src, cnt in sources.most_common():
        print(f"  {src:<22} {cnt:>6,}", file=sys.stderr)
    print(f"\nOutput: {OUT}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
