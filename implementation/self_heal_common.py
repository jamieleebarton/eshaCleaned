from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Iterable

import pandas as pd

import build_ingredient_fingerprint_clusters as ingredient_clusters
import build_product_to_best_esha_full_map as full_map
import match_esha_to_products as matcher
import self_heal_policy as policy


ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "implementation" / "output"
SELF_HEAL_DIR = OUT_DIR / "self_heal"
DEFAULT_INPUT_MAP = (
    OUT_DIR / "product_to_best_esha_full_map.vM3.csv"
    if (OUT_DIR / "product_to_best_esha_full_map.vM3.csv").exists()
    else OUT_DIR / "product_to_best_esha_full_map.csv"
)
VSELF_CSV = OUT_DIR / "product_to_best_esha_full_map.vSelf.csv"
SELF_HEAL_POLICY_VERSION = "retail_head_envelope_v17_bouillon_lane_alignment"

GENERIC_IDENTITY = (
    matcher.STOPWORDS
    | ingredient_clusters.TITLE_NOISE
    | ingredient_clusters.GENERIC_IDENTITY_TERMS
    | {
        "made", "style", "type", "with", "without", "organic", "natural",
        "premium", "select", "original", "classic", "lower", "sodium",
        "reduced", "free", "flavored", "flavour", "flavouring", "flavoring",
        "assorted", "mini", "large", "small", "count", "oz",
    }
)

FORM_TOKENS = {
    "bagel", "bagels", "bar", "bars", "bean", "beans", "bacon",
    "burger", "burgers", "patty", "patties", "pizza", "dressing",
    "dressings", "vinaigrette", "ranch", "oatmeal", "granola", "cereal",
    "yogurt", "cream", "creamer", "soup", "dip", "salsa", "hummus",
    "powder", "soda", "glucose", "syrup", "mix", "baking", "flour",
    "cookie", "cookies", "cooky",
}

BROAD_HEADS_NEED_IDENTITY = {
    "beans", "drink", "juice", "juice drink", "smoothie", "meal", "dish",
    "snack", "fruit", "vegetables", "sauce", "dessert",
}
BROAD_IDENTITY_NOISE = {
    "percent", "scoop", "powder", "instant", "drink", "beverage", "serving",
    "bottle", "carton", "box", "package", "packet", "pouch",
}
WATER_FLAVOR_TERMS = (set(matcher.FRUITS) - {"fruit", "fruits"}) | {"citrus", "ginger", "yuzu", "pomelo", "lychee"}
FLAVOR_TOKEN_ALIASES = {"citru": "citrus"}
BERRY_FLAVOR_TERMS = {"blackberry", "blueberry", "cranberry", "raspberry", "strawberry"}
TOMATO_MIX_TERMS = {"okra", "corn", "eggplant"}
DRY_DRINK_TERMS = {"dry", "mix", "powder", "powdered", "packet", "concentrate"}
SPREAD_FLAVOR_TERMS = (
    (set(matcher.FRUITS) - {"fruit", "fruits"})
    | {"fig", "rhubarb", "pomegranate", "jalapeno", "habanero", "pepper", "tomato", "morello"}
)
MILK_PRESERVED_FORM_TERMS = {"evaporated", "condensed", "canned", "dry", "dried", "powder", "powdered", "agglomerated"}
MILK_DRY_FORM_TERMS = {"dry", "dried", "powder", "powdered", "agglomerated"}
KEFIR_FLAVOR_TERMS = (set(matcher.FRUITS) - {"fruit", "fruits"}) | {"mango", "pomegranate", "vanilla"}
MILK_FLAVOR_TERMS = KEFIR_FLAVOR_TERMS | {
    "banana", "chocolate", "coffee", "hazelnut", "mocha", "orange", "creme",
    "maple", "pecan", "strawberry", "vanilla",
}
MILK_FUNCTIONAL_VARIANT_TERMS = {"plus", "bone", "health", "fiber", "omega", "dha", "protein", "cappuccino", "chai", "heartright"}
MILK_CULTURE_TERMS = {"acidophilus", "acidophilu", "bifidus", "bifidu", "probiotic", "cultured"}
MILK_SERVICE_SIZE_TERMS = {"short", "tall", "grande", "venti", "steamed"}
BOUILLON_IDENTITY_TERMS = {
    "bouillon", "broth", "base", "stock", "cube", "cubes", "dry", "dried",
    "dehydrated", "powder", "powdered", "pwd", "instant", "granule",
    "granules", "concentrate", "concentrated", "beef", "chicken",
    "vegetable", "vegetarian", "veggie", "clam", "seafood", "fish",
    "ham", "pork", "turkey", "flavor", "flavored", "low", "sodium",
    "reduced", "free",
}
BOUILLON_FLAVOR_TERMS = {
    "beef", "chicken", "vegetable", "vegetarian", "veggie", "clam",
    "seafood", "fish", "ham", "pork", "turkey",
}
BOUILLON_DRY_TERMS = {"cube", "cubes", "dry", "dried", "dehydrated", "powder", "powdered", "pwd", "instant", "granule", "granules"}
BOUILLON_HEADS = {"bouillon", "broth", "base", "stock"}
SEAFOOD_FORM_TERMS = {
    "shrimp", "crab", "clam", "scallop", "lobster", "oyster", "mussel",
    "cod", "haddock", "flounder", "salmon", "tuna", "tilapia", "catfish",
    "halibut", "pollock", "sole", "trout", "mahi", "mahimahi",
}
PRODUCE_VEGETABLE_TERMS = {
    "carrot", "zucchini", "squash", "kale", "celery", "radish", "radishe",
    "parsley", "broccoli", "cauliflower", "spinach", "lettuce", "greens",
}
SALAD_SUBTYPE_TERMS = {
    "egg", "coleslaw", "cole", "slaw", "whitefish", "tuna", "potato",
    "macaroni", "pasta", "chicken", "seafood", "crab",
}
MILK_SUBTYPE_TERMS = {
    "whole", "vitamin", "reduced", "lowfat", "low", "fat", "nonfat",
    "skim", "evaporated", "canned", "soy", "soymilk", "almond", "oat",
    "coconut", "goat", "lactose", "free", "chocolate", "orange", "creme",
    "maple", "pecan", "nog", "eggnog", "holiday", "buttermilk", "cultured", "kefir",
    "oatmilk", "alm", "almondmilk", "coconutmilk", "unsweetened", "sweetened",
    "plain", "vanilla", "banana", "strawberry",
}
PLANT_MILK_TERMS = {"soy", "soymilk", "alm", "almond", "oat", "oatmilk", "coconut", "almondmilk", "coconutmilk"}
CHEESE_SUBTYPE_TERMS = {
    "american", "asiago", "blue", "bleu", "brie", "cheddar", "colby",
    "cottage", "cream", "feta", "gouda", "goat", "jack", "manchego",
    "havarti", "monterey", "mozzarella", "muenster", "parmesan", "pepperjack",
    "provolone", "ricotta", "salsa", "swiss", "velveeta",
}
CHEESE_REQUIRED_SUBTYPE_TERMS = CHEESE_SUBTYPE_TERMS - {"cream", "salsa"}
CHEESE_FORM_TERMS = {
    "block", "brick", "crumbled", "cube", "diced", "shredded", "slice",
    "sliced", "spreadable", "wedge", "whipped",
}
POULTRY_FORM_TERMS = {"nugget", "nuggets", "strip", "strips", "tender", "tenders", "wing", "wings", "nibbler", "nibblers"}
PREPARED_FORM_REQUIRED_TERMS: dict[str, set[str]] = {
    "corn_dog": {"corn", "dog"},
    "quesadilla": {"quesadilla"},
    "pot_pie": {"pot", "pie"},
    "bologna": {"bologna"},
    "mac_and_cheese": {"macaroni", "cheese"},
    "pasta_dish": {"pasta"},
    "pierogi": {"pierogi"},
    "rice_dish": {"rice"},
    "quinoa_dish": {"quinoa"},
    "scalloped_potatoes": {"scalloped", "potato"},
    "potato_slices": {"potato", "slice"},
    "potatoes": {"potato"},
    "vegetable_appetizer": {"vegetable"},
    "ravioli": {"ravioli"},
    "tortellini": {"tortellini"},
    "crescent_roll": {"crescent", "roll"},
    "dinner_roll": {"dinner", "roll"},
    "sandwich_roll": {"sandwich", "roll"},
    "cinnamon_roll": {"cinnamon", "roll"},
    "wonton": {"wonton"},
}
FILLED_PASTA_FILLING_TERMS = {
    "cheese", "ricotta", "grana", "padano", "goat", "meat", "beef", "pork",
    "crab", "shrimp", "lobster", "eggplant", "pumpkin", "spinach",
}
MEAL_COMPONENT_TERMS = {
    "chicken", "turkey", "beef", "pork", "ham", "steak", "meatloaf",
    "salisbury", "rib", "ribs", "cutlet", "patty", "tender", "tenders",
    "noodle", "noodles", "biscuit", "biscuits", "stuffing", "corn",
    "pea", "peas", "carrot", "carrots", "broccoli", "gravy", "rice",
    "pasta", "macaroni", "spaghetti", "loaf", "fruit", "fruits",
}

HEAD_ALIASES = {
    "beans": {"beans", "baked beans", "beans rice", "beans and rice"},
    "baked beans": {"baked beans"},
    "pizza": {"pizza"},
    "bagel": {"bagel"},
    "bacon": {"bacon"},
    "salad dressing": {"salad dressing", "dressing"},
    "dressing": {"salad dressing", "dressing"},
    "vegetarian meat": {"vegetarian meat"},
    "meal": {"meal", "dish"},
    "dish": {"dish", "meal"},
    "cereal": {"cereal"},
    "yogurt": {"yogurt"},
    "ice cream": {"ice cream"},
    "baking powder": {"baking powder"},
    "baking soda": {"baking soda"},
    "glucose": {"glucose"},
    "sugar": {"sugar", "sweetener"},
    "sweetener": {"sweetener", "sugar"},
    "cream substitute": {"cream substitute"},
    "milk": {"milk", "almond milk"},
    "cookie": {"cookie", "cookies"},
    "cookies": {"cookie", "cookies"},
    "vegetables": {"vegetables", "vegetable"},
    "soda": {"soda"},
    "tea": {"tea"},
    "gum": {"gum", "chewing gum"},
    "pickles": {"pickles", "pickle"},
    "olives": {"olives", "olive"},
    "relish": {"relish"},
    "pasta": {"pasta", "noodles"},
    "noodles": {"noodles", "pasta"},
    "fish": {"fish"},
    "seafood": {"seafood", "fish", "shrimp"},
    "shrimp": {"shrimp", "fish"},
    "bar": {"bar"},
    "ketchup": {"ketchup", "catsup"},
    "spread": {"spread", "fruit spread"},
    "seeds": {"seeds", "seed"},
    "nuts": {"nuts", "nut"},
    "sandwich": {"sandwich"},
    "wrap": {"wrap"},
    "burrito": {"burrito"},
    "salad": {"salad"},
    "syrup": {"syrup"},
    "soup": {"soup", "chili"},
    "dip": {"dip", "hummus", "salsa"},
    "salsa": {"salsa", "dip"},
    "hummus": {"hummus", "dip"},
    "flour": {"flour"},
    "chips": {"chips", "snack"},
    "snack": {"snack", "chips", "crackers", "pretzels"},
    "candy": {"candy", "chocolate", "chocolate bar", "candy bar", "gum"},
    "chocolate": {"chocolate", "chocolate bar", "candy"},
    "popcorn": {"popcorn"},
    "doughnut": {"doughnut", "donut"},
    "donut": {"doughnut", "donut"},
    "fruit": {"fruit", "apple", "banana", "orange"},
    "potatoes": {"potatoes", "potato"},
    "mashed potatoes": {"mashed potatoes"},
    "turkey": {"turkey", "lunchmeat"},
    "chicken": {"chicken", "dish"},
    "pork": {"pork", "dish"},
    "sausage": {"sausage", "lunchmeat"},
    "lunchmeat": {"lunchmeat", "ham", "turkey", "sausage"},
}

LANE_HEADS: dict[str, tuple[str, ...]] = {
    "salad_dressing": ("Salad Dressing", "Dressing", "Sauce"),
    "dessert_topping": ("Dessert Topping", "Topping", "Sauce", "Syrup"),
    "pizza": ("Pizza",),
    "frozen_patties_burgers": ("Vegetarian Meat", "Meal", "Dish", "Sandwich"),
    "cereal": ("Cereal",),
    "yogurt": ("Yogurt",),
    "frozen_dessert": ("Ice Cream", "Yogurt", "Pudding"),
    "juice": ("Juice", "Juice Drink", "Smoothie", "Drink"),
    "water": ("Drink", "Water"),
    "cracker": ("Cracker", "Biscuit"),
    "oil": ("Oil",),
    "grain": ("Cereal", "Rice", "Wheat", "Flour"),
    "canned_bottled_beans": ("Beans", "Baked Beans"),
    "vegetable_lentil_mixes": ("Beans", "Vegetables", "Dish"),
    "baking_additives": ("Baking Powder", "Baking Soda", "Sweetener"),
    "baking_mix": ("Baking Mix", "Cake", "Cookie", "Muffin", "Pancakes", "Waffles"),
    "flour": ("Flour",),
    "creamer": ("Cream Substitute", "Coffee", "Drink"),
    "plant_milk": ("Milk", "Drink"),
    "milk": ("Milk", "Eggnog"),
    "candy_chocolate": ("Candy", "Chocolate", "Chocolate Bar", "Candy Bar", "Gum"),
    "bacon_meat": ("Bacon", "Pork", "Sausage"),
    "lunchmeat": ("Lunchmeat", "Sausage", "Ham", "Turkey"),
    "prepared_meal": ("Meal", "Dish"),
    "sandwich_wrap": ("Sandwich", "Wrap", "Burrito", "Meal", "Dish"),
    "soup": ("Soup", "Chili"),
    "dip_salsa": ("Dip", "Salsa", "Hummus", "Sauce"),
    "sauce_condiment": ("Sauce", "Salad Dressing", "Dressing", "Dip", "Salsa", "Jelly", "Jam", "Spread"),
    "syrup": ("Syrup", "Sweetener"),
    "snack": ("Snack", "Chips", "Cracker", "Pretzels", "Nuts", "Seeds"),
    "bread": ("Bread", "Bagel", "Bun", "Roll"),
    "cookie": ("Cookie", "Cookies", "Biscuit", "Cracker"),
    "dessert": ("Dessert", "Cake", "Pie", "Pudding", "Ice Cream", "Cookie"),
    "pastry": ("Pastry", "Muffin", "Croissant", "Sweet Roll", "Doughnut"),
    "produce_fruit": ("Fruit", "Apple", "Banana", "Salad"),
    "frozen_fruit": ("Fruit", "Smoothie", "Juice"),
    "seasoning": ("Seasoning", "Spice", "Sauce"),
    "cheese": ("Cheese",),
    "sweet_spread": ("Nut Butter", "Peanut Butter", "Jelly", "Jam", "Spread", "Syrup"),
    "powdered_drink": ("Drink", "Shake", "Glucose"),
    "coffee": ("Coffee", "Drink"),
    "soda": ("Soda", "Drink"),
    "ready_drink": ("Drink", "Juice", "Juice Drink", "Smoothie", "Tea", "Coffee", "Soda", "Water"),
    "tea": ("Tea", "Drink"),
    "pickles_relish": ("Pickles", "Olives", "Pepper", "Peppers", "Relish"),
    "pasta": ("Pasta", "Noodles", "Macaroni"),
    "sauce": ("Sauce", "Ketchup", "Mustard", "Salad Dressing", "Dressing"),
    "vegetable": ("Vegetables", "Tomato", "Tomatoes", "Beans", "Pumpkin", "Asparagus"),
    "gum_mints": ("Gum", "Candy"),
    "bar_snack": ("Bar", "Snack", "Cereal", "Trail Mix", "Nuts", "Seeds"),
    "frozen_appetizer": ("Dish", "Meal", "Pizza", "Snack"),
    "fish_seafood": ("Fish", "Seafood", "Shrimp"),
    "rice": ("Rice", "Rice Dish", "Rice & Beans"),
    "butter_spread": ("Butter", "Butter Substitute", "Spread"),
    "nut_butter": ("Nut Butter", "Peanut Butter"),
    "sugar": ("Sugar", "Sweetener"),
    "deli_salad": ("Salad", "Dish", "Meal"),
    "chili_stew": ("Chili", "Stew", "Soup", "Dish"),
    "cream": ("Cream", "Cream Substitute"),
    "meat_prepared": ("Chicken", "Turkey", "Pork", "Beef", "Ham", "Sausage", "Bacon", "Meal", "Dish"),
    "canned_meat": ("Chicken", "Turkey", "Pork", "Beef", "Ham", "Lunchmeat"),
    "fruit": ("Fruit", "Apple", "Apples", "Banana", "Apricot"),
}


@dataclass(frozen=True)
class Replacement:
    code: str
    description: str
    head: str
    family: str
    score: float
    reason: str
    pool_size: int


def norm_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").lower()).strip()


def norm_head(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def esha_head(description: str) -> str:
    return str(description or "").split(",", 1)[0].strip()


def slug(value: str) -> str:
    out = re.sub(r"[^a-z0-9]+", "_", str(value or "").lower()).strip("_")
    return out or "unknown"


def split_terms(value: str) -> tuple[str, ...]:
    return tuple(t for t in str(value or "").split() if t)


def top_values(values: Iterable[str], limit: int = 5) -> str:
    counts = Counter(v for v in values if v)
    return " | ".join(f"{k}:{v}" for k, v in counts.most_common(limit))


FOOD_SALAD_COMPONENTS = {
    "potato", "potatoes", "chicken", "cobb", "seafood", "crab", "tuna",
    "egg", "eggs", "lettuce", "greens", "macaroni", "pasta", "coleslaw",
    "slaw", "ham", "turkey", "chef",
}


def is_food_salad_product(description: str, title_tokens: set[str]) -> bool:
    desc = norm_text(description)
    if "salad" not in title_tokens and "salad" not in desc:
        return False
    food_salad_phrases = (
        "potato salad",
        "seafood salad",
        "chicken salad",
        "tuna salad",
        "egg salad",
        "macaroni salad",
        "pasta salad",
        "cobb",
        "coleslaw",
        "cole slaw",
    )
    if any(phrase in desc for phrase in food_salad_phrases):
        return True
    if title_tokens & FOOD_SALAD_COMPONENTS:
        return True
    return False


SAUCE_FORM_ALIASES: dict[str, tuple[str, ...]] = {
    "barbecue_sauce": ("barbecue", "barbeque", "bbq"),
    "hot_sauce": ("buffalo", "hot sauce", "hotsauce", "wing", "gochujang", "gochu jang", "sriracha"),
    "butter_sauce": ("butter", "garlic butter"),
    "pasta_sauce": ("pasta", "marinara", "alfredo", "vodka", "bolognese", "pomodoro"),
    "horseradish": ("horseradish",),
}


def sauce_form_mismatch_reason(form: str, candidate_description: str) -> str:
    aliases = SAUCE_FORM_ALIASES.get(form)
    if not aliases:
        return ""
    desc = norm_text(candidate_description)
    if not any(alias in desc for alias in aliases):
        return f"sauce_subtype_mismatch:{form}"
    if form != "pasta_sauce" and "pasta" in desc:
        return f"sauce_subtype_mismatch:{form}->pasta_sauce"
    if form == "horseradish" and "mustard" in desc and "horseradish" not in desc:
        return "sauce_subtype_mismatch:horseradish->mustard"
    return ""


@lru_cache(maxsize=None)
def _tokens_for_description(description: str) -> frozenset[str]:
    return frozenset(
        normalize_food_tokens({FLAVOR_TOKEN_ALIASES.get(token, token) for token in matcher.tokens_for(norm_text(description))})
    )


def normalize_food_tokens(tokens: Iterable[str]) -> set[str]:
    out = {str(token or "").strip().lower() for token in tokens if str(token or "").strip()}
    aliases = {
        "shrimps": "shrimp",
        "alm": "almond",
        "crabs": "crab",
        "clams": "clam",
        "scallops": "scallop",
        "lob": "lobster",
        "lobs": "lobster",
        "lobsters": "lobster",
        "oysters": "oyster",
        "mussels": "mussel",
        "wings": "wing",
        "rolls": "roll",
        "crescents": "crescent",
        "wontons": "wonton",
        "nuggets": "nugget",
        "strips": "strip",
        "tenders": "tender",
        "nibblers": "nibbler",
        "eggs": "egg",
        "potatoes": "potato",
        "slices": "slice",
        "carrots": "carrot",
        "zucchinis": "zucchini",
        "squashes": "squash",
        "radishes": "radish",
        "pierogies": "pierogi",
        "pierogis": "pierogi",
        "corndogs": "corndog",
        "vegetables": "vegetable",
        "sprinkles": "sprinkle",
        "preserves": "preserve",
        "cubes": "cube",
        "granules": "granule",
    }
    for token in tuple(out):
        if token in aliases:
            out.add(aliases[token])
    if "mac" in out:
        out.add("macaroni")
    if "soymilk" in out:
        out.update({"soy", "milk"})
    if "oatmilk" in out:
        out.update({"oat", "milk"})
    if "almondmilk" in out:
        out.update({"almond", "milk"})
    if "coconutmilk" in out:
        out.update({"coconut", "milk"})
    if "buttermilk" in out:
        out.update({"butter", "milk"})
    if "corndog" in out:
        out.update({"corn", "dog"})
    if "lobster" in out and "tail" in out:
        out.add("lobster_tail")
    return out


def _milk_preserved_lanes(tokens: set[str]) -> set[str]:
    lanes: set[str] = set()
    if "evaporated" in tokens:
        lanes.add("evaporated")
    if "condensed" in tokens:
        lanes.add("condensed")
    if tokens & MILK_DRY_FORM_TERMS:
        lanes.add("dry")
    if not lanes and "canned" in tokens:
        lanes.add("canned")
    return lanes


def _water_flavors(tokens: set[str]) -> set[str]:
    return {FLAVOR_TOKEN_ALIASES.get(token, token) for token in tokens if FLAVOR_TOKEN_ALIASES.get(token, token) in WATER_FLAVOR_TERMS}


def _flavor_covered(term: str, candidate_terms: set[str]) -> bool:
    if term in candidate_terms:
        return True
    return term in BERRY_FLAVOR_TERMS and "berry" in candidate_terms


def water_flavor_mismatch_reason(lane: str, product_evidence: set[str], candidate_description: str) -> str:
    if lane != "water":
        return ""
    product_flavors = _water_flavors(product_evidence)
    candidate_tokens = _tokens_for_description(candidate_description)
    candidate_flavors = _water_flavors(candidate_tokens)
    if "berry" in candidate_tokens:
        candidate_flavors.add("berry")
    missing = {term for term in product_flavors if not _flavor_covered(term, candidate_flavors)}
    if missing:
        return "water_flavor_missing:" + ",".join(sorted(missing))
    extra = {
        term
        for term in candidate_flavors
        if term not in product_flavors and not (term == "berry" and product_flavors & BERRY_FLAVOR_TERMS)
    }
    if extra and not product_flavors:
        return "water_flavor_unasked:" + ",".join(sorted(extra))
    return ""


def soup_form_mismatch_reason(form: str, product_evidence: set[str], candidate_description: str) -> str:
    if form != "chowder":
        return ""
    candidate_tokens = _tokens_for_description(candidate_description)
    if "chowder" not in candidate_tokens:
        return "chowder_product_to_non_chowder"
    if "clam" in product_evidence and "clam" not in candidate_tokens:
        return "clam_chowder_product_to_non_clam_chowder"
    return ""


def bouillon_form_mismatch_reason(form: str, product_evidence: set[str], candidate_description: str) -> str:
    if form != "bouillon":
        return ""
    product_tokens = normalize_food_tokens(product_evidence)
    candidate_tokens = _tokens_for_description(candidate_description)
    candidate_head = norm_head(esha_head(candidate_description))
    if candidate_head not in BOUILLON_HEADS:
        return "bouillon_product_to_non_bouillon"
    product_flavors = product_tokens & BOUILLON_FLAVOR_TERMS
    candidate_flavors = candidate_tokens & BOUILLON_FLAVOR_TERMS
    if product_flavors and not (product_flavors & candidate_flavors):
        return "bouillon_flavor_missing:" + ",".join(sorted(product_flavors))
    if "cube" in product_tokens and not (candidate_tokens & BOUILLON_DRY_TERMS):
        return "bouillon_cube_to_non_dry_candidate"
    return ""


def tomato_form_mismatch_reason(form: str, product_evidence: set[str], candidate_description: str) -> str:
    candidate_tokens = _tokens_for_description(candidate_description)
    if form == "tomato_sauce" and "sauce" not in candidate_tokens:
        return "tomato_sauce_product_to_non_sauce"
    if form == "tomato_vegetable_mix":
        missing = sorted(term for term in (product_evidence & TOMATO_MIX_TERMS) if term not in candidate_tokens)
        if missing:
            return "tomato_mix_missing:" + ",".join(missing)
    return ""


def beverage_form_mismatch_reason(lane: str, form: str, product_evidence: set[str], candidate_description: str) -> str:
    candidate_tokens = _tokens_for_description(candidate_description)
    product_tokens = normalize_food_tokens(product_evidence)
    if lane == "water":
        if candidate_tokens & DRY_DRINK_TERMS:
            return "water_product_to_dry_drink_mix"
        if "water" not in candidate_tokens and "seltzer" not in candidate_tokens:
            return "water_product_to_non_water_drink"
    if lane == "powdered_drink" or form in {"hot_cocoa", "drink_mix", "cocktail_mix", "bloody_mary_mix"}:
        if not (candidate_tokens & DRY_DRINK_TERMS):
            return "powdered_drink_to_non_dry_mix"
    return ""


def cheese_form_mismatch_reason(form: str, product_evidence: set[str], candidate_description: str) -> str:
    candidate_tokens = _tokens_for_description(candidate_description)
    candidate_head = norm_head(esha_head(candidate_description))
    if form == "cream_cheese":
        if candidate_head != "cream cheese":
            return "cream_cheese_product_to_non_cream_cheese"
        return ""
    if form == "cheese_food":
        if candidate_head != "cheese food":
            return "cheese_food_product_to_non_cheese_food"
        return ""
    if form == "cheese":
        product_specific = product_evidence & CHEESE_REQUIRED_SUBTYPE_TERMS
        if product_specific and not (candidate_tokens & product_specific):
            return "cheese_missing_product_subtype:" + ",".join(sorted(product_specific - candidate_tokens))
        candidate_specific = (candidate_tokens & (CHEESE_SUBTYPE_TERMS | CHEESE_FORM_TERMS)) - {"cheese"}
        missing = sorted(term for term in candidate_specific if term not in product_evidence)
        if missing:
            return "cheese_unasked_subtype:" + ",".join(missing[:8])
    return ""


def seafood_form_mismatch_reason(form: str, product_evidence: set[str], candidate_description: str) -> str:
    if form not in (SEAFOOD_FORM_TERMS | {"fish"}):
        return ""
    candidate_tokens = _tokens_for_description(candidate_description)
    product_tokens = normalize_food_tokens(product_evidence)
    product_seafood = product_tokens & SEAFOOD_FORM_TERMS
    if not product_seafood:
        return ""
    candidate_seafood = candidate_tokens & SEAFOOD_FORM_TERMS
    if not candidate_seafood:
        return "seafood_identity_missing:" + ",".join(sorted(product_seafood))
    if product_seafood & candidate_seafood:
        return ""
    return "seafood_identity_mismatch:" + ",".join(sorted(product_seafood)) + "->" + ",".join(sorted(candidate_seafood))


def poultry_form_mismatch_reason(form: str, product_evidence: set[str], candidate_description: str) -> str:
    required_by_form = {
        "chicken_nuggets": {"chicken", "nugget"},
        "chicken_strips": {"chicken", "strip"},
        "chicken_wings": {"chicken", "wing"},
        "popcorn_chicken": {"chicken", "popcorn"},
        "canned_chicken": {"chicken", "canned"},
    }
    required = required_by_form.get(form)
    if not required:
        return ""
    candidate_tokens = _tokens_for_description(candidate_description)
    candidate_head = norm_head(esha_head(candidate_description))
    normalized_candidate = set(candidate_tokens)
    if "nuggets" in normalized_candidate:
        normalized_candidate.add("nugget")
    if "strips" in normalized_candidate:
        normalized_candidate.add("strip")
    if "tenders" in normalized_candidate:
        normalized_candidate.add("tender")
    if "wings" in normalized_candidate:
        normalized_candidate.add("wing")
    if "nibblers" in normalized_candidate:
        normalized_candidate.add("nibbler")
    if form == "chicken_nuggets" and candidate_head != "nuggets":
        return "chicken_nuggets_to_non_nuggets"
    if form == "popcorn_chicken" and candidate_head != "popcorn chicken":
        return "popcorn_chicken_to_non_popcorn_chicken"
    if form == "chicken_strips" and candidate_head not in {"strips", "chicken"}:
        return "chicken_strips_to_wrong_head"
    if form == "chicken_wings" and "wing" not in normalized_candidate:
        return "chicken_wings_to_non_wings"
    if form == "canned_chicken" and candidate_head != "chicken":
        return "canned_chicken_to_non_chicken"
    missing = sorted(term for term in required if term not in normalized_candidate)
    if form == "chicken_strips" and "strip" in missing and "tender" in normalized_candidate:
        missing.remove("strip")
    if form == "canned_chicken" and "canned" in missing and (normalized_candidate & {"can", "broth", "mixin", "premium", "chunk"}):
        missing.remove("canned")
    if missing:
        return f"{form}_missing:" + ",".join(missing)
    return ""


def prepared_form_mismatch_reason(form: str, product_evidence: set[str], candidate_description: str) -> str:
    required = PREPARED_FORM_REQUIRED_TERMS.get(form)
    if not required:
        return ""
    candidate_tokens = _tokens_for_description(candidate_description)
    product_tokens = normalize_food_tokens(product_evidence)
    if form == "mac_and_cheese":
        if "macaroni" in candidate_tokens and "cheese" in candidate_tokens:
            return ""
        return "prepared_form_mismatch:mac_and_cheese"
    if form == "pot_pie":
        if "pot" in candidate_tokens and "pie" in candidate_tokens:
            return ""
        return "prepared_form_mismatch:pot_pie"
    if form == "corn_dog":
        if "corndog" in candidate_tokens or {"corn", "dog"} <= candidate_tokens:
            return ""
        return "prepared_form_mismatch:corn_dog"
    if form == "bologna":
        if "bologna" not in candidate_tokens:
            return "prepared_form_mismatch:bologna"
        if "chicken" in product_tokens and "chicken" not in candidate_tokens:
            return "prepared_form_mismatch:bologna_missing_chicken"
        return ""
    if form == "pierogi":
        if "pierogi" not in candidate_tokens:
            return "prepared_form_mismatch:pierogi_missing_leaf"
        return ""
    if form == "ravioli":
        if "ravioli" not in candidate_tokens:
            return "prepared_form_mismatch:ravioli_missing_leaf"
        for seafood in ("crab", "shrimp", "lobster"):
            if seafood in product_tokens and seafood not in candidate_tokens:
                return f"prepared_form_mismatch:ravioli_missing_{seafood}_filling"
        if product_tokens & {"meat", "beef", "pork"} and not (candidate_tokens & {"meat", "beef", "pork"}):
            return "prepared_form_mismatch:ravioli_missing_meat_filling"
        for filling in ("goat", "eggplant", "pumpkin", "spinach"):
            if filling in product_tokens and filling not in candidate_tokens:
                return f"prepared_form_mismatch:ravioli_missing_{filling}_filling"
        if product_tokens & {"cheese", "ricotta", "grana", "padano"} and not (candidate_tokens & {"cheese", "ricotta"}):
            return "prepared_form_mismatch:ravioli_missing_cheese_filling"
        return ""
    if form == "tortellini":
        if "tortellini" not in candidate_tokens:
            return "prepared_form_mismatch:tortellini_missing_leaf"
        for seafood in ("crab", "shrimp", "lobster"):
            if seafood in product_tokens and seafood not in candidate_tokens:
                return f"prepared_form_mismatch:tortellini_missing_{seafood}_filling"
        if product_tokens & {"meat", "beef", "pork"} and not (candidate_tokens & {"meat", "beef", "pork"}):
            return "prepared_form_mismatch:tortellini_missing_meat_filling"
        for filling in ("goat", "eggplant", "pumpkin", "spinach"):
            if filling in product_tokens and filling not in candidate_tokens:
                return f"prepared_form_mismatch:tortellini_missing_{filling}_filling"
        if product_tokens & {"cheese", "ricotta", "grana", "padano"} and not (candidate_tokens & {"cheese", "ricotta"}):
            return "prepared_form_mismatch:tortellini_missing_cheese_filling"
        return ""
    if form in {"crescent_roll", "dinner_roll", "sandwich_roll", "cinnamon_roll"}:
        if "roll" not in candidate_tokens:
            return f"prepared_form_mismatch:{form}:roll"
        subtype = form.split("_", 1)[0]
        if subtype not in candidate_tokens:
            return f"prepared_form_mismatch:{form}:{subtype}"
        unasked_roll_flavors = (
            candidate_tokens & {"garlic", "butter", "caramel", "cheese", "cinnamon", "reduced", "fat"}
        ) - product_tokens
        if unasked_roll_flavors:
            return f"prepared_form_mismatch:{form}:unasked_" + ",".join(sorted(unasked_roll_flavors))
        return ""
    if form == "wonton":
        if "wonton" not in candidate_tokens:
            return "prepared_form_mismatch:wonton"
        for seafood in ("crab", "shrimp", "lobster"):
            if seafood in product_tokens and seafood not in candidate_tokens:
                return f"prepared_form_mismatch:wonton_missing_{seafood}_filling"
        return ""
    if form in {"scalloped_potatoes", "potato_slices", "potatoes"}:
        missing = set()
        if "potato" not in candidate_tokens:
            missing.add("potato")
        if form == "scalloped_potatoes" and "scalloped" not in candidate_tokens:
            missing.add("scalloped")
        if form == "potato_slices" and "slice" not in candidate_tokens and "dehydrated" not in candidate_tokens:
            missing.add("slice")
        if missing:
            return f"prepared_form_mismatch:{form}:" + ",".join(sorted(missing))
        return ""
    if form == "rice_dish":
        if "rice" not in candidate_tokens:
            return "prepared_form_mismatch:rice_dish"
        if "chicken" in product_tokens and "chicken" not in candidate_tokens:
            return "prepared_form_mismatch:rice_dish_missing_chicken"
        return ""
    if form == "quinoa_dish":
        if "quinoa" not in candidate_tokens:
            return "prepared_form_mismatch:quinoa_dish"
        return ""
    if form == "quesadilla" and "quesadilla" not in candidate_tokens:
        return "prepared_form_mismatch:quesadilla"
    missing = sorted(required - candidate_tokens)
    if missing:
        return f"prepared_form_mismatch:{form}:" + ",".join(missing)
    return ""


def spread_form_mismatch_reason(form: str, product_evidence: set[str], candidate_description: str) -> str:
    if form not in {"jelly", "jam", "spread"}:
        return ""
    product_tokens = normalize_food_tokens(product_evidence)
    candidate_tokens = _tokens_for_description(candidate_description)
    product_flavors = product_tokens & SPREAD_FLAVOR_TERMS
    if "concord" in product_tokens and "grape" in product_tokens:
        product_flavors |= {"concord", "grape"}
    if not product_flavors:
        return ""
    candidate_flavors = candidate_tokens & (SPREAD_FLAVOR_TERMS | {"concord"})
    missing = sorted(product_flavors - candidate_flavors)
    if missing:
        return "spread_flavor_missing:" + ",".join(missing)
    return ""


def milk_form_mismatch_reason(form: str, product_evidence: set[str], candidate_description: str) -> str:
    if form not in {"milk", "plant_milk", "buttermilk", "kefir", "eggnog", "flavored_milk"}:
        return ""
    product_tokens = normalize_food_tokens(product_evidence)
    candidate_tokens = _tokens_for_description(candidate_description)
    candidate_head = norm_head(esha_head(candidate_description))
    product_preserved = product_tokens & MILK_PRESERVED_FORM_TERMS
    candidate_preserved = candidate_tokens & MILK_PRESERVED_FORM_TERMS
    product_preserved_lanes = _milk_preserved_lanes(product_tokens)
    candidate_preserved_lanes = _milk_preserved_lanes(candidate_tokens)
    if (candidate_tokens & MILK_SERVICE_SIZE_TERMS) and not (product_tokens & MILK_SERVICE_SIZE_TERMS):
        return "milk_subtype_mismatch:retail_to_service_size"
    if form == "buttermilk":
        if candidate_head != "buttermilk":
            return "milk_subtype_mismatch:buttermilk"
        if candidate_preserved and not product_preserved:
            return "milk_subtype_mismatch:buttermilk_dried"
        return ""
    if form == "kefir":
        if candidate_head != "kefir":
            return "milk_subtype_mismatch:kefir"
        candidate_flavors = candidate_tokens & KEFIR_FLAVOR_TERMS
        product_flavors = product_tokens & KEFIR_FLAVOR_TERMS
        unasked_flavors = candidate_flavors - product_flavors
        if unasked_flavors:
            return "milk_subtype_mismatch:kefir_unasked_flavor:" + ",".join(sorted(unasked_flavors))
        return ""
    if form == "eggnog":
        if candidate_head not in {"eggnog", "eggnog substitute"}:
            return "milk_subtype_mismatch:eggnog"
        return ""
    if form == "plant_milk":
        plant_terms = product_tokens & {"soy", "soymilk", "almond", "oat", "coconut"}
        if plant_terms:
            allowed_heads = {"soy milk", "almond milk", "oat milk", "coconut milk"}
            if plant_terms == {"coconut"}:
                allowed_heads.add("cream substitute")
            if candidate_head not in allowed_heads:
                return "milk_subtype_mismatch:plant_milk"
            if "soy" in plant_terms or "soymilk" in plant_terms:
                if not (candidate_tokens & {"soy", "soymilk"} or candidate_head == "soy milk"):
                    return "milk_subtype_missing:soy"
            if "almond" in plant_terms and "almond" not in candidate_tokens and candidate_head != "almond milk":
                return "milk_subtype_missing:almond"
            if "oat" in plant_terms and "oat" not in candidate_tokens and candidate_head != "oat milk":
                return "milk_subtype_missing:oat"
            if "coconut" in plant_terms and "coconut" not in candidate_tokens and candidate_head != "coconut milk":
                return "milk_subtype_missing:coconut"
            if "puerto" in candidate_tokens or "rican" in candidate_tokens:
                if not (product_tokens & {"puerto", "rican"}):
                    return "milk_subtype_mismatch:plant_milk_unasked_puerto_rican"
            if "unsweetened" in product_tokens and "unsweetened" not in candidate_tokens:
                return "milk_subtype_mismatch:plant_milk_missing_unsweetened"
            unasked_variant = (
                candidate_tokens
                & (MILK_FLAVOR_TERMS | MILK_FUNCTIONAL_VARIANT_TERMS)
                - product_tokens
                - {"original", "plain"}
            )
            if unasked_variant:
                return "milk_subtype_mismatch:plant_milk_unasked_variant:" + ",".join(sorted(unasked_variant))
        if "evaporated" in candidate_tokens or "canned" in candidate_tokens:
            return "milk_subtype_mismatch:plant_to_evaporated"
        return ""
    if candidate_head in {"buttermilk", "kefir", "eggnog", "eggnog substitute"}:
        return f"milk_subtype_mismatch:plain_to_{candidate_head.replace(' ', '_')}"
    if candidate_tokens & {"soy", "soymilk", "almond", "oat", "coconut"}:
        return "milk_subtype_mismatch:plain_to_plant_milk"
    if candidate_preserved and not product_preserved:
        return "milk_subtype_mismatch:fluid_to_preserved_milk:" + ",".join(sorted(candidate_preserved))
    if product_preserved and not candidate_preserved:
        return "milk_subtype_missing_preserved_form:" + ",".join(sorted(product_preserved))
    if product_preserved_lanes and candidate_preserved_lanes:
        missing_lanes = product_preserved_lanes - candidate_preserved_lanes
        extra_lanes = candidate_preserved_lanes - product_preserved_lanes
        if missing_lanes or extra_lanes:
            return (
                "milk_subtype_preserved_form_mismatch:"
                + ",".join(sorted(product_preserved_lanes))
                + "->"
                + ",".join(sorted(candidate_preserved_lanes))
            )
    if "solid" in candidate_tokens and "solid" not in product_tokens:
        return "milk_subtype_mismatch:fluid_to_milk_solids"
    if (candidate_tokens & MILK_CULTURE_TERMS) and not (product_tokens & MILK_CULTURE_TERMS):
        return "milk_subtype_mismatch:plain_to_cultured_milk"
    if (candidate_tokens & MILK_FUNCTIONAL_VARIANT_TERMS) and not (product_tokens & MILK_FUNCTIONAL_VARIANT_TERMS):
        return "milk_subtype_mismatch:plain_milk_unasked_variant:" + ",".join(
            sorted((candidate_tokens & MILK_FUNCTIONAL_VARIANT_TERMS) - product_tokens)
        )
    explicit_fat = product_tokens & {"whole", "reduced", "lowfat", "low", "nonfat", "skim", "2", "1"}
    if {"fat", "free"} <= product_tokens:
        explicit_fat.add("nonfat")
    candidate_reduced_fat = candidate_tokens & {"reduced", "lowfat", "low", "nonfat", "skim", "2", "1"}
    if not explicit_fat and candidate_reduced_fat:
        return "milk_subtype_mismatch:generic_to_reduced_fat"
    if "skim" in product_tokens and not (candidate_tokens & {"skim", "nonfat"}):
        return "milk_subtype_missing:skim"
    if "nonfat" in product_tokens and not (candidate_tokens & {"skim", "nonfat"}):
        return "milk_subtype_missing:nonfat"
    if {"fat", "free"} <= product_tokens and not (candidate_tokens & {"skim", "nonfat"}):
        return "milk_subtype_missing:nonfat"
    if "evaporated" not in product_tokens and "canned" not in product_tokens and "evaporated" in candidate_tokens:
        return "milk_subtype_mismatch:non_evaporated_to_evaporated"
    if "whole" in product_tokens and "whole" not in candidate_tokens:
        return "milk_subtype_missing:whole"
    if "vitamin" in product_tokens and not explicit_fat and not product_preserved_lanes:
        if candidate_tokens & {"evaporated", "nonfat", "skim", "lowfat", "2", "1"}:
            return "milk_subtype_mismatch:vitamin_d_to_reduced_or_evaporated"
    if "vitamin" in product_tokens and "evaporated" in candidate_tokens and "evaporated" not in product_tokens:
        return "milk_subtype_mismatch:vitamin_d_to_evaporated"
    if form == "flavored_milk":
        flavors = product_tokens & {"chocolate", "orange", "creme", "maple", "pecan", "strawberry", "vanilla"}
        if flavors and not (candidate_tokens & flavors):
            return "milk_flavor_missing:" + ",".join(sorted(flavors - candidate_tokens))
    return ""


def produce_form_mismatch_reason(form: str, product_evidence: set[str], candidate_description: str) -> str:
    if form not in {"carrot", "vegetable", "produce_vegetable"}:
        return ""
    product_tokens = normalize_food_tokens(product_evidence)
    candidate_tokens = _tokens_for_description(candidate_description)
    if "salad" in candidate_tokens and "salad" not in product_tokens:
        return "produce_product_to_salad"
    product_vegetables = product_tokens & PRODUCE_VEGETABLE_TERMS
    candidate_vegetables = candidate_tokens & PRODUCE_VEGETABLE_TERMS
    if form == "carrot" and "carrot" not in candidate_tokens:
        return "produce_identity_missing:carrot"
    if product_vegetables and candidate_vegetables and not (product_vegetables & candidate_vegetables):
        return "produce_identity_mismatch:" + ",".join(sorted(product_vegetables)) + "->" + ",".join(sorted(candidate_vegetables))
    return ""


def salad_form_mismatch_reason(form: str, product_evidence: set[str], candidate_description: str) -> str:
    if form not in {"egg_salad", "coleslaw", "whitefish_salad", "tuna_salad", "potato_salad", "macaroni_salad", "salad"}:
        return ""
    product_tokens = normalize_food_tokens(product_evidence)
    candidate_tokens = _tokens_for_description(candidate_description)
    if form == "coleslaw":
        if "coleslaw" in candidate_tokens or {"cole", "slaw"} <= candidate_tokens:
            return ""
        return "salad_subtype_mismatch:coleslaw"
    required_by_form = {
        "egg_salad": {"egg"},
        "whitefish_salad": {"whitefish"},
        "tuna_salad": {"tuna"},
        "potato_salad": {"potato"},
        "macaroni_salad": {"macaroni"},
    }
    required = required_by_form.get(form)
    if required and not (candidate_tokens & required):
        return f"salad_subtype_mismatch:{form}"
    product_subtypes = product_tokens & SALAD_SUBTYPE_TERMS
    candidate_subtypes = candidate_tokens & SALAD_SUBTYPE_TERMS
    if product_subtypes and candidate_subtypes and not (product_subtypes & candidate_subtypes):
        return "salad_identity_mismatch:" + ",".join(sorted(product_subtypes)) + "->" + ",".join(sorted(candidate_subtypes))
    return ""


def brownie_form_mismatch_reason(form: str, candidate_description: str) -> str:
    if form not in {"brownie", "brownie_mix"}:
        return ""
    candidate_tokens = _tokens_for_description(candidate_description)
    if "brownie" not in candidate_tokens:
        return f"brownie_form_mismatch:{form}->non_brownie"
    if form == "brownie_mix" and not (candidate_tokens & {"dry", "mix"}):
        return "brownie_form_mismatch:brownie_mix->not_dry_mix"
    return ""


def category_lane_for(description: str, category: str, title_tokens: set[str]) -> str:
    desc = norm_text(description)
    cat = norm_text(category)
    text = f"{desc} {cat}"
    # Strong retail categories and clear product forms are structural routing
    # signals. Keep them ahead of weak title words like "cookie", "cake", or
    # "syrup" so a dry-pasta aisle item cannot become a prepared dish and a
    # butter/spread item cannot become a cookie just because of flavor text.
    if "popcorn" in title_tokens or "popcorn" in desc:
        return "snack"
    if (
        ("pickles, olives, peppers & relishes" in cat or "pickles olives peppers relishes" in cat)
        and not is_food_salad_product(description, title_tokens)
    ):
        return "pickles_relish"
    if "pasta by shape" in cat or cat == "all noodles":
        return "pasta"
    if "canned & bottled beans" in cat:
        return "canned_bottled_beans"
    if "butter & spread" in cat:
        return "butter_spread"
    if "nut & seed butters" in cat:
        return "nut_butter"
    normalized_title = normalize_food_tokens(title_tokens)
    if "milk" in normalized_title and (normalized_title & {"evaporated", "condensed"}):
        return "milk"
    plant_milk_title = "milk" in normalized_title and bool(normalized_title & PLANT_MILK_TERMS)
    plant_milk_text = "plant based milk" in desc or "plant-based milk" in desc
    plant_milk_category = any(term in cat for term in ("plant based milk", "milk/milk substitutes", "milk/cream", "non alcoholic beverages", "ready to drink"))
    creamer_text = "creamer" in normalized_title or "creamer" in desc or "cream substitutes" in cat or "cream/cream substitutes" in cat
    if (plant_milk_text or plant_milk_title) and plant_milk_category and not creamer_text:
        return "plant_milk"
    if "plant based milk" in cat:
        return "plant_milk"
    if "milk additives" in cat or "cream substitutes" in cat or "cream/cream substitutes" in cat or re.search(r"\bcreamer\b", text):
        return "creamer"
    if any(term in cat for term in ("cake cookie", "cupcake mixes", "baking/cooking mixes/supplies", "bread & muffin mixes")):
        if ("mashed" in title_tokens or "mash" in title_tokens) and (title_tokens & {"potato", "potatoes"}):
            return "vegetable"
        return "baking_mix"
    if "glucose" in title_tokens:
        return "powdered_drink"
    if "syrup" in title_tokens and not (title_tokens & {"sausage", "sausages", "bacon", "cracker", "crackers", "cookie", "cookies"}):
        return "syrup"
    if "baking powder" in desc or ({"baking", "powder"} <= title_tokens):
        return "baking_additives"
    if "baking soda" in desc or ({"baking", "soda"} <= title_tokens):
        return "baking_additives"
    if "dessert toppings" in cat and (title_tokens & {"sauce", "fondue", "topping", "toppings"}):
        return "dessert_topping"
    if "snack, energy" in cat or "granola bars" in cat:
        if (title_tokens & {"cup", "cups"}) and ({"peanut", "butter"} <= title_tokens or "peanut butter" in desc):
            return "candy_chocolate"
        return "bar_snack"
    if "wholesome snacks" in cat and (title_tokens & matcher.FRUITS):
        return "fruit"
    if any(term in cat for term in ("chips", "pretzels", "snacks", "popcorn, peanuts", "seeds", "related snacks")):
        return "snack"
    if "prepared pasta & pizza sauces" in cat or "pasta sauces" in cat or "pizza sauces" in cat:
        return "sauce_condiment"
    if "pizza mixes & other dry dinners" in cat:
        if "rice" in title_tokens:
            return "rice"
        return "pizza" if "pizza" in title_tokens else "prepared_meal"
    if "dough based products" in cat and "dough" in title_tokens:
        return "bread"
    if (
        ("not ready to drink" in cat or "powdered drinks" in cat)
        and (title_tokens & {"powder", "powdered", "mix", "protein", "cocoa"})
    ):
        return "powdered_drink"
    if "plant based water" in cat or "coconut water" in desc:
        return "water"
    if "oils edible" in cat or "cooking spray" in text or "cooking sprays" in text:
        return "oil"
    if "gum" in title_tokens:
        return "gum_mints"
    if is_food_salad_product(description, title_tokens):
        return "deli_salad"
    # Hard retail lanes must beat flavor/brand text. "Coffee & donuts ice
    # cream", "Original Donut Shop coffee", and cheesecake-flavored yogurt are
    # not doughnuts, coffee cake, or cake.
    if "ice cream" in cat or "frozen yogurt" in cat or "frozen dessert" in cat or "gelato" in text:
        return "frozen_dessert"
    if cat == "coffee":
        return "coffee"
    if cat == "yogurt" or ("yogurt" in cat and "frozen yogurt" not in cat):
        return "yogurt"
    if title_tokens & {"donut", "donuts", "doughnut", "doughnuts"} or "donut" in desc or "doughnut" in desc:
        return "pastry"
    if "cookie" in title_tokens or "cookies" in title_tokens or "cooky" in title_tokens:
        return "cookie"
    if "cake" in title_tokens or "cupcake" in title_tokens or "cupcakes" in title_tokens:
        return "dessert"
    if "salad dressing" in cat or "mayonnaise" in cat:
        return "salad_dressing"
    if "pizza" in cat or "pizza" in title_tokens:
        return "pizza"
    if "sweet bakery products" in cat or "savoury bakery products" in cat:
        return "bread" if ("bagel" in title_tokens or "bagels" in title_tokens) else "pastry"
    if "frozen patties" in cat or "burger" in cat or "burgers" in cat:
        return "frozen_patties_burgers"
    if "cereal" in cat:
        return "cereal"
    if "fruit & vegetable juice" in cat or "juice" in cat or "nectars" in cat or "fruit drinks" in cat:
        return "juice"
    if cat == "water" or "sparkling water" in text:
        return "water"
    if cat == "soda":
        return "soda"
    if "non alcoholic beverages" in cat or cat == "other drinks":
        return "ready_drink"
    if "iced & bottle tea" in cat or "tea bags" in cat:
        return "tea"
    if "crackers" in cat or "biscotti" in cat:
        return "cracker"
    if "biscuits/cookies" in cat or "cookies" in cat:
        return "cookie"
    if "vegetable & cooking oils" in cat or cat.endswith(" oils") or "olive oil" in text:
        return "oil"
    if "other grains" in cat or "grains & seeds" in cat:
        return "grain"
    if "frozen vegetables" in cat or "canned vegetables" in cat or cat == "tomatoes":
        return "vegetable"
    if "vegetable and lentil mixes" in cat:
        return "vegetable_lentil_mixes"
    if any(term in cat for term in ("vegetables prepared/processed", "vegetables  prepared/processed", "vegetables - prepared/processed")):
        return "vegetable_lentil_mixes"
    if "baking additives" in cat or "extracts" in cat:
        return "baking_additives"
    if "flours" in cat or "corn meal" in cat:
        return "flour"
    if (cat in {"milk"} or "milk/milk substitutes" in cat or "milk/cream" in cat) and (normalized_title & PLANT_MILK_TERMS):
        return "plant_milk"
    if cat in {"milk"} or "milk/milk substitutes" in cat or "milk/cream" in cat:
        return "milk"
    if "chocolate" in cat or "candy" in cat or "confectionery" in cat:
        return "candy_chocolate"
    if "chewing gum" in cat or "mints" in cat:
        return "gum_mints"
    if "bacon" in cat or "sausages" in cat or "ribs" in cat:
        return "bacon_meat"
    if "pepperoni" in cat or "salami" in cat or "cold cuts" in cat:
        return "lunchmeat"
    if any(term in cat for term in ("meat/poultry/other animals prepared/processed", "meat/poultry/other animals - prepared/processed")):
        return "meat_prepared"
    if any(term in cat for term in ("frozen dinners", "entrees", "prepared meals", "prepared wraps", "burittos", "burritos", "ready-made combination meals", "based products / meals", "prepared/preserved foods variety packs")):
        return "prepared_meal"
    if any(term in cat for term in ("sandwiches/filled rolls/wraps", "filled rolls", "wraps")):
        return "sandwich_wrap"
    if "soup" in cat:
        return "soup"
    if "dips" in cat or "salsa" in cat:
        return "dip_salsa"
    if any(term in cat for term in ("sauces/spreads/dips/condiments", "ketchup", "mustard", "bbq", "cheese sauce", "oriental, mexican & ethnic sauces", "other cooking sauces")):
        return "sauce_condiment"
    if "jam, jelly" in cat or "fruit spreads" in cat:
        return "sweet_spread"
    if "syrup" in cat or "molasses" in cat:
        return "syrup"
    if "breads & buns" in cat or cat in {"bread", "breads"}:
        return "bread"
    if any(term in cat for term in ("pastries", "muffins", "croissants", "sweet rolls")):
        return "pastry"
    if "crusts & dough" in cat:
        return "pastry"
    if "baking decorations" in cat or "dessert toppings" in cat:
        return "dessert_topping"
    if any(term in cat for term in ("desserts", "dessert sauces", "cakes", "cupcakes", "snack cakes")):
        return "dessert"
    if "puddings" in cat or "custards" in cat:
        return "dessert"
    if "frozen fruit" in cat:
        return "frozen_fruit"
    if "canned fruit" in cat:
        return "fruit"
    if "pre-packaged fruit" in cat or "fruit & vegetables" in cat:
        return "produce_fruit"
    if "frozen appetizers" in cat or "hors d'oeuvres" in cat:
        return "frozen_appetizer"
    if "frozen fish" in cat or cat == "fish & seafood" or "fish unprepared" in cat or "shellfish" in cat:
        return "fish_seafood"
    if cat == "rice":
        return "rice"
    if "pasta dinners" in cat:
        return "prepared_meal"
    if "deli salads" in cat:
        return "deli_salad"
    if "chili & stew" in cat:
        return "chili_stew"
    if "granulated, brown & powdered sugar" in cat:
        return "sugar"
    if cat == "cream":
        return "cream"
    if any(term in cat for term in ("seasoning", "spices", "salts", "marinades", "tenderizers")):
        return "seasoning"
    if cat == "cheese" or cat.endswith("/cheese"):
        return "cheese"
    if "sweet spreads" in cat:
        return "sweet_spread"
    if "powdered drinks" in cat or "specialty formula supplements" in cat or cat == "vitamins" or "supplements" in cat:
        return "powdered_drink"
    return slug(category)


def product_form_for(description: str, category: str, lane: str, title_tokens: set[str]) -> str:
    desc = norm_text(description)
    text = f"{desc} {norm_text(category)}"
    norm_tokens = normalize_food_tokens(title_tokens)
    has = title_tokens.__contains__
    mixed_snack_terms = {
        "pretzel", "pretzels", "cookie", "cookies", "cup", "cups",
        "candy", "chocolate", "nut", "nuts", "cracker", "crackers",
        "jelly", "bean", "beans",
    }
    if ("mashed" in title_tokens or "mash" in title_tokens) and (title_tokens & {"potato", "potatoes"}):
        meal_components = {
            "chicken", "turkey", "beef", "pork", "steak", "meatloaf", "salisbury",
            "rib", "ribs", "cutlet", "patty", "tenders", "tender", "noodle",
            "noodles", "biscuit", "biscuits", "stuffing", "loaf", "bowl",
            "meal", "dinner", "entree",
        }
        component_hits = title_tokens & meal_components
        # "Chicken broth mashed potatoes" is a mashed-potato mix, not a
        # chicken meal. Real meal components still route to Meal/Dish.
        if not component_hits or (component_hits <= {"chicken"} and "broth" in title_tokens):
            return "mashed_potatoes"
    if "corndog" in norm_tokens or {"corn", "dog"} <= norm_tokens:
        return "corn_dog"
    if "quesadilla" in norm_tokens:
        return "quesadilla"
    if "pot" in norm_tokens and "pie" in norm_tokens:
        return "pot_pie"
    if "bologna" in norm_tokens:
        return "bologna"
    if "pierogi" in norm_tokens:
        return "pierogi"
    if "wonton" in norm_tokens:
        return "wonton"
    if ("macaroni" in norm_tokens or "mac" in norm_tokens) and "cheese" in norm_tokens:
        return "mac_and_cheese"
    if "ravioli" in norm_tokens:
        return "ravioli"
    if "tortellini" in norm_tokens:
        return "tortellini"
    if lane == "pizza" and ("bagel" in title_tokens or "bagels" in title_tokens):
        return "pizza_bagel"
    if lane == "pizza":
        return "pizza"
    if lane == "frozen_dessert":
        return "ice_cream" if "ice cream" in text else "frozen_dessert"
    if lane == "coffee":
        return "coffee"
    if lane == "yogurt":
        if "kefir" in norm_tokens:
            return "kefir"
        if "smoothie" in title_tokens or "smoothie" in desc:
            return "yogurt_smoothie"
        if "parfait" in title_tokens or "parfait" in desc:
            return "yogurt_parfait"
        return "yogurt"
    if lane == "deli_salad":
        if "egg" in norm_tokens:
            return "egg_salad"
        if "coleslaw" in norm_tokens or {"cole", "slaw"} <= norm_tokens:
            return "coleslaw"
        if "whitefish" in norm_tokens:
            return "whitefish_salad"
        if "tuna" in norm_tokens:
            return "tuna_salad"
        if "potato" in norm_tokens:
            return "potato_salad"
        if "macaroni" in norm_tokens:
            return "macaroni_salad"
        return "salad"
    if lane == "salad_dressing" or any(t in title_tokens for t in ("dressing", "vinaigrette", "mayonnaise", "mayo")):
        return "dressing"
    if any(t in title_tokens for t in ("burger", "burgers", "patty", "patties")):
        return "veggie_burger" if ({"veggie", "vegetarian"} & title_tokens or "black bean" in text) else "burger"
    if title_tokens & {"donut", "donuts", "doughnut", "doughnuts"} or "donut" in desc or "doughnut" in desc:
        return "doughnut"
    if "baking powder" in text or (has("baking") and has("powder")):
        return "baking_powder"
    if "baking soda" in text or (has("baking") and has("soda")):
        return "baking_soda"
    if "glucose" in title_tokens:
        return "glucose"
    if lane == "water":
        if "seltzer" in norm_tokens:
            return "seltzer"
        if "sparkling" in norm_tokens:
            return "sparkling_water"
        return "water"
    if "oatmeal" in title_tokens:
        return "oatmeal"
    if "granola" in title_tokens:
        return "granola"
    if lane == "cereal":
        return "cereal"
    if lane == "snack" and "popcorn" in desc:
        if (title_tokens & {"mix", "combination", "assortment", "collection"}) and (title_tokens & mixed_snack_terms):
            return "snack_mix"
        return "popcorn"
    if lane in {"canned_bottled_beans", "vegetable_lentil_mixes", "vegetable"} and ("green bean" in text or "green beans" in text):
        return "green_beans"
    if lane in {"vegetable_lentil_mixes", "vegetable"} and "potato" in norm_tokens:
        if "scalloped" in norm_tokens:
            return "scalloped_potatoes"
        if "slice" in norm_tokens or "dehydrated" in norm_tokens:
            return "potato_slices"
        return "potatoes"
    if lane in {"canned_bottled_beans", "vegetable_lentil_mixes"} and ("bean" in title_tokens or "beans" in title_tokens):
        if any(t in title_tokens for t in ("burger", "burgers", "patty", "patties", "tamale", "tamales", "burrito", "burritos", "enchilada", "bowl", "bowls", "blend", "rice", "quinoa", "spinach")):
            return "bean_dish"
        if "baked" in title_tokens:
            return "baked_beans"
        if "refried" in title_tokens:
            return "refried_beans"
        return "beans"
    if "vanilla bean" in text and lane not in {"canned_bottled_beans", "vegetable_lentil_mixes"}:
        return f"{lane}_vanilla_bean_flavor"
    if any(t in title_tokens for t in ("bean", "beans")) and lane not in {"canned_bottled_beans", "vegetable_lentil_mixes"}:
        return f"{lane}_bean_component"
    if lane == "bacon_meat" and "bacon" in title_tokens:
        return "bacon"
    if "bacon" in title_tokens:
        return f"{lane}_bacon_component"
    if lane == "creamer":
        return "creamer"
    if lane == "plant_milk":
        return "plant_milk"
    if lane == "milk":
        if "kefir" in norm_tokens:
            return "kefir"
        if "buttermilk" in norm_tokens:
            return "buttermilk"
        if norm_tokens & PLANT_MILK_TERMS:
            return "plant_milk"
        if "nog" in norm_tokens or "eggnog" in norm_tokens:
            return "eggnog"
        if norm_tokens & {"chocolate", "strawberry", "orange", "creme", "maple", "pecan"}:
            return "flavored_milk"
        return "milk"
    if lane == "soup":
        if "chowder" in title_tokens or "chowder" in desc:
            return "chowder"
        if "chili" in title_tokens or "chili" in desc:
            return "chili"
        return "soup"
    if lane == "seasoning":
        if "bouillon" in norm_tokens:
            return "bouillon"
        if ("broth" in norm_tokens or "stock" in norm_tokens) and (norm_tokens & BOUILLON_DRY_TERMS):
            return "bouillon"
        if "base" in norm_tokens and (norm_tokens & BOUILLON_FLAVOR_TERMS):
            return "bouillon"
        return "seasoning"
    if lane == "dip_salsa":
        if "hummus" in title_tokens:
            return "hummus"
        if "salsa" in title_tokens:
            return "salsa"
        return "dip"
    if lane == "baking_mix":
        if "brownie" in title_tokens or "brownies" in title_tokens:
            return "brownie_mix"
        if "cookie" in title_tokens or "cookies" in title_tokens or "cooky" in title_tokens:
            return "cookie_mix"
        if "cake" in title_tokens or "cupcake" in title_tokens or "cupcakes" in title_tokens:
            return "cake_mix"
        if "bread" in title_tokens:
            return "bread_mix"
        if "bar" in title_tokens or "bars" in title_tokens:
            return "bar_mix"
        if "roll" in title_tokens or "rolls" in title_tokens:
            return "roll_mix"
        return "baking_mix"
    if lane == "sauce_condiment":
        if any(t in title_tokens for t in ("dressing", "vinaigrette", "mayonnaise", "mayo")):
            return "dressing"
        if "ketchup" in title_tokens:
            return "ketchup"
        if "horseradish" in title_tokens:
            return "horseradish"
        if "mustard" in title_tokens:
            return "mustard"
        if title_tokens & {"bbq", "barbecue", "barbeque"}:
            return "barbecue_sauce"
        if (
            title_tokens & {"buffalo", "hotsauce", "gochujang", "sriracha"}
            or {"gochu", "jang"} <= title_tokens
            or ("hot" in title_tokens and "sauce" in title_tokens)
        ):
            return "hot_sauce"
        if "butter" in title_tokens and "sauce" in title_tokens:
            return "butter_sauce"
        if title_tokens & {"pasta", "marinara", "alfredo", "vodka", "bolognese", "pomodoro"}:
            return "pasta_sauce"
        if "jelly" in title_tokens:
            return "jelly"
        if "jam" in title_tokens or "preserves" in title_tokens:
            return "jam"
        return "sauce"
    if lane == "syrup":
        return "syrup"
    if lane == "dessert_topping":
        if "whipped" in title_tokens or "topping" in title_tokens:
            return "whipped_topping" if "whipped" in title_tokens else "dessert_topping"
        if "sprinkle" in norm_tokens or "crunch" in title_tokens:
            return "decorative_topping"
        return "dessert_topping"
    if lane == "candy_chocolate":
        if (title_tokens & {"cup", "cups"}) and ({"peanut", "butter"} <= title_tokens or "peanut butter" in desc):
            return "peanut_butter_cup"
        if "gum" in title_tokens:
            return "gum"
        return "candy"
    if lane == "snack":
        if (title_tokens & {"mix", "combination", "assortment", "collection"}) and "popcorn" in desc and (title_tokens & mixed_snack_terms):
            return "snack_mix"
        if "popcorn" in title_tokens or "popcorn" in desc:
            return "popcorn"
        if "seed" in title_tokens or "seeds" in title_tokens:
            return "seeds"
        if "nut" in title_tokens or "nuts" in title_tokens:
            return "nuts"
        if "chip" in title_tokens or "chips" in title_tokens:
            return "chips"
        if "pretzel" in title_tokens or "pretzels" in title_tokens:
            return "pretzels"
        if "mix" in title_tokens or "trail" in title_tokens:
            return "snack_mix"
        return "snack"
    if lane == "flour":
        return "flour"
    if lane == "bread" and ("bagel" in title_tokens or "bagels" in title_tokens):
        return "bagel"
    if lane == "bread" and "dough" in title_tokens and "pizza" in title_tokens:
        return "pizza_dough"
    if lane == "bread":
        if "roll" in title_tokens or "rolls" in title_tokens:
            return "roll"
        if "bun" in title_tokens or "buns" in title_tokens:
            return "bun"
        return "bread"
    if lane == "cookie":
        if "cookie" in title_tokens or "cookies" in title_tokens or "cooky" in title_tokens:
            return "cookie"
        if "cracker" in title_tokens or "crackers" in title_tokens:
            return "cracker"
        return "cookie"
    if lane == "dessert":
        if ("brownie" in title_tokens or "brownies" in title_tokens) and "pie" not in title_tokens:
            return "brownie"
        if "cake" in title_tokens or "cupcake" in title_tokens or "cupcakes" in title_tokens:
            return "cake"
        if "cookie" in title_tokens or "cookies" in title_tokens or "cooky" in title_tokens:
            return "cookie"
        if "pie" in title_tokens:
            return "pie"
        if "pudding" in title_tokens:
            return "pudding"
        if "ice" in title_tokens and "cream" in title_tokens:
            return "ice_cream"
        return "dessert"
    if lane == "pastry":
        if "biscuit" in title_tokens or "biscuits" in title_tokens:
            return "biscuit"
        if "muffin" in title_tokens or "muffins" in title_tokens:
            return "muffin"
        if "crescent" in norm_tokens and "roll" in norm_tokens:
            return "crescent_roll"
        if "sandwich" in norm_tokens and "roll" in norm_tokens:
            return "sandwich_roll"
        if "dinner" in norm_tokens and "roll" in norm_tokens:
            return "dinner_roll"
        if "cinnamon" in norm_tokens and "roll" in norm_tokens:
            return "cinnamon_roll"
        if "roll" in title_tokens or "rolls" in title_tokens:
            return "roll"
        if "doughnut" in title_tokens or "donut" in title_tokens:
            return "doughnut"
        if "croissant" in title_tokens:
            return "croissant"
        return "pastry"
    if lane == "sandwich_wrap":
        for form in ("burrito", "wrap", "sandwich", "roll"):
            if form in title_tokens or form in text:
                return form
        return "sandwich"
    if lane == "prepared_meal":
        if "quinoa" in norm_tokens:
            return "quinoa_dish"
        if "rice" in norm_tokens:
            return "rice_dish"
        if title_tokens & {"pasta", "noodle", "noodles", "spaghetti", "macaroni", "lasagna", "ravioli", "fettuccine"}:
            return "pasta_dish"
        if "pizza" in title_tokens:
            return "pizza"
        for form in ("burrito", "wrap", "sandwich", "taco", "quesadilla", "tamale", "bowl"):
            if form in title_tokens or form in text:
                return form
        return "meal"
    if lane == "meat_prepared":
        if "bacon" in title_tokens and ("turkey" in title_tokens or "chicken" in title_tokens):
            return "poultry_bacon"
        if "bacon" in title_tokens and any(term in text for term in ("sliced bacon", "smoked bacon", "cured bacon", "turkey bacon", "chicken bacon")):
            return "bacon"
        for form in ("chicken", "turkey", "pork", "beef", "ham", "sausage"):
            if form in title_tokens:
                return form
        return "meal"
    if lane == "soda":
        return "soda"
    if lane == "ready_drink":
        if "kombucha" in norm_tokens:
            return "kombucha"
        if "cocoa" in norm_tokens:
            return "hot_cocoa"
        if "protein" in norm_tokens or "whey" in norm_tokens:
            return "protein_drink"
        if "bloody" in norm_tokens and "mary" in norm_tokens:
            return "bloody_mary_mix"
        if "cocktail" in norm_tokens and "mix" in norm_tokens:
            return "cocktail_mix"
        if "yogurt" in text or "oatgurt" in text:
            return "drinkable_yogurt"
        if "probiotic" in norm_tokens and "drink" in norm_tokens:
            return "probiotic_drink"
        if "tea" in title_tokens:
            return "tea"
        if "coffee" in title_tokens:
            return "coffee"
        if "juice" in title_tokens:
            return "juice"
        if "smoothie" in title_tokens:
            return "smoothie"
        if "soda" in title_tokens:
            return "soda"
        return "drink"
    if lane == "tea":
        return "tea"
    if lane == "pickles_relish":
        if title_tokens & {"olive", "olives", "olif"}:
            return "olives"
        if "relish" in title_tokens:
            return "relish"
        if "pepper" in title_tokens or "peppers" in title_tokens:
            return "peppers"
        return "pickles"
    if lane == "pasta":
        if "ravioli" in norm_tokens:
            return "ravioli"
        if "tortellini" in norm_tokens:
            return "tortellini"
        if "quinoa" in norm_tokens and "pasta" not in norm_tokens:
            return "quinoa"
        return "noodles" if "noodle" in title_tokens or "noodles" in title_tokens else "pasta"
    if lane == "vegetable":
        if ("tomato" in title_tokens or "tomatoes" in title_tokens) and "sauce" in title_tokens:
            return "tomato_sauce"
        if (title_tokens & {"tomato", "tomatoes"}) and (title_tokens & TOMATO_MIX_TERMS):
            return "tomato_vegetable_mix"
        if "tomato" in title_tokens or "tomatoes" in title_tokens:
            return "tomatoes"
        if "pumpkin" in title_tokens:
            return "pumpkin"
        if "bean" in title_tokens or "beans" in title_tokens:
            return "bean_dish" if any(t in title_tokens for t in ("blend", "rice", "quinoa", "corn", "bowl")) else "beans"
        return "vegetable"
    if lane == "gum_mints":
        return "gum" if "gum" in title_tokens else "candy"
    if lane == "bar_snack":
        if "bar" in title_tokens or "bars" in title_tokens:
            return "bar"
        if "granola" in title_tokens:
            return "granola"
        if any(t in title_tokens for t in ("mix", "trail")):
            return "snack_mix"
        return "snack"
    if lane == "frozen_appetizer":
        if "popcorn" in title_tokens and "chicken" in title_tokens:
            return "popcorn_chicken"
        if "chicken" in title_tokens and "nugget" in title_tokens:
            return "chicken_nuggets"
        if "chicken" in title_tokens and (title_tokens & {"strip", "tender", "nibbler"}):
            return "chicken_strips"
        if "chicken" in title_tokens and "wing" in title_tokens:
            return "chicken_wings"
        return "pizza" if "pizza" in title_tokens else "dish"
    if lane == "canned_meat":
        if "chicken" in title_tokens:
            return "canned_chicken"
        return "meat"
    if lane == "fish_seafood":
        seafood_hits = norm_tokens & SEAFOOD_FORM_TERMS
        if seafood_hits:
            for form in ("shrimp", "crab", "clam", "scallop", "lobster", "oyster", "mussel", "cod", "haddock", "flounder", "salmon", "tuna"):
                if form in seafood_hits:
                    return form
        return "fish"
    if lane == "rice":
        return "rice"
    if lane == "deli_salad":
        if "egg" in norm_tokens:
            return "egg_salad"
        if "coleslaw" in norm_tokens or {"cole", "slaw"} <= norm_tokens:
            return "coleslaw"
        if "whitefish" in norm_tokens:
            return "whitefish_salad"
        if "tuna" in norm_tokens:
            return "tuna_salad"
        if "potato" in norm_tokens:
            return "potato_salad"
        if "macaroni" in norm_tokens:
            return "macaroni_salad"
        return "salad"
    if lane == "chili_stew":
        return "chili" if "chili" in title_tokens else "stew"
    if lane == "butter_spread":
        return "butter" if "butter" in title_tokens else "spread"
    if lane == "nut_butter":
        return "nut_butter"
    if lane == "sugar":
        return "sugar"
    if lane == "cream":
        return "cream"
    if lane in {"produce_fruit", "fruit"}:
        if "carrot" in norm_tokens:
            return "carrot"
        if norm_tokens & PRODUCE_VEGETABLE_TERMS:
            return "produce_vegetable"
        primary = ingredient_clusters.primary_food(tuple(title_tokens))
        return primary or "fruit"
    if lane == "cheese":
        if "cheese food" in text:
            return "cheese_food"
        if "cream cheese" in text or ({"cream", "cheese"} <= title_tokens):
            return "cream_cheese"
        return "cheese"
    if lane == "sweet_spread":
        if any(t in title_tokens for t in ("butter", "spread")) and any(t in title_tokens for t in ("peanut", "almond", "cashew")):
            return "nut_butter"
        if "jelly" in title_tokens:
            return "jelly"
        if "jam" in title_tokens or "preserves" in title_tokens:
            return "jam"
        return "spread"
    if lane == "powdered_drink":
        if "glucose" in title_tokens:
            return "glucose"
        if "cocoa" in norm_tokens:
            return "hot_cocoa"
        if "margarita" in norm_tokens or ("cocktail" in norm_tokens and "mix" in norm_tokens):
            return "cocktail_mix"
        if "shake" in title_tokens:
            return "shake"
        if "protein" in title_tokens:
            return "protein_drink"
        if "powder" in norm_tokens or "powdered" in norm_tokens or "mix" in norm_tokens:
            return "drink_mix"
        return "drink_mix"
    if lane == "coffee":
        return "coffee"
    primary = ingredient_clusters.primary_food(tuple(title_tokens))
    return primary or lane


def role_for(description: str, lane: str, form: str, title_tokens: set[str]) -> str:
    text = norm_text(description)
    if "vanilla bean" in text and lane not in {"canned_bottled_beans", "vegetable_lentil_mixes"}:
        return "flavor"
    if form.endswith("_component") or form in {"pizza_bagel", "veggie_burger", "burger", "dressing"}:
        if title_tokens & {"bean", "beans", "bacon", "bagel", "bagels"}:
            return "component"
    return "main"


def identity_terms_for(title_tokens: set[str], ingredient_tokens: set[str], form: str, role: str) -> tuple[str, ...]:
    terms = set(title_tokens) - GENERIC_IDENTITY - FORM_TOKENS
    if role == "main":
        terms |= {t for t in title_tokens if t in matcher.FRUITS or t in matcher.VEGETABLES or t in matcher.LEGUMES}
    if form in {"veggie_burger", "burger"}:
        terms |= title_tokens & {"black", "bean", "beans", "veggie", "vegetarian", "turkey", "chicken"}
    if form == "pizza_bagel":
        terms |= title_tokens & {"pizza", "bagel", "bagels", "pepperoni", "cheese", "sausage"}
    if form == "pizza_dough":
        terms |= title_tokens & {"pizza", "dough", "crust", "grain", "wheat", "whole"}
    if form == "dressing":
        terms |= title_tokens & {"ranch", "french", "italian", "caesar", "bacon", "honey"}
    if form in {"baking_powder", "baking_soda", "glucose"}:
        terms |= title_tokens & {"baking", "powder", "soda", "glucose", "double", "acting"}
    if form in {"oatmeal", "granola", "cereal"}:
        terms |= title_tokens & {"oatmeal", "granola", "oat", "oats", "cereal"}
    if form == "popcorn":
        terms |= title_tokens & {
            "popcorn", "butter", "buttery", "light", "movie", "theater",
            "kettle", "caramel", "cheddar", "cheese", "white", "yellow",
            "microwave", "microwavable", "microwaveable", "unpopped", "popped",
        }
    if form == "doughnut":
        terms |= title_tokens & {"donut", "donuts", "doughnut", "doughnuts", "powdered", "cinnamon", "chocolate", "cake"}
        if any(t.startswith("donut") or t.startswith("doughnut") for t in title_tokens):
            terms.add("donut")
    if form in {"yogurt", "yogurt_smoothie", "yogurt_parfait"}:
        terms |= title_tokens & {
            "yogurt", "smoothie", "parfait", "strawberry", "blueberry",
            "raspberry", "blackberry", "banana", "peach", "vanilla",
            "cheesecake", "granola",
        }
    if form == "biscuit":
        terms |= title_tokens & {"biscuit", "biscuits", "butter", "honey", "flaky", "homestyle", "jumbo"}
    if form in {"barbecue_sauce", "hot_sauce", "butter_sauce", "pasta_sauce", "horseradish"}:
        terms |= title_tokens & {
            "bbq", "barbecue", "barbeque", "buffalo", "hot", "hotsauce",
            "gochu", "jang", "gochujang", "sriracha", "wing", "butter", "garlic", "pasta",
            "marinara", "alfredo", "vodka", "bolognese", "pomodoro", "sauce",
            "horseradish", "cream",
        }
    if form in {"chowder", "tomato_sauce", "tomato_vegetable_mix"}:
        terms |= title_tokens & {
            "chowder", "clam", "new", "england", "manhattan", "tomato",
            "tomatoes", "sauce", "okra", "corn", "eggplant",
        }
    if form == "bouillon":
        terms |= normalize_food_tokens(title_tokens) & BOUILLON_IDENTITY_TERMS
    if form in {"brownie", "brownie_mix"}:
        terms |= title_tokens & {
            "brownie", "brownies", "fudge", "chocolate", "walnut", "caramel",
            "salted", "swirl", "baked", "soft", "mix",
        }
    if form == "peanut_butter_cup":
        terms |= title_tokens & {"peanut", "butter", "cup", "cups", "chocolate", "dark", "mint"}
    if form == "dessert_topping":
        terms |= title_tokens & {"sauce", "fondue", "toffee", "chocolate", "peanut", "butter", "topping"}
    if form == "mashed_potatoes":
        terms |= title_tokens & {
            "mashed", "mash", "potato", "potatoes", "homestyle", "loaded",
            "garlic", "butter", "buttery", "herb", "cheddar", "cheese",
            "instant", "original", "creamy", "ranch",
        }
    if form == "green_beans":
        terms |= title_tokens & {"green", "bean", "beans", "snap", "string", "french", "cut"}
    if form in {"cream_cheese", "cheese_food", "cheese"}:
        terms |= title_tokens & {
            "american", "cheddar", "cheese", "cream", "feta", "food",
            "light", "plain", "salsa", "swiss", "wedge", "wedges",
        }
    if form in {"chicken_nuggets", "chicken_strips", "chicken_wings", "popcorn_chicken", "canned_chicken"}:
        terms |= title_tokens & {
            "chicken", "nugget", "nuggets", "strip", "strips", "tender",
            "tenders", "wing", "wings", "nibbler", "nibblers", "popcorn",
            "chunk", "water", "canned", "cooked", "fully", "spicy", "hot",
        }
    if form in {
        "corn_dog", "quesadilla", "pot_pie", "bologna", "mac_and_cheese",
        "pierogi", "rice_dish", "quinoa_dish", "scalloped_potatoes",
        "potato_slices", "potatoes", "vegetable_appetizer", "ravioli",
        "tortellini", "crescent_roll", "dinner_roll", "sandwich_roll",
        "cinnamon_roll", "wonton",
    }:
        terms |= normalize_food_tokens(title_tokens) & ({
            "corn", "dog", "corndog", "quesadilla", "pot", "pie", "bologna",
            "chicken", "beef", "pork", "turkey", "mac", "macaroni", "cheese",
            "pierogi", "rice", "quinoa", "potato", "scalloped", "slice",
            "dehydrated", "vegetable", "broccoli", "carrot", "onion",
            "ravioli", "tortellini", "sage",
            "crescent", "dinner", "sandwich", "cinnamon", "wonton", "shrimp",
            "roll", "sourdough",
        } | FILLED_PASTA_FILLING_TERMS)
    if form in {"shrimp", "crab", "clam", "scallop", "lobster", "oyster", "mussel", "cod", "haddock", "flounder", "salmon", "tuna", "fish"}:
        terms |= normalize_food_tokens(title_tokens) & (SEAFOOD_FORM_TERMS | {"stuffed", "tail", "salad", "raw", "cooked"})
    if form in {"water", "sparkling_water", "seltzer"}:
        terms |= normalize_food_tokens(title_tokens) & (WATER_FLAVOR_TERMS | {"water", "sparkling", "seltzer"})
    if form in {"hot_cocoa", "drink_mix", "cocktail_mix", "bloody_mary_mix", "kombucha", "drinkable_yogurt", "probiotic_drink"}:
        terms |= normalize_food_tokens(title_tokens) & {
            "hot", "cocoa", "mix", "powder", "powdered", "margarita", "cocktail",
            "bloody", "mary", "kombucha", "jun", "yogurt", "oatgurt", "probiotic",
            "blueberry", "cherry", "lime", "caramel", "salt", "candy", "cane",
        }
    if form in {"milk", "plant_milk", "buttermilk", "kefir", "eggnog", "flavored_milk"}:
        terms |= normalize_food_tokens(title_tokens) & (MILK_SUBTYPE_TERMS | {"milk"})
    if form in {"carrot", "produce_vegetable"}:
        terms |= normalize_food_tokens(title_tokens) & (PRODUCE_VEGETABLE_TERMS | {"fresh", "baby", "cut", "stick", "spiral", "noodle", "shredded", "chopped", "peeled"})
    if form in {"egg_salad", "coleslaw", "whitefish_salad", "tuna_salad", "potato_salad", "macaroni_salad", "salad"}:
        terms |= normalize_food_tokens(title_tokens) & (SALAD_SUBTYPE_TERMS | {"salad", "coleslaw"})
    if form in {"jelly", "jam", "spread"}:
        terms |= normalize_food_tokens(title_tokens) & (SPREAD_FLAVOR_TERMS | {"jelly", "jam", "preserve", "concord", "grape", "spread"})
    if form in {"whipped_topping", "decorative_topping"}:
        terms |= normalize_food_tokens(title_tokens) & {"whipped", "topping", "peppermint", "sprinkle", "crunch", "candy", "decorative"}
    if form in {"pasta", "noodles"}:
        terms |= title_tokens & {
            "pasta", "noodle", "noodles", "spaghetti", "macaroni", "penne",
            "rigatoni", "fettuccine", "lasagna", "ravioli", "linguine",
        }
    if not terms:
        terms = (set(title_tokens) | set(ingredient_tokens)) - GENERIC_IDENTITY - FORM_TOKENS
    return tuple(sorted(t for t in terms if len(t) > 1))


def target_heads_for(lane: str, form: str, role: str, title_tokens: set[str]) -> tuple[str, ...]:
    if form == "pizza_bagel":
        return ("Pizza",)
    if form == "pizza":
        return ("Pizza",)
    if form == "pizza_dough":
        return ("Pizza Crust", "Crust")
    if form in {"veggie_burger", "burger"}:
        return ("Vegetarian Meat", "Meal", "Dish", "Sandwich")
    if form == "dressing":
        return ("Salad Dressing", "Dressing", "Sauce")
    if form in {"oatmeal", "granola", "cereal"}:
        return ("Cereal",)
    if form == "mashed_potatoes":
        return ("Mashed Potatoes",)
    if form == "yogurt":
        return ("Yogurt",)
    if form == "yogurt_smoothie":
        return ("Yogurt", "Smoothie", "Drink")
    if form == "yogurt_parfait":
        return ("Parfait", "Yogurt")
    if form == "ice_cream":
        return ("Ice Cream",)
    if form == "frozen_dessert":
        return ("Ice Cream", "Yogurt", "Pudding")
    if form == "glucose":
        return ("Glucose", "Glucose Gel", "Sugar", "Sweetener")
    if form == "plant_milk":
        return ("Soy Milk", "Almond Milk", "Oat Milk", "Coconut Milk", "Cream Substitute")
    if form == "buttermilk":
        return ("Buttermilk",)
    if form == "kefir":
        return ("Kefir",)
    if form == "eggnog":
        return ("Eggnog", "Eggnog Substitute")
    if form == "flavored_milk":
        return ("Milk", "Milk Shake", "Drink")
    if form == "milk":
        return ("Milk",)
    if lane == "juice":
        return ("Juice", "Juice Drink", "Smoothie", "Drink")
    if lane == "water":
        return ("Water", "Drink")
    if lane == "cracker":
        return ("Cracker", "Biscuit")
    if lane == "oil":
        return ("Oil",)
    if lane == "grain":
        return ("Cereal", "Rice", "Wheat", "Flour")
    if form in {"beans", "refried_beans"}:
        return ("Beans",)
    if form == "green_beans":
        return ("Beans", "Vegetables")
    if form == "bean_dish":
        return ("Dish", "Meal", "Vegetables", "Beans & Rice")
    if form == "baked_beans":
        return ("Baked Beans", "Beans")
    if form == "baking_powder":
        return ("Baking Powder",)
    if form == "baking_soda":
        return ("Baking Soda",)
    if form in {"baking_mix", "cake_mix", "cookie_mix", "bread_mix", "bar_mix", "roll_mix"}:
        return {
            "baking_mix": ("Baking Mix", "Cake", "Cookie", "Muffin", "Pancakes", "Waffles"),
            "cake_mix": ("Cake", "Baking Mix"),
            "cookie_mix": ("Cookie", "Cookies", "Baking Mix"),
            "bread_mix": ("Bread", "Baking Mix"),
            "bar_mix": ("Bar", "Baking Mix", "Cake"),
            "roll_mix": ("Roll", "Sweet Roll", "Baking Mix"),
        }[form]
    if form == "brownie_mix":
        return ("Brownie", "Cake", "Baking Mix")
    if form == "cookie":
        return ("Cookie", "Cookies", "Biscuit", "Cracker")
    if form in {"cake", "pie", "pudding", "dessert"}:
        return {
            "cake": ("Cake",),
            "pie": ("Pie",),
            "pudding": ("Pudding",),
            "dessert": ("Dessert", "Cake", "Pie", "Pudding", "Ice Cream", "Cookie"),
        }[form]
    if form == "brownie":
        return ("Brownie",)
    if form == "bar":
        return ("Bar",)
    if form == "chicken_nuggets":
        return ("Nuggets",)
    if form == "chicken_strips":
        return ("Strips", "Chicken")
    if form == "chicken_wings":
        return ("Hot Wings", "Chicken")
    if form == "popcorn_chicken":
        return ("Popcorn Chicken",)
    if form == "canned_chicken":
        return ("Chicken",)
    if form == "corn_dog":
        return ("Corn Dog",)
    if form == "quesadilla":
        return ("Quesadilla",)
    if form == "pot_pie":
        return ("Pot Pie",)
    if form == "bologna":
        return ("Lunchmeat",)
    if form == "mac_and_cheese":
        return ("Macaroni & Cheese", "Macaroni and Cheese")
    if form == "pierogi":
        return ("Pierogi",)
    if form == "ravioli":
        return ("Ravioli",)
    if form == "tortellini":
        return ("Tortellini",)
    if form in {"crescent_roll", "dinner_roll", "sandwich_roll"}:
        return ("Roll",)
    if form == "cinnamon_roll":
        return ("Sweet Roll",)
    if form == "wonton":
        return ("Wonton", "Wrappers")
    if form == "rice_dish":
        return ("Rice Dish", "Dish")
    if form == "quinoa_dish":
        return ("Quinoa", "Dish", "Meal")
    if form == "scalloped_potatoes":
        return ("Casserole",)
    if form in {"potato_slices", "potatoes"}:
        return ("Potatoes",)
    if form == "snack_mix":
        return ("Snack", "Nuts", "Seeds", "Trail Mix")
    if form == "popcorn":
        return ("Popcorn",)
    if form in {"seeds", "nuts", "chips", "pretzels", "snack"}:
        return {
            "seeds": ("Seeds", "Nuts", "Snack"),
            "nuts": ("Nuts", "Seeds", "Snack"),
            "chips": ("Chips", "Snack"),
            "pretzels": ("Pretzels", "Snack"),
            "snack": ("Snack", "Chips", "Cracker", "Pretzels", "Nuts", "Seeds"),
        }[form]
    if form == "doughnut":
        return ("Doughnut",)
    if form == "biscuit":
        return ("Biscuit",)
    if form in {"sandwich", "wrap", "burrito"}:
        return (form.title(), "Meal", "Dish")
    if form == "pasta_dish":
        return ("Pasta Dish", "Meal", "Dish")
    if form in {"taco", "tamale", "bowl"}:
        return ("Meal", "Dish")
    if form == "poultry_bacon":
        return ("Bacon",)
    if form in {"chicken", "turkey", "pork", "beef", "ham", "sausage"}:
        return (form.title(), "Meal", "Dish", "Sausage")
    if form == "cream_cheese":
        return ("Cream Cheese",)
    if form == "cheese_food":
        return ("Cheese Food", "Cheese")
    if form == "cheese":
        return ("Cheese",)
    if form == "nut_butter":
        return ("Nut Butter", "Peanut Butter")
    if form in {"jelly", "jam"}:
        return ("Jelly", "Jam", "Jam/Preserves")
    if form == "spread":
        return ("Spread", "Jelly", "Jam", "Nut Butter")
    if form in {"dessert_topping", "whipped_topping", "decorative_topping"}:
        return ("Dessert Topping", "Topping", "Sauce", "Syrup")
    if form == "shake":
        return ("Shake", "Drink")
    if form in {
        "soda", "tea", "coffee", "juice", "smoothie", "drink", "water",
        "sparkling_water", "seltzer", "drink_mix", "hot_cocoa",
        "cocktail_mix", "bloody_mary_mix", "kombucha", "drinkable_yogurt",
        "probiotic_drink",
    }:
        return {
            "soda": ("Soda", "Drink"),
            "tea": ("Tea", "Drink"),
            "coffee": ("Coffee", "Drink"),
            "juice": ("Juice", "Juice Drink", "Smoothie", "Drink"),
            "smoothie": ("Smoothie", "Juice", "Drink"),
            "drink": ("Drink", "Juice", "Juice Drink", "Smoothie", "Tea", "Coffee", "Soda", "Water"),
            "water": ("Water", "Drink"),
            "sparkling_water": ("Water", "Drink"),
            "seltzer": ("Water", "Drink"),
            "drink_mix": ("Drink",),
            "hot_cocoa": ("Hot Cocoa",),
            "cocktail_mix": ("Cocktail Mix", "Mixer", "Drink"),
            "bloody_mary_mix": ("Mixer", "Cocktail Mix", "Drink"),
            "kombucha": ("Kombucha", "Tea", "Drink"),
            "drinkable_yogurt": ("Yogurt", "Drink"),
            "probiotic_drink": ("Drink", "Yogurt"),
        }[form]
    if form in {"pickles", "olives", "relish", "peppers"}:
        return {
            "pickles": ("Pickles",),
            "olives": ("Olives",),
            "relish": ("Relish",),
            "peppers": ("Pepper", "Peppers", "Chili Pepper", "Chili Peppers"),
        }[form]
    if form in {"pasta", "noodles", "quinoa"}:
        return {
            "pasta": ("Pasta", "Noodles", "Macaroni"),
            "noodles": ("Pasta", "Noodles", "Macaroni"),
            "quinoa": ("Quinoa",),
        }[form]
    if form in {"ketchup", "mustard", "sauce", "barbecue_sauce", "hot_sauce", "butter_sauce", "pasta_sauce", "horseradish"}:
        return {
            "ketchup": ("Ketchup", "Sauce"),
            "mustard": ("Mustard", "Sauce"),
            "sauce": ("Sauce", "Ketchup", "Mustard"),
            "barbecue_sauce": ("Sauce",),
            "hot_sauce": ("Sauce",),
            "butter_sauce": ("Sauce",),
            "pasta_sauce": ("Sauce",),
            "horseradish": ("Sauce", "Spice"),
        }[form]
    if form == "pumpkin":
        return ("Pumpkin",) if lane == "vegetable" else LANE_HEADS.get(lane, ())
    if form in {"tomatoes", "tomato_sauce", "tomato_vegetable_mix", "vegetable"}:
        return {
            "tomatoes": ("Tomato", "Tomatoes", "Tomato Sauce", "Tomato Paste"),
            "tomato_sauce": ("Tomato Sauce", "Sauce"),
            "tomato_vegetable_mix": ("Dish", "Vegetables", "Tomato", "Tomatoes"),
            "vegetable": ("Vegetables",),
        }[form]
    if form == "carrot":
        return ("Carrot",)
    if form == "produce_vegetable":
        return ("Vegetables", "Carrot", "Squash", "Kale", "Celery")
    if form == "gum":
        return ("Gum", "Chewing Gum")
    if form == "peanut_butter_cup":
        return ("Candy", "Chocolate", "Candy Bar")
    if form == "candy":
        return ("Candy", "Chocolate", "Chocolate Bar", "Candy Bar", "Gum")
    if form in {"shrimp", "crab", "lobster"}:
        return (form.title(),)
    if form in {"clam", "scallop", "oyster", "mussel"}:
        return ("Mollusks", "Dish")
    if form in {"cod", "haddock", "flounder", "salmon", "tuna", "fish"}:
        return ("Fish",)
    if form == "rice":
        return ("Rice", "Rice Dish", "Rice & Beans")
    if form in {"egg_salad", "potato_salad", "macaroni_salad", "tuna_salad", "whitefish_salad", "salad"}:
        return ("Salad",)
    if form == "coleslaw":
        return ("Coleslaw", "Salad")
    if form == "chowder":
        return ("Chowder", "Soup")
    if form == "bouillon":
        return ("Bouillon", "Broth", "Base")
    if form == "seasoning":
        return ("Seasoning", "Spice", "Sauce", "Base")
    if form == "chili":
        return ("Chili", "Soup")
    if form == "stew":
        return ("Stew", "Soup", "Dish")
    if form == "butter":
        return ("Butter", "Butter Substitute")
    if form == "sugar":
        return ("Sugar", "Sweetener")
    if form == "cream":
        return ("Cream", "Cream Substitute")
    if form == "protein_drink":
        return ("Drink", "Shake")
    if form in matcher.FRUITS:
        return (form.title(), "Fruit")
    if role == "flavor" and "vanilla_bean" in form:
        if lane == "cereal":
            return ("Cereal",)
        if lane == "yogurt":
            return ("Yogurt",)
        if lane == "frozen_dessert":
            return ("Ice Cream", "Yogurt", "Pudding")
        if lane == "creamer":
            return ("Cream Substitute", "Coffee", "Drink")
    return LANE_HEADS.get(lane, ())


def build_product_facts(current_map: pd.DataFrame | None = None) -> pd.DataFrame:
    products = ingredient_clusters.load_products()
    if current_map is not None:
        key = "fdc_id" if "fdc_id" in current_map.columns else "gtin_upc"
        cols = [key] + [
            c
            for c in (
                "best_esha_code", "best_esha_description", "best_esha_family",
                "score", "n_candidates", "assignment_source",
            )
            if c in current_map.columns
        ]
        products = products.merge(current_map[cols].drop_duplicates(key, keep="first"), on=key, how="left")

    rows: list[dict[str, object]] = []
    for _, row in products.iterrows():
        desc = str(row.get("product_description") or "")
        category = str(row.get("branded_food_category") or "")
        title = set(ingredient_clusters.title_tokens(desc))
        ingredients = set(ingredient_clusters.tokenize_ingredients(str(row.get("ingredients") or "")))
        lane = category_lane_for(desc, category, title)
        form = product_form_for(desc, category, lane, title)
        role = role_for(desc, lane, form, title)
        identity = identity_terms_for(title, ingredients, form, role)
        heads = target_heads_for(lane, form, role, title)
        product_family = ingredient_clusters.product_family_for(desc, category, tuple(title))
        primary = ingredient_clusters.primary_food(tuple(title))
        state = ingredient_clusters.state_lane(desc, category, tuple(title))
        ingredient_key = ingredient_clusters.ingredient_key(tuple(sorted(ingredients)))
        profile_key = ingredient_clusters.ingredient_profile_key(tuple(sorted(ingredients)), product_family, primary)
        cluster_basis = (
            lane,
            form,
            " ".join(identity[:8]),
            profile_key or ingredient_key[:240],
        )
        rows.append(
            {
                "gtin_upc": row.get("gtin_upc", ""),
                "fdc_id": row.get("fdc_id", ""),
                "product_description": desc,
                "branded_food_category": category,
                "brand_owner": row.get("brand_owner", ""),
                "brand_name": row.get("brand_name", ""),
                "category_lane": lane,
                "product_form": form,
                "product_role": role,
                "identity_terms": " ".join(identity),
                "target_heads": "|".join(heads),
                "product_family_hint": product_family,
                "primary_food": primary,
                "state_lane": state,
                "ingredient_signature": ingredient_key,
                "ingredient_profile_signature": profile_key,
                "cluster_key": ingredient_clusters.cluster_id_for(tuple(str(v) for v in cluster_basis)),
                "policy_version": SELF_HEAL_POLICY_VERSION,
                "title_tokens": " ".join(sorted(title)),
                "ingredient_tokens": " ".join(sorted(ingredients)),
                **{
                    c: row.get(c, "")
                    for c in (
                        "best_esha_code", "best_esha_description", "best_esha_family",
                        "score", "n_candidates", "assignment_source",
                    )
                    if c in row.index
                },
            }
        )
    return pd.DataFrame(rows)


def build_esha_facts(
    candidates: dict[str, full_map.Candidate] | None = None,
) -> pd.DataFrame:
    if candidates is None:
        candidates, _category_to_codes, _family_to_codes, _idf = full_map.build_candidates()
    rows = []
    for code, candidate in candidates.items():
        head = esha_head(candidate.description)
        rows.append(
            {
                "esha_code": code,
                "esha_description": candidate.description,
                "esha_head": head,
                "esha_head_norm": norm_head(head),
                "esha_family": candidate.family,
                "identity_terms": " ".join(sorted(candidate.identity_terms)),
                "meaningful_terms": " ".join(sorted(candidate.meaningful_terms)),
                "category_support": candidate.category_support,
                "needs_fix": int(candidate.needs_fix),
                "categories": " | ".join(sorted(candidate.categories)[:20]),
            }
        )
    return pd.DataFrame(rows)


def build_head_index(candidates: dict[str, full_map.Candidate]) -> dict[str, list[str]]:
    index: dict[str, list[str]] = defaultdict(list)
    for code, candidate in candidates.items():
        index[norm_head(esha_head(candidate.description))].append(code)
    return dict(index)


def head_norms_for_targets(target_heads: Iterable[str]) -> set[str]:
    return policy.head_norms_for_targets(target_heads)


def head_compatible(target_heads: Iterable[str], esha_head_value: str) -> bool:
    return policy.head_matches_targets(target_heads, esha_head_value)


def broad_head_identity_mismatch(
    *,
    esha_head_value: str,
    anchor_identity_terms: Iterable[str],
    anchor_tokens: Iterable[str] = (),
    product_evidence: set[str],
) -> str | None:
    """Broad heads are only safe when the leaf identity overlaps the product.

    A head like "Drink" or "Dish" can be structurally legal for many categories,
    but that does not mean "Drink, protein, whey chocolate" is legal for cucumber
    lemon juice. This guard keeps broad heads from becoming attractors.
    """
    h = norm_head(esha_head_value)
    if h not in BROAD_HEADS_NEED_IDENTITY:
        return None
    anchor_identity = {
        t
        for t in anchor_identity_terms
        if t and t not in GENERIC_IDENTITY and t not in FORM_TOKENS and t not in BROAD_IDENTITY_NOISE and len(t) > 1
    }
    if not anchor_identity:
        anchor_identity = {
            t
            for t in anchor_tokens
            if t and t not in GENERIC_IDENTITY and t not in FORM_TOKENS and t not in BROAD_IDENTITY_NOISE and len(t) > 1
        }
    if not anchor_identity:
        return None
    if product_evidence & anchor_identity:
        return None
    return f"broad_head_identity_mismatch:{esha_head_value}"


def missing_meal_components(candidate_description: str, product_evidence: set[str]) -> set[str]:
    """Return major meal components present in candidate but absent from product."""
    candidate_terms = {t for t in re.split(r"[^a-z0-9]+", norm_text(candidate_description)) if t}
    normalized_evidence = set(product_evidence)
    if "potato" in normalized_evidence:
        normalized_evidence.add("potatoes")
    if "potatoes" in normalized_evidence:
        normalized_evidence.add("potato")
    if "noodle" in normalized_evidence:
        normalized_evidence.add("noodles")
    if "noodles" in normalized_evidence:
        normalized_evidence.add("noodle")
    if "biscuit" in normalized_evidence:
        normalized_evidence.add("biscuits")
    if "biscuits" in normalized_evidence:
        normalized_evidence.add("biscuit")
    return (candidate_terms & MEAL_COMPONENT_TERMS) - normalized_evidence


def bean_subtypes_from_text(text: str, terms: set[str]) -> set[str]:
    """Detect bean subtype identities without confusing flavor words for beans."""
    n = norm_text(text)
    out: set[str] = set()
    phrase_map = {
        "green": ("green bean", "green beans", "string bean", "string beans", "snap bean", "snap beans"),
        "black": ("black bean", "black beans"),
        "pinto": ("pinto bean", "pinto beans"),
        "kidney": ("kidney bean", "kidney beans"),
        "garbanzo": ("garbanzo bean", "garbanzo beans", "chickpea", "chickpeas"),
        "great_northern": ("great northern bean", "great northern beans"),
        "navy": ("navy bean", "navy beans"),
        "red": ("red bean", "red beans"),
        "butter": ("butter bean", "butter beans", "lima bean", "lima beans"),
        "baked": ("baked bean", "baked beans"),
        "refried": ("refried bean", "refried beans"),
    }
    for subtype, phrases in phrase_map.items():
        if any(phrase in n for phrase in phrases):
            out.add(subtype)
    if "black" in terms and ({"bean", "beans"} & terms):
        out.add("black")
    if "pinto" in terms and ({"bean", "beans"} & terms):
        out.add("pinto")
    if "kidney" in terms and ({"bean", "beans"} & terms):
        out.add("kidney")
    if "garbanzo" in terms or "chickpea" in terms or "chickpeas" in terms:
        out.add("garbanzo")
    return out


def code_pool_for_heads(
    target_heads: Iterable[str],
    head_index: dict[str, list[str]],
    candidates: dict[str, full_map.Candidate],
) -> list[str]:
    target_norms = head_norms_for_targets(target_heads)
    seen: set[str] = set()
    out: list[str] = []
    for head_norm, codes in head_index.items():
        if head_norm not in target_norms:
            continue
        for code in codes:
            if code in candidates and code not in seen:
                seen.add(code)
                out.append(code)
    return out


def product_fact_map(product_facts: pd.DataFrame) -> dict[str, pd.Series]:
    return {str(r["fdc_id"]): r for _, r in product_facts.iterrows()}


def esha_fact_map(esha_facts: pd.DataFrame) -> dict[str, pd.Series]:
    return {str(r["esha_code"]): r for _, r in esha_facts.iterrows()}


def current_assignment_decision(
    feature_row: pd.Series,
    fact_row: pd.Series,
    anchor: ingredient_clusters.EshaAnchor | None,
) -> tuple[str, str]:
    code = str(feature_row.get("best_esha_code") or "").split(".")[0].strip()
    if not code:
        return "missing_leaf", "no_current_assignment"
    if anchor is None:
        return "rejected_incompatible", "missing_esha_anchor"
    target_heads = str(fact_row.get("target_heads") or "").split("|")
    if not any(target_heads):
        return "kept_unconstrained", "no_target_heads_for_lane"
    head = esha_head(anchor.description)
    if not head_compatible(target_heads, head):
        return "rejected_incompatible", f"head_mismatch:{head}->allowed:{'|'.join(target_heads)}"
    title_tokens = set(split_terms(str(fact_row.get("title_tokens") or "")))
    category_ok, category_reason = policy.category_allows_head(
        category=str(fact_row.get("branded_food_category") or ""),
        product_description=str(fact_row.get("product_description") or ""),
        title_tokens=title_tokens,
        candidate_head=head,
    )
    if not category_ok:
        return "rejected_incompatible", category_reason
    narrow_reason = policy.narrow_head_requires_title_support(
        head,
        title_tokens,
        str(fact_row.get("product_description") or ""),
    )
    if narrow_reason:
        return "rejected_incompatible", narrow_reason
    form = str(fact_row.get("product_form") or "")
    strict_form_heads: dict[str, set[str]] = {
        "popcorn": {"popcorn"},
        "doughnut": {"doughnut"},
        "mashed_potatoes": {"mashed potatoes"},
        "pasta": {"pasta", "noodles", "macaroni"},
        "noodles": {"pasta", "noodles", "macaroni"},
        "green_beans": {"beans", "vegetables"},
        "baking_powder": {"baking powder"},
        "baking_soda": {"baking soda"},
    }
    strict_heads = strict_form_heads.get(form)
    if strict_heads and norm_head(head) not in strict_heads:
        return "rejected_incompatible", f"form_head_mismatch:{form}->{head}"
    sauce_reason = sauce_form_mismatch_reason(form, anchor.description)
    if sauce_reason:
        return "rejected_incompatible", sauce_reason
    evidence = (
        set(feature_row.get("_title_tokens") or ())
        | set(feature_row.get("_ingredient_tokens") or ())
        | set(split_terms(str(fact_row.get("identity_terms") or "")))
    )
    milk_evidence = set(split_terms(str(fact_row.get("title_tokens") or ""))) | set(
        split_terms(str(fact_row.get("identity_terms") or ""))
    )
    lane = str(fact_row.get("category_lane") or "")
    for form_reason in (
        water_flavor_mismatch_reason(lane, evidence, anchor.description),
        beverage_form_mismatch_reason(lane, form, evidence, anchor.description),
        soup_form_mismatch_reason(form, evidence, anchor.description),
        bouillon_form_mismatch_reason(form, evidence, anchor.description),
        tomato_form_mismatch_reason(form, evidence, anchor.description),
        cheese_form_mismatch_reason(form, evidence, anchor.description),
        milk_form_mismatch_reason(form, milk_evidence, anchor.description),
        produce_form_mismatch_reason(form, evidence, anchor.description),
        salad_form_mismatch_reason(form, evidence, anchor.description),
        seafood_form_mismatch_reason(form, evidence, anchor.description),
        poultry_form_mismatch_reason(form, evidence, anchor.description),
        prepared_form_mismatch_reason(form, evidence, anchor.description),
        spread_form_mismatch_reason(form, evidence, anchor.description),
        brownie_form_mismatch_reason(form, anchor.description),
    ):
        if form_reason:
            return "rejected_incompatible", form_reason
    if norm_head(head) == "drink" and (set(anchor.tokens) & {"protein", "whey", "egg"}) and not (evidence & {"protein", "whey", "egg"}):
        return "rejected_incompatible", "protein_drink_anchor_on_non_protein_product"
    broad_reason = broad_head_identity_mismatch(
        esha_head_value=head,
        anchor_identity_terms=anchor.identity_terms,
        anchor_tokens=anchor.tokens,
        product_evidence=evidence,
    )
    if broad_reason:
        return "rejected_incompatible", broad_reason
    broad_extra_identity = {
        t
        for t in anchor.identity_terms
        if t and t not in evidence and t not in GENERIC_IDENTITY and t not in FORM_TOKENS and t not in BROAD_IDENTITY_NOISE
    }
    if norm_head(head) in BROAD_HEADS_NEED_IDENTITY and broad_extra_identity:
        return "rejected_incompatible", "broad_head_unasked_identity:" + ",".join(sorted(broad_extra_identity))
    if norm_head(head) in {"meal", "dish", "bowl"}:
        missing_components = missing_meal_components(anchor.description, evidence)
        if missing_components:
            return "rejected_incompatible", "broad_meal_extra_components_absent:" + ",".join(sorted(missing_components))
    structural_reason = ingredient_clusters.form_mismatch_reason(feature_row, anchor, evidence)
    if structural_reason in ingredient_clusters.HARD_FORM_MISMATCH_REASONS:
        return "rejected_incompatible", structural_reason
    return "kept_compatible", "compatible_current_assignment"


def candidate_score(
    fact_row: pd.Series | dict[str, object],
    candidate: full_map.Candidate,
    idf: dict[str, float],
) -> tuple[float, str] | None:
    target_heads = fact_row.get("_target_heads")
    if target_heads is None:
        target_heads = str(fact_row.get("target_heads") or "").split("|")
    head = esha_head(candidate.description)
    if not head_compatible(target_heads, head):
        return None
    title_terms = fact_row.get("_title_terms")
    if title_terms is None:
        title_terms = set(split_terms(str(fact_row.get("title_tokens") or "")))
    ingredient_terms = fact_row.get("_ingredient_terms")
    if ingredient_terms is None:
        ingredient_terms = set(split_terms(str(fact_row.get("ingredient_tokens") or "")))
    identity_terms = fact_row.get("_identity_terms")
    if identity_terms is None:
        identity_terms = set(split_terms(str(fact_row.get("identity_terms") or "")))
    evidence = fact_row.get("_evidence")
    if evidence is None:
        evidence = title_terms | ingredient_terms | identity_terms
    category_ok, _category_reason = policy.category_allows_head(
        category=str(fact_row.get("branded_food_category") or ""),
        product_description=str(fact_row.get("product_description") or ""),
        title_tokens=title_terms,
        candidate_head=head,
    )
    if not category_ok:
        return None
    if policy.narrow_head_requires_title_support(head, title_terms, str(fact_row.get("product_description") or "")):
        return None
    meaningful = set(candidate.meaningful_terms)
    cand_identity = set(candidate.identity_terms)
    form = str(fact_row.get("product_form") or "")
    lane = str(fact_row.get("category_lane") or "")
    h_norm = norm_head(head)
    candidate_tokens = _tokens_for_description(candidate.description)
    product_tokens = fact_row.get("_product_tokens")
    if product_tokens is None:
        product_tokens = normalize_food_tokens(evidence)
    if form == "cream_cheese" and h_norm == "cream cheese":
        meaningful |= {"cream", "cheese"}
        cand_identity |= {"cream", "cheese"}
    if form == "cheese_food" and h_norm == "cheese food":
        meaningful |= {"cheese", "food"}
        cand_identity |= {"cheese", "food"}
    if form in {"ravioli", "tortellini"} and h_norm == form:
        filled_pasta_terms = candidate_tokens & (FILLED_PASTA_FILLING_TERMS | {form})
        meaningful |= filled_pasta_terms
        cand_identity |= filled_pasta_terms
    if form in {"milk", "plant_milk", "buttermilk", "kefir", "flavored_milk", "eggnog"} and h_norm in {
        "milk", "soy milk", "almond milk", "oat milk", "coconut milk",
        "cream substitute", "buttermilk", "kefir", "eggnog", "eggnog substitute",
    }:
        milk_candidate_terms = candidate_tokens & (MILK_SUBTYPE_TERMS | {"milk"})
        if h_norm == "soy milk":
            milk_candidate_terms |= {"soy", "soymilk", "milk"}
        elif h_norm in {"almond milk", "oat milk", "coconut milk"}:
            milk_candidate_terms |= set(h_norm.split())
        elif h_norm == "cream substitute" and "coconut" in candidate_tokens and "milk" in candidate_tokens:
            milk_candidate_terms |= {"coconut", "milk"}
        elif h_norm == "buttermilk":
            milk_candidate_terms |= {"buttermilk", "butter", "milk", "cultured"}
        elif h_norm == "kefir":
            milk_candidate_terms |= {"kefir"} | (candidate_tokens & KEFIR_FLAVOR_TERMS)
        elif h_norm in {"eggnog", "eggnog substitute"}:
            milk_candidate_terms |= {"eggnog", "nog"}
        else:
            milk_candidate_terms |= {"milk"}
        milk_candidate_terms |= candidate_tokens & (
            MILK_FLAVOR_TERMS | MILK_FUNCTIONAL_VARIANT_TERMS | MILK_CULTURE_TERMS | {"unsweetened", "sweetened", "plain"}
        )
        meaningful |= milk_candidate_terms
        cand_identity |= milk_candidate_terms
    if form == "bouillon" and h_norm in BOUILLON_HEADS:
        bouillon_candidate_terms = set(candidate_tokens & BOUILLON_IDENTITY_TERMS)
        if h_norm in {"bouillon", "broth", "base"}:
            bouillon_candidate_terms.add(h_norm)
        meaningful |= bouillon_candidate_terms
        cand_identity |= bouillon_candidate_terms
    if water_flavor_mismatch_reason(lane, evidence, candidate.description):
        return None
    if beverage_form_mismatch_reason(lane, form, evidence, candidate.description):
        return None
    if soup_form_mismatch_reason(form, evidence, candidate.description):
        return None
    if bouillon_form_mismatch_reason(form, evidence, candidate.description):
        return None
    if tomato_form_mismatch_reason(form, evidence, candidate.description):
        return None
    if cheese_form_mismatch_reason(form, evidence, candidate.description):
        return None
    milk_evidence = title_terms | identity_terms
    if milk_form_mismatch_reason(form, milk_evidence, candidate.description):
        return None
    if produce_form_mismatch_reason(form, evidence, candidate.description):
        return None
    if salad_form_mismatch_reason(form, evidence, candidate.description):
        return None
    if seafood_form_mismatch_reason(form, evidence, candidate.description):
        return None
    if poultry_form_mismatch_reason(form, evidence, candidate.description):
        return None
    prepared_evidence = evidence
    if form in {"ravioli", "tortellini", "wonton"}:
        prepared_evidence = title_terms | identity_terms
    if prepared_form_mismatch_reason(form, prepared_evidence, candidate.description):
        return None
    if spread_form_mismatch_reason(form, evidence, candidate.description):
        return None
    if brownie_form_mismatch_reason(form, candidate.description):
        return None
    if form == "doughnut" and ("doughnut" in meaningful or "doughnut" in cand_identity):
        meaningful |= {"donut", "donuts", "doughnuts"}
        cand_identity |= {"donut", "donuts", "doughnuts"}
    if norm_head(head) == "drink" and (meaningful | cand_identity) & {"protein", "whey", "egg"} and not evidence & {"protein", "whey", "egg"}:
        return None
    if norm_head(head) in {"meal", "dish", "bowl"} and missing_meal_components(candidate.description, evidence):
        return None
    if form in (SEAFOOD_FORM_TERMS | {"fish"}):
        unasked_seafood_states = {
            "dried", "dry", "breaded", "fried", "batter", "battered",
            "canned", "can", "drained", "imitation", "surimi",
        }
        if (candidate_tokens & unasked_seafood_states) and not (product_tokens & unasked_seafood_states):
            return None
    title_hits = title_terms & meaningful
    ingredient_hits = ingredient_terms & meaningful
    identity_hits = evidence & cand_identity
    extra_identity = cand_identity - evidence - GENERIC_IDENTITY - {"dry", "fs", "serving", "prepared"}
    if form == "doughnut":
        extra_identity -= {
            "doughnut", "doughnuts", "donut", "donuts", "cake", "raised",
            "enriched", "medium", "large", "small", "rich",
        }
    if form == "popcorn":
        extra_identity -= {"popcorn", "popped", "unpopped", "microwaved", "snack", "serving"}
    if form == "pizza_dough":
        extra_identity -= {"pizza", "crust", "dough", "grain", "wheat", "whole", "dry", "frozen"}
    if form == "mashed_potatoes":
        extra_identity -= {"mashed", "mash", "potato", "potatoes", "dry", "prepared", "serving"}
    if form in {"milk", "plant_milk", "buttermilk", "kefir", "flavored_milk", "eggnog"}:
        extra_identity = {
            t
            for t in extra_identity
            if t in (MILK_SUBTYPE_TERMS | KEFIR_FLAVOR_TERMS) and t not in {"vitamin", "added"}
        }
    if form == "bouillon":
        extra_identity -= BOUILLON_IDENTITY_TERMS | {"prepared", "serving", "fs", "msg", "added"}
    if form in {"carrot", "produce_vegetable"}:
        extra_identity -= PRODUCE_VEGETABLE_TERMS | {"fresh", "baby", "cut", "peeled", "whole", "organic"}
    if form in {"egg_salad", "coleslaw", "whitefish_salad", "tuna_salad", "potato_salad", "macaroni_salad", "salad"}:
        extra_identity -= SALAD_SUBTYPE_TERMS | {"salad", "coleslaw", "fs"}
    if h_norm in {"beans", "baked beans", "beans rice", "beans and rice"} or form in {"beans", "baked_beans", "refried_beans", "green_beans"}:
        product_text = str(fact_row.get("product_description") or "")
        product_subtypes = bean_subtypes_from_text(product_text, title_terms | identity_terms)
        candidate_subtypes = bean_subtypes_from_text(candidate.description, meaningful | cand_identity)
        if form == "green_beans" and "green" not in candidate_subtypes:
            return None
        if form == "baked_beans" and h_norm != "baked beans" and "baked" not in candidate_subtypes:
            return None
        if form == "refried_beans" and "refried" not in candidate_subtypes and "refried" not in norm_text(candidate.description):
            return None
        if product_subtypes and candidate_subtypes and not (product_subtypes & candidate_subtypes):
            return None
    target_head_norms = fact_row.get("_target_head_norms")
    if target_head_norms is None:
        target_head_norms = head_norms_for_targets(target_heads)
    head_exact = norm_head(head) in target_head_norms

    score = 0.0
    score += 18.0 if head_exact else 12.0
    score += 4.5 * len(title_hits)
    score += 4.0 * len(identity_hits)
    score += 1.2 * len(ingredient_hits)
    score += sum(idf.get(t, 1.0) for t in title_hits)
    score += 0.25 * math.log1p(candidate.category_support)
    score -= 1.6 * len(extra_identity)
    if candidate.needs_fix:
        score -= 2.5

    lane = str(fact_row.get("category_lane") or "")
    if lane in " ".join(sorted(candidate.categories)):
        score += 1.5
    if form.replace("_", " ") in norm_text(candidate.description):
        score += 3.0
    if form == "pizza_bagel" and "bagel" in candidate.meaningful_terms and norm_head(head) == "pizza":
        score += 6.0
    if form in {"veggie_burger", "burger"} and {"burger", "vegetarian"} & meaningful:
        score += 5.0
    if form == "dressing" and {"dressing", "ranch", "vinaigrette"} & meaningful:
        score += 5.0
    if form == "popcorn":
        if norm_head(head) != "popcorn":
            return None
        if "butter" in evidence and "butter" not in meaningful:
            return None
        if "kettle" in evidence and not (meaningful & {"kettle", "korn", "corn"}):
            return None
        if (evidence & {"cheddar", "cheese"}) and not (meaningful & {"cheddar", "cheese"}):
            return None
        score += 8.0
    if form == "pizza_dough":
        if norm_head(head) not in {"crust", "pizza crust"}:
            return None
        if "pizza" not in norm_text(candidate.description):
            return None
        score += 8.0
    if form == "doughnut":
        if norm_head(head) != "doughnut":
            return None
        cand_text = norm_text(candidate.description)
        title_subtype_evidence = title_terms | identity_terms
        required_subtypes = {
            "cinnamon": ("cinnamon", "cinn"),
            "powdered": ("powdered", "powder"),
            "chocolate": ("chocolate",),
            "frosted": ("frosted", "iced"),
            "glazed": ("glazed",),
            "jelly": ("jelly",),
            "cream": ("cream", "creme", "kreme", "custard"),
            "creme": ("cream", "creme", "kreme", "custard"),
            "custard": ("custard", "cream", "creme", "kreme"),
            "blueberry": ("blueberry",),
            "pumpkin": ("pumpkin",),
            "apple": ("apple",),
        }
        for subtype, aliases in required_subtypes.items():
            if subtype in title_subtype_evidence and not any(alias in cand_text for alias in aliases):
                return None
        unasked_subtypes = 0
        for subtype, aliases in required_subtypes.items():
            if subtype not in title_subtype_evidence and any(alias in cand_text for alias in aliases):
                unasked_subtypes += 1
        score -= 5.0 * unasked_subtypes
        score += 8.0
    if form in {"brownie", "brownie_mix"}:
        cand_text = norm_text(candidate.description)
        if form == "brownie" and "frozen" in cand_text and "frozen" not in evidence:
            return None
        score += 10.0 if form == "brownie_mix" else 8.0
    if form == "peanut_butter_cup":
        cand_tokens = _tokens_for_description(candidate.description)
        if not ({"peanut", "butter"} <= cand_tokens and (cand_tokens & {"cup", "cups"})):
            return None
        score += 10.0
    if form == "dessert_topping":
        cand_tokens = _tokens_for_description(candidate.description)
        flavor_evidence = evidence & {"chocolate", "fudge", "toffee", "caramel", "strawberry"}
        if flavor_evidence and not (cand_tokens & flavor_evidence):
            return None
        score += 6.0
    if form == "mashed_potatoes":
        if norm_head(head) != "mashed potatoes":
            return None
        cand_text = norm_text(candidate.description)
        title_subtype_evidence = title_terms | identity_terms
        required_subtypes = {
            "garlic": ("garlic",),
            "butter": ("butter", "buttery"),
            "buttery": ("butter", "buttery"),
            "herb": ("herb",),
            "cheddar": ("cheddar", "cheese"),
            "cheese": ("cheese", "cheddar"),
            "instant": ("instant", "flake", "granule", "dry"),
            "loaded": ("loaded",),
            "ranch": ("ranch",),
        }
        for subtype, aliases in required_subtypes.items():
            if subtype in title_subtype_evidence and not any(alias in cand_text for alias in aliases):
                return None
        forbidden_components = {
            "chicken", "noodle", "noodles", "biscuit", "biscuits", "beef",
            "pork", "turkey", "steak", "meatloaf", "stuffing", "corn",
        }
        if forbidden_components & set(split_terms(cand_text)):
            return None
        score += 10.0
    if form in {"barbecue_sauce", "hot_sauce", "butter_sauce", "pasta_sauce", "horseradish"}:
        sauce_reason = sauce_form_mismatch_reason(form, candidate.description)
        if sauce_reason:
            return None
        if form == "horseradish" and "cream" in product_tokens and "cream" in candidate_tokens:
            score += 6.0
        score += 9.0
    if form in (SEAFOOD_FORM_TERMS | {"fish"}):
        if form == "shrimp" and product_tokens & {"salad", "cooked"} and candidate_tokens & {"cooked", "peeled", "deveined"}:
            score += 6.0
        if "tail" in product_tokens and "tail" in candidate_tokens:
            score += 4.0
        score += 7.0
    if form in {"milk", "plant_milk", "buttermilk", "kefir", "flavored_milk", "eggnog"}:
        if "whole" in product_tokens and "whole" in candidate_tokens:
            score += 10.0
        if "vitamin" in product_tokens and "vitamin" in candidate_tokens:
            score += 4.0
        if form == "plant_milk" and product_tokens & candidate_tokens & {"soy", "soymilk", "almond", "oat", "coconut"}:
            score += 8.0
        if form == "buttermilk" and "buttermilk" in candidate_tokens:
            score += 10.0
        if form == "buttermilk" and product_tokens & candidate_tokens & {"lowfat", "cultured", "percent"}:
            score += 4.0
        if form == "kefir":
            if norm_head(head) != "kefir":
                return None
            if "kefir" in candidate_tokens:
                score += 10.0
            if product_tokens & candidate_tokens & KEFIR_FLAVOR_TERMS:
                score += 4.0
        score += 4.0
    if form == "bouillon":
        if norm_head(head) not in BOUILLON_HEADS:
            return None
        if "bouillon" in candidate_tokens:
            score += 8.0
        if product_tokens & candidate_tokens & BOUILLON_FLAVOR_TERMS:
            score += 8.0
        if "cube" in product_tokens and "cube" in candidate_tokens:
            score += 8.0
        if product_tokens & candidate_tokens & {"instant", "powder", "powdered", "dry", "dried", "dehydrated", "granule"}:
            score += 3.0
        if "prepared" in candidate_tokens and "prepared" not in product_tokens:
            score -= 2.0
        score += 5.0
    if form in {"carrot", "produce_vegetable"}:
        if "fresh" in candidate_tokens or "fresh" in product_tokens:
            score += 3.0
        if product_tokens & candidate_tokens & PRODUCE_VEGETABLE_TERMS:
            score += 8.0
    if form in {"egg_salad", "coleslaw", "whitefish_salad", "tuna_salad", "potato_salad", "macaroni_salad", "salad"}:
        if product_tokens & candidate_tokens & SALAD_SUBTYPE_TERMS:
            score += 8.0
        if form == "coleslaw" and ("coleslaw" in candidate_tokens or {"cole", "slaw"} <= candidate_tokens):
            score += 8.0

    has_evidence = bool(title_hits or identity_hits or ingredient_hits)
    broad = norm_head(head) in {"meal", "dish", "snack", "drink", "fruit", "beans"}
    if not has_evidence:
        return None
    if broad and not (title_hits or identity_hits):
        return None
    if broad and extra_identity:
        return None
    if len(extra_identity) >= 4:
        return None
    reason = (
        f"head={head};title_hits={len(title_hits)};ingredient_hits={len(ingredient_hits)};"
        f"identity_hits={len(identity_hits)};extra_identity={len(extra_identity)}"
    )
    return score, reason


def choose_replacement(
    fact_row: pd.Series,
    candidates: dict[str, full_map.Candidate],
    head_index: dict[str, list[str]],
    idf: dict[str, float],
    pool: list[str] | None = None,
) -> Replacement | None:
    heads = str(fact_row.get("target_heads") or "").split("|")
    if not any(heads):
        return None
    if pool is None:
        pool = code_pool_for_heads(heads, head_index, candidates)
    evidence = (
        set(split_terms(str(fact_row.get("title_tokens") or "")))
        | set(split_terms(str(fact_row.get("ingredient_tokens") or "")))
        | set(split_terms(str(fact_row.get("identity_terms") or "")))
    )
    title_terms = set(split_terms(str(fact_row.get("title_tokens") or "")))
    ingredient_terms = set(split_terms(str(fact_row.get("ingredient_tokens") or "")))
    identity_terms = set(split_terms(str(fact_row.get("identity_terms") or "")))
    score_fact = dict(fact_row)
    score_fact["_target_heads"] = heads
    score_fact["_target_head_norms"] = head_norms_for_targets(heads)
    score_fact["_title_terms"] = title_terms
    score_fact["_ingredient_terms"] = ingredient_terms
    score_fact["_identity_terms"] = identity_terms
    score_fact["_evidence"] = evidence
    score_fact["_product_tokens"] = normalize_food_tokens(evidence)
    if len(pool) > 80:
        key_evidence = normalize_food_tokens(evidence) - GENERIC_IDENTITY - FORM_TOKENS
        filtered = [
            code
            for code in pool
            if key_evidence
            & (
                candidates[code].meaningful_terms
                | candidates[code].identity_terms
                | _tokens_for_description(candidates[code].description)
            )
        ]
        if filtered:
            pool = filtered
    scored: list[tuple[float, str, full_map.Candidate]] = []
    for code in pool:
        result = candidate_score(score_fact, candidates[code], idf)
        if result is None:
            continue
        score, reason = result
        scored.append((score, reason, candidates[code]))
    if not scored:
        return None
    scored.sort(key=lambda item: (item[0], item[2].category_support, -len(item[2].identity_terms)), reverse=True)
    best_score, reason, best = scored[0]
    second = scored[1][0] if len(scored) > 1 else 0.0
    margin = best_score - second
    # Nearest compatible is allowed, but require enough evidence that this is not
    # just another broad-head attractor.
    min_score = 12.0 if len(pool) <= 10 else 15.0
    if best_score < min_score:
        return None
    if margin < 0.1 and best_score < 24.0:
        return None
    return Replacement(
        code=best.code,
        description=best.description,
        head=esha_head(best.description),
        family=best.family,
        score=round(best_score, 4),
        reason=f"{reason};margin={margin:.3f}",
        pool_size=len(pool),
    )


def summarize_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
