#!/usr/bin/env python3
"""Direct recipe-ingredient → SR-28 fdc_id mapper.

The HTC→SR aggregation in htc_gram_weights.csv is too lossy for nutrient
calculation (one HTC pools many SR codes from retail rows; "saffron threads"
ends up backed by an unrelated SR like garlic). For nutrient calc we need
ingredient-level SR-28 codes.

This builds a per-ingredient map: item → fdc_id + sr_description + score,
using token-overlap scoring against the SR-28 sr_legacy_food descriptions.

Output: ingredient_to_sr28.csv
"""
from __future__ import annotations

import csv
import re
import sys
from collections import Counter
from pathlib import Path

csv.field_size_limit(sys.maxsize)

ROOT = Path(__file__).resolve().parents[2]
SR28 = ROOT / "data" / "sr28_csv"
HERE = Path(__file__).resolve().parent
DEFAULT_TAGS = HERE / "output" / "recipe_ingredient_htc_tagged.csv"
OUT = HERE / "output" / "ingredient_to_sr28.csv"

WS = re.compile(r"\s+")
NONALPHA = re.compile(r"[^a-z0-9 ]+")
STOPWORDS = {
    "fresh", "frozen", "dried", "canned", "raw", "cooked", "ground",
    "chopped", "diced", "minced", "sliced", "cubed", "whole", "large",
    "medium", "small", "extra", "pure", "natural", "organic",
    "the", "a", "an", "or", "of", "in", "to", "with", "and", "for",
    "powder", "dry", "ripe", "boneless", "skinless",
    "leaves", "leaf", "seeds", "seed", "stick", "sticks",
    "package", "pkg", "container", "all", "purpose",
    "added", "without", "with",
    "homemade", "store.bought", "low", "fat", "free",
    "recipe", "use", "as", "needed",
}


def tokens(s: str) -> set[str]:
    s = (s or "").lower()
    s = NONALPHA.sub(" ", s)
    out = {t for t in WS.split(s) if len(t) >= 2 and t not in STOPWORDS}
    return out


def core_tokens(s: str) -> set[str]:
    """Like tokens() but includes form/prep words too — for query side."""
    s = (s or "").lower()
    s = NONALPHA.sub(" ", s)
    return {t for t in WS.split(s) if len(t) >= 2}


# Foods we know are common simple ingredients — when they're the query head,
# strongly prefer the canonical SR row.
CANONICAL_OVERRIDES: dict[str, str] = {
    "all-purpose flour": "20081",   # Wheat flour, white, all-purpose, enriched, bleached
    "all purpose flour": "20081",
    "ap flour": "20081",
    "flour": "20081",                # bare "flour" → wheat AP (most common recipe meaning)
    "white flour": "20081",
    "plain flour": "20081",
    "bread flour": "20082",          # Wheat flour, white, bread, enriched
    "cake flour": "20083",           # Wheat flour, white, cake, enriched
    "whole wheat flour": "20080",
    "baking powder": "18371",        # Leavening agents, baking powder
    "baking soda": "18372",          # Leavening agents, baking soda
    "yeast": "18375",                # Leavening agents, yeast, baker's, active dry
    "egg whites": "1124",            # Egg, white, raw, fresh
    "egg yolks": "1125",             # Egg, yolk, raw, fresh
    "ground cinnamon": "2010",       # Spices, cinnamon, ground
    "cinnamon": "2010",
    "ground nutmeg": "2025",         # Spices, nutmeg, ground
    "nutmeg": "2025",
    "ground ginger": "2021",         # Spices, ginger, ground
    "ground black pepper": "2030",   # Spices, pepper, black
    "black pepper": "2030",
    "ground turmeric": "2043",       # Spices, turmeric, ground
    "ice cube": "14411",             # Water, tap, drinking (use water for ice)
    "ice cubes": "14411",
    "ice": "14411",
    "fresh water": "14411",
    "water": "14411",
    # Chicken — verified from sr_legacy_food.csv 2026-05-04
    "boneless skinless chicken breasts": "5062",   # Chicken, broiler, breast, skinless, boneless, meat only, raw
    "boneless skinless chicken breast": "5062",
    "skinless chicken breast": "5062",
    "boneless skinless chicken thighs": "5096",    # Chicken, broilers or fryers, dark meat, thigh, meat only, raw  ✓
    "boneless skinless chicken thigh": "5096",
    "skinless chicken thigh": "5096",
    "chicken thighs": "5095",        # Chicken, broilers or fryers, thigh, meat and skin, raw
    "chicken thigh": "5095",
    "chicken breast": "5061",        # Chicken, broilers or fryers, breast, meat and skin, raw
    "boneless chicken breast": "5062",
    "rotisserie chicken": "5293",    # Turkey breast, pre-basted, meat and skin, cooked, roasted (closest analog)
    "shredded chicken": "5062",
    "ground chicken": "5331",        # Chicken, ground, raw
    "ground chicken breast": "5662",  # Turkey-equivalent — SR doesn't have ground chicken breast specifically
    "chicken wings": "5126",         # Chicken, broilers or fryers, wing, meat and skin, raw
    "chicken drumstick": "5018",     # Chicken, broilers or fryers, drumstick, meat and skin, raw
    "chicken drumsticks": "5018",
    "granulated sugar": "19335",     # Sugars, granulated
    "white sugar": "19335",
    "sugar": "19335",
    "brown sugar": "19334",
    "powdered sugar": "19336",
    "confectioners sugar": "19336",
    "olive oil": "4053",             # Oil, olive, salad or cooking
    "extra virgin olive oil": "4053",
    "vegetable oil": "4669",         # Oil, vegetable, soybean, refined
    "canola oil": "4582",
    "butter": "1001",                # Butter, salted
    "salted butter": "1001",
    "unsalted butter": "1145",       # Butter, without salt
    "whole milk": "1077",            # Milk, whole, 3.25% milkfat, with added vitamin D
    "milk": "1077",
    "skim milk": "1085",             # Milk, nonfat, fluid, with added vitamin A and vitamin D
    "2% milk": "1079",
    "salt": "2047",                  # Salt, table
    "kosher salt": "2047",
    "sea salt": "2047",
    "table salt": "2047",
    "honey": "19296",
    "vanilla extract": "2050",       # Vanilla extract
    "lemon juice": "9152",           # Lemon juice, raw
    "fresh lemon juice": "9152",
    "lime juice": "9160",
    "fresh lime juice": "9160",
    # Citrus peel / zest — distinct from juice (oil-rich rind, different SR row)
    "lemon zest": "9156",            # Lemon peel, raw   (verified)
    "lemon peel": "9156",
    "grated lemon peel": "9156",
    "fresh lemon zest": "9156",
    "lime zest": "9156",             # SR-28 has no lime peel — closest is lemon peel (citrus oil)
    "lime peel": "9156",
    "orange zest": "9216",           # Orange peel, raw   (verified)
    "orange peel": "9216",
    "grated orange peel": "9216",
    "grapefruit zest": "9216",       # SR-28 grapefruit peel not present; orange peel close
    "grapefruit peel": "9216",
    "garlic": "11215",               # Garlic, raw
    "garlic cloves": "11215",
    "onion": "11282",                # Onions, raw
    "onions": "11282",
    "yellow onion": "11282",
    "red onion": "11282",
    "white onion": "11282",
    "tomato": "11529",               # Tomatoes, red, ripe, raw, year round average
    "tomatoes": "11529",
    "diced tomatoes": "11529",
    "carrot": "11124",
    "carrots": "11124",
    "celery": "11143",
    "blueberries": "9050",           # Blueberries, raw
    "fresh blueberries": "9050",
    "strawberries": "9316",
    "fresh strawberries": "9316",
    "bananas": "9040",
    "ripe bananas": "9040",
    "applesauce": "9019",            # Applesauce, canned, unsweetened, without added vitamin C
    "eggs": "1123",                  # Egg, whole, raw, fresh
    "egg": "1123",
    "large eggs": "1123",
    "vanilla yogurt": "1119",        # Yogurt, vanilla, low fat  ✓
    "low fat vanilla yogurt": "1119",
    "non-fat vanilla yogurt": "1295",  # Yogurt, vanilla, non-fat
    "plain yogurt": "1117",          # Yogurt, plain, low fat  ✓
    "plain low fat yogurt": "1117",
    "plain whole milk yogurt": "1116",  # Yogurt, plain, whole milk
    "whole milk yogurt": "1116",
    "plain greek yogurt": "1287",    # Yogurt, Greek, plain, lowfat
    "greek yogurt": "1287",
    "vanilla greek yogurt": "1297",  # Yogurt, Greek, vanilla, lowfat
    "non-fat greek yogurt": "1256",  # Yogurt, Greek, plain, nonfat
    "saffron threads": "2037",       # Spices, saffron
    "ground cardamom": "2006",       # Spices, cardamom
    "cardamom": "2006",
    "cardamom seeds": "2006",
    "ground cloves": "2011",         # Spices, cloves, ground
    "ground mace": "2013",           # Spices, mace
    "mace": "2013",
    "ground cumin": "2014",
    "cumin seeds": "2014",
    "coriander seeds": "2013",       # Spices, coriander seed (NDB 2013)
    "ground coriander": "2013",
    "ground allspice": "2001",
    "paprika": "2028",
    "smoked paprika": "2028",
    "peppercorns": "2030",
    "whole peppercorns": "2030",
    "poppy seeds": "2033",
    "fennel seeds": "2017",
    "rice": "20444",                 # Rice, white, long-grain, regular, raw, enriched
    "white rice": "20444",
    "basmati rice": "20444",
    "jasmine rice": "20444",
    "brown rice": "20036",
    "ground beef": "23572",          # Beef, ground, 80% lean meat / 20% fat, raw
    "lean ground beef": "23574",     # 90/10
    "extra lean ground beef": "23576",  # 95/5
    "soy sauce": "16123",            # Soy sauce made from soy and wheat (shoyu)
    "fresh parsley": "11297",        # Parsley, fresh
    "parsley": "11297",
    "fresh cilantro": "11165",       # Coriander (cilantro) leaves, raw
    "cilantro": "11165",
    "fresh mint": "2064",            # Spices, peppermint, fresh
    "mint": "2064",
    "ghee": "1323",                  # Butter, Clarified butter (ghee)  ✓
    "clarified butter": "1323",
    # ── HIGH-IMPACT GAP CLOSERS (recipes-per-item shown in comments) ──
    "ketchup": "11935",              # Catsup
    "catsup": "11935",
    "tomato ketchup": "11935",
    "buttermilk": "1088",            # Milk, buttermilk, fluid, cultured, lowfat
    "low fat buttermilk": "1088",
    "onion powder": "2026",          # Spices, onion powder
    "garlic powder": "2020",         # Spices, garlic powder
    "breadcrumbs": "18079",          # Bread crumbs, dry, grated, plain
    "bread crumbs": "18079",
    "dry breadcrumbs": "18079",
    "panko": "18079",
    "panko breadcrumbs": "18079",
    "italian breadcrumbs": "18079",
    "fresh breadcrumbs": "18079",
    "shallot": "11677",              # Shallots, raw
    "shallots": "11677",
    "rolled oats": "8121",           # Oats (raw rolled oats)
    "old fashioned oats": "8121",
    "quick oats": "8121",
    "instant oats": "8121",
    "scallion": "11291",             # Onions, spring or scallions, raw (includes tops)
    "scallions": "11291",
    "green onion": "11291",
    "green onions": "11291",
    "cinnamon stick": "2010",        # Spices, cinnamon, ground (same nutrient profile)
    "cinnamon sticks": "2010",
    "jalapeño": "11978",             # Peppers, jalapeño, raw
    "jalapenos": "11978",
    "jalapeno": "11978",
    "fresh jalapeños": "11978",
    "leek": "11246",                 # Leeks, (bulb and lower leaf-portion), raw
    "leeks": "11246",
    "prosciutto": "7969",            # Pork, cured, ham, prosciutto
    "crabmeat": "15139",             # Crustaceans, crab, blue, raw
    "lump crabmeat": "15139",
    "crab meat": "15139",
    "linguine": "20120",             # Pasta, dry, unenriched
    "fettuccine": "20120",
    "spaghetti": "20120",
    "macaroni": "20121",             # Macaroni, dry, enriched
    "penne": "20121",
    "rigatoni": "20121",
    "rotini": "20121",
    "elbow macaroni": "20121",
    "egg noodles": "20109",          # Noodles, egg, dry, enriched
    "noodles": "20109",
    "cornflour": "20020",            # Cornmeal, whole-grain, yellow (closest to UK cornflour)
    "corn flour": "20020",
    "cornstarch": "20027",           # Cornstarch
    "garam masala": "2003",          # Spices, basil, dried (closest analog; SR has no garam masala)
    "cool whip": "1180",             # Whipped topping, frozen, low fat
    "whipped topping": "1180",
    "frozen whipped topping": "1180",
    "extracts and flavorings": "2050",
    # alcohol — recipes commonly use these
    "vodka": "14554",                # Alcoholic beverage, distilled, all (gin, rum, vodka, whiskey)
    "rum": "14554",
    "dark rum": "14554",
    "light rum": "14554",
    "white rum": "14554",
    "bourbon": "14554",
    "whiskey": "14554",
    "whisky": "14554",
    "scotch": "14554",
    "gin": "14554",
    "tequila": "14554",
    "brandy": "14037",               # Alcoholic beverage, wine, table (closest for cooking brandy)
    "cognac": "14554",
    "dry sherry": "14096",           # Alcoholic beverage, wine, dessert, dry
    "sherry": "14096",
    "marsala": "14096",
    "dry vermouth": "14037",
    "red wine": "14096",
    "white wine": "14096",
    "dry white wine": "14096",
    "dry red wine": "14096",
    "cooking wine": "14096",
    "mirin": "14555",                # Alcoholic beverage, distilled, sake (closest for mirin)
    "sake": "14555",
    "beer": "14003",                 # Alcoholic beverage, beer, regular
    # mint
    "mint leaves": "2064",
    "fresh mint leaves": "2064",
    "fresh sage": "2038",            # Spices, sage, ground (no fresh sage in SR)
    "sage leaves": "2038",
    # buns + bread variants
    "hamburger buns": "18351",       # Rolls, hamburger or hot dog, plain
    "hot dog buns": "18351",
    "hot dog rolls": "18351",
    "kaiser rolls": "18350",
    "dinner rolls": "18352",
    "bread rolls": "18352",
    "english muffins": "18348",      # English muffins, plain, enriched
    "tortillas": "18361",            # Tortillas, ready-to-bake or -fry, flour
    "corn tortillas": "18364",       # Tortillas, ready-to-bake or -fry, corn
    "flour tortillas": "18361",
    # additional staples
    "lemon zest": "9156",            # already exists but reinforce
    "extra virgin olive oil": "4053",
    "evoo": "4053",
    "coconut oil": "4047",           # Oil, coconut
    "sesame oil": "4058",            # Oil, sesame, salad or cooking
    "canola oil": "4582",            # Oil, canola
    "peanut oil": "4042",            # Oil, peanut, salad or cooking
    "avocado oil": "4584",           # Oil, avocado
    "sunflower oil": "4506",         # Oil, sunflower, linoleic, (~65%)
    "safflower oil": "4511",         # Oil, safflower, salad or cooking, high oleic
    "grape seed oil": "4517",        # Oil, grapeseed
    "grapeseed oil": "4517",
    # Fresh vs dried herbs — SEPARATE SR entries, vastly different gram density
    "dried parsley": "2029",         # Spices, parsley, dried
    "parsley flakes": "2029",
    "dried basil": "2003",           # Spices, basil, dried
    "dried thyme": "2042",           # Spices, thyme, dried
    "dried oregano": "2027",         # Spices, oregano, dried
    "dried rosemary": "2036",        # Spices, rosemary, dried
    "dried sage": "2038",            # Spices, sage, ground
    "dried tarragon": "2041",        # Spices, tarragon, dried
    "dried marjoram": "2024",        # Spices, marjoram, dried
    "dried mint": "2065",            # Spices, peppermint, dried (or 2064 fresh — separate)
    "dried dill": "2015",            # Spices, dill weed, dried
    "dried chervil": "2008",         # Spices, chervil, dried
    "fresh basil": "172232",
    "fresh thyme": "173470",
    "fresh oregano": "171328",       # actually "Spices, oregano, dried" — fresh oregano not in SR
    "fresh rosemary": "173473",
    "fresh sage": "172232",          # SR doesn't have fresh sage; fall back
    "fresh dill": "169999",          # Dill weed, fresh
    "fresh tarragon": "169998",      # Tarragon, fresh — actually rare; many recipes use dried
    "fresh oregano leaves": "171328",
    # Turkey — verified NDB numbers (sr_legacy_food.csv)
    "turkey": "5165",                # Turkey, whole, meat and skin, raw  ✓
    "whole turkey": "5165",
    "ground turkey": "5305",         # Turkey, Ground, raw  ✓
    "ground turkey breast": "5662",  # Turkey, ground, fat free, raw (closest to lean breast)
    "lean ground turkey": "5665",    # Turkey, ground, 93% lean, 7% fat, raw
    "extra lean ground turkey": "5662",  # Turkey, ground, fat free, raw
    "turkey breast": "5219",         # Turkey, whole, breast, meat only, raw  ✓
    "boneless turkey breast": "5219",
    "turkey breast meat": "5219",
    "deli turkey": "42128",          # Ham, turkey, sliced, extra lean, prepackaged or deli  ✓
    "sliced turkey": "42128",
    "shredded deli turkey": "42128",
    "turkey lunch meat": "42128",
    "smoked turkey": "43391",        # Turkey, light or dark meat, smoked, cooked  ✓
    "smoked turkey breast": "7943",  # Turkey, breast, smoked, lemon pepper flavor, 97% fat-free  ✓
    "smoked turkey wing": "43366",
    "smoked turkey drumstick": "43367",
    "turkey bacon": "7254",          # Bacon, turkey, unprepared (raw)  ✓
    "raw turkey bacon": "7254",
    "cooked turkey bacon": "7973",   # Bacon, turkey, microwaved
    "turkey thighs": "5740",         # Turkey, thigh, from whole bird, meat only, raw  ✓
    "turkey thigh": "5740",
    "turkey legs": "5193",           # Turkey, all classes, leg, meat and skin, raw
    "turkey wings": "5195",
    "roast turkey": "5293",          # Turkey breast, pre-basted, meat and skin, cooked, roasted
    "roasted turkey": "5293",
    # Ham — verified NDB numbers
    "ham": "7029",                   # Ham, sliced, regular (~11% fat)  ✓
    "sliced ham": "7029",
    "deli ham": "7028",              # Ham, sliced, pre-packaged, deli meat (96% fat free)
    "bone-in ham": "10936",          # Pork, cured, ham, shank, bone-in, separable lean and fat, unheated
    "spiral ham": "10893",           # Pork, cured, ham with natural juices, spiral slice, boneless, unheated
    "spiral sliced ham": "10893",
    "honey ham": "7029",             # SR doesn't have honey ham; sliced regular is closest
    "smoked ham": "7977",            # Ham, smoked, extra lean, low sodium
    "country ham": "10182",          # Pork, cured, ham, boneless, extra lean and regular, unheated
    "boneless ham": "10182",
    "whole ham": "10009",            # Pork, fresh, leg (ham), whole, separable lean and fat, cooked, roasted
    "ham hock": "10017",             # Pork, fresh, leg (ham), shank half, separable lean and fat, cooked, roasted
    # Ginger / cinnamon — make sure ground variants stay in spices
    "ginger": "11216",               # Ginger root, raw — for fresh ginger
    "fresh ginger": "11216",
    "fresh gingerroot": "11216",
    "gingerroot": "11216",           # SR has it as ginger root
}


def main() -> int:
    print("loading SR-28 sr_legacy_food descriptions...")
    sr_rows: list[dict] = []
    ndb_to_fdc: dict[str, str] = {}
    with (SR28 / "sr_legacy_food.csv").open() as f:
        for row in csv.DictReader(f):
            ndb_to_fdc[row["NDB_number"]] = row["fdc_id"]
    with (SR28 / "food.csv").open() as f:
        for row in csv.DictReader(f):
            if row.get("data_type") == "sr_legacy_food":
                sr_rows.append({
                    "fdc_id": row["fdc_id"],
                    "description": row.get("description", ""),
                    "tokens": tokens(row.get("description", "")),
                    "first_word": (row.get("description", "") or "").split(",")[0].strip().lower(),
                    "n_tokens": len(tokens(row.get("description", ""))),
                })
    print(f"  {len(sr_rows):,} SR-28 entries  ({len(ndb_to_fdc):,} ndb→fdc)")
    fdc_lookup = {r["fdc_id"]: r for r in sr_rows}

    # Build a head-word index for fast first-pass filtering.
    by_head: dict[str, list[dict]] = {}
    for r in sr_rows:
        for tok in tokens(r["first_word"]):
            by_head.setdefault(tok, []).append(r)

    print(f"loading ingredient tags from {DEFAULT_TAGS.name}...")
    items: list[tuple[str, int]] = []
    with DEFAULT_TAGS.open() as f:
        for row in csv.DictReader(f):
            try:
                rc = int(row["recipe_count"])
            except ValueError:
                rc = 0
            items.append((row["item"], rc))
    print(f"  {len(items):,} unique items")

    print("matching each ingredient to best SR-28 entry...")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    matched = 0
    no_match = 0
    overrides_used = 0
    with OUT.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["item", "recipe_count", "fdc_id", "sr_description", "score"])
        for item, rc in items:
            item_lc = item.lower().strip()
            # Hard-coded overrides for the staples — by far the most accurate path
            override_ndb = CANONICAL_OVERRIDES.get(item_lc)
            if override_ndb and override_ndb in ndb_to_fdc:
                fdc = ndb_to_fdc[override_ndb]
                rec = fdc_lookup.get(fdc)
                if rec:
                    overrides_used += 1
                    matched += 1
                    w.writerow([item, rc, fdc, rec["description"], "OVERRIDE"])
                    continue

            it_tokens = tokens(item)
            it_core = core_tokens(item)
            if not it_tokens:
                w.writerow([item, rc, "", "", 0])
                no_match += 1
                continue
            # candidate pool: all SR rows whose first_word head shares a token
            # with the ingredient (otherwise we'd score against 7,793 every time)
            pool: dict[str, dict] = {}
            for tok in it_tokens:
                for r in by_head.get(tok, []):
                    pool[r["fdc_id"]] = r
            if not pool:
                pool = {r["fdc_id"]: r for r in sr_rows}
            best = None
            best_score = -1.0
            for r in pool.values():
                inter = it_tokens & r["tokens"]
                if not inter:
                    continue
                # Strong signal: first-word match
                first_match = 1.5 if r["first_word"] in it_tokens else 0.0
                # Penalize SR descriptions whose first word isn't in the query
                # (e.g., "Cinnamon buns" when query is "ground cinnamon")
                first_word_extra_penalty = 0.0
                if r["first_word"] and r["first_word"] not in it_core:
                    first_word_extra_penalty = 1.5
                # Raw/fresh bonus, BUT honor explicit form qualifiers in the query.
                desc_lc = r["description"].lower()
                q_dried = "dried" in item_lc or "ground" in item_lc
                q_fresh = "fresh" in item_lc or "raw" in item_lc
                desc_dried = "dried" in desc_lc or "ground" in desc_lc or "powder" in desc_lc
                desc_fresh = "fresh" in desc_lc or ", raw" in desc_lc
                # If query says dried, prefer dried SR; if query says fresh, prefer fresh.
                # If neither qualifier, lightly prefer raw/fresh (recipe default).
                form_bonus = 0.0
                if q_dried and desc_dried:
                    form_bonus += 1.5
                elif q_dried and desc_fresh:
                    form_bonus -= 1.5      # explicit form mismatch — hard penalty
                elif q_fresh and desc_fresh:
                    form_bonus += 1.5
                elif q_fresh and desc_dried:
                    form_bonus -= 1.5
                elif desc_fresh:
                    form_bonus += 0.4      # default: prefer raw/fresh
                # Penalize compound-product descriptions when query is simple
                compound_penalty = 0.0
                bad_words = ("buns", "bread", "cake", "muffin", "cookie", "frosted",
                             "chocolate", "coated", "fried", "breaded", "stuffed",
                             "filled", "ice creams", "baking chocolate", "sandwich",
                             "salad", "pizza", "soup", "shake", "smoothie")
                for bw in bad_words:
                    if bw in desc_lc and bw not in item_lc:
                        compound_penalty += 1.0
                # Short SR descriptions preferred (3-token desc beats 8-token)
                length_penalty = 0.10 * max(0, r["n_tokens"] - len(it_tokens))
                score = (len(inter)
                         + first_match
                         + form_bonus
                         - first_word_extra_penalty
                         - compound_penalty
                         - length_penalty)
                if score > best_score:
                    best_score = score
                    best = r
            if best and best_score > -1:
                matched += 1
                w.writerow([item, rc, best["fdc_id"], best["description"], f"{best_score:.2f}"])
            else:
                no_match += 1
                w.writerow([item, rc, "", "", 0])

    print(f"  matched: {matched:,}  no_match: {no_match:,}  overrides_used: {overrides_used:,}")
    print(f"  -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
