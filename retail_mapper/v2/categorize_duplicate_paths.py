#!/usr/bin/env python3
"""Categorize the 14k duplicate-path pairs into actionable buckets.

Output: retail_mapper/v2/duplicate_path_buckets.csv with a 'bucket' column
plus per-bucket counts to stdout.

Buckets:
  A_singular_plural       Bar / Bars, Cone / Cones, Sandwich / Sandwiches, ...
  B_redundant_parent_word Olive Oil > Virgin > Extra Virgin (parent's word repeats in child)
  B_repeating_segment     Ice Cream > Ice Cream Bar > Bar  (same word starts a child)
  C_cross_family          Same leaf, different top-level (e.g. Pantry vs Beverage)
  D_claim_form_leaf       Leaf is a claim ('High Protein', 'Organic') stuck in a non-matching parent
  E_parent_vs_child_same  parent bucket vs same-top child branch (NOT a duplicate; subtypes — flag only)
  F_other                 anything else
"""
from __future__ import annotations

import csv
import re
import sys
from collections import Counter
from pathlib import Path

V2 = Path("/Users/jamiebarton/Desktop/esha_audit_bundle/retail_mapper/v2")
IN = V2 / "duplicate_path_pairs.csv"
OUT = V2 / "duplicate_path_buckets.csv"

csv.field_size_limit(sys.maxsize)

CLAIM_LEAVES = {
    "high protein", "low fat", "fat free", "low sodium", "no salt added",
    "low sugar", "sugar free", "no sugar added", "reduced fat", "lowfat",
    "organic", "non gmo", "non-gmo", "gluten free", "low calorie",
    "keto", "paleo", "vegan", "kosher", "halal", "natural", "all natural",
    "fortified", "probiotic", "plant based", "dairy free", "lactose free",
    "unsweetened", "sweetened", "premium", "light", "rich",
    "mini", "mini's", "minis", "swirl", "swirled", "bar", "bars",
    "cone", "cones", "sandwich", "sandwiches", "powder",
}

PLURAL_MAP = {
    "bars": "bar", "cones": "cone", "sandwiches": "sandwich",
    "cookies": "cookie", "cakes": "cake", "buns": "bun",
    "loaves": "loaf", "minis": "mini", "balls": "ball", "bites": "bite",
    "wraps": "wrap", "rolls": "roll", "patties": "patty",
    "yogurts": "yogurt", "milks": "milk", "salads": "salad",
    "sauces": "sauce", "soups": "soup", "drinks": "drink",
}


def singularize_token(t: str) -> str:
    return PLURAL_MAP.get(t.lower(), t.lower())


def singularize_path(path: str) -> str:
    segs = path.split(" > ")
    return " > ".join(" ".join(singularize_token(w) for w in s.split()) for s in segs)


def is_singular_plural_pair(a: str, b: str) -> bool:
    return singularize_path(a) == singularize_path(b) and a != b


def has_redundant_parent_word(path: str) -> bool:
    """e.g. 'Olive Oil > Virgin > Extra Virgin' -> 'Virgin' duplicated"""
    segs = path.split(" > ")
    seen_tokens: set[str] = set()
    for s in segs:
        toks = {w.lower() for w in re.findall(r"[A-Za-z0-9]+", s) if len(w) > 2}
        if toks & seen_tokens and toks <= seen_tokens | toks:
            # Check: at least one token in this segment was already in a previous segment
            return True
        seen_tokens |= toks
    return False


def has_repeating_segment_word(path: str) -> bool:
    """e.g. 'Ice Cream > Ice Cream Bar > Bar' — child starts with parent's full segment"""
    segs = path.split(" > ")
    for i in range(1, len(segs)):
        prev = segs[i - 1].lower()
        cur = segs[i].lower()
        if prev != cur and (cur.startswith(prev + " ") or prev.startswith(cur + " ")):
            return True
    return False


def is_cross_family(a: str, b: str) -> bool:
    return a.split(" > ")[0] != b.split(" > ")[0]


def is_parent_vs_child_same_top(a: str, b: str) -> bool:
    return a.startswith(b + " > ") or b.startswith(a + " > ")


def is_claim_form_leaf(a: str, b: str) -> bool:
    """Either path ends in a claim/form leaf and the parent chain is non-matching to that claim."""
    for p in (a, b):
        leaf = p.split(" > ")[-1].lower()
        if leaf in CLAIM_LEAVES:
            return True
    return False


def categorize(a: str, b: str) -> str:
    if is_parent_vs_child_same_top(a, b):
        return "E_parent_vs_child_same"
    if is_singular_plural_pair(a, b):
        return "A_singular_plural"
    if has_redundant_parent_word(a) or has_redundant_parent_word(b):
        return "B_redundant_parent_word"
    if has_repeating_segment_word(a) or has_repeating_segment_word(b):
        return "B_repeating_segment"
    if is_cross_family(a, b):
        if is_claim_form_leaf(a, b):
            return "D_claim_form_leaf"
        return "C_cross_family"
    if is_claim_form_leaf(a, b):
        return "D_claim_form_leaf"
    return "F_other"


def main() -> None:
    rows: list[dict] = []
    with IN.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            r["bucket"] = categorize(r["path_a"], r["path_b"])
            rows.append(r)

    bucket_count = Counter(r["bucket"] for r in rows)
    print(f"  {len(rows):,} pairs categorized")
    for b, n in sorted(bucket_count.items(), key=lambda x: -x[1]):
        print(f"    {b:<30} {n:>5}")

    cols = list(rows[0].keys())
    with OUT.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    print(f"  wrote {OUT.name}")

    # Per-bucket samples (top 10)
    for bucket in sorted(bucket_count, key=lambda b: -bucket_count[b]):
        print(f"\n=== {bucket} — top 10 by impact ===")
        sub = [r for r in rows if r["bucket"] == bucket]
        sub.sort(key=lambda r: -int(r["total_skus"]))
        for r in sub[:10]:
            print(f"  sim={r['centroid_sim']} {r['sku_a']:>4}+{r['sku_b']:>4}  "
                  f"A: {r['path_a']}\n                              B: {r['path_b']}")


if __name__ == "__main__":
    main()
