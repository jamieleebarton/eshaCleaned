#!/usr/bin/env python3
"""Match a recipe ingredient to its actual retail SKUs.

Two-stage filter:
  1. HTC code prefix — same group/family/form/processing/ptype family
  2. product_identity_fixed match — within that HTC, narrow to SKUs whose
     retail identity matches the ingredient noun (token overlap, longest match)

Returns the actual retail SKU list — what the user would buy.
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

csv.field_size_limit(sys.maxsize)

HERE = Path(__file__).resolve().parent
ING_TAGS = HERE / "output" / "recipe_ingredient_htc_tagged.csv"
CON_TAGS = HERE / "output" / "consensus_htc_tagged.csv"

WS = re.compile(r"\s+")
NONALPHA = re.compile(r"[^a-z0-9 ]+")
STOP = {"fresh", "frozen", "raw", "ground", "whole", "large", "medium", "small",
        "the", "of", "and", "a", "an", "or", "with", "for", "to",
        "boneless", "skinless", "chopped", "diced", "minced", "sliced",
        "extra", "lean", "low", "fat", "free", "organic", "natural"}


def normalize(s: str) -> set[str]:
    s = NONALPHA.sub(" ", (s or "").lower()).strip()
    return {t for t in WS.split(s) if len(t) >= 2 and t not in STOP}


def load() -> tuple[dict, dict]:
    ing = {}
    with ING_TAGS.open() as f:
        for r in csv.DictReader(f):
            ing[r["item"].lower()] = r
    by_htc: dict[str, list] = defaultdict(list)
    with CON_TAGS.open() as f:
        for r in csv.DictReader(f):
            by_htc[r["htc_code"]].append(r)
    return ing, dict(by_htc)


def match_skus(item: str, ing_lookup: dict, retail_by_htc: dict,
               max_results: int = 5) -> dict:
    entry = ing_lookup.get(item.lower())
    if not entry:
        return {"item": item, "error": "not in recipe corpus"}
    code = entry["htc_code"]
    skus = retail_by_htc.get(code, [])
    item_tokens = normalize(item)
    # score each candidate by token overlap with product_identity_fixed
    scored = []
    for s in skus:
        pid = s.get("product_identity_fixed", "") or ""
        pid_tokens = normalize(pid)
        if not pid_tokens:
            continue
        inter = item_tokens & pid_tokens
        if not inter:
            continue
        # prefer pid that exactly equals one of the item tokens, or the
        # item is a substring of the pid, or vice-versa
        bonus = 0.0
        if item.lower() == pid.lower(): bonus += 5.0
        elif pid.lower() in item.lower() or item.lower() in pid.lower(): bonus += 2.0
        score = len(inter) + bonus - 0.05 * len(pid_tokens - item_tokens)
        scored.append((score, s))
    scored.sort(key=lambda x: -x[0])
    # Group by product_identity to dedupe
    pid_counts = Counter()
    for _, s in scored:
        pid_counts[s.get("product_identity_fixed", "")] += 1
    return {
        "item": item,
        "htc_code": code,
        "total_skus_at_htc": len(skus),
        "matching_pid_count": sum(pid_counts.values()),
        "top_pids": pid_counts.most_common(8),
        "sample_skus": [(round(sc, 2), s["title"][:60], s["product_identity_fixed"])
                        for sc, s in scored[:max_results]],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--items", nargs="*", default=[
        "ham", "sliced ham", "bone-in ham", "smoked ham",
        "deli turkey", "ground turkey", "smoked turkey", "turkey breast", "whole turkey",
        "turkey bacon", "bacon",
        "vanilla yogurt", "plain yogurt", "greek yogurt",
        "whole milk", "skim milk", "heavy cream",
        "cheddar cheese", "mozzarella cheese", "parmesan cheese",
        "ground beef", "chicken breast", "boneless skinless chicken breasts",
        "olive oil", "butter", "unsalted butter",
        "salt", "kosher salt", "saffron threads",
    ])
    args = ap.parse_args()

    print("loading lookup tables...")
    ing, by_htc = load()
    print(f"  {len(ing):,} recipe items, {sum(len(v) for v in by_htc.values()):,} "
          f"retail SKUs across {len(by_htc):,} HTCs\n")

    for q in args.items:
        r = match_skus(q, ing, by_htc, max_results=4)
        if "error" in r:
            print(f"  '{q}': {r['error']}")
            continue
        print(f"--- '{q}' (HTC {r['htc_code']}, {r['total_skus_at_htc']:,} SKUs at this HTC)")
        print(f"    top product identities at this HTC matching ingredient:")
        for pid, n in r["top_pids"][:5]:
            if pid:
                print(f"      {n:>4}  {pid!r}")
        if not r["top_pids"]:
            print(f"      (no PID overlap; HTC alone returns {r['total_skus_at_htc']:,} SKUs)")
        print(f"    sample SKUs:")
        for sc, t, pid in r["sample_skus"]:
            print(f"      [{sc}] {t}  ← pid={pid!r}")
        print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
