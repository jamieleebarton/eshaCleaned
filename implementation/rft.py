"""
Retail Food Taxonomy (RFT) — v2.

Pipeline
========
Stage 1 (already done in rft_poc.py): produced parsed_unified.csv with rows
    [source, code, head, identity_raw, facets_pipe, full_desc, category]

This script (rft.py) does Stages 2-5:
  Stage 2  Auto-detect CARRIERS  (Dish, Cereal, Soup, ...) from the data
  Stage 3  Re-extract identity heads, walking past carriers
  Stage 4  Cluster LEAVES by (head, key_facets) tuple
            → each leaf has per-source provenance (best SR28 / FNDDS / ESHA)
  Stage 5  ROUTE retail surfaces with full per-source traceability,
            splitting identity tokens from retail attributes

Outputs (under implementation/output/rft_v2/):
  carriers.csv          Auto-detected carrier first-fragments
  leaves.csv            Final taxonomy with per-source codes + scores
  retail_routes.csv     Full traceability per retail surface
  validation_diff.csv   Routes vs canonical_surface ground truth, dressings
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

ROOT = Path("/Users/jamiebarton/Desktop/esha_audit_bundle")
PARSED = ROOT / "implementation" / "output" / "rft_poc" / "parsed_unified.csv"
SURFACE_CLEANED = ROOT / "implementation" / "output" / "canonical_surface_normalized_with_product_proxies_CLEANED.csv"
SURFACE = SURFACE_CLEANED if SURFACE_CLEANED.exists() else ROOT / "implementation" / "output" / "canonical_surface_normalized_with_product_proxies.csv"
OUT = ROOT / "implementation" / "output" / "rft_v2"
OUT.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------

WORD = re.compile(r"[a-z][a-z0-9'%-]*")

PLURAL = {
    "dressings": "dressing", "strips": "strip", "tenders": "tender",
    "nuggets": "nugget", "patties": "patty", "filets": "filet",
    "fillets": "fillet", "breasts": "breast", "thighs": "thigh", "legs": "leg",
    "wings": "wing", "drumsticks": "drumstick", "pieces": "piece",
    "milks": "milk", "creamers": "creamer", "cookies": "cookie",
    "crackers": "cracker", "cakes": "cake", "pies": "pie",
    "soups": "soup", "sauces": "sauce", "cheeses": "cheese", "juices": "juice",
    "jellies": "jelly", "preserves": "preserve", "pickles": "pickle",
    "olives": "olive", "peppers": "pepper", "mushrooms": "mushroom",
    "stems": "stem", "berries": "berry", "tomatoes": "tomato",
    "potatoes": "potato", "onions": "onion", "carrots": "carrot",
    "beans": "bean", "peas": "pea", "nuts": "nut", "seeds": "seed",
    "eggs": "egg", "noodles": "noodle", "rolls": "roll", "buns": "bun",
    "biscuits": "biscuit", "muffins": "muffin", "yogurts": "yogurt",
}

GLOBAL_NOISE = {
    "the", "a", "an", "and", "or", "with", "without", "of", "in", "for",
    "on", "to", "at", "by", "from", "made", "style", "fs", "is", "be",
    "type", "as", "regular", "commercial", "added", "form", "fluid",
    "no", "nos", "nfs", "ns", "us", "purchased", "any", "all",
    "product", "products", "item", "items",
    "use", "ready", "instant", "quick",
}

# Synonyms: variant spellings/names that should be normalized to one form
# during tokenization so leaves and surfaces share vocabulary.
SYNONYMS = {
    "catsup": "ketchup",
    "bleu": "blue",
    "doughnut": "donut",
    "doughnuts": "donuts",
    "yoghurt": "yogurt",
    "yoghurts": "yogurts",
    "cinamon": "cinnamon",
    "cinnanon": "cinnamon",
    "mayo": "mayonnaise",
    "ck": "cake",          # SR28 abbreviation
    "ic": "ice",
    "ice-cream": "icecream",
    "bars": "bar",         # form-word plural; nutrition DBs use both
    "chips": "chip",
    "mac": "macaroni",     # mac n cheese, mac & cheese, mac salad
    "veggie": "vegetable",
    "veggies": "vegetable",
    "veg": "vegetable",
    "choc": "chocolate",
    "choco": "chocolate",
    "pb": "peanut",        # peanut butter, peanut butter cups
    "bbq": "barbecue",
    "barbeque": "barbecue",
    # spelling normalizations from category audits
    "chevre": "goat",
    "calamata": "kalamata",
    # candy/cake spelling normalizations
    "kake": "cake",
    "koffee": "coffee",
    "cupkake": "cupcake",
    "kisses": "kiss",
    "truffles": "truffle",
    # cereal/oatmeal normalizations
    "froot": "fruit",   # froot loops → fruit loops
    "barbeque": "barbecue",  # all 3 forms unify
    "bbq": "barbecue",
    "crisps": "chips",  # britishism
    "crisp": "chip",
    "tarter": "tartar",
    "vinagrette": "vinaigrette",
    "boullion": "bouillon",
    "achiotina": "achiote",
    "peperoncini": "pepperoncini",
    "pimiento": "pimento",
    "mozz": "mozzarella",
    "flavour": "flavor",
    "flavoured": "flavored",
    "lowfat": "low-fat",   # one-word retail form → hyphenated leaf form
    "kraut": "sauerkraut",
    "cremes": "creme",
    "crmes": "creme",
    "crm": "creme",
}

# Phrase aliases: retail surfaces often split compound food words into two
# words ("apple sauce", "egg nog") while the nutrition DB stores them as a
# single token ("applesauce", "eggnog").  Collapsing these BEFORE the word
# regex runs ensures the surface and concept vocabularies align.
# Keys must be lower-case, space-separated, exact whole-word sequences.
PHRASE_ALIASES = {
    "apple sauce": "applesauce",
    "egg nog": "eggnog",
    "cole slaw": "coleslaw",
    "corn starch": "cornstarch",
    "corn bread": "cornbread",
    "cheese cake": "cheesecake",
    "meat loaf": "meatloaf",
    "water melon": "watermelon",
    "marsh mallows": "marshmallows",
    "sauer kraut": "sauerkraut",
    "pine apple": "pineapple",
    "buck wheat": "buckwheat",
    "bread stick": "breadstick",
    # Cheese hyphen/spacing normalizations from category audits — retail
    # surfaces use hyphenated forms; nutrition DB uses space-separated.
    "low-moisture": "low moisture",
    "part-skim": "part skim",
    "partially skim": "part skim",
    "non-fat": "nonfat",
    "low-fat": "lowfat",
    "reduced-fat": "reduced fat",
    "fat-free": "fat free",
    # Pickle/relish compounds — retail variants
    "bread and butter": "bread butter",
    # Cookie compounds — split hyphenated retail forms to match concept space
    "chocolate-chip": "chocolate chip",
    "peanut-butter": "peanut butter",
    # Other normalizations
    "with-out": "without",
    # Snack/popcorn/seed compounds
    "kettle corn": "kettlecorn",
    "kettle-corn": "kettlecorn",
    # Frozen dessert compounds
    "ice-cream": "ice-cream",
    "ice cream": "ice-cream",
    "frozen-yogurt": "frozen-yogurt",
    "frozen yogurt": "frozen-yogurt",
    # Candy compounds
    "salt water taffy": "saltwater taffy",
    # Chocolate bigrams are deliberately NOT aliased here.  The token-set
    # router distinguishes "milk chocolate almonds" (candy) from
    # "almond milk chocolate" (drink) naturally because "almond milk" is
    # aliased to "almond-milk" while "milk chocolate" stays as two tokens.
    # Collapsing chocolate bigrams created a vocabulary split: ESHA retail
    # descriptions have "dark chocolate" contiguous (→ dark-chocolate) while
    # USDA/FNDDS comma-split descriptions have "chocolate, dark" (→ two
    # separate tokens), so surface and concept vocabularies no longer aligned.
    # Keeping them as separate tokens lets both sides match consistently.
    # plant milk compounds (drinks, not flavored milk)
    "almond milk": "almond-milk",
    "oat milk": "oat-milk",
    "soy milk": "soy-milk",
    "rice milk": "rice-milk",
    "coconut milk": "coconut-milk",
    "hemp milk": "hemp-milk",
    "cashew milk": "cashew-milk",
    "pea milk": "pea-milk",
    "macadamia milk": "macadamia-milk",
    "flax milk": "flax-milk",
    # cream compounds — DB mostly stores these as "Cream, X" (comma split),
    # so surface "X cream" already tokenizes to {X, cream} and matches
    # naturally. Only aliases where DB consistently has the bigram form.
    "cream cheese": "cream-cheese",
    # ice cream sub-types: don't collapse — let multi-token match handle
    # `cone`/`sandwich`/`bar` via existing concept tokens.
    # cheese compounds — most DB entries are comma-split too
    # (e.g. "Cheese, cottage, X"), so let multi-token match handle them.
    # nut/seed compounds
    "peanut butter": "peanut-butter",
    "almond butter": "almond-butter",
    "cashew butter": "cashew-butter",
    "sunflower seed": "sunflower-seed",
    "pumpkin seed": "pumpkin-seed",
    # beverage compounds — hot dog stays as bigram (it's always one phrase).
    # hot cocoa / hot chocolate exist as both bigrams and "Milk, hot cocoa"
    # comma-split forms; bare token match handles both.
    "hot dog": "hot-dog",
    # other common compounds where order matters
    "chocolate chip": "chocolate-chip",
    "chocolate chunk": "chocolate-chunk",
    "chocolate covered": "chocolate-covered",
    "yogurt covered": "yogurt-covered",
    "candy covered": "candy-covered",
    # bar compounds — anchor "bar" within the right product class.
    # Without these, "bar" alone defaults to candy-bar/chocolate-bar via
    # FORM_DRIFT and product-line bars (granola, energy, etc.) misroute.
    "granola bar": "granola-bar",
    "energy bar": "energy-bar",
    "snack bar": "snack-bar",
    "protein bar": "protein-bar",
    "fiber bar": "fiber-bar",
    "fruit bar": "fruit-bar",
    "nut bar": "nut-bar",
    "breakfast bar": "breakfast-bar",
    "cereal bar": "cereal-bar",
    "meal bar": "meal-bar",
    "meal replacement bar": "meal-replacement-bar",
    "nutrition bar": "nutrition-bar",
    "rice krispie treat": "rice-krispie-treat",
    "rice krispies treat": "rice-krispie-treat",
    "krispie treat": "krispie-treat",
    # cake compounds — DB stores most as bigrams in description
    "bundt cake": "bundt-cake",
    "pound cake": "pound-cake",
    "loaf cake": "loaf-cake",
    "coffee cake": "coffee-cake",
    "sponge cake": "sponge-cake",
    "snack cake": "snack-cake",
    "layer cake": "layer-cake",
    "sheet cake": "sheet-cake",
    "angel food": "angel-food",
    "devil's food": "devils-food",
    "devils food": "devils-food",
    "red velvet": "red-velvet",
    "yellow cake": "yellow-cake",
    "white cake": "white-cake",
    # donut compounds
    "cake donut": "cake-donut",
    "mini donut": "mini-donut",
    "donut hole": "donut-hole",
    "doughnut hole": "donut-hole",
    "cinnamon roll": "cinnamon-roll",
    "sweet roll": "sweet-roll",
    # cereal compounds
    "raisin bran": "raisin-bran",
    "frosted flakes": "frosted-flakes",
    "rice krispies": "rice-krispies",
    "lucky charms": "lucky-charms",
    "fiber one": "fiber-one",
    "special k": "special-k",
    "froot loops": "froot-loops",
    "fruit loops": "froot-loops",
    "cocoa puffs": "cocoa-puffs",
    "cinnamon toast crunch": "cinnamon-toast-crunch",
    "honey bunches of oats": "honey-bunches-of-oats",
    "cap'n crunch": "capn-crunch",
    "instant oatmeal": "instant-oatmeal",
    "old fashioned oatmeal": "old-fashioned-oatmeal",
    "old-fashioned oatmeal": "old-fashioned-oatmeal",
    "steel cut oats": "steel-cut-oats",
    "steel-cut oats": "steel-cut-oats",
    "rolled oats": "rolled-oats",
    "cream of wheat": "cream-of-wheat",
    # bread compounds
    "english muffin": "english-muffin",
    "hamburger bun": "hamburger-bun",
    "hot dog bun": "hot-dog-bun",
    "dinner roll": "dinner-roll",
    "kaiser roll": "kaiser-roll",
    "hoagie roll": "hoagie-roll",
    "sub roll": "sub-roll",
    "bread crumb": "bread-crumb",
    "bread crumbs": "bread-crumbs",
    "sandwich thin": "sandwich-thin",
    "sandwich thins": "sandwich-thins",
    "whole wheat": "whole-wheat",
    "whole grain": "whole-grain",
    "multi grain": "multi-grain",
    "multi-grain": "multi-grain",
    # soda compounds
    "ginger ale": "ginger-ale",
    "ginger beer": "ginger-beer",
    "root beer": "root-beer",
    "lemon lime": "lemon-lime",
    "lemon-lime": "lemon-lime",
    "diet cola": "diet-cola",
    "diet coke": "diet-coke",
    "club soda": "club-soda",
    "tonic water": "tonic-water",
    "sparkling water": "sparkling-water",
    "cream soda": "cream-soda",
    "dr pepper": "dr-pepper",
    "dr. pepper": "dr-pepper",
    "mountain dew": "mountain-dew",
    "coca-cola": "coca-cola",
    "coca cola": "coca-cola",
    "energy drink": "energy-drink",
    "sports drink": "sports-drink",
    "pink lemonade": "pink-lemonade",
    # chip/pretzel form compounds (preserve form within snack class)
    "potato chip": "potato-chip",
    "tortilla chip": "tortilla-chip",
    "corn chip": "corn-chip",
    "pita chip": "pita-chip",
    "veggie chip": "veggie-chip",
    "kettle chip": "kettle-chip",
    "kettle cooked": "kettle-cooked",
    "kettle-cooked": "kettle-cooked",
    "pretzel rod": "pretzel-rod",
    "pretzel stick": "pretzel-stick",
    "pretzel bite": "pretzel-bite",
    "pretzel twist": "pretzel-twist",
    "pretzel nugget": "pretzel-nugget",
    "pork rind": "pork-rind",
    "pork skin": "pork-rind",
    # snack flavor compounds
    "sea salt": "sea-salt",
    "sour cream and onion": "sour-cream-onion",
    "sour cream & onion": "sour-cream-onion",
    "salt and vinegar": "salt-vinegar",
    "salt & vinegar": "salt-vinegar",
    "dill pickle": "dill-pickle",
    "nacho cheese": "nacho-cheese",
    "flamin hot": "flamin-hot",
    "flamin' hot": "flamin-hot",
    "cracked pepper": "cracked-pepper",
    "french onion": "french-onion",
    "chili lime": "chili-lime",
    "chili cheese": "chili-cheese",
    "honey bbq": "honey-bbq",
    "honey barbecue": "honey-bbq",
    # snack mix compounds
    "party mix": "party-mix",
    "trail mix": "trail-mix",
    # cheese puff compounds
    "cheese puff": "cheese-puff",
    "cheese curl": "cheese-curl",
    "cheese ball": "cheese-ball",
    # yogurt compounds
    "greek yogurt": "greek-yogurt",
    "icelandic yogurt": "icelandic-yogurt",
    "australian yogurt": "australian-yogurt",
    "drinkable yogurt": "drinkable-yogurt",
    "yogurt drink": "yogurt-drink",
    "yogurt parfait": "yogurt-parfait",
    "frozen yogurt bar": "frozen-yogurt-bar",
    # low fat / fat free yogurt: DB stores as comma-split "Yogurt, low fat" —
    # let the multi-token match handle these; don't collapse.
    # SAUCE/DRESSING/MUSTARD/SEASONING/MARINADE compounds REMOVED.
    # The nutrition DB stores most of these as comma-split forms ("Sauce,
    # pasta, marinara" / "Italian dressing, X" but also "Salad dressing,
    # italian"). Aliasing the bigram creates a vocabulary split where
    # surface aliasing fires but concept side has comma-split tokens that
    # don't get collapsed, and the resulting bags don't match.
    # Instead, taxonomy_overrides.csv provides explicit proxy entries for
    # the high-impact compounds (hot sauce, ranch/italian/caesar/french
    # dressing, balsamic vinaigrette, bbq sauce, etc.) so they route via
    # the override mechanism rather than via tokenization.
    # bouillon
    "bouillon cube": "bouillon-cube",
    "chicken bouillon": "chicken-bouillon",
    "beef bouillon": "beef-bouillon",
    # spice/seasoning compounds — these usually appear contiguously in DB
    # descriptions (no comma split) so the alias is safe
    "garam masala": "garam-masala",
    "pumpkin pie spice": "pumpkin-pie-spice",
    "apple pie spice": "apple-pie-spice",
    "cinnamon sugar": "cinnamon-sugar",
    "brown sugar": "brown-sugar",
    "powdered sugar": "powdered-sugar",
    "confectioners sugar": "powdered-sugar",
    "lemon pepper": "lemon-pepper",
    "garlic powder": "garlic-powder",
    "onion powder": "onion-powder",
    "chili powder": "chili-powder",
    "curry powder": "curry-powder",
    "olive oil": "olive-oil",
    "extra virgin": "extra-virgin",
    "miracle whip": "miracle-whip",
}

# Brand-name → canonical-food aliases. The nutrition base doesn't carry
# brand knowledge: when a retail string contains a known brand (in product
# description OR brand_owner/brand_name columns), we *append* the canonical
# food token(s) so routing finds the right leaf.
#
# Examples: "Butter Flavor Crisco" has no nutrition vocabulary token that
# routes to shortening; appending 'shortening' makes it route correctly.
# "Ac'cent Seasoning" similarly needs 'msg, monosodium, glutamate' appended.
#
# Seed list — extend liberally. Keys are matched as case-insensitive
# substrings of (description | brand_owner | brand_name).
BRAND_FOOD_ALIASES = {
    "crisco":     "shortening",
    "accent":     "monosodium glutamate msg",
    "ac'cent":    "monosodium glutamate msg",
    "spam":       "luncheon meat pork canned",
    "twinkie":    "snack cake creme",
    "ho ho":      "snack cake chocolate",
    "ho hos":     "snack cake chocolate",
    "ding dong":  "snack cake chocolate",
    "oreo":       "sandwich cookie",
    "pop-tart":   "toaster pastry",
    "pop tart":   "toaster pastry",
    "cheerios":   "cereal oats toasted ring",
    "doritos":    "tortilla chip",
    "pringles":   "potato chip",
    "fritos":     "corn chip",
    "ritz":       "cracker",
    "saltines":   "cracker saltine",
    "graham":     "cracker graham",
    "tootsie":    "candy chocolate roll",
    "kit kat":    "candy chocolate wafer",
    "snickers":   "candy chocolate peanut",
    "m&m":        "candy chocolate",
    "skittles":   "candy fruit",
    "starburst":  "candy fruit chew",
    "twizzlers":  "candy licorice",
    "kool-aid":   "drink fruit flavored",
    "kool aid":   "drink fruit flavored",
    "gatorade":   "sports drink",
    "powerade":   "sports drink",
    "red bull":   "energy drink",
    "v8":         "vegetable juice",
    "ovaltine":   "drink mix chocolate malt",
    "nesquik":    "drink mix chocolate",
    "tang":       "drink mix orange",
}

# Retail attributes — TRACKED for display/search, but NOT used for routing
# unless they appear in nutrition leaf descriptions. We keep them in routing
# tokens too (so frozen/dried etc. discriminate when relevant); they're
# additionally surfaced as retail_attrs metadata for downstream search.
#
# Words that NEVER affect nutrition routing (pure marketing/branding/form
# without nutritional impact). Stripped from BOTH heads and routing tokens.
RETAIL_ATTRS_NONROUTING = {
    "organic", "natural", "naturally", "original",
    "premium", "select", "gourmet", "imported", "domestic",
    "kosher", "vegan", "vegetarian", "gluten-free",
    "homemade", "home-made", "store-bought",
    "baby", "young", "mature",  # AGENTS.md: weak modifiers, not identity
    "small", "large", "medium",
    # Form-suffix words — describe shape/anatomy, do not change nutrition.
    # "arugula leaves" should route like "arugula" — `leaves` is the part
    # used, not a discriminator.
    #
    # NOTE: Words removed from this list because they form compound food
    # names: root (root beer ≠ beer), head (head cheese ≠ cheese),
    # shoot (bamboo shoots is a food). Those stay in routing tokens.
    "leaf", "leaves",
    "sprout", "sprouts",
    "floret", "florets",
    "kernel", "kernels",
    "tip", "tips",
    "curl", "curls",
    "cut", "cuts",
    "spear", "spears",
    "bunch", "bunches",
    "stalk", "stalks",
    "clove", "cloves",
    "bulb", "bulbs",
    "blossom", "blossoms", "flower", "flowers",
    "piece", "pieces", "stem", "stems", "halves", "halved",
    "quartered", "quarters",
    # Prep cuts — same nutrition regardless of how it's cut.
    "sliced", "diced", "chopped", "shredded", "minced", "cubed",
}

# Words that ARE nutrition-relevant (state/processing changes calories,
# water, sodium, etc.). Kept in routing tokens AND in leaf vocab.
# Note: prep-only cuts (sliced/diced/chopped/shredded/minced) were moved
# to RETAIL_ATTRS_NONROUTING — a diced ham steak has the same nutrition
# as a whole ham steak; these are presentation, not nutrition state.
RETAIL_ATTRS_ROUTING = {
    "frozen", "fresh", "dried", "raw", "canned", "jarred", "bottled",
    "whole",
    "fillet", "fillets", "filet", "filets",  # cut style — sometimes nutrition
}

# Union — for display/metadata purposes.
RETAIL_ATTRS = RETAIL_ATTRS_NONROUTING | RETAIL_ATTRS_ROUTING

# Core food-category heads that must NEVER be demoted to carriers, regardless
# of what auto-detection says. These words are themselves the identity in
# retail context. (Carrier semantics in nutrition DB: "<category>, <identity>".)
# Form words — describe SHAPE/FORM, not identity. Treat these as facets when
# they appear inside leaf descriptions, but DO NOT let the carrier walker
# skip past them. "Frozen dessert bar, mango" → head=bar (form), key_facets
# include mango. NOT head=mango via carrier-walk.
FORM_WORDS = {
    "bar", "stick", "cube", "ball", "chunk", "patty", "slice",
    "fillet", "filet", "roll", "log", "wedge", "ring", "round",
    "loaf", "crumble", "chip", "shred", "powder", "flake",
}

# Modifier tokens — describe state/processing, NEVER an identity head.
# Surface routing: never pick these as the head; they remain in routing tokens
# (and thus discriminate leaves) but they don't claim to be the food itself.
# Leaf build: never used as the leaf's head (carrier-walk past them too).
MODIFIER_TOKENS = {
    # state / processing
    "boneless", "skinless", "shelled", "unshelled",
    "lightly", "heavily", "mildly", "extra", "super",
    "sweetened", "unsweetened", "salted", "unsalted",
    "enriched", "fortified", "refined", "unrefined",
    "breaded", "battered", "coated",
    "fried", "deep-fried", "pan-fried",
    "grilled", "broiled", "baked", "roasted", "smoked",
    "steamed", "boiled", "poached", "sauteed",
    # fat / sodium / sugar levels
    "low-moisture", "part-skim", "skim", "whole-milk",
    "lowfat", "low-fat", "nonfat", "non-fat", "fat-free", "reduced-fat",
    "low-sodium", "no-sodium", "reduced-sodium",
    "sugar-free", "no-sugar-added", "no-sugar",
    # cure / brine
    "uncured", "cured",
    # quality / grade — not identity
    "grade", "premium", "select", "choice", "prime",
    # numeric prefixes
    "100%",
    # generic descriptors that show up in nutrition first-fragments but
    # aren't real identities
    "concentrate", "covered",
}

# Units — measurement words that creep into retail strings. Never heads.
UNITS = {
    "ct", "oz", "g", "kg", "lb", "lbs", "mg", "ml", "l", "fl",
    "pkg", "pcs", "qty", "pack", "count", "ea",
    "ozs", "kcal", "cal",
}

# Surface-only modifier words: valid leaf heads in nutrition descriptions
# (e.g. "Fat, bacon grease" has head=fat) but NEVER the right head for a
# retail string. "Reduced fat bacon" → head should be bacon, not fat.
# Used only by parse_surface; extract_head_and_facets still allows them.
SURFACE_MODIFIERS = {
    "fat", "grease",
    "calorie", "calories",
    "protein",
    "fiber",
    "sodium",
    "sugar",          # "no sugar added cookies" → head=cookie, not sugar
    "carb", "carbs",
    "starch",
    "ingredient", "ingredients",
    "flavor", "flavored", "flavoring",
    "blend", "blended",
    "mix",            # "trail mix" stays via parent-child; "cake mix" → cake
    "selection",
    "variety",
    "assortment", "assorted",
    "size", "sized",
    "free",           # "fat free", "sugar free" — modifier in retail
}

# Hand-curated carriers — words that act as a category prefix in nutrition
# descriptions and should be skipped when extracting the identity head.
# Auto-detection was over-aggressive (it ate `applesauce`, `chips`, `crust`,
# `pie`, `base`); we replace it with this small curated whitelist.
CURATED_CARRIERS = {
    "babyfood", "lunchmeat", "dish", "base", "topping",
    "meal", "side", "entree",
    # Restaurant-prefix pseudo-carriers ("Applebee's, X" → real food X)
    "denny's", "applebee's", "ihop", "kfc", "subway",
    "wendy's", "mcdonald's", "starbucks", "pizza-hut",
    # Food-brand prefixes — ESHA/SR28/FNDDS store entries like
    # "Pillsbury, Cinnamon Rolls". Walk past them so leaf heads become real
    # food categories. ONLY include brand tokens that are NOT food words —
    # multi-word brands ("general mills", "lean cuisine", "swiss miss",
    # "trader joe's") are handled by the brand registry / phrase strip
    # because their individual tokens conflict with food vocabulary.
    "pillsbury", "kraft", "heinz", "nabisco", "hostess",
    "kellogg's", "kelloggs",
    "nestle", "nestlé",
    "hershey's", "hersheys",
    "skippy", "jif",
    "smucker's", "smuckers",
    "progresso", "tropicana",
    "pepperidge", "annie's", "annies",
    "sun-maid", "sunmaid",
    "mott's", "motts",
    "chiquita", "dole", "ortega",
    "mahatma", "barilla", "ronzoni",
    "prego", "ragu",
    "planters",
    "klondike", "haagen-dazs", "haagendazs",
    "dreyer's", "dreyers", "edy's", "edys",
    "philadelphia",  # cream cheese brand specifically
    "dannon", "yoplait", "chobani", "fage",
    "horizon",
    "silk",          # plant milk brand
    "califia", "ripple",
    "amy's", "amys",
    "morningstar", "gardenburger", "lightlife", "tofurky",
    "swanson", "stouffer's", "stouffers",
    "conagra",
    "perdue", "hormel",
    "tyson",
    "frito-lay",
    "kraft-heinz",
    "lipton", "tetley",
    "ovaltine",
    "doritos", "pringles", "fritos", "ritz",
    "twinkies", "twinkie",
    "oreo", "oreos",
    "snickers",
    "skittles",
    "starburst",
    "twizzlers",
    "kit-kat", "kitkat",
    "tootsie",
    "powerade", "gatorade",
    "ovaltine", "nesquik",
    "kombucha",  # not a brand but a generic that doesn't have leaves
}

PROTECTED_HEADS = {
    "soup", "stew", "broth",
    "dressing", "sauce", "gravy", "salsa", "marinade",
    "jelly", "jam", "preserve", "marmalade",
    "butter", "spread", "cream", "syrup", "vinegar", "oil",
    "milk", "yogurt", "cheese", "ice", "yoghurt",
    "bread", "cake", "cookie", "cracker", "muffin", "bun", "roll",
    "juice", "tea", "coffee", "soda", "beer", "wine",
    "chicken", "beef", "pork", "turkey", "lamb", "fish", "salmon",
    "egg", "rice", "pasta", "noodle", "cereal",
}


def _singular(t: str) -> str:
    return PLURAL.get(t, t)


def _normalize(t: str) -> str:
    """Apply synonym normalization, then plural reduction."""
    t = SYNONYMS.get(t, t)
    return PLURAL.get(t, t)


def _strip_diacritics(s: str) -> str:
    """jalapeño → jalapeno, café → cafe, doña → dona, etc."""
    import unicodedata
    return "".join(
        c for c in unicodedata.normalize("NFKD", s)
        if not unicodedata.combining(c)
    )


_PHRASE_ALIASES_SORTED = sorted(PHRASE_ALIASES.items(),
                                  key=lambda kv: -len(kv[0]))
_PHRASE_PATTERN = re.compile(
    "|".join(re.escape(p) for p, _ in _PHRASE_ALIASES_SORTED)
)


def _collapse_phrases(s: str) -> str:
    """Replace known multi-word phrases with their canonical single token.
    Runs before the word regex so "apple sauce" becomes "applesauce".

    Single regex pass with longest-first alternation: at any character
    position, the longest matching phrase wins, and the regex engine then
    advances past the match. This prevents overlap bugs like "almond milk
    chocolate" cascading from "almond-milk chocolate" → "almond-milk-chocolate"
    via a substring re-match across the hyphen.
    """
    s = s.lower()
    return _PHRASE_PATTERN.sub(lambda m: PHRASE_ALIASES[m.group(0)], s)


def tokens(s: str) -> list[str]:
    return [_normalize(t) for t in WORD.findall(_strip_diacritics(_collapse_phrases(s)))]


# ---------------------------------------------------------------------------
# Stage 1 reader
# ---------------------------------------------------------------------------

@dataclass
class Row:
    source: str
    code: str
    first_frag: str
    facets: list[str]
    full_desc: str


def build_auto_plurals(rows: list["Row"]) -> dict[str, str]:
    """Discover plural→singular mappings from observed nutrition vocabulary.

    For every singular word in any leaf description, register common plural
    forms (X+s, X+es, Xy→Xies, Xf→Xves) as plural-of-X. We register even
    when the plural is also in vocab — both 'tortilla' and 'tortillas' will
    appear in the data, and we want them collapsed to the singular form.

    Risk of false positives is low for food vocabulary (e.g. 'press' and
    'pres' aren't both real food words).
    """
    vocab: set[str] = set()
    for r in rows:
        for t in WORD.findall(r.full_desc.lower()):
            vocab.add(t)
    auto: dict[str, str] = {}
    # Ordered shortest-singular-first so longer derivations don't override
    for w in sorted(vocab, key=len):
        if len(w) < 4 or "'" in w:
            continue
        forms: list[str] = []
        if w.endswith("y"):
            forms.append(w[:-1] + "ies")
        if w.endswith("o"):
            forms.append(w + "es")
        if w.endswith("f"):
            forms.append(w[:-1] + "ves")
        if w.endswith("fe"):
            forms.append(w[:-2] + "ves")
        forms.append(w + "es")
        forms.append(w + "s")
        for p in forms:
            if p == w:
                continue
            if p in auto:
                continue
            # Only register if the plural itself isn't a known shorter singular
            # (e.g. don't make "as" map to "a"). Shorter words preserved.
            auto[p] = w
    return auto


def load_rows() -> list[Row]:
    out: list[Row] = []
    with PARSED.open() as f:
        for r in csv.DictReader(f):
            facets = r["facets_pipe"].split("|") if r["facets_pipe"] else []
            out.append(Row(
                source=r["source"],
                code=r["code"],
                first_frag=r["identity_raw"],
                facets=facets,
                full_desc=r["full_desc"],
            ))
    # Append hand-authored taxonomy overrides for retail product classes
    # absent from SR28/FNDDS/ESHA (e.g. liqueur, kettle corn, energy bar,
    # imitation crab, pepper jelly, etc.). Same row schema; loader treats
    # them identically. Each override carries proxy SR28/FNDDS/ESHA codes
    # so downstream nutrition lookups still work.
    overrides_path = ROOT / "implementation" / "taxonomy_overrides.csv"
    if overrides_path.exists():
        with overrides_path.open() as f:
            for r in csv.DictReader(f):
                facets = r["facets_pipe"].split("|") if r.get("facets_pipe") else []
                out.append(Row(
                    source=r["source"],
                    code=r["code"],
                    first_frag=r["identity_raw"],
                    facets=facets,
                    full_desc=r["full_desc"],
                ))
    # Augment PLURAL with vocabulary-derived plural forms before any
    # subsequent tokenization. Walnuts → walnut, raspberries → raspberry, etc.
    auto = build_auto_plurals(out)
    PLURAL.update(auto)
    return out


# ---------------------------------------------------------------------------
# Stage 2: detect carriers
# ---------------------------------------------------------------------------

def detect_carriers(rows: list[Row], min_distinct_seconds: int = 8,
                    echo_threshold: float = 0.5) -> dict[str, dict]:
    """Return the hand-curated carrier set.

    Auto-detection was retired because it consistently demoted real food
    identities (applesauce, chips, crust, pie, base) to carriers when their
    descriptions had many varieties. Carriers are now a deliberate design
    choice; see CURATED_CARRIERS at the top of this module.
    """
    info: dict[str, dict] = {}
    # Count occurrences for the audit CSV, but include only curated carriers.
    occ: Counter = Counter()
    for r in rows:
        first_toks = tokens(r.first_frag)
        if first_toks:
            occ[first_toks[-1]] += 1
    for c in CURATED_CARRIERS:
        info[c] = {
            "n_occurrences": occ.get(c, 0),
            "n_distinct_seconds": 0,
            "echoed_seconds": 0,
            "echo_ratio": 1.0,
        }
    return info


# ---------------------------------------------------------------------------
# Stage 3: identity head + key facets per row
# ---------------------------------------------------------------------------

# Verbosity that shows up in nutrition descriptions but doesn't change leaf.
VERBOSITY = {
    "commercial", "regular", "added", "with", "vitamin", "vitamins",
    "fortified", "enriched",  # arguably keep — but for v2 strip them
    "sodium", "potassium", "calcium",
    "form", "fluid", "as", "purchased", "made", "type", "name",
    "national", "data", "bank", "any", "all",
}

def extract_head_and_facets(row: Row, carriers: set[str]) -> tuple[str, set[str]]:
    """Walk fragments, return (head, key_facets).

    For each fragment, walk RIGHT-TO-LEFT and pick the first non-skip token
    as the candidate head. Skip-set includes carriers, modifiers, units,
    retail-routing attrs, and form words. This handles cases like
    "Amaranth leaves, raw" → head=amaranth (skip 'leaves'), or
    "Pillsbury, Cinnamon rolls with icing" → head=icing (skip 'pillsbury'
    via carriers, then take last non-skip of next fragment).
    """
    fragments = [row.first_frag] + row.facets
    head = ""
    for frag in fragments:
        ftoks = tokens(frag)
        if not ftoks:
            continue
        candidate = ""
        for h in reversed(ftoks):
            if (h in carriers or h in MODIFIER_TOKENS or h in UNITS
                    or h in RETAIL_ATTRS_ROUTING or h in FORM_WORDS
                    or h in GLOBAL_NOISE):
                continue
            candidate = h
            break
        if candidate:
            head = candidate
            break
    if not head:
        return "", set()

    # Build key_facets from the entire full_desc, stripping head + noise.
    # MODIFIER_TOKENS stay in facets — they discriminate leaves.
    # UNITS are stripped — they don't discriminate identity.
    facets: set[str] = set()
    for t in tokens(row.full_desc):
        if t == head:
            continue
        if t in carriers or t in GLOBAL_NOISE or t in VERBOSITY:
            continue
        if t in RETAIL_ATTRS_NONROUTING or t in UNITS:
            continue
        facets.add(t)
    return head, facets


# ---------------------------------------------------------------------------
# Stage 4: leaf clustering with per-source provenance
# ---------------------------------------------------------------------------

@dataclass
class LeafProvenance:
    code: str
    desc: str
    score: float            # 1.0 = perfect canonical, lower = verbose/proxy

@dataclass
class Leaf:
    leaf_id: str
    head: str
    canonical_name: str
    key_facets: frozenset
    sources: dict[str, LeafProvenance] = field(default_factory=dict)
    all_codes: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))


def make_leaf_id(head: str, key_facets: frozenset) -> str:
    sig = head + "|" + "|".join(sorted(key_facets))
    return hashlib.sha1(sig.encode()).hexdigest()[:12]


def build_leaves(rows: list[Row], carriers: set[str]) -> dict[str, Leaf]:
    # Group rows by (head, key_facets) tuple
    groups: dict[tuple, list[Row]] = defaultdict(list)
    row_meta: dict[int, tuple[str, frozenset]] = {}
    for i, r in enumerate(rows):
        head, facets = extract_head_and_facets(r, carriers)
        if not head:
            continue
        key = (head, frozenset(facets))
        groups[key].append(r)
        row_meta[i] = (head, frozenset(facets))

    leaves: dict[str, Leaf] = {}
    for (head, kf), members in groups.items():
        leaf_id = make_leaf_id(head, kf)
        # Canonical name: shortest member desc — least verbose.
        members_sorted = sorted(members, key=lambda x: len(x.full_desc))
        canonical = members_sorted[0].full_desc

        leaf = Leaf(leaf_id=leaf_id, head=head, canonical_name=canonical,
                    key_facets=kf)
        # Per-source: pick the shortest desc as the canonical representative
        by_source: dict[str, list[Row]] = defaultdict(list)
        for m in members:
            by_source[m.source].append(m)
            leaf.all_codes[m.source].append(m.code)
        for src, ms in by_source.items():
            best = min(ms, key=lambda x: len(x.full_desc))
            # Score: 1.0 if the description's content tokens match the leaf's
            # key_facets exactly; lower if verbose (more tokens than facets).
            best_content = {t for t in tokens(best.full_desc)
                            if t != head and t not in GLOBAL_NOISE
                            and t not in RETAIL_ATTRS_NONROUTING
                            and t not in VERBOSITY
                            and t not in carriers}
            if not kf:
                score = 1.0 if not best_content else 0.8
            else:
                inter = len(best_content & kf)
                union = len(best_content | kf)
                score = inter / union if union else 1.0
            leaf.sources[src] = LeafProvenance(
                code=best.code, desc=best.full_desc, score=round(score, 3))
        leaves[leaf_id] = leaf
    return leaves


# ---------------------------------------------------------------------------
# Stage 5: route a retail surface with traceability
# ---------------------------------------------------------------------------

def build_facet_users(leaves: dict[str, "Leaf"]) -> dict[str, set[str]]:
    """For each token used as a key_facet, list which heads contain it.

    Lets parse_surface decide that `parmesan` is a child of `cheese` (since
    parmesan appears in cheese-headed leaves' facets), and prefer the parent
    when both are candidate heads in a retail string.
    """
    fu: dict[str, set[str]] = defaultdict(set)
    for leaf in leaves.values():
        for f in leaf.key_facets:
            fu[f].add(leaf.head)
    return fu


def parse_surface(s: str, known_heads: set[str],
                  head_leaf_count: dict[str, int],
                  facet_users: dict[str, set[str]] | None = None) -> dict:
    """Split surface tokens into:
        - head            : the identity (a known nutrition head)
        - routing_tokens  : nutrition-relevant tokens used for leaf selection
        - retail_attrs    : preserved metadata (organic/sliced/frozen/...)
        - brand_candidates: tokens not in any known nutrition vocab

    Brand handling: tokens that aren't in nutrition vocab AND aren't retail
    attrs are treated as brand candidates. They're surfaced separately so
    downstream search can index by brand without affecting the routing.
    """
    raw = tokens(s)
    retail_present = [t for t in raw if t in RETAIL_ATTRS]
    # Routing pool keeps RETAIL_ATTRS_ROUTING (canned/frozen/etc.) because
    # they ARE nutrition-relevant. Only RETAIL_ATTRS_NONROUTING is stripped.
    identity_pool = [t for t in raw
                     if t not in GLOBAL_NOISE
                     and t not in RETAIL_ATTRS_NONROUTING]
    head = ""
    # Head selection rules, in priority order:
    #   1. Never pick RETAIL_ATTRS_ROUTING (frozen/fresh/canned), MODIFIER_TOKENS
    #      (boneless/lightly/sweetened/...), or UNITS (oz/g/ct) as head.
    #   2. Prefer the RIGHTMOST known head that has ≥2 leaves. English
    #      head-final convention: "habanero pepper jelly" → jelly,
    #      "beef stroganoff" → stroganoff.
    #   3. Fall back to most-leaves head.
    #   4. Fall back to rightmost identity token.
    eligible = [t for t in identity_pool
                if t in known_heads
                and t not in RETAIL_ATTRS_ROUTING
                and t not in MODIFIER_TOKENS
                and t not in UNITS
                and t not in FORM_WORDS
                and t not in SURFACE_MODIFIERS]  # fat/sodium/sugar/etc.

    # English head-final: rightmost eligible token wins.
    # We dropped the parent-child demotion. It was actively wrong on cases
    # like "bread yeast" (yeast is rightmost — the food — but the rule
    # demoted it because yeast appears in some bread leaf facets). Pure
    # rightmost works for the cases parent-child was intended to help
    # (e.g. "parmesan cheese" → cheese is rightmost anyway).
    if eligible:
        head = eligible[-1]
    elif identity_pool:
        # Strip RETAIL_ATTRS_ROUTING + MODIFIER_TOKENS + UNITS from the
        # fallback too — none of those are identities.
        non_attr = [t for t in identity_pool
                    if t not in RETAIL_ATTRS_ROUTING
                    and t not in MODIFIER_TOKENS
                    and t not in UNITS]
        head = non_attr[-1] if non_attr else identity_pool[-1]
    routing = {t for t in identity_pool if t != head}
    return {
        "raw_tokens": raw,
        "retail_attrs": retail_present,
        "head": head,
        "routing_tokens": routing,
    }


def route(surface: str, leaves: dict[str, Leaf],
          leaves_by_head: dict[str, list[Leaf]],
          known_heads: set[str], known_vocab: set[str],
          head_leaf_count: dict[str, int],
          facet_users: dict[str, set[str]] | None = None) -> dict:
    parsed = parse_surface(surface, known_heads, head_leaf_count, facet_users)
    head = parsed["head"]
    rtoks = parsed["routing_tokens"]

    if not head or head not in leaves_by_head:
        return {"verdict": "NO_IDENTITY_NODE", "parsed": parsed,
                "leaf": None, "candidates": []}

    # Tokens not in any nutrition vocab AND not retail attrs AND not a known
    # head elsewhere in the taxonomy = brand candidates. (Excluding known
    # heads prevents words like 'salad' or 'soup' showing up as brands when
    # they're carriers in the leaf desc but real identities elsewhere.)
    recognized = {t for t in rtoks if t in known_vocab or t == head
                  or t in known_heads}
    brand_candidates = {t for t in rtoks
                        if t not in known_vocab and t != head
                        and t not in known_heads
                        and t not in RETAIL_ATTRS}
    unresolved = rtoks - recognized

    # Empty routing tokens — surface is just the head identity (or head +
    # retail-attrs only). Pick the LEAST-specific leaf (smallest key_facets);
    # that's the canonical generic for the head.
    if not rtoks:
        candidates_simple = sorted(leaves_by_head[head],
                                   key=lambda l: (len(l.key_facets),
                                                  len(l.canonical_name)))
        best = candidates_simple[0]
        return {
            "verdict": "GENERIC",
            "parsed": parsed,
            "unresolved_tokens": [],
            "brand_candidates": [],
            "leaf": best,
            "match_meta": {"cov": 1.0, "shared": set(), "missing": set(),
                           "leaf_extra": best.key_facets},
            "top3": [(c.leaf_id, {"cov": 1.0, "shared": set(),
                                  "missing": set(),
                                  "leaf_extra": c.key_facets})
                     for c in candidates_simple[:3]],
            "n_candidates": len(candidates_simple),
        }

    candidates: list[tuple[Leaf, dict]] = []
    for leaf in leaves_by_head[head]:
        shared = recognized & leaf.key_facets
        missing = recognized - leaf.key_facets
        leaf_extra = leaf.key_facets - recognized
        cov = len(shared) / max(1, len(recognized)) if recognized else (
            1.0 if not leaf.key_facets else 0.0)
        candidates.append((leaf, {
            "cov": cov,
            "shared": shared,
            "missing": missing,
            "leaf_extra": leaf_extra,
        }))
    candidates.sort(key=lambda c: (-c[1]["cov"],
                                   len(c[1]["leaf_extra"]),
                                   len(c[0].key_facets)))
    best_leaf, best_meta = candidates[0]

    # Verdict
    if best_meta["cov"] >= 0.999 and not best_meta["missing"] \
            and not best_meta["leaf_extra"]:
        verdict = "EXACT"
    elif best_meta["cov"] >= 0.999 and not best_meta["missing"]:
        # Recognized tokens fully covered, leaf has more facets — caller
        # surface is less specific. Pick the LEAST specific leaf instead.
        less_specific = sorted(
            [c for c in candidates if c[1]["cov"] >= 0.999
             and not c[1]["missing"]],
            key=lambda c: len(c[0].key_facets))
        best_leaf, best_meta = less_specific[0]
        verdict = "EXACT"
    elif best_meta["cov"] >= 0.67:
        verdict = "STRONG"
    elif best_meta["cov"] >= 0.5:
        verdict = "WEAK"
    else:
        verdict = "NEEDS_NEW_LEAF"

    # Per-source closest match — for traceability.
    # Two regimes:
    #   (1) Surface has recognized routing tokens → scan ALL candidates,
    #       require cov > 0 to be eligible per source. No false closest.
    #   (2) Surface has NO recognized routing tokens (head-only or
    #       all-brand-noise) → use ONLY the matched leaf's own source
    #       provenance. Don't scan other candidates — that creates the
    #       "denny's golden fried shrimp" bug where a random SR28 leaf in
    #       the same head gets nominated as 'closest' for every popcorn /
    #       bay / jumbo / raw shrimp surface.
    PER_SRC_MIN_COV = 1e-9
    no_routing_signal = (len(recognized) == 0)
    per_source_closest: dict[str, dict] = {}
    if no_routing_signal:
        for src in ("sr28", "fndds", "esha"):
            prov = best_leaf.sources.get(src)
            if prov:
                per_source_closest[src] = {
                    "code": prov.code,
                    "desc": prov.desc,
                    "leaf_id": best_leaf.leaf_id,
                    "leaf_canonical": best_leaf.canonical_name,
                    "coverage": best_meta["cov"],
                    "missing_from_leaf": sorted(best_meta["missing"]),
                    "leaf_extra_facets": sorted(best_meta["leaf_extra"]),
                }
            else:
                per_source_closest[src] = None
    else:
        for src in ("sr28", "fndds", "esha"):
            best_for_src = None
            best_score = -1.0
            for c_leaf, c_meta in candidates:
                prov = c_leaf.sources.get(src)
                if not prov:
                    continue
                cov = c_meta["cov"]
                if cov < PER_SRC_MIN_COV:
                    continue   # no shared token → not 'closest', report None
                extra_penalty = 0.05 * len(c_meta["leaf_extra"])
                score = cov - extra_penalty
                if score > best_score:
                    best_score = score
                    best_for_src = (c_leaf, c_meta, prov)
            if best_for_src:
                cl, cm, prov = best_for_src
                per_source_closest[src] = {
                    "code": prov.code,
                    "desc": prov.desc,
                    "leaf_id": cl.leaf_id,
                    "leaf_canonical": cl.canonical_name,
                    "coverage": cm["cov"],
                    "missing_from_leaf": sorted(cm["missing"]),
                    "leaf_extra_facets": sorted(cm["leaf_extra"]),
                }
            else:
                per_source_closest[src] = None

    return {
        "verdict": verdict,
        "parsed": parsed,
        "unresolved_tokens": sorted(unresolved),
        "brand_candidates": sorted(brand_candidates),
        "leaf": best_leaf,
        "match_meta": best_meta,
        "top3": [(c[0].leaf_id, c[1]) for c in candidates[:3]],
        "n_candidates": len(candidates),
        "per_source_closest": per_source_closest,
    }


# ---------------------------------------------------------------------------
# Output writers
# ---------------------------------------------------------------------------

def write_carriers(carriers: dict[str, dict]):
    p = OUT / "carriers.csv"
    with p.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["carrier_word", "n_occurrences", "n_distinct_seconds",
                    "echoed_seconds", "echo_ratio"])
        for k in sorted(carriers, key=lambda x: -carriers[x]["echo_ratio"]):
            d = carriers[k]
            w.writerow([k, d["n_occurrences"], d["n_distinct_seconds"],
                        d["echoed_seconds"], round(d["echo_ratio"], 3)])
    return p


def write_leaves(leaves: dict[str, Leaf]):
    p = OUT / "leaves.csv"
    with p.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "leaf_id", "head", "canonical_name", "key_facets",
            "n_sources",
            "sr28_code", "sr28_desc", "sr28_score",
            "fndds_code", "fndds_desc", "fndds_score",
            "esha_code", "esha_desc", "esha_score",
        ])
        for leaf in sorted(leaves.values(),
                           key=lambda x: (x.head, x.canonical_name)):
            sr = leaf.sources.get("sr28")
            fn = leaf.sources.get("fndds")
            es = leaf.sources.get("esha")
            w.writerow([
                leaf.leaf_id, leaf.head, leaf.canonical_name,
                "|".join(sorted(leaf.key_facets)),
                len(leaf.sources),
                sr.code if sr else "", sr.desc if sr else "",
                sr.score if sr else "",
                fn.code if fn else "", fn.desc if fn else "",
                fn.score if fn else "",
                es.code if es else "", es.desc if es else "",
                es.score if es else "",
            ])
    return p


def write_routes(routes: list[dict]):
    p = OUT / "retail_routes.csv"
    with p.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "surface", "verdict", "head", "routing_tokens",
            "retail_attrs", "unresolved_tokens",
            "leaf_id", "canonical_name",
            "sr28_code", "sr28_desc",
            "fndds_code", "fndds_desc",
            "esha_code", "esha_desc",
            "missing_from_leaf", "leaf_facets_not_in_surface",
        ])
        for r in routes:
            leaf = r["result"]["leaf"]
            mm = r["result"].get("match_meta") or {}
            sr = leaf.sources.get("sr28") if leaf else None
            fn = leaf.sources.get("fndds") if leaf else None
            es = leaf.sources.get("esha") if leaf else None
            w.writerow([
                r["surface"], r["result"]["verdict"],
                r["result"]["parsed"]["head"],
                "|".join(sorted(r["result"]["parsed"]["routing_tokens"])),
                "|".join(r["result"]["parsed"]["retail_attrs"]),
                "|".join(r["result"].get("unresolved_tokens", [])),
                leaf.leaf_id if leaf else "",
                leaf.canonical_name if leaf else "",
                sr.code if sr else "", sr.desc if sr else "",
                fn.code if fn else "", fn.desc if fn else "",
                es.code if es else "", es.desc if es else "",
                "|".join(sorted(mm.get("missing", []))),
                "|".join(sorted(mm.get("leaf_extra", []))),
            ])
    return p


# ---------------------------------------------------------------------------
# Pretty test runner
# ---------------------------------------------------------------------------

def show(label: str, surface: str, leaves, leaves_by_head, known, vocab, hcounts):
    print(f"\n=== {label} ===")
    print(f"  input: {surface!r}")
    res = route(surface, leaves, leaves_by_head, known, vocab, hcounts)
    p = res["parsed"]
    print(f"  parsed: head={p['head']!r}  routing={sorted(p['routing_tokens'])}  "
          f"retail_attrs={p['retail_attrs']}")
    if res.get("brand_candidates"):
        print(f"  brand candidates: {res['brand_candidates']}")
    if res.get("unresolved_tokens"):
        print(f"  unresolved: {res['unresolved_tokens']}")
    print(f"  verdict: {res['verdict']}")
    if res["verdict"] == "NO_IDENTITY_NODE":
        return
    leaf = res["leaf"]
    mm = res["match_meta"]
    print(f"  matched leaf: {leaf.leaf_id} \"{leaf.canonical_name}\"")
    print(f"    key_facets={sorted(leaf.key_facets)}  cov={mm['cov']:.2f}  "
          f"miss={sorted(mm['missing'])}  leaf_extra={sorted(mm['leaf_extra'])}")
    print(f"  per-source provenance (matched leaf):")
    for src in ("sr28", "fndds", "esha"):
        prov = leaf.sources.get(src)
        if prov:
            print(f"    {src:5s}: [{prov.code:>10}] {prov.desc[:75]}  "
                  f"(score={prov.score})")
        else:
            print(f"    {src:5s}: — no leaf in this source")
    psc = res.get("per_source_closest") or {}
    if res["verdict"] in ("NEEDS_NEW_LEAF", "WEAK"):
        print(f"  per-source CLOSEST (independent scan):")
        for src in ("sr28", "fndds", "esha"):
            c = psc.get(src)
            if c:
                print(f"    {src:5s}: [{c['code']:>10}] {c['desc'][:75]}  "
                      f"cov={c['coverage']:.2f}  miss={c['missing_from_leaf']}")
            else:
                print(f"    {src:5s}: — no leaf in this source for head={leaf.head!r}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("Loading parsed_unified.csv…", flush=True)
    rows = load_rows()
    print(f"  {len(rows):,} rows")

    print("Detecting carriers…", flush=True)
    carriers_info = detect_carriers(rows)
    carriers = set(carriers_info.keys())
    write_carriers(carriers_info)
    print(f"  {len(carriers)} carriers detected (top 15 by echo_ratio):")
    for h in sorted(carriers, key=lambda x: -carriers_info[x]["echo_ratio"])[:15]:
        d = carriers_info[h]
        print(f"    {h:20s} occ={d['n_occurrences']:5d}  "
              f"distinct_seconds={d['n_distinct_seconds']:4d}  "
              f"echo_ratio={d['echo_ratio']:.2f}")

    print("\nBuilding leaves…", flush=True)
    leaves = build_leaves(rows, carriers)
    leaves_by_head: dict[str, list[Leaf]] = defaultdict(list)
    known_heads: set[str] = set()
    known_vocab: set[str] = set()
    for leaf in leaves.values():
        leaves_by_head[leaf.head].append(leaf)
        known_heads.add(leaf.head)
        known_vocab |= leaf.key_facets
    head_leaf_count = {h: len(v) for h, v in leaves_by_head.items()}
    write_leaves(leaves)

    n_3way = sum(1 for l in leaves.values() if len(l.sources) == 3)
    n_2way = sum(1 for l in leaves.values() if len(l.sources) == 2)
    n_1way = sum(1 for l in leaves.values() if len(l.sources) == 1)
    print(f"  {len(leaves):,} leaves across {len(known_heads)} identity heads")
    print(f"    3-source agreement : {n_3way:,}")
    print(f"    2-source agreement : {n_2way:,}")
    print(f"    1-source only      : {n_1way:,}")
    print(f"  vocabulary: {len(known_vocab):,} key facet tokens")

    # Test cases
    TESTS = [
        ("100% bran (your callout)",          "100% bran"),
        ("Asiago peppercorn (still WEAK?)",   "asiago peppercorn salad dressing"),
        ("Peppercorn dressing (control)",     "peppercorn salad dressing"),
        ("Bacon ranch dressing",               "bacon ranch dressing"),
        ("Bleu cheese dressing",               "bleu cheese dressing"),
        ("Mushroom pieces and stems",         "mushroom pieces and stems"),
        ("Mushroom gravy (carrier check)",    "mushroom gravy"),
        ("Baby kale",                          "baby kale"),
        ("Organic sliced frozen mango",       "organic sliced frozen mango"),
        ("Trader joe's organic baby spinach", "trader joe's organic baby spinach"),
        ("Frozen grilled chicken breast",     "frozen grilled chicken breast"),
        ("Beef stroganoff (carrier test)",    "beef stroganoff"),
        ("Tomato basil soup",                  "tomato basil soup"),
        ("Habanero pepper jelly",              "habanero pepper jelly"),
        ("Grace evaporated filled milk",      "grace evaporated filled milk"),
        ("Fat free organic milk",              "fat free organic milk"),
        ("Harris teeter milk (your callout)", "harris teeter milk"),
        ("Kraft singles american cheese",     "kraft singles american cheese"),
        # Form-state tests — these MUST produce different leaves
        ("Green beans, frozen",                "frozen green beans"),
        ("Green beans, canned",                "canned green beans"),
        ("Green beans, fresh",                 "fresh green beans"),
        ("Green beans, dried",                 "dried green beans"),
        ("Mango, frozen",                      "frozen mango"),
        ("Mango, fresh",                       "fresh mango"),
        ("Mango, dried",                       "dried mango"),
    ]

    print("\n" + "=" * 70)
    print("TEST CASES")
    print("=" * 70)
    routes = []
    for label, s in TESTS:
        show(label, s, leaves, leaves_by_head, known_heads, known_vocab,
             head_leaf_count)
        routes.append({
            "surface": s,
            "result": route(s, leaves, leaves_by_head, known_heads,
                            known_vocab, head_leaf_count),
        })
    write_routes(routes)

    # Validation pass: route every dressing surface in canonical_surface
    print("\n" + "=" * 70)
    print("VALIDATION: dressing surfaces in canonical_surface")
    print("=" * 70)
    val_rows = []
    if SURFACE.exists():
        with SURFACE.open(encoding="utf-8", errors="replace") as f:
            for r in csv.DictReader(f):
                surf = (r.get("canonical_surface") or "").lower().strip()
                if "dressing" not in surf:
                    continue
                cur_esha = (r.get("esha_code") or "").strip()
                cur_desc = (r.get("esha_description") or "").strip()
                res = route(surf, leaves, leaves_by_head, known_heads,
                            known_vocab, head_leaf_count)
                leaf = res["leaf"]
                rft_esha = ""
                rft_desc = ""
                if leaf and "esha" in leaf.sources:
                    rft_esha = leaf.sources["esha"].code
                    rft_desc = leaf.sources["esha"].desc
                val_rows.append({
                    "surface": surf, "current_esha": cur_esha,
                    "current_desc": cur_desc,
                    "rft_verdict": res["verdict"],
                    "rft_esha": rft_esha, "rft_desc": rft_desc,
                    "rft_canonical": leaf.canonical_name if leaf else "",
                    "head": res["parsed"]["head"],
                    "retail_attrs": "|".join(res["parsed"]["retail_attrs"]),
                    "unresolved": "|".join(res.get("unresolved_tokens", [])),
                })
    val_path = OUT / "validation_diff.csv"
    if val_rows:
        with val_path.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(val_rows[0].keys()))
            w.writeheader()
            w.writerows(val_rows)
    verdict_counter = Counter(r["rft_verdict"] for r in val_rows)
    agree = sum(1 for r in val_rows
                if r["current_esha"] and r["rft_esha"] == r["current_esha"])
    disagree = sum(1 for r in val_rows
                   if r["current_esha"] and r["rft_esha"]
                   and r["rft_esha"] != r["current_esha"])
    only_rft = sum(1 for r in val_rows
                   if not r["current_esha"] and r["rft_esha"])
    only_cur = sum(1 for r in val_rows
                   if r["current_esha"] and not r["rft_esha"])
    print(f"  total dressing surfaces : {len(val_rows)}")
    print(f"  verdict mix             : {dict(verdict_counter)}")
    print(f"  agree w/ current        : {agree}")
    print(f"  disagree w/ current     : {disagree}")
    print(f"  rft routed, current empty: {only_rft}")
    print(f"  current had, rft empty  : {only_cur}")

    # Brand candidate frequency analysis — pull from the validation routes.
    print("\n" + "=" * 70)
    print("BRAND CANDIDATE ANALYSIS (top unresolved tokens across dressing surfaces)")
    print("=" * 70)
    brand_freq: Counter = Counter()
    for r in val_rows:
        # We need to re-route to get brand_candidates (val_rows didn't store it).
        res = route(r["surface"], leaves, leaves_by_head, known_heads,
                    known_vocab, head_leaf_count)
        for t in res.get("brand_candidates", []):
            brand_freq[t] += 1
    if brand_freq:
        print(f"  {len(brand_freq)} distinct brand-candidate tokens found")
        print(f"  top 20:")
        for t, n in brand_freq.most_common(20):
            print(f"    {t:30s} {n}")
    else:
        print("  none — dressing surfaces are mostly nutrition vocab")

    print("\nFiles written:")
    for p in [OUT / "carriers.csv", OUT / "leaves.csv",
              OUT / "retail_routes.csv", val_path]:
        print(f"  {p.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
