#!/usr/bin/env python3
"""Find SKUs at single-spice / single-fruit / single-vegetable / single-cheese
leaves whose name doesn't even mention the leaf food.

Examples we already saw:
  Cinnamon path → Bearded Butchers Maple Bacon DIY Kit
  Oregano path  → Great Value Italian-Style Diced Tomatoes
  Ginger path   → McCormick Sesame and Ginger Crunch with Garlic All Purpose

Generalize: at SINGLE_FOOD leaves, every SKU's name must contain the
leaf food token (or known synonym). Otherwise flag for reclassification.
"""
from __future__ import annotations
import csv, sqlite3
from pathlib import Path

ROOT = Path("/Users/jamiebarton/Desktop/esha_audit_bundle")
DB   = ROOT / "recipe_pricing" / "data" / "priced_products_v2.db"
OUT  = ROOT / "recipe_pricing" / "path_name_mismatch_audit.csv"

# Single-food leaves. The leaf token (or a synonym) MUST appear in the SKU name.
SINGLE_FOOD_LEAVES: dict[str, list[str]] = {
    # Spices
    "Pantry > Spices & Seasonings > Oregano":   ["oregano"],
    "Pantry > Spices & Seasonings > Basil":     ["basil"],
    "Pantry > Spices & Seasonings > Cumin":     ["cumin"],
    "Pantry > Spices & Seasonings > Sage":      ["sage"],
    "Pantry > Spices & Seasonings > Thyme":     ["thyme"],
    "Pantry > Spices & Seasonings > Paprika":   ["paprika"],
    "Pantry > Spices & Seasonings > Turmeric":  ["turmeric"],
    "Pantry > Spices & Seasonings > Rosemary":  ["rosemary"],
    "Pantry > Spices & Seasonings > Nutmeg":    ["nutmeg"],
    "Pantry > Spices & Seasonings > Cloves":    ["clove"],
    "Pantry > Spices & Seasonings > Cinnamon":  ["cinnamon"],
    "Pantry > Spices & Seasonings > Ginger":    ["ginger"],
    "Pantry > Spices & Seasonings > Cardamom":  ["cardamom"],
    "Pantry > Spices & Seasonings > Allspice":  ["allspice"],
    "Pantry > Spices & Seasonings > Bay Leaves":["bay leaf","bay leaves"],
    "Pantry > Spices & Seasonings > Tarragon":  ["tarragon"],
    "Pantry > Spices & Seasonings > Dill Weed": ["dill"],
    "Pantry > Spices & Seasonings > Saffron":   ["saffron"],
    "Pantry > Spices & Seasonings > Caraway":   ["caraway"],
    "Pantry > Spices & Seasonings > Anise":     ["anise"],
    # Fruits (single)
    "Produce > Fruit > Strawberries":   ["strawberr"],
    "Produce > Fruit > Blueberries":    ["blueberr"],
    "Produce > Fruit > Raspberries":    ["raspberr"],
    "Produce > Fruit > Blackberries":   ["blackberr"],
    "Produce > Fruit > Cranberries":    ["cranberr"],
    "Produce > Fruit > Pineapple":      ["pineapple"],
    "Produce > Fruit > Mangoes":        ["mango"],
    "Produce > Fruit > Peaches":        ["peach"],
    "Produce > Fruit > Pears":          ["pear"],
    "Produce > Fruit > Apples":         ["apple"],
    "Produce > Fruit > Bananas":        ["banana"],
    "Produce > Fruit > Watermelon":     ["watermelon"],
    "Produce > Fruit > Cantaloupe":     ["cantaloupe","melon"],
    # Vegetables (single)
    "Produce > Vegetables > Broccoli":  ["broccoli"],
    "Produce > Vegetables > Cauliflower":["cauliflower"],
    "Produce > Vegetables > Spinach":   ["spinach"],
    "Produce > Vegetables > Kale":      ["kale"],
    "Produce > Vegetables > Garlic":    ["garlic"],
    "Produce > Vegetables > Onions":    ["onion"],
    "Produce > Vegetables > Carrots":   ["carrot"],
    "Produce > Vegetables > Celery":    ["celery"],
    "Produce > Vegetables > Tomatoes":  ["tomato"],
    "Produce > Vegetables > Cucumbers": ["cucumber"],
    "Produce > Vegetables > Potatoes":  ["potato"],
    "Produce > Vegetables > Bell Peppers":["bell pepper","sweet pepper"],
    "Produce > Vegetables > Mushrooms": ["mushroom"],
}


def main():
    con = sqlite3.connect(str(DB))
    cur = con.cursor()
    bugs = []
    for path, tokens in SINGLE_FOOD_LEAVES.items():
        cur.execute("""SELECT DISTINCT upc, name, grams, cents
            FROM priced_products WHERE consensus_canonical = ? AND available=1""",
            (path,))
        for upc, name, g, c in cur.fetchall():
            nl = (name or "").lower()
            if not any(t in nl for t in tokens):
                bugs.append({
                    "upc": upc, "path": path,
                    "expected_tokens": "|".join(tokens),
                    "name": name[:90],
                    "grams": round(g, 1) if g else 0,
                    "cents": c or 0,
                })

    print(f"path-name mismatches: {len(bugs)} distinct UPCs across {len(SINGLE_FOOD_LEAVES)} leaves")
    by_path = {}
    for b in bugs: by_path.setdefault(b["path"], []).append(b)
    for path in sorted(by_path, key=lambda p: -len(by_path[p])):
        print(f"\n  {len(by_path[path])} at: {path}")
        for b in by_path[path][:5]:
            print(f"    upc={b['upc']}  ${b['cents']/100:.2f}  {b['name'][:65]}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(bugs[0].keys()) if bugs else
                                            ["upc","path","expected_tokens","name","grams","cents"])
        w.writeheader()
        for b in bugs: w.writerow(b)
    print(f"\n→ {OUT}")


if __name__ == "__main__":
    main()
