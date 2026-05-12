#!/usr/bin/env python3
"""Find DUPLICATE canonical_path values across all golden files.

Two paths are duplicates if they normalize to the same string:
  - case-insensitive
  - whitespace stripped (so "Cornmeal" == "Corn Meal")
  - punctuation stripped
  - singular form (so "Bay Leaves" == "Bay Leaf")
  - leaf-token order independent (handles "Mozzarella Cheese" vs "Cheese > Mozzarella")
    by sorting tokens of the LEAF only

Sources scanned:
  recipe_pricing/data/priced_products_v2.db (consensus_canonical)
  recipe_pricing/output/api_cache_taxonomy_v2.csv (canonical_path)
  recipe_mapper/v1/output/recipe_ingredient_taxonomy_v2.csv (canonical_path)
  retail_mapper/v2/consensus_full_corpus_audit.csv (canonical_path)

Output:
  recipe_pricing/duplicate_canonical_paths.csv
    columns: canonical_path, normalized_key, n_products,
             n_api_rows, n_recipe_rows, n_consensus_rows, total_uses
    sorted with most-used path FIRST per duplicate group
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
OUT = ROOT / "recipe_pricing" / "duplicate_canonical_paths.csv"


def normalize_segment(seg: str) -> str:
    """Normalize a single path segment: lower, no punct, no whitespace, singular."""
    s = seg.lower().strip()
    s = re.sub(r"[-_]+", "", s)        # collapse hyphens/underscores
    s = re.sub(r"[^\w]", "", s)         # drop non-word chars
    # singularize: drop trailing 's' but not 'ss'
    if s.endswith("s") and not s.endswith("ss") and len(s) > 3:
        s = s[:-1]
    return s


def normalize_path(path: str) -> str:
    """Normalize an entire canonical_path. Each segment normalized. Last
    segment's tokens are sorted (so 'Mozzarella Cheese' == 'Cheese Mozzarella')."""
    segs = [s.strip() for s in path.split(" > ") if s.strip()]
    if not segs:
        return ""
    parents = [normalize_segment(s) for s in segs[:-1]]
    leaf = segs[-1]
    # Tokenize the leaf and normalize each token, then SORT
    leaf_tokens = sorted(normalize_segment(t) for t in leaf.split() if t.strip())
    return ">".join(parents + ["".join(leaf_tokens)])


def main() -> int:
    # Scan each source, accumulating (path, source_file, n) tuples
    print("scanning sources...", file=sys.stderr)
    path_counts: defaultdict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    if DB.exists():
        con = sqlite3.connect(str(DB))
        cur = con.cursor()
        cur.execute("""
            SELECT consensus_canonical, COUNT(*) FROM priced_products
            WHERE consensus_canonical != '' AND available = 1
            GROUP BY consensus_canonical
        """)
        for cp, n in cur.fetchall():
            path_counts[cp]["priced_products"] = n
        con.close()
        print(f"  priced_products: {sum(path_counts[p]['priced_products'] for p in path_counts):,} products", file=sys.stderr)

    for src_path, src_label, cp_field in [
        (API, "api_cache", "canonical_path"),
        (ING, "recipe_ingredient", "canonical_path"),
        (CONSENSUS, "consensus", "canonical_path"),
    ]:
        if not src_path.exists():
            print(f"  missing {src_path}", file=sys.stderr)
            continue
        with src_path.open() as f:
            for row in csv.DictReader(f):
                cp = (row.get(cp_field) or "").strip()
                if cp:
                    path_counts[cp][src_label] += 1
        n_total = sum(path_counts[p][src_label] for p in path_counts)
        print(f"  {src_label}: {n_total:,} rows", file=sys.stderr)

    # Group paths by normalized form
    grouped: defaultdict[str, list[str]] = defaultdict(list)
    for path in path_counts.keys():
        key = normalize_path(path)
        grouped[key].append(path)

    # Filter to groups with multiple distinct paths = DUPLICATES
    duplicate_groups = {k: v for k, v in grouped.items() if len(v) >= 2}
    print(f"\nfound {len(duplicate_groups):,} duplicate path groups", file=sys.stderr)

    # Output as CSV
    rows = []
    for key, paths in duplicate_groups.items():
        # Compute total-uses per path and pick the most-used as canonical
        path_total: dict[str, int] = {}
        for p in paths:
            path_total[p] = sum(path_counts[p].values())
        sorted_paths = sorted(paths, key=lambda p: -path_total[p])
        canonical = sorted_paths[0]
        for p in sorted_paths:
            rows.append({
                "canonical_path": p,
                "normalized_key": key,
                "is_canonical": "yes" if p == canonical else "",
                "canonical_path_chosen": canonical,
                "n_products":      path_counts[p].get("priced_products", 0),
                "n_api_rows":      path_counts[p].get("api_cache", 0),
                "n_recipe_rows":   path_counts[p].get("recipe_ingredient", 0),
                "n_consensus_rows":path_counts[p].get("consensus", 0),
                "total_uses":      path_total[p],
            })

    rows.sort(key=lambda r: (r["normalized_key"], -r["total_uses"]))

    with OUT.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=[
            "canonical_path", "normalized_key", "is_canonical",
            "canonical_path_chosen",
            "n_products", "n_api_rows", "n_recipe_rows",
            "n_consensus_rows", "total_uses",
        ])
        w.writeheader()
        w.writerows(rows)

    print(f"\nTop 25 duplicate groups by total impact:", file=sys.stderr)
    sorted_groups = sorted(
        duplicate_groups.items(),
        key=lambda kv: -sum(sum(path_counts[p].values()) for p in kv[1]),
    )
    for key, paths in sorted_groups[:25]:
        sorted_paths = sorted(paths, key=lambda p: -sum(path_counts[p].values()))
        print(f"\n  group [{key}]:", file=sys.stderr)
        for p in sorted_paths:
            tot = sum(path_counts[p].values())
            print(f"    [{tot:>5}] {p}", file=sys.stderr)
    print(f"\n  → {OUT}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
