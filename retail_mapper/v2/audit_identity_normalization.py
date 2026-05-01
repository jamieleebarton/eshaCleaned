#!/usr/bin/env python3
"""Audit every identity in full_corpus_cleaned.csv against family-canonical
expectations. Classifies each identity that contains a "family word" (bread,
cake, sauce, cookies, candy, cheese, pasta, soup, milk, yogurt, etc.) as one of:

  canonical          — already in canonical form (keep as-is)
  short_to_full      — short form, should rename to full ('Rye' → 'Rye Bread')
  compound_to_split  — compound, should split base + leftover ('Caraway Rye' →
                       'Rye Bread' + leftover ['caraway'])
  distinct_product   — own identity, contains family word incidentally
                       ('Bread Crumbs', 'Pasta Sauce', 'Cream Cheese')
  multi_product      — composite ('Cookies and Frosting Pack')
  unknown            — needs human review

Writes identity_normalization_report.csv with the proposed classification +
canonical mapping for every identity in scope.

Read-only on the corpus. Safe to run anytime.
"""
from __future__ import annotations

import csv
import re
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
V2 = REPO / "retail_mapper" / "v2"
SRC = V2 / "full_corpus_cleaned.csv"
OUT = V2 / "identity_normalization_report.csv"

csv.field_size_limit(sys.maxsize)


# ---------------- Family configurations ----------------
# Each family has:
#   canonical: identities that stay as-is
#   distinct:  identities that contain the family word but are their own
#              product (e.g. 'Bread Crumbs' is not 'Bread')
#   patterns:  list of (lowercase pattern, full canonical name) — matches
#              compound identities and renames them. Most-specific first.

FAMILIES: dict[str, dict] = {
    "bread": {
        "canonical": {
            "Bread", "Rye Bread", "Sourdough Bread", "Wheat Bread",
            "Whole Wheat Bread", "Multigrain Bread", "Pumpernickel Bread",
            "French Bread", "Italian Bread", "Brown Bread", "White Bread",
            "Banana Bread", "Pumpkin Bread", "Zucchini Bread", "Cranberry Bread",
            "Lemon Bread", "Date Bread", "Nut Bread", "Cinnamon Swirl Bread",
            "Cinnamon Raisin Bread", "Raisin Bread", "Hawaiian Sweet Bread",
            "Portuguese Sweet Bread", "Garlic Bread", "Cheese Bread",
            "Texas Toast", "Soda Bread", "Irish Soda Bread", "Cornbread",
            "Anadama Bread", "Monkey Bread",
        },
        "distinct": {
            "Bread Crumbs", "Bread Mix", "Bread Sticks", "Bread Bowls",
            "Pita Bread", "Bread Dough", "Garlic Bread Loaf",
            "French Bread Pizza", "Bread Pudding",
        },
        "patterns": [
            ("whole wheat", "Whole Wheat Bread"),
            ("multigrain",  "Multigrain Bread"),
            ("multi grain", "Multigrain Bread"),
            ("pumpernickel","Pumpernickel Bread"),
            ("sourdough",   "Sourdough Bread"),
            ("rye",         "Rye Bread"),
            ("french bread","French Bread"),
            ("italian bread","Italian Bread"),
        ],
    },
    "cake": {
        "canonical": {
            "Cake", "Cheesecake", "Cupcakes", "Pound Cake", "Bundt Cake",
            "Layer Cake", "Coffee Cake", "Carrot Cake", "Birthday Cake",
            "Angel Food Cake", "Sponge Cake", "Upside Down Cake",
            "Snack Cakes", "Tea Cakes", "Mug Cake", "Cake Roll",
        },
        "distinct": {
            "Cake Mix", "Cake Decorations", "Cake Flour", "Cake Cups",
            "Cake Topper", "Cake Drip", "Cake Donut Mix", "Cake Decorating Kit",
            "Cake Bars", "Crab Cake Mix", "Coffee Cake Mix", "Fish Cake",
            "Crab Cakes", "Rice Cakes", "Beef Cakes", "Salmon Cakes",
        },
        "patterns": [],   # most cake variants are already in canonical
    },
    "sauce": {
        "canonical": {
            "Sauce", "Pasta Sauce", "Hot Sauce", "Soy Sauce", "Barbecue Sauce",
            "Pizza Sauce", "Tomato Sauce", "Marinara Sauce", "Alfredo Sauce",
            "Cheese Sauce", "Tartar Sauce", "Cocktail Sauce",
            "Worcestershire Sauce", "Steak Sauce", "Teriyaki Sauce",
            "Enchilada Sauce", "Cranberry Sauce", "Chili Sauce", "Taco Sauce",
            "Curry Sauce", "Spaghetti Sauce", "Chipotle Sauce", "Buffalo Sauce",
            "Stir Fry Sauce", "Hoisin Sauce", "Fish Sauce", "Ponzu Sauce",
            "Chimichurri Sauce", "Mole Sauce", "Cooking Sauce", "Simmer Sauce",
        },
        "distinct": {"Sauce Mix", "Sauce Packet"},
        "patterns": [],   # sauces are mostly distinct products
    },
    "cookies": {
        "canonical": {
            "Cookies", "Cookie Bars", "Sandwich Cookies",
            "Macarons", "Biscotti", "Shortbread", "Wafers",
        },
        "distinct": {"Cookie Mix", "Cookie Dough", "Cookie Butter", "Cookie Cutter"},
        "patterns": [
            ("cookie", "Cookies"),  # Cookie → Cookies (plural)
        ],
    },
    "candy": {
        "canonical": {
            "Candy", "Hard Candy", "Gummy Candy", "Chocolate Candy",
            "Sour Candy", "Cotton Candy", "Caramel Candy", "Bubble Gum",
            "Candy Cane", "Candy Bar", "Candy Corn", "Fruit Candy",
            "Chewy Candy", "Soft Candy", "Ginger Candy", "Mexican Candy",
        },
        "distinct": {"Candy Coating", "Candy Melts", "Candy Decorations",
                     "Candy Apple", "Candy Straws", "Candy Wafers",
                     "Candy Decorating Kit", "Candy Coated Peanuts"},
        "patterns": [],
    },
    "cheese": {
        "canonical": {
            "Cheese", "Cream Cheese", "Cottage Cheese", "String Cheese",
            "Mac and Cheese", "Cheese Crisps", "Cheese Puffs", "Cheese Curls",
            "Cheese Spread", "Cheese Sauce", "Cheese Bread", "Cheese Crackers",
            "Cheese Curds", "Cheese Snacks", "Cheese Balls", "Cheese Sticks",
            "Cheese and Crackers Pack",
        },
        "distinct": {"Cheese Powder", "Cheese Whip", "Cheese Singles",
                     "Goat Cheese", "Blue Cheese", "Swiss Cheese",
                     "Cheddar Cheese", "Parmesan Cheese", "Mozzarella Cheese",
                     "Feta Cheese", "Ricotta Cheese", "Provolone Cheese",
                     "Gouda Cheese", "Brie Cheese", "Pepper Jack Cheese",
                     "Monterey Jack Cheese", "American Cheese"},
        "patterns": [],
    },
    "pasta": {
        "canonical": {
            "Pasta", "Spaghetti", "Macaroni", "Penne", "Rotini", "Ravioli",
            "Tortellini", "Gnocchi", "Lasagna", "Fettuccine", "Linguine",
            "Rigatoni", "Manicotti", "Stuffed Shells", "Angel Hair Pasta",
            "Pasta Sauce", "Pasta Salad", "Pasta Mix", "Pasta Dishes",
        },
        "distinct": {"Pasta Sauce Mix", "Pasta Salad Mix", "Pasta Dinner",
                     "Pasta Dinner Mix", "Pasta Side Dish", "Filled Pasta",
                     "Pasta Shells", "Beef Pasta", "Chicken Pasta",
                     "Canned Pasta", "Rice and Pasta Blend"},
        "patterns": [],
    },
    "soup": {
        "canonical": {
            "Soup", "Bisque", "Chowder", "Menudo", "Gazpacho", "Minestrone",
            "Pho", "Ramen", "Wonton Soup", "Chicken Noodle Soup",
            "Chicken Soup", "Tomato Soup", "Broccoli Cheddar Soup",
            "Cream of Mushroom Soup", "Minestrone Soup", "Split Pea Soup",
            "Miso Soup", "Vegetable Soup", "Tomato Basil Soup",
            "Egg Drop Soup", "Hot and Sour Soup", "Matzo Ball Soup",
            "French Onion Soup", "Posole", "Borscht", "Tom Yum",
            "Tom Kha", "Ramen Noodle Soup", "Chicken Tortilla Soup",
            "Chicken Rice Soup",
        },
        "distinct": {"Soup Mix", "Onion Soup Mix", "Soup Starter",
                     "Bone Broth Soup", "Soup Bowl"},
        "patterns": [],
    },
    "milk": {
        "canonical": {
            "Milk", "Almond Milk", "Oat Milk", "Coconut Milk", "Soy Milk",
            "Rice Milk", "Cashew Milk", "Hemp Milk", "Hazelnut Milk",
            "Macadamia Milk", "Banana Milk", "Sesame Milk", "Flax Milk",
            "Plant Milk", "Chocolate Milk", "Strawberry Milk", "Vanilla Milk",
            "Goat Milk", "Buttermilk", "Flavored Milk",
            "Sweetened Condensed Milk", "Evaporated Milk", "Condensed Milk",
            "Nonfat Dry Milk", "Whole Milk", "Skim Milk",
        },
        "distinct": {"Chocolate Milk Mix", "Milk Powder", "Milk Bar",
                     "Malted Milk Balls", "Milk Substitute"},
        "patterns": [],
    },
    "yogurt": {
        "canonical": {
            "Yogurt", "Greek Yogurt", "Plant Yogurt", "Kefir", "Frozen Yogurt",
            "Drinkable Yogurt", "Yogurt Drink", "Yogurt Smoothie",
        },
        "distinct": {"Yogurt Bars", "Frozen Yogurt Bars", "Yogurt Raisins",
                     "Yogurt Covered Raisins", "Yogurt Bites",
                     "Yogurt Coated Raisins", "Yogurt Starter",
                     "Yogurt Spread", "Yogurt Cranberries", "Yogurt Shake",
                     "Frozen Yogurt Sandwiches"},
        "patterns": [],
    },
    "brownie": {
        "canonical": {"Brownies", "Brownie Bites", "Brownie Brittle"},
        "distinct": {"Brownie Mix"},
        "patterns": [
            ("brownie", "Brownies"),  # singular → plural
        ],
    },
    "muffin": {
        "canonical": {"Muffins", "English Muffins", "Mini Muffins"},
        "distinct": {"Muffin Mix", "Muffin Tops", "Muffin Pan",
                     "English Muffin Bread", "Mini Muffin Mix"},
        "patterns": [
            ("muffin", "Muffins"),
        ],
    },
    "donut": {
        "canonical": {"Doughnuts", "Donut Holes", "Mini Donuts"},
        "distinct": {"Doughnut Mix", "Donut Mix"},
        "patterns": [
            ("donut",    "Doughnuts"),
            ("doughnut", "Doughnuts"),
        ],
    },
}


def classify_identity(identity: str, family_word: str, fam: dict) -> dict:
    """Return classification dict for a single (identity, family) pair."""
    proposed_canonical = ""
    proposed_modifier_tokens: list[str] = []
    classification = "unknown"

    if identity in fam["canonical"]:
        classification = "canonical"
    elif identity in fam["distinct"]:
        classification = "distinct_product"
    else:
        # Try patterns
        id_l = identity.lower()
        for pat, full in fam["patterns"]:
            if pat in id_l:
                if full == identity:
                    classification = "canonical"
                    break
                # Check if it's just a short→full or compound
                leftover = id_l.replace(pat, " ").strip()
                leftover_tokens = [w for w in re.split(r"\s+", leftover)
                                   if w and w != family_word]
                if not leftover_tokens:
                    classification = "short_to_full"
                else:
                    classification = "compound_to_split"
                proposed_canonical = full
                proposed_modifier_tokens = leftover_tokens
                break
        else:
            # Identity contains family word but no pattern matched
            # Check if it has multiple distinct product words ("Cookies and Frosting Pack")
            if " and " in id_l or " & " in id_l or " with " in id_l:
                classification = "multi_product"
            else:
                classification = "unknown"

    return {
        "classification": classification,
        "proposed_canonical": proposed_canonical,
        "proposed_modifier_tokens": " | ".join(proposed_modifier_tokens),
    }


def main() -> None:
    print(f"  reading {SRC.name}")
    id_count: Counter = Counter()
    with SRC.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            pid = (r.get("product_identity_fixed") or "").strip()
            if pid:
                id_count[pid] += 1
    print(f"  found {len(id_count):,} distinct identities")

    rows: list[dict] = []
    summary: dict[str, Counter] = {fam: Counter() for fam in FAMILIES}

    for identity, n in id_count.items():
        words = re.split(r"[\s\-]+", identity.lower())
        for fam_word, fam in FAMILIES.items():
            if fam_word in words:
                cls = classify_identity(identity, fam_word, fam)
                rows.append({
                    "identity": identity,
                    "n_rows": n,
                    "family_word": fam_word,
                    **cls,
                })
                summary[fam_word][cls["classification"]] += 1
                break  # match first family

    rows.sort(key=lambda r: (r["family_word"], r["classification"], -r["n_rows"]))

    cols = ["identity", "n_rows", "family_word", "classification",
            "proposed_canonical", "proposed_modifier_tokens"]
    with OUT.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print(f"  wrote {OUT.name} ({len(rows):,} (identity, family) pairs)")

    print()
    print("Summary by family:")
    print(f"  {'family':12s}  {'canonical':>10s}  {'distinct':>9s}  "
          f"{'short->full':>12s}  {'compound':>10s}  {'multi':>6s}  {'unknown':>8s}")
    for fam_word, c in summary.items():
        print(f"  {fam_word:12s}  "
              f"{c['canonical']:>10d}  {c['distinct_product']:>9d}  "
              f"{c['short_to_full']:>12d}  {c['compound_to_split']:>10d}  "
              f"{c['multi_product']:>6d}  {c['unknown']:>8d}")


if __name__ == "__main__":
    main()
