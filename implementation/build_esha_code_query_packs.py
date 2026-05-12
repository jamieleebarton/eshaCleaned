from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

import esha_contracts
import match_esha_to_products as matcher


ROOT = Path(__file__).resolve().parent.parent
ESHA_CSV = ROOT / "esha_cleaned.csv"
PRODUCTS_DB = ROOT / "data" / "master_products.db"
OUT_ROOT = ROOT / "implementation" / "output" / "esha_code_query_packs"
OUT_INDEX = ROOT / "implementation" / "output" / "esha_code_query_pack_index.csv"
QUERY_TERM_DROP_CANDIDATES_CSV = ROOT / "implementation" / "output" / "query_term_drop_candidates.csv"
RETAIL_QUERY_REWRITE_PLAN_CSV = ROOT / "implementation" / "output" / "retail_query_rewrite_plan.csv"
INDEX_FIELDS = [
    "esha_code",
    "description",
    "family",
    "query",
    "pack_path",
    "total_product_matches",
    "category_count",
    "candidate_count_capped",
    "top_category",
    "top_category_count",
    "error",
]


CATEGORY_HINTS = {
    "milk": ("milk", "dairy", "beverage"),
    "plant_milk": ("milk", "dairy", "beverage", "plant"),
    "yogurt": ("yogurt", "dairy"),
    "cheese": ("cheese", "dairy"),
    "cream": ("cream", "dairy"),
    "butter": ("butter & spread", "butter/butter", "margarine/butter", "butter substitute", "dairy"),
    "nut_butter": ("nut & seed butters", "peanut butter"),
    "egg": ("egg", "dairy"),
    "fruit": ("fruit", "produce", "canned fruit", "frozen fruit", "dried fruit"),
    "vegetable": ("vegetable", "produce", "canned vegetables", "frozen vegetables"),
    "legume": ("bean", "beans", "legume", "lentil", "vegetable"),
    "grain": (
        "bread", "rice", "pasta", "pasta by shape", "all noodles", "noodle", "noodles",
        "macaroni", "grain", "cereal", "flour", "bakery",
    ),
    "meat": ("meat", "beef", "pork", "bacon", "sausage"),
    "poultry": ("poultry", "chicken", "turkey"),
    "seafood": ("seafood", "fish", "shellfish"),
    "condiment": ("condiment", "sauce", "dressing", "pickle", "relish"),
    "soup": ("soup", "stew", "chili"),
    "prepared_food": (
        "frozen prepared", "prepared side", "ready made", "combination meal",
        "dough based", "entree", "small meal", "side dish", "frozen dinner",
        "frozen appetizer", "hors d oeuvre", "other deli", "prepared subs", "sandwich",
    ),
    "sweetener": ("sugar", "sweetener", "syrup", "honey"),
    "dessert_snack": ("snack", "cookie", "candy", "chocolate", "dessert", "chips", "crackers"),
    "beverage": ("beverage", "drink", "juice", "coffee", "tea", "water"),
    "spice": ("herbs & spices", "seasoning mixes, salts, marinades & tenderizers", "seasonings/preservatives/extracts", "baking additives & extracts"),
    "oil": ("vegetable & cooking oils", "cooking oils", "oils"),
}

CANDY_CATEGORY_HINTS = (
    "candy",
    "chocolate",
    "gum",
    "fruit snack",
)

CONTEXT_CATEGORY_HINTS = {
    "sorbet": ("ice cream", "frozen yogurt", "frozen dessert", "other frozen desserts"),
    "sherbet": ("ice cream", "frozen yogurt", "frozen dessert", "other frozen desserts"),
    "baby": ("baby/infant foods/beverages", "baby/infant", "baby"),
    "jam": ("jam, jelly & fruit spreads",),
    "jelly": ("jam, jelly & fruit spreads",),
    "preserve": ("jam, jelly & fruit spreads",),
    "pickle": ("pickles, olives, peppers & relishes",),
    "olive": ("pickles, olives, peppers & relishes",),
    "infant": ("baby/infant foods/beverages", "baby/infant", "baby"),
    "tomato": ("tomatoes",),
    "broth": ("canned soup", "broths", "soups"),
    "stock": ("canned soup", "broths", "soups"),
    "salt": ("seasoning mixes, salts, marinades & tenderizers", "herbs & spices"),
    "brickle": ("candy", "baking decorations & dessert toppings", "desserts/dessert sauces/toppings"),
    "ensure": ("energy, protein & muscle recovery drinks", "nutrition", "drink"),
    "bagel": ("breads & buns", "bread", "buns"),
    "cracker": ("crackers & biscotti", "cookies & biscuits", "crackers"),
    "crackers": ("crackers & biscotti", "cookies & biscuits", "crackers"),
    "graham": ("cookies & biscuits", "cracker"),
    "hamburger": ("baking/cooking mixes/supplies", "dough based products / meals"),
    "leather": ("snacks", "candy"),
    "lemonade": ("frozen fruit & fruit juice concentrates", "juice", "drink"),
    "oatmeal": ("cereal", "processed cereal products"),
    "pancake": ("frozen pancakes, waffles, french toast & crepes", "pancakes, waffles, french toast & crepes"),
    "pediasure": ("energy, protein & muscle recovery drinks", "nutrition", "drink"),
    "pizza": ("pizza", "crusts & dough"),
    "soup": ("prepared soups", "other soups", "canned condensed soup", "canned soup"),
    "tempeh": ("other meats", "vegetable based", "vegetarian frozen meats"),
    "tortilla": ("mexican dinner mixes", "breads & buns", "bread", "buns"),
    "roll": ("snacks", "sweet rolls", "pastries"),
    "fry": ("french fries, potatoes & onion rings",),
    "fries": ("french fries, potatoes & onion rings",),
    "frappuccino": ("other drinks", "coffee/tea/substitutes"),
    "latte": ("other drinks", "coffee/tea/substitutes", "iced & bottle tea"),
    "cappuccino": ("other drinks", "coffee/tea/substitutes"),
    "cocoa": ("powdered drinks", "coffee"),
    "twist": ("snacks", "candy"),
    "wafer": ("cookies & biscuits",),
    "waffle": ("frozen pancakes, waffles, french toast & crepes", "pancakes, waffles, french toast & crepes"),
}

CONTEXT_IGNORE_NOISE = {
    "sorbet": {"ice", "cream", "yogurt"},
    "sherbet": {"ice", "cream", "yogurt"},
    "eggnog": {"cream", "flavor", "flavored"},
    "mayonnaise": {"salad", "dressing"},
    "mayo": {"salad", "dressing"},
    "morsel": {"milk"},
}

CONTEXT_EXTRA_NOISE = {
    "mayonnaise": {
        "aioli", "avocado", "barbecue", "bbq", "buffalo", "chipotle", "dijon",
        "dijonnaise", "garlic", "habanero", "horseradish", "jalapeno", "ketchup",
        "lime", "pesto", "ranch", "serrano", "spicy", "sriracha", "truffle",
        "wasabi",
    },
    "mayo": {
        "aioli", "avocado", "barbecue", "bbq", "buffalo", "chipotle", "dijon",
        "dijonnaise", "garlic", "habanero", "horseradish", "jalapeno", "ketchup",
        "lime", "pesto", "ranch", "serrano", "spicy", "sriracha", "truffle",
        "wasabi",
    },
    "peanut": {
        "almond", "cashew", "hazelnut", "macadamia", "pistachio", "sesame",
        "sunflower", "tahini", "walnut",
    },
    "sorbet": {"candy", "chocolate"},
    "sherbet": {"candy", "chocolate"},
    "salt": {
        "barbecue", "bbq", "celery", "chipotle", "garlic", "herb", "jalapeno",
        "onion", "pepper", "seasoned", "smoked", "taco", "truffle",
    },
    "evaporated": {"coconut", "creamer", "filled", "goat"},
    "condensed": {"coconut", "creamer", "filled", "goat"},
    "eggnog": {"kefir", "smoothie", "yogurt"},
    "malted": {"ball", "balls", "candy", "cupcake", "egg", "eggs", "frosting", "ice", "cream"},
}

NOISE_TERMS = {
    "milk": (
        "chocolate", "cocoa", "strawberry", "vanilla", "banana", "coffee", "mocha",
        "caramel", "flavored", "flavor", "malted", "shake", "protein", "smoothie",
        "almond", "oat", "soy", "soymilk", "coconut", "rice", "cashew", "hemp",
        "plant", "alternative", "substitute", "yogurt", "cheese", "ice", "cream",
    ),
    "plant_milk": (
        "chocolate", "cocoa", "strawberry", "vanilla", "banana", "coffee", "mocha",
        "caramel", "flavored", "flavor", "malted", "shake", "protein", "smoothie",
        "yogurt", "cheese", "ice", "cream",
    ),
    "yogurt": (
        "drink", "smoothie", "shake", "bar", "covered", "coated", "cereal", "snack",
        "ice", "cream", "cheese",
    ),
    "butter": (
        "peanut", "almond", "cashew", "pistachio", "walnut", "macadamia", "hazelnut",
        "nut", "seed", "sunflower", "sesame", "cookie", "cooky", "biscuit",
        "cracker", "bar", "cup", "candy", "chocolate", "popcorn", "ice",
        "pickle", "vegetable", "potato", "casserole", "dish", "sauce", "spray",
        "oil", "protein", "cereal", "toffee",
    ),
    "legume": (
        "soup", "chili", "stew", "rice", "salad", "burrito", "wrap", "dip", "hummus",
        "casserole", "meal", "dinner", "snack", "chip", "coffee", "espresso",
    ),
    "vegetable": (
        "soup", "stew", "chili", "casserole", "sauce", "dip", "meal", "dinner",
        "pizza", "pasta", "rice", "snack", "chip",
    ),
    "cheese": (
        "mac", "macaroni", "pasta", "sauce", "dip", "soup", "cracker", "chip",
        "popcorn", "snack", "meal", "sandwich", "burrito", "pizza",
    ),
    "condiment": (
        "sandwich", "wrap", "salad", "kit", "meal", "chicken", "tuna", "chip",
        "snack",
    ),
    "grain": (
        "meal", "dinner", "entree", "kit", "soup", "salad", "sandwich", "pizza",
    ),
    "dessert_snack": (
        "ice", "cream", "yogurt", "milk", "cereal", "protein", "shake",
    ),
    "nut_butter": (
        "almond", "bar", "cashew", "cereal", "chocolate", "cookie", "hazelnut",
        "macadamia", "pistachio", "protein", "sesame", "sunflower", "tahini",
        "walnut",
    ),
    "beverage": (
        "protein", "recovery", "muscle", "prebiotic",
    ),
    "oil": (
        "bar", "butter", "candy", "chip", "chocolate", "cookie", "dressing",
        "popcorn", "protein", "sauce", "snack", "spread",
    ),
}

GENERIC_QUERY_TERMS = {
    "food",
    "dish",
    "regular",
    "plain",
    "prepared",
    "recipe",
    "style",
    "type",
    "with",
}

NO_PLURAL_VARIANT = {
    "baked",
    "canned",
    "cooked",
    "drained",
    "dried",
    "dry",
    "fat",
    "free",
    "frozen",
    "instant",
    "low",
    "mature",
    "raw",
    "reduced",
    "refried",
    "roasted",
    "sodium",
    "spicy",
    "unsalted",
    "butter",
}

IDENTITY_QUERY_TERMS = {
    "baked",
    "refried",
    "black",
    "pinto",
    "kidney",
    "lima",
    "navy",
    "garbanzo",
    "chickpea",
    "red",
    "white",
    "green",
    "snap",
    "wax",
    "string",
    "spicy",
    "jalapeno",
    "onion",
    "bacon",
    "barbecue",
    "vegetarian",
    "whole",
    "canned",
    "frozen",
    "dried",
    "dry",
    "drained",
    "evaporated",
    "condensed",
    "eggnog",
    "malted",
    "shake",
    "skim",
    "filled",
    "goat",
    "rinsed",
}

DEFAULT_RETAIL_STATE_TERMS_BY_FAMILY = {
    "grain": {"dry"},
    "spice": {"dry"},
    "sweetener": {"dry"},
}

RETAIL_CLAIM_FAMILIES = {"beverage", "dessert_snack", "yogurt", "condiment"}

OPTIONAL_QUERY_TERMS_BY_FAMILY = {
    "grain": {"dry", "egg", "enriched"},
    "dessert_snack": {"fat", "free", "reduced", "calorie", "individual", "sd", "zesty", "orchard", "reserve", "light", "rich", "low"},
}

RESCUE_ATTEMPT_LIMIT = 8

PREPARED_FOOD_CUES = {
    "alfredo",
    "burger",
    "burgers",
    "burrito",
    "burritos",
    "casserole",
    "casseroles",
    "chimichanga",
    "chimichangas",
    "dish",
    "meal",
    "dinner",
    "enchilada",
    "enchiladas",
    "entree",
    "fettuccine",
    "fettuccini",
    "meatloaf",
    "side",
    "lasagna",
    "pizza",
    "pasta",
    "noodle",
    "noodles",
    "quiche",
    "quesadilla",
    "quesadillas",
    "ravioli",
    "salisbury",
    "steak",
    "stir",
    "stroganoff",
    "fry",
    "stew",
    "chili",
    "soup",
    "gratin",
    "scalloped",
    "sauce",
    "gravy",
    "polenta",
    "risotto",
    "taquito",
    "taquitos",
    "tamale",
    "tamales",
    "empanada",
    "empanadas",
    "potsticker",
    "potstickers",
    "sandwich",
    "sandwiches",
    "slider",
    "sliders",
    "sub",
    "subs",
    "wrap",
    "wraps",
}

CANDY_CONTEXT_TERMS = {
    "candy",
    "gummy",
    "gumdrop",
    "jujube",
    "licorice",
    "marshmallow",
    "marzipan",
    "nougat",
    "reese",
    "skittle",
    "starburst",
    "taffy",
    "toffee",
    "turtle",
    "twizzler",
}

FROZEN_DESSERT_CATEGORY_HINTS = (
    "ice cream",
    "frozen yogurt",
    "other frozen desserts",
)

FROZEN_DESSERT_SHAPE_TERMS = {
    "bar",
    "bars",
    "cone",
    "cones",
    "float",
    "sandwich",
    "sandwiches",
    "serve",
}

STATE_OR_PROCESS_TERMS = {
    "baked",
    "boiled",
    "canned",
    "cooked",
    "drained",
    "dried",
    "dry",
    "enriched",
    "fresh",
    "frozen",
    "heated",
    "prepared",
    "raw",
    "ready",
    "reconstituted",
    "refrigerated",
    "rinsed",
    "roasted",
    "salted",
    "sliced",
    "toasted",
    "unsalted",
}

SOFT_STATE_TERMS = {
    "fresh",
    "raw",
}

INGREDIENT_ONLY_TERMS = {
    "acesulfame",
    "acesulfamek",
    "aspartame",
    "monkfruit",
    "saccharin",
    "stevia",
    "sucralose",
}

PROCESS_ONLY_TERMS = {
    "drained",
    "heated",
    "prepared",
    "ready",
    "reconstituted",
    "rinsed",
    "water",
    "wtr",
}

CLAIM_TRANSLATION_TERMS = {
    "calorie",
    "diet",
    "fat",
    "free",
    "light",
    "low",
    "reduced",
    "sugar",
}

PEEL_PROXY_TERMS = {"peel", "rind", "zest"}

INFANT_ROUTING_TERMS = {
    "food",
    "foods",
    "fruit",
    "dessert",
    "juice",
    "snack",
    "snacks",
    "stage",
    "month",
    "months",
    "toddler",
    "junior",
    "organic",
    "org",
    "with",
    "ounce",
    "ounces",
    "oz",
    "jar",
    "pouch",
}

INFANT_FLAVOR_CUES = {
    "apple",
    "applesauce",
    "apricot",
    "avocado",
    "banana",
    "barley",
    "berry",
    "blueberry",
    "carrot",
    "cereal",
    "cinnamon",
    "cranberry",
    "fruit",
    "grape",
    "grain",
    "guava",
    "kiwi",
    "mango",
    "mixed",
    "oat",
    "oatmeal",
    "papaya",
    "peach",
    "pear",
    "pineapple",
    "plum",
    "prune",
    "pumpkin",
    "raspberry",
    "rice",
    "strawberry",
}

FORMULA_BRAND_TERMS = {"ensure", "pediasure", "nutren", "optimental"}

PRODUCE_PROXY_BLOCK_TERMS = {
    "bowl",
    "cream",
    "dip",
    "dressing",
    "hummus",
    "juice",
    "kit",
    "meal",
    "mix",
    "paste",
    "preserve",
    "preserves",
    "salad",
    "sauce",
    "seasoning",
    "snack",
    "tea",
    "topping",
    "tray",
    "water",
}

SIMPLE_PRODUCE_BLOCK_TERMS = PRODUCE_PROXY_BLOCK_TERMS | {
    "banana",
    "blueberry",
    "blackberry",
    "grape",
    "kiwi",
    "mango",
    "parfait",
    "pineapple",
    "raspberry",
    "yogurt",
}

FAMILY_IDENTITY_TERMS = {
    "milk": {"milk", "condensed", "eggnog", "evaporated", "malted"},
    "plant_milk": {"milk", "almond", "oat", "soy", "coconut"},
    "yogurt": {"yogurt"},
    "cheese": {"cheese"},
    "cream": {"cream"},
    "butter": {"butter"},
    "nut_butter": {"butter", "peanut", "almond", "cashew"},
    "egg": {"egg"},
    "fruit": {"apple", "banana", "berry", "fruit", "orange", "peach", "pear"},
    "vegetable": {"bean", "carrot", "corn", "green", "pea", "potato", "tomato", "vegetable"},
    "legume": {"bean", "black", "chickpea", "garbanzo", "kidney", "lentil", "lima", "navy", "pinto"},
    "grain": {"bread", "cereal", "flour", "macaroni", "noodle", "pasta", "rice"},
    "meat": {"bacon", "beef", "meat", "pork", "sausage"},
    "poultry": {"chicken", "poultry", "turkey"},
    "seafood": {"fish", "salmon", "seafood", "shrimp", "tuna"},
    "condiment": {"dressing", "mayo", "mayonnaise", "mustard", "sauce"},
    "soup": {"chili", "soup", "stew"},
    "sweetener": {"honey", "sugar", "syrup"},
    "beverage": {"beverage", "coffee", "drink", "juice", "tea", "water"},
}

QUERY_TERM_OVERRIDES_BY_CODE = {
    "1": ("whole", "milk"),
    "2": ("2", "milk"),
    "4": ("1", "milk"),
    "23": ("goat", "milk"),
    "42": ("sheep", "milk"),
    "43": ("carob", "powder"),
    "52": ("low", "sodium", "milk"),
    "67": ("skim", "milk", "powder"),
    "615": ("rice", "milk", "vanilla"),
    "618": ("vanilla", "drink"),
    "1075": ("parmesan", "grated", "cheese"),
    "436": ("baby", "green", "bean", "potato"),
    "12470": ("frozen", "waffle"),
    "16642": ("frozen", "pancake"),
    "16643": ("frozen", "pancake", "buttermilk"),
    "16646": ("frozen", "pancake", "blueberry"),
    "37261": ("focus", "water"),
    "37264": ("dwnld", "water"),
    "37266": ("connect", "water"),
    "37278": ("multi", "water"),
    "37281": ("stur",),
    "37282": ("sparkling", "water"),
    "45213": ("frozen", "waffle"),
    "52742": ("frozen", "waffle", "blueberry"),
    "91243": ("tempeh",),
    "38579": ("elbow", "macaroni"),
    "38591": ("linguine", "pasta"),
    "50343": ("chicken", "broth"),
    "501": ("light", "cream"),
    "40775": ("pie", "crust"),
    "42508": ("hamburger", "buns"),
    "92863": ("prosciutto",),
    "13021": ("pepperoni",),
    "27004": ("prepared", "horseradish"),
    "31312": ("mandarin", "oranges"),
    "46516": ("basmati", "rice"),
    "9083": ("marinara", "sauce"),
    "49045": ("puff", "pastry"),
    "35278": ("vanilla", "bean"),
    "50504": ("condensed", "tomato", "soup"),
    "23184": ("butterscotch", "chips"),
    "91972": ("celery", "salt"),
    "31545": ("hoisin", "sauce"),
    "91947": ("cajun", "seasoning"),
    "93138": ("wheat", "germ"),
    "4715": ("macadamia", "nuts"),
    "15061": ("chicken", "thighs"),
    "15046": ("chicken", "wings"),
    "17230": ("salmon", "fillets"),
    "27997": ("beef", "stew", "meat"),
    "13082": ("italian", "sausage"),
    "9329": ("baby", "carrots"),
    "90467": ("red", "onions"),
    "6032": ("arugula",),
    "37790": ("onion", "soup", "mix"),
    "42358": ("italian", "breadcrumbs"),
    "53615": ("teriyaki", "sauce"),
    "36158": ("whole", "wheat", "bread"),
    "44895": ("sunflower", "oil"),
    "26627": ("fresh", "rosemary"),
    "90442": ("ginger", "root"),
    "25760": ("fresh", "strawberries"),
    "47878": ("gruyere", "cheese"),
    "93184": ("arborio", "rice"),
    "4790": ("ginger", "ale"),
    "23299": ("apricot", "preserves"),
    "91953": ("onion", "salt"),
    "38079": ("quinoa",),
    "1452": ("fat", "free", "cream", "cheese"),
    "33229": ("light", "cream", "cheese"),
    "55029": ("reduced", "fat", "cream", "cheese"),
    "50475": ("condensed", "cream", "chicken", "soup"),
    "6265": ("cream", "style", "corn"),
    "4521": ("pistachios",),
    "34639": ("graham", "crackers"),
    "8107": ("lard",),
    "9200": ("pimientos",),
    "1005": ("brie", "cheese"),
    "38064": ("oat", "bran"),
    "538": ("reduced", "fat", "sour", "cream"),
    "23064": ("marshmallow", "creme"),
    "23071": ("marshmallow", "cream"),
    "7480": ("chunky", "salsa"),
    "26024": ("ground", "mace"),
    "30261": ("potato", "starch"),
    "92310": ("steak", "sauce"),
    "37704": ("barley",),
    "19177": ("rye", "bread"),
    "38346": ("chow", "mein", "noodles"),
    "42317": ("biscuit", "mix"),
    "38448": ("vital", "wheat", "gluten"),
    "38022": ("rye", "flour"),
    "1060": ("neufchatel", "cheese"),
    "48001": ("apple", "pie", "filling"),
    "53909": ("potato", "chips"),
    "13234": ("salami",),
    "16455": ("almond", "milk"),
    "4649": ("cream", "of", "coconut"),
    "9755": ("dried", "currants"),
    "36978": ("white", "cheddar", "cheese"),
    "17033": ("catfish", "fillets"),
    "34570": ("anchovy", "paste"),
    "5711": ("asparagus", "spears"),
    "1281": ("colby", "cheese"),
    "11581": ("ground", "veal"),
    "91272": ("raspberry", "preserves"),
    "90887": ("seedless", "raspberry", "jam"),
    "41383": ("liquid", "egg", "substitute"),
    "26013": ("fresh", "parsley"),
    "1054": ("gouda", "cheese"),
    "33351": ("muenster", "cheese"),
    "35063": ("fenugreek", "seed"),
    "25758": ("honeydew", "melon"),
    "37838": ("serrano", "pepper"),
    "26106": ("anise", "seed"),
    "49218": ("candied", "ginger"),
    "41219": ("halibut", "fillets"),
    "26098": ("msg",),
    "53023": ("beef", "gravy"),
    "3164": ("fruit", "cocktail", "juice"),
    "3126": ("prunes",),
    "41309": ("malt", "vinegar"),
    "7378": ("red", "lentils"),
    "92163": ("ramen", "noodles"),
    "28169": ("chicken", "ramen", "noodles"),
    "58511": ("andouille", "sausage"),
    "22593": ("rum",),
    "508": ("whipped", "topping"),
    "26630": ("fresh", "mint"),
    "5359": ("chive",),
    "2004": ("vanilla", "ice", "cream"),
    "48557": ("dried", "cranberries"),
    "52629": ("shrimp",),
    "52630": ("cooked", "shrimp"),
    "26017": ("cream", "tartar"),
    "6813": ("eggplant",),
    "53474": ("fish", "sauce"),
    "4511": ("shredded", "coconut"),
    "4573": ("flaked", "coconut"),
    "22604": ("sherry",),
    "14984": ("green", "chiles"),
    "5001": ("asparagus",),
    "41524": ("semisweet", "chocolate"),
    "22513": ("brandy",),
    "5446": ("sun", "dried", "tomatoes"),
    "22594": ("vodka",),
    "38277": ("bread", "flour"),
    "38033": ("self", "rising", "flour"),
    "24190": ("crawfish",),
    "22614": ("beer",),
    "90965": ("vegetable", "oil"),
    "13472": ("corn", "tortilla"),
    "5172": ("plum", "tomato"),
    "46086": ("cake", "flour"),
    "34814": ("splenda",),
    "6298": ("pumpkin",),
    "45336": ("mustard",),
    "35682": ("mustard",),
    "3006": ("applesauce",),
    "46797": ("applesauce",),
    "46799": ("applesauce", "cinnamon"),
    "46801": ("applesauce",),
    "46806": ("applesauce", "sugar"),
    "5441": ("yellow", "bell", "pepper"),
    "26482": ("taco", "seasoning"),
    "24169": ("unsweetened", "chocolate"),
    "9114": ("spaghetti", "sauce"),
    "1272": ("velveeta",),
    "26901": ("black", "peppercorn"),
    "5206": ("leek",),
    "3380": ("banana",),
    "25570": ("salsa",),
    "50477": ("cream", "mushroom", "condensed", "soup"),
    "90374": ("cream", "chicken", "condensed", "soup"),
    "91928": ("seasoning", "salt"),
    "90530": ("cherry", "tomato"),
    "5511": ("capers",),
    "3381": ("blueberries",),
    "4504": ("almonds",),
    "49260": ("sliced", "almonds"),
    "1793": ("vegetable", "broth"),
    "22501": ("red", "wine"),
    "3990": ("pineapple", "juice"),
    "5104": ("white", "onion"),
    "26622": ("fresh", "dill"),
    "5055": ("celery",),
    "30000": ("cornstarch",),
    "36417": ("chili", "powder"),
    "45892": ("powdered", "sugar"),
    "12165": ("bacon",),
    "4578": ("pecan",),
    "7805": ("red", "onion"),
    "5169": ("tomato",),
    "7425": ("diced", "tomato"),
    "4557": ("walnut",),
    "6989": ("red", "bell", "pepper"),
    "5715": ("potato",),
    "3766": ("raisin",),
    "6846": ("green", "bell", "pepper"),
    "27204": ("red", "wine", "vinegar"),
    "26669": ("ketchup",),
    "44966": ("margarine",),
    "22504": ("white", "wine"),
    "49296": ("sea", "salt"),
    "26008": ("onion", "powder"),
    "51329": ("banana",),
    "26513": ("mustard", "powder"),
    "8771": ("sesame", "oil"),
    "44896": ("peanut", "oil"),
    "35301": ("cooking", "spray"),
    "23712": ("cocoa", "powder"),
    "53475": ("cider", "vinegar"),
    "42439": ("bread", "crumbs"),
    "3088": ("orange", "peel"),
    "28000": ("active", "dry", "yeast"),
    "53471": ("tabasco", "sauce"),
    "53470": ("hot", "sauce"),
    "4523": ("sesame", "seed"),
    "25490": ("flour", "tortilla"),
    "2013": ("plain", "yogurt"),
    "3001": ("apple",),
    "15071": ("chicken",),
    "11967": ("plain", "lowfat", "yogurt"),
    "37836": ("bok", "choy"),
    "8278": ("shortening",),
    "5799": ("acorn", "squash"),
    "3838": ("mango", "chutney"),
    "49277": ("walnut",),
    "23070": ("caramel", "topping"),
    "19037": ("imitation", "crab"),
    "12893": ("extra", "firm", "tofu"),
    "4756": ("dry", "roasted", "peanuts"),
    "8047": ("grapeseed", "oil"),
    "9539": ("olives",),
    "51362": ("tortilla",),
    "27301": ("baked", "beans"),
    "22670": ("whiskey",),
    "35205": ("vermouth",),
    "33295": ("espresso",),
    "38396": ("small", "shells", "pasta"),
    "4770": ("flax", "seed"),
    "37597": ("popped", "popcorn"),
    "91198": ("ziti", "pasta"),
    "12008": ("canadian", "bacon"),
    "34574": ("chili", "paste"),
    "33128": ("chili", "garlic", "sauce"),
    "91197": ("penne", "pasta"),
    "4928": ("pomegranate", "juice"),
    "5589": ("frozen", "hash", "browns"),
    "8772": ("safflower", "oil"),
    "4966": ("chocolate", "shavings"),
    "794": ("grapefruit", "juice"),
    "19026": ("oyster",),
    "7351": ("white", "mushrooms"),
    "16621": ("biscuit", "dough"),
    "34067": ("dark", "beer"),
    "15424": ("ladyfinger",),
    "295": ("thousand", "island", "dressing"),
    "73123": ("prawn",),
    "8085": ("walnut", "oil"),
    "52470": ("kaiser", "roll"),
    "33770": ("rice", "noodles"),
    "38801": ("arrowroot", "starch"),
    "12896": ("silken", "tofu"),
    "91201": ("farfalle", "pasta"),
    "4794": ("lemonade",),
    "93175": ("tapioca", "flour"),
    "37877": ("habanero", "pepper"),
    "20032": ("sprite",),
    "3487": ("craisins",),
    "15455": ("hot", "dog", "bun"),
    "91214": ("jumbo", "shells", "pasta"),
    "20950": ("condensed", "milk"),
    "9558": ("cheddar", "cheese", "sauce"),
    "16477": ("agra", "peas", "greens"),
    "16514": ("tempeh", "spicy"),
    "16515": ("vegetarian", "jerky", "original"),
    "16693": ("pancake", "wild", "rice", "mix"),
    "16695": ("pancake", "waffle", "grain", "mix"),
    "33366": ("swiss", "cheese"),
    "92017": ("quick", "oats"),
    "4686": ("tahini",),
    "5113": ("onion", "flakes"),
    "5222": ("watercress",),
    "6499": ("kalamata", "olives"),
    "6492": ("roma", "tomatoes"),
    "19029": ("scallops",),
    "26105": ("fennel", "seed"),
    "6863": ("baby", "spinach"),
    "17741": ("white", "kidney", "beans"),
    "38987": ("skirt", "steak"),
    "6251": ("french", "style", "green", "beans"),
    "27980": ("beef", "chuck", "roast"),
    "35078": ("juniper", "berries"),
    "49315": ("raw", "cane", "sugar"),
    "7846": ("green", "olives", "stuffed", "pimento"),
    "26037": ("white", "pepper"),
    "23640": ("ciabatta", "rolls"),
    "58267": ("flank", "steak"),
    "42257": ("pillsbury", "breadsticks"),
    "48217": ("maraschino", "cherries"),
}

EXACT_PRODUCT_CATEGORY_FILTERS_BY_CODE = {
    "1": ("Milk",),
    "2": ("Milk",),
    "4": ("Milk",),
    "12470": ("Frozen Pancakes, Waffles, French Toast & Crepes",),
    "16642": ("Frozen Pancakes, Waffles, French Toast & Crepes",),
    "16643": ("Frozen Pancakes, Waffles, French Toast & Crepes",),
    "16646": ("Frozen Pancakes, Waffles, French Toast & Crepes",),
    "37261": ("Water",),
    "37264": ("Water",),
    "37266": ("Water",),
    "37278": ("Water",),
    "37281": ("Liquid Water Enhancer",),
    "37282": ("Water",),
    "45213": ("Frozen Pancakes, Waffles, French Toast & Crepes",),
    "52742": ("Frozen Pancakes, Waffles, French Toast & Crepes",),
    "91243": ("Other Meats",),
}


PRODUCT_CATEGORY_FILTERS_BY_CODE = {
    "23": ("milk", "milk/cream"),
    "42": ("milk", "milk/cream"),
    "43": ("powdered drinks", "other drinks", "breakfast drinks", "non alcoholic beverages"),
    "52": ("milk", "milk/cream"),
    "67": ("milk", "milk additives"),
    "615": ("plant based milk", "other drinks", "milk additives", "powdered drinks"),
    "618": ("other drinks", "non alcoholic beverages", "drinks flavoured"),
    "4791": ("water", "drink", "beverage"),
    "9558": ("sauce", "condiment", "dip"),
    "1075": ("cheese",),
    "436": ("baby", "infant"),
    "16477": ("frozen prepared", "prepared side", "entree", "small meal", "other deli"),
    "16514": ("vegetarian frozen meats", "other meats", "vegetable based"),
    "16515": ("other snacks", "snack", "jerky"),
    "16693": ("cake", "cookie", "cupcake", "bread", "muffin", "mix"),
    "16695": ("cake", "cookie", "cupcake", "bread", "muffin", "mix"),
    "38579": ("pasta", "noodle", "macaroni"),
    "38591": ("pasta", "noodle"),
    "50343": ("broth", "soup", "stock"),
    "501": ("cream", "dairy", "baking", "bakery"),
    "40775": ("baking", "crust", "dough", "frozen", "pie"),
    "42508": ("bread", "bun", "roll", "bakery"),
    "92863": ("meat", "pork", "sausage"),
    "13021": ("meat", "pork", "sausage"),
    "27004": ("condiment", "sauce", "relish"),
    "31312": ("canned", "fruit", "snack"),
    "46516": ("rice", "grain"),
    "9083": ("sauce", "condiment"),
    "49045": ("baking", "dough", "frozen", "pastry"),
    "35278": ("baking", "spice", "seasoning"),
    "50504": ("soup",),
    "23184": ("baking", "chip", "chocolate", "dessert"),
    "91972": ("salt", "seasoning", "spice"),
    "31545": ("sauce", "condiment"),
    "91947": ("spice", "seasoning"),
    "93138": ("baking", "cereal", "grain"),
    "4715": ("nut", "snack"),
    "15061": ("chicken", "poultry", "meat"),
    "15046": ("chicken", "poultry", "meat"),
    "17230": ("seafood", "fish", "shellfish", "frozen"),
    "27997": ("beef", "meat"),
    "13082": ("sausage", "meat", "pork"),
    "9329": ("pre-packaged", "vegetable", "produce"),
    "90467": ("pre-packaged", "vegetable", "produce"),
    "6032": ("pre-packaged", "vegetable", "produce"),
    "46797": ("fruit", "produce", "pre-packaged", "canned fruit", "baby"),
    "46799": ("fruit", "produce", "pre-packaged", "canned fruit", "baby"),
    "46801": ("fruit", "produce", "pre-packaged", "canned fruit", "baby"),
    "46806": ("fruit", "produce", "pre-packaged", "canned fruit", "baby"),
    "37790": ("soup", "seasoning", "mix"),
    "42358": ("bread", "breading", "baking"),
    "53615": ("sauce", "condiment", "marinade"),
    "36158": ("bread", "bakery"),
    "44895": ("oil",),
    "26627": ("herb", "spice", "produce", "vegetable"),
    "90442": ("produce", "spice", "vegetable"),
    "25760": ("fruit", "produce", "pre-packaged"),
    "47878": ("cheese", "dairy"),
    "93184": ("rice", "grain"),
    "4790": ("soda", "soft drink", "beverage"),
    "23299": ("jam", "jelly", "preserve", "spread"),
    "91953": ("salt", "seasoning", "spice"),
    "38079": ("grain", "rice", "quinoa"),
    "1452": ("cheese", "dairy"),
    "33229": ("cheese", "dairy"),
    "55029": ("cheese", "dairy"),
    "50475": ("soup",),
    "6265": ("canned", "vegetable", "corn"),
    "4521": ("nut", "snack"),
    "34639": ("cracker", "cookie", "snack"),
    "8107": ("fat", "oil", "baking"),
    "9200": ("canned", "vegetable", "condiment"),
    "1005": ("cheese", "dairy"),
    "38064": ("bran", "cereal", "grain"),
    "538": ("cream", "dairy", "sour cream"),
    "23064": ("baking", "dessert", "topping"),
    "23071": ("baking", "dessert", "topping"),
    "7480": ("salsa", "condiment", "sauce"),
    "26024": ("spice", "seasoning"),
    "30261": ("baking", "starch"),
    "92310": ("sauce", "condiment"),
    "37704": ("barley", "grain"),
    "19177": ("bread", "bakery"),
    "38346": ("noodle", "pasta"),
    "42317": ("baking", "mix"),
    "38448": ("baking", "flour"),
    "38022": ("baking", "flour"),
    "1060": ("cheese", "dairy"),
    "48001": ("baking", "pie", "fruit"),
    "53909": ("chip", "chips", "snack"),
    "13234": ("meat", "salami", "sausage"),
    "16455": ("milk", "plant"),
    "4649": ("canned", "coconut", "baking"),
    "9755": ("dried fruit", "fruit", "snack"),
    "36978": ("cheese", "dairy"),
    "17033": ("seafood", "fish", "frozen"),
    "34570": ("fish", "seafood", "condiment"),
    "5711": ("pre-packaged", "vegetable", "produce"),
    "1281": ("cheese", "dairy"),
    "11581": ("meat", "veal"),
    "91272": ("jam", "jelly", "preserve", "spread"),
    "90887": ("jam", "jelly", "preserve", "spread"),
    "41383": ("egg", "substitute"),
    "26013": ("fresh", "produce", "pre-packaged", "herb"),
    "1054": ("cheese", "dairy"),
    "33351": ("cheese", "dairy"),
    "35063": ("spice", "seasoning"),
    "25758": ("fruit", "produce", "pre-packaged"),
    "37838": ("pepper", "produce", "vegetable"),
    "26106": ("spice", "seasoning"),
    "49218": ("candy", "snack"),
    "41219": ("seafood", "fish", "frozen"),
    "26098": ("seasoning", "salt", "spice"),
    "53023": ("gravy", "sauce"),
    "3164": ("canned", "fruit"),
    "3126": ("dried fruit", "fruit", "snack", "wholesome"),
    "41309": ("vinegar", "sauce", "condiment"),
    "7378": ("lentil", "legume", "vegetable"),
    "92163": ("noodle", "soup"),
    "28169": ("noodle", "soup"),
    "58511": ("sausage", "meat", "brat"),
    "22593": ("alcohol", "liquor"),
    "508": ("dessert", "topping", "baking decorations"),
    "26630": ("herb", "spice", "produce", "vegetable"),
    "5359": ("herb", "spice", "produce", "vegetable"),
    "2004": ("ice cream", "frozen yogurt"),
    "48557": ("dried fruit", "fruit", "snack"),
    "52629": ("seafood", "fish", "shellfish", "frozen"),
    "52630": ("seafood", "fish", "shellfish", "frozen"),
    "26017": ("baking", "spice", "seasoning"),
    "6813": ("pre-packaged", "vegetable", "produce"),
    "53474": ("sauce", "condiment"),
    "4511": ("baking", "coconut", "nut", "snack"),
    "4573": ("baking", "coconut", "nut", "snack"),
    "22604": ("wine", "alcohol", "cooking"),
    "14984": ("canned", "vegetable", "pepper"),
    "5001": ("pre-packaged", "vegetable", "produce"),
    "41524": ("baking", "chocolate", "candy"),
    "22513": ("alcohol", "liquor"),
    "5446": ("vegetable", "produce", "canned", "condiment"),
    "22594": ("alcohol", "liquor"),
    "38277": ("baking", "flour"),
    "22614": ("beer", "alcohol"),
    "90965": ("oil",),
    "13472": ("tortilla", "flatbread", "mexican", "bread", "buns"),
    "5172": ("pre-packaged", "vegetable", "produce"),
    "46086": ("baking", "flour"),
    "34814": ("sweetener", "sugar", "baking"),
    "6298": ("canned", "vegetable", "baking"),
    "45336": ("mustard", "condiment", "sauce"),
    "35682": ("mustard", "condiment", "sauce"),
    "3006": ("fruit", "canned", "snack"),
    "27367": ("pre-packaged", "fruit", "produce"),
    "5441": ("pre-packaged", "vegetable", "produce"),
    "26482": ("spice", "seasoning"),
    "24169": ("baking", "chocolate", "candy"),
    "25778": ("nut & seed butters", "nut butter", "peanut butter"),
    "9114": ("sauce", "condiment"),
    "1272": ("cheese", "dairy"),
    "26901": ("spice", "seasoning"),
    "5206": ("pre-packaged", "vegetable", "produce"),
    "3380": ("pre-packaged", "fruit", "produce"),
    "25570": ("salsa", "condiment", "sauce"),
    "50477": ("soup",),
    "90374": ("soup",),
    "91928": ("salt", "seasoning", "spice"),
    "90530": ("pre-packaged", "vegetable", "produce"),
    "5511": ("pickle", "olive", "relish", "condiment", "vegetable"),
    "3381": ("pre-packaged", "fruit", "produce"),
    "4504": ("nut", "snack"),
    "49260": ("nut", "snack"),
    "1793": ("broth", "soup", "stock"),
    "22501": ("wine", "alcohol", "cooking"),
    "3990": ("juice", "drink", "beverage"),
    "5104": ("pre-packaged", "vegetable", "produce"),
    "26622": ("herb", "spice", "produce", "vegetable"),
    "5055": ("pre-packaged", "vegetable", "produce"),
    "7805": ("pre-packaged", "vegetable", "produce"),
    "5169": ("pre-packaged", "vegetable", "produce"),
    "7425": ("canned", "vegetable"),
    "6989": ("pre-packaged", "vegetable", "produce"),
    "6846": ("pre-packaged", "vegetable", "produce"),
    "5715": ("pre-packaged", "vegetable", "produce"),
    "12165": ("bacon", "meat"),
    "30000": ("baking", "flour", "corn meal"),
    "36417": ("spice", "seasoning"),
    "45892": ("sugar", "baking"),
    "4578": ("nut", "snack"),
    "4557": ("nut", "snack"),
    "3766": ("fruit", "snack"),
    "27204": ("vinegar", "cooking wine", "sauce"),
    "26669": ("ketchup", "condiment", "sauce"),
    "44966": ("butter", "spread", "margarine"),
    "22504": ("wine", "alcohol", "cooking"),
    "49296": ("salt", "seasoning", "spice"),
    "26008": ("seasoning", "spice"),
    "51329": ("pre-packaged", "fruit", "produce"),
    "26513": ("seasoning", "spice"),
    "8771": ("oil",),
    "44896": ("oil",),
    "35301": ("oil", "spray"),
    "23712": ("baking", "cocoa"),
    "53475": ("vinegar", "cooking wine", "sauce"),
    "42439": ("bread", "breading", "baking"),
    "3088": ("fruit", "produce", "spice"),
    "28000": ("baking",),
    "53471": ("sauce", "condiment"),
    "53470": ("sauce", "condiment"),
    "4523": ("seed", "spice", "snack"),
    "25490": ("tortilla", "flatbread", "mexican", "bread", "buns"),
    "2013": ("yogurt", "dairy"),
    "20950": ("milk", "dairy", "canned"),
    "3001": ("pre-packaged", "fruit", "produce"),
    "15071": ("chicken", "poultry", "meat"),
    "11967": ("yogurt", "dairy"),
    "37836": ("pre-packaged", "vegetable", "produce"),
    "8278": ("shortening", "oil", "baking"),
    "5799": ("pre-packaged", "vegetable", "produce"),
    "3838": ("sauce", "condiment", "chutney"),
    "49277": ("nut", "snack"),
    "23070": ("syrup", "topping", "dessert"),
    "19037": ("seafood", "fish", "shellfish"),
    "12893": ("tofu", "plant", "meat"),
    "4756": ("nut", "snack", "peanut"),
    "8047": ("oil",),
    "9539": ("olive", "pickle", "relish", "vegetable"),
    "51362": ("tortilla", "flatbread", "mexican", "bread", "buns"),
    "27301": ("bean", "legume", "vegetable"),
    "22670": ("alcohol", "liquor"),
    "35205": ("wine", "alcohol", "cooking"),
    "33295": ("coffee",),
    "38396": ("pasta", "noodle"),
    "4770": ("seed", "snack", "spice"),
    "37597": ("popcorn", "snack"),
    "91198": ("pasta", "noodle"),
    "12008": ("bacon", "meat"),
    "34574": ("sauce", "condiment", "pepper"),
    "33128": ("sauce", "condiment"),
    "91197": ("pasta", "noodle"),
    "4928": ("juice", "drink", "beverage"),
    "5589": ("frozen", "potato", "vegetable"),
    "8772": ("oil",),
    "4966": ("baking", "chocolate", "dessert", "topping"),
    "794": ("juice", "drink", "beverage"),
    "19026": ("seafood", "fish", "shellfish"),
    "7351": ("pre-packaged", "vegetable", "produce"),
    "16621": ("baking", "dough", "bread", "bakery"),
    "34067": ("beer", "alcohol"),
    "15424": ("cookie", "bakery"),
    "295": ("dressing", "mayonnaise", "condiment"),
    "73123": ("seafood", "fish", "shellfish", "frozen"),
    "8085": ("oil",),
    "52470": ("bread", "bun", "roll", "bakery"),
    "33770": ("noodle", "pasta"),
    "38801": ("baking", "flour", "starch"),
    "12896": ("tofu", "plant", "meat"),
    "91201": ("pasta", "noodle"),
    "4794": ("juice", "drink", "beverage"),
    "93175": ("baking", "flour", "starch"),
    "37877": ("pre-packaged", "vegetable", "produce", "pepper"),
    "20032": ("soda", "soft drink", "beverage"),
    "3487": ("dried fruit", "fruit", "snack"),
    "15455": ("bread", "bun", "roll", "bakery"),
    "91214": ("pasta", "noodle"),
    "33366": ("cheese", "dairy"),
    "92017": ("cereal", "oat", "grain"),
    "4686": ("tahini", "sesame", "dressing", "mayonnaise", "nut", "seed", "spice"),
    "5113": ("spice", "seasoning"),
    "5222": ("pre-packaged", "vegetable", "produce"),
    "6499": ("olive", "pickle", "relish", "vegetable"),
    "6492": ("pre-packaged", "vegetable", "produce", "tomatoes"),
    "19029": ("seafood", "fish", "shellfish", "frozen"),
    "26105": ("spice", "seasoning"),
    "6863": ("pre-packaged", "vegetable", "produce"),
    "17741": ("bean", "legume", "vegetable", "canned", "bottled"),
    "38987": ("meat", "beef"),
    "6251": ("canned", "frozen", "vegetable"),
    "27980": ("meat", "beef"),
    "35078": ("spice", "seasoning"),
    "49315": ("sugar", "baking"),
    "7846": ("olive", "pickle", "relish", "vegetable"),
    "26037": ("spice", "seasoning"),
    "23640": ("bread", "bun", "roll", "bakery"),
    "58267": ("meat", "beef"),
    "42257": ("baking", "dough", "bread", "bakery"),
    "48217": ("baking", "fruit", "topping", "canned"),
}

_QUERY_TERM_DROP_CANDIDATES_CACHE: dict[str, set[str]] | None = None
_RETAIL_QUERY_REWRITE_PLAN_CACHE: dict[str, dict[str, str]] | None = None


def slugify(value: str, max_len: int = 80) -> str:
    value = matcher.normalize_text(value)
    value = re.sub(r"[^a-z0-9]+", "_", value).strip("_")
    return value[:max_len].strip("_") or "esha"


def fts_token(term: str) -> str:
    return re.sub(r"[^a-z0-9]", "", term.lower())


def term_variants(term: str) -> list[str]:
    term = fts_token(term)
    if not term:
        return []
    variants = {term}
    if term == "bean":
        variants.add("beans")
    elif term == "beans":
        variants.add("bean")
    elif term == "chickpea":
        variants.update({"chickpeas", "garbanzo", "garbanzos"})
    elif term == "garbanzo":
        variants.update({"garbanzos", "chickpea", "chickpeas"})
    elif term == "potato":
        variants.add("potatoes")
    elif term == "tomato":
        variants.add("tomatoes")
    elif term == "pasta":
        variants.update({"pastas", "macaroni", "noodle", "noodles"})
    elif term == "macaroni":
        variants.update({"mac", "pasta", "pastas", "noodle", "noodles"})
    elif term == "mac":
        variants.update({"macaroni", "pasta", "pastas"})
    elif term == "noodle":
        variants.update({"noodles", "pasta", "pastas", "macaroni"})
    elif term == "fettuccini":
        variants.add("fettuccine")
    elif term == "fettuccine":
        variants.add("fettuccini")
    elif term == "bow":
        variants.update({"bows", "bowtie", "bowties", "farfalle"})
    elif term == "tie":
        variants.update({"ties", "bowtie", "bowties", "farfalle"})
    elif term == "mayo":
        variants.add("mayonnaise")
    elif term == "mayonnaise":
        variants.add("mayo")
    elif term == "yogurt":
        variants.update({"yoghurt", "froyo"})
    elif term == "yoghurt":
        variants.update({"yogurt", "froyo"})
    elif term == "froyo":
        variants.update({"yogurt", "yoghurt"})
    elif term == "cookie":
        variants.add("cookies")
    elif term == "fry":
        variants.add("fries")
    elif term == "fries":
        variants.add("fry")
    elif term not in NO_PLURAL_VARIANT and not term.endswith("s"):
        variants.add(term + "s")
    return sorted(variants)


PROTECTED_CORE_TERMS_BY_CODE = {
    "1": {"whole", "milk"},
    "2": {"2", "milk"},
    "4": {"1", "milk"},
    "43": {"carob"},
    "52": {"low", "sodium"},
    "67": {"skim", "milk", "powder"},
    "615": {"rice", "milk", "vanilla"},
    "618": {"vanilla", "drink"},
    "9558": {"cheddar", "cheese", "sauce"},
    "1075": {"parmesan", "grated", "cheese"},
    "436": {"baby", "infant", "food", "potato"},
    "12470": {"frozen", "waffle"},
    "16477": {"agra", "peas", "greens"},
    "16642": {"frozen", "pancake"},
    "16643": {"frozen", "pancake", "buttermilk"},
    "16646": {"frozen", "pancake", "blueberry"},
    "16514": {"tempeh", "spicy"},
    "16515": {"jerky", "jurky"},
    "16693": {"pancake", "wild", "rice"},
    "16695": {"waffle", "pancake", "grain"},
    "37261": {"focus", "water"},
    "37264": {"dwnld", "water"},
    "37266": {"connect", "water"},
    "37278": {"multi", "water"},
    "37281": {"stur"},
    "37282": {"sparkling", "water"},
    "45213": {"frozen", "waffle"},
    "52742": {"frozen", "waffle", "blueberry"},
    "91243": {"tempeh"},
    "46797": {"applesauce"},
    "46799": {"applesauce", "cinnamon"},
    "46801": {"applesauce"},
    "46806": {"applesauce", "sugar"},
}

STRICT_QUERY_ONLY_CODES = {
    "37264",
    "37266",
    "37278",
}


def query_terms_for(profile: matcher.EshaProfile) -> tuple[str, ...]:
    if profile.code in QUERY_TERM_OVERRIDES_BY_CODE:
        return QUERY_TERM_OVERRIDES_BY_CODE[profile.code]
    terms = []
    for term in profile.hard_terms:
        if term not in terms:
            terms.append(term)
    for token in profile.tokens:
        if token in IDENTITY_QUERY_TERMS and token not in terms:
            terms.append(token)
    for attr in profile.attrs:
        if attr in {"canned", "frozen", "unsalted", "smoked", "pickled"} and attr not in terms:
            terms.append(attr)
        elif profile.family == "milk" and attr in {"condensed", "evaporated", "skim"} and attr not in terms:
            terms.append(attr)
        elif attr == "low_sodium":
            for token in ("low", "sodium"):
                if token not in terms:
                    terms.append(token)
        elif attr == "dry":
            dry_term = "powder" if profile.family in {"milk", "beverage"} else "dry"
            if dry_term not in terms:
                terms.append(dry_term)
    return tuple(term for term in terms if term not in GENERIC_QUERY_TERMS)


DestinationIndex = tuple[dict[str, list[matcher.EshaProfile]], dict[str, tuple[str, ...]]]


def build_destination_index(profiles: list[matcher.EshaProfile]) -> DestinationIndex:
    by_term: dict[str, list[matcher.EshaProfile]] = defaultdict(list)
    terms_by_code: dict[str, tuple[str, ...]] = {}
    for profile in profiles:
        if profile.skip_reason:
            continue
        terms = query_terms_for(profile)
        if not terms:
            continue
        terms_by_code[profile.code] = terms
        for term in terms:
            by_term[term].append(profile)
            for variant in term_variants(term):
                by_term[variant].append(profile)
    return by_term, terms_by_code


def product_terms_for_destination(product: dict[str, str]) -> set[str]:
    terms = set(matcher.tokens_for(product["description"]))
    terms.update(matcher.tokens_for(product["category"]))
    terms.update(matcher.tokens_for(product.get("ingredients", "")))
    if "garbanzo" in terms:
        terms.add("chickpea")
    if "chickpea" in terms:
        terms.add("garbanzo")
    if "mayo" in terms:
        terms.add("mayonnaise")
    if "mayonnaise" in terms:
        terms.add("mayo")
    if "powder" in terms:
        terms.add("dry")
    if "dry" in terms:
        terms.add("powder")
    if "skim" in terms:
        terms.add("nonfat")
    if "nonfat" in terms:
        terms.add("skim")
    return terms


def product_matches_terms(product_norm: str, product_tokens: set[str], terms: tuple[str, ...]) -> bool:
    if not terms:
        return False
    return all(matcher.product_has_term(product_norm, product_tokens, term) for term in terms)


def destination_candidates_for_product(
    product: dict[str, str],
    source: matcher.EshaProfile,
    destination_index: DestinationIndex,
    source_noise_terms: set[str],
    max_destinations: int = 5,
    max_profiles_per_seed_term: int = 500,
) -> list[tuple[matcher.EshaProfile, tuple[str, ...], str]]:
    by_term, terms_by_code = destination_index
    product_norm = matcher.normalize_text(product["description"])
    product_description_tokens = set(matcher.tokens_for(product["description"]))
    tokens = product_terms_for_destination(product)
    source_terms = terms_by_code.get(source.code, query_terms_for(source))
    seed_terms = {term for term in source_noise_terms if not term.startswith("missing_") and not term.startswith("phrase_")}
    if not seed_terms:
        seed_terms = tokens - set(source_terms)
    if not seed_terms:
        seed_terms = tokens

    candidates: dict[str, matcher.EshaProfile] = {}
    for term in seed_terms:
        profiles_for_term = by_term.get(term, ())
        if (
            max_profiles_per_seed_term
            and len(profiles_for_term) > max_profiles_per_seed_term
            and term not in source_noise_terms
        ):
            continue
        for profile in profiles_for_term:
            candidates[profile.code] = profile

    rows = []
    for profile in candidates.values():
        if profile.code == source.code or profile.skip_reason:
            continue
        terms = terms_by_code.get(profile.code)
        if not terms:
            continue
        if not product_matches_terms(product_norm, product_description_tokens, terms):
            continue
        if (
            profile.family != source.family
            and category_signal(product["category"], profile.family, set(terms), product["description"]) == "category_noise"
        ):
            continue
        noise_overlap = source_noise_terms & set(terms)
        reason = "more_specific" if len(terms) > len(source_terms) else "alternate"
        if noise_overlap:
            reason = "noise_destination"
        elif profile.family != source.family:
            reason = "different_family"
        rows.append((profile, terms, reason))

    reason_order = {
        "noise_destination": 0,
        "more_specific": 1,
        "different_family": 2,
        "alternate": 3,
    }
    rows.sort(
        key=lambda item: (
            reason_order.get(item[2], 9),
            item[0].family != source.family,
            -len(item[1]),
            len(item[0].description),
            int(item[0].code) if item[0].code.isdigit() else 10**9,
        )
    )
    return rows[:max_destinations]


def fts_query(terms: tuple[str, ...]) -> str:
    clauses = []
    for term in terms:
        if term in GENERIC_QUERY_TERMS:
            continue
        variants = term_variants(term)
        if not variants:
            continue
        if len(variants) == 1:
            clauses.append(variants[0])
        else:
            clauses.append("(" + " OR ".join(variants) + ")")
    return " AND ".join(clauses)


def dedupe_terms(terms: list[str]) -> tuple[str, ...]:
    deduped = []
    for term in terms:
        if term and term not in deduped:
            deduped.append(term)
    return tuple(deduped)


def load_query_term_drop_candidates(path: Path = QUERY_TERM_DROP_CANDIDATES_CSV) -> dict[str, set[str]]:
    global _QUERY_TERM_DROP_CANDIDATES_CACHE
    if _QUERY_TERM_DROP_CANDIDATES_CACHE is not None:
        return _QUERY_TERM_DROP_CANDIDATES_CACHE
    candidates: dict[str, set[str]] = defaultdict(set)
    if not path.exists():
        _QUERY_TERM_DROP_CANDIDATES_CACHE = {}
        return _QUERY_TERM_DROP_CANDIDATES_CACHE
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            if row.get("candidate_action") != "demote_from_query":
                continue
            code = str(row.get("esha_code") or "").strip()
            term = str(row.get("term") or "").strip()
            if code and term:
                candidates[code].add(term)
    _QUERY_TERM_DROP_CANDIDATES_CACHE = {code: terms for code, terms in candidates.items()}
    return _QUERY_TERM_DROP_CANDIDATES_CACHE


def split_pipe_terms(raw: str) -> tuple[str, ...]:
    return dedupe_terms([part.strip() for part in str(raw or "").split("|") if part.strip()])


def load_retail_query_rewrite_plan(path: Path = RETAIL_QUERY_REWRITE_PLAN_CSV) -> dict[str, dict[str, str]]:
    global _RETAIL_QUERY_REWRITE_PLAN_CACHE
    if _RETAIL_QUERY_REWRITE_PLAN_CACHE is not None:
        return _RETAIL_QUERY_REWRITE_PLAN_CACHE
    if not path.exists():
        _RETAIL_QUERY_REWRITE_PLAN_CACHE = {}
        return _RETAIL_QUERY_REWRITE_PLAN_CACHE
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        rows = {
            str(row.get("esha_code") or "").strip(): {str(key): str(value or "") for key, value in row.items()}
            for row in reader
            if str(row.get("esha_code") or "").strip()
        }
    _RETAIL_QUERY_REWRITE_PLAN_CACHE = rows
    return _RETAIL_QUERY_REWRITE_PLAN_CACHE


def rewrite_plan_for(profile: matcher.EshaProfile) -> dict[str, str] | None:
    return load_retail_query_rewrite_plan().get(profile.code)


def term_roles_for(profile: matcher.EshaProfile, primary: tuple[str, ...]) -> dict[str, str]:
    roles: dict[str, str] = {}
    demoted = load_query_term_drop_candidates().get(profile.code, set())
    attrs = set(profile.attrs)
    for term in primary:
        if term in INGREDIENT_ONLY_TERMS:
            roles[term] = "ingredient_only"
        elif term in PROCESS_ONLY_TERMS:
            roles[term] = "process_only"
        elif term in attrs or term in STATE_OR_PROCESS_TERMS:
            roles[term] = "state_only" if term in SOFT_STATE_TERMS or term in {"canned", "dried", "frozen", "salted", "smoked", "pickled", "unsalted"} else "process_only"
        elif term in CLAIM_TRANSLATION_TERMS and profile.family in RETAIL_CLAIM_FAMILIES:
            roles[term] = "query_optional_or_claim_translation"
        elif term in demoted:
            roles[term] = "do_not_query"
        else:
            roles[term] = "query_required"
    return roles


def translated_retail_terms_for(profile: matcher.EshaProfile, primary: tuple[str, ...]) -> dict[str, tuple[str, ...]]:
    termset = set(primary)
    translations: dict[str, tuple[str, ...]] = {}
    if profile.family in RETAIL_CLAIM_FAMILIES and {"reduced", "calorie"} <= termset:
        translations["reduced"] = ("light", "diet", "free")
        translations["calorie"] = ("light", "diet", "free")
    if profile.family == "beverage" and {"hot", "cocoa"} <= termset and ("aspartame" in termset or "sugar_free" in set(profile.attrs)):
        translations["aspartame"] = ("sugar free", "no sugar added")
    if "wtr" in termset or "water" in termset:
        translations["wtr"] = ()
        translations["water"] = ()
    return translations


def semantic_filter_terms_for(profile: matcher.EshaProfile, primary: tuple[str, ...]) -> tuple[str, ...]:
    roles = term_roles_for(profile, primary)
    terms = set(primary) | set(profile.attrs) | set(profile.hard_terms)
    filters = [
        term
        for term, role in roles.items()
        if role in {"ingredient_only", "state_only"}
    ]
    if profile.family == "milk" and {"condensed", "evaporated"} & terms:
        filters = [term for term in filters if term != "canned"]
    base_hard_terms = [term for term in profile.hard_terms if term not in STATE_OR_PROCESS_TERMS and term not in PEEL_PROXY_TERMS]
    if profile.family in {"fruit", "vegetable"} and {"fresh", "raw"} & set(profile.attrs) and len(base_hard_terms) == 1:
        filters.append("single_commodity")
    if any(term in PEEL_PROXY_TERMS for term in profile.hard_terms):
        filters.append("produce_proxy_peel")
    return dedupe_terms(filters)


def infant_core_terms(primary: tuple[str, ...]) -> tuple[str, ...]:
    cues = [term for term in primary if term in INFANT_FLAVOR_CUES and term not in INFANT_ROUTING_TERMS]
    return tuple(cues[:2])


def recommended_category_terms_for(profile: matcher.EshaProfile, primary: tuple[str, ...]) -> tuple[str, ...]:
    terms = set(primary) | set(profile.attrs)
    if "infant" in terms or "baby" in terms:
        if "cereal" in terms or "oatmeal" in terms or "rice" in terms or "grain" in terms:
            return ("baby", "cereal", "processed cereal")
        return ("baby", "infant")
    if "bagel" in terms:
        return ("bagel", "bread", "buns")
    if "tortilla" in terms:
        return ("tortilla", "mexican", "bread", "buns")
    if "cracker" in terms or "crackers" in terms or "melba" in terms or "toast" in terms:
        return ("cracker", "crackers", "biscotti", "cookies", "snacks")
    if profile.family == "milk" and {"condensed", "eggnog", "evaporated"} & terms:
        return ("milk",)
    if profile.family == "milk" and "malted" in terms:
        return ("powdered", "not ready to drink")
    if profile.family == "milk" and "buttermilk" in terms:
        if "pancake" in terms or "waffle" in terms:
            return ("mix", "baking", "frozen")
        if "biscuit" in terms or "biscuits" in terms:
            return ("biscuits", "frozen bread", "sandwiches")
        if "ranch" in terms or "dressing" in terms or "salad" in terms:
            return ("dressing", "dips", "sauces")
        return ("milk",)
    if "ensure" in terms or "pediasure" in terms:
        return ("energy", "protein", "drink")
    if {"cinnamon", "roll"} <= terms or {"sweet", "roll"} <= terms or "danish" in terms:
        return ("sweet rolls", "pastries", "cakes", "dough")
    if "oatmeal" in terms or "farina" in terms:
        return ("cereal", "processed cereal")
    if {"hamburger", "helper"} <= terms:
        return ("mix", "baking", "meal")
    if {"graham", "cracker"} <= terms or {"graham", "crackers"} <= terms:
        return ("cookies", "biscuits", "cracker")
    if "wafer" in terms:
        return ("cookies", "biscuits")
    if profile.family == "soup":
        if {"pepper", "jalapeno"} <= terms or {"pepper", "green"} <= terms:
            return ("peppers", "canned vegetables", "pickles", "relishes")
        if "soup" in terms or "chili" in terms or "stew" in terms:
            return ("soup", "prepared soups", "canned condensed soup")
    if {"fruit", "twist"} <= terms or {"fruit", "twists"} <= terms or {"fruit", "leather"} <= terms or {"fruit", "foot"} <= terms:
        return ("snacks", "candy")
    if "lemonade" in terms and "frozen" in terms:
        return ("frozen fruit", "juice", "drink")
    if "pizza" in terms:
        return ("pizza", "crust")
    if {"french", "fry"} <= terms or {"french", "fries"} <= terms:
        return ("french fries",)
    if "frappuccino" in terms:
        return ("other drinks", "coffee")
    if "latte" in terms or "cappuccino" in terms:
        return ("other drinks", "coffee", "tea")
    if profile.family == "cream" and {"cream", "soup"} <= terms:
        return ("soup", "prepared soups", "canned condensed soup")
    if profile.family == "cream" and {"sour", "cream"} <= terms:
        return ("cream", "dips")
    if profile.family == "cream" and ({"whipped", "cream"} <= terms or {"whip", "cream"} <= terms or {"whipping", "cream"} <= terms):
        return ("cream",)
    if {"hot", "cocoa"} <= terms:
        return ("powdered drinks", "coffee")
    if profile.family in {"fruit", "vegetable"} and {"fresh", "raw"} & terms:
        return ("pre-packaged", "produce")
    if profile.family == "spice" and {"fresh", "raw"} & terms:
        return ("pre-packaged", "produce", "herb")
    if profile.family in {"fruit", "vegetable", "spice"} and "frozen" in terms:
        return ("frozen",)
    if profile.family in {"fruit", "vegetable", "spice"} and "canned" in terms:
        return ("canned",)
    if profile.family in {"fruit", "vegetable", "spice"} and "dried" in terms:
        return ("dried", "snack")
    if has_candy_context(terms, profile.description):
        return CANDY_CATEGORY_HINTS
    if has_prepared_food_context(terms, profile.description):
        return CATEGORY_HINTS["prepared_food"]
    return PRODUCT_CATEGORY_FILTERS_BY_CODE.get(profile.code, ())


def routing_fix_applied_for(profile: matcher.EshaProfile, primary: tuple[str, ...]) -> bool:
    termset = set(primary)
    if has_prepared_food_context(termset, profile.description):
        return True
    if profile.family == "condiment" and {"mayo", "mayonnaise"} & termset:
        if any(term in termset for term in CONTEXT_EXTRA_NOISE["mayonnaise"]):
            return True
    return False


def planned_query_attempt_for(profile: matcher.EshaProfile) -> tuple[str, tuple[str, ...]] | None:
    row = rewrite_plan_for(profile)
    if not row:
        return None
    if row.get("exactness_status") != "strong":
        return None
    terms = split_pipe_terms(row.get("query_terms_after", ""))
    if not terms:
        return None
    return ("rewrite_plan", terms)


def category_terms_for_profile(profile: matcher.EshaProfile) -> tuple[str, ...]:
    exact_terms = EXACT_PRODUCT_CATEGORY_FILTERS_BY_CODE.get(profile.code, ())
    if exact_terms:
        return tuple(f"={term}" for term in exact_terms)
    explicit_terms = PRODUCT_CATEGORY_FILTERS_BY_CODE.get(profile.code, ())
    row = rewrite_plan_for(profile)
    if row and row.get("exactness_status") == "strong":
        terms = split_pipe_terms(row.get("category_terms_after", ""))
        if terms:
            return terms
    if row and row.get("exactness_status") == "unresolved":
        if explicit_terms:
            return explicit_terms
        terms = split_pipe_terms(row.get("category_terms_after", ""))
        if terms:
            return terms
    return explicit_terms


def semantic_filters_for_profile(profile: matcher.EshaProfile) -> tuple[str, ...]:
    row = rewrite_plan_for(profile)
    if row and row.get("exactness_status") in {"strong", "unresolved"}:
        return split_pipe_terms(row.get("semantic_filter_terms", ""))
    return ()


def retail_cleanup_primary_terms(profile: matcher.EshaProfile, primary: tuple[str, ...]) -> tuple[str, ...]:
    demoted = load_query_term_drop_candidates().get(profile.code, set())
    if not demoted:
        return ()
    cleaned = dedupe_terms([term for term in primary if term not in demoted])
    return cleaned if cleaned and cleaned != primary else ()


def retail_claim_attempts_for(profile: matcher.EshaProfile, primary: tuple[str, ...]) -> list[tuple[str, tuple[str, ...]]]:
    termset = set(primary)
    code = getattr(profile, "code", "")
    singular_shapes = {"bar", "cone", "float", "sandwich"} & termset
    attempts: list[tuple[str, tuple[str, ...]]] = []
    if code == "16515":
        attempts.append(("retail_vegetarian_jerky", dedupe_terms(["vegetarian", "jerky"])))
        attempts.append(("retail_vegan_jerky", dedupe_terms(["vegan", "jerky"])))
        attempts.append(("retail_original_vegan_jerky", dedupe_terms(["original", "vegan", "jerky"])))
        attempts.append(("retail_original_vegetarian_jerky", dedupe_terms(["original", "vegetarian", "jerky"])))
    if code == "16514":
        attempts.append(("retail_tempeh", ("tempeh",)))
        attempts.append(("retail_spicy_tempeh", dedupe_terms(["spicy", "tempeh"])))
    if code == "16693":
        attempts.append(("retail_wild_rice_pancake_mix", dedupe_terms(["wild", "rice", "pancake", "mix"])))
    if code == "16695":
        attempts.append(("retail_grain_pancake_waffle_mix", dedupe_terms(["grain", "pancake", "waffle", "mix"])))
        if "10" in termset:
            attempts.append(("retail_10_grain_pancake_waffle_mix", dedupe_terms(["10", "grain", "pancake", "waffle", "mix"])))
    if "infant" in termset or "baby" in termset:
        core_terms = infant_core_terms(primary)
        if "cereal" in termset or "oatmeal" in termset or "rice" in termset or "grain" in termset:
            attempts.append(("retail_baby_cereal", dedupe_terms(["baby", "cereal"])))
            for cue in ("oatmeal", "rice", "grain"):
                if cue in termset:
                    attempts.append((f"retail_baby_cereal_{cue}", dedupe_terms(["baby", "cereal", cue])))
            for cue in core_terms:
                attempts.append((f"retail_baby_cereal_{cue}", dedupe_terms(["baby", "cereal", cue])))
        else:
            attempts.append(("retail_baby_food", dedupe_terms(["baby", "food"])))
            for cue in core_terms:
                attempts.append((f"retail_baby_food_{cue}", dedupe_terms(["baby", "food", cue])))
            if "juice" in termset:
                attempts.append(("retail_baby_juice", dedupe_terms(["baby", "juice"])))
    if profile.family == "milk":
        if "evaporated" in termset:
            attempts.append(("retail_evaporated_milk", dedupe_terms(["evaporated", "milk"])))
            if "skim" in termset:
                attempts.append(("retail_evaporated_skim_milk", dedupe_terms(["evaporated", "skim", "milk"])))
        if "condensed" in termset:
            attempts.append(("retail_condensed_milk", dedupe_terms(["condensed", "milk"])))
            if "sweetened" in termset:
                attempts.append(("retail_sweetened_condensed_milk", dedupe_terms(["sweetened", "condensed", "milk"])))
        if "eggnog" in termset:
            attempts.append(("retail_eggnog", ("eggnog",)))
        if "malted" in termset:
            attempts.append(("retail_malted_milk", dedupe_terms(["malted", "milk"])))
            attempts.append(("retail_malted_milk_mix", dedupe_terms(["malted", "milk", "mix"])))
            if "chocolate" in termset:
                attempts.append(("retail_chocolate_malted_milk", dedupe_terms(["malted", "milk", "chocolate"])))
    if "cheddar" in termset and "sauce" in termset:
        attempts.append(("retail_cheddar_cheese_sauce", dedupe_terms(["cheddar", "cheese", "sauce"])))
        attempts.append(("retail_double_cheddar_sauce", dedupe_terms(["double", "cheddar", "sauce"])))
    if profile.family in RETAIL_CLAIM_FAMILIES and {"reduced", "calorie"} <= termset:
        base = [term for term in primary if term not in {"reduced", "calorie"}]
        for label, extra in (
            ("retail_claim_light", ("light",)),
            ("retail_claim_diet", ("diet",)),
            ("retail_claim_free", ("free",)),
        ):
            attempts.append((label, dedupe_terms(base + list(extra))))
    if profile.family == "beverage" and "chocolate" in termset and ("powder" in termset or "dry" in profile.attrs):
        cocoa_terms = []
        for term in primary:
            if term == "chocolate":
                cocoa_terms.append("cocoa")
            elif term != "dairy":
                cocoa_terms.append(term)
        attempts.append(("retail_chocolate_cocoa", dedupe_terms(cocoa_terms)))
        if "aspartame" in termset or {"reduced", "calorie"} <= termset:
            base = [term for term in cocoa_terms if term not in {"aspartame", "reduced", "calorie"}]
            attempts.append(
                (
                    "retail_hot_cocoa_sugar_free",
                    dedupe_terms(base + ["hot", "sugar", "free"]),
                )
            )
            stripped = [
                term
                for term in primary
                if term
                not in {"aspartame", "calcium", "calorie", "dairy", "dry", "low", "packet", "phosphoru", "powder", "reduced", "wtr"}
            ]
            identity = [term for term in stripped if term in {"drink", "chocolate"}]
            if identity:
                attempts.append(
                    (
                        "retail_chocolate_drink_sugar_free_mix",
                        dedupe_terms(identity + ["sugar", "free", "mix"]),
                    )
                )
                attempts.append(
                    (
                        "retail_chocolate_drink_no_sugar_added_mix",
                        dedupe_terms(identity + ["sugar", "added", "mix"]),
                    )
                )
            attempts.append(
                (
                    "retail_hot_cocoa_no_sugar_added_mix",
                    dedupe_terms(["hot", "cocoa", "sugar", "added", "mix"]),
                )
            )
    if profile.family == "beverage" and {"hot", "cocoa"} <= termset and ("sugar_free" in set(profile.attrs) or "aspartame" in termset or {"low", "calorie"} <= termset or {"reduced", "calorie"} <= termset):
        attempts.append(
            (
                "retail_hot_cocoa_sugar_free_mix",
                dedupe_terms(["hot", "cocoa", "sugar", "free", "mix"]),
            )
        )
        attempts.append(
            (
                "retail_hot_cocoa_no_sugar_added_mix",
                dedupe_terms(["hot", "cocoa", "sugar", "added", "mix"]),
            )
        )
    if {"ice", "cream"} <= termset:
        if not singular_shapes:
            attempts.append(("retail_ice_cream", ("ice", "cream")))
        for shape in ("bar", "cone", "sandwich", "float"):
            if shape in termset:
                attempts.append((f"retail_ice_cream_{shape}", dedupe_terms(["ice", "cream", shape])))
    if {"fruit", "twists"} <= termset or {"fruit", "twist"} <= termset:
        attempts.append(("retail_fruit_twists", dedupe_terms(["fruit", "twists"])))
    if {"fruit", "leather"} <= termset:
        attempts.append(("retail_fruit_leather", dedupe_terms(["fruit", "leather"])))
    if {"fruit", "foot"} <= termset:
        attempts.append(("retail_fruit_by_the_foot", dedupe_terms(["fruit", "foot"])))
    if {"fruit", "roll"} <= termset:
        attempts.append(("retail_fruit_rollups", dedupe_terms(["fruit", "roll"])))
    if "lemonade" in termset and "frozen" in termset:
        attempts.append(("retail_frozen_lemonade_concentrate", dedupe_terms(["frozen", "concentrate", "lemonade"])))
        if "pink" in termset:
            attempts.append(("retail_frozen_pink_lemonade_concentrate", dedupe_terms(["pink", "frozen", "concentrate", "lemonade"])))
    if {"salad", "dressing"} <= termset:
        attempts.append(("retail_salad_dressing", dedupe_terms(["salad", "dressing"])))
        for cue in ("french", "italian", "ranch", "vinaigrette"):
            if cue in termset:
                attempts.append((f"retail_salad_dressing_{cue}", dedupe_terms(["salad", "dressing", cue])))
    if {"miracle", "whip"} <= termset:
        attempts.append(("retail_miracle_whip", dedupe_terms(["miracle", "whip"])))
    if "pickle" in termset and {"bread", "butter"} <= termset:
        attempts.append(("retail_bread_and_butter_pickles", dedupe_terms(["bread", "butter", "pickles"])))
    if "sandwich" in termset:
        attempts.append(("retail_sandwich", ("sandwich",)))
        if "breakfast" in termset:
            attempts.append(("retail_breakfast_sandwich", dedupe_terms(["breakfast", "sandwich"])))
        for cue in ("beef", "cheese", "chicken", "club", "egg", "ham", "roast", "steak", "tuna", "turkey"):
            if cue in termset:
                attempts.append((f"retail_sandwich_{cue}", dedupe_terms(["sandwich", cue])))
    if "wrap" in termset:
        attempts.append(("retail_wrap", ("wrap",)))
        for cue in ("beef", "breakfast", "cheese", "chicken", "club", "egg", "ham", "steak", "tuna", "turkey"):
            if cue in termset:
                attempts.append((f"retail_wrap_{cue}", dedupe_terms(["wrap", cue])))
    if "sub" in termset:
        attempts.append(("retail_sub_sandwich", dedupe_terms(["sub", "sandwich"])))
        for cue in ("beef", "cheese", "chicken", "club", "ham", "roast", "steak", "tuna", "turkey"):
            if cue in termset:
                attempts.append((f"retail_sub_{cue}", dedupe_terms(["sub", cue])))
    if {"cheese", "steak"} <= termset:
        attempts.append(("retail_cheese_steak", dedupe_terms(["cheese", "steak"])))
        for cue in ("sandwich", "sub", "wrap"):
            if cue in termset:
                attempts.append((f"retail_cheese_steak_{cue}", dedupe_terms(["cheese", "steak", cue])))
    if {"hot", "dog"} <= termset and "sandwich" in termset:
        attempts.append(("retail_hot_dog", dedupe_terms(["hot", "dog"])))
    if "oatmeal" in termset:
        attempts.append(("retail_oatmeal", ("oatmeal",)))
        if "instant" in termset or "packet" in termset:
            attempts.append(("retail_instant_oatmeal", dedupe_terms(["instant", "oatmeal"])))
        if {"apple", "cinnamon"} <= termset:
            attempts.append(("retail_apple_cinnamon_oatmeal", dedupe_terms(["instant", "oatmeal", "apple", "cinnamon"])))
        if {"cinnamon", "roll"} <= termset:
            attempts.append(("retail_cinnamon_roll_oatmeal", dedupe_terms(["instant", "oatmeal", "cinnamon", "roll"])))
    if "farina" in termset:
        attempts.append(("retail_farina", ("farina",)))
        if "instant" in termset:
            attempts.append(("retail_instant_farina", dedupe_terms(["instant", "farina"])))
    if {"graham", "cracker"} <= termset or {"graham", "crackers"} <= termset:
        attempts.append(("retail_graham_crackers", dedupe_terms(["graham", "crackers"])))
        if "cinnamon" in termset:
            attempts.append(("retail_cinnamon_graham_crackers", dedupe_terms(["cinnamon", "graham", "crackers"])))
    if "wafer" in termset and "vanilla" in termset:
        attempts.append(("retail_vanilla_wafer", dedupe_terms(["vanilla", "wafer"])))
    if {"cinnamon", "roll"} <= termset or {"sweet", "roll"} <= termset:
        attempts.append(("retail_cinnamon_roll", dedupe_terms(["cinnamon", "roll"])))
    if "danish" in termset:
        attempts.append(("retail_danish", ("danish",)))
        if {"apple", "cinnamon"} <= termset:
            attempts.append(("retail_apple_cinnamon_danish", dedupe_terms(["apple", "cinnamon", "danish"])))
        elif "cinnamon" in termset:
            attempts.append(("retail_cinnamon_danish", dedupe_terms(["cinnamon", "danish"])))
    if "bagel" in termset:
        attempts.append(("retail_bagel", ("bagel",)))
        for cue in ("plain", "poppy", "sesame", "everything"):
            if cue in termset:
                attempts.append((f"retail_bagel_{cue}", dedupe_terms([cue, "bagel"])))
    if {"saltine", "cracker"} <= termset or {"saltine", "crackers"} <= termset:
        attempts.append(("retail_saltine_crackers", dedupe_terms(["saltine", "crackers"])))
        if "unsalted" in termset or "top" in termset or "tops" in termset:
            attempts.append(("retail_unsalted_tops_saltines", dedupe_terms(["unsalted", "tops", "saltine", "crackers"])))
    if {"melba", "toast"} <= termset:
        attempts.append(("retail_melba_toast", dedupe_terms(["melba", "toast"])))
    if "triscuit" in termset or "triscuits" in termset:
        attempts.append(("retail_triscuit_crackers", dedupe_terms(["triscuit", "crackers"])))
    if {"cheez", "it"} <= termset:
        attempts.append(("retail_cheez_it", dedupe_terms(["cheez", "it"])))
        attempts.append(("retail_cheez_it_crackers", dedupe_terms(["cheez", "it", "crackers"])))
    if {"town", "house"} <= termset:
        attempts.append(("retail_town_house_crackers", dedupe_terms(["town", "house", "crackers"])))
    if "wheatables" in termset:
        attempts.append(("retail_wheatables", ("wheatables",)))
    if "tortilla" in termset:
        attempts.append(("retail_tortilla", ("tortilla",)))
        if "flour" in termset:
            attempts.append(("retail_flour_tortilla", dedupe_terms(["flour", "tortilla"])))
        if "corn" in termset:
            attempts.append(("retail_corn_tortilla", dedupe_terms(["corn", "tortilla"])))
    if {"hamburger", "helper"} <= termset:
        attempts.append(("retail_hamburger_helper", dedupe_terms(["hamburger", "helper"])))
    if {"sushi", "roll"} <= termset or {"maki", "roll"} <= termset:
        attempts.append(("retail_sushi_roll", dedupe_terms(["sushi", "roll"])))
        if {"california"} <= termset:
            attempts.append(("retail_california_roll", dedupe_terms(["california", "roll"])))
    if profile.family == "nut_seed":
        if {"almond", "joy"} <= termset:
            attempts.append(("retail_almond_joy", dedupe_terms(["almond", "joy", "candy"])))
        if {"grape", "nut"} <= termset or {"grape", "nuts"} <= termset:
            attempts.append(("retail_grape_nuts", dedupe_terms(["grape", "nuts"])))
    if profile.family == "soup":
        if {"jalapeno", "pepper"} <= termset or {"jalapeno", "peppers"} <= termset:
            attempts.append(("retail_jalapeno_peppers", dedupe_terms(["jalapeno", "peppers"])))
        if {"green", "pepper"} <= termset and ("chili" in termset or "chile" in termset):
            attempts.append(("retail_green_chiles", dedupe_terms(["green", "chiles"])))
        for cue in ("ancho", "guajillo", "morita", "poblano"):
            if cue in termset and ("pepper" in termset or "chili" in termset or "chile" in termset):
                attempts.append((f"retail_{cue}_chiles", dedupe_terms([cue, "chiles"])))
        if {"chili", "con", "carne"} <= termset:
            attempts.append(("retail_chili_con_carne", dedupe_terms(["chili", "con", "carne"])))
        if {"soup", "chicken", "noodle"} <= termset:
            attempts.append(("retail_chicken_noodle_soup", dedupe_terms(["chicken", "noodle", "soup"])))
        if {"soup", "black", "bean"} <= termset:
            attempts.append(("retail_black_bean_soup", dedupe_terms(["black", "bean", "soup"])))
        if {"soup", "split", "pea"} <= termset:
            attempts.append(("retail_split_pea_soup", dedupe_terms(["split", "pea", "soup"])))
        if "soup" in termset and "bean" in termset and "ham" in termset:
            attempts.append(("retail_bean_ham_soup", dedupe_terms(["bean", "ham", "soup"])))
        if {"beef", "stew"} <= termset:
            attempts.append(("retail_beef_stew", dedupe_terms(["beef", "stew"])))
    if profile.family == "milk":
        if "buttermilk" in termset:
            attempts.append(("retail_buttermilk", ("buttermilk",)))
            if "pancake" in termset:
                attempts.append(("retail_buttermilk_pancake_mix", dedupe_terms(["buttermilk", "pancake", "mix"])))
            if "biscuit" in termset or "biscuits" in termset:
                attempts.append(("retail_buttermilk_biscuits", dedupe_terms(["buttermilk", "biscuits"])))
            if "waffle" in termset or "waffles" in termset:
                attempts.append(("retail_buttermilk_waffles", dedupe_terms(["buttermilk", "waffles"])))
            if "ranch" in termset:
                attempts.append(("retail_buttermilk_ranch", dedupe_terms(["buttermilk", "ranch"])))
        if "steamer" in termset:
            attempts.append(("retail_steamer", ("steamer",)))
    if profile.family == "cream":
        if {"cream", "substitute"} <= termset:
            attempts.append(("retail_cream_substitute", dedupe_terms(["cream", "substitute"])))
        if {"sour", "cream"} <= termset:
            attempts.append(("retail_sour_cream", dedupe_terms(["sour", "cream"])))
        if {"whipping", "cream"} <= termset:
            attempts.append(("retail_whipping_cream", dedupe_terms(["whipping", "cream"])))
        if {"whipped", "cream"} <= termset or {"whip", "cream"} <= termset:
            attempts.append(("retail_whipped_cream", dedupe_terms(["whipped", "cream"])))
        if {"coffee", "cooler"} <= termset:
            attempts.append(("retail_coffee_cooler", dedupe_terms(["coffee", "cooler"])))
        if {"cappuccino", "blast"} <= termset:
            attempts.append(("retail_cappuccino_blast", dedupe_terms(["cappuccino", "blast"])))
        if {"cream", "soup"} <= termset or ("soup" in termset and "cream" in termset):
            for cue in ("mushroom", "broccoli", "potato", "chicken", "shrimp", "onion", "celery", "asparagus"):
                if cue in termset:
                    attempts.append((f"retail_cream_of_{cue}_soup", dedupe_terms(["cream", "of", cue, "soup"])))
                    attempts.append((f"retail_{cue}_cream_soup", dedupe_terms(["cream", cue, "soup"])))
    for brand in sorted(FORMULA_BRAND_TERMS & termset):
        attempts.append((f"retail_{brand}", (brand,)))
        for cue in ("vanilla", "chocolate", "strawberry"):
            if cue in termset:
                attempts.append((f"retail_{brand}_{cue}", dedupe_terms([brand, cue])))
    if "yogurt" in termset and ("frozen" in termset or "frozen" in set(profile.attrs)):
        if not singular_shapes:
            attempts.append(("retail_frozen_yogurt", dedupe_terms(["frozen", "yogurt"])))
            attempts.append(("retail_froyo", ("froyo",)))
        for shape in ("bar", "cone", "sandwich"):
            if shape in termset:
                attempts.append((f"retail_frozen_yogurt_{shape}", dedupe_terms(["frozen", "yogurt", shape])))
                attempts.append((f"retail_froyo_{shape}", dedupe_terms(["froyo", shape])))
    if {"dessert", "frozen"} <= termset:
        if not singular_shapes:
            attempts.append(("retail_frozen_dessert", dedupe_terms(["frozen", "dessert"])))
        for shape in ("bar", "cone", "sandwich"):
            if shape in termset:
                attempts.append((f"retail_frozen_dessert_{shape}", dedupe_terms(["frozen", "dessert", shape])))
    if "taquito" in termset:
        attempts.append(("retail_taquito", ("taquito",)))
        for fill in ("beef", "cheese", "chicken"):
            if fill in termset:
                attempts.append((f"retail_taquito_{fill}", dedupe_terms(["taquito", fill])))
    if "tamale" in termset:
        attempts.append(("retail_tamale", ("tamale",)))
        for fill in ("beef", "cheese", "chicken", "pork"):
            if fill in termset:
                attempts.append((f"retail_tamale_{fill}", dedupe_terms(["tamale", fill])))
    if {"egg", "roll"} <= termset:
        attempts.append(("retail_egg_roll", dedupe_terms(["egg", "roll"])))
        for fill in ("chicken", "pork", "shrimp", "vegetable"):
            if fill in termset:
                attempts.append((f"retail_egg_roll_{fill}", dedupe_terms(["egg", "roll", fill])))
    if {"spring", "roll"} <= termset:
        attempts.append(("retail_spring_roll", dedupe_terms(["spring", "roll"])))
        for fill in ("chicken", "shrimp", "vegetable"):
            if fill in termset:
                attempts.append((f"retail_spring_roll_{fill}", dedupe_terms(["spring", "roll", fill])))
    if "empanada" in termset:
        attempts.append(("retail_empanada", ("empanada",)))
        for fill in ("beef", "chicken", "pork"):
            if fill in termset:
                attempts.append((f"retail_empanada_{fill}", dedupe_terms(["empanada", fill])))
    if "quiche" in termset:
        attempts.append(("retail_quiche", ("quiche",)))
        for fill in ("bacon", "cheese", "florentine", "spinach", "swiss"):
            if fill in termset:
                attempts.append((f"retail_quiche_{fill}", dedupe_terms(["quiche", fill])))
    if "potsticker" in termset:
        attempts.append(("retail_potsticker", ("potsticker",)))
        for fill in ("chicken", "pork", "shrimp", "vegetable"):
            if fill in termset:
                attempts.append((f"retail_potsticker_{fill}", dedupe_terms(["potsticker", fill])))
    if {"corn", "dog"} <= termset:
        attempts.append(("retail_corn_dog", dedupe_terms(["corn", "dog"])))
        for fill in ("beef", "chicken", "turkey"):
            if fill in termset:
                attempts.append((f"retail_corn_dog_{fill}", dedupe_terms(["corn", "dog", fill])))
        if "popcorn" in termset:
            attempts.append(("retail_popcorn_corn_dog", dedupe_terms(["popcorn", "corn", "dog"])))
    if "pizza" in termset:
        attempts.append(("retail_pizza", ("pizza",)))
        if {"original", "crust"} <= termset:
            attempts.append(("retail_pizza_original_crust", dedupe_terms(["pizza", "original", "crust"])))
        if {"hand", "tossed"} <= termset:
            attempts.append(("retail_pizza_hand_tossed", dedupe_terms(["pizza", "hand", "tossed"])))
        if {"thin", "crust"} <= termset:
            attempts.append(("retail_pizza_thin_crust", dedupe_terms(["pizza", "thin", "crust"])))
        if {"skinny", "crust"} <= termset:
            attempts.append(("retail_pizza_skinny_crust", dedupe_terms(["pizza", "skinny", "crust"])))
    if {"french", "fry"} <= termset or {"french", "fries"} <= termset:
        attempts.append(("retail_french_fries", dedupe_terms(["french", "fries"])))
        if {"crinkle", "cut"} <= termset:
            attempts.append(("retail_crinkle_cut_fries", dedupe_terms(["french", "fries", "crinkle", "cut"])))
        if {"straight", "cut"} <= termset:
            attempts.append(("retail_straight_cut_fries", dedupe_terms(["french", "fries", "straight", "cut"])))
        if "shoestring" in termset:
            attempts.append(("retail_shoestring_fries", dedupe_terms(["french", "fries", "shoestring"])))
        if "crisscut" in termset:
            attempts.append(("retail_crisscut_fries", dedupe_terms(["french", "fries", "crisscut"])))
        if "wedge" in termset:
            attempts.append(("retail_wedge_fries", dedupe_terms(["french", "fries", "wedge"])))
        if {"regular", "cut"} <= termset:
            attempts.append(("retail_regular_cut_fries", dedupe_terms(["french", "fries", "regular", "cut"])))
    if "frappuccino" in termset:
        attempts.append(("retail_frappuccino", ("frappuccino",)))
        if "creme" in termset:
            attempts.append(("retail_creme_frappuccino", dedupe_terms(["creme", "frappuccino"])))
        if "coffee" in termset:
            attempts.append(("retail_coffee_frappuccino", dedupe_terms(["coffee", "frappuccino"])))
        for flavor in ("caramel", "mocha", "vanilla", "mint", "white"):
            if flavor in termset:
                attempts.append((f"retail_{flavor}_frappuccino", dedupe_terms(["frappuccino", flavor])))
    if "latte" in termset:
        base = ["latte"]
        if "iced" in termset:
            base.insert(0, "iced")
        attempts.append(("retail_latte", dedupe_terms(base)))
        for cue in ("chai", "cinnamon", "coffee", "mocha", "tea", "vanilla"):
            if cue in termset:
                attempts.append((f"retail_latte_{cue}", dedupe_terms(base + [cue])))
    if "cappuccino" in termset:
        attempts.append(("retail_cappuccino", ("cappuccino",)))
        if "coffee" in termset:
            attempts.append(("retail_coffee_cappuccino", dedupe_terms(["coffee", "cappuccino"])))
    if {"hot", "cocoa"} <= termset:
        attempts.append(("retail_hot_cocoa", dedupe_terms(["hot", "cocoa"])))
        if {"white", "chocolate"} <= termset:
            attempts.append(("retail_white_hot_cocoa", dedupe_terms(["hot", "cocoa", "white", "chocolate"])))
    if {"cake", "ice", "cream"} <= termset:
        attempts.append(("retail_ice_cream_cake", dedupe_terms(["ice", "cream", "cake"])))
        if "blizzard" in termset:
            attempts.append(("retail_blizzard_cake", dedupe_terms(["blizzard", "cake"])))
    if {"cookie", "sandwich"} <= termset and "oreo" in termset:
        attempts.append(("retail_oreo_cookie_sandwich", dedupe_terms(["oreo", "cookie", "sandwich"])))
        attempts.append(("retail_oreo_cookie", dedupe_terms(["oreo", "cookie"])))
    if {"candy", "bar"} <= termset:
        brand_pairs = (
            ({"milky", "way"}, "retail_milky_way_bar", ["milky", "way", "bar"]),
            ({"kit", "kat"}, "retail_kit_kat_bar", ["kit", "kat", "bar"]),
            ({"snicker", "snickers"}, "retail_snickers_bar", ["snickers", "bar"]),
            ({"twix"}, "retail_twix_bar", ["twix", "bar"]),
            ({"butterfinger"}, "retail_butterfinger_bar", ["butterfinger", "bar"]),
            ({"reese"}, "retail_reese_bar", ["reese", "bar"]),
        )
        for required, label, terms in brand_pairs:
            if required <= termset or any(term in termset for term in required):
                attempts.append((label, dedupe_terms(terms)))
    if {"potato", "skin"} <= termset or {"potato", "skins"} <= termset:
        attempts.append(("retail_potato_skins", dedupe_terms(["potato", "skins"])))
        for fill in ("bacon", "cheddar", "cheese"):
            if fill in termset:
                attempts.append((f"retail_potato_skins_{fill}", dedupe_terms(["potato", "skins", fill])))
    if {"mozzarella", "stick"} <= termset or {"mozzarella", "sticks"} <= termset:
        attempts.append(("retail_mozzarella_sticks", dedupe_terms(["mozzarella", "sticks"])))
        if "breaded" in termset:
            attempts.append(("retail_breaded_mozzarella_sticks", dedupe_terms(["mozzarella", "sticks", "breaded"])))
    if {"macaroni", "cheese"} <= termset or {"mac", "cheese"} <= termset:
        attempts.append(("retail_mac_and_cheese", dedupe_terms(["mac", "cheese"])))
    if "lasagna" in termset:
        attempts.append(("retail_lasagna", ("lasagna",)))
        for protein in ("beef", "chicken", "sausage", "meat", "cheese"):
            if protein in termset:
                attempts.append((f"retail_lasagna_{protein}", dedupe_terms(["lasagna", protein])))
    if {"pot", "pie"} <= termset:
        attempts.append(("retail_pot_pie", ("pot", "pie")))
        for protein in ("beef", "chicken", "turkey"):
            if protein in termset:
                attempts.append((f"retail_pot_pie_{protein}", dedupe_terms(["pot", "pie", protein])))
    if "alfredo" in termset:
        attempts.append(("retail_alfredo_pasta", dedupe_terms(["alfredo", "pasta"])))
        if "chicken" in termset:
            attempts.append(("retail_chicken_alfredo", dedupe_terms(["chicken", "alfredo"])))
        if "fettuccini" in termset or "fettuccine" in termset:
            attempts.append(("retail_fettuccine_alfredo", dedupe_terms(["fettuccini", "alfredo"])))
    if "stroganoff" in termset:
        attempts.append(("retail_stroganoff", ("stroganoff",)))
        if "beef" in termset:
            attempts.append(("retail_beef_stroganoff", dedupe_terms(["beef", "stroganoff"])))
    if {"salisbury", "steak"} <= termset:
        attempts.append(("retail_salisbury_steak", dedupe_terms(["salisbury", "steak"])))
    if "meatloaf" in termset:
        attempts.append(("retail_meatloaf", ("meatloaf",)))
    if "burrito" in termset:
        attempts.append(("retail_burrito", ("burrito",)))
        for fill in ("bean", "beef", "cheese", "chicken"):
            if fill in termset:
                attempts.append((f"retail_burrito_{fill}", dedupe_terms(["burrito", fill])))
    if "quesadilla" in termset:
        attempts.append(("retail_quesadilla", ("quesadilla",)))
    return attempts


def query_attempts_for(profile: matcher.EshaProfile) -> list[tuple[str, tuple[str, ...]]]:
    primary = dedupe_terms(list(query_terms_for(profile) or profile.fts_terms or tuple(term for term in profile.hard_terms if len(term) >= 3)))
    attempts: list[tuple[str, tuple[str, ...]]] = []
    planned = planned_query_attempt_for(profile)
    if planned is not None:
        attempts.append(planned)
    attempts.append(("strict", primary))
    retail_primary = retail_cleanup_primary_terms(profile, primary)
    if retail_primary:
        attempts.append(("retail_cleanup", retail_primary))
    default_state = DEFAULT_RETAIL_STATE_TERMS_BY_FAMILY.get(profile.family, set())
    if default_state:
        attempts.append(("drop_default_retail_state", dedupe_terms([term for term in primary if term not in default_state])))
    optional = OPTIONAL_QUERY_TERMS_BY_FAMILY.get(profile.family, set())
    if optional:
        attempts.append(("drop_optional_retail_modifiers", dedupe_terms([term for term in primary if term not in optional])))
    attempts.extend(retail_claim_attempts_for(profile, retail_primary or primary))
    if profile.family == "grain" and {"bow", "tie"} <= set(primary):
        attempts.append(("retail_shape_name", ("pasta", "bow", "tie")))
        attempts.append(("shape_only", ("bow", "tie")))
    deduped_attempts = []
    seen = set()
    for label, terms in attempts:
        if not terms or terms in seen:
            continue
        seen.add(terms)
        deduped_attempts.append((label, terms))
    return deduped_attempts


def has_prepared_food_context(source_terms: set[str] | None = None, description: str = "") -> bool:
    terms = set(source_terms or ())
    terms.update(matcher.tokens_for(description))
    if terms & PREPARED_FOOD_CUES:
        return True
    combo_cues = (
        {"pot", "pie"},
        {"mac", "cheese"},
        {"macaroni", "cheese"},
        {"lo", "mein"},
        {"salisbury", "steak"},
        {"egg", "roll"},
        {"spring", "roll"},
        {"corn", "dog"},
        {"potato", "skin"},
        {"potato", "skins"},
        {"mozzarella", "stick"},
        {"mozzarella", "sticks"},
    )
    return any(cue <= terms for cue in combo_cues)


def has_candy_context(source_terms: set[str] | None = None, description: str = "") -> bool:
    terms = context_terms(source_terms, description)
    return bool(terms & CANDY_CONTEXT_TERMS)


def has_ice_cream_context(source_terms: set[str] | None = None, description: str = "") -> bool:
    terms = context_terms(source_terms, description)
    return {"ice", "cream"} <= terms or "gelato" in terms


def has_frozen_yogurt_context(source_terms: set[str] | None = None, description: str = "") -> bool:
    terms = context_terms(source_terms, description)
    return "yogurt" in terms and ("frozen" in terms or "froyo" in terms or bool(terms & FROZEN_DESSERT_SHAPE_TERMS))


def has_frozen_dessert_context(source_terms: set[str] | None = None, description: str = "") -> bool:
    terms = context_terms(source_terms, description)
    return (
        has_ice_cream_context(terms, description)
        or has_frozen_yogurt_context(terms, description)
        or {"dessert", "frozen"} <= terms
        or "sorbet" in terms
        or "sherbet" in terms
    )


def context_terms(source_terms: set[str] | None = None, description: str = "") -> set[str]:
    terms = set(source_terms or ())
    terms.update(matcher.tokens_for(description))
    if "mayonnaise" in terms:
        terms.add("mayo")
    if "mayo" in terms:
        terms.add("mayonnaise")
    return terms


def hint_in_category(hint: str, category_norm: str) -> bool:
    return matcher.normalize_text(hint) in category_norm


def category_signal(
    category: str,
    family: str,
    source_terms: set[str] | None = None,
    description: str = "",
) -> str:
    cat = matcher.normalize_text(category)
    terms = context_terms(source_terms, description)
    if has_candy_context(terms, description):
        if any(hint_in_category(hint, cat) for hint in CANDY_CATEGORY_HINTS):
            return "in_scope_category"
        return "category_noise"
    if has_ice_cream_context(terms, description):
        if any(hint_in_category(hint, cat) for hint in FROZEN_DESSERT_CATEGORY_HINTS):
            return "in_scope_category"
        return "category_noise"
    if has_frozen_yogurt_context(terms, description):
        if any(hint_in_category(hint, cat) for hint in FROZEN_DESSERT_CATEGORY_HINTS):
            return "in_scope_category"
        return "category_noise"
    if has_frozen_dessert_context(terms, description):
        if any(hint_in_category(hint, cat) for hint in FROZEN_DESSERT_CATEGORY_HINTS):
            return "in_scope_category"
    if {"sorbet", "sherbet"} & terms:
        hints = CONTEXT_CATEGORY_HINTS["sorbet"]
        if any(hint_in_category(hint, cat) for hint in hints):
            return "in_scope_category"
        return "category_noise"
    for term, hints in CONTEXT_CATEGORY_HINTS.items():
        if term in terms and any(hint_in_category(hint, cat) for hint in hints):
            return "in_scope_category"
    if family == "butter":
        if any(bad in cat for bad in ("nut", "seed", "peanut", "snack", "candy", "chocolate", "cookie", "ice cream", "pickle")):
            return "category_noise"
        if any(good in cat for good in ("butter and spread", "butter butter", "margarine butter", "butter substitute", "dairy")):
            return "in_scope_category"
        return "category_noise"
    if family == "prepared_food":
        hints = CATEGORY_HINTS.get(family, ())
        if any(hint_in_category(hint, cat) for hint in hints):
            return "in_scope_category"
        if "frozen vegetable" in cat and has_prepared_food_context(source_terms, description):
            return "in_scope_category"
        return "category_noise"
    if has_prepared_food_context(source_terms, description):
        prepared_hints = CATEGORY_HINTS.get("prepared_food", ())
        if any(hint_in_category(hint, cat) for hint in prepared_hints):
            return "in_scope_category"
        if any(hint_in_category(hint, cat) for hint in ("pasta dinner", "ready made combination meal", "entrees sides small meals")):
            return "in_scope_category"
    hints = CATEGORY_HINTS.get(family, ())
    if not hints:
        return "review"
    if any(hint_in_category(hint, cat) for hint in hints):
        return "in_scope_category"
    return "category_noise"


def product_noise(description: str, category: str, family: str, source_terms: set[str], ingredients: str = "") -> list[str]:
    tokens = set(matcher.tokens_for(description)) | set(matcher.tokens_for(category)) | set(matcher.tokens_for(ingredients))
    description_tokens = set(matcher.tokens_for(description))
    terms = context_terms(source_terms, description)
    ignore_terms = set()
    extra_terms = set()
    for term, values in CONTEXT_IGNORE_NOISE.items():
        if term in terms:
            ignore_terms |= values
    for term, values in CONTEXT_EXTRA_NOISE.items():
        if term in terms:
            extra_terms |= values
    if has_candy_context(terms, description):
        ignore_terms |= {"chocolate", "cocoa", "cream", "flavor", "flavored", "ice", "milk", "protein", "soy", "vanilla", "yogurt"}
    if has_ice_cream_context(terms, description):
        ignore_terms |= {"milk", "yogurt", "protein"}
    if has_frozen_yogurt_context(terms, description):
        ignore_terms |= {"cream", "ice"}
    if {"dessert", "frozen"} <= terms:
        ignore_terms |= {"ice", "cream", "milk", "yogurt"}
    if has_prepared_food_context(terms, description):
        ignore_terms |= {"chip", "cracker", "dip", "meal", "pasta", "pizza", "sandwich", "sauce", "snack", "soup"}
    if "peanut" not in terms:
        extra_terms -= CONTEXT_EXTRA_NOISE["peanut"]
    noise = []
    if {"mayo", "mayonnaise"} & terms and not ({"mayo", "mayonnaise"} & description_tokens):
        noise.append("missing_mayo")
    if has_frozen_yogurt_context(terms, description) and not ({"froyo", "yogurt", "yoghurt"} & description_tokens):
        noise.append("missing_yogurt")
    if family == "nut_butter" and "peanut" in terms and "peanut" not in description_tokens:
        noise.append("missing_peanut")
    for term in tuple(NOISE_TERMS.get(family, ())) + tuple(sorted(extra_terms)):
        if term in ignore_terms:
            continue
        if term in tokens and term not in source_terms:
            noise.append(term)
    return sorted(noise)


def table_cell(value: str, max_len: int = 320) -> str:
    value = re.sub(r"\s+", " ", str(value or "")).strip().replace("|", "/")
    if len(value) <= max_len:
        return value
    return value[: max_len - 3].rstrip() + "..."


def load_profiles() -> list[matcher.EshaProfile]:
    profiles = []
    with ESHA_CSV.open(newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            profiles.append(matcher.profile_for(row))
    return profiles


def select_profiles(
    profiles: list[matcher.EshaProfile],
    codes: set[str],
    contains: str,
    family: str,
    limit: int | None,
) -> list[matcher.EshaProfile]:
    selected = []
    needle = matcher.normalize_text(contains) if contains else ""
    for profile in profiles:
        if codes and profile.code not in codes:
            continue
        if family and profile.family != family:
            continue
        if needle and needle not in profile.norm:
            continue
        selected.append(profile)
        if limit is not None and len(selected) >= limit:
            break
    return selected


def load_codes_file(path: Path | None) -> set[str]:
    if path is None or not path.exists():
        return set()
    codes: set[str] = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        code = raw.strip()
        if code:
            codes.add(code)
    return codes


def category_sql_filter(alias: str, category_terms: tuple[str, ...]) -> tuple[str, list[object]]:
    if not category_terms:
        return "", []
    exact_terms = [term[1:].strip().lower() for term in category_terms if term.startswith("=") and term[1:].strip()]
    like_terms = [term.lower() for term in category_terms if term and not term.startswith("=")]
    clauses: list[str] = []
    params: list[object] = []
    if exact_terms:
        placeholders = ", ".join(["?"] * len(exact_terms))
        clauses.append(f"lower(COALESCE({alias}.branded_food_category, '')) IN ({placeholders})")
        params.extend(exact_terms)
    if like_terms:
        clauses.append(
            "(" + " OR ".join([f"lower(COALESCE({alias}.branded_food_category, '')) LIKE ?"] * len(like_terms)) + ")"
        )
        params.extend(f"%{term}%" for term in like_terms)
    if not clauses:
        return "", []
    clause = " AND (" + " OR ".join(clauses) + ")"
    return clause, params


def query_categories(
    con: sqlite3.Connection,
    query: str,
    max_categories: int,
    category_terms: tuple[str, ...] = (),
) -> list[tuple[str, int]]:
    category_clause, params = category_sql_filter("p", category_terms)
    sql = """
        SELECT COALESCE(p.branded_food_category, '') AS category, COUNT(*) AS n
        FROM products_fts
        JOIN products p ON p.rowid = products_fts.rowid
        WHERE products_fts MATCH ?
        """ + category_clause + """
        GROUP BY category
        ORDER BY n DESC, category
        LIMIT ?
    """
    bound: list[object] = [query, *params, max_categories]
    return [(str(row[0]), int(row[1])) for row in con.execute(sql, bound)]


def query_total(con: sqlite3.Connection, query: str, category_terms: tuple[str, ...] = ()) -> int:
    category_clause, params = category_sql_filter("p", category_terms)
    sql = """
        SELECT COUNT(*)
        FROM products_fts
        JOIN products p ON p.rowid = products_fts.rowid
        WHERE products_fts MATCH ?
        """ + category_clause
    bound: list[object] = [query, *params]
    return int(con.execute(sql, bound).fetchone()[0])


def product_count(con: sqlite3.Connection) -> int:
    return int(con.execute("SELECT COUNT(*) FROM products").fetchone()[0])


def term_total(con: sqlite3.Connection, term: str, cache: dict[str, int]) -> int:
    if term not in cache:
        query = fts_query((term,))
        cache[term] = query_total(con, query) if query else 0
    return cache[term]


def term_stats_for(
    profile: matcher.EshaProfile,
    con: sqlite3.Connection,
    total_products: int,
    term_cache: dict[str, int],
) -> list[dict[str, object]]:
    primary = dedupe_terms(list(query_terms_for(profile) or profile.fts_terms or profile.hard_terms))
    drops = set(profile.attrs) | STATE_OR_PROCESS_TERMS
    drops |= DEFAULT_RETAIL_STATE_TERMS_BY_FAMILY.get(profile.family, set())
    drops |= OPTIONAL_QUERY_TERMS_BY_FAMILY.get(profile.family, set())
    identity = FAMILY_IDENTITY_TERMS.get(profile.family, set())
    stats = []
    for term in primary:
        total = term_total(con, term, term_cache)
        idf = math.log((total_products + 1) / (total + 1))
        if term in drops:
            kind = "state_process"
        elif total == 0:
            kind = "dead"
        elif term in identity:
            kind = "family_identity"
        elif total / max(total_products, 1) > 0.08:
            kind = "broad"
        else:
            kind = "signal"
        stats.append({"term": term, "total": total, "idf": idf, "kind": kind})
    return stats


def weighted_query_attempts(term_stats: list[dict[str, object]]) -> list[tuple[str, tuple[str, ...]]]:
    keepable = [row for row in term_stats if row["kind"] not in {"dead", "state_process"} and int(row["total"]) > 0]
    identities = [row for row in keepable if row["kind"] == "family_identity"]
    signals = [row for row in keepable if row["kind"] == "signal"]
    broad = [row for row in keepable if row["kind"] == "broad"]
    by_weight = sorted(signals, key=lambda row: float(row["idf"]), reverse=True)
    attempts: list[tuple[str, tuple[str, ...]]] = []
    if keepable and len(keepable) < len(term_stats):
        attempts.append(("tfidf_drop_dead_state_terms", dedupe_terms([str(row["term"]) for row in keepable])))
    if identities and by_weight:
        terms = [str(identities[0]["term"]), *[str(row["term"]) for row in by_weight[:3]]]
        attempts.append(("tfidf_identity_plus_signal", dedupe_terms(terms)))
    if len(by_weight) >= 2:
        attempts.append(("tfidf_top_signal_terms", dedupe_terms([str(row["term"]) for row in by_weight[:3]])))
    if identities and broad:
        terms = [str(identities[0]["term"]), *[str(row["term"]) for row in broad[:2]]]
        attempts.append(("tfidf_identity_plus_broad", dedupe_terms(terms)))
    deduped_attempts = []
    seen = set()
    for label, terms in attempts:
        if not terms or terms in seen:
            continue
        seen.add(terms)
        deduped_attempts.append((label, terms))
    return deduped_attempts


def diagnostic_rescue_attempts_for(profile: matcher.EshaProfile) -> list[tuple[str, tuple[str, ...]]]:
    primary = list(dedupe_terms(list(query_terms_for(profile) or profile.fts_terms or profile.hard_terms)))
    drops = set(profile.attrs) | STATE_OR_PROCESS_TERMS
    drops |= DEFAULT_RETAIL_STATE_TERMS_BY_FAMILY.get(profile.family, set())
    drops |= OPTIONAL_QUERY_TERMS_BY_FAMILY.get(profile.family, set())
    attempts: list[tuple[str, tuple[str, ...]]] = []
    core = dedupe_terms([term for term in primary if term not in drops])
    if core and tuple(primary) != core:
        attempts.append(("drop_state_process_terms", core))
    source_core = dedupe_terms([term for term in profile.hard_terms if term not in drops and len(term) >= 3])
    if source_core and source_core != core:
        attempts.append(("source_core_terms", source_core))
    if "brickle" in core and "bit" in core:
        attempts.append(("brickle_bits_identity", ("brickle", "bit")))
    protected_terms: set[str] = set()
    if profile.family == "cheese":
        protected_terms.update(term for term in core if term not in {"cheese"})
    if profile.family == "milk":
        protected_terms.update(term for term in core if term in {"condensed", "eggnog", "evaporated", "malted"})
    protected_terms.update(PROTECTED_CORE_TERMS_BY_CODE.get(profile.code, set()))
    if len(core) > 1:
        for term in reversed(core):
            if term in protected_terms:
                continue
            reduced = dedupe_terms([candidate for candidate in core if candidate != term])
            if len(reduced) >= 1:
                attempts.append((f"drop_one_core_term:{term}", reduced))
    if profile.family == "grain" and any(term in core for term in ("pasta", "macaroni", "noodle")):
        attempts.append(("grain_pasta_identity", ("pasta",)))
        if "bow" in core or "tie" in core:
            attempts.append(("grain_shape_identity", tuple(term for term in ("pasta", "bow", "tie") if term in core)))
    if profile.family == "legume":
        beans = [term for term in ("black", "pinto", "kidney", "lima", "navy", "garbanzo", "chickpea") if term in core]
        if beans:
            attempts.append(("legume_variety_identity", dedupe_terms(["bean", *beans])))
    deduped_attempts = []
    seen = set()
    for label, terms in attempts:
        terms = dedupe_terms(list(terms))
        if not terms or terms in seen:
            continue
        seen.add(terms)
        deduped_attempts.append((label, terms))
    return deduped_attempts


def format_term_stats(term_stats: list[dict[str, object]]) -> str:
    return " | ".join(
        f"{row['term']}:{row['kind']}:{row['total']}:{float(row['idf']):.2f}" for row in term_stats
    )


def query_products(
    con: sqlite3.Connection,
    query: str,
    max_products: int,
    category_terms: tuple[str, ...] = (),
) -> list[dict[str, str]]:
    category_clause, category_params = category_sql_filter("p", category_terms)
    params: list[object] = [query, *category_params]
    params.append(max_products)
    sql = """
        SELECT
            p.gtin_upc,
            p.fdc_id,
            p.description,
            COALESCE(p.brand_owner, ''),
            COALESCE(p.brand_name, ''),
            COALESCE(p.branded_food_category, ''),
            COALESCE(NULLIF(p.ingredients_clean, ''), NULLIF(p.ingredients, ''), '') AS ingredients,
            bm25(products_fts) AS rank
        FROM products_fts
        JOIN products p ON p.rowid = products_fts.rowid
        WHERE products_fts MATCH ?
        """ + category_clause + """
        ORDER BY rank, p.gtin_upc
        LIMIT ?
    """
    rows = []
    for row in con.execute(sql, params):
        rows.append(
            {
                "gtin_upc": str(row[0] or ""),
                "fdc_id": str(row[1] or ""),
                "description": str(row[2] or ""),
                "brand_owner": str(row[3] or ""),
                "brand_name": str(row[4] or ""),
                "category": str(row[5] or ""),
                "ingredients": str(row[6] or ""),
                "rank": f"{float(row[7]):.4f}",
            }
        )
    return rows


def product_row_for_contract(product: dict[str, str]) -> matcher.ProductRow:
    return matcher.ProductRow(
        gtin_upc=product.get("gtin_upc", ""),
        fdc_id=product.get("fdc_id", ""),
        description=product.get("description", ""),
        brand_owner=product.get("brand_owner", ""),
        brand_name=product.get("brand_name", ""),
        category=product.get("category", ""),
        serving_size="",
        serving_size_unit="",
        calories="",
        protein_g="",
        fat_g="",
        carbs_g="",
        sugar_g="",
        sodium_mg="",
    )


def semantic_filter_failures(
    profile: matcher.EshaProfile,
    product: dict[str, str],
    semantic_filters: tuple[str, ...] = (),
) -> list[str]:
    if not semantic_filters:
        return []
    description = product.get("description", "")
    category = product.get("category", "")
    ingredients = product.get("ingredients", "")
    category_norm = matcher.normalize_text(category)
    product_norm = matcher.normalize_text(" ".join(part for part in (description, category, ingredients) if part))
    tokens = product_terms_for_destination(product)
    detail_tokens = set(matcher.tokens_for(description)) | set(matcher.tokens_for(ingredients))
    commodity_terms = {
        term
        for term in profile.hard_terms
        if term not in STATE_OR_PROCESS_TERMS and term not in PEEL_PROXY_TERMS
    }
    failures: list[str] = []
    for term in semantic_filters:
        if term == "single_commodity":
            if detail_tokens & SIMPLE_PRODUCE_BLOCK_TERMS:
                failures.append(term)
                continue
            other_commodities = (matcher.FRUITS | matcher.VEGETABLES) - commodity_terms
            if detail_tokens & other_commodities:
                failures.append(term)
            continue
        if term == "produce_proxy_peel":
            if tokens & PRODUCE_PROXY_BLOCK_TERMS:
                failures.append(term)
                continue
            explicit_peel = bool(tokens & PEEL_PROXY_TERMS)
            plain_produce = (
                commodity_terms <= tokens
                and (
                    "produce" in category_norm
                    or "pre packaged" in category_norm
                    or "pre-packaged" in category.lower()
                )
            )
            if not explicit_peel and not plain_produce:
                failures.append(term)
            continue
        if term in INGREDIENT_ONLY_TERMS:
            ingredient_tokens = set(matcher.tokens_for(ingredients))
            description_tokens = set(matcher.tokens_for(description))
            if term not in ingredient_tokens and term not in description_tokens:
                failures.append(term)
            continue
        if term == "fresh":
            if any(noisy in tokens for noisy in {"canned", "dried", "freeze", "frozen", "pickled", "smoked"}):
                failures.append(term)
                continue
            if profile.family in {"fruit", "vegetable", "spice"}:
                if "produce" not in category_norm and "pre packaged" not in category_norm and "pre-packaged" not in category.lower():
                    failures.append(term)
            elif term not in tokens:
                failures.append(term)
            continue
        if term == "raw":
            if any(noisy in tokens for noisy in {"baked", "boiled", "canned", "cooked", "dried", "freeze", "frozen", "heated", "pickled", "roasted", "smoked", "toasted"}):
                failures.append(term)
                continue
            if profile.family in {"fruit", "vegetable"}:
                if "produce" not in category_norm and "pre packaged" not in category_norm and "pre-packaged" not in category.lower():
                    failures.append(term)
            elif term not in tokens:
                failures.append(term)
            continue
        if term in {"canned", "dried", "frozen", "pickled", "salted", "smoked", "unsalted"}:
            if not matcher.product_has_term(product_norm, tokens, term):
                failures.append(term)
    return failures


def contract_noise_terms(reason: str) -> list[str]:
    reason = reason.strip().lower()
    if "excluded term(s): " in reason:
        return [term for term in reason.split("excluded term(s): ", 1)[1].split("|") if term]
    if "excluded ingredient term(s): " in reason:
        return [term for term in reason.split("excluded ingredient term(s): ", 1)[1].split("|") if term]
    if "excluded ingredient phrase(s): " in reason:
        return ["ingredient_phrase"]
    if "missing required term(s): " in reason:
        return [f"missing_{term}" for term in reason.split("missing required term(s): ", 1)[1].split("|") if term]
    if "excluded phrase(s): " in reason:
        return [f"phrase_{term}" for term in reason.split("excluded phrase(s): ", 1)[1].split("|") if term]
    if "missing required phrase(s): " in reason:
        return [f"missing_phrase_{term}" for term in reason.split("missing required phrase(s): ", 1)[1].split("|") if term]
    if "category mismatch" in reason:
        return ["category_mismatch"]
    return [slugify(reason, max_len=60)]


def classify_product(
    profile: matcher.EshaProfile,
    product: dict[str, str],
    semantic_filters: tuple[str, ...] = (),
    allow_generated_contracts: bool = True,
) -> tuple[str, list[str]]:
    facts = esha_contracts.ProductFacts.from_components(
        product.get("description", ""),
        product.get("category", ""),
        product.get("ingredients", ""),
    )
    contract_source = esha_contracts.contract_source_module(profile.code)
    use_contract = allow_generated_contracts or "reviewed_nebius_generated" not in contract_source
    contract_decision = esha_contracts.evaluate_facts(profile.code, facts) if use_contract else None
    if contract_decision:
        if contract_decision.status == "accept":
            signal = "contract_accept"
            noise: list[str] = []
        else:
            return "contract_reject", contract_noise_terms(contract_decision.reason)
    else:
        source_terms = set(profile.tokens)
        signal = category_signal(product["category"], profile.family, source_terms, product["description"])
        noise = product_noise(product["description"], product["category"], profile.family, source_terms, product.get("ingredients", ""))
        # Soften: a single noise term is too brittle. Only flip to review_noise
        # when there are ≥2 noise signals OR the in-scope category itself is wrong.
        if len(noise) >= 2 or (noise and signal != "in_scope_category"):
            signal = "review_noise"
    semantic_failures = semantic_filter_failures(profile, product, semantic_filters)
    if semantic_failures:
        noise = sorted(set(noise + [f"semantic_{term}" for term in semantic_failures]))
        if signal in {"contract_accept", "in_scope_category"}:
            signal = "semantic_filter_mismatch"
    return signal, noise


def clean_product_count(
    profile: matcher.EshaProfile,
    products: list[dict[str, str]],
    semantic_filters: tuple[str, ...] = (),
    allow_generated_contracts: bool = True,
) -> int:
    count = 0
    for product in products:
        signal, noise = classify_product(profile, product, semantic_filters, allow_generated_contracts=allow_generated_contracts)
        if signal in {"in_scope_category", "contract_accept"} and not noise:
            count += 1
    return count


def draft_excludes(
    profile: matcher.EshaProfile,
    products: list[dict[str, str]],
    semantic_filters: tuple[str, ...] = (),
    allow_generated_contracts: bool = True,
) -> list[str]:
    counter: Counter[str] = Counter()
    for product in products:
        _, noise = classify_product(profile, product, semantic_filters, allow_generated_contracts=allow_generated_contracts)
        for term in noise:
            counter[term] += 1
    return [term for term, _ in counter.most_common(20)]


def write_pack(
    out_path: Path,
    profile: matcher.EshaProfile,
    query: str,
    query_attempts: list[dict[str, str]],
    total_matches: int,
    categories: list[tuple[str, int]],
    products: list[dict[str, str]],
    query_term_stats: str = "",
    destination_index: DestinationIndex | None = None,
    semantic_filters: tuple[str, ...] = (),
    category_terms: tuple[str, ...] = (),
    rewrite_plan: dict[str, str] | None = None,
) -> None:
    source_terms = set(profile.tokens)
    excludes = draft_excludes(profile, products, semantic_filters)
    selected_attempt = ""
    for attempt in reversed(query_attempts):
        if attempt["query"] == query:
            selected_attempt = attempt["label"]
            break
    category_noise_count = sum(
        count
        for category, count in categories
        if category_signal(category, profile.family, source_terms) == "category_noise"
    )
    product_noise_count = sum(1 for product in products if classify_product(profile, product, semantic_filters)[1])
    lines = [
        f"# ESHA {profile.code}: {profile.description}",
        "",
        "## Product Query Results",
        "",
        f"- family: {profile.family}",
        f"- product_query: `{query or '[no query generated]'}`",
        f"- selected_query_attempt: {selected_attempt}",
        f"- total_product_matches: {total_matches}",
        f"- product_rows_in_this_file: {len(products)}",
        f"- category_rows_in_this_file: {len(categories)}",
        f"- category_noise_matches_in_top_categories: {category_noise_count}",
        f"- noisy_product_rows_in_this_file: {product_noise_count}",
        f"- esha_required_terms_from_description: {' | '.join(profile.hard_terms)}",
        f"- esha_attrs_from_description: {' | '.join(profile.attrs)}",
        f"- likely_category_hints: {' | '.join(CATEGORY_HINTS.get(profile.family, ())) }",
        f"- rewrite_plan_status: {(rewrite_plan or {}).get('exactness_status', '')}",
        f"- rewrite_category_terms: {' | '.join(category_terms)}",
        f"- semantic_filter_terms: {' | '.join(semantic_filters)}",
        f"- noisy_terms_seen_in_returned_products: {' | '.join(excludes)}",
        f"- weighted_query_term_stats: {query_term_stats}",
        "",
        "## Query Attempts",
        "",
        "| attempt | query | total_matches | error |",
        "| --- | --- | ---: | --- |",
    ]
    for attempt in query_attempts:
        lines.append(
            f"| {attempt['label']} | `{attempt['query'] or '[no query generated]'}` | {attempt['total_matches']} | {attempt['error']} |"
        )

    lines.extend(
        [
            "",
        "## Categories Returned By Query",
        "",
        "| count | category | signal |",
        "| ---: | --- | --- |",
        ]
    )
    for category, count in categories:
        lines.append(f"| {count} | {category} | {category_signal(category, profile.family, source_terms)} |")

    lines.extend(
        [
            "",
            "## Candidate Clean Products",
            "",
            "| rank | gtin_upc | fdc_id | description | category | ingredients | signal | noise_terms |",
            "| ---: | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    product_rows: list[tuple[dict[str, str], str, list[str]]] = []
    for product in products:
        signal, noise = classify_product(profile, product, semantic_filters)
        product_rows.append((product, signal, noise))
    for product, signal, noise in product_rows:
        if signal not in {"in_scope_category", "contract_accept"} or noise:
            continue
        lines.append(
            f"| {product['rank']} | {product['gtin_upc']} | {product['fdc_id']} | "
            f"{table_cell(product['description'])} | {table_cell(product['category'])} | "
            f"{table_cell(product.get('ingredients', ''))} | {signal} | {'/'.join(noise)} |"
        )
    lines.extend(
        [
            "",
            "## Rows To Clean Up",
            "",
            "| rank | gtin_upc | fdc_id | description | category | ingredients | signal | noise_terms |",
            "| ---: | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for product, signal, noise in product_rows:
        if signal in {"in_scope_category", "contract_accept"} and not noise:
            continue
        lines.append(
            f"| {product['rank']} | {product['gtin_upc']} | {product['fdc_id']} | "
            f"{table_cell(product['description'])} | {table_cell(product['category'])} | "
            f"{table_cell(product.get('ingredients', ''))} | {signal} | {'/'.join(noise)} |"
        )

    lines.extend(
        [
            "",
            "## Cross Reference Conflicts",
            "",
            "Rows below came back from this card's query but also fit another ESHA card. Use this as routing evidence; do not auto-promote from this table.",
            "",
            "| product | category | source_signal | source_noise | likely_destinations |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    if destination_index is not None:
        conflict_count = 0
        for product, signal, noise in product_rows:
            if signal in {"in_scope_category", "contract_accept"} and not noise:
                continue
            destinations = destination_candidates_for_product(product, profile, destination_index, set(noise))
            if not destinations:
                continue
            conflict_count += 1
            destination_text = " ; ".join(
                f"{dest.code} {dest.description} [{reason}: {'/'.join(terms)}]"
                for dest, terms, reason in destinations
            )
            lines.append(
                f"| {table_cell(product['description'])} | {table_cell(product['category'])} | "
                f"{signal} | {'/'.join(noise)} | {table_cell(destination_text)} |"
            )
            if conflict_count >= 30:
                break

    lines.extend(
        [
            "",
            "## Audit Notes To Fill In",
            "",
            "- accept_patterns:",
            "- reject_patterns:",
            "- required_terms_final:",
            "- allowed_categories_final:",
            "- exclude_terms_final:",
            "- contract_decision:",
            "",
        ]
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")


def build_pack(
    con: sqlite3.Connection,
    profile: matcher.EshaProfile,
    out_root: Path,
    max_products: int,
    max_categories: int,
    query_cache: dict[tuple[str, tuple[str, ...]], tuple[int, list[tuple[str, int]], list[dict[str, str]], str]],
    total_products: int,
    term_cache: dict[str, int],
    destination_index: DestinationIndex | None = None,
) -> dict[str, str]:
    categories: list[tuple[str, int]] = []
    products: list[dict[str, str]] = []
    total_matches = 0
    error = ""
    query = ""
    attempted_queries: list[dict[str, str]] = []
    query_term_stats = ""
    fallback_result: tuple[str, int, list[tuple[str, int]], list[dict[str, str]], str] | None = None
    rewrite_plan = rewrite_plan_for(profile)
    product_category_terms = category_terms_for_profile(profile)
    semantic_filters = semantic_filters_for_profile(profile)
    strict_identity_lock = profile.family == "cheese" and any(term not in {"cheese"} for term in profile.hard_terms)
    for label, terms in query_attempts_for(profile):
        query = fts_query(terms)
        cache_key = (query, product_category_terms)
        if cache_key in query_cache:
            total_matches, categories, products, error = query_cache[cache_key]
        else:
            try:
                total_matches = query_total(con, query, product_category_terms)
                categories = query_categories(con, query, max_categories, product_category_terms)
                products = query_products(con, query, max_products, product_category_terms)
            except sqlite3.Error as exc:
                error = str(exc)
            query_cache[cache_key] = (total_matches, categories, products, error)
        clean_count = clean_product_count(profile, products, semantic_filters) if total_matches > 0 and not error else 0
        attempted_queries.append(
            {
                "label": label,
                "query": query,
                "total_matches": str(total_matches),
                "error": error,
            }
        )
        if error:
            break
        if label == "strict" and strict_identity_lock and total_matches > 0:
            break
        if total_matches > 0 and clean_count > 0:
            break
        if total_matches > 0 and fallback_result is None:
            fallback_result = (query, total_matches, categories, products, error)
            continue
    initial_fallback_result = fallback_result
    current_clean_count = clean_product_count(profile, products, semantic_filters) if total_matches > 0 and not error else 0
    locked_strict_result = strict_identity_lock and any(
        attempt["label"] == "strict" and int(attempt["total_matches"] or "0") > 0
        for attempt in attempted_queries
    )
    if not error and current_clean_count == 0 and not locked_strict_result:
        term_stats = term_stats_for(profile, con, total_products, term_cache)
        query_term_stats = format_term_stats(term_stats)
        seen_queries = {attempt["query"] for attempt in attempted_queries}
        rescue_attempts = []
        if profile.code not in STRICT_QUERY_ONLY_CODES:
            rescue_attempts = weighted_query_attempts(term_stats) + diagnostic_rescue_attempts_for(profile)
        fallback_result = None if total_matches == 0 else fallback_result
        for label, terms in rescue_attempts[:RESCUE_ATTEMPT_LIMIT]:
            query = fts_query(terms)
            if not query or query in seen_queries:
                continue
            seen_queries.add(query)
            cache_key = (query, product_category_terms)
            if cache_key in query_cache:
                total_matches, categories, products, error = query_cache[cache_key]
            else:
                try:
                    total_matches = query_total(con, query, product_category_terms)
                    categories = query_categories(con, query, max_categories, product_category_terms)
                    products = query_products(con, query, max_products, product_category_terms)
                    error = ""
                except sqlite3.Error as exc:
                    error = str(exc)
                query_cache[cache_key] = (total_matches, categories, products, error)
            clean_count = clean_product_count(profile, products, semantic_filters) if total_matches > 0 and not error else 0
            attempted_queries.append(
                {
                    "label": label,
                    "query": query,
                    "total_matches": str(total_matches),
                    "error": error,
                }
            )
            if error:
                break
            if total_matches > 0 and clean_count > 0:
                break
            if total_matches > 0 and fallback_result is None:
                fallback_result = (query, total_matches, categories, products, error)
        if total_matches > 0 and clean_product_count(profile, products, semantic_filters) == 0 and fallback_result is not None:
            query, total_matches, categories, products, error = fallback_result
        if total_matches == 0:
            best_fallback = initial_fallback_result or fallback_result
            if best_fallback is not None:
                query, total_matches, categories, products, error = best_fallback
    # Primary-noun fallback: when nothing has matched yet, try a single-noun
    # query from the ESHA description's most distinctive hard term. Caps the
    # match count so we don't accept queries that return tens of thousands of
    # rows (those packs need narrower queries from the rewrite plan).
    if total_matches == 0 and not error and profile.code not in STRICT_QUERY_ONLY_CODES:
        seen_queries = {a["query"] for a in attempted_queries}
        candidate_terms: list[str] = []
        for tok in (profile.hard_terms or ()):
            if not tok or tok in GENERIC_QUERY_TERMS or tok in candidate_terms:
                continue
            if len(tok) < 3:
                continue
            candidate_terms.append(tok)
        for tok in candidate_terms[:3]:
            single_query = fts_query((tok,))
            if not single_query or single_query in seen_queries:
                continue
            try:
                single_total = query_total(con, single_query, product_category_terms)
            except sqlite3.Error:
                continue
            if 0 < single_total <= 5000:
                try:
                    cats = query_categories(con, single_query, max_categories, product_category_terms)
                    prods = query_products(con, single_query, max_products, product_category_terms)
                except sqlite3.Error:
                    continue
                attempted_queries.append({
                    "label": f"primary_noun_fallback:{tok}",
                    "query": single_query,
                    "total_matches": str(single_total),
                    "error": "",
                })
                query, total_matches, categories, products, error = (single_query, single_total, cats, prods, "")
                break
    if (
        rewrite_plan
        and rewrite_plan.get("exactness_status") == "unresolved"
        and total_matches == 0
    ):
        query = ""
        categories = []
        products = []
        error = ""
    slug = slugify(profile.description)
    out_path = out_root / profile.family / f"{int(profile.code):06d}_{slug}.md" if profile.code.isdigit() else out_root / profile.family / f"{slug}.md"
    write_pack(
        out_path,
        profile,
        query,
        attempted_queries,
        total_matches,
        categories,
        products,
        query_term_stats,
        destination_index,
        semantic_filters,
        product_category_terms,
        rewrite_plan,
    )
    return {
        "esha_code": profile.code,
        "description": profile.description,
        "family": profile.family,
        "query": query,
        "pack_path": str(out_path),
        "total_product_matches": str(total_matches),
        "category_count": str(len(categories)),
        "candidate_count_capped": str(len(products)),
        "top_category": categories[0][0] if categories else "",
        "top_category_count": str(categories[0][1]) if categories else "0",
        "error": error,
    }


def write_index(rows: list[dict[str, str]], out_index: Path = OUT_INDEX) -> None:
    out_index.parent.mkdir(parents=True, exist_ok=True)
    with out_index.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=INDEX_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def load_index(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def merge_index_rows(existing: list[dict[str, str]], updates: list[dict[str, str]]) -> list[dict[str, str]]:
    by_code = {row.get("esha_code", ""): {field: row.get(field, "") for field in INDEX_FIELDS} for row in existing if row.get("esha_code")}
    for row in updates:
        if row.get("esha_code"):
            by_code[row["esha_code"]] = {field: row.get(field, "") for field in INDEX_FIELDS}
    return sorted(by_code.values(), key=lambda row: (0, int(row["esha_code"])) if row["esha_code"].isdigit() else (1, row["esha_code"]))


def metric_from_lines(lines: list[str], label: str) -> str:
    prefix = f"- {label}:"
    for line in lines:
        if line.startswith(prefix):
            return line.split(":", 1)[1].strip()
    return ""


def table_count(lines: list[str], heading: str) -> int:
    in_section = False
    count = 0
    for line in lines:
        if line == heading:
            in_section = True
            continue
        if in_section and line.startswith("## "):
            break
        if in_section and line.startswith("| ") and not line.startswith("| ---") and not line.startswith("| count ") and not line.startswith("| rank "):
            count += 1
    return count


def top_category_from_lines(lines: list[str]) -> tuple[str, str]:
    in_section = False
    for line in lines:
        if line == "## Categories Returned By Query":
            in_section = True
            continue
        if in_section and line.startswith("## "):
            break
        if not in_section or not line.startswith("| ") or line.startswith("| ---") or line.startswith("| count "):
            continue
        parts = [part.strip() for part in line.strip().strip("|").split("|")]
        if len(parts) >= 2:
            return parts[1], parts[0]
    return "", "0"


def rebuild_index_from_packs(out_root: Path, profiles: list[matcher.EshaProfile]) -> list[dict[str, str]]:
    profile_by_code = {profile.code: profile for profile in profiles}
    rows: list[dict[str, str]] = []
    for path in sorted(out_root.rglob("*.md")):
        lines = path.read_text(encoding="utf-8").splitlines()
        if not lines:
            continue
        match = re.match(r"# ESHA\s+([^:]+):\s*(.*)", lines[0])
        if not match:
            continue
        code = match.group(1).strip()
        profile = profile_by_code.get(code)
        top_category, top_category_count = top_category_from_lines(lines)
        rows.append(
            {
                "esha_code": code,
                "description": profile.description if profile else match.group(2).strip(),
                "family": profile.family if profile else path.parent.name,
                "query": metric_from_lines(lines, "product_query").strip("`"),
                "pack_path": str(path),
                "total_product_matches": metric_from_lines(lines, "total_product_matches"),
                "category_count": str(table_count(lines, "## Categories Returned By Query")),
                "candidate_count_capped": metric_from_lines(lines, "product_rows_in_this_file"),
                "top_category": top_category,
                "top_category_count": top_category_count,
                "error": "",
            }
        )
    return sorted(rows, key=lambda row: (0, int(row["esha_code"])) if row["esha_code"].isdigit() else (1, row["esha_code"]))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--code", action="append", default=[])
    parser.add_argument("--codes-file", type=Path, default=None)
    parser.add_argument("--contains", default="")
    parser.add_argument("--family", default="")
    parser.add_argument("--limit-codes", type=int, default=None)
    parser.add_argument("--max-products", type=int, default=80)
    parser.add_argument("--max-categories", type=int, default=30)
    parser.add_argument("--out-root", default=str(OUT_ROOT))
    parser.add_argument("--index-out", default=str(OUT_INDEX))
    parser.add_argument("--no-index", action="store_true")
    parser.add_argument("--rebuild-index-from-packs", action="store_true")
    args = parser.parse_args()

    all_profiles = load_profiles()
    out_root = Path(args.out_root)
    index_path = Path(args.index_out)
    if args.rebuild_index_from_packs:
        rows = rebuild_index_from_packs(out_root, all_profiles)
        write_index(rows, index_path)
        print(f"rebuilt_index_rows={len(rows)} out_index={index_path}")
        return

    codes = {str(code).strip() for code in args.code if str(code).strip()}
    codes |= load_codes_file(args.codes_file)
    profiles = select_profiles(
        all_profiles,
        codes=codes,
        contains=args.contains,
        family=args.family,
        limit=args.limit_codes,
    )
    destination_index = build_destination_index(all_profiles)
    rows = []
    query_cache: dict[tuple[str, tuple[str, ...]], tuple[int, list[tuple[str, int]], list[dict[str, str]], str]] = {}
    term_cache: dict[str, int] = {}
    with sqlite3.connect(PRODUCTS_DB) as con:
        total_products = product_count(con)
        for idx, profile in enumerate(profiles, start=1):
            rows.append(
                build_pack(
                    con,
                    profile,
                    out_root,
                    args.max_products,
                    args.max_categories,
                    query_cache,
                    total_products,
                    term_cache,
                    destination_index,
                )
            )
            if idx % 100 == 0:
                print(f"packs={idx}", flush=True)
    if not args.no_index:
        partial = bool(codes or args.contains or args.family or args.limit_codes is not None)
        write_index(merge_index_rows(load_index(index_path), rows) if partial else rows, index_path)
    print(f"wrote_packs={len(rows)} out_root={out_root} index={'[skipped]' if args.no_index else index_path}")


if __name__ == "__main__":
    main()
