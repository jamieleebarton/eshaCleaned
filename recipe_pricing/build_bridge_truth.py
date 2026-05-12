#!/usr/bin/env python3
"""Seed bridge_truth.csv from audit_full_bridge_top.csv.

For every concept in the top-offenders file, produce a truth-row with:
  recipe_cp, htc_form, must_contain (any of), must_not_contain (none of),
  required_top_cat, max_acceptable_n_recipes_for_no_match, notes

The auto-generated negatives come from the current bad SKU's distinctive
tokens. Top-50 by recipe-impact get hand-curated (CROSS_CATEGORY → block
priced top_cat; SKU_LEAF_MISS → block cleaning/cosmetic/non-food tokens).

Output: recipe_pricing/bridge_truth.csv
"""
from __future__ import annotations
import csv, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IN_TOP = ROOT / "recipe_pricing" / "audit_full_bridge_top.csv"
OUT = ROOT / "recipe_pricing" / "bridge_truth.csv"

STOP = {"the","a","an","of","and","or","with","fresh","raw","organic","plain",
        "ground","dried","cooked","whole","mix","style","flavor","grade","food",
        "great","value","kroger","marketside","brand","ready","fully","easy"}

# Universal negative tokens — any food-path SKU containing these is wrong.
# IMPORTANT: every phrase must be specific enough that substring-match won't
# fire on legitimate food. "gel" matches "large lemon" when collapsed;
# "plant" matches "eggplant"; "spray" matches "cooking spray" (legitimate).
# When in doubt: prefer the multi-word phrase over the single word.
UNIVERSAL_NEG = (
    "cleaner|candle|fragrance|bouquet|fertilizer|mulch|"
    "lotion|shampoo|detergent|deodorant|toilet|laundry|"
    "live plant|seedling|petunia|hosta|tomato plant|bonnie plants|"
    "cleaner spray|fragrance spray|hair spray|"
    "shoe polish|furniture polish|silver polish|"
    "scented candle|tea light|votive candle|"
    "shower gel|hand sanitizer|antiperspirant|"
    "weed killer|pesticide|insect spray"
)

# Foods that legitimately exist in BOTH Produce (fresh) and Pantry (dried)
# top-categories. The fixture allows either as required_top_cat.
PRODUCE_PANTRY_OK = {
    "Cilantro", "Basil", "Parsley", "Chives", "Mint", "Thyme",
    "Oregano", "Rosemary", "Sage", "Dill", "Bay Leaves", "Tarragon",
    "Marjoram", "Ginger", "Garlic", "Currants", "Dried Onion",
}

# Foods OK in either Produce or Frozen (fresh vs frozen)
PRODUCE_FROZEN_OK = {
    "Spinach", "Broccoli", "Cauliflower", "Peas", "Corn", "Strawberries",
    "Blueberries", "Raspberries", "Blackberries", "Lemon", "Limes",
    "Mango", "Pineapple",
}

# Snack-tier foods that are also OK at other tiers
SNACK_PANTRY_OK = {"Mints", "Chocolate Candy", "Candy", "Crackers", "Chili"}

# Per-leaf overrides — recipe wants X, must NOT match Y
LEAF_NEG = {
    "Chicken Broth": "lunchmeat|jerky|cooked|grilled|breast|tender|wing|drumstick|nugget|patty",
    "Beef Broth":    "marrow|jerky|patty|tender|nugget|sirloin|chuck|brisket|short rib",
    "Vegetable Broth": "stir fry|stew kit|frozen mixed",
    "Limes":         "splash|cocktail|juice cocktail|seltzer|hard seltzer",
    "Lemons":        "splash|cocktail|grapefruit|orange|extra pulp|drink mix",
    "Oranges":       "juice|orange juice|drink mix|cocktail|orange blend",
    "Bell Peppers":  "banana pepper|jalapeno|chili|pepper rings|serrano",
    "Ginger":        "sushi ginger|pickled ginger|crystallized|candied",
    "Basil":         "cleaner|candle|fragrance|cleaning|soap",
    "Cumin":         "toddler|baby food|infant",
    "Coriander":     "cilantro plant|cilantro fresh|fresh cilantro",
    "Mints":         "plant|mint plant|sweet mint plant|live plant",
    # Margarine: SKU must be a butter alternative, NOT pure butter.
    "Margarine":     "salted butter|unsalted butter|sweet cream butter",
    "Strawberries":  "smoothie|cocktail|wine cooler|frosting|topping|drink mix",
    "Apples":        "juice|cider drink|apple drink|sauce drink",
    "Active Dry Yeast": "instant|fast.rising|fast acting|rapid",
    "Cilantro":      "(?!)" ,  # cross-cat ok, both are cilantro
    "Garlic":        "garlic powder|garlic salt|garlic press|garlic spray",
    "Heavy Cream":   "whipped topping|cool whip|coconut cream|coffee creamer|powdered creamer",
    "Buttermilk":    "ranch|dressing|biscuit mix|powder|powdered",
    "Mozzarella":    "daiya|vegan|plant.based|imitation",
    "Cheddar":       "daiya|vegan|imitation",
    "Tortillas":     "tortilla chips|chip|nacho",
    "Bread Crumbs":  "panko",  # if recipe says "breadcrumbs" plain panko is wrong
    "Butter":        "imperial|spread|margarine|i can't believe",
    "Milk":          "almond|soy|coconut|oat|hemp|rice",  # only for plain "milk"
}


def leaf(p: str) -> str:
    return (p.split(" > ")[-1] if p else "")


def top(p: str) -> str:
    return (p.split(" > ")[0] if p else "")


# Synonyms — recipe leaf X allows SKU containing any of these tokens too.
# R13 tightened: dropped omnibus aliases that were too permissive.
# Specifically removed:
#   - "sausage" → hot dog/bologna/frankfurter (these are NOT sausage substitutes)
#   - "spreads" → peanut butter/mayonnaise (PB ≠ jam ≠ mayo ≠ butter, distinct foods)
#   - "vegetables" → tomato/carrot/etc. (too broad — recipe wanting "vegetables" as
#     leaf is rare AND should not match a single specific veg)
# Kept synonyms only where the recipe-side leaf and SKU-side leaf are
# genuinely interchangeable foods (margarine ≡ vegetable oil spread, sugar
# substitute ≡ sweetener brand names).
LEAF_SYNONYMS = {
    # Margarine: modern brands sell "Vegetable Oil Spread" — same product
    "margarine": "vegetable oil spread|i can't believe it's not butter|country crock|smart balance|earth balance",
    # Maraschino cherries ARE candied fruit
    "candied fruit": "maraschino|glazed cherries|crystallized cherries",
    # Drink mix variants
    "drink mix": "kool aid|atole|drink blend|punch mix|powdered drink",
    # Sugar substitute = sweetener brands (these ARE the same product)
    "sweetener": "sucralose|aspartame|stevia|saccharin|monk fruit|truvia|equal|sweet n low",
    "sugar substitute": "sucralose|aspartame|stevia|saccharin|monk fruit|truvia|equal|sweet n low|no calorie|zero calorie",
    # Food coloring forms
    "food coloring": "food color|gel color|food dye|liquid color|paste color",
    # Pastry forms — honey bun IS a pastry
    "pastry": "honey bun|iced bun|cinnamon roll|donut|danish|croissant|turnover|bear claw|kolache",
    # Baking mix variants
    "baking mix": "muffin mix|biscuit mix|pancake mix|cake mix|brownie mix|bread mix",
    # Canned seafood is ANY canned fish
    "canned seafood": "tuna|salmon|sardine|anchovy|crab|clam|oyster|mackerel|herring",
    # Tea variants
    "tea": "tea bag|black tea|green tea|herbal tea|loose leaf|chai|earl grey|english breakfast",
    # Liqueur is a category — these are common members
    "liqueur": "amaretto|kahlua|baileys|grand marnier|sambuca|chambord|cointreau|drambuie|frangelico",
    "cream liqueur": "baileys|carolans|amaretto cream|rumchata",
}


def leaf_token(p: str) -> str:
    """Pull the dominant content word from leaf for must_contain.
    Returns multiple alternatives separated by "|" so plural/singular and
    common synonyms all qualify."""
    L = leaf(p).lower()
    toks = [t for t in re.findall(r"[a-z]+", L) if len(t) > 2 and t not in STOP]
    if not toks: return ""
    # Use ALL content words (e.g., "Bell Peppers" → both "bell" and "peppers"
    # qualify; the test stem-matches so plural→singular works)
    return "|".join(toks)


def main():
    if not IN_TOP.exists():
        print(f"missing {IN_TOP}", file=sys.stderr); sys.exit(1)

    rows_out = []
    with IN_TOP.open() as f:
        for row in csv.DictReader(f):
            cp = row["recipe_cp"]
            l = leaf(cp)
            tc = top(cp)
            # Skip top-only cps (e.g., recipe_cp == "Pantry") — there is no
            # specific food we can assert on; these will get assertions added
            # by hand if needed
            if " > " not in cp:
                continue
            mc = leaf_token(cp)
            if not mc: continue
            # Layer in synonyms — recipe says "Sausage" but chorizo IS a
            # sausage; "Margarine" but Imperial Vegetable Oil Spread IS
            # modern margarine. Synonyms attach to the leaf (case-insensitive).
            leaf_lc = l.lower()
            if leaf_lc in LEAF_SYNONYMS:
                mc = mc + "|" + LEAF_SYNONYMS[leaf_lc]
            mn = LEAF_NEG.get(l, "")
            # Always layer in universal negatives (cleaner/plant/etc.) ON TOP
            mn_full = UNIVERSAL_NEG if not mn else f"{mn}|{UNIVERSAL_NEG}"
            tops = [tc]
            if l in PRODUCE_PANTRY_OK:
                tops = sorted({"Produce", "Pantry"})
            elif l in PRODUCE_FROZEN_OK:
                tops = sorted({"Produce", "Frozen"})
            elif l in SNACK_PANTRY_OK:
                tops = sorted({"Snack", "Pantry"})
            rows_out.append({
                "recipe_cp": cp,
                "htc_form": row["htc_form"],
                "required_top_cat": "|".join(tops),
                "must_contain_any": mc,
                "must_not_contain_any": mn_full,
                "n_recipes_baseline": row["n_recipes_touched"],
                "current_picked_sku": row["cheapest_sku"],
                "current_flags": row["flags"],
                "notes": "auto-seed",
            })

    # Drop dupes (keep highest impact)
    seen: dict = {}
    for r in rows_out:
        k = r["recipe_cp"]
        if k not in seen or int(r["n_recipes_baseline"]) > int(seen[k]["n_recipes_baseline"]):
            seen[k] = r
    rows_out = sorted(seen.values(),
                       key=lambda r: -int(r["n_recipes_baseline"]))

    with OUT.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows_out[0].keys()))
        w.writeheader()
        for r in rows_out: w.writerow(r)

    print(f"wrote {len(rows_out):,} truth rows → {OUT}", file=sys.stderr)
    print(f"top recipe-impact: {rows_out[0]['n_recipes_baseline']}",
          file=sys.stderr)


if __name__ == "__main__":
    main()
