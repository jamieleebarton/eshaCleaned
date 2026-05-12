#!/usr/bin/env python3
"""Find duplicate parent/child canonical_paths in priced_products_v2.db.

Pattern: a parent path AND a child sub-leaf of the parent both have
products of the same identity. Examples:
  Frozen > Frozen Fruit > Strawberries          (some products)
  Frozen > Frozen Fruit > Strawberries > Plain  (other products — same thing)

These are NOT real distinctions — "Plain" doesn't change the identity.
The two paths should be merged into one (the parent).

Heuristic: when the child sub-leaf token is a MEANINGLESS MODIFIER, the
split is a false distinction. Otherwise (e.g. Greek under Yogurt, White
under Bread), the split is a real sub-type and keep distinct.

Output:
  recipe_pricing/duplicate_parent_child_paths.csv
    columns: parent_path, child_path, child_modifier, parent_n,
             child_n, total_products, dominant_path, action
    where action = 'merge_to_parent' | 'merge_to_child' | 'keep_distinct'
"""
from __future__ import annotations

import csv
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "recipe_pricing" / "data" / "priced_products_v2.db"
OUT = ROOT / "recipe_pricing" / "duplicate_parent_child_paths.csv"


# Sub-leaf tokens that don't add identity — when these appear as a child
# under a parent path that ALSO has products, it's a false distinction.
MEANINGLESS_MODIFIERS = {
    "plain", "original", "whole", "regular", "standard", "basic", "classic",
    "simple", "natural", "traditional", "everyday", "all natural",
    "100 percent", "fresh", "raw", "uncooked", "untreated",
    "default", "ordinary", "normal", "generic", "unbranded",
}

# Sub-leaf tokens that MEAN a real distinction (don't merge)
IDENTITY_MODIFIERS = {
    "greek", "white", "brown", "yellow", "red", "green", "black",
    "whole wheat", "whole grain", "whole milk", "skim", "organic",
    "smoked", "roasted", "spicy", "hot", "mild", "sweet", "sour",
    "extra virgin", "virgin", "light", "dark",
    "cheddar", "mozzarella", "parmesan", "feta", "ricotta",
    "italian", "french", "thai", "mexican", "japanese", "chinese",
    "fresh", "frozen", "canned", "dried", "pickled",
}


def main() -> int:
    if not DB.exists():
        raise SystemExit(f"missing {DB}")
    con = sqlite3.connect(str(DB))
    cur = con.cursor()
    cur.execute("""
        SELECT consensus_canonical, COUNT(*)
        FROM priced_products
        WHERE consensus_canonical != '' AND available = 1
          AND grams > 0 AND cents > 0
        GROUP BY consensus_canonical
    """)
    path_counts = dict(cur.fetchall())

    # For each path, see if it's a sub-leaf of another (parent) path that
    # also exists. e.g. "A > B > C > D" is sub-leaf of "A > B > C".
    pairs: list[dict] = []
    for child_path, child_n in path_counts.items():
        if " > " not in child_path:
            continue
        parent_path = " > ".join(child_path.split(" > ")[:-1])
        if parent_path not in path_counts:
            continue
        modifier = child_path.split(" > ")[-1].lower()
        parent_n = path_counts[parent_path]
        # Decide action: meaningless modifier → merge to parent
        if modifier in MEANINGLESS_MODIFIERS:
            action = "merge_to_parent"
        elif modifier in IDENTITY_MODIFIERS:
            action = "keep_distinct"
        else:
            # Default: review needed (don't auto-merge ambiguous)
            action = "review"
        pairs.append({
            "parent_path": parent_path,
            "child_path": child_path,
            "child_modifier": modifier,
            "parent_n": parent_n,
            "child_n": child_n,
            "total_products": parent_n + child_n,
            "action": action,
        })

    # Sort by total products descending
    pairs.sort(key=lambda r: -r["total_products"])

    with OUT.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=[
            "parent_path", "child_path", "child_modifier",
            "parent_n", "child_n", "total_products", "action",
        ])
        w.writeheader()
        w.writerows(pairs)

    n_merge = sum(1 for r in pairs if r["action"] == "merge_to_parent")
    n_keep = sum(1 for r in pairs if r["action"] == "keep_distinct")
    n_review = sum(1 for r in pairs if r["action"] == "review")
    n_merge_products = sum(r["child_n"] for r in pairs if r["action"] == "merge_to_parent")
    print(f"\nfound {len(pairs):,} parent/child pairs", file=sys.stderr)
    print(f"  auto merge_to_parent (meaningless modifier): {n_merge:,}  ({n_merge_products:,} products)", file=sys.stderr)
    print(f"  keep distinct (real identity modifier):      {n_keep:,}", file=sys.stderr)
    print(f"  review needed (unknown modifier):            {n_review:,}", file=sys.stderr)
    print(f"\nTop 20 mergers by product impact:", file=sys.stderr)
    for r in [p for p in pairs if p["action"] == "merge_to_parent"][:20]:
        print(f"  [{r['child_n']:>4}+{r['parent_n']:>4}] {r['child_path'][:65]}", file=sys.stderr)
        print(f"          → {r['parent_path']}", file=sys.stderr)
    print(f"\nTop 15 review (unknown modifier):", file=sys.stderr)
    for r in [p for p in pairs if p["action"] == "review"][:15]:
        print(f"  [{r['child_n']:>4}+{r['parent_n']:>4}] modifier={r['child_modifier']!r}  {r['child_path'][:60]}", file=sys.stderr)
    print(f"\n  → {OUT}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
