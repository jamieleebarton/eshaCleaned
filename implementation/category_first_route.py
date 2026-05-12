#!/usr/bin/env python3
"""Category-first deterministic routing pass.

See ARCHITECTURE.md for the design.

Inputs:
  - implementation/output/product_to_best_esha_full_map.vIdentity.csv  (canonical, edited in place)
  - implementation/output/product_to_best_esha_full_map.vIdentity.baseline.csv (untainted)
  - esha_cleaned_canonical.csv

Outputs (written next to vIdentity.csv):
  - product_to_best_esha_full_map.vIdentity.csv (in-place rewrite)
  - category_first_changelog.csv
  - category_first_new_leaves.csv

No LLM calls. No remote APIs. No new versioned files.
"""
from __future__ import annotations

import csv
import json
import os
import pickle
import re
import sys
import time
from collections import Counter, defaultdict

import numpy as np

ROOT = "/Users/jamiebarton/Desktop/esha_audit_bundle"
IMPL = os.path.join(ROOT, "implementation")
OUT = os.path.join(IMPL, "output")
EMB = os.path.join(IMPL, ".embed_cache")

VID = os.path.join(OUT, "product_to_best_esha_full_map.vIdentity.csv")
BASE = os.path.join(OUT, "product_to_best_esha_full_map.vIdentity.baseline.csv")
ESHA = os.path.join(ROOT, "esha_cleaned_canonical.csv")

CHANGELOG = os.path.join(OUT, "category_first_changelog.csv")
NEW_LEAVES = os.path.join(OUT, "category_first_new_leaves.csv")
TMP_OUT = VID + ".tmp"

csv.field_size_limit(sys.maxsize)

# ---------------------------------------------------------------------------
# Category cluster map. Hand curated: NARROW. Sibling categories grouped only
# when they clearly describe the same nutritional concept space.
# Rule: when in doubt, do NOT cluster.
# ---------------------------------------------------------------------------

CATEGORY_CLUSTERS: list[list[str]] = [
    # Bread (loaves, buns, bagels)
    [
        "Breads & Buns",
        "Bread",
        "Bread - Incl. Buns And Rolls",
        "Bread/Bakery Products Variety Packs",
        "Frozen Bread & Dough",
        "Bread & Muffin Mixes",
    ],
    # Crackers / biscotti / flatbreads
    [
        "Crackers & Biscotti",
        "Flavored Snack Crackers",
        "Biscuits Cracker",
    ],
    # Cookies / biscuits / cookie mixes
    [
        "Cookies & Biscuits",
        "Biscuits/Cookies",
        "Biscuits/Cookies (Shelf Stable)",
        "Biscuits Chocolate",
        "Cake, Cookie & Cupcake Mixes",
    ],
    # Cakes / pastries / sweet bakery
    [
        "Cakes, Cupcakes, Snack Cakes",
        "Croissants, Sweet Rolls, Muffins & Other Pastries",
        "Sweet Bakery Products",
        "Cakes - Sweet (Frozen)",
        "Cakes and Slices",
        "Pies/Pastries - Sweet (Shelf Stable)",
        "Pancakes, Waffles, French Toast & Crepes",
        "Frozen Pancakes, Waffles, French Toast & Crepes",
        "Savoury Bakery Products",
    ],
    # Pickles, olives, peppers, relishes
    [
        "Pickles, Olives, Peppers & Relishes",
        "Pickles/Relishes/Chutneys/Olives",
    ],
    # Cheese
    [
        "Cheese",
        "Cheese/Cheese Substitutes",
        "Cheese - Speciality",
        "Cheese - Block",
    ],
    # Yogurt
    [
        "Yogurt",
        "Yogurt/Yogurt Substitutes",
        "Dairy Foods/Yoghurts",
    ],
    # Milk
    [
        "Milk",
        "Milk/Milk Substitutes",
        "Plant Based Milk",
        "Milk Additives",
        "Milk/Cream - Shelf Stable",
    ],
    # Cream / butter
    [
        "Cream",
        "Cream/Cream Substitutes",
    ],
    [
        "Butter & Spread",
        "Butter/Butter Substitutes",
    ],
    # Ice cream / frozen dessert
    [
        "Ice Cream & Frozen Yogurt",
        "Ice Cream/Ice Novelties (Shelf Stable)",
        "Other Frozen Desserts",
        "Ice-Cream Take Home",
    ],
    # Pizza / dough-based
    [
        "Pizza",
        "Crusts & Dough",
        "Dough Based Products / Meals",
        "Pies/Pastries/Pizzas/Quiches - Savoury (Frozen)",
    ],
    # Pasta dry
    [
        "Pasta by Shape & Type",
        "All Noodles",
        "Pasta/Noodles",
    ],
    # Pasta dinners cooked
    [
        "Pasta Dinners",
        "Prepared Pasta & Pizza Sauces",
    ],
    # Cereal
    [
        "Cereal",
        "Processed Cereal Products",
        "Cereals Products - Ready to Eat (Shelf Stable)",
        "Cereals Products - Not Ready to Eat (Shelf Stable)",
        "Breakfast Cereals - Hot And Cold",
    ],
    # Snack bars
    [
        "Snack, Energy & Granola Bars",
        "Cereal/Muesli Bars",
        "Wrapped Snacks - Muesli Bars",
    ],
    # Chips / pretzels / snacks
    [
        "Chips, Pretzels & Snacks",
        "Chips/Crisps/Snack Mixes - Natural/Extruded (Shelf Stable)",
        "Snack Foods - Chips",
    ],
    # Popcorn / nuts / seeds
    [
        "Popcorn, Peanuts, Seeds & Related Snacks",
        "Nut & Seed Butters",
        "Nuts/Seeds  Prepared/Processed",
        "Nuts/Seeds - Prepared/Processed",
        "Nuts/Seeds - Prepared/Processed (Shelf Stable)",
    ],
    # Candy / chocolate. We deliberately do NOT include the catch-all
    # "Confectionery Products" here — it's ambiguous (covers gum, mints,
    # chocolate, hard candy) and clustering it with Candy was producing
    # gum -> Skittles type errors. Confectionery Products is its own
    # singleton; products there will mostly get flagged for new leaves
    # which is the honest answer.
    [
        "Candy",
        "Chocolate",
        "Confectionery",
    ],
    # Juice
    [
        "Fruit & Vegetable Juice, Nectars & Fruit Drinks",
        "Frozen Fruit & Fruit Juice Concentrates",
        "Drinks - Juices, Drinks and Cordials",
    ],
    # Soda / soft drinks
    [
        "Soda",
        "Drinks - Soft Drinks",
    ],
    # Other drinks (bottled tea / sport / energy / RTD)
    [
        "Iced & Bottle Tea",
        "Tea Bags",
        "Tea and Infusions/Tisanes",
    ],
    [
        "Coffee",
        "Coffee/Tea/Substitutes",
        "Coffee/Coffee Substitutes",
    ],
    [
        "Sport Drinks",
        "Energy, Protein & Muscle Recovery Drinks",
    ],
    # Water
    [
        "Water",
        "Plant Based Water",
        "Liquid Water Enhancer",
    ],
    # Salad dressing / mayo / oil
    [
        "Salad Dressing & Mayonnaise",
        "Salad Dressings",
    ],
    [
        "Vegetable & Cooking Oils",
        "Oils Edible",
        "Fats Edible",
    ],
    # Dips / salsa / hummus
    [
        "Dips & Salsa",
        "Dips/Hummus/Pate",
    ],
    # Condiments / sauces
    [
        "Ketchup, Mustard, BBQ & Cheese Sauce",
        "Other Condiments",
        "Sauces/Spreads/Dips/Condiments",
        "Sauces",
        "Sauces- Cooking",
        "Other Cooking Sauces",
        "Oriental, Mexican & Ethnic Sauces",
    ],
    # Jam / preserves / sweet spreads
    [
        "Jam, Jelly & Fruit Spreads",
        "Sweet Spreads",
        "Spreads",
        "Honey",
        "Syrups & Molasses",
    ],
    # Soup
    [
        "Other Soups",
        "Canned Soup",
        "Canned Condensed Soup",
        "Prepared Soups",
        "Chili & Stew",
    ],
    # Frozen entrees / meals
    [
        "Frozen Dinners & Entrees",
        "Frozen Appetizers & Hors D'oeuvres",
        "Ready-Made Combination Meals",
        "Prepared Meals",
        "Frozen Meals",
        "Entrees, Sides & Small Meals",
        "Frozen Prepared Sides",
    ],
    # Lunch meat / cold cuts
    [
        "Pepperoni, Salami & Cold Cuts",
        "Salami / Cured Meat",
        "Other Deli",
    ],
    # Sausage / bacon / hotdog
    [
        "Sausages, Hotdogs & Brats",
        "Frozen Sausages, Hotdogs & Brats",
        "Bacon, Sausages & Ribs",
        "Frozen Bacon, Sausages & Ribs",
        "Bacon",
        "Sausages/Smallgoods",
        "Meat/Poultry/Other Animals Sausages  Prepared/Processed",
        "Meat/Poultry/Other Animals Sausages - Prepared/Processed",
    ],
    # Poultry
    [
        "Poultry, Chicken & Turkey",
        "Frozen Poultry, Chicken & Turkey",
        "Frozen Chicken - Processed",
    ],
    # Other meats
    [
        "Other Meats",
        "Other Frozen Meats",
        "Frozen Meat",
        "Frozen Patties and Burgers",
        "Meat/Poultry/Other Animals  Prepared/Processed",
        "Meat/Poultry/Other Animals - Prepared/Processed",
        "Meat/Poultry/Other Animals  Unprepared/Unprocessed",
        "Meat/Poultry/Other Animals - Unprepared/Unprocessed",
        "Canned Meat",
        "Vegetarian Frozen Meats",
    ],
    # Fish / seafood
    [
        "Fish & Seafood",
        "Frozen Fish & Seafood",
        "Frozen Fish/Seafood",
        "Canned Seafood",
        "Canned Tuna",
        "Canned Fish and Meat",
        "Fish  Unprepared/Unprocessed",
        "Fish  Prepared/Processed",
        "Fish - Prepared/Processed",
        "Shellfish Unprepared/Unprocessed",
        "Smoked fish",
        "Seafood Miscellaneous",
        "Sushi",
    ],
    # Vegetables (canned, fresh, frozen)
    [
        "Canned Vegetables",
        "Frozen Vegetables",
        "Pre-Packaged Fruit & Vegetables",
        "Vegetables  Prepared/Processed",
        "Vegetables - Prepared/Processed",
        "Vegetables - Prepared/Processed (Shelf Stable)",
        "Tomatoes",
        "Vegetable and Lentil Mixes",
        "Vegetable Based Products / Meals",
        "Vegetable Based Products / Meals - Not Ready to Eat (Frozen)",
        "Canned/Dried Veges",
    ],
    # Fruit
    [
        "Canned Fruit",
        "Frozen Fruit",
        "Fruit  Prepared/Processed",
        "Fruit - Prepared/Processed",
        "Fruit - Prepared/Processed (Shelf Stable)",
    ],
    # Beans
    [
        "Canned & Bottled Beans",
    ],
    # Rice / grains
    [
        "Rice",
        "Flavored Rice Dishes",
        "Other Grains & Seeds",
        "Grains/Flour",
        "Grain Based Products / Meals",
    ],
    # Flour / baking
    [
        "Flours & Corn Meal",
        "Baking Additives & Extracts",
        "Baking Decorations & Dessert Toppings",
        "Baking/Cooking Mixes/Supplies",
        "Baking/Cooking Supplies (Shelf Stable)",
        "Baking",
        "Baking Needs",
        "Granulated, Brown & Powdered Sugar",
        "Sugars/Sugar Substitute Products",
        "Sugar And Flour",
    ],
    # Eggs
    [
        "Eggs & Egg Substitutes",
        "Eggs/Eggs Substitutes",
    ],
    # Pudding / gelatin
    [
        "Puddings & Custards",
        "Gelatin, Gels, Pectins & Desserts",
        "Desserts & Custard",
        "Desserts/Dessert Sauces/Toppings",
    ],
    # Pizza/pasta dry mixes
    [
        "Pizza Mixes & Other Dry Dinners",
        "Mexican Dinner Mixes",
    ],
    # Stuffing
    [
        "Stuffing",
    ],
    # Spice / seasonings
    [
        "Seasoning Mixes, Salts, Marinades & Tenderizers",
        "Herbs & Spices",
        "Herbs/Spices/Extracts",
        "Herbs And Spices",
        "Seasonings/Preservatives/Extracts Variety Packs",
    ],
    # Gravy
    [
        "Gravy Mix",
    ],
    # Breakfast sandwiches
    [
        "Frozen Breakfast Sandwiches, Biscuits & Meals",
        "Breakfast Sandwiches, Biscuits & Meals",
    ],
    # Sandwiches / wraps
    [
        "Prepared Subs & Sandwiches",
        "Sandwiches/Filled Rolls/Wraps",
        "Prepared Wraps and Burittos",
    ],
    # Fries / potato sides
    [
        "French Fries, Potatoes & Onion Rings",
    ],
    # Deli salads / cooked & prepared
    [
        "Deli Salads",
        "Salads",
        "Cooked & Prepared",
    ],
    # Lunch combos
    [
        "Lunch Snacks & Combinations",
    ],
    # Powdered drinks / mixes
    [
        "Powdered Drinks",
        "Breakfast Drinks",
        "Non Alcoholic Beverages  Not Ready to Drink",
        "Non Alcoholic Beverages - Not Ready to Drink",
    ],
    # Other drinks RTD
    [
        "Other Drinks",
        "Non Alcoholic Beverages  Ready to Drink",
        "Non Alcoholic Beverages - Ready to Drink",
        "Drinks Flavoured - Ready to Drink",
    ],
    # Alcohol
    [
        "Alcohol",
        "Alcoholic Beverages",
    ],
    # Chewing gum
    [
        "Chewing Gum & Mints",
    ],
    # Pastry shells / fillings
    [
        "Pastry Shells & Fillings",
    ],
    # Vegetarian
    [
        "Vegetarian",
    ],
    # Specialty supplements
    [
        "Specialty Formula Supplements",
        "Meal Replacement Supplements",
        "Children's Nutritional Supplements",
        "Health Care",
        "Vitamins",
        "Health Supplements and Vitamins",
        "Herbal Supplements",
        "Digestive & Fiber Supplements",
        "Green Supplements",
        "Weight Control",
    ],
    # Taco shells
    [
        "Taco Shells",
    ],
    # Baby
    [
        "Baby/Infant  Foods/Beverages",
    ],
]


def build_category_to_cluster() -> dict[str, str]:
    m: dict[str, str] = {}
    for cluster in CATEGORY_CLUSTERS:
        canonical = cluster[0]
        for c in cluster:
            m[c] = canonical
    return m


# ---------------------------------------------------------------------------
# Tokenization
# ---------------------------------------------------------------------------

DOMAIN_STOPWORDS = {
    "flavor", "flavored", "flavour", "flavoured",
    "style", "styled", "original", "variety", "pack", "packs",
    "with", "without", "from", "made", "into",
    "size", "sized", "value", "family", "premium", "natural",
    "organic", "homestyle", "country", "fresh", "freshly",
    "real", "classic", "regular", "selected", "special", "best",
    "small", "large", "medium", "mini", "jumbo",
    "added", "free", "less", "lite", "light", "low", "high", "extra",
    "case", "container", "bottle", "bottles", "jar", "jars", "bag", "bags",
    "ounce", "ounces", "pound", "pounds", "gram", "grams", "fluid",
    "each", "count", "ready", "shelf", "stable", "frozen", "refrigerated",
    "fully", "cooked", "uncooked", "prepared", "processed",
    "brand", "brands", "store", "stores",
    "edible", "based", "products",
    "the", "and", "for", "all", "new", "not", "but", "any",
    "this", "that", "these", "those", "such", "more", "most",
    "are", "was", "were", "has", "have", "had", "be", "been", "being",
    "served", "serves", "serving", "servings", "per", "great", "good",
}


_word_re = re.compile(r"[A-Za-z]+")


# Distinctive identity markers — if a candidate description contains one of
# these and the product description does NOT, that's a strong "wrong code"
# signal. Penalty applied per match.
SURPRISE_MARKERS = {
    "vegetarian", "vegan",
    "kids", "kid", "junior", "baby", "toddler", "infant",
    "pulled",  # "pulled chicken" specific
    "smoked", "smokey", "fried",
    "dehydrated", "freeze",  # freeze dried
    "powdered", "powder",
    "instant", "concentrate", "concentrated",
    "stewed",
    "candied",
    "pickled",
    "sour",
    "diet", "lite",  # only surprise if not in product
    "fortified",
    "imitation",
    "artificial",
    "mandarin",
    "tropical",  # tropical-punch type wins
    "neapolitan",
    "sandwich",  # cheese sandwich/wraps
    "ball",  # cheese ball, etc
    "cracker",
    "stick", "sticks",  # only when not in product
    "crusted",
}


def tokens(s: str | None, *, min_len: int = 4) -> set[str]:
    if not s:
        return set()
    out = set()
    for m in _word_re.finditer(s.lower()):
        w = m.group(0)
        if len(w) < min_len:
            continue
        if w in DOMAIN_STOPWORDS:
            continue
        out.add(w)
    return out


def head_noun(esha_desc: str | None) -> str:
    """Extract the leading head noun from an ESHA description.
    'Cereal, Frosted Mini Wheats, blueberry muffin, bites' -> 'cereal'.
    'Chewing Gum, sugarless' -> 'chewing'.   (caller should also check
       second token for compound heads.)
    """
    if not esha_desc:
        return ""
    head = esha_desc.split(",", 1)[0].strip().lower()
    m = _word_re.findall(head)
    return m[0] if m else ""


def head_phrase_tokens(esha_desc: str | None) -> set[str]:
    """All alpha tokens in the leading phrase before the first comma."""
    if not esha_desc:
        return set()
    head = esha_desc.split(",", 1)[0].strip().lower()
    return {w for w in _word_re.findall(head) if len(w) >= 3}


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------


def load_tree() -> tuple[list[str], list[str], dict[str, str]]:
    with open(os.path.join(EMB, "tree_codes.pkl"), "rb") as f:
        tc = pickle.load(f)  # list of (code, desc)
    codes = [c for c, _ in tc]
    descs = [d for _, d in tc]
    code2desc = dict(tc)
    return codes, descs, code2desc


def cohort_majority_from_baseline() -> dict[str, dict]:
    """Compute (majority_category, majority_share, cohort_size) per ESHA code
    using the BASELINE assignments — uncontaminated by recent passes."""
    code_cat: dict[str, Counter] = defaultdict(Counter)
    with open(BASE, newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            c = (row.get("best_esha_code") or "").strip()
            cat = (row.get("branded_food_category") or "").strip()
            if c and cat:
                code_cat[c][cat] += 1
    out = {}
    for code, ctr in code_cat.items():
        total = sum(ctr.values())
        top, k = ctr.most_common(1)[0]
        out[code] = {
            "majority_category": top,
            "majority_share": k / total,
            "cohort_size": total,
        }
    return out


# ---------------------------------------------------------------------------
# Main pass
# ---------------------------------------------------------------------------


def main() -> None:
    t0 = time.time()
    print(f"[{time.strftime('%H:%M:%S')}] loading inputs...")

    cat2cluster = build_category_to_cluster()
    cohort = cohort_majority_from_baseline()
    print(f"  cohort fingerprints: {len(cohort)} codes")

    tree_codes, tree_descs, code2desc = load_tree()
    print(f"  tree codes: {len(tree_codes)}")
    code2idx = {c: i for i, c in enumerate(tree_codes)}

    # Embeddings (used only as tiebreak)
    tree_emb = np.load(os.path.join(EMB, "tree_emb.npy"))
    prod_emb = np.load(os.path.join(EMB, "prod_emb.npy"), mmap_mode="r")
    prod_ids = np.load(os.path.join(EMB, "prod_ids.npy"), allow_pickle=True)
    pid2row = {str(p): i for i, p in enumerate(prod_ids)}
    print(f"  embeddings: prod {prod_emb.shape}, tree {tree_emb.shape}")

    # Pre-tokenize tree descriptions and extract head phrase tokens
    tree_tokens = [tokens(d) for d in tree_descs]
    tree_heads = [head_phrase_tokens(d) for d in tree_descs]

    # Build per-cluster pool of candidate codes (only codes whose cohort majority
    # maps to a cluster). Skip codes with cohort_size < 1.
    cluster_to_codes: dict[str, list[str]] = defaultdict(list)
    code2cluster: dict[str, str] = {}
    for code, m in cohort.items():
        cl = cat2cluster.get(m["majority_category"])
        if cl is None:
            # singleton cluster keyed by category itself (so same-cat codes still pool)
            cl = m["majority_category"]
        code2cluster[code] = cl
        cluster_to_codes[cl].append(code)
    print(f"  clusters with at least one code: {len(cluster_to_codes)}")

    # Read full vIdentity, decide actions per row, accumulate writes
    with open(VID, newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        header = r.fieldnames
        rows = list(r)
    print(f"  loaded {len(rows)} vIdentity rows")

    changelog_rows = []
    new_leaf_rows = []
    n_category_ok = 0
    n_unknown_current = 0  # current code has no cohort or unknown cat
    n_needs_reroute = 0
    n_rerouted = 0
    n_new_leaf = 0
    n_protected = 0

    for ri, row in enumerate(rows):
        if ri % 50000 == 0 and ri:
            print(f"    processed {ri:,}/{len(rows):,}  elapsed {time.time()-t0:.0f}s")
        cur_code = (row.get("best_esha_code") or "").strip()
        prod_cat = (row.get("branded_food_category") or "").strip()
        if not prod_cat:
            n_category_ok += 1  # nothing we can do
            continue
        prod_cluster = cat2cluster.get(prod_cat, prod_cat)

        # Determine current code's cluster
        cur_meta = cohort.get(cur_code)
        if not cur_meta or cur_meta["cohort_size"] < 4:
            cur_cluster = None  # unreliable / unknown
        else:
            cur_cluster = code2cluster.get(cur_code)

        # CATEGORY-OK check
        if cur_cluster is not None and cur_cluster == prod_cluster:
            n_category_ok += 1
            continue

        # We have a category mismatch (or unreliable cohort). Decide whether to act.
        verdict = (row.get("rft_verdict") or "").strip()

        # Protected: STRONG/EXACT with reliable cohort that *agrees with category* —
        # but if we got here, the cohort doesn't agree. So still candidate for reroute.
        # However if the current code's cohort is unknown (size<4) we are more
        # cautious: only reroute if there is a high-quality candidate.

        n_needs_reroute += 1

        # Build candidate pool: codes whose cluster == prod_cluster.
        pool = cluster_to_codes.get(prod_cluster, [])
        if not pool:
            new_leaf_rows.append((row, [], "no_candidate_cluster_for_category"))
            n_new_leaf += 1
            continue

        # Score candidates
        prod_desc = row.get("product_description", "")
        rft_canon = row.get("rft_canonical_name", "")
        rft_fndds = row.get("rft_fndds_desc", "")
        rft_sr28 = row.get("rft_sr28_desc", "")
        prod_toks = tokens(prod_desc) | tokens(rft_canon)
        fndds_toks = tokens(rft_fndds)
        sr28_toks = tokens(rft_sr28)

        # Embedding row index
        pid = str(row.get("fdc_id", ""))
        emb_row_idx = pid2row.get(pid)
        prod_vec = prod_emb[emb_row_idx] if emb_row_idx is not None else None

        # Build the head-gate evidence pool. Tightly: ONLY the product
        # description tokens (and brand) — not rft_canonical, not rft_fndds,
        # not rft_sr28. Those upstream fields are inherited and frequently
        # leak the wrong head noun (e.g. an almonds product gets
        # rft_sr28="nuts, almonds" by inheritance, and lets a "Nuts, macadamia"
        # candidate pass the gate). The product's own name is the authority.
        head_evidence = tokens(prod_desc, min_len=3) | tokens(row.get("brand_name", ""), min_len=3)

        scored: list[tuple[float, str, dict]] = []
        for code in pool:
            ti = code2idx.get(code)
            if ti is None:
                continue
            ttoks = tree_tokens[ti]
            if not ttoks:
                continue

            # HARD guard: candidate's head phrase must overlap with the product
            # description's own tokens. We do not allow inherited fndds/sr28
            # tokens to satisfy this — those leak the wrong head.
            cand_head = tree_heads[ti]
            if cand_head and not (cand_head & head_evidence):
                continue

            score = 0.0
            signals = {}

            # Token overlap (product description)
            if prod_toks:
                ov = prod_toks & ttoks
                if ov:
                    score += 10 * len(ov)
                    signals["prod_token_overlap"] = sorted(ov)

            # FNDDS exact
            if fndds_toks and ttoks:
                fov = fndds_toks & ttoks
                if fov and len(fov) >= max(1, len(fndds_toks) // 2):
                    # at least half of fndds tokens hit the candidate
                    score += 50
                    signals["fndds_match"] = sorted(fov)

            # SR28 exact
            if sr28_toks and ttoks:
                sov = sr28_toks & ttoks
                if sov and len(sov) >= max(1, len(sr28_toks) // 2):
                    score += 30
                    signals["sr28_match"] = sorted(sov)

            # Tiny embedding tiebreak (max 5 pts)
            if prod_vec is not None:
                cos = float(prod_vec @ tree_emb[ti])
                score += 5.0 * cos
                signals["embed_cos"] = round(cos, 3)

            # Penalty for very small target cohorts (unreliable destinations).
            cmeta = cohort.get(code)
            if cmeta:
                if cmeta["cohort_size"] < 4:
                    score -= 25
                    signals["small_target_cohort"] = cmeta["cohort_size"]
                elif cmeta["cohort_size"] < 8:
                    score -= 12
                    signals["small_target_cohort"] = cmeta["cohort_size"]

            # Penalty for "surprise" tokens — distinctive identity markers in
            # the candidate description that aren't in the product. Stops
            # "Vegetarian Meat" winning over real meat products on shared
            # tokens, and stops "kids/pulled/freeze dried/dehydrated" wins.
            surprise = ttoks - prod_toks - fndds_toks - sr28_toks
            distinctive_surprise = surprise & SURPRISE_MARKERS
            if distinctive_surprise:
                score -= 15 * len(distinctive_surprise)
                signals["surprise_markers"] = sorted(distinctive_surprise)

            scored.append((score, code, signals))

        if not scored:
            new_leaf_rows.append((row, [], "no_candidate_pool_codes_in_tree"))
            n_new_leaf += 1
            continue

        scored.sort(key=lambda x: -x[0])
        best_score, best_code, best_signals = scored[0]
        runner_up = scored[1][0] if len(scored) > 1 else 0.0

        # Decision threshold. Score alone is necessary but not sufficient —
        # we also require *substantive* signal (multi-token overlap or a
        # strong fndds/sr28 hit). This kills wins like "PEANUT BUTTER KANDY
        # KAKES" -> "Butter, whipped, sweet cream" where the only overlap
        # was the 1 token "butter".
        prod_ov = best_signals.get("prod_token_overlap", []) if best_signals else []
        fndds_match = best_signals.get("fndds_match", []) if best_signals else []
        sr28_match = best_signals.get("sr28_match", []) if best_signals else []
        substantive = (
            len(prod_ov) >= 3
            or len(fndds_match) >= 2
            or len(sr28_match) >= 2
            # tolerate 2-token product overlap if also fndds-confirmed
            or (len(prod_ov) >= 2 and (fndds_match or sr28_match))
        )
        confident = best_score >= 25 and (best_score - runner_up) >= 8 and substantive

        if not confident:
            # record top3 attempt for human review
            top3 = [(c, round(s, 2), sig) for s, c, sig in scored[:3]]
            new_leaf_rows.append((row, top3, "low_confidence_inpool"))
            n_new_leaf += 1
            continue

        # No-op if the best candidate is the current code (can happen when
        # cur cohort is < 4 size so cur_cluster=None even though current code
        # is fine). Don't rewrite.
        if best_code == cur_code:
            n_category_ok += 1
            continue

        # APPLY reroute
        old_code = cur_code
        old_desc = row.get("best_esha_description", "")
        new_desc = code2desc.get(best_code, "")

        # preserve audit trail: only set original if not set
        if not (row.get("best_esha_original_code") or "").strip():
            row["best_esha_original_code"] = old_code
            row["best_esha_original_description"] = old_desc

        row["best_esha_code"] = best_code
        row["best_esha_description"] = new_desc
        row["assignment_source"] = "category_first_route"
        row["best_esha_change_reason"] = "category_first_route"

        changelog_rows.append({
            "fdc_id": row.get("fdc_id", ""),
            "product_description": prod_desc,
            "branded_food_category": prod_cat,
            "old_code": old_code,
            "old_desc": old_desc,
            "new_code": best_code,
            "new_desc": new_desc,
            "score": round(best_score, 2),
            "runner_up_score": round(runner_up, 2),
            "rft_verdict": verdict,
            "rft_fndds_desc": rft_fndds,
            "rft_sr28_desc": rft_sr28,
            "signals": json.dumps(best_signals),
            "cluster": prod_cluster,
            "old_cohort_majority": cur_meta["majority_category"] if cur_meta else "",
            "old_cohort_size": cur_meta["cohort_size"] if cur_meta else 0,
        })
        n_rerouted += 1

    print(
        f"[{time.strftime('%H:%M:%S')}] decisions:\n"
        f"   category_ok                 : {n_category_ok:,}\n"
        f"   needs_reroute (mismatched)  : {n_needs_reroute:,}\n"
        f"     -> rerouted               : {n_rerouted:,}\n"
        f"     -> new_leaf_proposed      : {n_new_leaf:,}\n"
        f"   protected (skipped)         : {n_protected:,}\n"
    )

    # Write outputs
    print(f"[{time.strftime('%H:%M:%S')}] writing outputs...")
    with open(TMP_OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=header)
        w.writeheader()
        for row in rows:
            w.writerow(row)
    os.replace(TMP_OUT, VID)
    print(f"  rewrote {VID}")

    with open(CHANGELOG, "w", newline="", encoding="utf-8") as f:
        if changelog_rows:
            w = csv.DictWriter(f, fieldnames=list(changelog_rows[0].keys()))
            w.writeheader()
            for r in changelog_rows:
                w.writerow(r)
        else:
            f.write("(no changes)\n")
    print(f"  wrote {CHANGELOG} ({len(changelog_rows)} rows)")

    with open(NEW_LEAVES, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "fdc_id", "product_description", "branded_food_category",
            "current_code", "current_desc", "rft_verdict", "reason",
            "top1_code", "top1_desc", "top1_score",
            "top2_code", "top2_desc", "top2_score",
            "top3_code", "top3_desc", "top3_score",
        ])
        for row, top3, reason in new_leaf_rows:
            cells = [
                row.get("fdc_id", ""),
                row.get("product_description", ""),
                row.get("branded_food_category", ""),
                row.get("best_esha_code", ""),
                row.get("best_esha_description", ""),
                row.get("rft_verdict", ""),
                reason,
            ]
            for i in range(3):
                if i < len(top3):
                    code, score, _sig = top3[i]
                    cells.extend([code, code2desc.get(code, ""), score])
                else:
                    cells.extend(["", "", ""])
            w.writerow(cells)
    print(f"  wrote {NEW_LEAVES} ({len(new_leaf_rows)} rows)")

    print(f"[{time.strftime('%H:%M:%S')}] done in {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
