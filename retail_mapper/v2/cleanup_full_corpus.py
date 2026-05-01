#!/usr/bin/env python3
"""Post-run cleanup of the LLM full-corpus output.

Two jobs:

1. AUDIT every hint-table identity for "lonely hint" miscategorization —
   rows where the model emitted that identity but the title doesn't contain
   its natural keyword. These are likely cases where the model was forced
   into the wrong identity because the hint table was too narrow.

2. FIX known patterns:
   - Apple Chips with non-apple title -> reassign to Banana Chips /
     Mango Chips / Strawberry Chips / Sweet Potato Chips / Veggie Chips /
     Dried Fruit based on title keywords.
   - Add other patterns as discovered.

Writes a corrected CSV alongside the raw export. Pure script — no LLM calls.

Usage:
    python3 retail_mapper/v2/cleanup_full_corpus.py --audit-only
        # report lonely-hint cases without rewriting

    python3 retail_mapper/v2/cleanup_full_corpus.py
        # apply known fixes; write full_corpus_cleaned.csv
"""
from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
V2 = REPO / "retail_mapper" / "v2"
DEFAULT_LIVE = V2 / "full_corpus.live.jsonl"
DEFAULT_OUT  = V2 / "full_corpus_cleaned.csv"
DEFAULT_AUDIT = V2 / "lonely_hint_audit.txt"
DEFAULT_PLURAL_MAP = V2 / "identity_plural_map.json"
DEFAULT_PATH_VOTE_MAP = V2 / "path_vote_map.json"
DEFAULT_SEGMENT_PLURAL_MAP = V2 / "path_segment_plural_map.json"
DEFAULT_SEGMENT_SYNONYMS  = V2 / "path_segment_synonyms.json"
DEFAULT_REPORT  = V2 / "path_collision_report.csv"
DEFAULT_DISPUTE = V2 / "path_dispute.csv"

csv.field_size_limit(sys.maxsize)


def load_module():
    sp = importlib.util.spec_from_file_location("ltc", V2 / "llm_taxonomy_cleanup.py")
    m = importlib.util.module_from_spec(sp); sys.modules["ltc"] = m
    sp.loader.exec_module(m)
    return m


# ---------------- known-fix rules ----------------

# --- Apple Chips: real apple chips OR resolve to specific fruit/veggie chip
APPLE_CHIPS_REMAP = [
    ("banana", "Banana Chips"), ("mango", "Mango Chips"),
    ("strawberry", "Strawberry Chips"), ("peach", "Peach Chips"),
    ("apricot", "Apricot Chips"), ("pineapple", "Pineapple Chips"),
    ("sweet potato", "Sweet Potato Chips"), ("sweetpotato", "Sweet Potato Chips"),
    ("plantain", "Plantain Chips"), ("coconut", "Coconut Chips"),
    ("beet", "Beet Chips"), ("kale", "Kale Chips"),
    ("veggie", "Veggie Chips"), ("vegetable", "Veggie Chips"),
    ("jackfruit", "Jackfruit Chips"), ("persimmon", "Persimmon Chips"),
]
def fix_apple_chips(title: str, identity: str) -> str | None:
    if identity != "Apple Chips": return None
    t = (title or "").lower()
    if "apple" in t: return None
    for kw, new_id in APPLE_CHIPS_REMAP:
        if kw in t: return new_id
    return "Dried Fruit Chips"


# --- Apple Snack Pack: real apple OR resolve to other fruit/veggie pack
APPLE_SNACK_PACK_REMAP = [
    ("carrot", "Carrot Snack Pack"),
    ("celery", "Celery Snack Pack"),
    ("veggie", "Veggie Snack Pack"), ("vegetable", "Veggie Snack Pack"),
    ("cantaloupe", "Cantaloupe Cup"), ("watermelon", "Watermelon Cup"),
    ("melon", "Melon Cup"),
    ("grape", "Grape Cup"), ("pineapple", "Pineapple Cup"),
    ("mango", "Mango Cup"), ("peach", "Peach Cup"),
    ("strawberry", "Strawberry Cup"), ("blueberry", "Blueberry Cup"),
    ("raspberry", "Raspberry Cup"), ("kiwi", "Kiwi Cup"),
    ("cherry", "Cherry Cup"), ("orange", "Orange Cup"),
    ("banana", "Banana Cup"),
]
def fix_apple_snack_pack(title: str, identity: str) -> str | None:
    if identity != "Apple Snack Pack": return None
    t = (title or "").lower()
    if "apple" in t: return None
    for kw, new_id in APPLE_SNACK_PACK_REMAP:
        if kw in t: return new_id
    return "Fruit Snack Pack"


# --- Mixed Nuts: real mix OR resolve to single-nut identity
MIXED_NUTS_REMAP = [
    # Most specific first; "mix"/"blend"/"medley" wins → keep Mixed Nuts
    ("pignoli", "Pine Nuts"),
    ("pine nut", "Pine Nuts"),
    ("brazil", "Brazil Nuts"),
    ("hazelnut", "Hazelnuts"),
    ("filbert", "Hazelnuts"),
    ("macadamia", "Macadamia Nuts"),
    ("pistachio", "Pistachios"),
    ("walnut", "Walnuts"),
    ("pecan", "Pecans"),
    ("cashew", "Cashews"),
    ("almond", "Almonds"),
    ("peanut", "Peanuts"),
    ("edamame", "Edamame"),
    ("sunflower seed", "Sunflower Seeds"),
    ("pumpkin seed", "Pumpkin Seeds"), ("pepita", "Pumpkin Seeds"),
]
def fix_mixed_nuts(title: str, identity: str) -> str | None:
    if identity != "Mixed Nuts": return None
    t = (title or "").lower()
    # Genuinely mixed if title says so
    if any(w in t for w in ("mixed", " mix ", "medley", "assorted", "trail mix", "blend")):
        return None
    for kw, new_id in MIXED_NUTS_REMAP:
        if kw in t: return new_id
    return None  # leave alone if no specific nut found


# --- Barbecue Sauce: real BBQ OR resolve to specific sauce subtype
BARBECUE_SAUCE_REMAP = [
    ("worcestershire", "Worcestershire Sauce"),
    ("a1", "Steak Sauce"), ("steak sauce", "Steak Sauce"),
    ("cocktail sauce", "Cocktail Sauce"),
    ("tartar sauce", "Tartar Sauce"),
    ("hoisin", "Hoisin Sauce"),
    ("teriyaki", "Teriyaki Sauce"),
    ("soy sauce", "Soy Sauce"),
    ("oyster sauce", "Oyster Sauce"),
    ("fish sauce", "Fish Sauce"),
    ("chimichurri", "Chimichurri Sauce"),
    ("ponzu", "Ponzu Sauce"),
    ("buffalo", "Buffalo Sauce"),
    ("hot sauce", "Hot Sauce"),
    ("sriracha", "Sriracha"),
    ("chipotle", "Chipotle Sauce"),
    ("enchilada", "Enchilada Sauce"),
    ("mole", "Mole Sauce"),
    ("alfredo", "Alfredo Sauce"),
    ("marinara", "Marinara Sauce"),
    ("pesto", "Pesto"),
    ("pasta sauce", "Pasta Sauce"),
    ("pizza sauce", "Pizza Sauce"),
    ("tomato sauce", "Tomato Sauce"),
    ("cheese sauce", "Cheese Sauce"),
    ("ketchup", "Ketchup"),
    ("mustard", "Mustard"),
    ("mayonnaise", "Mayonnaise"), ("mayo", "Mayonnaise"),
    ("aioli", "Aioli"),
]
def fix_barbecue_sauce(title: str, identity: str) -> str | None:
    if identity != "Barbecue Sauce": return None
    t = (title or "").lower()
    if any(kw in t for kw in ("barbecue", "bbq", "smoky bbq", "kansas city", "memphis", "carolina sauce")):
        return None
    for kw, new_id in BARBECUE_SAUCE_REMAP:
        if kw in t: return new_id
    return "Sauce"  # generic — at least don't claim it's BBQ


# --- Bark: real chocolate-bark OR resolve brownie-brittle / other
BARK_REMAP = [
    ("brownie brittle", "Brownie Brittle"),
    ("brownie bark", "Brownie Brittle"),
    ("brownie bite", "Brownie Bites"),
    ("brownie", "Brownies"),
    ("toffee", "Toffee"),
    ("brittle", "Brittle"),
    ("truffle", "Truffle"),
    ("pretzel", "Chocolate-Covered Pretzels"),
]
def fix_bark(title: str, identity: str) -> str | None:
    if identity != "Bark": return None
    t = (title or "").lower()
    # Real bark patterns — keep as is
    if any(kw in t for kw in ("almond bark","chocolate bark","peppermint bark",
                              "yogurt bark","fruit bark","cookie bark","white bark",
                              "birthday cake bark","mini bark")):
        return None
    for kw, new_id in BARK_REMAP:
        if kw in t: return new_id
    return None  # leave Bark if can't determine


# --- Broccoli with Cheese Sauce: real broccoli OR resolve to actual veg
BROCCOLI_CHEESE_REMAP = [
    ("brussels sprouts", "Brussels Sprouts with Cheese Sauce"),
    ("cauliflower",      "Cauliflower with Cheese Sauce"),
    ("buffalo cauliflower", "Buffalo Cauliflower"),
    ("spinach artichoke","Spinach Artichoke Dip"),
    ("creamy spinach",   "Creamed Spinach"),
    ("spinach",          "Creamed Spinach"),
    ("butternut squash", "Butternut Squash"),
    ("squash",           "Squash"),
    ("carrot",           "Glazed Carrots"),
    ("green bean",       "Green Beans with Sauce"),
    ("asparagus",        "Asparagus with Sauce"),
    ("artichoke",        "Artichoke"),
    ("vegetable",        "Vegetables with Sauce"),
    ("veggie",           "Vegetables with Sauce"),
]
def fix_broccoli_cheese(title: str, identity: str) -> str | None:
    if identity != "Broccoli with Cheese Sauce": return None
    t = (title or "").lower()
    if "broccoli" in t: return None
    for kw, new_id in BROCCOLI_CHEESE_REMAP:
        if kw in t: return new_id
    return None


# --- Butter: real dairy butter OR resolve nut butters / spreads
BUTTER_REMAP = [
    # most specific first
    ("peanut butter",       "Peanut Butter"),
    ("almond butter",       "Almond Butter"),
    ("cashew butter",       "Cashew Butter"),
    ("hazelnut butter",     "Hazelnut Butter"),
    ("nutella",             "Hazelnut Spread"),
    ("sun butter",          "Sunflower Seed Butter"),
    ("sunbutter",           "Sunflower Seed Butter"),
    ("sunflower seed butter","Sunflower Seed Butter"),
    ("sunflower butter",    "Sunflower Seed Butter"),
    ("macadamia butter",    "Macadamia Butter"),
    ("pecan butter",        "Pecan Butter"),
    ("walnut butter",       "Walnut Butter"),
    ("pistachio butter",    "Pistachio Butter"),
    ("nut butter",          "Mixed Nut Butter"),
    ("tahini",              "Tahini"),
    ("sesame butter",       "Tahini"),
    ("apple butter",        "Apple Butter"),
    ("cocoa butter",        "Cocoa Butter"),
    ("cookie butter",       "Cookie Butter"),
    ("ghee",                "Ghee"),
    ("compound butter",     "Compound Butter"),
    ("garlic butter",       "Compound Butter"),
    ("herb butter",         "Compound Butter"),
]
def fix_butter(title: str, identity: str) -> str | None:
    if identity != "Butter": return None
    t = (title or "").lower()
    for kw, new_id in BUTTER_REMAP:
        if kw in t: return new_id
    return None  # leave as Butter if no specific subtype


# --- Cake: real cake OR resolve donuts/danishes/brownies/etc.
# Real cake variants we KEEP under Cake: bundt, layer, birthday, tea, coffee,
# cake mix as filling, ice cream cake, pound cake, sponge cake, butter cake,
# etc.
CAKE_REMAP = [
    # Most specific first
    ("rice cake",        "Rice Cakes"),
    ("fish cake",        "Fish Cakes"),
    ("crab cake",        "Crab Cakes"),
    ("pound cake",       "Pound Cake"),
    ("cup cake",         "Cupcakes"),
    ("cupcake",          "Cupcakes"),
    ("snack cake",       "Snack Cakes"),
    ("coffee cake",      "Coffee Cake"),
    ("tea cake",         "Tea Cakes"),
    ("bundt",            "Bundt Cake"),
    ("layer cake",       "Layer Cake"),
    ("birthday cake",    "Birthday Cake"),
    ("upside down",      "Upside Down Cake"),
    ("angel food",       "Angel Food Cake"),
    ("pound",            "Pound Cake"),
    ("carrot cake",      "Carrot Cake"),
    ("cheesecake",       "Cheesecake"),
    ("cheese cake",      "Cheesecake"),
    # Non-cake products
    ("cinnamon roll",    "Cinnamon Rolls"),
    ("sweet roll",       "Sweet Rolls"),
    ("dinner roll",      "Dinner Rolls"),
    ("danish",           "Danish"),
    ("croissant",        "Croissants"),
    ("scone",            "Scones"),
    ("biscotti",         "Biscotti"),
    ("brownie",          "Brownies"),
    ("doughnut",         "Doughnuts"),
    ("donut",            "Doughnuts"),
    ("muffin",           "Muffins"),
    ("pancake",          "Pancakes"),
    ("waffle",           "Waffles"),
    ("pie",              "Pie"),
    ("cobbler",          "Cobbler"),
    ("strudel",          "Strudel"),
    ("turnover",         "Turnovers"),
    ("eclair",           "Eclair"),
    ("cannoli",          "Cannoli"),
    ("baklava",          "Baklava"),
    ("trifle",           "Trifle"),
    ("tiramisu",         "Tiramisu"),
    ("pudding",          "Pudding"),
    ("custard",          "Custard"),
    ("flan",             "Flan"),
    ("mousse",           "Mousse"),
    # Cake mix → its own thing
    ("cake mix",         "Cake Mix"),
]
def fix_cake(title: str, identity: str) -> str | None:
    if identity != "Cake": return None
    t = (title or "").lower()
    for kw, new_id in CAKE_REMAP:
        if kw in t: return new_id
    return None  # leave as Cake if no specific match


# --- Candied Fruit: only true candied fruit OR remap to actual product
CANDIED_FRUIT_REMAP = [
    ("crystallized ginger","Candied Ginger"),
    ("candied ginger",   "Candied Ginger"),
    ("ginger candy",     "Ginger Candy"),
    ("ginger bites",     "Ginger Candy"),
    ("maraschino",       "Maraschino Cherries"),
    ("candied peel",     "Candied Peel"),
    ("candied citron",   "Candied Citron"),
    ("orange peel",      "Candied Peel"),
    ("lemon peel",       "Candied Peel"),
    ("citron",           "Candied Citron"),
    ("glace",            "Glacé Fruit"),
    ("date rolls",       "Date Rolls"),
    ("dates",            "Dates"),
    ("dried mango",      "Dried Mango"),
    ("dried apricot",    "Dried Apricots"),
    ("dried fruit",      "Dried Fruit"),
    ("raisin",           "Raisins"),
    ("currant",          "Currants"),
    ("guava paste",      "Guava Paste"),
    ("fruit paste",      "Fruit Paste"),
    ("date paste",       "Date Paste"),
    # Decorations / sprinkles — completely different category
    ("confetti",         "Edible Confetti"),
    ("sprinkle",         "Sprinkles"),
    ("jimmies",          "Sprinkles"),
    ("sugar pearl",      "Sugar Pearls"),
    ("decorat",          "Cake Decorations"),
    # Mexican / international candy not candied fruit
    ("mexican candy",    "Mexican Candy"),
    ("baked beans",      "Baked Beans"),  # really, this got into Candied Fruit
]
def fix_candied_fruit(title: str, identity: str) -> str | None:
    if identity != "Candied Fruit": return None
    t = (title or "").lower()
    # Real candied fruit signals
    if "candied fruit" in t or "candied cherry" in t or "candied peel" in t or "glace fruit" in t:
        return None
    for kw, new_id in CANDIED_FRUIT_REMAP:
        if kw in t: return new_id
    return None  # leave as Candied Fruit if can't determine


# --- Pizza Crust Mix magnet (F13): only true pizza/crust mixes
PIZZA_CRUST_REMAP = [
    ("tortilla mix",     "Tortilla Mix"),
    ("flatbread mix",    "Flatbread Mix"),
    ("focaccia",         "Focaccia Mix"),
    ("naan mix",         "Naan Mix"),
    ("pita mix",         "Pita Mix"),
    ("blondie mix",      "Blondie Mix"),
    ("brownie mix",      "Brownie Mix"),
    ("bar mix",          "Baking Mix"),
    ("cookie mix",       "Cookie Mix"),
    ("muffin",           "Muffin Mix"),
    ("bread mix",        "Bread Mix"),
    ("hushpuppy",        "Hushpuppy Mix"),
    ("pakora",           "Pakora Mix"),
    ("bhajia",           "Pakora Mix"),
    ("idli mix",         "Idli Mix"),
    ("pretzel",          "Pretzel Mix"),
    ("corn meal mix",    "Cornbread Mix"),
    ("cornbread",        "Cornbread Mix"),
    ("coating mix",      "Seasoned Coating Mix"),
    ("dough mix",        "Dough Mix"),
    ("recipe mix",       "Baking Mix"),
]
def fix_pizza_crust_mix(title: str, identity: str) -> str | None:
    if identity != "Pizza Crust Mix": return None
    t = (title or "").lower()
    if "pizza" in t or "crust" in t or "dough" in t.replace("dough mix",""):
        return None
    for kw, new_id in PIZZA_CRUST_REMAP:
        if kw in t: return new_id
    return "Baking Mix"


# --- Soda magnet (F15): non-soda titles (lemonade, juice, energy, etc.)
SODA_REMAP = [
    ("lemonade",         "Lemonade"),
    ("limeade",          "Limeade"),
    ("kombucha",         "Kombucha"),
    ("energy drink",     "Energy Drink"),
    ("energy water",     "Functional Water"),
    ("fruit punch",      "Fruit Punch"),
    ("punch",            "Fruit Punch"),
    ("hard cider",       "Hard Cider"),
    ("cider",            "Apple Cider"),
    ("seltzer",          "Sparkling Water"),
    ("sparkling water",  "Sparkling Water"),
    ("flavored water",   "Flavored Water"),
    ("iced tea",         "Iced Tea"),
    ("tea",              "Tea"),
    ("coffee",           "Coffee"),
    ("juice",            "Juice"),
    ("milk",             "Milk"),
    ("beer",             "Beer"),
    ("shake",            "Milkshake"),
    ("smoothie",         "Smoothie"),
]
SODA_KEEP_KEYWORDS = ("soda","cola","pop","tonic","ginger ale","ginger beer",
    "root beer","sprite","dr pepper","pepsi","coke ","mountain dew","crush ",
    "fanta","7up","7-up","squirt","schweppes","a&w","cream soda","club soda",
    "soft drink","carbonated")
def fix_soda(title: str, identity: str) -> str | None:
    if identity != "Soda": return None
    t = (title or "").lower()
    if any(k in t for k in SODA_KEEP_KEYWORDS):
        return None
    for kw, new_id in SODA_REMAP:
        if kw in t: return new_id
    return None  # leave as Soda (the 357 unclassifiable rows)


# --- Sparkling Water magnet (F16): non-sparkling water products
SPARKLING_WATER_REMAP = [
    ("lemonade",         "Lemonade"),
    ("limeade",          "Limeade"),
    ("electrolyte",      "Electrolyte Water"),
    ("energy water",     "Functional Water"),
    ("vita ice",         "Energy Ice"),
    ("caffeine ice",     "Energy Ice"),
    ("ice ",             "Frozen Pop"),
    ("water beverage",   "Flavored Water"),
    ("water drink",      "Flavored Water"),
    ("spring water",     "Flavored Water"),
    ("mineral water",    "Mineral Water"),
    ("agua",             "Flavored Water"),
    ("crystal quenchers","Flavored Water"),
    ("water +",          "Flavored Water"),
    ("infused water",    "Flavored Water"),
]
SPARKLING_KEEP = ("sparkling","carbonated","seltzer","fizz","bubbl","tonic",
                  "effervesc","co2","club soda","aqua frizzante")
def fix_sparkling_water(title: str, identity: str) -> str | None:
    if identity != "Sparkling Water": return None
    t = (title or "").lower()
    if any(k in t for k in SPARKLING_KEEP):
        return None
    for kw, new_id in SPARKLING_WATER_REMAP:
        if kw in t: return new_id
    return None


# --- Hummus pluralization + one-offs (F14)
HUMMUS_COLLAPSE = {
    "Snack Packs":              "Snack Pack",
    "Hummus and Chips":         "Snack Pack",
    "Hummus and Flatbread Pack":"Snack Pack",
    "Hummus Bites":             "Crisps",
    "Vegetable Tray with Hummus":"Veggie Snack Pack",
    "Vegetable Bowl with Hummus":"Veggie Snack Pack",
    "Carrots with Hummus":      "Veggie Snack Pack",
}
def fix_hummus_oneoffs(title: str, identity: str) -> str | None:
    if identity in HUMMUS_COLLAPSE:
        return HUMMUS_COLLAPSE[identity]
    # Dessert/chocolate/etc. "Dip" with hummus in title → Hummus
    if identity == "Dip" and "hummus" in (title or "").lower():
        return "Hummus"
    return None


# --- Bare-Jerky → meat-typed jerky (F9 partial)
JERKY_TYPE_REMAP = [
    ("beef",     "Beef Jerky"),
    ("turkey",   "Turkey Jerky"),
    ("pork",     "Pork Jerky"),
    ("salmon",   "Salmon Jerky"),
    ("chicken",  "Chicken Jerky"),
    ("bacon",    "Bacon Jerky"),
    ("mushroom", "Mushroom Jerky"),
    ("coconut",  "Coconut Jerky"),
    ("beet",     "Beet Jerky"),
    ("soy",      "Soy Jerky"),
    ("vegan",    "Vegan Jerky"),
    ("plant-based","Plant-Based Jerky"),
    ("plant based","Plant-Based Jerky"),
]
def fix_bare_jerky(title: str, identity: str) -> str | None:
    if identity != "Jerky": return None
    t = (title or "").lower()
    for kw, new_id in JERKY_TYPE_REMAP:
        if kw in t: return new_id
    return None


# ----- Bread short-name to full-name rename -----
# The LLM gave some bread types short names (e.g. "Rye") and others full names
# (e.g. "Rye Bread"). Normalize to the full form so the same product class
# doesn't split across two identities.
BREAD_FULL_NAMES = {
    "Rye":             "Rye Bread",
    "Pumpernickel":    "Pumpernickel Bread",
    "Sourdough":       "Sourdough Bread",
    "Whole Wheat":     "Whole Wheat Bread",
    "Wheat":           "Wheat Bread",
    "White":           "White Bread",
    "Multigrain":      "Multigrain Bread",
    "Multi Grain":     "Multigrain Bread",
    "Italian":         "Italian Bread",
    "French":          "French Bread",
    "Brown":           "Brown Bread",
    "Brioche":         "Brioche",      # already full name, keep
    "Ciabatta":        "Ciabatta",     # already full name, keep
    "Baguette":        "Baguette",     # already full name, keep
}

# Pattern-based bread-type detection — when the LLM gives a compound identity
# like "Rye Caraway" or "Caraway Rye Marble", we recognize it as a Rye Bread
# product with leftover words as modifier. Order: most-specific patterns first.
BREAD_PATTERNS = [
    ("whole wheat",  "Whole Wheat Bread"),
    ("multigrain",   "Multigrain Bread"),
    ("multi grain",  "Multigrain Bread"),
    ("pumpernickel", "Pumpernickel Bread"),
    ("sourdough",    "Sourdough Bread"),
    ("rye",          "Rye Bread"),
    ("french bread", "French Bread"),
    ("italian bread","Italian Bread"),
    ("white bread",  "White Bread"),
    ("brown bread",  "Brown Bread"),
]


_BREAD_CANONICAL_FORMS = set(BREAD_FULL_NAMES.values())


def normalize_bread_identity(identity: str) -> tuple[str, list[str]] | None:
    """Returns (canonical_identity, leftover_modifier_tokens) when the LLM
    identity contains a bread-type word but is a compound (e.g. 'Rye Caraway').
    Returns None if identity is already canonical or doesn't match any pattern."""
    direct = BREAD_FULL_NAMES.get(identity)
    if direct and direct != identity:
        return direct, []
    if identity in _BREAD_CANONICAL_FORMS:
        return None  # already in full canonical form (e.g. 'Rye Bread')
    id_l = identity.lower()
    for pat, full in BREAD_PATTERNS:
        if pat in id_l:
            if full.lower() == id_l:
                return None
            leftover = id_l.replace(pat, " ").strip()
            leftover_tokens = [w for w in re.split(r"\s+", leftover)
                               if w and w != "bread"]
            return full, leftover_tokens
    return None


# ----- Smart roll/bun format detector -----
# Catches titles like "BRIOCHE PETITE ROLLS" where the style and format word
# are separated by other words. Substring matching wouldn't catch this; we
# need to detect rolls/buns presence separately and look for any style word.
# Function-words win over style-words: "BRIOCHE DINNER ROLLS" → Dinner Rolls
# (with Brioche as modifier), not Brioche Rolls. Function = what the product is
# *for* / shape; Style = dough/material.
ROLL_STYLE_TO_IDENTITY = {
    # FUNCTION/USE-FIRST — function defines the product, style is modifier.
    # Critically: "hamburger roll" = "hamburger bun" in retail; route to BUN
    # identity so the canonical structure is Bakery > Buns > Hamburger Buns >
    # Brioche (function-first), not Bakery > Rolls > Brioche Rolls > Hamburger.
    "hamburger":    "Hamburger Buns",
    "burger":       "Hamburger Buns",
    "cheeseburger": "Hamburger Buns",
    "hot dog":      "Hot Dog Buns",
    "hotdog":       "Hot Dog Buns",
    "slider":       "Slider Buns",
    "brat":         "Brat Buns",
    # Roll functions (no bun equivalent)
    "dinner":       "Dinner Rolls",
    "crescent":     "Crescent Rolls",
    "sandwich":     "Sandwich Rolls",
    "sub":          "Sub Rolls",
    "hoagie":       "Hoagie Rolls",
    "kaiser":       "Kaiser Rolls",
    "sweet":        "Sweet Rolls",
    "bolillo":      "Bolillo Rolls",
    # STYLE/MATERIAL (only used when no function word in title)
    "brioche":      "Brioche Rolls",
    "ciabatta":     "Ciabatta Rolls",
    "hawaiian":     "Hawaiian Rolls",
    "french":       "French Rolls",
    "italian":      "Italian Rolls",
    "portuguese":   "Portuguese Rolls",
    "pretzel":      "Pretzel Rolls",
    "focaccia":     "Focaccia Rolls",
    "sourdough":    "Sourdough Rolls",
    "potato":       "Potato Rolls",
}
BUN_STYLE_TO_IDENTITY = {
    # FUNCTION/USE-FIRST
    "hamburger":    "Hamburger Buns",
    "burger":       "Hamburger Buns",
    "cheeseburger": "Hamburger Buns",
    "hot dog":      "Hot Dog Buns",
    "hotdog":       "Hot Dog Buns",
    "slider":       "Slider Buns",
    "brat":         "Brat Buns",
    "sandwich":     "Sandwich Buns",
    # STYLE/MATERIAL
    "brioche":      "Brioche Buns",
    "pretzel":      "Pretzel Buns",
    "potato":       "Potato Buns",
    "milk":         "Milk Buns",
    "kaiser":       "Kaiser Rolls",  # kaiser bun = kaiser roll, retail uses both
}


def detect_roll_bun_format(title: str, current_identity: str) -> str | None:
    """If title has 'rolls' or 'buns' anywhere AND a known style word
    elsewhere, force identity to the matching specific format. Allows
    arbitrary words between (e.g. 'BRIOCHE PETITE ROLLS' → 'Brioche Rolls')."""
    t = " " + (title or "").lower() + " "
    has_rolls = (" rolls " in t) or (" roll " in t) or (" rolls," in t) or (" roll," in t)
    has_buns  = (" buns "  in t) or (" bun "  in t) or (" buns," in t) or (" bun," in t)
    if not (has_rolls or has_buns):
        return None
    # Match style + format pairs
    if has_rolls:
        for style, new_id in ROLL_STYLE_TO_IDENTITY.items():
            if " " + style + " " in t or " " + style + "," in t:
                return new_id
        return "Rolls"  # generic — title says rolls but no recognized style
    if has_buns:
        for style, new_id in BUN_STYLE_TO_IDENTITY.items():
            if " " + style + " " in t or " " + style + "," in t:
                return new_id
        return "Buns"
    return None


# ----- Title-to-identity strong override -----
# For products with a distinctive name (biscotti, churros, etc.), override the
# LLM's identity REGARDLESS of what it picked. This catches cases where the
# LLM lumped a niche product into "Cookies" / "Bread" / "Buns" because its hint
# table was too narrow. Runs after the per-identity fix_X functions.
TITLE_TO_IDENTITY: list[tuple[str, str]] = [
    # Italian baked goods
    ("biscottini",  "Biscotti"),
    ("biscotti",    "Biscotti"),
    # Spanish / Mexican fried dough
    ("churro",      "Churros"),
    # Bread family that the LLM often misses by identity
    ("crouton",     "Croutons"),
    ("breadcrumb",  "Bread Crumbs"),
    ("panko",       "Bread Crumbs"),
    ("bagel chip",  "Bagel Chips"),
    ("pita chip",   "Pita Chips"),
    # Pastries
    ("cinnamon roll", "Cinnamon Rolls"),
    ("croissant",   "Croissants"),
    ("danish",      "Danishes"),
    ("eclair",      "Eclairs"),
    ("scone",       "Scones"),
    ("english muffin","English Muffins"),
    # Format-specific bun/roll types we want to refine even when LLM already
    # said "Buns" or "Rolls" (generic) — refine to specific type
    ("hamburger bun","Hamburger Buns"),
    ("burger bun",   "Hamburger Buns"),
    ("hot dog bun",  "Hot Dog Buns"),
    ("hotdog bun",   "Hot Dog Buns"),
    ("slider bun",   "Slider Buns"),
    ("slider",       "Slider Buns"),
    ("pretzel bun",  "Pretzel Buns"),
    ("brioche bun",  "Brioche Buns"),
    ("dinner roll",  "Dinner Rolls"),
    ("crescent roll","Crescent Rolls"),
    # Niche bread types that often get lumped as Bread
    ("bialy",        "Bialys"),
    ("challah",      "Challah"),
    ("babka",        "Babka"),
    ("matzo",        "Matzo"),
    ("matzah",       "Matzo"),
    ("matzoh",       "Matzo"),
    ("naan",         "Naan"),
    ("ciabatta",     "Ciabatta"),
    ("focaccia",     "Focaccia"),
    ("baguette",     "Baguette"),
    ("brioche",      "Brioche"),
    ("flatbread",    "Flatbread"),
    ("flat bread",   "Flatbread"),
    ("lavash",       "Lavash"),
    ("injera",       "Injera"),
    ("paratha",      "Paratha"),
    ("crumpet",      "Crumpets"),
]


def title_to_identity_override(title: str, current_identity: str) -> str | None:
    """If title contains a distinctive product keyword, override the identity.
    Higher-priority than fix_bread / fix_lasagna because the LLM frequently
    lumps niche products into broad identities."""
    t = (title or "").lower()
    for kw, new_id in TITLE_TO_IDENTITY:
        if kw in t and current_identity != new_id:
            return new_id
    return None


# ----- Bread magnet: split rolls / buns / format-specifics from generic Bread -----
# 34% of Bread identity rows are actually rolls, buns, ciabatta, baguettes, etc.
# Order matters — most specific keyword first so "hamburger bun" wins over "bun".
BREAD_REMAP = [
    # Specific bun/roll types (most specific first)
    ("hamburger bun",       "Hamburger Buns"),
    ("burger bun",          "Hamburger Buns"),    # synonym
    ("cheeseburger bun",    "Hamburger Buns"),    # synonym
    ("hot dog bun",         "Hot Dog Buns"),
    ("hotdog bun",          "Hot Dog Buns"),
    ("brat bun",            "Brat Buns"),
    ("pretzel bun",         "Pretzel Buns"),
    ("slider bun",          "Slider Buns"),
    ("brioche bun",         "Brioche Buns"),
    ("sandwich roll",       "Sandwich Rolls"),
    ("sub roll",            "Sub Rolls"),
    ("hoagie roll",         "Hoagie Rolls"),
    ("hoagie",              "Hoagie Rolls"),
    ("kaiser roll",         "Kaiser Rolls"),
    ("kaiser bun",          "Kaiser Rolls"),
    ("kaiser",              "Kaiser Rolls"),
    ("dinner roll",         "Dinner Rolls"),
    ("crescent roll",       "Crescent Rolls"),
    ("brat roll",           "Brat Rolls"),
    ("french roll",         "French Rolls"),
    ("italian roll",        "Italian Rolls"),
    ("portuguese roll",     "Portuguese Rolls"),
    ("bolillo",             "Bolillo Rolls"),
    ("hawaiian roll",       "Hawaiian Rolls"),
    ("slider",              "Slider Buns"),
    # Bread-type + roll/bun specific (must come BEFORE the single-word matches)
    ("ciabatta roll",       "Ciabatta Rolls"),
    ("ciabatta bun",        "Ciabatta Rolls"),
    ("brioche roll",        "Brioche Buns"),
    ("focaccia roll",       "Focaccia Rolls"),
    ("pretzel roll",        "Pretzel Rolls"),
    ("sourdough roll",      "Sourdough Rolls"),
    ("whole wheat roll",    "Whole Wheat Rolls"),
    ("sweet roll",          "Sweet Rolls"),
    # Sweet / quick-bread types — these are their own category, not "Bread"
    ("banana bread",        "Banana Bread"),
    ("pumpkin bread",       "Pumpkin Bread"),
    ("zucchini bread",      "Zucchini Bread"),
    ("cranberry bread",     "Cranberry Bread"),
    ("lemon bread",         "Lemon Bread"),
    ("date bread",          "Date Bread"),
    ("nut bread",           "Nut Bread"),
    ("cinnamon swirl",      "Cinnamon Swirl Bread"),
    ("cinnamon raisin",     "Cinnamon Raisin Bread"),
    ("raisin bread",        "Raisin Bread"),
    # Regional/named bread types
    ("texas toast",         "Texas Toast"),
    ("garlic toast",        "Garlic Bread"),
    ("garlic bread",        "Garlic Bread"),
    ("cheese bread",        "Cheese Bread"),
    ("hawaiian sweet",      "Hawaiian Sweet Bread"),
    ("hawaiian bread",      "Hawaiian Sweet Bread"),
    ("portuguese sweet",    "Portuguese Sweet Bread"),
    ("irish soda",          "Irish Soda Bread"),
    ("soda bread",          "Soda Bread"),
    ("cornbread",           "Cornbread"),
    ("corn bread",          "Cornbread"),
    ("johnnycake",          "Cornbread"),
    ("monkey bread",        "Monkey Bread"),
    ("churro",              "Churros"),
    ("pumpernickel",        "Pumpernickel"),
    ("jewish rye",          "Rye Bread"),
    ("rye bread",           "Rye Bread"),
    ("brown bread",         "Brown Bread"),
    ("anadama",             "Anadama Bread"),
    # Bread family by name (each its own category)
    ("bialy",               "Bialys"),
    ("bialys",              "Bialys"),
    ("ciabatta",            "Ciabatta"),
    ("baguette",            "Baguette"),
    ("brioche",             "Brioche"),
    ("english muffin",      "English Muffins"),
    ("pita",                "Pita Bread"),
    ("naan",                "Naan"),
    ("focaccia",            "Focaccia"),
    ("breadstick",          "Breadsticks"),
    ("bread stick",         "Breadsticks"),
    ("flatbread",           "Flatbread"),
    ("flat bread",          "Flatbread"),
    ("lavash",              "Lavash"),
    ("injera",              "Injera"),
    ("paratha",             "Paratha"),
    ("roti",                "Roti"),
    ("tortilla",            "Tortillas"),
    ("matzo",               "Matzo"),
    ("matzah",              "Matzo"),
    ("matzoh",              "Matzo"),
    ("challah",             "Challah"),
    ("babka",               "Babka"),
    ("stollen",             "Stollen"),
    ("panettone",           "Panettone"),
    ("crumpet",             "Crumpets"),
    ("scone",               "Scones"),
    ("biscotti",            "Biscotti"),
    ("croutons",            "Croutons"),
    ("crouton",             "Croutons"),
    ("breadcrumb",          "Bread Crumbs"),
    ("bread crumb",         "Bread Crumbs"),
    ("panko",               "Bread Crumbs"),
    ("stuffing",            "Stuffing"),
    # Generic fallbacks (least specific last)
    ("rolls",               "Rolls"),
    ("roll",                "Rolls"),
    ("buns",                "Buns"),
    (" bun",                "Buns"),
]
def fix_bread(title: str, identity: str) -> str | None:
    if identity != "Bread": return None
    t = (title or "").lower()
    for kw, new_id in BREAD_REMAP:
        if kw in t: return new_id
    return None  # leave as Bread if no roll/bun/format match


# ----- Frozen Entree magnet: catches diverse Asian/Italian/Mexican dishes -----
FROZEN_ENTREE_REMAP = [
    # Asian
    ("orange chicken",           "Orange Chicken"),
    ("general tso",              "General Tso Chicken"),
    ("kung pao",                 "Kung Pao Chicken"),
    ("sweet and sour",           "Sweet and Sour Chicken"),
    ("teriyaki chicken",         "Teriyaki Chicken"),
    ("teriyaki",                 "Teriyaki"),
    ("sesame chicken",           "Sesame Chicken"),
    ("mongolian beef",           "Mongolian Beef"),
    ("mongolian",                "Mongolian Beef"),
    ("beef broccoli",            "Beef and Broccoli"),
    ("beef and broccoli",        "Beef and Broccoli"),
    ("chicken tikka masala",     "Chicken Tikka Masala"),
    ("tikka masala",             "Tikka Masala"),
    ("butter chicken",           "Butter Chicken"),
    ("pad thai",                 "Pad Thai"),
    ("lo mein",                  "Lo Mein"),
    ("chow mein",                "Chow Mein"),
    ("chop suey",                "Chop Suey"),
    ("fried rice",               "Fried Rice"),
    ("dumpling",                 "Dumplings"),
    ("egg roll",                 "Egg Rolls"),
    ("spring roll",              "Spring Rolls"),
    ("potsticker",               "Potstickers"),
    ("ramen",                    "Ramen"),
    # Italian
    ("chicken parmesan",         "Chicken Parmesan"),
    ("chicken parmigian",        "Chicken Parmesan"),
    ("chicken alfredo",          "Chicken Alfredo"),
    ("fettuccine alfredo",       "Fettuccine Alfredo"),
    ("alfredo",                  "Chicken Alfredo"),
    ("lasagna",                  "Lasagna"),
    ("ravioli",                  "Ravioli"),
    ("tortellini",               "Tortellini"),
    ("manicotti",                "Manicotti"),
    ("stuffed shells",           "Stuffed Shells"),
    ("baked ziti",               "Baked Ziti"),
    ("ziti",                     "Baked Ziti"),
    ("spaghetti",                "Spaghetti"),
    ("rigatoni",                 "Rigatoni"),
    ("penne",                    "Penne"),
    ("gnocchi",                  "Gnocchi"),
    ("bolognese",                "Bolognese"),
    ("meatball",                 "Meatballs"),
    # Mexican
    ("burrito",                  "Burritos"),
    ("enchilada",                "Enchiladas"),
    ("fajita",                   "Fajitas"),
    ("quesadilla",               "Quesadillas"),
    ("tamale",                   "Tamales"),
    ("taquito",                  "Taquitos"),
    ("chimichanga",              "Chimichangas"),
    ("chile verde",              "Chile Verde"),
    ("chile relleno",            "Chile Relleno"),
    # Comfort/American
    ("salisbury steak",          "Salisbury Steak"),
    ("beef stroganoff",          "Beef Stroganoff"),
    ("stroganoff",               "Beef Stroganoff"),
    ("shepherd",                 "Shepherds Pie"),
    ("pot pie",                  "Pot Pie"),
    ("meatloaf",                 "Meatloaf"),
    ("mac and cheese",           "Mac and Cheese"),
    ("mac n cheese",             "Mac and Cheese"),
    ("macaroni and cheese",      "Mac and Cheese"),
    ("macaroni & cheese",        "Mac and Cheese"),
    ("chicken pot pie",          "Chicken Pot Pie"),
    ("chicken nugget",           "Chicken Nuggets"),
    ("chicken tender",           "Chicken Tenders"),
    ("chicken strip",            "Chicken Strips"),
    ("chicken wing",             "Chicken Wings"),
    ("buffalo wing",             "Buffalo Wings"),
    ("popcorn chicken",          "Popcorn Chicken"),
    ("fish stick",               "Fish Sticks"),
    ("fish filet",               "Fish Fillets"),
    ("fish fillet",              "Fish Fillets"),
    ("country fried steak",      "Country Fried Steak"),
    ("chicken fried steak",      "Chicken Fried Steak"),
    # Generic fallback
    ("rice bowl",                "Rice Bowl"),
    ("noodle bowl",              "Noodle Bowl"),
]
def fix_frozen_entree(title: str, identity: str) -> str | None:
    if identity != "Frozen Entree": return None
    t = (title or "").lower()
    for kw, new_id in FROZEN_ENTREE_REMAP:
        if kw in t: return new_id
    return None  # leave as Frozen Entree if no specific match


# ----- Seasoning magnet: catches specific seasonings/spices -----
SEASONING_REMAP = [
    ("garlic salt",              "Garlic Salt"),
    ("seasoned salt",            "Seasoned Salt"),
    ("celery salt",              "Celery Salt"),
    ("lemon pepper",             "Lemon Pepper"),
    ("garlic pepper",            "Garlic Pepper"),
    ("italian seasoning",        "Italian Seasoning"),
    ("cajun seasoning",          "Cajun Seasoning"),
    ("cajun",                    "Cajun Seasoning"),
    ("creole seasoning",         "Creole Seasoning"),
    ("greek seasoning",          "Greek Seasoning"),
    ("caribbean jerk",           "Jerk Seasoning"),
    ("jerk seasoning",           "Jerk Seasoning"),
    ("taco seasoning",           "Taco Seasoning"),
    ("fajita seasoning",         "Fajita Seasoning"),
    ("chili seasoning",          "Chili Seasoning"),
    ("ranch seasoning",          "Ranch Seasoning"),
    ("steak seasoning",          "Steak Seasoning"),
    ("poultry seasoning",        "Poultry Seasoning"),
    ("everything bagel",         "Everything Bagel Seasoning"),
    ("adobo",                    "Adobo Seasoning"),
    ("herbs de provence",        "Herbs de Provence"),
    ("ras el hanout",            "Ras el Hanout"),
    ("zaatar",                   "Zaatar"),
    ("za'atar",                  "Zaatar"),
    ("garam masala",             "Garam Masala"),
    ("five spice",               "Five Spice"),
    ("old bay",                  "Old Bay Seasoning"),
    ("chili powder",             "Chili Powder"),
    ("garlic powder",            "Garlic Powder"),
    ("onion powder",             "Onion Powder"),
    ("paprika",                  "Paprika"),
    ("cumin",                    "Cumin"),
    ("oregano",                  "Oregano"),
    ("rosemary",                 "Rosemary"),
    ("thyme",                    "Thyme"),
    ("basil",                    "Basil"),
    ("sage",                     "Sage"),
    ("dill",                     "Dill"),
    ("turmeric",                 "Turmeric"),
    ("cinnamon",                 "Cinnamon"),
    ("nutmeg",                   "Nutmeg"),
    ("ginger",                   "Ginger"),
    ("sea salt",                 "Sea Salt"),
    ("kosher salt",              "Kosher Salt"),
    ("himalayan salt",           "Himalayan Salt"),
]
def fix_seasoning(title: str, identity: str) -> str | None:
    if identity != "Seasoning": return None
    t = (title or "").lower()
    for kw, new_id in SEASONING_REMAP:
        if kw in t: return new_id
    return None


# ----- Trail Mix magnet: single-nut SKUs that got mis-tagged -----
TRAIL_MIX_KEEP = ("trail mix","gorp","mountain mix","party mix","snack mix")
def fix_trail_mix(title: str, identity: str) -> str | None:
    if identity != "Trail Mix": return None
    t = (title or "").lower()
    if any(kw in t for kw in TRAIL_MIX_KEEP):
        return None
    # Reuse the Mixed Nuts logic — single-nut titles route to single-nut ID
    for kw, new_id in MIXED_NUTS_REMAP:
        if kw in t: return new_id
    return None


# ----- Meal Starter magnet: cooking-base products -----
MEAL_STARTER_REMAP = [
    ("hamburger helper",         "Hamburger Helper"),
    ("tuna helper",              "Tuna Helper"),
    ("chicken helper",           "Chicken Helper"),
    ("dinner kit",               "Dinner Kit"),
    ("taco kit",                 "Taco Kit"),
    ("burrito kit",              "Burrito Kit"),
    ("fajita kit",               "Fajita Kit"),
    ("rice kit",                 "Rice Kit"),
    ("pad thai",                 "Pad Thai Kit"),
    ("biryani",                  "Biryani Kit"),
    ("paella",                   "Paella Kit"),
    ("risotto",                  "Risotto Mix"),
    ("polenta",                  "Polenta Mix"),
    ("falafel",                  "Falafel Mix"),
    ("hummus mix",               "Hummus Mix"),
    ("tabbouleh",                "Tabbouleh"),
    ("couscous",                 "Couscous"),
    ("quinoa",                   "Quinoa Mix"),
    ("brown rice",               "Brown Rice Mix"),
    ("rice mix",                 "Rice Mix"),
    ("rice pilaf",               "Rice Pilaf"),
    ("stuffing",                 "Stuffing Mix"),
]
def fix_meal_starter(title: str, identity: str) -> str | None:
    if identity != "Meal Starter": return None
    t = (title or "").lower()
    for kw, new_id in MEAL_STARTER_REMAP:
        if kw in t: return new_id
    return None


# ----- Soup magnet: bisques, menudos, etc. -----
SOUP_REMAP = [
    ("lobster bisque",           "Bisque"),
    ("seafood bisque",           "Bisque"),
    ("tomato bisque",            "Bisque"),
    ("bisque",                   "Bisque"),
    ("chowder",                  "Chowder"),
    ("clam chowder",             "Clam Chowder"),
    ("corn chowder",             "Corn Chowder"),
    ("menudo",                   "Menudo"),
    ("gazpacho",                 "Gazpacho"),
    ("minestrone",               "Minestrone"),
    ("pho",                      "Pho"),
    ("ramen",                    "Ramen"),
    ("borscht",                  "Borscht"),
    ("tom yum",                  "Tom Yum"),
    ("tom kha",                  "Tom Kha"),
    ("miso soup",                "Miso Soup"),
    ("egg drop",                 "Egg Drop Soup"),
    ("hot and sour",             "Hot and Sour Soup"),
    ("wonton",                   "Wonton Soup"),
    ("french onion",             "French Onion Soup"),
    ("split pea",                "Split Pea Soup"),
    ("posole",                   "Posole"),
    ("pozole",                   "Posole"),
    ("matzo ball",               "Matzo Ball Soup"),
]
def fix_soup(title: str, identity: str) -> str | None:
    if identity != "Soup": return None
    t = (title or "").lower()
    if "soup" in t:  # title says soup → keep generic
        # Still allow specific subtype if present
        for kw, new_id in SOUP_REMAP:
            if kw in t: return new_id
        return None
    for kw, new_id in SOUP_REMAP:
        if kw in t: return new_id
    return None


# ----- Salad Dressing magnet -----
SALAD_DRESSING_REMAP = [
    ("balsamic vinaigrette",     "Balsamic Vinaigrette"),
    ("white balsamic vinaigrette","White Balsamic Vinaigrette"),
    ("italian vinaigrette",      "Italian Vinaigrette"),
    ("greek vinaigrette",        "Greek Vinaigrette"),
    ("red wine vinaigrette",     "Red Wine Vinaigrette"),
    ("champagne vinaigrette",    "Champagne Vinaigrette"),
    ("raspberry vinaigrette",    "Raspberry Vinaigrette"),
    ("vinaigrette",              "Vinaigrette"),
    ("italian dressing",         "Italian Dressing"),
    ("italian salad dressing",   "Italian Dressing"),
    ("ranch dressing",           "Ranch Dressing"),
    ("ranch",                    "Ranch Dressing"),
    ("caesar dressing",          "Caesar Dressing"),
    ("caesar",                   "Caesar Dressing"),
    ("blue cheese dressing",     "Blue Cheese Dressing"),
    ("blue cheese",              "Blue Cheese Dressing"),
    ("thousand island",          "Thousand Island Dressing"),
    ("french dressing",          "French Dressing"),
    ("russian dressing",         "Russian Dressing"),
    ("greek dressing",           "Greek Dressing"),
    ("honey mustard dressing",   "Honey Mustard Dressing"),
    ("ginger dressing",          "Ginger Dressing"),
    ("poppyseed",                "Poppyseed Dressing"),
    ("poppy seed",               "Poppyseed Dressing"),
    ("green goddess",            "Green Goddess Dressing"),
    ("salad cream",              "Salad Cream"),
]
def fix_salad_dressing(title: str, identity: str) -> str | None:
    if identity != "Salad Dressing": return None
    t = (title or "").lower()
    for kw, new_id in SALAD_DRESSING_REMAP:
        if kw in t: return new_id
    return None


# ----- Skillet Meal magnet -----
SKILLET_MEAL_REMAP = [
    ("beef stroganoff",          "Beef Stroganoff"),
    ("beef pasta",               "Beef Pasta"),
    ("cheeseburger",             "Cheeseburger Skillet"),
    ("chicken teriyaki",         "Teriyaki Chicken"),
    ("chicken alfredo",          "Chicken Alfredo"),
    ("beef fajita",              "Beef Fajitas"),
    ("chicken fajita",           "Chicken Fajitas"),
    ("fajita",                   "Fajitas"),
    ("stir fry",                 "Stir Fry"),
    ("stir-fry",                 "Stir Fry"),
    ("teriyaki",                 "Teriyaki"),
    ("orange chicken",           "Orange Chicken"),
    ("kung pao",                 "Kung Pao Chicken"),
    ("sweet and sour",           "Sweet and Sour Chicken"),
    ("meatball",                 "Meatballs"),
    ("shrimp scampi",            "Shrimp Scampi"),
]
def fix_skillet_meal(title: str, identity: str) -> str | None:
    if identity != "Skillet Meal": return None
    t = (title or "").lower()
    for kw, new_id in SKILLET_MEAL_REMAP:
        if kw in t: return new_id
    return None


# --- Lasagna: ID is a magnet for other pasta dishes when title doesn't say lasagna
LASAGNA_REMAP = [
    ("baked ziti",        "Baked Ziti"),
    ("ziti",              "Baked Ziti"),
    ("chicken parmesan",  "Chicken Parmesan"),
    ("chicken parmigian", "Chicken Parmesan"),
    ("chicken alfredo",   "Chicken Alfredo"),
    ("spaghetti",         "Spaghetti"),
    ("rigatoni",          "Rigatoni"),
    ("penne",             "Penne"),
    ("fettuccine",        "Fettuccine"),
    ("cavatappi",         "Cavatappi"),
    ("gemelli",           "Gemelli"),
    ("rotini",            "Rotini"),
    ("macaroni",          "Macaroni"),
    ("bolognese",         "Bolognese"),
    ("meatball",          "Meatballs"),
    ("ravioli",           "Ravioli"),
    ("tortellini",        "Tortellini"),
    ("gnocchi",           "Gnocchi"),
    ("manicotti",         "Manicotti"),
    ("stuffed shells",    "Stuffed Shells"),
    ("chop suey",         "Chop Suey"),
    ("chow mein",         "Chow Mein"),
    ("lo mein",           "Lo Mein"),
]
def fix_lasagna(title: str, identity: str) -> str | None:
    if identity != "Lasagna": return None
    t = (title or "").lower()
    if "lasagna" in t or "lasagne" in t:
        return None
    for kw, new_id in LASAGNA_REMAP:
        if kw in t: return new_id
    return "Pasta Dish"  # generic fallback — at least not Lasagna


# --- Bagels: split bagel pizzas / breakfast sandwiches / stuffed / dogs / chips
def fix_bagels(title: str, identity: str) -> str | None:
    if identity not in ("Bagel", "Bagels"): return None
    t = (title or "").lower()
    # Order matters: most specific first
    if "bagel dog" in t or "bagel pup" in t:
        return "Bagel Dog"
    if "bagel chip" in t:
        return "Bagel Chips"
    if "bagel crisp" in t:
        return "Bagel Crisps"
    if "pizza" in t:
        return "Pizza Bagel"
    if any(kw in t for kw in ("stuffed bagel", "filled with", "cream cheese stuffed",
                              "bagel filled", "stuffed with")):
        return "Stuffed Bagel"
    # Breakfast sandwich: bagel + egg/sausage/ham/bacon (the meat is the giveaway)
    if any(kw in t for kw in (" egg ", "egg ", "sausage", "ham,", "ham ", "bacon",
                              "turkey sausage", "tky sausage", "turkey ham", "tky ham",
                              "breakfast bagel", "bagel sandwich")):
        # Real "egg bagels" (the bread style) shouldn't trigger this — they don't have other meat
        if "egg bagel" in t and not any(k in t for k in ("sausage","bacon","ham","cheese,","cheese ","turkey","tky")):
            return None
        return "Breakfast Bagel Sandwich"
    return None


KNOWN_FIXERS = [
    fix_apple_chips,
    fix_apple_snack_pack,
    fix_mixed_nuts,
    fix_barbecue_sauce,
    fix_bark,
    fix_broccoli_cheese,
    fix_butter,
    fix_cake,
    fix_candied_fruit,
    fix_pizza_crust_mix,
    fix_soda,
    fix_sparkling_water,
    fix_hummus_oneoffs,
    fix_bare_jerky,
    fix_bagels,
    fix_bread,
    fix_lasagna,
    fix_frozen_entree,
    fix_seasoning,
    fix_trail_mix,
    fix_meal_starter,
    fix_soup,
    fix_salad_dressing,
    fix_skillet_meal,
]


# ---------------- Path canonicalization ----------------
# F9, F10, F12, F14, F17 all share: same identity, multiple paths.
# Strategy: (1) collapse path synonyms (identity-agnostic regex);
# (2) BFC-driven overrides for canned-fruit mis-routing (F11);
# (3) identity → canonical-path map for known consolidated trees.

# Identity-agnostic synonym collapse (left=variants, right=canonical)
PATH_SYNONYMS = [
    # F10: juice tree
    (r"^Beverage > Fruit-based Drinks$", "Beverage > Juice"),
    (r"^Beverage > Fruit-based Drinks > Juice( > .*)?$", "Beverage > Juice"),
    # F12: canned seafood
    (r"^Pantry > Canned Fish & Seafood$", "Pantry > Canned Seafood"),
    (r"^Pantry > Canned Tuna$", "Pantry > Canned Seafood"),
    (r"^Pantry > Canned & Jarred Vegetables$", "Pantry > Canned Vegetables"),
    (r"^Pantry > Canned & Jarred$", "Pantry > Canned"),
    # F9: jerky tree
    (r"^Snack > Jerky & Meat Snacks$", "Snack > Jerky"),
    (r"^Snack > Meat Snacks$", "Snack > Jerky"),
    (r"^Meat & Seafood > Jerky( & Meat Snacks)?$", "Snack > Jerky"),
    # Syrup tree (user's example)
    (r"^Pantry > Syrups$", "Pantry > Sweeteners > Syrup"),
    (r"^Pantry > Syrups & Molasses$", "Pantry > Sweeteners > Syrup"),
    (r"^Pantry > Sweeteners > Syrup > Syrup$", "Pantry > Sweeteners > Syrup"),
    # F17: oat tree
    (r"^Pantry > Hot Cereal > Oatmeal( > Oats)?$", "Pantry > Grain > Oats"),
    (r"^Pantry > Grain > Oats > Hot$", "Pantry > Grain > Oats"),
]
PATH_SYNONYMS_COMPILED = [(re.compile(p), r) for p, r in PATH_SYNONYMS]

# BFC says fruit but path says vegetables → force canned fruit (F11)
# BFC says dry pasta but path is cooked-dish/etc → force Pantry > Pasta
# BFC says baking mix but path is finished-bakery → force Pantry > Baking Mixes
def bfc_path_override(bfc: str, identity: str, path: str) -> str | None:
    bfc_l = (bfc or "").lower()
    p = path or ""
    if "canned fruit" in bfc_l and "Canned Vegetables" in p:
        return "Pantry > Canned Fruit"
    if "pasta by shape" in bfc_l or bfc_l.startswith("pasta shape"):
        if not p.startswith("Pantry > Pasta"):
            return "Pantry > Pasta"
    # Baking mixes / batters / doughs: catch any BFC indicating a *mix* /
    # *batter* / *dough* product. Examples:
    #   "Baking/Cooking Mixes/Supplies", "Bread & Muffin Mixes",
    #   "Cake Mixes", "Cookie Mixes", "Brownie Mixes", "Pancake Mixes",
    #   "Crusts & Dough" (when not already pasta).
    if (
        ("baking" in bfc_l and ("mix" in bfc_l or "supplies" in bfc_l))
        or "muffin mix" in bfc_l
        or "bread & muffin" in bfc_l
        or "cake mix" in bfc_l
        or "cookie mix" in bfc_l
        or "brownie mix" in bfc_l
        or "pancake mix" in bfc_l
        or "biscuit mix" in bfc_l
        or "stuffing mix" in bfc_l
        or "dessert mix" in bfc_l
        or bfc_l.endswith(" mixes")
        or bfc_l.endswith(" mix")
    ):
        if not p.startswith("Pantry > Baking Mixes"):
            return "Pantry > Baking Mixes"
    return None


# When BFC indicates a baking mix / batter / dough, rename the LLM's identity
# to its "*Mix" version so the retail tree has Bread Mix / Cake Mix / Cookie
# Mix as separate leaves from finished Bread / Cake / Cookies.
BAKING_MIX_IDENTITY_MAP = {
    "Bread":         "Bread Mix",
    "Bread Sticks":  "Bread Stick Mix",
    "Cake":          "Cake Mix",
    "Cupcakes":      "Cupcake Mix",
    "Cookies":       "Cookie Mix",
    "Biscuits":      "Biscuit Mix",
    "Brownie":       "Brownie Mix",
    "Brownies":      "Brownie Mix",
    "Muffins":       "Muffin Mix",
    "Pancakes":      "Pancake Mix",
    "Waffles":       "Waffle Mix",
    "Doughnuts":     "Doughnut Mix",
    "Donuts":        "Doughnut Mix",
    "Sweet Rolls":   "Sweet Roll Mix",
    "Cinnamon Rolls":"Cinnamon Roll Mix",
    "Scones":        "Scone Mix",
    "Pie":           "Pie Mix",
    "Pizza Crust Mix":"Pizza Crust Mix",   # already a mix, leave
    "Pancake Mix":   "Pancake Mix",         # already a mix
    "Cake Mix":      "Cake Mix",            # already a mix
    "Bread Mix":     "Bread Mix",           # already a mix
}
def bfc_identity_override(identity: str, bfc: str) -> str | None:
    """Return new identity if BFC says baking mix and identity has a *Mix mapping.
    Returns None when no override applies."""
    bfc_l = (bfc or "").lower()
    is_mix_bfc = (
        ("baking" in bfc_l and ("mix" in bfc_l or "supplies" in bfc_l))
        or "muffin mix" in bfc_l
        or "bread & muffin" in bfc_l
        or "cake mix" in bfc_l
        or "cookie mix" in bfc_l
        or "brownie mix" in bfc_l
        or "pancake mix" in bfc_l
        or "biscuit mix" in bfc_l
        or "stuffing mix" in bfc_l
        or "dessert mix" in bfc_l
        or bfc_l.endswith(" mixes")
        or bfc_l.endswith(" mix")
    )
    if not is_mix_bfc:
        return None
    return BAKING_MIX_IDENTITY_MAP.get(identity)

# Hard spelling unification — applied AFTER plural collapse, BEFORE path
# resolution. Forces one canonical surface form per concept (donut/doughnut,
# muffin variants) regardless of which spelling the LLM picked.
SPELLING_UNIFY = {
    "Donut":           "Doughnuts",
    "Donuts":          "Doughnuts",
    "Doughnut":        "Doughnuts",
    "Donut Hole":      "Doughnut Holes",
    "Donut Holes":     "Doughnut Holes",
    "Doughnut Hole":   "Doughnut Holes",
    "Donut Mix":       "Doughnut Mix",
    "Mini Donuts":     "Doughnuts",
    "Mini Doughnuts":  "Doughnuts",
}

# Identity-driven path consolidation (F17 oats, others)
IDENTITY_TO_PATH = {
    # F17: all oat-grain forms → one parent
    "Oatmeal":         "Pantry > Grain > Oats",
    "Oats":            "Pantry > Grain > Oats",
    "Steel Cut Oats":  "Pantry > Grain > Oats",
    "Rolled Oats":     "Pantry > Grain > Oats",
    "Instant Oatmeal": "Pantry > Grain > Oats",
    "Overnight Oats":  "Pantry > Grain > Oats",
    # Syrup family (user-flagged)
    "Syrup":           "Pantry > Sweeteners > Syrup",
    "Maple Syrup":     "Pantry > Sweeteners > Syrup",
    "Pancake Syrup":   "Pantry > Sweeteners > Syrup",
    "Agave Syrup":     "Pantry > Sweeteners > Syrup",
    "Honey":           "Pantry > Sweeteners > Honey",
    "Molasses":        "Pantry > Sweeteners > Molasses",
    # Buns: sibling of Bread under Bakery (not child of Bread)
    "Buns":            "Bakery > Buns",
    "Hamburger Buns":  "Bakery > Buns",
    "Hot Dog Buns":    "Bakery > Buns",
    "Brat Buns":       "Bakery > Buns",
    "Pretzel Buns":    "Bakery > Buns",
    "Slider Buns":     "Bakery > Buns",
    "Brioche Buns":    "Bakery > Buns",
    "Sandwich Buns":   "Bakery > Buns",
    # Rolls: sibling of Bread under Bakery
    "Rolls":           "Bakery > Rolls",
    "Sandwich Rolls":  "Bakery > Rolls",
    "Sub Rolls":       "Bakery > Rolls",
    "Hoagie Rolls":    "Bakery > Rolls",
    "Kaiser Rolls":    "Bakery > Rolls",
    "Dinner Rolls":    "Bakery > Rolls",
    "Crescent Rolls":  "Bakery > Rolls",
    "Brat Rolls":      "Bakery > Rolls",
    "French Rolls":    "Bakery > Rolls",
    "Italian Rolls":   "Bakery > Rolls",
    "Portuguese Rolls":"Bakery > Rolls",
    "Bolillo Rolls":   "Bakery > Rolls",
    "Hawaiian Rolls":  "Bakery > Rolls",
    "Ciabatta Rolls":  "Bakery > Rolls",
    "Focaccia Rolls":  "Bakery > Rolls",
    "Pretzel Rolls":   "Bakery > Rolls",
    "Sourdough Rolls": "Bakery > Rolls",
    "Whole Wheat Rolls": "Bakery > Rolls",
    "Sweet Rolls":     "Bakery > Rolls",
    "Brioche Rolls":   "Bakery > Rolls",
    "Potato Rolls":    "Bakery > Rolls",
    "Potato Buns":     "Bakery > Buns",
    "Milk Buns":       "Bakery > Buns",
    # Real duplicate identities (per duplicate_paths_report.txt audit) —
    # consolidate to one canonical parent so the same product isn't scattered.
    "Cookie Dough":     "Pantry > Baking Mixes > Cookie Dough",
    "Cookie Dough Bites":"Bakery > Cookie Dough",
    "Cheesecake":       "Bakery > Cheesecake",
    "Bread Pudding":    "Dairy > Pudding > Bread Pudding",
    "Mousse":           "Dairy > Mousse",
    "Arepas":           "Bakery > Arepas",
    "Knishes":          "Bakery > Pastry > Knishes",
    "Samosas":          "Frozen > Appetizers & Snacks > Samosas",
    "Tostones":         "Snack > Veggie Snacks > Tostones",
    "Hushpuppies":      "Bakery > Hushpuppies",
    "Acai Bowl":        "Frozen > Bowls > Acai Bowl",
    "Crab Cakes":       "Meat & Seafood > Crab > Crab Cakes",
    "Crab Cake":        "Meat & Seafood > Crab > Crab Cakes",
    "Crab Cake Mix":    "Pantry > Baking Mixes > Crab Cake Mix",
    "Fish Cake":        "Meat & Seafood > Seafood > Fish Cakes",
    "Fish Cakes":       "Meat & Seafood > Seafood > Fish Cakes",
    "Salmon Cake":      "Meat & Seafood > Salmon > Salmon Cakes",
    "Salmon Cakes":     "Meat & Seafood > Salmon > Salmon Cakes",
    "Beef Cake":        "Meat & Seafood > Beef > Beef Patties",
    "Beef Cakes":       "Meat & Seafood > Beef > Beef Patties",
    "Rice Cakes":       "Snack > Rice Cakes",
    "Rice Cake":        "Snack > Rice Cakes",
    "Brownies":         "Bakery > Brownies",
    "Brownie":          "Bakery > Brownies",
    "Brownie Bites":    "Bakery > Brownies > Brownie Bites",
    "Brownie Brittle":  "Snack > Brittle",
    "Brownie Mix":      "Pantry > Baking Mixes > Brownie Mix",
    "Danish":           "Bakery > Pastry > Danishes",
    "Danishes":         "Bakery > Pastry > Danishes",
    "Croissant":        "Bakery > Pastry > Croissants",
    "Eclair":           "Bakery > Pastry > Eclairs",
    "Scone":            "Bakery > Scones",
    "Muffin":           "Bakery > Muffins",
    "Cupcake":          "Bakery > Cupcakes",
    "Cookie":           "Snack > Cookies",
    "Doughnut":         "Bakery > Doughnuts",
    "Donut":            "Bakery > Doughnuts",
    "Donuts":           "Bakery > Doughnuts",
    "Donut Holes":      "Bakery > Doughnuts > Doughnut Holes",
    "Doughnut Holes":   "Bakery > Doughnuts > Doughnut Holes",
    "Cruller":          "Bakery > Doughnuts > Crullers",
    "Crullers":         "Bakery > Doughnuts > Crullers",
    "Twinkies":         "Bakery > Snack Cakes > Twinkies",
    "Twinkie":          "Bakery > Snack Cakes > Twinkies",
    "Snack Cakes":      "Bakery > Snack Cakes",
    "Snack Cake":       "Bakery > Snack Cakes",
    "Honey Bun":        "Bakery > Snack Cakes > Honey Buns",
    "Honey Buns":       "Bakery > Snack Cakes > Honey Buns",
    "Fritter":          "Bakery > Pastry > Fritters",
    "Fritters":         "Bakery > Pastry > Fritters",
    "Apple Fritters":   "Bakery > Pastry > Fritters > Apple",
    "Apple Fritter":    "Bakery > Pastry > Fritters > Apple",
    "Eclair":           "Bakery > Pastry > Eclairs",
    "Strudels":         "Bakery > Pastry > Strudel",
    "Turnovers":        "Bakery > Pastry > Turnover",
    "Knish":            "Bakery > Pastry > Knishes",
    "Tart":             "Bakery > Pastry > Tart",
    "Tarts":            "Bakery > Pastry > Tart",
    "Pastry":           "Bakery > Pastry",
    "Pastries":         "Bakery > Pastry",
    "Sweet Bread":      "Bakery > Sweet Breads",
    "Quick Bread":      "Bakery > Sweet Breads",
    "Gefilte Fish":     "Pantry > Canned Seafood > Gefilte Fish",
    "Mochi":            "Frozen > Mochi",
    "Apple Crisp":      "Bakery > Crisps > Apple Crisp",
    "Crepes":           "Bakery > Crepes",
    "Crumble":          "Bakery > Crumble",
    "Turnover":         "Bakery > Pastry > Turnover",
    "Stuffed Mushrooms":"Frozen > Appetizers & Snacks > Stuffed Mushrooms",
    "Stuffed Jalapenos":"Frozen > Appetizers & Snacks > Stuffed Jalapenos",
    "Stuffed Peppers":  "Meal > Composite Dishes > Stuffed Peppers",
    "Pulled Pork":      "Meat & Seafood > Pork > Pulled Pork",
    "Smoked Sausage":   "Meat & Seafood > Sausage > Smoked Sausage",
    "Egg Bites":        "Frozen > Breakfast Sandwiches > Egg Bites",
    "Chicken Bites":    "Meat & Seafood > Poultry > Chicken Bites",
    "Chicken Strips":   "Meat & Seafood > Poultry > Chicken Strips",
    "Chicken Tenders":  "Meat & Seafood > Poultry > Chicken Tenders",
    "Chicken Wings":    "Meat & Seafood > Poultry > Chicken Wings",
    "Calamari":         "Meat & Seafood > Seafood > Calamari",
    "Mussels":          "Meat & Seafood > Seafood > Mussels",
    "Squid":            "Meat & Seafood > Seafood > Squid",
    "Meatballs":        "Meat & Seafood > Meatballs",
    "Dumplings":        "Frozen > Dumplings",
    "Pierogies":        "Frozen > Dumplings > Pierogies",
    "Potstickers":      "Frozen > Dumplings > Potstickers",
    "Wontons":          "Frozen > Dumplings > Wontons",
    "Shumai":           "Frozen > Dumplings > Shumai",
    # Pasta shapes — for retail SKUs LLM put in dish categories. Force to Pantry > Pasta.
    "Penne":            "Pantry > Pasta > Penne",
    "Rotini":           "Pantry > Pasta > Rotini",
    "Ravioli":          "Pantry > Pasta > Ravioli",
    "Stuffed Shells":   "Pantry > Pasta > Stuffed Shells",
    "Gnocchi":          "Pantry > Pasta > Gnocchi",
    "Manicotti":        "Pantry > Pasta > Manicotti",
    "Tortellini":       "Pantry > Pasta > Tortellini",
    # Pretzel-related (often misshelved)
    "Pretzels":         "Snack > Pretzels",
    # Other Bakery siblings — own categories not children of Bread
    "Breadsticks":     "Bakery > Breadsticks",
    "English Muffins": "Bakery > English Muffins",
    "Pita Bread":      "Bakery > Pita Bread",
    "Naan":            "Bakery > Naan",
    "Tortillas":       "Bakery > Tortillas",
    "Flatbread":       "Bakery > Flatbread",
    "Cornbread":       "Bakery > Cornbread",
    "Challah":         "Bakery > Challah",
    "Babka":           "Bakery > Babka",
    "Stollen":         "Bakery > Stollen",
    "Panettone":       "Bakery > Panettone",
    "Matzo":           "Bakery > Matzo",
    "Lavash":          "Bakery > Lavash",
    "Injera":          "Bakery > Injera",
    "Paratha":         "Bakery > Paratha",
    "Roti":            "Bakery > Roti",
    "Crumpets":        "Bakery > Crumpets",
    "Biscotti":        "Bakery > Biscotti",
    "Bialys":          "Bakery > Bagels",  # bialys are flat bagels, lump together
    "Croutons":        "Bakery > Croutons",
    "Bread Crumbs":    "Pantry > Bread Crumbs",
    "Stuffing":        "Pantry > Stuffing",
    # Sweet/quick breads — own siblings, sold differently from sandwich bread
    "Banana Bread":    "Bakery > Sweet Breads",
    "Pumpkin Bread":   "Bakery > Sweet Breads",
    "Zucchini Bread":  "Bakery > Sweet Breads",
    "Cranberry Bread": "Bakery > Sweet Breads",
    "Lemon Bread":     "Bakery > Sweet Breads",
    "Date Bread":      "Bakery > Sweet Breads",
    "Nut Bread":       "Bakery > Sweet Breads",
    "Cinnamon Swirl Bread":  "Bakery > Sweet Breads",
    "Cinnamon Raisin Bread": "Bakery > Sweet Breads",
    "Raisin Bread":    "Bakery > Sweet Breads",
    "Monkey Bread":    "Bakery > Sweet Breads",
    "Hawaiian Sweet Bread":  "Bakery > Sweet Breads",
    "Portuguese Sweet Bread":"Bakery > Sweet Breads",
    # Specialty/regional that aren't sandwich bread
    # Specific bread TYPES are children of Bread (not siblings).
    "Garlic Bread":    "Bakery > Bread",
    "Texas Toast":     "Bakery > Bread",
    "Cheese Bread":    "Bakery > Bread",
    "Irish Soda Bread":"Bakery > Bread",
    "Soda Bread":      "Bakery > Bread",
    # Pastry-family items (not bread)
    "Churros":         "Bakery > Pastry > Churros",
    "Doughnuts":       "Bakery > Doughnuts",
    "Donuts":          "Bakery > Doughnuts",
    "Croissants":      "Bakery > Pastry > Croissants",
    "Danishes":        "Bakery > Pastry > Danishes",
    "Eclairs":         "Bakery > Pastry > Eclairs",
    "Strudel":         "Bakery > Pastry > Strudel",
    "Cinnamon Rolls":  "Bakery > Pastry > Cinnamon Rolls",
    "Scones":          "Bakery > Scones",
    "Muffins":         "Bakery > Muffins",
}

# ---------------- Auto-generated maps from corpus ----------------

def build_pluralization_map(rows) -> dict:
    """For each pair {X, Xs} or {X, Xes} in identity space, the more common spelling wins.
    Returns {loser: winner} so application is a one-step lookup."""
    id_counts = Counter()
    for o in rows:
        rec = o.get("record", {}) or {}
        if "_parse_error" in rec or "_api_error" in rec: continue
        pid = (rec.get("product_identity") or "").strip()
        if pid:
            id_counts[pid] += 1
    plural_map: dict[str, str] = {}
    for pid in id_counts:
        candidates = []
        if pid + "s" in id_counts:  candidates.append(pid + "s")
        if pid + "es" in id_counts: candidates.append(pid + "es")
        if pid.endswith("es") and pid[:-2] in id_counts: candidates.append(pid[:-2])
        if pid.endswith("s")  and pid[:-1] in id_counts: candidates.append(pid[:-1])
        if not candidates: continue
        all_forms = [pid] + candidates
        winner = max(all_forms, key=lambda f: id_counts[f])
        for f in all_forms:
            if f != winner:
                plural_map[f] = winner
    return plural_map


def build_path_vote_map_from_pairs(id_path_pairs: list, plural_map: dict) -> dict:
    """Build the vote map from a list of (final_identity, final_path_pre_vote)
    tuples produced by the main loop's pass-1. This guarantees the vote sees
    the *exact* same identities and paths as the row writer, so dispatch and
    audit are consistent.
    Format: {identity: {top_level: canonical_path}}"""
    id_to_paths: dict[str, Counter] = defaultdict(Counter)
    for pid, path in id_path_pairs:
        if pid and path:
            id_to_paths[pid][path] += 1

    GENERIC_TOKENS = {"and","with","the","a","of","in","on","mix","food","drink",
                      "snack","sauce","blend","style","flavored","flavor"}

    def name_matches(pid: str, path: str) -> bool:
        """True if path tree contains the identity, or any non-generic word of it.
        Examples that should match (pid → segment):
          'Bagels' → 'Bagels'; 'Pizza Bagels' → 'Bagels' OR 'Pizza';
          'Stuffed Bagel' → 'Bagels'; 'Bagel Thins' → 'Bagels'."""
        pid_n = pid.lower().rstrip("s")
        # tokenize identity: lowercase words (singular form), drop generic
        pid_words = [w.rstrip("s") for w in re.split(r"\W+", pid.lower()) if w]
        pid_words = [w for w in pid_words if w and w not in GENERIC_TOKENS]
        for seg in path.split(">")[1:]:  # skip top-level
            seg_n = seg.strip().lower().rstrip("s")
            if seg_n == pid_n: return True
            # word-level: if any non-generic identity word matches a path segment
            seg_words = [w.rstrip("s") for w in re.split(r"\W+", seg_n) if w]
            if any(w in pid_words for w in seg_words):
                return True
        return False

    vote_map: dict[str, dict[str, str]] = {}
    for pid, paths in id_to_paths.items():
        if len(paths) <= 1: continue
        by_top: dict[str, Counter] = defaultdict(Counter)
        for p, n in paths.items():
            top = p.split(">", 1)[0].strip()
            by_top[top][p] += n
        for top, sub in by_top.items():
            if len(sub) <= 1: continue
            total = sum(sub.values())
            # 1) Prefer any path that names the identity in its tree (specificity wins)
            named = [(p, n) for p, n in sub.items() if name_matches(pid, p)]
            if named:
                winner = max(named, key=lambda pn: pn[1])[0]
                vote_map.setdefault(pid, {})[top] = winner
                continue
            # 2) Fall back to plurality vote, no threshold.
            # When all paths tie at 1 each, pick the shortest (= most general
            # parent node, less likely to be wrong than an oddly-specific leaf).
            best = sorted(sub.items(), key=lambda pn: (-pn[1], len(pn[0]), pn[0]))
            winner = best[0][0]
            vote_map.setdefault(pid, {})[top] = winner
    return vote_map


def build_path_segment_plural_map(rows) -> dict[str, str]:
    """Type 1: For every path segment that appears in singular AND plural form,
    pick the more common spelling. Returns {loser_spelling: winner_spelling}."""
    seg_counts: Counter = Counter()
    for o in rows:
        rec = o.get("record", {}) or {}
        if "_parse_error" in rec or "_api_error" in rec: continue
        path = (rec.get("category_path") or "").strip()
        if not path: continue
        for seg in path.split(">"):
            s = seg.strip()
            if s:
                seg_counts[s] += 1
    seg_plural: dict[str, str] = {}
    for seg in list(seg_counts):
        candidates = []
        if seg + "s" in seg_counts: candidates.append(seg + "s")
        if seg + "es" in seg_counts: candidates.append(seg + "es")
        if seg.endswith("es") and seg[:-2] in seg_counts: candidates.append(seg[:-2])
        if seg.endswith("s") and seg[:-1] in seg_counts:  candidates.append(seg[:-1])
        if not candidates: continue
        all_forms = [seg] + candidates
        winner = max(all_forms, key=lambda f: seg_counts[f])
        for f in all_forms:
            if f != winner:
                seg_plural[f] = winner
    return seg_plural


def normalize_segment_pluralization(path: str, seg_plural: dict[str, str]) -> str:
    """Type 1: apply per-segment plural canonical."""
    if not path or not seg_plural:
        return path
    parts = [s.strip() for s in path.split(">")]
    return " > ".join(seg_plural.get(p, p) for p in parts if p)


def strip_redundant_leaf(path: str) -> str:
    """Type 2: drop leaf segment if it's a singular/plural variant of its parent.
    e.g. 'Bakery > Bagels > Bagel' -> 'Bakery > Bagels'."""
    if not path: return path
    parts = [s.strip() for s in path.split(">") if s.strip()]
    while len(parts) >= 2:
        a = parts[-2].lower().rstrip("s")
        b = parts[-1].lower().rstrip("s")
        if a == b:
            parts = parts[:-1]
        else:
            break
    return " > ".join(parts)


# --------------- Storage-as-facet rewrites (Problem 1) ---------------
# Strip storage-state prefixes ("Frozen >" / "Refrigerated >") from paths whose
# product class exists elsewhere as a top-level. Add the storage to the
# processing_storage facet. Inherently-cold products (ice cream, gelato, etc.)
# are kept untouched.

# Frozen second-level segments that ARE inherently frozen — keep these.
FROZEN_KEEP = {
    "Ice Cream", "Ice Cream & Frozen Yogurt", "Frozen Yogurt", "Gelato",
    "Sorbet", "Sherbet", "Frozen Pops", "Popsicles", "Italian Ice",
    "Frozen Novelties", "Frozen Custard", "Frozen Treats",
    "Pizza",                                      # frozen pizza is a distinct product class
    "Single Entrees", "TV Dinners", "Skillet Meals", "Pot Pies",
    "Burritos", "Lunch Kits",                     # frozen meal prep
    "Appetizers & Snacks", "Breakfast Sandwiches",
    "Breakfast Sandwiches, Biscuits & Meals",
    "Pancakes, Waffles, French Toast & Crepes",
}

# Frozen second-level → product-class top-level remap.
FROZEN_STRIP_MAP = {
    "Vegetables":          "Produce > Vegetables",
    "Potatoes":            "Produce > Vegetables > Potatoes",
    "French Fries":        "Produce > Vegetables > Potatoes > French Fries",
    "Fruit":               "Produce > Fruit",
    "Prepared Vegetables": "Produce > Vegetables",
    "Fish & Seafood":      "Meat & Seafood > Seafood",
    "Seafood":             "Meat & Seafood > Seafood",
    "Poultry":             "Meat & Seafood > Poultry",
    "Beef":                "Meat & Seafood > Beef",
    "Pork":                "Meat & Seafood > Pork",
    "Bacon":               "Meat & Seafood > Bacon",
    "Sausage":             "Meat & Seafood > Sausage",
    "Patties & Burgers":   "Meat & Seafood > Patties & Burgers",
    "Nuggets":             "Meat & Seafood > Nuggets",
    "Meatballs":           "Meat & Seafood > Meatballs",
    "Chicken Wings":       "Meat & Seafood > Poultry > Chicken Wings",
    "Bites":               "Snack > Bites",
    "Smoothies":           "Beverage > Smoothie",
    "Smoothie Bowls":      "Snack > Smoothie Bowls",
    "Juice Concentrate":   "Beverage > Juice > Concentrate",
    "Bread & Dough":       "Bakery > Bread",
    "Bread":               "Bakery > Bread",
    "Bagels":              "Bakery > Bagels",
    "Stuffed Sandwiches":  "Meal > Sandwiches",
    "Empanadas":           "Meal > Empanadas",
    "Bowls":               "Meal > Bowls",
}

# Refrigerated rules
REFRIG_KEEP: set = set()  # nothing inherently refrigerated lives at top-level
REFRIG_STRIP_MAP = {
    "Lunch Kits":          "Meal > Lunch Kits",
    "Dough":               "Bakery > Bread > Dough",
    "Egg Wraps":           "Bakery > Wraps",
    "Wraps":               "Bakery > Wraps",
}

# Singleton-top normalizations (Problem 4)
SINGLETON_TOP_REMAP = {
    "Breakfast":           "Bakery > Breakfast",
    "Desserts":            "Bakery",
    "Deli":                "Meat & Seafood > Deli",
    "Baby Food":           "Baby & Toddler > Baby Food",
}


# ---------------- Master canonical-tree remap ----------------
# Direct path overrides applied LAST. Catches every garbage path / singleton-top /
# nonsensical placement we've found by audit. Edit this dict to extend.
CANONICAL_PATH_REMAP = {
    # ---- Bakery cleanup ----
    "Bakery > Donuts":                            "Bakery > Doughnuts",
    "Bakery > Donuts > Crullers":                 "Bakery > Doughnuts > Crullers",
    "Bakery > Pastries":                          "Bakery > Pastry",
    "Bakery > Cookies":                           "Snack > Cookies",
    "Dairy > Cheesecake":                         "Bakery > Cheesecake",
    "Dairy > Cheesecake Filling":                 "Bakery > Cheesecake",
    "Dairy > Desserts":                           "Bakery > Desserts",
    "Dairy > Pudding & Custard":                  "Dairy > Pudding",
    "Dairy > Pudding & Dessert":                  "Dairy > Pudding",
    "Dairy > Yogurt & Cultured Desserts":         "Dairy > Yogurt",
    "Dairy > Eggs & Egg Substitutes":             "Dairy > Eggs",
    "Dairy > Butter & Spread":                    "Dairy > Butter",
    "Dairy > Cream & Creamers":                   "Dairy > Cream",
    "Dairy > Creamers":                           "Beverage > Coffee Creamer",
    "Dairy > Cream > Flan":                       "Dairy > Pudding > Flan",
    "Dairy > Cream > Creme":                      "Dairy > Cream",
    "Dairy > Cream > Spreads":                    "Dairy > Cream",
    "Dairy > Cream > Instant Pudding Pie":        "Dairy > Pudding",
    # ---- Beverage cleanup ----
    "Beverage > Soda":                            "Beverage > Carbonated > Soda",
    "Beverage > Cocktails & Mixes":               "Beverage > Mixes",
    # ---- Frozen → strip the rest of the storage modifiers ----
    "Frozen > Burgers":                           "Meat & Seafood > Patties & Burgers",
    "Frozen > Patties and Burgers":               "Meat & Seafood > Patties & Burgers",
    "Frozen > Meat Alternatives":                 "Meat & Seafood > Meat Alternatives",
    "Frozen > Fruit & Juice Concentrates":        "Beverage > Juice > Concentrate",
    "Frozen > Prepared Chicken":                  "Meat & Seafood > Poultry > Chicken",
    "Frozen > Chicken Tenders":                   "Meat & Seafood > Poultry > Chicken Tenders",
    "Frozen > Fish Sticks":                       "Meat & Seafood > Seafood > Fish Sticks",
    "Frozen > Cookie Dough":                      "Bakery > Cookie Dough",
    "Frozen > Cheesecake":                        "Bakery > Cheesecake",
    "Frozen > Pie":                               "Bakery > Pie",
    "Frozen > Soup":                              "Pantry > Soup",
    "Frozen > Pierogies":                         "Meal > Dumplings > Pierogies",
    "Frozen > Dumplings":                         "Meal > Dumplings",
    "Frozen > Potstickers":                       "Meal > Dumplings > Potstickers",
    "Frozen > Tamales":                           "Meal > Tamales",
    "Frozen > Taquitos":                          "Meal > Taquitos",
    "Frozen > Corn Dog":                          "Meat & Seafood > Hot Dogs & Sausages > Corn Dog",
    # ---- Pantry garbage paths ----
    "Pantry > Sweeteners > Sugar > Sauce":        "Pantry > Sauces & Salsas",
    "Pantry > Sweeteners > Sugar > Topping":      "Pantry > Dessert Toppings",
    "Pantry > Sweeteners > Sugar > Topping > Whipped Topping": "Dairy > Whipped Toppings",
    "Pantry > Sweeteners > Syrup > Topping":      "Pantry > Dessert Toppings",
    "Pantry > Sweeteners > Syrup > Topping > Whipped Topping": "Dairy > Whipped Toppings",
    "Pantry > Hot Cereal > Oatmeal":              "Pantry > Grain > Oats",
    "Pantry > Hot Cereal > Oatmeal > Oats":       "Pantry > Grain > Oats",
    # ---- Singleton garbage tops ----
    "Baby Food > Baby Food Pouches":              "Baby & Toddler > Baby Food",
    "Baby Food > Fruit & Vegetable Blends":       "Baby & Toddler > Baby Food",
    "Baby Food > Purees":                         "Baby & Toddler > Baby Food",
    "Breakfast > Cereal":                         "Pantry > Cereal",
    "Deli > Prepared Salads":                     "Meat & Seafood > Deli > Salads",
    "Deli > Prepared Sides":                      "Meal > Sides",
    "Desserts > Dessert Sauces & Toppings":       "Pantry > Dessert Toppings",
    "Desserts > Pudding":                         "Dairy > Pudding",
    "Health Care > Oral Care":                    "Sports & Wellness > Oral Care",
    # ---- Produce garbage residuals ----
    "Produce > Corn":                             "Produce > Vegetables",
    "Produce > Spinach":                          "Produce > Vegetables",
    "Produce > Potatoes":                         "Produce > Vegetables > Potatoes",
    "Produce > Berries":                          "Produce > Fruit > Berries",
    "Produce > Dates":                            "Produce > Fruit > Dates",
    "Produce > Dried Fruit":                      "Snack > Dried Fruit",
    "Produce > Vegetables > Potatoes":            "Produce > Vegetables > Potatoes",
    "Produce > Corn > Chef Sides > Sides":        "Meal > Sides",
    "Produce > Prepared Vegetables":              "Produce > Vegetables",
    "Produce > Appetizers & Snacks":              "Snack > Snack Packs",
}


def force_canonical_tree(path: str) -> tuple[str, bool]:
    """Apply CANONICAL_PATH_REMAP. Returns (new_path, changed)."""
    if not path: return path, False
    new = CANONICAL_PATH_REMAP.get(path, path)
    if new != path:
        return new, True
    # Prefix-match for paths that start with a remapped prefix
    for old_prefix, new_prefix in CANONICAL_PATH_REMAP.items():
        if path.startswith(old_prefix + " > "):
            tail = path[len(old_prefix) + 3:]
            return new_prefix + " > " + tail, True
    return path, False


def apply_storage_strip(path: str, proc_storage: list) -> tuple[str, list]:
    """Return (new_path, new_processing_storage_list).
    Strips Frozen / Refrigerated prefixes when the product class exists
    elsewhere; appends the corresponding storage tag to processing_storage."""
    if not path:
        return path, proc_storage
    parts = [s.strip() for s in path.split(">") if s.strip()]
    if not parts:
        return path, proc_storage
    top, rest = parts[0], parts[1:]
    proc = list(proc_storage or [])

    if top == "Frozen" and rest:
        second = rest[0]
        if second in FROZEN_KEEP:
            return path, proc  # keep as-is
        if second in FROZEN_STRIP_MAP:
            new_prefix = FROZEN_STRIP_MAP[second]
            tail = rest[1:]
            new_path = " > ".join([new_prefix] + tail) if tail else new_prefix
            if "frozen" not in proc:
                proc.append("frozen")
            return new_path, proc
        # Unknown Frozen child — leave alone for now
        return path, proc

    if top == "Refrigerated" and rest:
        second = rest[0]
        if second in REFRIG_KEEP:
            return path, proc
        if second in REFRIG_STRIP_MAP:
            new_prefix = REFRIG_STRIP_MAP[second]
            tail = rest[1:]
            new_path = " > ".join([new_prefix] + tail) if tail else new_prefix
            if "refrigerated" not in proc:
                proc.append("refrigerated")
            return new_path, proc
        return path, proc

    if top in SINGLETON_TOP_REMAP and len(parts) == 1:
        return SINGLETON_TOP_REMAP[top], proc

    return path, proc


# Path-segment synonyms: hand-curated, loaded from JSON. Seeded from MODEL_NOTES.
DEFAULT_SEGMENT_SYNONYMS_DICT = {
    # Type 3 — left=variants, right=canonical.
    # Single segment substitutions (case-sensitive) applied path-wide.
    "Fruit-based Drinks": "Juice",
    "Canned Fish & Seafood": "Canned Seafood",
    "Canned Tuna": "Canned Seafood",
    "Canned & Jarred Vegetables": "Canned Vegetables",
    "Jerky & Meat Snacks": "Jerky",
    "Meat Snacks": "Jerky",
    "Syrups": "Syrup",
    "Syrups & Molasses": "Syrup",
}


def apply_segment_synonyms(path: str, syn: dict[str, str]) -> str:
    """Type 3: substitute synonym segments."""
    if not path: return path
    parts = [s.strip() for s in path.split(">") if s.strip()]
    parts = [syn.get(p, p) for p in parts]
    # Collapse adjacent duplicates that result from synonym substitution
    deduped: list[str] = []
    for p in parts:
        if not deduped or deduped[-1].lower() != p.lower():
            deduped.append(p)
    return " > ".join(deduped)


def load_or_build_static_maps(rows, plural_path: Path,
                              seg_plural_path: Path, syn_path: Path,
                              rebuild: bool) -> tuple[dict, dict, dict]:
    """Plural / seg-plural / synonyms only. Vote map is built in pass 1 of main."""
    if not syn_path.exists():
        syn_path.write_text(json.dumps(DEFAULT_SEGMENT_SYNONYMS_DICT, indent=2, sort_keys=True))
        print(f"  seeded {syn_path.name} ({len(DEFAULT_SEGMENT_SYNONYMS_DICT)} entries)")
    syn = json.loads(syn_path.read_text())

    if not rebuild and plural_path.exists() and seg_plural_path.exists():
        plural = json.loads(plural_path.read_text())
        seg_plural = json.loads(seg_plural_path.read_text())
        print(f"  loaded plural ({len(plural)}), segment-plural ({len(seg_plural)}), "
              f"synonyms ({len(syn)}) from JSON")
        return plural, seg_plural, syn

    print(f"  building plural + seg-plural maps from corpus...")
    plural = build_pluralization_map(rows)
    seg_plural = build_path_segment_plural_map(rows)
    plural_path.write_text(json.dumps(plural, indent=2, sort_keys=True))
    seg_plural_path.write_text(json.dumps(seg_plural, indent=2, sort_keys=True))
    print(f"  wrote {plural_path.name} ({len(plural)} pairs)")
    print(f"  wrote {seg_plural_path.name} ({len(seg_plural)} pairs)")
    print(f"  using {syn_path.name} ({len(syn)} entries)")
    return plural, seg_plural, syn


def apply_path_fix(category_path: str, identity: str, bfc: str) -> tuple[str, str | None]:
    """Return (new_path, reason) — or (path, None) if unchanged."""
    if not category_path:
        return category_path, None

    # 1. Identity-driven map wins (most authoritative)
    if identity in IDENTITY_TO_PATH:
        canon = IDENTITY_TO_PATH[identity]
        if category_path != canon:
            return canon, f"identity_map[{identity}]"

    # 2. BFC override for canned-fruit-in-veg
    bfc_fix = bfc_path_override(bfc, identity, category_path)
    if bfc_fix and bfc_fix != category_path:
        return bfc_fix, "bfc_override"

    # 3. Identity-agnostic synonym collapse
    for pat, repl in PATH_SYNONYMS_COMPILED:
        new_path = pat.sub(repl, category_path)
        if new_path != category_path:
            return new_path, f"path_synonym"

    return category_path, None


def apply_fixes(title: str, identity: str) -> tuple[str, str | None]:
    """Run all fixers, return (new_identity, fixer_name) — or (identity, None) if unchanged."""
    for fixer in KNOWN_FIXERS:
        new_id = fixer(title, identity)
        if new_id and new_id != identity:
            return new_id, fixer.__name__
    return identity, None


# ---------------- audit: find lonely-hint cases ----------------

def stem_keyword(identity: str) -> str | None:
    """For 'Apple Chips' return 'apple'. For 'Almond Milk' return 'almond'.
    Returns the first non-generic word as the natural-keyword guess."""
    if not identity:
        return None
    GENERIC = {"chips","milk","water","candy","bar","bars","sauce","mix","powder",
               "drink","beverage","snack","pack","cake","cakes","cookies","cookie",
               "bread","cream","cup","cups","sticks","stix"}
    words = identity.lower().split()
    for w in words:
        # strip trailing punctuation
        w = re.sub(r'[^a-z0-9]', '', w)
        if w and w not in GENERIC:
            return w
    return None


def audit(rows, m) -> dict:
    """For each hint-table identity, check how many rows have it as identity
    but title doesn't contain the natural keyword."""
    counts_by_id: dict[str, int] = Counter()
    suspect_by_id: dict[str, list] = defaultdict(list)
    for o in rows:
        rec = o.get("record", {}) or {}
        if "_parse_error" in rec or "_api_error" in rec: continue
        norm = m.normalize_record(rec, {"title": o.get("title",""), "branded_food_category": o.get("branded_food_category","")})
        pid = norm.get("product_identity","")
        if pid not in m.CANONICAL_CATEGORY_HINTS:
            continue
        kw = stem_keyword(pid)
        if not kw:
            continue
        counts_by_id[pid] += 1
        title = (o.get("title") or "").lower()
        if kw not in title:
            suspect_by_id[pid].append(o)
    suspect_summary = sorted(
        ((pid, len(suspect_by_id[pid]), counts_by_id[pid]) for pid in suspect_by_id),
        key=lambda t: -t[1]
    )
    return {"counts": counts_by_id, "suspect": suspect_by_id, "summary": suspect_summary}


def join_list(v) -> str:
    if not v: return ""
    if isinstance(v, list): return " | ".join(str(x) for x in v)
    return str(v)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", type=Path, default=DEFAULT_LIVE)
    parser.add_argument("--out",  type=Path, default=DEFAULT_OUT)
    parser.add_argument("--audit", type=Path, default=DEFAULT_AUDIT)
    parser.add_argument("--plural-map", type=Path, default=DEFAULT_PLURAL_MAP)
    parser.add_argument("--vote-map", type=Path, default=DEFAULT_PATH_VOTE_MAP)
    parser.add_argument("--seg-plural-map", type=Path, default=DEFAULT_SEGMENT_PLURAL_MAP)
    parser.add_argument("--synonyms", type=Path, default=DEFAULT_SEGMENT_SYNONYMS)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--dispute", type=Path, default=DEFAULT_DISPUTE)
    parser.add_argument("--rebuild-maps", action="store_true",
                        help="Force regeneration of plural/vote maps from corpus")
    parser.add_argument("--no-maps", action="store_true",
                        help="Skip pluralization + path-vote remap (audit only)")
    parser.add_argument("--audit-only", action="store_true",
                        help="Just write the lonely-hint audit, don't rewrite CSV")
    args = parser.parse_args()

    if not args.live.exists():
        raise SystemExit(f"no live file at {args.live}")

    m = load_module()
    rows = [json.loads(l) for l in args.live.open() if l.strip()]
    print(f"  loaded {len(rows):,} rows from {args.live}")

    # ---- audit
    a = audit(rows, m)
    with args.audit.open("w") as fh:
        fh.write("Lonely-hint audit — identities where the model emitted them\n")
        fh.write("but title doesn't contain the natural keyword.\n\n")
        fh.write(f"{'identity':35s}  {'suspect':>8s}  {'total':>6s}  {'%':>5s}\n")
        fh.write("-"*70 + "\n")
        for pid, nsus, ntot in a["summary"]:
            pct = 100*nsus/max(ntot,1)
            fh.write(f"{pid:35s}  {nsus:>8d}  {ntot:>6d}  {pct:>4.0f}%\n")
        fh.write("\n\nSamples per identity (first 5):\n")
        for pid, _, _ in a["summary"][:30]:
            fh.write(f"\n  === {pid} ===\n")
            for o in a["suspect"][pid][:5]:
                fh.write(f"    fdc={o.get('fdc_id','')}  title={o.get('title','')[:80]}\n")
    print(f"  wrote audit -> {args.audit}")

    # Print top-line audit
    print()
    print("  Top 15 lonely-hint identities (likely miscategorizations):")
    print(f"    {'identity':30s}  {'suspect':>8s}  {'total':>6s}  pct")
    for pid, nsus, ntot in a["summary"][:15]:
        pct = 100*nsus/max(ntot,1)
        print(f"    {pid:30s}  {nsus:>8d}  {ntot:>6d}  {pct:>3.0f}%")

    if args.audit_only:
        return

    # ---- Phase 1: load/build static maps (plural, seg_plural, synonyms)
    plural_map: dict = {}
    seg_plural_map: dict = {}
    synonyms_map: dict = {}
    if not args.no_maps:
        plural_map, seg_plural_map, synonyms_map = load_or_build_static_maps(
            rows, args.plural_map, args.seg_plural_map, args.synonyms,
            args.rebuild_maps
        )

    # ---- apply known fixes
    columns = [
        "fdc_id","title","branded_food_category",
        "retail_type",
        "category_path_original","category_path_fixed","path_fixer_applied",
        "product_identity_original","product_identity_fixed","fixer_applied",
        "canonical_path","canonical_label",
        "variant","flavor","form_texture_cut","processing_storage","claims",
        "components_count","components",
        "confidence","mint_required","review_flags","rationale",
    ]
    fix_counter = Counter()
    path_fix_counter = Counter()
    plural_counter = Counter()
    vote_counter = Counter()
    seg_plural_counter = 0
    leaf_strip_counter = 0
    synonym_counter = 0
    # Track per-identity paths before/after for the report
    paths_before: dict[str, Counter] = defaultdict(Counter)
    paths_after:  dict[str, Counter] = defaultdict(Counter)
    # Rows where multiple paths persist after all rules → dispute
    dispute_seen: dict[tuple, list] = defaultdict(list)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    # Pass 1: apply all transforms EXCEPT path-vote, accumulate processed rows
    processed: list[dict] = []
    id_path_pairs: list[tuple[str, str]] = []
    for o in rows:
        rec = o.get("record", {}) or {}
        if "_parse_error" in rec or "_api_error" in rec: continue
        try:
            norm = m.normalize_record(rec, {"title": o.get("title",""), "branded_food_category": o.get("branded_food_category","")})
        except Exception:
            continue
        orig_id = norm.get("product_identity","")
        title = o.get("title","")
        bfc = o.get("branded_food_category","")
        new_id, fixer = apply_fixes(title, orig_id)
        if fixer:
            fix_counter[fixer] += 1
        if new_id in plural_map:
            new_id = plural_map[new_id]
            plural_counter[orig_id + " -> " + new_id] += 1
            if not fixer:
                fixer = "plural_collapse"
                fix_counter["plural_collapse"] += 1
        # Hard spelling unification — collapse known spelling variants AFTER
        # plural-collapse but BEFORE all path resolution. Ensures one canonical
        # surface form per concept regardless of LLM choice.
        if new_id in SPELLING_UNIFY:
            new_id = SPELLING_UNIFY[new_id]
            if not fixer:
                fixer = "spelling_unify"
                fix_counter["spelling_unify"] += 1
        # Roll/Bun format detector — when title says "rolls" or "buns" anywhere,
        # force identity to a roll/bun-family identity even if the LLM picked
        # a generic Bread or specific bread-style like Brioche.
        roll_bun_override = detect_roll_bun_format(title, new_id)
        if roll_bun_override and roll_bun_override != new_id:
            new_id = roll_bun_override
            fix_counter["roll_bun_format_override"] += 1
            if not fixer:
                fixer = "roll_bun_format_override"
        # Bread short-name + compound-identity normalization. Examples:
        #   'Rye'           → 'Rye Bread' (short→full)
        #   'Rye Caraway'   → 'Rye Bread' + leftover ['caraway'] (compound)
        # Leftover tokens get prepended to the variant facet so they survive
        # into the modifier (e.g., the row's modifier becomes 'Caraway').
        bread_norm = normalize_bread_identity(new_id)
        if bread_norm:
            new_full, leftover = bread_norm
            if new_full != new_id:
                new_id = new_full
                fix_counter["bread_full_name"] += 1
                if not fixer:
                    fixer = "bread_full_name"
                if leftover:
                    existing_variant = norm.get("variant", []) or []
                    if isinstance(existing_variant, str):
                        existing_variant = [existing_variant] if existing_variant else []
                    norm["variant"] = list(leftover) + list(existing_variant)
        # Title-strength override: if the title contains a distinctive product
        # name (biscotti, churros, ciabatta, etc.), override the LLM's identity.
        # Catches cases where the LLM lumped a niche product into broad
        # categories like Cookies / Bread / Buns due to hint-table gaps.
        title_override = title_to_identity_override(title, new_id)
        if title_override and title_override != new_id:
            new_id = title_override
            fix_counter["title_override"] += 1
            if not fixer:
                fixer = "title_override"
        # BFC-driven identity override: when BFC says "Baking/Cooking Mixes",
        # rename Bread→Bread Mix, Cake→Cake Mix, etc. so retail tree splits
        # finished bakery products from baking mixes/batters/doughs.
        bfc_id_override = bfc_identity_override(new_id, bfc)
        if bfc_id_override and bfc_id_override != new_id:
            new_id = bfc_id_override
            if not fixer:
                fixer = "bfc_identity_override"
                fix_counter["bfc_identity_override"] += 1
        orig_path = norm.get("category_path","")
        paths_before[new_id][orig_path] += 1
        cur_path = orig_path
        path_fixer = None
        np1 = normalize_segment_pluralization(cur_path, seg_plural_map)
        if np1 != cur_path:
            cur_path = np1
            path_fixer = path_fixer or "seg_plural"
            seg_plural_counter += 1
        np2 = strip_redundant_leaf(cur_path)
        if np2 != cur_path:
            cur_path = np2
            path_fixer = path_fixer or "leaf_strip"
            leaf_strip_counter += 1
        np3 = apply_segment_synonyms(cur_path, synonyms_map)
        if np3 != cur_path:
            cur_path = np3
            path_fixer = path_fixer or "synonym_seg"
            synonym_counter += 1
        np4, sub_fixer = apply_path_fix(cur_path, new_id, bfc)
        if sub_fixer:
            cur_path = np4
            path_fixer = path_fixer or sub_fixer
            path_fix_counter[sub_fixer] += 1
        proc_orig = list(norm.get("processing_storage", []) or [])
        cur_path, proc_new = apply_storage_strip(cur_path, proc_orig)
        if proc_new != proc_orig:
            norm["processing_storage"] = proc_new
            if not path_fixer:
                path_fixer = "storage_strip"
        cur_path, canon_changed = force_canonical_tree(cur_path)
        if canon_changed and not path_fixer:
            path_fixer = "canonical_tree"
        # Pre-vote state — record (final_id, pre_vote_path) for vote map build
        id_path_pairs.append((new_id, cur_path))
        processed.append({
            "fdc_id": o.get("fdc_id",""),
            "title": title,
            "bfc": bfc,
            "norm": norm,
            "orig_id": orig_id,
            "new_id": new_id,
            "fixer": fixer,
            "orig_path": orig_path,
            "pre_vote_path": cur_path,
            "path_fixer": path_fixer,
        })

    # Build vote map from the EXACT same (id, path) pairs the writer will use
    print(f"  building vote map from {len(id_path_pairs):,} processed rows...")
    vote_map = build_path_vote_map_from_pairs(id_path_pairs, plural_map)
    args.vote_map.write_text(json.dumps(vote_map, indent=2, sort_keys=True))
    print(f"  wrote {args.vote_map.name} ({len(vote_map)} identities, "
          f"{sum(len(v) for v in vote_map.values())} (id,top) pairs)")

    # Pass 2: apply path-vote, write CSV
    written = 0
    with args.out.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=columns)
        w.writeheader()
        for r in processed:
            new_id = r["new_id"]; cur_path = r["pre_vote_path"]
            path_fixer = r["path_fixer"]; norm = r["norm"]
            if new_id in vote_map and cur_path:
                top = cur_path.split(">", 1)[0].strip()
                canon = vote_map[new_id].get(top)
                if canon and canon != cur_path:
                    vote_counter[f"{new_id} | {top}"] += 1
                    cur_path = canon
                    path_fixer = path_fixer or "path_vote"
            new_path = cur_path
            paths_after[new_id][new_path] += 1
            canon = (new_path + " > " + new_id) if new_path and new_id else (new_path or new_id)
            canon = strip_redundant_leaf(canon)
            w.writerow({
                "fdc_id": r["fdc_id"],
                "title": r["title"],
                "branded_food_category": r["bfc"],
                "retail_type": norm.get("retail_type",""),
                "category_path_original": r["orig_path"],
                "category_path_fixed":    new_path,
                "path_fixer_applied":     path_fixer or "",
                "product_identity_original": r["orig_id"],
                "product_identity_fixed":    new_id,
                "fixer_applied":             r["fixer"] or "",
                "canonical_path":            canon,
                "canonical_label":           norm.get("canonical_label",""),
                "variant":           join_list(norm.get("variant",[])),
                "flavor":            join_list(norm.get("flavor",[])),
                "form_texture_cut":  join_list(norm.get("form_texture_cut",[])),
                "processing_storage":join_list(norm.get("processing_storage",[])),
                "claims":            join_list(norm.get("claims",[])),
                "components_count":  len(norm.get("components",[]) or []),
                "components":        join_list([c.get("identity","") for c in norm.get("components",[]) or []]),
                "confidence":        norm.get("confidence",""),
                "mint_required":     norm.get("mint_required",""),
                "review_flags":      join_list(norm.get("review_flags",[])),
                "rationale":         (norm.get("rationale","") or "")[:500],
            })
            written += 1
    print()
    print(f"  wrote {written:,} rows -> {args.out}")
    print(f"  identity fixers applied: {dict(fix_counter)}")
    print(f"  path fixers applied:     {dict(path_fix_counter)}")
    print(f"  segment-plural rewrites:  {seg_plural_counter:,}")
    print(f"  leaf-strip rewrites:      {leaf_strip_counter:,}")
    print(f"  synonym-segment rewrites: {synonym_counter:,}")
    print(f"  pluralization collapses:  {sum(plural_counter.values()):,} rows  ({len(plural_counter)} pairs)")
    print(f"  path-vote consolidations: {sum(vote_counter.values()):,} rows  ({len(vote_counter)} (id,top) pairs)")

    # ---- Path collision report
    # For every identity that started with multiple paths, log before/after
    rep_cols = ["identity", "n_rows", "n_paths_before", "n_paths_after",
                "paths_before", "paths_after", "still_multi"]
    n_resolved = 0
    n_still_multi = 0
    with args.report.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=rep_cols)
        w.writeheader()
        all_ids = set(paths_before.keys()) | set(paths_after.keys())
        # Sort by total row volume desc
        for pid in sorted(all_ids, key=lambda k: -sum(paths_after[k].values())):
            before = paths_before[pid]
            after = paths_after[pid]
            if len(before) <= 1 and len(after) <= 1:
                continue
            still = len(after) > 1
            if still: n_still_multi += 1
            else:     n_resolved += 1
            w.writerow({
                "identity": pid,
                "n_rows": sum(after.values()),
                "n_paths_before": len(before),
                "n_paths_after": len(after),
                "paths_before": " | ".join(f"{p} ({n})" for p, n in before.most_common()),
                "paths_after":  " | ".join(f"{p} ({n})" for p, n in after.most_common()),
                "still_multi": still,
            })
    print(f"  wrote {args.report.name}: {n_resolved} identities collapsed, "
          f"{n_still_multi} still multi-path")

    # ---- Dispute CSV: every (identity, top-level) where >1 path remains
    disp_cols = ["identity", "top_level", "n_rows", "paths_with_counts", "suggestion"]
    dispute_rows = 0
    with args.dispute.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=disp_cols)
        w.writeheader()
        for pid, after in paths_after.items():
            if len(after) <= 1: continue
            by_top: dict[str, Counter] = defaultdict(Counter)
            for p, n in after.items():
                top = p.split(">", 1)[0].strip()
                by_top[top][p] += n
            for top, sub in by_top.items():
                if len(sub) <= 1: continue
                # Suggest the path with most rows in this top
                winner, _ = sub.most_common(1)[0]
                w.writerow({
                    "identity": pid,
                    "top_level": top,
                    "n_rows": sum(sub.values()),
                    "paths_with_counts": " | ".join(f"{p} ({n})" for p, n in sub.most_common()),
                    "suggestion": winner,
                })
                dispute_rows += 1
    print(f"  wrote {args.dispute.name}: {dispute_rows} unresolved (id, top) collisions")


if __name__ == "__main__":
    main()
