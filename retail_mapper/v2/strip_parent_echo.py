#!/usr/bin/env python3
"""Strip parent-echo redundancy across the entire taxonomy.

When a 3rd-segment contains the parent's last word (e.g. parent='Chips' and
3rd='Potato Chips'), drop the redundant word so the segment becomes 'Potato'.
That makes 'Snack > Chips > Potato > X' reachable as one branch instead of
fragmenting across 'Snack > Chips > Potato Chips > X'.

Plural-aware: parent 'Chips' matches segments containing 'Chips' or 'Chip'.

Skip-list: parents and segments where the redundancy is part of the official
product name and stripping would cause confusion. (E.g. 'Chocolate Chip' under
'Snack > Cookies' — stripping 'Chip' would leave just 'Chocolate' but those
are different cookies. Same for 'Jelly Beans' under 'Snack > Candy', etc.)
"""
from __future__ import annotations

import csv
import re
import shutil
import sys
from collections import defaultdict
from pathlib import Path

V2 = Path("/Users/jamiebarton/Desktop/esha_audit_bundle/retail_mapper/v2")
AUDIT = V2 / "full_corpus_audit.csv"
LOG = V2 / "strip_parent_echo_log.csv"

csv.field_size_limit(sys.maxsize)

# Parents we'll process. Each entry: (parent_path, parent_words_to_strip).
# parent_words_to_strip is a set of words/phrases that, when found in a 3rd-segment,
# get stripped IF they appear at start or end of that segment.
ECHO_PARENTS: list[tuple[str, set[str]]] = [
    ("Snack > Chips",          {"Chips", "Chip"}),
    ("Snack > Bars",           {"Bars", "Bar"}),
    ("Snack > Jerky",          {"Jerky"}),
    ("Snack > Candy",          {"Candy", "Candies"}),
    ("Snack > Crackers",       {"Crackers", "Cracker"}),
    ("Snack > Cookies",        {"Cookies", "Cookie"}),
    ("Snack > Chocolate Candy", {"Candy", "Candies"}),
    ("Snack > Pretzels",       {"Pretzels", "Pretzel"}),
    ("Snack > Granola",        {"Granola"}),
    ("Snack > Trail Mix",      {"Trail Mix", "Mix"}),
    ("Snack > Nuts",           {"Nuts", "Nut"}),
    ("Snack > Cheese Crisps",  {"Cheese Crisps", "Cheese Crisp", "Crisps", "Crisp"}),
    ("Snack > Pork Rinds",     {"Pork Rinds", "Pork Rind", "Rinds", "Rind"}),
    ("Snack > Puffs",          {"Puffs", "Puff"}),
    ("Snack > Sticks",         {"Sticks", "Stick"}),
    ("Snack > Mixes",          {"Mix"}),
    ("Snack > Fruit Snacks",   {"Fruit Snacks", "Snacks", "Snack"}),
    ("Pantry > Soup",          {"Soup", "Soups"}),
    ("Pantry > Salad Dressings", {"Salad Dressings", "Salad Dressing", "Dressings", "Dressing"}),
    ("Pantry > Sauces & Salsas", {"Sauces", "Sauce"}),
    ("Pantry > Pasta",         {"Pasta"}),
    ("Pantry > Cereal",        {"Cereal", "Cereals"}),
    ("Pantry > Spices & Seasonings", {"Spices", "Seasonings", "Seasoning", "Spice"}),
    ("Pantry > Oil",           {"Oils", "Oil"}),
    ("Pantry > Vinegar",       {"Vinegars", "Vinegar"}),
    ("Pantry > Olives",        {"Olives", "Olive"}),
    ("Pantry > Pickles",       {"Pickles", "Pickle"}),
    ("Pantry > Dried Fruit",   {"Dried Fruit"}),
    ("Pantry > Sweeteners",    {"Sweeteners", "Sweetener"}),
    ("Pantry > Mixes",         {"Mix"}),
    ("Pantry > Baking Mixes",  {"Baking Mixes", "Mix"}),
    ("Pantry > Spreads",       {"Spreads", "Spread"}),
    ("Pantry > Dips & Spreads", {"Dips", "Dip", "Spreads", "Spread"}),
    ("Pantry > Mushrooms",     {"Mushrooms", "Mushroom"}),
    ("Pantry > Canned Vegetables", {"Vegetables", "Vegetable"}),
    ("Pantry > Canned Fruit",  {"Fruit", "Fruits"}),
    ("Pantry > Canned Seafood", {"Seafood"}),
    ("Pantry > Canned Meat",   {"Meat", "Meats"}),
    ("Pantry > Nut Butters",   set()),  # Already handled — don't re-strip
    ("Pantry > Protein Powders", {"Protein Powders", "Powders", "Powder"}),
    ("Pantry > Rice",          {"Rice"}),
    ("Pantry > Grain",         {"Grains", "Grain"}),
    ("Beverage > Juice",       {"Juice", "Juices"}),
    ("Beverage > Tea",         {"Tea", "Teas"}),
    ("Beverage > Coffee",      {"Coffee"}),
    ("Beverage > Soda",        {"Soda", "Sodas"}),
    ("Beverage > Carbonated",  {"Carbonated"}),
    ("Beverage > Sparkling Water", {"Sparkling Water", "Water"}),
    ("Beverage > Lemonade",    {"Lemonade"}),
    ("Beverage > Energy Drinks", {"Energy Drinks", "Drinks", "Drink"}),
    ("Beverage > Sports Drinks", {"Sports Drinks", "Drinks", "Drink"}),
    ("Beverage > Protein Drinks", {"Protein Drinks", "Drinks", "Drink"}),
    ("Beverage > Smoothies",   {"Smoothies", "Smoothie"}),
    ("Beverage > Plant Milk",  {"Milk"}),
    ("Beverage > Fruit Drinks", {"Fruit Drinks", "Drinks", "Drink"}),
    ("Beverage > Mixes",       {"Mixes", "Mix"}),
    ("Beverage > Wellness Shots", {"Wellness Shots", "Shots", "Shot"}),
    ("Beverage > Functional Drinks", {"Functional Drinks", "Drinks", "Drink"}),
    ("Beverage > Kombucha",    {"Kombucha"}),
    ("Beverage > Mixers",      {"Mixers", "Mixer"}),
    ("Dairy > Cheese",         {"Cheese", "Cheeses"}),
    ("Dairy > Yogurt",         {"Yogurt", "Yogurts"}),
    ("Dairy > Milk",           {"Milk"}),
    ("Dairy > Butter",         {"Butter"}),
    ("Dairy > Cream",          {"Cream"}),
    ("Dairy > Sour Cream",     {"Sour Cream"}),
    ("Dairy > Pudding",        {"Pudding", "Puddings"}),
    ("Dairy > Mousse",         {"Mousse"}),
    ("Dairy > Eggs",           {"Eggs", "Egg"}),
    ("Dairy > Flavored Milk",  {"Milk"}),
    ("Bakery > Bread",         {"Bread", "Breads"}),
    ("Bakery > Cake",          {"Cake", "Cakes"}),
    ("Bakery > Cupcakes",      {"Cupcakes", "Cupcake"}),
    ("Bakery > Cookies",       {"Cookies", "Cookie"}),
    ("Bakery > Muffins",       {"Muffins", "Muffin"}),
    ("Bakery > Doughnuts",     {"Doughnuts", "Doughnut", "Donuts", "Donut"}),
    ("Bakery > Bagels",        {"Bagels", "Bagel"}),
    ("Bakery > Tortillas",     {"Tortillas", "Tortilla"}),
    ("Bakery > Rolls",         {"Rolls", "Roll"}),
    ("Bakery > Buns",          {"Buns", "Bun"}),
    ("Bakery > Pie",           {"Pies", "Pie"}),
    ("Bakery > Brownies",      {"Brownies", "Brownie"}),
    ("Bakery > Flatbread",     {"Flatbread", "Flatbreads"}),
    ("Bakery > Croissants",    {"Croissants", "Croissant"}),
    ("Bakery > Biscuits",      {"Biscuits", "Biscuit"}),
    ("Bakery > Pastry",        {"Pastry", "Pastries"}),
    ("Bakery > Breadsticks",   {"Breadsticks", "Breadstick"}),
    ("Bakery > Crackers",      {"Crackers", "Cracker"}),
    ("Frozen > Ice Cream",     {"Ice Cream"}),
    ("Frozen > Pizza",         {"Pizza", "Pizzas"}),
    ("Frozen > Appetizers",    {"Appetizers", "Appetizer"}),
    ("Frozen > Single Entrees", {"Entrees", "Entree"}),
    ("Frozen > Breakfast",     {"Breakfast"}),
    ("Frozen > Prepared Seafood", {"Seafood"}),
    ("Meat & Seafood > Beef",  {"Beef"}),
    ("Meat & Seafood > Poultry", {"Poultry"}),
    ("Meat & Seafood > Pork",  {"Pork"}),
    ("Meat & Seafood > Salmon", {"Salmon"}),
    ("Meat & Seafood > Tuna",  {"Tuna"}),
    ("Meat & Seafood > Sausage", {"Sausage", "Sausages"}),
    ("Meat & Seafood > Bacon", {"Bacon"}),
    ("Meat & Seafood > Deli",  {"Deli"}),
    ("Meat & Seafood > Charcuterie", {"Charcuterie"}),
    ("Meat & Seafood > Ham",   {"Ham"}),
    ("Meat & Seafood > Turkey", {"Turkey"}),
    ("Meat & Seafood > Shrimp", {"Shrimp"}),
    ("Meat & Seafood > Hot Dogs", {"Hot Dogs", "Hot Dog"}),
    ("Meal > Salads",          {"Salads", "Salad"}),
    ("Meal > Pasta Dishes",    {"Pasta Dishes", "Dishes"}),
    ("Meal > Sandwiches",      {"Sandwiches", "Sandwich"}),
    ("Meal > Pizza",           {"Pizza", "Pizzas"}),
    ("Meal > Soup",            {"Soup", "Soups"}),
    ("Meal > Composite Dishes", {"Dishes", "Dish"}),
    ("Meal > Salad Kits",      {"Salad Kits", "Kits", "Kit"}),
    ("Meal > Dumplings",       {"Dumplings", "Dumpling"}),
    ("Produce > Fruit",        {"Fruit", "Fruits"}),
    ("Produce > Vegetables",   {"Vegetables", "Vegetable"}),
    ("Produce > Salad Mixes",  {"Salad Mixes", "Mixes", "Mix"}),
    ("Produce > Salad Kits",   {"Salad Kits", "Kits", "Kit"}),
    ("Produce > Herbs",        {"Herbs", "Herb"}),
]

# Skip these compound segments — the redundancy is part of the official name
SKIP_SEGMENTS = {
    "Chocolate Chip", "Sugar Cookie", "Peanut Butter Cookie", "Oatmeal Cookie",
    "Jelly Beans", "Fruit Snacks", "Ice Cream", "Hot Dog", "Hot Dogs",
    "Cream Cheese",  # Cream is also a parent in Dairy — skip explicit collapse
    "Cottage Cheese",  # Cottage is itself a sub-type
    "Goat Cheese", "Blue Cheese", "String Cheese",
    "Trail Mix", "Snack Mix",
    "Sour Cream", "Whipped Cream", "Heavy Cream", "Light Cream",
    "Coffee Creamer", "Cream Soda",
    "Salad Dressing",  # Already in parent
}


def strip_echo(seg: str, words_to_strip: set[str]) -> str:
    """Remove parent-echo word from segment. Word can be at start or end.
    'Potato Chips' + {Chips, Chip} → 'Potato'
    'Sweet Potato Chips' + {Chips} → 'Sweet Potato'
    """
    if seg in SKIP_SEGMENTS: return seg
    # Try multi-word entries first
    for word in sorted(words_to_strip, key=lambda w: -len(w)):
        # End-of-segment with leading space
        if seg.endswith(" " + word):
            return seg[:-len(word)-1].strip()
        # Start-of-segment with trailing space (rare but possible)
        if seg.startswith(word + " "):
            return seg[len(word)+1:].strip()
    return seg


def fix_path(path: str) -> str:
    if not path: return path
    segs = path.split(" > ")
    if len(segs) < 3: return path
    parent = " > ".join(segs[:2])
    # Find matching ECHO_PARENTS entry
    words: set[str] | None = None
    for parent_path, ws in ECHO_PARENTS:
        if parent == parent_path:
            words = ws; break
    if words is None or not words:
        return path
    # Strip parent-echo from 3rd segment
    new_third = strip_echo(segs[2], words)
    if new_third == segs[2]:
        return path  # nothing to change
    if not new_third:
        # Don't allow empty 3rd segment — just keep as is
        return path
    new_segs = segs[:2] + [new_third] + segs[3:]
    # Dedupe non-consecutive
    seen = set(); out = []
    for s in new_segs:
        k = s.lower()
        if k in seen: continue
        seen.add(k); out.append(s)
    return " > ".join(out)


def main() -> None:
    tmp = AUDIT.with_suffix(".tmp.csv")
    log_rows: list[dict] = []
    parent_counts: dict[str, int] = defaultdict(int)
    n_changed = 0
    with AUDIT.open(encoding="utf-8", newline="") as fin, \
         tmp.open("w", encoding="utf-8", newline="") as fout:
        rdr = csv.DictReader(fin)
        wtr = csv.DictWriter(fout, fieldnames=rdr.fieldnames)
        wtr.writeheader()
        for r in rdr:
            old_cp = r.get("canonical_path", "") or ""
            old_rlp = r.get("retail_leaf_path", "") or ""
            new_cp = fix_path(old_cp); new_rlp = fix_path(old_rlp)
            if new_cp != old_cp or new_rlp != old_rlp:
                n_changed += 1
                if new_cp != old_cp:
                    parent_counts[" > ".join(new_cp.split(" > ")[:2])] += 1
                r["canonical_path"] = new_cp
                r["retail_leaf_path"] = new_rlp
                log_rows.append({
                    "fdc_id": r.get("fdc_id", ""),
                    "old_canonical": old_cp, "new_canonical": new_cp,
                    "old_retail_leaf": old_rlp, "new_retail_leaf": new_rlp,
                })
            wtr.writerow(r)
    shutil.move(str(tmp), str(AUDIT))
    print(f"  rows changed: {n_changed:,}")
    print(f"  per parent (top 25):")
    for p in sorted(parent_counts, key=lambda k: -parent_counts[k])[:25]:
        print(f"    {p:<40} {parent_counts[p]:>5}")
    if log_rows:
        cols = list(log_rows[0].keys())
        with LOG.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=cols)
            w.writeheader()
            w.writerows(log_rows)
        print(f"  wrote {LOG.name}")


if __name__ == "__main__":
    main()
