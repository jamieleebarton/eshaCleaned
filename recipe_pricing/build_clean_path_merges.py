#!/usr/bin/env python3
"""Generate the canonical_path merges CSV cleanly.

Rules:
  1. The FDC `consensus_full_corpus_audit.csv` is the source of truth. We
     NEVER target a non-FDC path. Every merge target must already exist
     in the FDC tree.
  2. For each generic-class leaf (Cookies, Cereal, Yogurt, Mayonnaise,
     etc.), the FDC parent with the most rows is canonical. All OTHER
     FDC paths ending in the same leaf get merged into the canonical
     parent.
  3. Hand-curated extras (specific stray paths like "Dairy > Cheese >
     Butter") are appended only when they have an obvious target that
     ALREADY exists in FDC.

Output: recipe_pricing/walmart_kroger_path_rewrites.csv
"""
from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path

csv.field_size_limit(sys.maxsize)

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "retail_mapper" / "v2" / "consensus_full_corpus_audit.csv"
OUT = ROOT / "recipe_pricing" / "walmart_kroger_path_rewrites.csv"

# Class leaves to consolidate (the LAST segment of canonical_path).
# When a leaf appears under multiple parents, the FDC majority parent wins;
# the others merge into it.
CLASS_LEAVES = [
    "Cookies", "Cereal", "Yogurt", "Salad Dressing", "Mayonnaise",
    "Granola", "Protein Bars", "Granola Bars", "Hummus", "Salsa",
    "Crackers", "Vinaigrette", "Ranch Dressing", "Italian Dressing",
    "Trail Mix", "Mixed Nuts", "Pasta", "Soup", "Dip", "Spice Blend",
    "Bread", "Pizza", "Ice Cream", "Coffee", "Tea", "Milk",
    "Butter", "Margarine", "Sausage", "Bacon", "Ham", "Mustard",
    "Ketchup", "Pancake Mix", "Cake", "Brownie", "Pie", "Pretzels",
    "Almonds", "Peanuts", "Walnuts", "Cashews", "Pistachios", "Pecans",
    "Honey", "Syrup", "Jam", "Jelly", "Preserves", "Vinegar",
    "Olive Oil", "Coconut Oil", "Vegetable Oil", "Salt", "Pepper",
    "Cinnamon", "Vanilla Extract", "Almond Extract", "Lemon Juice",
    "Lime Juice", "Apple Juice", "Orange Juice", "Smoothie", "Juice",
    "Wine", "Beer", "Vodka", "Whiskey", "Rum", "Gin", "Liqueur",
    "Tortilla Chips", "Potato Chips", "Pita Chips", "Popcorn",
    "Chocolate Candy", "Hard Candy", "Gummy Candy", "Marshmallows",
    "Frosting", "Pancake Syrup", "Maple Syrup", "Cream Cheese",
    "Sour Cream", "BBQ Sauce", "Hot Sauce", "Soy Sauce",
    "Worcestershire Sauce", "Pasta Sauce", "Marinara Sauce",
    "Tomato Sauce", "Alfredo Sauce", "Pesto", "Pickles", "Relish",
    "Olives", "Capers", "Anchovies",
]

# Hand-curated extras: stray FDC paths that map to clear targets.
# Each (old_path, new_path) — both must exist in FDC.
HAND_MERGES = [
    ("Dairy > Cheese > Butter", "Dairy > Butter"),
    ("Dairy > Cheese > Yogurt", "Dairy > Yogurt"),
    ("Dairy > Cheese > Pizza", "Meal > Pizza"),
    ("Snack > Trail Mix > Cookies", "Bakery > Cookies"),
    ("Snack > Chocolate Candy > Cookies", "Bakery > Cookies"),
    ("Snack > Crackers > Cookies", "Bakery > Cookies"),
    ("Pantry > Pasta > Bread", "Bakery > Bread"),
    ("Beverage > Protein Drinks > Cereal", "Pantry > Cereal"),
    ("Snack > Jerky > Cereal", "Pantry > Cereal"),
    ("Beverage > Flavored Drinks > Coffee", "Beverage > Coffee"),
    ("Pantry > Plant Based Cheese > Salad Dressing",
     "Pantry > Salad Dressings > Salad Dressing"),
    ("Pantry > Plant Based Cheese > Mayonnaise",
     "Pantry > Sauces & Salsas > Mayonnaise"),
    ("Pantry > Plant Based Cheese > Hummus",
     "Pantry > Dips & Spreads > Hummus"),
    ("Pantry > Plant Based Cheese > Vinaigrette",
     "Pantry > Salad Dressings > Vinaigrette"),
    ("Pantry > Plant Based Cheese > Ranch Dressing",
     "Pantry > Salad Dressings > Ranch Dressing"),
    ("Pantry > Plant Based Cheese > Italian Dressing",
     "Pantry > Salad Dressings > Italian Dressing"),
    ("Pantry > Plant Based Cheese > Caesar Dressing",
     "Pantry > Salad Dressings > Caesar Dressing"),
    ("Pantry > Plant Based Cheese > Blue Cheese Dressing",
     "Pantry > Salad Dressings > Blue Cheese Dressing"),
    ("Pantry > Frosting > Cake", "Pantry > Frosting"),
    ("Bakery > Pastries > Funnel Cake", "Bakery > Cake"),
    ("Frozen > Ice Cream Sandwiches > Ice Cream Sandwich",
     "Frozen > Ice Cream"),
    ("Beverage > Other Beverages > Ice Cream Soda",
     "Beverage > Carbonated > Soda"),
    ("Pantry > Spices & Seasonings > Seasoning Mix",
     "Pantry > Spices & Seasonings > Seasoning"),
    ("Pantry > Spices & Seasonings > Mints",
     "Pantry > Spices & Seasonings > Herbs"),
    ("Produce > Herbs", "Pantry > Spices & Seasonings > Herbs"),
    ("Pantry > Dips & Spreads > Dip Mix", "Pantry > Dips & Spreads > Dip"),
    ("Pantry > Pasta & Grains > Pasta & Grains", "Pantry > Pasta"),
]


def main() -> int:
    # Load FDC universe
    paths = defaultdict(int)
    with AUDIT.open() as f:
        for row in csv.DictReader(f):
            cp = (row.get("canonical_path") or "").strip()
            if cp:
                paths[cp] += 1

    universe = set(paths.keys())
    print(f"FDC universe: {len(universe):,} canonical_paths", file=sys.stderr)

    # Group by trailing leaf
    by_leaf = defaultdict(list)
    for cp, cnt in paths.items():
        leaf = cp.split(" > ")[-1].strip()
        by_leaf[leaf].append((cp, cnt))

    rules: list[tuple[str, str, str]] = []
    seen_olds: set[str] = set()

    # Auto: pick FDC majority parent per class leaf, merge others to it
    for leaf in CLASS_LEAVES:
        candidates = by_leaf.get(leaf, [])
        if len(candidates) < 2:
            continue
        candidates.sort(key=lambda c: -c[1])
        canonical = candidates[0][0]
        for path, cnt in candidates[1:]:
            if cnt < 3 or path == canonical:
                continue
            if path in seen_olds:
                continue
            rules.append((path, canonical, f"merge into FDC majority for '{leaf}' ({cnt} rows)"))
            seen_olds.add(path)

    # Hand-curated extras
    for old, new in HAND_MERGES:
        if old not in universe:
            print(f"  skip hand merge — '{old}' not in FDC universe", file=sys.stderr)
            continue
        if new not in universe:
            print(f"  skip hand merge — target '{new}' not in FDC universe", file=sys.stderr)
            continue
        if old in seen_olds:
            continue
        rules.append((old, new, "hand-curated stray path → FDC canonical"))
        seen_olds.add(old)

    # Validation pass: every target must be in FDC universe
    bad_targets = [(o, n) for o, n, _ in rules if n not in universe]
    if bad_targets:
        print("ERROR: rules with non-FDC targets:", file=sys.stderr)
        for o, n in bad_targets:
            print(f"  {o} -> {n}  (target NOT in FDC tree)", file=sys.stderr)
        return 2

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["old_canonical_path", "new_canonical_path", "note"])
        for old, new, note in rules:
            w.writerow([old, new, note])

    print(f"wrote {len(rules):,} merge rules -> {OUT}")
    print(f"  all targets verified to exist in FDC universe ({len(universe):,} paths)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
