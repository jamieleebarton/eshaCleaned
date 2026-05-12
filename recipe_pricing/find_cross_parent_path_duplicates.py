#!/usr/bin/env python3
"""Find paths whose LEAF identity is the same but PARENT chain differs.

Example duplicates:
  Dairy > Cheese > Mozzarella       (leaf 'mozzarella')
  Pantry > Mozzarella Cheese        (leaf 'mozzarella cheese' contains 'mozzarella')

These can't be detected by full-path-normalize because the parent chains
differ entirely. Detection: extract the leaf token(s), find other paths
whose leaf has overlapping food-noun tokens.

Output:
  recipe_pricing/cross_parent_path_duplicates.csv
"""
from __future__ import annotations

import csv
import re
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

csv.field_size_limit(sys.maxsize)

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "recipe_pricing" / "data" / "priced_products_v2.db"
API = ROOT / "recipe_pricing" / "output" / "api_cache_taxonomy_v2.csv"
ING = ROOT / "recipe_mapper" / "v1" / "output" / "recipe_ingredient_taxonomy_v2.csv"
CONSENSUS = ROOT / "retail_mapper" / "v2" / "consensus_full_corpus_audit.csv"
OUT = ROOT / "recipe_pricing" / "cross_parent_path_duplicates.csv"


SOFT = {"the","a","an","of","and","or","with","for","in","to","on","fresh","dried",
        "ground","powdered","whole","crushed","chopped","diced","sliced","minced",
        "grated","shredded","frozen","raw","cooked","canned","jarred","pickled",
        "small","medium","large","extra","big","tiny","light","dark"}


def leaf_tokens(path: str) -> frozenset[str]:
    """Extract significant tokens from the LEAF segment, normalized."""
    if not path or " > " not in path:
        leaf = path.strip()
    else:
        leaf = path.split(" > ")[-1].strip()
    leaf_lower = leaf.lower()
    leaf_clean = re.sub(r"[^\w\s]", "", leaf_lower)
    tokens = set()
    for w in leaf_clean.split():
        if w in SOFT or len(w) <= 2:
            continue
        # singularize
        if w.endswith("s") and not w.endswith("ss") and len(w) > 3:
            w = w[:-1]
        tokens.add(w)
    return frozenset(tokens)


def main() -> int:
    # Pull all paths + product counts
    print("scanning sources...", file=sys.stderr)
    path_counts: defaultdict[str, int] = defaultdict(int)
    if DB.exists():
        con = sqlite3.connect(str(DB))
        cur = con.cursor()
        cur.execute("""
            SELECT consensus_canonical, COUNT(*) FROM priced_products
            WHERE consensus_canonical != '' AND available = 1
            GROUP BY consensus_canonical
        """)
        for cp, n in cur.fetchall():
            path_counts[cp] += n
        con.close()
    for src in [API, ING, CONSENSUS]:
        if not src.exists():
            continue
        with src.open() as f:
            for row in csv.DictReader(f):
                cp = (row.get("canonical_path") or "").strip()
                if cp:
                    path_counts[cp] += 1

    # Group by leaf token set
    by_tokens: defaultdict[frozenset, list[str]] = defaultdict(list)
    for path in path_counts:
        toks = leaf_tokens(path)
        if not toks:
            continue
        by_tokens[toks].append(path)

    # Pairs: same leaf-tokens, different paths (any parent)
    duplicate_groups = []
    for toks, paths in by_tokens.items():
        if len(paths) < 2:
            continue
        # Filter to "interesting" groups: ≥3 product-count and tokens are
        # specific (not generic single words like "cheese" or "salt")
        if len(toks) == 0:
            continue
        sorted_paths = sorted(paths, key=lambda p: -path_counts[p])
        canonical = sorted_paths[0]
        canonical_n = path_counts[canonical]
        if canonical_n < 5:
            continue  # skip tiny groups
        for variant in sorted_paths[1:]:
            variant_n = path_counts[variant]
            duplicate_groups.append({
                "leaf_tokens": "|".join(sorted(toks)),
                "canonical_path": canonical,
                "variant_path": variant,
                "canonical_n": canonical_n,
                "variant_n": variant_n,
                "total_n": canonical_n + variant_n,
            })

    duplicate_groups.sort(key=lambda r: -r["variant_n"])

    with OUT.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=[
            "leaf_tokens", "canonical_path", "variant_path",
            "canonical_n", "variant_n", "total_n",
        ])
        w.writeheader()
        w.writerows(duplicate_groups)

    print(f"\nfound {len(duplicate_groups):,} cross-parent duplicate pairs", file=sys.stderr)
    print(f"variant products that could merge: {sum(r['variant_n'] for r in duplicate_groups):,}", file=sys.stderr)
    print(f"\nTop 25 by variant_n (most consolidatable):", file=sys.stderr)
    for r in duplicate_groups[:25]:
        print(f"  variant={r['variant_n']:>4}  canonical={r['canonical_n']:>5}  "
              f"[{r['leaf_tokens']}]", file=sys.stderr)
        print(f"     CANONICAL: {r['canonical_path']}", file=sys.stderr)
        print(f"     VARIANT  : {r['variant_path']}", file=sys.stderr)
    print(f"\n  → {OUT}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
