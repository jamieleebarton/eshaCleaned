#!/usr/bin/env python3
"""Audit canonical_paths whose terminal segment is a known FORM or CLAIM
facet. Per HTC_SPEC, those should live at htc_form (positions 5-7) or in
claims_hex — not as canonical_path leaves. Each such path fragments what
should be one bucket.

Examples:
  Pantry > Canned Vegetables > Green Chiles > Diced
  Pantry > Canned Vegetables > Green Chiles > Chopped
  Pantry > Canned Vegetables > Green Chiles > Mild
should all collapse to: Pantry > Canned Vegetables > Green Chiles

Outputs CSV ranked by SKU count. Surfaces collapse candidates.
"""
from __future__ import annotations
import csv, sqlite3, sys
from collections import defaultdict
from pathlib import Path

ROOT = Path("/Users/jamiebarton/Desktop/esha_audit_bundle")
DB   = ROOT / "recipe_pricing" / "data" / "priced_products_v2.db"
OUT  = ROOT / "recipe_pricing" / "path_facet_leaves_audit.csv"

# Form/processing/preparation facets that should NOT be canonical_path leaves.
FORM_FACETS = {
    "diced", "chopped", "sliced", "minced", "crushed", "shredded",
    "grated", "pureed", "smashed", "mashed", "halved", "quartered",
    "wedges", "rings", "stripped", "stripped",
    "whole", "halves", "halved", "small", "medium", "large", "jumbo",
    "fresh", "frozen", "canned", "dried", "smoked", "cured",
    "pickled", "brined", "marinated", "roasted", "steamed", "raw",
    "freeze dried", "freeze-dried", "fire roasted", "fire-roasted",
    "ground", "uncrushed",
}
# Claim facets — heat level, sourcing, regional, etc.
CLAIM_FACETS = {
    "hot", "mild", "medium", "spicy", "extra hot",
    "organic", "non-gmo", "non gmo", "natural", "premium",
    "low fat", "fat free", "lowfat", "non-fat", "nonfat",
    "low sodium", "no salt added", "reduced sodium",
    "sweetened", "unsweetened",
    "hatch", "new mexico", "anaheim", "poblano",
    "kosher", "halal",
    "with bacon", "with cheese", "with garlic", "with herbs",
    "with onions", "with peppers", "with tomatoes",
    "extra virgin", "virgin",
    "salted", "unsalted",
    "boneless", "bone-in", "bone in", "skinless",
    "lean", "extra lean",
    "regular", "plain", "original", "classic",
}
ALL_FACETS = FORM_FACETS | CLAIM_FACETS


def is_facet_leaf(path: str) -> tuple[bool, str]:
    """Return (is_facet, leaf) — leaf is the terminal segment."""
    parts = [p.strip() for p in path.split(" > ") if p.strip()]
    if len(parts) < 3: return False, ""
    leaf = parts[-1].lower().strip()
    if leaf in ALL_FACETS:
        return True, parts[-1]
    return False, ""


def main():
    con = sqlite3.connect(str(DB))
    cur = con.cursor()
    cur.execute("""SELECT consensus_canonical, COUNT(DISTINCT upc), COUNT(*)
        FROM priced_products WHERE available=1
          AND consensus_canonical IS NOT NULL AND consensus_canonical != ''
        GROUP BY consensus_canonical""")
    paths = cur.fetchall()
    print(f"scanning {len(paths):,} distinct canonical_paths…", file=sys.stderr)

    facet_paths = []
    for cp, n_upc, n_rows in paths:
        is_facet, leaf = is_facet_leaf(cp)
        if not is_facet: continue
        # Compute proposed parent
        parts = cp.split(" > ")
        parent = " > ".join(parts[:-1])
        facet_paths.append({
            "canonical_path": cp,
            "facet_leaf": leaf,
            "proposed_parent": parent,
            "n_distinct_upc": n_upc,
            "n_rows": n_rows,
        })
    facet_paths.sort(key=lambda r: -r["n_distinct_upc"])
    print(f"  facet-leaf paths: {len(facet_paths):,}", file=sys.stderr)
    print(f"  total UPCs in those paths: {sum(r['n_distinct_upc'] for r in facet_paths):,}",
          file=sys.stderr)
    print(f"  total rows in those paths: {sum(r['n_rows'] for r in facet_paths):,}",
          file=sys.stderr)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["canonical_path","facet_leaf",
            "proposed_parent","n_distinct_upc","n_rows"])
        w.writeheader()
        for r in facet_paths: w.writerow(r)
    print(f"  → {OUT}", file=sys.stderr)

    print(f"\n=== TOP 25 facet-leaf paths by SKU count ===")
    for r in facet_paths[:25]:
        print(f"  {r['n_distinct_upc']:>4} UPCs  {r['canonical_path'][:55]:<55}")
        print(f"             → collapse to: {r['proposed_parent'][:55]}")


if __name__ == "__main__":
    main()
