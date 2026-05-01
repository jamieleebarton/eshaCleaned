#!/usr/bin/env python3
"""LLM cleanup harness for semantic retail taxonomy rows.

This script does three jobs:

1. Builds a compact decision packet from the enriched retail CSV.
2. Prompts an LLM for the row-level taxonomy shape we want.
3. Validates that the answer can compile into the traversible tree:

   Retail Taxonomy
     Beverage
       Plant Milk
         Almond Milk
           @flavor
             chocolate
           @claims
             unsweetened

The LLM is allowed to reason about messy evidence, but it is not allowed to
invent a different output shape. The validator is deliberately strict about the
common failures we saw: meal rows collapsing to a sauce/protein component,
claims getting placed under flavor, and attributes leaking into canonical paths.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable


csv.field_size_limit(sys.maxsize)

REPO = Path(__file__).resolve().parents[2]
V2 = REPO / "retail_mapper" / "v2"

DEFAULT_INPUT = V2 / "retail_leaf_v2_enriched_v2.csv"
DEFAULT_GOLD = V2 / "llm_taxonomy_gold_cases.jsonl"
DEFAULT_REQUESTS = V2 / "llm_taxonomy_requests.jsonl"
DEFAULT_OUTPUT = V2 / "llm_taxonomy_outputs.jsonl"
DEFAULT_SWEEP_OUT = V2 / "llm_taxonomy_model_sweep"
TREE_ROOT = "Retail Taxonomy"

DEFAULT_MODEL_CANDIDATES = [
    "deepseek-ai/DeepSeek-V3.2",
    "openai/gpt-oss-120b-fast",
    "Qwen/Qwen3-30B-A3B-Instruct-2507",
    "meta-llama/Llama-3.3-70B-Instruct",
    "NousResearch/Hermes-4-70B",
    "MiniMaxAI/MiniMax-M2.5-fast",
]

CANONICAL_CATEGORY_HINTS = {
    # --- v1 originals ---
    "Almond Milk": "Beverage > Plant Milk",
    "Barbecue Sauce": "Pantry > Sauces & Salsas",
    "Breakfast Sandwich": "Frozen > Breakfast Sandwiches",
    "Broccoli Cheddar Soup": "Pantry > Soup",
    "Cheese": "Dairy > Cheese",
    "Cheese Crisps": "Snack > Cheese Crisps",
    "Chicken Broth": "Pantry > Broth & Stock",
    "Chicken Burgers": "Meat & Seafood > Poultry",
    "Coconut Water": "Beverage > Coconut Water",
    "Cookies": "Snack > Cookies",
    "Dip": "Pantry > Dips & Spreads",
    "Meal Starter": "Meal > Meal Starters",
    "Parfait": "Meal > Composite Dishes",
    "Penne Alfredo": "Meal > Pasta Dishes",
    "Pizza": "Meal > Pizza",
    "Pizza Crust Mix": "Pantry > Baking Mixes",
    "Pretzels": "Snack > Pretzels",
    "Sandwich": "Meal > Sandwiches",
    "Seasoning": "Pantry > Spices & Seasonings",
    "Tomatoes": "Pantry > Canned Vegetables",
    "Tortillas": "Pantry > Tortillas",
    # --- v2 additions: bakery / cakes ---
    "Cake": "Bakery > Cake",
    "Pound Cake": "Bakery > Cake",
    "Carrot Cake": "Bakery > Cake",
    "Angel Food Cake": "Bakery > Cake",
    "Cupcakes": "Bakery > Cupcakes",
    "Muffins": "Bakery > Muffins",
    "Snack Cakes": "Snack > Snack Cakes",
    "Toaster Pastries": "Bakery > Toaster Pastries",
    # --- v2: breads ---
    "Bread": "Bakery > Bread",
    "Sourdough Bread": "Bakery > Bread",
    # --- v2: bars (all consolidate to a small set) ---
    "Granola Bars": "Snack > Bars",
    "Protein Bars": "Snack > Bars",
    "Energy Bars": "Snack > Bars",
    "Cereal Bars": "Snack > Bars",
    "Fruit Bars": "Snack > Bars",
    "Breakfast Bars": "Snack > Bars",
    "Kids Bars": "Snack > Bars",
    "Meal Replacement Bars": "Snack > Bars",
    "Nutrition Bars": "Snack > Bars",
    "Cookie Bars": "Snack > Bars",
    "Yogurt Bars": "Snack > Bars",
    "Snack Bars": "Snack > Bars",
    "Marshmallow Squares": "Snack > Bars",
    "Energy Gels": "Sports & Wellness > Energy Gels",
    "Candy Bar": "Snack > Chocolate Candy",
    # Candy subtypes — model defaults to bare "Candy" without these.
    "Marshmallows": "Snack > Candy",
    "Gummy Candy": "Snack > Candy",
    "Lollipops": "Snack > Candy",
    "Caramel Candy": "Snack > Candy",
    "Toffee": "Snack > Candy",
    "Truffle": "Snack > Candy",
    "Bark": "Snack > Candy",
    "Fudge": "Snack > Candy",
    "Cotton Candy": "Snack > Candy",
    "Licorice": "Snack > Candy",
    "Bubble Gum": "Snack > Gum",
    "Fruit Snacks": "Snack > Fruit Snacks",
    "Candied Fruit": "Snack > Candied Fruit",
    # --- v2: trail mix / nuts / granola ---
    "Trail Mix": "Snack > Trail Mix",
    "Mixed Nuts": "Snack > Nuts",
    "Granola": "Snack > Granola",
    # --- v2: meat ---
    "Chicken Breast": "Meat & Seafood > Poultry",
    "Chicken Thighs": "Meat & Seafood > Poultry",
    "Whole Chicken": "Meat & Seafood > Poultry",
    "Ground Turkey": "Meat & Seafood > Poultry",
    "Ground Beef": "Meat & Seafood > Beef",
    "Skirt Steak": "Meat & Seafood > Beef",
    "Ribeye Steak": "Meat & Seafood > Beef",
    "Filet Mignon": "Meat & Seafood > Beef",
    "Pork Chops": "Meat & Seafood > Pork",
    "Pork Ribs": "Meat & Seafood > Pork",
    # --- v2: vegetables ---
    "Broccoli": "Produce > Vegetables",
    "Peas": "Frozen > Vegetables",
    "Potatoes": "Frozen > Vegetables",
    "Baby Carrots": "Produce > Vegetables",
    "Green Beans": "Pantry > Canned Vegetables",
    "Vegetable Blend": "Frozen > Vegetables",
    "Broccoli with Cheese Sauce": "Frozen > Prepared Vegetables",
    # --- v2: candy ---
    "Chocolate Bar": "Snack > Chocolate Candy",
    "Chocolate Candy": "Snack > Chocolate Candy",
    "Chocolate Squares": "Snack > Chocolate Candy",
    "Fruit Candy": "Snack > Candy",
    "Fruit Chews": "Snack > Candy",
    "Hard Candy": "Snack > Candy",
    "Sour Candy": "Snack > Candy",
    "Jelly Beans": "Snack > Candy",
    # --- v2: dairy / milk-adjacent ---
    "Chocolate Milk": "Dairy > Flavored Milk",
    "Strawberry Milk": "Dairy > Flavored Milk",
    "Vanilla Milk": "Dairy > Flavored Milk",
    "Banana Milk": "Dairy > Flavored Milk",
    "Oat Milk": "Beverage > Plant Milk",
    "Eggnog": "Beverage > Eggnog",
    "Kefir": "Dairy > Kefir",
    "Butter": "Dairy > Butter",
    "Ice Cream": "Frozen > Ice Cream",
    "Gelato": "Frozen > Gelato",
    # --- v2: beverages ---
    "Sparkling Water": "Beverage > Sparkling Water",
    "Kombucha": "Beverage > Kombucha",
    "Apple Cider Vinegar Drink": "Beverage > Functional Drinks",
    "Wellness Shot": "Beverage > Wellness Shots",
    "Cold Brew Coffee": "Beverage > Coffee",
    "Protein Shake": "Beverage > Protein Drinks",
    # --- v2: drink mixes (powder/dry) ---
    "Latte Mix": "Pantry > Drink Mixes",
    "Lemonade Mix": "Pantry > Drink Mixes",
    "Hot Cocoa Mix": "Pantry > Drink Mixes",
    "Sports Drink Mix": "Pantry > Drink Mixes",
    "Chocolate Milk Mix": "Pantry > Drink Mixes",
    # --- v2: pantry / sauces / dressings / spreads ---
    "Aioli": "Pantry > Sauces & Salsas",
    "Mayonnaise": "Pantry > Sauces & Salsas",
    "Salad Dressing": "Pantry > Salad Dressings",
    "Ranch Dressing": "Pantry > Salad Dressings",
    "Apple Butter": "Pantry > Spreads",
    "Pie Filling": "Pantry > Pie Fillings",
    "Applesauce": "Pantry > Applesauce",
    # --- v2: spices ---
    "BBQ Rub": "Pantry > Spices & Seasonings",
    "Curry Powder": "Pantry > Spices & Seasonings",
    "Salt and Pepper": "Pantry > Spices & Seasonings",
    "Spice Blend": "Pantry > Spices & Seasonings",
    # --- v2: snack/chip-like ---
    "Apple Chips": "Snack > Dried Fruit",
    "Veggie Straws": "Snack > Veggie Snacks",
    "Fruit Leather": "Snack > Fruit Leather",
    "Fruit and Veggie Strips": "Snack > Fruit Leather",
    "Flatbread Crisps": "Snack > Crackers",
    # --- v2: prepared meals ---
    "TV Dinner": "Frozen > TV Dinners",
    "Frozen Entree": "Frozen > Single Entrees",
    "Skillet Meal": "Frozen > Skillet Meals",
    "Pot Pie": "Frozen > Pot Pies",
    "Mac and Cheese": "Frozen > Single Entrees",
    "Lasagna": "Meal > Pasta Dishes",
    "Kids Meal": "Frozen > Kids Meals",
    "French Bread Pizza": "Frozen > Pizza",
    "Pizza Pocket": "Frozen > Stuffed Sandwiches",
    "Lunch Kit": "Refrigerated > Lunch Kits",
    # --- v2: snack packs ---
    "Apple Snack Pack": "Produce > Snack Packs",
    "Cheese and Crackers Pack": "Snack > Snack Packs",
    # --- v2: juice / concentrate ---
    "Juice Concentrate": "Frozen > Juice Concentrate",
}

# Tokens the LLM keeps adding as default top-level facets even when no evidence
# supports them. The normalizer strips these UNLESS they are present in the
# row's title or ingredient text. (Component-level traits are left alone — those
# are deduced separately on the components array.)
EVIDENCE_GATED_PROCESSING_TOKENS = {
    "canned", "frozen", "shelf_stable", "fully_cooked",
    "ready_to_eat", "smoked", "dried", "from_concentrate",
    "baked", "roasted", "toasted", "kettle_cooked", "oven_baked",
    "seasoned", "marinated", "brined", "cured",
}
EVIDENCE_GATED_FORM_TOKENS = {
    "blend", "crisps", "sandwich", "mix", "kit", "starter",
}

# Compound facet tokens the LLM tends to split. Map sorted-tuple of split parts
# to the canonical compound token.
COMPOUND_FACET_TOKENS = {
    ("peeled", "whole"): "whole_peeled",
    ("crushed", "whole"): "whole_crushed",
    ("diced", "petite"): "petite_diced",
    ("crushed", "fire_roasted"): "fire_roasted_crushed",
    ("diced", "fire_roasted"): "fire_roasted_diced",
    ("meat_cheese", "tuscan"): "tuscan_meat_cheese",
}

# Identities that imply retail_type = meal_kit (the LLM often labels these as
# composite_dish instead).
MEAL_KIT_IDENTITY_TOKENS = {
    "meal_starter", "dinner_kit", "salad_kit", "stir_fry_kit",
    "pasta_kit", "meal_kit", "kit",
}

# Hard-coded "claim never travels with this identity" rules. These come from
# scoring failures where the LLM put a marketing slogan into claims.
DISALLOWED_CLAIMS_BY_IDENTITY = {
    # marketing fluff, never a real claim
    "Cheese": {"real_cheese", "100_real", "100_percent_real_cheese", "100_percent_real"},
    "Cheese Crisps": {"real_cheese", "made_with_real_cheese", "100_real",
                      "100_percent_real_cheese", "100_percent_real"},
    "Chicken Broth": {"real_cheese"},
}

# Marketing words that aren't anywhere — drop from variant/flavor/form universally.
MARKETING_DROP_TOKENS = {
    "creamy", "premium", "classic", "original", "extra_virgin", "select",
    "signature", "homestyle", "deluxe",
}

# Identities that should be retail_type=composite_dish (model often picks single).
COMPOSITE_DISH_IDENTITIES = {
    "Sandwich", "Sandwiches", "Breakfast Sandwich",
    "Flatbread Sandwich", "Wrap", "Burrito", "Taco",
    "Parfait",
}

# Component identity canonicalization: simple food noun mappings.
COMPONENT_IDENTITY_CANONICALIZE = {
    "Chicken Breast": "Chicken",
    "Chicken Thigh": "Chicken",
    "Chicken Strips": "Chicken",
    "Chicken Tenders": "Chicken",
    "Chicken Breast Strips": "Chicken",
    "Chicken Breast Tenders": "Chicken",
    "Sesame Garlic Chicken Breast Strips": "Chicken",
    "Sesame Garlic Chicken Breast": "Chicken",
    "Beef Strips": "Beef",
    "Beef Tips": "Beef",
    "Pork Loin": "Pork",
    "Turkey Breast": "Turkey",
    "Red Bell Pepper": "Red Peppers",
    "Red Bell Peppers": "Red Peppers",
}

# Decorator suffixes the LLM appends to product_identity that we should strip.
# After stripping, if the remainder doesn't match a hint, we also try the
# pluralized form via IDENTITY_PLURAL_FALLBACKS.
IDENTITY_DECORATOR_SUFFIXES = (
    " Blend",
    " Pieces",
    " Bites",
    " Bits",
    " Style",
    " Variety",
    " Mix",
)

# When a suffix is stripped from product_identity, what to do with the token:
#   "form"  -> add it to form_texture_cut (pretzel pieces / bagel bites are real forms)
#   "drop"  -> remove it from form/variant entirely (Blend/Mix are filler)
DECORATOR_SUFFIX_DESTINATION = {
    "blend": "drop",
    "mix": "drop",
    "style": "drop",
    "variety": "drop",
    "pieces": "form",
    "bites": "form",
    "bits": "form",
}

# When a stripped identity isn't in CANONICAL_CATEGORY_HINTS, try one of these
# plural fallbacks (single -> plural) to recover the canonical key.
IDENTITY_PLURAL_FALLBACKS = {
    "Pretzel": "Pretzels",
    "Cookie": "Cookies",
    "Tortilla": "Tortillas",
    "Tomato": "Tomatoes",
    "Cracker": "Crackers",
    "Chip": "Chips",
    "Chicken Burger": "Chicken Burgers",
    "Burger": "Burgers",
    "Cheese Crisp": "Cheese Crisps",
    "Sandwich": "Sandwich",  # singular form already canonical
}

# mint_required is a deterministic property based on whether the
# product_identity is a node that already exists in established FNDDS/USDA
# baseline taxonomy. Per expert review: this is a lookup, not an LLM
# decision — the model gets it wrong on ~half the cases. Hard-code the
# established-classics set; everything else with a CANONICAL_CATEGORY_HINTS
# entry is mint_required=True.
MINT_NOT_REQUIRED_IDENTITIES = {
    "Cookies", "Cake", "Cupcakes", "Brownies",
    "Bread", "Bagel", "Muffin", "Roll", "Bun",
    "Yogurt", "Milk", "Cheese",
    "Sandwich", "Wrap", "Burrito", "Taco",
    "Parfait", "Cereal", "Granola",
    "Pretzels", "Crackers", "Chips",
    "Ice Cream", "Sherbet", "Sorbet",
    "Juice", "Soda", "Water",
    "Eggs", "Butter",
    "Pasta", "Rice",
    "Soup",  # generic soup is established; compound soups (Broccoli Cheddar Soup) need minting
}


# Tokens that are unambiguously taste-notes (flavor) regardless of context.
# When the LLM puts these in `variant`, we move them to `flavor`.
KNOWN_FORM_TOKENS = {
    "whole_peeled", "whole_crushed", "petite_diced", "fire_roasted_diced",
    "fire_roasted_crushed", "diced", "crushed", "sliced", "shredded",
    "crumbled", "grated", "minced", "chopped", "cubed", "halved", "quartered",
    "flatbread", "tortilla", "wrap", "patty",
    # Meat cut descriptors — these are FORM, not variant
    "boneless", "skinless", "bone_in", "skin_on", "bone_less", "skin_less",
    "trimmed", "untrimmed", "lean", "extra_lean",
}

KNOWN_FLAVOR_TOKENS = {
    "chocolate", "chocolate_chip", "chocolate_chunk", "double_chocolate",
    "vanilla", "vanilla_bean", "french_vanilla",
    "strawberry", "raspberry", "blueberry", "blackberry", "cherry",
    "lemon", "lime", "orange", "grapefruit",
    "mint", "peppermint", "spearmint",
    "cinnamon", "cinnamon_sugar", "snickerdoodle",
    "peanut_butter", "almond", "hazelnut", "pecan", "walnut",
    "caramel", "butterscotch", "toffee",
    "maple", "honey",
    "coconut", "pineapple", "mango", "peach", "apple",
    "basil",  # culinary herb used as taste accent in tomatoes/sauces
}

FACET_GROUPS = ["variant", "flavor", "form_texture_cut", "processing_storage", "claims"]
COMPONENT_FACET_GROUPS = ["variant", "flavor", "form_texture_cut", "processing_storage", "claims"]
COMPONENT_FIELDS = ["identity", "role", *COMPONENT_FACET_GROUPS]
REQUIRED_FIELDS = [
    "fdc_id",
    "retail_type",
    "category_path",
    "product_identity",
    "canonical_path",
    "canonical_label",
    "variant",
    "flavor",
    "form_texture_cut",
    "processing_storage",
    "claims",
    "components",
    "confidence",
    "mint_required",
    "review_flags",
    "rationale",
    "tree_paths",
]

STRICT_COMPARE_FIELDS = [
    "retail_type",
    "category_path",
    "product_identity",
    "canonical_path",
    "canonical_label",
    "variant",
    "flavor",
    "form_texture_cut",
    "processing_storage",
    "claims",
    "components",
    "mint_required",
    "tree_paths",
]

CORE_COMPARE_FIELDS = [
    "retail_type",
    "category_path",
    "product_identity",
    "canonical_path",
    "variant",
    "flavor",
    "form_texture_cut",
    "processing_storage",
    "claims",
]

RETAIL_TYPES = {
    "single",
    "composite_dish",
    "meal_kit",
    "combo_pack",
    "combination_meal",
    "multi_pack",
    "unknown",
}

CLAIM_ORDER = {
    "gluten_free": 10,
    "dairy_free": 11,
    "lactose_free": 12,
    "nut_free": 13,
    "peanut_free": 14,
    "tree_nut_free": 15,
    "soy_free": 16,
    "egg_free": 17,
    "caffeine_free": 20,
    "vegan": 100,
    "vegetarian": 101,
    "plant_based": 102,
    "keto": 103,
    "paleo": 104,
    "kosher": 105,
    "halal": 106,
    "calorie_free": 180,
    "low_calorie": 181,
    "reduced_calorie": 182,
    "sugar_free": 200,
    "zero_sugar": 201,
    "no_sugar_added": 202,
    "unsweetened": 203,
    "reduced_sugar": 204,
    "lightly_sweetened": 205,
    "sweetened": 206,
    "monk_fruit": 208,
    "no_salt_added": 300,
    "unsalted": 301,
    "salt_free": 302,
    "low_sodium": 303,
    "reduced_sodium": 304,
    "sea_salt": 305,
    "fat_free": 400,
    "nonfat": 401,
    "low_fat": 402,
    "reduced_fat": 403,
    "light": 404,
    "lite": 405,
    "high_protein": 500,
    "probiotic": 501,
    "fortified": 503,
    "whole_grain": 508,
    "organic": 600,
    "non_gmo": 601,
    "grass_fed": 602,
    "pasture_raised": 603,
    "free_range": 604,
    "cage_free": 605,
    "wild_caught": 606,
    "sustainable": 607,
    "fair_trade": 608,
    "extra_virgin": 609,
    "natural": 700,
    "all_natural": 701,
}

CLAIM_VALUES = set(CLAIM_ORDER)
TOP_LEVEL_ONLY = {"Bakery", "Beverage", "Dairy", "Frozen", "Meal", "Meat & Seafood", "Other", "Pantry", "Produce", "Snack"}
GENERIC_PRODUCT_IDENTITIES = TOP_LEVEL_ONLY | {"Food", "Foods", "Product", "Item", "Grocery", "Bakery", "Deli"}

MEAL_BFC_HINTS = (
    "other deli",
    "frozen dinners",
    "frozen meals",
    "prepared meals",
    "prepared subs",
    "prepared wraps",
    "entrees",
    "sides and small meals",
    "breakfast sandwiches biscuits meals",
)

SOURCE_FIELDS = [
    "fdc_id",
    "gtin_upc",
    "title",
    "branded_food_category",
    "current_esha",
    "current_esha_desc",
    "retail_leaf",
    "ing_full",
    "semantic_retail_type",
    "semantic_category_path",
    "semantic_product_identity",
    "semantic_canonical_path",
    "semantic_canonical_label",
    "semantic_review_flags",
    "source_parser_primary_food",
    "source_parser_form",
    "source_parser_flavor",
    "product_form_guess",
    "modifier_guesses",
    "ingredient_guesses",
    "ing_top5",
    "ing_categories",
    "title_ngrams_json",
    "role_candidates_json",
    "llm_evidence_block",
]


@dataclass
class LlmTaxonomyRecord:
    fdc_id: str
    retail_type: str
    category_path: str
    product_identity: str
    canonical_path: str
    canonical_label: str
    variant: list[str] = field(default_factory=list)
    flavor: list[str] = field(default_factory=list)
    form_texture_cut: list[str] = field(default_factory=list)
    processing_storage: list[str] = field(default_factory=list)
    claims: list[str] = field(default_factory=list)
    components: list[dict[str, object]] = field(default_factory=list)
    confidence: float = 0.0
    mint_required: bool = False
    review_flags: list[str] = field(default_factory=list)
    rationale: str = ""
    tree_paths: list[str] = field(default_factory=list)


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def normalize_token(value: str) -> str:
    value = normalize_space(value).lower()
    value = value.replace("&", " and ")
    value = re.sub(r"[^a-z0-9]+", "_", value).strip("_")
    return value


def titleize_token(value: str) -> str:
    if not value:
        return ""
    special = {"bbq": "BBQ", "pb": "PB"}
    return " ".join(special.get(part, part.capitalize()) for part in normalize_token(value).split("_"))


def split_path(path: str) -> list[str]:
    return [part.strip() for part in (path or "").split(">") if part.strip()]


def clean_list(values: object) -> list[str]:
    if values is None or values == "":
        return []
    if isinstance(values, str):
        raw = [part.strip() for part in values.split("|")]
    elif isinstance(values, list):
        raw = [str(part).strip() for part in values]
    else:
        raw = [str(values).strip()]
    out: list[str] = []
    seen: set[str] = set()
    for value in raw:
        token = normalize_token(value)
        if token and token not in seen:
            seen.add(token)
            out.append(token)
    return out


def clean_string_list(values: object) -> list[str]:
    if values is None or values == "":
        return []
    raw = values if isinstance(values, list) else [values]
    out: list[str] = []
    seen: set[str] = set()
    for value in raw:
        text = normalize_space(str(value))
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out


def order_claims(values: Iterable[str]) -> list[str]:
    return sorted(clean_list(list(values)), key=lambda item: (CLAIM_ORDER.get(item, 9999), item))


def clean_components(values: object) -> list[dict[str, object]]:
    if not isinstance(values, list):
        return []
    out: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()
    for value in values:
        if not isinstance(value, dict):
            continue
        identity = normalize_space(str(value.get("identity", "")))
        role = normalize_token(str(value.get("role", ""))) or "unknown"
        if not identity:
            continue
        key = (identity, role)
        if key in seen:
            continue
        seen.add(key)
        component: dict[str, object] = {"identity": identity, "role": role}
        for group in COMPONENT_FACET_GROUPS:
            component[group] = order_claims(value.get(group, [])) if group == "claims" else clean_list(value.get(group, []))
        out.append(component)
    return out


def display_attr(value: str) -> str:
    return titleize_token(value)


def build_canonical_path(category_path: str, product_identity: str) -> str:
    return " > ".join(split_path(category_path) + [normalize_space(product_identity)])


def build_canonical_label(product_identity: str, record: dict[str, object]) -> str:
    attrs: list[str] = []
    for group in FACET_GROUPS:
        values = order_claims(record.get(group, [])) if group == "claims" else clean_list(record.get(group, []))
        attrs.extend(display_attr(value) for value in values)
    if not attrs:
        return normalize_space(product_identity)
    return f"{normalize_space(product_identity)} ({', '.join(attrs)})"


def build_tree_paths(record: dict[str, object]) -> list[str]:
    canonical = str(record.get("canonical_path") or "")
    if not canonical:
        canonical = build_canonical_path(str(record.get("category_path") or ""), str(record.get("product_identity") or ""))
    base = f"{TREE_ROOT} > {canonical}"
    paths = [base]
    for group in FACET_GROUPS:
        values = order_claims(record.get(group, [])) if group == "claims" else clean_list(record.get(group, []))
        for value in values:
            paths.append(f"{base} > @{group} > {value}")
    for component in clean_components(record.get("components", [])):
        component_id = normalize_token(str(component.get("identity", "")))
        if component_id:
            paths.append(f"{base} > @components > {component_id}")
    return paths


def parse_record(payload: dict[str, object]) -> LlmTaxonomyRecord:
    data = dict(payload)
    for group in FACET_GROUPS:
        data[group] = clean_list(data.get(group, []))
    data["components"] = clean_components(data.get("components", []))
    data["review_flags"] = clean_list(data.get("review_flags", []))
    data["confidence"] = float(data.get("confidence") or 0.0)
    data["mint_required"] = bool(data.get("mint_required", False))
    if not data.get("canonical_path"):
        data["canonical_path"] = build_canonical_path(str(data.get("category_path") or ""), str(data.get("product_identity") or ""))
    if not data.get("canonical_label"):
        data["canonical_label"] = build_canonical_label(str(data.get("product_identity") or ""), data)
    data["tree_paths"] = clean_string_list(data.get("tree_paths", [])) or build_tree_paths(data)
    return LlmTaxonomyRecord(**{field.name: data.get(field.name) for field in LlmTaxonomyRecord.__dataclass_fields__.values()})


def validate_record(payload: dict[str, object], source_row: dict[str, str] | None = None) -> list[str]:
    errors: list[str] = []
    for field_name in REQUIRED_FIELDS:
        if field_name not in payload:
            errors.append(f"missing_field:{field_name}")

    try:
        record = parse_record(payload)
    except Exception as exc:  # pragma: no cover - defensive against malformed LLM JSON.
        return [f"parse_error:{exc}"]

    for group in FACET_GROUPS:
        raw_values = payload.get(group, [])
        if not isinstance(raw_values, list):
            errors.append(f"invalid_list:{group}")
            continue
        for raw_value in raw_values:
            if not isinstance(raw_value, str):
                errors.append(f"invalid_list_item:{group}")
                continue
            if raw_value != normalize_token(raw_value):
                errors.append(f"attribute_not_normalized:{group}:{raw_value}")

    raw_components = payload.get("components", [])
    if not isinstance(raw_components, list):
        errors.append("invalid_list:components")
    else:
        for idx, component in enumerate(raw_components):
            if not isinstance(component, dict):
                errors.append(f"invalid_component:{idx}")
                continue
            identity = component.get("identity", "")
            if not isinstance(identity, str) or not normalize_space(identity):
                errors.append(f"invalid_component_identity:{idx}")
            elif identity == normalize_token(identity):
                errors.append(f"component_identity_not_title_case:{idx}:{identity}")
            role = component.get("role", "")
            if not isinstance(role, str) or role != normalize_token(role):
                errors.append(f"component_role_not_normalized:{idx}:{role}")
            for group in COMPONENT_FACET_GROUPS:
                values = component.get(group, [])
                if not isinstance(values, list):
                    errors.append(f"invalid_component_list:{idx}:{group}")
                    continue
                for raw_value in values:
                    if not isinstance(raw_value, str):
                        errors.append(f"invalid_component_list_item:{idx}:{group}")
                        continue
                    if raw_value != normalize_token(raw_value):
                        errors.append(f"component_attribute_not_normalized:{idx}:{group}:{raw_value}")
                if group == "claims" and clean_list(values) != order_claims(values):
                    errors.append(f"component_claims_out_of_order:{idx}")

    if record.retail_type not in RETAIL_TYPES:
        errors.append(f"invalid_retail_type:{record.retail_type}")

    category_parts = split_path(record.category_path)
    if len(category_parts) < 2:
        errors.append("category_path_too_shallow")
    if any(part.startswith("@") for part in split_path(record.canonical_path)):
        errors.append("facet_group_inside_canonical_path")
    if normalize_space(record.product_identity) in GENERIC_PRODUCT_IDENTITIES:
        errors.append("generic_product_identity")

    expected_path = build_canonical_path(record.category_path, record.product_identity)
    if record.canonical_path != expected_path:
        errors.append(f"canonical_path_mismatch:{expected_path}")

    expected_label = build_canonical_label(record.product_identity, asdict(record))
    if record.canonical_label != expected_label:
        errors.append(f"canonical_label_mismatch:{expected_label}")

    misplaced_claims = CLAIM_VALUES & set(record.flavor)
    if misplaced_claims:
        errors.append(f"claims_in_flavor:{'|'.join(sorted(misplaced_claims))}")

    if record.claims != order_claims(record.claims):
        errors.append("claims_out_of_order")

    if record.retail_type == "combination_meal" and len(record.components) < 2:
        errors.append("combination_meal_missing_components")

    expected_tree_paths = build_tree_paths(asdict(record))
    if record.tree_paths != expected_tree_paths:
        errors.append("tree_paths_mismatch")

    return errors


# Fields that bloat the payload without improving model decisions, OR that
# actively mislead it. From an expert prompt-engineering review of the
# diabolical cases: title_ngrams_json (~65% of source_row bytes) and
# role_candidates_json (~15%) are dense JSON the model rarely uses; semantic_*
# are pre-existing taxonomy guesses that are wrong on every hostile case
# (Parfait misclassified as Cereal, Sandwich as Cheese, Meal Starter as
# Chicken, etc.) and become anchors the LLM has to fight to override.
LEAN_DROP_FIELDS = {
    "title_ngrams_json",
    "role_candidates_json",
    "semantic_canonical_path",
    "semantic_product_identity",
    "semantic_category_path",
    "semantic_canonical_label",
    "semantic_retail_type",
    "semantic_review_flags",
}

# Module-level toggle for lean evidence mode. Default ON because the bloat
# fields are net-harmful per expert review. Override with --no-lean-evidence.
_LEAN_EVIDENCE_MODE = True


def compact_source_row(row: dict[str, str]) -> dict[str, str]:
    compact: dict[str, str] = {}
    for field_name in SOURCE_FIELDS:
        if _LEAN_EVIDENCE_MODE and field_name in LEAN_DROP_FIELDS:
            continue
        value = row.get(field_name, "")
        if value:
            compact[field_name] = value[:6000] if field_name in {"ing_full", "llm_evidence_block"} else value
    return compact


def candidate_paths(row: dict[str, str]) -> list[str]:
    paths = []
    for field_name in [
        "semantic_canonical_path",
        "semantic_existing_taxonomy_path",
        "retail_leaf",
        "source_clean_retail_leaf",
    ]:
        value = row.get(field_name, "")
        if value and value not in paths:
            paths.append(value)
    return paths[:8]


def schema_text() -> str:
    return json.dumps(
        {
            "fdc_id": "same fdc_id as input",
            "retail_type": "single | composite_dish | combination_meal | meal_kit | combo_pack | multi_pack | unknown",
            "category_path": "Department > Category, excluding product identity and attributes",
            "product_identity": "shopper-facing thing being bought",
            "canonical_path": "category_path > product_identity",
            "canonical_label": "Product Identity (Variant, Flavor, Form, Processing, Claims), generated from top-level facets in that order",
            "variant": ["subtype/style/protein/variety that changes selection but is not the identity"],
            "flavor": ["taste notes only"],
            "form_texture_cut": ["physical state, texture, cut, shape, presentation"],
            "processing_storage": ["frozen/canned/dried/smoked/from_concentrate/ready_to_eat/etc"],
            "claims": ["dietary/nutrition/marketing claims in canonical order"],
            "components": [
                {
                    "identity": "Title Case component identity, e.g. Chicken Breast",
                    "role": "main | protein | base | sauce | topping | side | filling | included_item | ingredient | bread | cheese | fruit | unknown",
                    "variant": [],
                    "flavor": [],
                    "form_texture_cut": [],
                    "processing_storage": [],
                    "claims": [],
                }
            ],
            "confidence": 0.0,
            "mint_required": False,
            "review_flags": ["short_machine_flags_if_needed"],
            "rationale": "one short sentence",
            "tree_paths": [
                "Retail Taxonomy > category_path > product_identity",
                "Retail Taxonomy > category_path > product_identity > @variant > value",
                "Retail Taxonomy > category_path > product_identity > @components > normalized_component_identity",
            ],
        },
        indent=2,
    )


def claim_order_text() -> str:
    ordered = [claim for claim, _rank in sorted(CLAIM_ORDER.items(), key=lambda item: (item[1], item[0]))]
    return ", ".join(ordered)


def canonical_category_hint_text() -> str:
    return "\n".join(f"- {identity}: {path}" for identity, path in sorted(CANONICAL_CATEGORY_HINTS.items()))


# ---------------------------------------------------------------------------
# Two-pass prompts (split identity decision from facet/component decision so
# each prompt is short enough for the model to pay attention to every rule —
# combats primacy/recency loss on the long single-pass prompt.)
# ---------------------------------------------------------------------------

SYSTEM_PROMPT_IDENTITY = f"""You are a retail grocery taxonomy adjudicator. PASS 1 of 2: IDENTITY ONLY.

Your single job in this pass is to decide WHAT the shopper is buying. Do NOT decide facets, flavors, components, or claims yet — that is pass 2.

Tree model:
Retail Taxonomy > Department > Category > Product Identity

Core question:
What is on the shopper's grocery list?

Evidence priority:
1. Product title
2. Full ingredient list and top ingredients
3. Branded food category
4. Parser fields, n-grams, role candidates
5. Existing ESHA / current semantic / candidate paths (these are clues; override when wrong)

Decision process:
1. Decide retail_type from: single, composite_dish, combination_meal, meal_kit, combo_pack, multi_pack, unknown.
2. Decide product_identity using the grocery-list test.
3. Decide category_path as Department > Category only.
4. Build canonical_path exactly as category_path > product_identity.
5. Decide mint_required (see rules below).

Canonical category routing hints (USE these category_paths when product_identity matches):
{canonical_category_hint_text()}

Identity rules:
- If the SKU is a prepared dish, meal, sandwich, wrap, bowl, kit, starter, parfait, combo, or mixed pack, keep the whole item as product_identity. Never collapse it to a component.
- Product forms like Meal Starter, Dinner Kit, Salad Kit, Sauce Mix, Seasoning Mix, Pizza Crust Mix, Cheese Crisps, Protein Parfait, Breakfast Sandwich, Flatbread Sandwich are real shopper-facing identities.
- COMPOUND IDENTITY: when the title contains a recognized compound noun (Broccoli Cheddar Soup, Tomato Basil Soup, Chicken Noodle Soup, Pineapple Coconut Water, Spinach Artichoke Dip, Pumpkin Spice Latte), use the WHOLE compound as product_identity. Do NOT split into a generic identity with the modifiers as variant. Example: "Creamy Cheddar Broccoli Soup" -> product_identity="Broccoli Cheddar Soup", category_path="Pantry > Soup". Marketing words like Creamy, Premium, Classic, Original, Protein at the start of an identity should be DROPPED here (pass 2 handles them).
- If the SKU is just a single base ingredient with marketing prefix (e.g., "Premium Tomatoes"), product_identity is the bare base ("Tomatoes"). Drop the marketing word.
- If the title gives only a generic identity (Hard Aged Cheese), product_identity stays generic ("Cheese") — pass 2 will fill the variant/form. Do not guess Parmesan/Pecorino/Asiago without evidence.
- If the product identity is not proven, set retail_type="unknown", category_path="Other > Needs Review", product_identity="Unknown Product", confidence<=0.50.

mint_required = TRUE when this SKU corresponds to a retail-specific or compound product node that does NOT exist as a standard FNDDS/ESHA classic. Set TRUE for: Chicken Broth, Tomatoes, Seasoning, Tortillas, Coconut Water, Dip, Broccoli Cheddar Soup, Pizza Crust Mix, Chicken Burgers, Cheese Crisps, Meal Starter, Breakfast Sandwich, and any compound identity from the hint table that names a retail concept (not a USDA classic).
mint_required = FALSE for established FNDDS/USDA classics: Cookies, Cake, Bread, Yogurt, Cheese, Sandwich, Parfait, Pretzels, Crackers, Chips, Ice Cream, Milk, Juice.

Output STRICT JSON ONLY. First char {{, last char }}. No markdown fences. No commentary.

Required schema:
{{
  "fdc_id": "same fdc_id as input",
  "retail_type": "single | composite_dish | combination_meal | meal_kit | combo_pack | multi_pack | unknown",
  "category_path": "Department > Category",
  "product_identity": "shopper-facing thing being bought",
  "canonical_path": "category_path > product_identity",
  "confidence": 0.0,
  "mint_required": false,
  "review_flags": ["short_machine_flags_if_needed"],
  "rationale": "one short sentence"
}}
"""


SYSTEM_PROMPT_FACETS = f"""You are a retail grocery taxonomy adjudicator. PASS 2 of 2: FACETS AND COMPONENTS.

The product_identity, category_path, canonical_path, and retail_type were LOCKED in pass 1 — DO NOT change them. They appear in the user payload under "locked_identity". Echo them back verbatim in your output.

Your job in this pass is to fill out the facet arrays (variant, flavor, form_texture_cut, processing_storage, claims) and components, then derive canonical_label and tree_paths.

Facet rules:
- variant = subtype/style/protein/variety that changes selection but is not the identity (e.g., chicken_apple_sausage, sesame_garlic_chicken, asiago, almond_flour, red_pepper_feta).
- flavor = taste notes only: chocolate, vanilla, basil, hatch_green_chile, jalapeno, chipotle, sriracha, buffalo, ranch, honey_mustard, bbq, cajun, garlic_herb, cinnamon, mint, etc.
- form_texture_cut = physical state, shape, cut, texture, presentation: diced, whole_peeled, flatbread, hard, soft, firm, semi_soft, crumbled, sliced, shredded, pieces, bites.
- processing_storage = frozen, canned, dried, smoked, shelf_stable, ready_to_eat, fully_cooked. Do NOT include processing tokens that describe how the product TYPE is normally made (pretzels are baked; do not output processing=["baked"] unless the title literally says baked).
- claims = dietary/nutrition/marketing claims only, in this exact order:
{claim_order_text()}

Critical placement rules:
- retail_type describes PACK STRUCTURE, not food category. Allowed values ONLY: single, composite_dish, combination_meal, meal_kit, combo_pack, multi_pack, unknown. Do NOT use "beverage", "snack", "dairy" — those describe food category, not pack structure. A single bottle of eggnog is retail_type="single" with category_path="Beverage > Eggnog".
- MEAT CUT FORM DESCRIPTORS: boneless, skinless, bone_in, skin_on, trimmed, lean, extra_lean — these go in form_texture_cut, NEVER variant. Example: "Boneless Skinless Chicken Breast" -> identity="Chicken Breast", form_texture_cut=["boneless","skinless"], variant=[]. Do NOT put boneless/skinless in variant.
- TEXTURE BELONGS IN form_texture_cut, NOT variant. The words hard, soft, firm, semi_soft, crumbly, smooth, creamy, chunky describe texture. NEVER variants. Example: "Hard Aged Cheese" -> identity="Cheese", variant=["aged"], form_texture_cut=["hard"].
- REGIONAL/NAMED FLAVOR ACCENTS STAY IN flavor AND DO NOT MERGE INTO variant. Example: "Hatch Green Chile Asiago Cheese Crisps" -> variant=["asiago"], flavor=["hatch_green_chile"]. NEVER variant=["hatch_green_chile_asiago"].
- DO NOT APPEND COMPONENT-CATEGORY WORDS TO A VARIANT. Example: "Red Pepper Feta Chicken Burgers" -> variant=["red_pepper_feta"] (NOT variant=["red_pepper_feta_cheese"]). Feta is already cheese.
- Do NOT put the product identity itself into form_texture_cut. Example: Breakfast Sandwich should not have form_texture_cut=["sandwich"]. Use form_texture_cut=["flatbread"] only if flatbread is the carrier/presentation.
- Keep useful named filling combinations together (egg_white_cheddar in a breakfast sandwich), but separate the protein phrase from the egg/cheese phrase.
- Compound texture tokens stay compound: whole_peeled is one form token, NOT ["whole","peeled"].
- Do NOT add processing tokens that the title doesn't say. "Frozen Meals" BFC is a category, not authorization to mark every SKU frozen unless the title also says frozen or evidence is unambiguous.

Component rules:
- Components are NOT an ingredient dump. List only named/separable meal parts or distinctive ingredients the shopper sees on the package.
- COMPONENT IDENTITY = canonical food noun. Strip prep phrases ("In Sauce", "Dices", "Strips", "Crumbles", "Chunks", "Pieces") and pure flavor prefixes ("Cinnamon ", "Spicy ", "Honey ", "Buttery ", "Sweet ", "Garlic "). Examples:
  - ingredient line "Apple Dices In Sauce" -> component identity "Apple"
  - ingredient line "Sesame Garlic Chicken Breast Strips" inside a meal kit -> component identity "Chicken"
  - ingredient line "Cinnamon Granola Topping" -> component identity "Granola Topping"
- DO NOT strip "Smoked", "Roasted", "Toasted", "Sea Salt" — those define a distinct food noun ("Smoked Ham" is its own product, not just "Ham").
- DISTINCTIVE-INGREDIENT PROMOTION: when a top-level variant token names a primary distinguishing ingredient (almond_flour, oat_milk, hemp_seed, coconut_milk), ALSO emit it as a top-level component with role="ingredient". Example: "Almond Flour Tortillas" -> variant=["almond_flour"], components=[{{"identity":"Almond Flour","role":"ingredient",...}}].
- Component role: use "ingredient" for distinctive-ingredient promotions and component-as-evidenced-ingredient cases (Spinach, Artichoke in a dip; Broccoli, Cheddar Cheese in a soup). Use "main", "protein", "base", "topping", "filling", "bread", "cheese", "fruit", "side", "included_item" for meal-kit / composite-dish parts.
- Do not include the SKU's primary identity itself as a component. A "Tomatoes" SKU does NOT have a "Tomatoes" component.
- Cheese Crisps SKU with variant=["asiago"] does NOT also list "Asiago Cheese" as a component — that's an echo.
- Single-flavor accents (basil in a Tomatoes SKU) belong in flavor=["basil"], NOT in components.

Output derivation:
- canonical_label = "Product Identity (Variant, Flavor, Form, Processing, Claims)" — top-level facet display values in this exact order. Snake_case becomes Title Case (egg_white_cheddar -> "Egg White Cheddar"). NEVER use "&", slashes, or raw title punctuation. If all facet arrays are empty, canonical_label is just the product_identity with no parens.
- tree_paths = exactly derived from canonical_path + facets + components. Use exact group names: @variant, @flavor, @form_texture_cut, @processing_storage, @claims, @components. NEVER @form or @processing.
- Component tree path values are the normalized component identity (Chicken Apple Sausage Patty -> chicken_apple_sausage_patty).

Output STRICT JSON ONLY. First char {{, last char }}. No markdown fences.

Required schema (echo locked fields verbatim from the user payload):
{{
  "fdc_id": "same fdc_id as input",
  "retail_type": "<from locked_identity>",
  "category_path": "<from locked_identity>",
  "product_identity": "<from locked_identity>",
  "canonical_path": "<from locked_identity>",
  "canonical_label": "Product Identity (Variant, Flavor, Form, Processing, Claims)",
  "variant": [],
  "flavor": [],
  "form_texture_cut": [],
  "processing_storage": [],
  "claims": [],
  "components": [
    {{"identity":"Title Case", "role":"main|protein|base|sauce|topping|side|filling|included_item|ingredient|bread|cheese|fruit|unknown",
      "variant":[], "flavor":[], "form_texture_cut":[], "processing_storage":[], "claims":[]}}
  ],
  "confidence": 0.0,
  "mint_required": false,
  "review_flags": [],
  "rationale": "one short sentence",
  "tree_paths": [
    "Retail Taxonomy > category_path > product_identity",
    "Retail Taxonomy > category_path > product_identity > @variant > value",
    "Retail Taxonomy > category_path > product_identity > @components > normalized_component_identity"
  ]
}}
"""


def build_prompt_identity(row: dict[str, str]) -> list[dict[str, str]]:
    source = compact_source_row(row)
    paths = candidate_paths(row)
    user_payload = {
        "source_row": source,
        "candidate_paths_from_existing_pipeline": paths,
        "reminder": "Pass 1: identity only. Return ONLY the identity-pass JSON object.",
    }
    return [
        {"role": "system", "content": SYSTEM_PROMPT_IDENTITY},
        {"role": "user", "content": json.dumps(user_payload, indent=2, sort_keys=True)},
    ]


def build_prompt_facets(row: dict[str, str], identity_record: dict[str, object]) -> list[dict[str, str]]:
    source = compact_source_row(row)
    paths = candidate_paths(row)
    locked = {
        "retail_type": identity_record.get("retail_type"),
        "category_path": identity_record.get("category_path"),
        "product_identity": identity_record.get("product_identity"),
        "canonical_path": identity_record.get("canonical_path"),
        "mint_required": identity_record.get("mint_required"),
        "confidence_from_pass_1": identity_record.get("confidence"),
        "review_flags_from_pass_1": identity_record.get("review_flags", []),
    }
    user_payload = {
        "source_row": source,
        "candidate_paths_from_existing_pipeline": paths,
        "locked_identity": locked,
        "reminder": "Pass 2: fill facets and components. Echo locked_identity verbatim. Do NOT change product_identity, category_path, canonical_path, retail_type, or mint_required.",
    }
    return [
        {"role": "system", "content": SYSTEM_PROMPT_FACETS},
        {"role": "user", "content": json.dumps(user_payload, indent=2, sort_keys=True)},
    ]


SYSTEM_PROMPT_LEGACY = f"""You are a retail grocery taxonomy adjudicator.

Your job is to convert one messy retail SKU row into a stable taxonomy record for a traversible product tree.

Tree model:
Retail Taxonomy
  Department
    Category
      Product Identity
        @variant
        @flavor
        @form_texture_cut
        @processing_storage
        @claims
        @components

Core question:
What is the shopper buying?

Do not classify the nutrition database ingredient. Do not classify only one component. Classify the retail SKU.

Evidence priority:
1. Product title
2. Full ingredient list and top ingredients
3. Branded food category
4. Parser fields, n-grams, role candidates
5. Existing ESHA/current semantic/candidate paths

Existing mappings are clues, not truth. Override them when title plus ingredients prove a different retail product.

Decision process:
1. Decide retail_type.
2. Decide product_identity using the grocery-list test: "If this were on a grocery list, what would a normal shopper expect in the cart?"
3. Decide category_path as Department > Category only.
4. Build canonical_path exactly as category_path > product_identity.
5. Put modifiers into facets, never into canonical_path.
6. Add components only for separable/named meal parts or component-level traits.

Canonical category routing hints:
Use these category_path values when product_identity matches. If the SKU clearly belongs to one of these identities, do not copy a broader or wrong source category.
{canonical_category_hint_text()}

Important identity rules:
- If the SKU is a prepared dish, meal, sandwich, wrap, bowl, kit, starter, parfait, combo, or mixed pack, keep that whole item as the product identity.
- Product forms like Meal Starter, Dinner Kit, Salad Kit, Sauce Mix, Seasoning Mix, Pizza Crust Mix, Cheese Crisps, Protein Parfait, Breakfast Sandwich, and Flatbread Sandwich are real shopper-facing identities.
- Never collapse a prepared SKU into sauce, cheese, chicken, beans, salsa, pasta, bread, sausage, egg, cereal, crust, or another component unless the SKU itself is that standalone item.
- If ingredients reveal a carrier/form missing from the title, such as roll, tortilla, flatbread, crust, bowl, or sandwich bread, use that evidence and add review flag title_identity_inferred_from_ingredients.
- If a generic identity is clearly all the source proves, keep the generic identity and add specificity as facets/review flags. Example: Hard Aged Cheese means product_identity="Cheese", variant=["aged"], form_texture_cut=["hard"], review_flags=["specific_identity_missing"]. Do not guess Parmesan, Pecorino, or Asiago without evidence.
- If the product identity is not proven, use retail_type="unknown", category_path="Other > Needs Review", product_identity="Unknown Product", confidence<=0.50, mint_required=false, and review_flags including insufficient_identity_evidence.
- Do not inherit claims from conflicting ESHA/current_esha_desc when product title/category/ingredients do not make that claim. Example: stale ESHA "low calorie" does not make the retail SKU low_calorie.
- COMPOUND IDENTITY RULE: when the title contains a compound noun phrase that names a recognized shopper-facing product category (Broccoli Cheddar Soup, Tomato Basil Soup, Chicken Noodle Soup, Pumpkin Spice Latte, Pineapple Coconut Water, Spinach Artichoke Dip), use the WHOLE compound as product_identity — do NOT split into a generic identity with the modifiers as variant. Example: title "Creamy Cheddar Broccoli Soup" -> product_identity="Broccoli Cheddar Soup", variant=[], form_texture_cut=[] (the word "creamy" is descriptive marketing, not a SKU-distinguishing facet), category_path="Pantry > Soup". Do NOT output product_identity="Soup" with variant=["broccoli_cheddar"].
- When ingredient evidence shows the product contains the head noun referenced in the gold canonical hint table (see Canonical category routing hints above), prefer the hinted compound identity even when the title leads with marketing words.

Facet rules:
- variant = subtype/style/protein/variety that changes selection but is not the identity.
- flavor = taste notes only, such as chocolate, vanilla, cajun, hickory, hatch_green_chile, basil.
- form_texture_cut = physical state, shape, cut, texture, presentation, such as diced, whole_peeled, flatbread, hard, soft, firm, semi_soft, crumbled, sliced, shredded.
- processing_storage = frozen, canned, dried, smoked, shelf_stable, ready_to_eat, fully_cooked. Do NOT include processing tokens that describe how the product type is normally made (pretzels are baked; do not output processing=["baked"] unless the title explicitly says baked).
- claims = dietary/nutrition/marketing claims only.
- Claims are never flavors.
- Top-level facets describe the whole SKU. If only a component has a trait, put the trait on that component.
- Do not put the product identity itself into form_texture_cut. Example: Breakfast Sandwich should not have form_texture_cut=["sandwich"]; use form_texture_cut=["flatbread"] only if flatbread is the carrier/presentation.
- Keep useful named filling combinations together when shoppers would say them together. Example: egg white plus cheddar in a breakfast sandwich should be egg_white_cheddar, not separate egg_white and cheddar variants.
- Put fully_cooked on a component when only that component is fully cooked. Do not put fully_cooked on the whole SKU unless the whole retail item is sold as fully cooked/ready to eat.
- TEXTURE BELONGS IN form_texture_cut, NOT variant. The words hard, soft, firm, semi_soft, semi_firm, crumbly, smooth, creamy, chunky describe texture and go in form_texture_cut. They are NEVER variants. Example: title "Hard Aged Cheese" -> identity="Cheese", variant=["aged"], form_texture_cut=["hard"]. Title "Creamy Cheddar Broccoli Soup" -> the word "creamy" is descriptive marketing — leave it OUT of all facets.
- REGIONAL/NAMED FLAVOR ACCENTS STAY IN flavor AND DO NOT MERGE INTO variant. Tokens like hatch_green_chile, jalapeno, chipotle, sriracha, buffalo, ranch, honey_mustard, bbq, cajun, garlic_herb are flavor accents. The base ingredient (asiago, cheddar, etc.) is the variant. Example: title "Hatch Green Chile Asiago Cheese Crisps" -> identity="Cheese Crisps", variant=["asiago"], flavor=["hatch_green_chile"]. NEVER output variant=["hatch_green_chile_asiago"]. NEVER concatenate the flavor onto the variant.
- DO NOT APPEND COMPONENT-CATEGORY WORDS TO A VARIANT WHEN THE COMPONENT TYPE IS ALREADY NAMED. Example: title "Red Pepper Feta Chicken Burger" -> variant=["red_pepper_feta"], NOT variant=["red_pepper_feta_cheese"]. Feta is a cheese; do not re-state "cheese". Same rule for "_meat", "_sauce", "_bread" suffixes when the named token already implies it.

Claims must use this order, not alphabetical order:
{claim_order_text()}

Component rules:
- Components are not ingredient dumps.
- Use components for named/separable meal parts, included items, or component-level traits.
- Component identity uses Title Case.
- Component role and all component facet values use snake_case.
- Do not repeat a component identity as that component's variant. Example: component identity "Cheddar Cheese" has variant=[]; do not set variant=["cheddar"]. Component identity "Multi-Grain Flatbread" has variant=[]; do not set variant=["multi_grain"].
- COMPONENT IDENTITY MUST BE THE CANONICAL FOOD NOUN, NOT THE INGREDIENT LINE PHRASING. Strip preparation phrases ("In Sauce", "Dices", "Strips", "Crumbles", "Chunks", "Pieces"), kit-internal labels ("Topping"), and brand wording. Examples:
  - ingredient line "Apple Dices In Sauce" -> component identity "Apple" (form_texture_cut on the component is ["diced"] if you need the cut).
  - ingredient line "Sesame Garlic Chicken Breast Strips" inside a meal kit -> component identity "Chicken" with variant=["sesame_garlic"] on the component if needed.
  - ingredient line "Cinnamon Granola Topping" -> component identity "Granola Topping" (the word "Cinnamon" is component-level flavor: component.flavor=["cinnamon"]).
  - ingredient line "Apple Dices In Sauce With Cinnamon" -> component identity "Apple", component.form_texture_cut=["diced"], component.flavor=["cinnamon"].
- DISTINCTIVE-INGREDIENT VARIANT PROMOTION: when a top-level variant token names a primary distinguishing ingredient (e.g., almond_flour for tortillas, oat_milk for creamers, hemp_seed for energy bars, coconut_milk for ice cream), ALSO emit that ingredient as a top-level component with role="ingredient". Example: "Almond Flour Tortillas" -> identity="Tortillas", variant=["almond_flour"], components=[{{"identity":"Almond Flour","role":"ingredient","variant":[],"flavor":[],"form_texture_cut":[],"processing_storage":[],"claims":[]}}].
- For meal kits, dinner kits, salad kits, meal starters: components list the simple food nouns the shopper sees on the box (Chicken, Rice Noodles, Vegetables, Sauce, Tortillas, Spice Packet), NOT the full ingredient phrasing. Compress "Sesame Garlic Chicken Breast Strips" to component identity "Chicken".
- Do not include the SKU's primary identity itself as a component. A Tomatoes SKU does NOT have a "Tomatoes" component. A Soup SKU named "Broccoli Cheddar Soup" does NOT have a "Soup" component (but DOES have "Broccoli" and "Cheddar Cheese" components since those are separable meal parts).
- Do not promote a flavor accent to a component on its own. Example: a Tomatoes SKU with basil ingredient -> flavor=["basil"], components=[]. Do NOT emit components=[{{"identity":"Basil","role":"ingredient"}}].

Facet placement examples:
- "Chicken Apple Sausage, Egg White & Cheddar served on Multi-Grain Flatbread" is product_identity="Breakfast Sandwich", category_path="Frozen > Breakfast Sandwiches", variant=["chicken_apple_sausage","egg_white_cheddar"], form_texture_cut=["flatbread"], processing_storage=["frozen"], claims=[].
- In that breakfast sandwich example, do not use form_texture_cut=["sandwich"], because Sandwich is already the product identity.
- In that breakfast sandwich example, do not use variant=["egg_white","cheddar","multi_grain_flatbread"]. Egg White & Cheddar is one named filling variant; flatbread is the carrier/form.
- In that breakfast sandwich example, do not use variant=["chicken_apple_sausage_egg_white_cheddar"]. The protein phrase and egg/cheese phrase are separate useful selection facets.
- In that breakfast sandwich example, fully_cooked belongs on Chicken Apple Sausage Patty if present in ingredients; it is not a top-level processing_storage value for the whole SKU.
- In that breakfast sandwich example, the chicken component identity is Chicken Apple Sausage Patty, not Chicken Sausage Patty with variant=["chicken_apple_sausage"]. Keep "apple" in the component identity because the ingredient says Chicken Sausage Patty with Apples.

Output derivation rules:
- canonical_label must be Product Identity plus top-level facet display values in this exact order: variant, flavor, form_texture_cut, processing_storage, claims.
- canonical_label displays snake_case facet values as Title Case words, e.g. egg_white_cheddar becomes Egg White Cheddar.
- canonical_label must include every top-level facet value. If processing_storage=["frozen"], canonical_label must include Frozen.
- canonical_label must be generated from the arrays, not copied from the title. Do not use &, slashes, or raw title punctuation in canonical_label.
- tree_paths must be exactly derived from canonical_path and top-level facets/components.
- Use exact facet group names in tree_paths: @variant, @flavor, @form_texture_cut, @processing_storage, @claims, @components.
- Never use @form or @processing in tree_paths.
- Component tree path values are normalized component identities, e.g. Chicken Apple Sausage Patty becomes chicken_apple_sausage_patty.

Formatting rules:
- Output strict JSON only. The first character must be {{ and the last character must be }}.
- No markdown fences. No ```json. No commentary.
- Use snake_case for all facet values and component roles.
- Use Title Case for product_identity, component identity, category labels, and path labels.
- Do not include brands, package sizes, claims, flavors, cuts, storage, or @facet nodes in canonical_path.

Required schema:
{schema_text()}
"""


FEW_SHOT_EXAMPLES = """
Worked example 1 (compound identity, override bad ESHA, components with roles, flavor accent on a component):
INPUT: title="CINNAMON GRANOLA TOPPING + APPLE DICES IN SAUCE + COCONUT PUDDING PROTEIN PARFAIT", branded_food_category="Yogurts", ingredients=["Coconut Pudding", "Apple Dices In Sauce", "Cinnamon Granola Topping", ...]
OUTPUT:
{
  "fdc_id": "...",
  "retail_type": "composite_dish",
  "category_path": "Meal > Composite Dishes",
  "product_identity": "Parfait",
  "canonical_path": "Meal > Composite Dishes > Parfait",
  "canonical_label": "Parfait (Cinnamon, Apple, Coconut, High Protein)",
  "variant": [], "flavor": ["cinnamon","apple","coconut"],
  "form_texture_cut": [], "processing_storage": [], "claims": ["high_protein"],
  "components": [
    {"identity":"Granola Topping","role":"topping","variant":[],"flavor":["cinnamon"],"form_texture_cut":[],"processing_storage":[],"claims":[]},
    {"identity":"Apple","role":"fruit","variant":[],"flavor":[],"form_texture_cut":["diced"],"processing_storage":[],"claims":[]},
    {"identity":"Coconut Pudding","role":"base","variant":[],"flavor":[],"form_texture_cut":[],"processing_storage":[],"claims":[]}
  ],
  "confidence": 0.92, "mint_required": false, "review_flags": [], "rationale": "Parfait composite; protein is implicit claim.",
  "tree_paths": ["Retail Taxonomy > Meal > Composite Dishes > Parfait", "...etc"]
}
Notes: Drop "Protein" prefix (it's the high_protein claim, not a variant). Component identities are CANONICAL FOOD NOUNS — strip "Cinnamon" prefix and "Dices In Sauce" suffix. Cinnamon goes on the granola component as flavor; "diced" goes on apple as form_texture_cut.

Worked example 2 (variant compounding, form vs identity, component-level processing, frozen authorized by BFC):
INPUT: title="CHICKEN APPLE SAUSAGE, EGG WHITE & CHEDDAR ON MULTI-GRAIN FLATBREAD BREAKFAST SANDWICH", branded_food_category="Frozen Breakfast Sandwiches"
OUTPUT:
{
  "fdc_id": "...",
  "retail_type": "single",
  "category_path": "Frozen > Breakfast Sandwiches",
  "product_identity": "Breakfast Sandwich",
  "canonical_path": "Frozen > Breakfast Sandwiches > Breakfast Sandwich",
  "canonical_label": "Breakfast Sandwich (Chicken Apple Sausage, Egg White Cheddar, Flatbread, Frozen)",
  "variant": ["chicken_apple_sausage","egg_white_cheddar"],
  "flavor": [], "form_texture_cut": ["flatbread"], "processing_storage": ["frozen"], "claims": [],
  "components": [
    {"identity":"Chicken Apple Sausage Patty","role":"protein","variant":[],"flavor":[],"form_texture_cut":[],"processing_storage":["fully_cooked"],"claims":[]},
    {"identity":"Egg White","role":"protein","variant":[],"flavor":[],"form_texture_cut":[],"processing_storage":[],"claims":[]},
    {"identity":"Cheddar Cheese","role":"cheese","variant":[],"flavor":[],"form_texture_cut":[],"processing_storage":[],"claims":[]},
    {"identity":"Multi-Grain Flatbread","role":"bread","variant":[],"flavor":[],"form_texture_cut":[],"processing_storage":[],"claims":[]}
  ],
  "confidence": 0.94, "mint_required": true, "review_flags": [], "rationale": "Breakfast sandwich with named filling combos; flatbread is the carrier.",
  "tree_paths": ["..."]
}
Notes: Egg White & Cheddar is ONE named filling combo (egg_white_cheddar), not two separate variants. Flatbread is form, not identity. fully_cooked is on the sausage patty component, NOT top-level. "Frozen" is authorized by BFC "Frozen Breakfast Sandwiches".
"""

SYSTEM_PROMPT = f"""You are a retail SKU taxonomy adjudicator. Convert one SKU row into a stable taxonomy record.

GROCERY-LIST TEST: What would a normal shopper expect in their cart? That is product_identity. Never a single ingredient, flavor accent, or marketing claim.

EVIDENCE PRIORITY (override lower with higher):
1. title  2. ingredient list  3. branded_food_category  4. current_esha_desc (often stale — verify before inheriting claims)
Ignore entirely: title_ngrams_json, role_candidates_json, semantic_*, candidate paths. They are frequently wrong; do NOT use them as anchors.

CANONICAL CATEGORY ROUTING (use these category_paths when product_identity matches):
{canonical_category_hint_text()}

HARD RULES:
- Compound identity: keep recognized compounds whole — Broccoli Cheddar Soup, Tomato Basil Soup, Pineapple Coconut Water, Spinach Artichoke Dip, Breakfast Sandwich, Pizza Crust Mix, Cheese Crisps, Meal Starter. Do NOT split into generic + variant.
- Texture (hard, soft, firm, semi_soft, crumbly, creamy, chunky) -> form_texture_cut. NEVER variant.
- Regional / named flavor accents (hatch_green_chile, jalapeno, chipotle, sriracha, buffalo, ranch, honey_mustard, bbq, cajun, basil) -> flavor. Base ingredient (asiago, cheddar) -> variant. NEVER concatenate flavor onto variant.
- Drop marketing prefixes (Premium, Creamy, Classic, Original, Protein) from product_identity. "Protein" implies claims=["high_protein"], not variant.
- Generic-when-unproven: "Hard Aged Cheese" -> identity="Cheese", variant=["aged"], form_texture_cut=["hard"]. Do NOT guess Parmesan/Pecorino without evidence.
- processing_storage: "frozen", "canned", "shelf_stable" require EXPLICIT evidence in title or branded_food_category. Do NOT add baked/roasted/toasted just because the product type implies them.
- Components: emit them for prepared/composite SKUs (sandwiches, burgers, parfaits, soups with named ingredients, dips with named ingredients, breakfast sandwiches, kits, starters, combos). Also for distinctive-ingredient promotion (almond_flour tortillas -> Almond Flour component). For purely single ingredient SKUs (Cookies, Cheese, Tortillas without distinctive_ingredient, Coconut Water, Pretzels, Tomatoes, Chicken Broth, Seasoning), components=[].
- "X with Y" or "X & Y" in title where Y is a flavor accent: Y goes to flavor, NOT to variant. Example: "Whole Peeled Tomatoes With Basil" -> flavor=["basil"], NOT variant=["with_basil"].
- CONSOLIDATION RULE (CRITICAL): The product_identity MUST come from the canonical hint table above when any entry matches. Do NOT invent synonyms — if "TV Dinner" is in the hint table, do not emit "Frozen Dinner" / "Frozen Meal" / "Meatloaf Dinner" instead. Do NOT invent flavor-specific identities (a chocolate-flavored bar's identity is still the bar category from the hint table; "chocolate" is a flavor, not part of the identity). The hint table is the canonical set of nodes — variations always go in variant/flavor/form/processing/claims, never as a new identity.
- BARE-GENERIC IDENTITIES ARE FORBIDDEN. Do NOT emit product_identity = "Bar" or "Bars" alone — pick the SUBTYPE from the title: "Protein Bar" in title -> "Protein Bars"; "Energy Bar" / "Endurance" / "Performance" -> "Energy Bars"; "Granola Bar" -> "Granola Bars"; "Nutrition Bar" -> "Nutrition Bars"; "Cereal Bar" / "Fruit & Grain" / "Fiber Bar" -> "Cereal Bars"; "Fruit Bar" / "Fruit & Nut" -> "Fruit Bars"; "Cookie Bar" -> "Cookie Bars"; "Yogurt Bar" -> "Yogurt Bars"; "Marshmallow Squares" / "Crispy Squares" -> "Marshmallow Squares"; "Energy Gel" -> "Energy Gels". Always pick the most specific subtype.
- Do NOT emit product_identity = "Candy" alone — pick the SUBTYPE from title/ingredients: marshmallow -> "Marshmallows"; gummi/gummy -> "Gummy Candy"; jelly bean -> "Jelly Beans"; lollipop / ring pop -> "Lollipops"; bubble gum -> "Bubble Gum"; licorice -> "Licorice"; truffle -> "Truffle"; bark -> "Bark"; toffee -> "Toffee"; fudge -> "Fudge"; cotton candy -> "Cotton Candy"; taffy / caramel -> "Caramel Candy"; fruit snack -> "Fruit Snacks"; peanut butter cup / chocolate egg / chocolate candy -> "Chocolate Candy"; peppermint patti -> "Chocolate Candy"; spice drops / imperials / discs / barrels / balls / drops / mints / hard candy -> "Hard Candy"; sour candy -> "Sour Candy"; candied ginger / orange slices -> "Candied Fruit". The bare word "Candy" is never a valid identity.
- Component identity = CANONICAL FOOD NOUN. Strip prep suffixes ("In Sauce", "Strips", "Dices", "Pieces", "Crumbles", "Chunks") and pure flavor prefixes ("Cinnamon ", "Spicy ", "Honey ", "Buttery ", "Sweet ", "Garlic "). KEEP "Smoked"/"Roasted"/"Toasted" — those define a distinct food noun ("Smoked Ham" is its own product).
- Component role: use "ingredient" for distinctive-ingredient promotions and ingredient-component cases (Spinach+Artichoke in dip, Broccoli+Cheddar Cheese in soup, Almond Flour in tortillas). Use "main", "protein", "base", "topping", "filling", "bread", "cheese", "fruit", "side", "included_item" for meal-kit/composite parts.

{FEW_SHOT_EXAMPLES}

FINAL CHECK before you output product_identity (read this last; this is universal, not just for candy or bars):

Imagine handing your shopping list to a friend. Read your product_identity out loud as: "Get me ___."

Right granularity (the shopping-list level — what a normal person says out loud at the store):
  ✓ "Get me hard candy"          -> Hard Candy
  ✓ "Get me gummy candy"         -> Gummy Candy
  ✓ "Get me a protein bar"       -> Protein Bars
  ✓ "Get me chocolate milk"      -> Chocolate Milk
  ✓ "Get me milk"                -> Milk (when SKU is plain milk)
  ✓ "Get me yogurt"              -> Yogurt
  ✓ "Get me eggnog"              -> Eggnog
  ✓ "Get me tortillas"           -> Tortillas
  ✓ "Get me sourdough bread"     -> Sourdough Bread
  ✓ "Get me trail mix"           -> Trail Mix
  ✓ "Get me chicken broth"       -> Chicken Broth

Too GENERIC — your friend can't shop with this:
  ✗ "Get me candy"               <- rejected, pick a subtype
  ✗ "Get me a bar"               <- rejected, pick a subtype
  ✗ "Get me a beverage"          <- rejected, pick a subtype
  ✗ "Get me a snack"             <- rejected, pick a subtype
  ✗ "Get me chocolate"           <- rejected when the SKU is a chocolate bar (Chocolate Bar) or chocolate milk (Chocolate Milk)
  ✗ "Get me bread"               <- rejected when the SKU is a specific bread type (Sourdough Bread, Bagels, etc.)
  ✗ "Get me cereal"              <- rejected, pick the right subtype (Granola, Hot Cereal, etc.)

Too PRECISE — that's the SKU title, not the shopping-list level:
  ✗ "Get me Hershey's Milk Chocolate Sea Salt 1.5oz"   (variant/flavor/size live in facets, not identity)
  ✗ "Get me whole wheat sourdough multigrain artisan loaf"
  ✗ "Get me a chocolate peanut butter whey protein bar"   (Protein Bars + flavor=chocolate_peanut_butter)
  ✗ "Get me a Dutch coffee-flavored hard candy"          (Hard Candy + flavor=coffee + variant=dutch)

Self-check: if your rationale names a specific subtype (e.g., "this is a hard candy", "this is a granola bar", "this is chocolate milk"), USE THAT SUBTYPE as the product_identity. Do not retreat to a generic word. Your rationale and your identity must agree.

OUTPUT FORMAT:
- canonical_label = "Product Identity (Variant, Flavor, Form, Processing, Claims)" — Title Case display values in this exact facet order. NO "&", slashes, or raw title punctuation.
- claims order: {claim_order_text()}
- tree_paths: derive from canonical_path + facets + components. Use exact group names @variant, @flavor, @form_texture_cut, @processing_storage, @claims, @components. NEVER @form or @processing.
- Return strict JSON only. Schema: fdc_id, retail_type, category_path, product_identity, canonical_path, canonical_label, variant, flavor, form_texture_cut, processing_storage, claims, components, confidence, mint_required, review_flags, rationale, tree_paths. snake_case for facet values; Title Case for product_identity, component identity, category labels.
"""


def build_prompt(row: dict[str, str]) -> list[dict[str, str]]:
    source = compact_source_row(row)
    paths = candidate_paths(row) if not _LEAN_EVIDENCE_MODE else []
    user_payload = {
        "source_row": source,
    }
    if paths:
        user_payload["candidate_paths_from_existing_pipeline_DO_NOT_TRUST"] = paths
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(user_payload, indent=2, sort_keys=True)},
    ]


def read_jsonl(path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def write_jsonl(path: Path, rows: Iterable[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def load_rows_by_fdc(path: Path, wanted_fdc: set[str]) -> dict[str, dict[str, str]]:
    found: dict[str, dict[str, str]] = {}
    with path.open(newline="", errors="replace") as handle:
        for row in csv.DictReader(handle):
            fdc_id = row.get("fdc_id", "")
            if fdc_id in wanted_fdc and fdc_id not in found:
                found[fdc_id] = row
            if len(found) == len(wanted_fdc):
                break
    return found


# Sidecar mapping: fixture fdc_id -> real CSV fdc_id. Built by find_fixture_evidence
# tooling. When a case's source.fdc_id is a synthetic "*_fixture" id, we graft the
# rich evidence from the real row but keep the fixture's title/bfc/fdc_id so the
# gold expected record still applies.
DEFAULT_FIXTURE_EVIDENCE_MAP = V2 / "fixture_real_evidence_map.json"

# Fields we copy from the real row onto the fixture source. We keep title,
# branded_food_category, and fdc_id from the fixture; everything else that
# carries evidence comes from the real row.
EVIDENCE_GRAFT_FIELDS = [
    "current_esha",
    "current_esha_desc",
    "retail_leaf",
    "ing_full",
    "ing_top5",
    "ing_categories",
    "protein_source",
    "dairy_source",
    "grain_source",
    "sweetener_source",
    "oil_source",
    "distinctive_tokens",
    "distinctive_bigrams",
    "title_ngrams_json",
    "role_candidates_json",
    "product_form_guess",
    "modifier_guesses",
    "ingredient_guesses",
    "form_word_in_title",
    "form_word_in_esha",
    "form_word_in_bfc",
    "llm_evidence_block",
    "semantic_retail_type",
    "semantic_category_path",
    "semantic_product_identity",
    "semantic_canonical_path",
    "semantic_canonical_label",
    "semantic_review_flags",
    "source_parser_primary_food",
    "source_parser_form",
    "source_parser_flavor",
]


def load_fixture_evidence_map(path: Path | None) -> dict[str, str]:
    candidate = path or DEFAULT_FIXTURE_EVIDENCE_MAP
    if not candidate or not candidate.exists():
        return {}
    try:
        data = json.loads(candidate.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"warning: failed to read fixture map {candidate}: {exc}")
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): str(v) for k, v in data.items() if k and v}


def graft_evidence(fixture_source: dict[str, object], real_row: dict[str, str]) -> dict[str, object]:
    """Return a row dict that uses fixture title/bfc/fdc_id but real ingredient evidence."""
    grafted: dict[str, object] = {}
    # Start with whatever the fixture source provides (title, bfc, fdc_id, etc.)
    for k, v in fixture_source.items():
        grafted[k] = v
    # Layer real-row evidence under EVIDENCE_GRAFT_FIELDS, but never overwrite
    # title, branded_food_category, or fdc_id.
    for field_name in EVIDENCE_GRAFT_FIELDS:
        value = real_row.get(field_name)
        if value not in (None, ""):
            grafted[field_name] = value
    # Ensure preserved fields stay from fixture
    for keep in ("fdc_id", "title", "branded_food_category"):
        if fixture_source.get(keep):
            grafted[keep] = fixture_source[keep]
    return grafted


def build_requests_from_gold(
    gold_path: Path,
    input_path: Path,
    case_filters: set[str] | None = None,
    fixture_map_path: Path | None = None,
) -> list[dict[str, object]]:
    cases = read_jsonl(gold_path)
    if case_filters:
        cases = [
            case
            for case in cases
            if case.get("name") in case_filters or str(case.get("source", {}).get("fdc_id", "")) in case_filters
        ]
    fixture_map = load_fixture_evidence_map(fixture_map_path)
    # Wanted set includes BOTH the fixture-source fdc_ids (in case they really exist
    # in the CSV) and the mapped real fdc_ids that supply evidence.
    wanted: set[str] = set()
    for case in cases:
        case_fdc = str(case.get("source", {}).get("fdc_id", ""))
        if case_fdc:
            wanted.add(case_fdc)
        mapped = fixture_map.get(case_fdc)
        if mapped:
            wanted.add(str(mapped))
    rows_by_fdc = load_rows_by_fdc(input_path, wanted)
    requests: list[dict[str, object]] = []
    for case in cases:
        source = dict(case["source"])
        fdc_id = str(source.get("fdc_id", ""))
        # Decide which row supplies evidence
        real_fdc = fixture_map.get(fdc_id)
        evidence_source_fdc = ""
        if fdc_id in rows_by_fdc:
            row = rows_by_fdc[fdc_id]
        elif real_fdc and real_fdc in rows_by_fdc:
            row = graft_evidence(source, rows_by_fdc[real_fdc])
            evidence_source_fdc = real_fdc
        else:
            row = source
        requests.append(
            {
                "case": case["name"],
                "fdc_id": fdc_id,
                "evidence_source_fdc": evidence_source_fdc,
                "messages": build_prompt(row),
                "expected": case["expected"],
            }
        )
    return requests


def extract_json_object(text: str) -> dict[str, object]:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("no JSON object found")
    return json.loads(match.group(0))


def is_rate_limit_error(exc: Exception) -> bool:
    status_code = getattr(exc, "status_code", None)
    return status_code == 429 or "rate limit" in str(exc).lower()


def create_completion_with_retries(
    client: object,
    request: dict[str, object],
    model: str,
    retry_attempts: int,
    retry_base_seconds: float,
) -> object:
    for attempt in range(retry_attempts + 1):
        try:
            return client.chat.completions.create(
                model=model,
                messages=request["messages"],
                temperature=0.0,
                max_tokens=1200,
                response_format={"type": "json_object"},
            )
        except Exception as exc:
            if not is_rate_limit_error(exc) or attempt >= retry_attempts:
                raise
            delay = retry_base_seconds * (2**attempt)
            print(f"rate limited; retrying in {delay:.1f}s")
            time.sleep(delay)
    raise RuntimeError("unreachable retry loop")


def run_live(
    requests: list[dict[str, object]],
    model: str,
    output_path: Path,
    pause_seconds: float = 0.0,
    retry_attempts: int = 0,
    retry_base_seconds: float = 10.0,
) -> list[dict[str, object]]:
    api_key = os.environ.get("NEBIUS_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("NEBIUS_API_KEY is not set")
    from openai import OpenAI  # Imported only for live runs.

    client = OpenAI(api_key=api_key, base_url="https://api.studio.nebius.com/v1/")
    outputs: list[dict[str, object]] = read_jsonl(output_path) if output_path.exists() else []
    completed = {str(output.get("case", "")) for output in outputs if output.get("case")}
    for request in requests:
        case_name = str(request.get("case", ""))
        if case_name in completed:
            print(f"skip existing output: {case_name}")
            continue
        try:
            response = create_completion_with_retries(client, request, model, retry_attempts, retry_base_seconds)
            raw = response.choices[0].message.content or ""
            try:
                parsed = extract_json_object(raw)
            except ValueError as parse_exc:
                print(f"  parse error on {case_name}: {parse_exc} (continuing)")
                parsed = {"_parse_error": str(parse_exc), "_raw_preview": raw[:200]}
            outputs.append({"case": case_name, "fdc_id": request.get("fdc_id", ""), "raw": raw, "record": parsed})
        except Exception as exc:
            print(f"  API error on {case_name}: {type(exc).__name__}: {exc} (continuing)")
            outputs.append({
                "case": case_name,
                "fdc_id": request.get("fdc_id", ""),
                "raw": "",
                "record": {"_api_error": f"{type(exc).__name__}: {exc}"},
            })
        completed.add(case_name)
        write_jsonl(output_path, outputs)
        print(f"wrote live output: {case_name}")
        if pause_seconds > 0:
            time.sleep(pause_seconds)
    return outputs


def run_live_two_pass(
    gold_path: Path,
    input_path: Path,
    case_filters: set[str] | None,
    fixture_map_path: Path | None,
    model: str,
    output_path: Path,
    pause_seconds: float = 0.0,
    retry_attempts: int = 0,
    retry_base_seconds: float = 10.0,
) -> list[dict[str, object]]:
    """Two-pass run: pass 1 returns identity; pass 2 returns facets/components.

    The two pass results are merged into one record per case (the same shape as
    the single-pass record) so all downstream scoring/normalizing works
    unchanged. Each row is also stored with `pass1_record` and `pass2_record`
    so we can debug what each prompt produced.
    """
    api_key = os.environ.get("NEBIUS_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("NEBIUS_API_KEY is not set")
    from openai import OpenAI

    client = OpenAI(api_key=api_key, base_url="https://api.studio.nebius.com/v1/")

    cases = read_jsonl(gold_path)
    if case_filters:
        cases = [
            case for case in cases
            if case.get("name") in case_filters or str(case.get("source", {}).get("fdc_id", "")) in case_filters
        ]
    fixture_map = load_fixture_evidence_map(fixture_map_path)
    wanted: set[str] = set()
    for case in cases:
        case_fdc = str(case.get("source", {}).get("fdc_id", ""))
        if case_fdc:
            wanted.add(case_fdc)
        mapped = fixture_map.get(case_fdc)
        if mapped:
            wanted.add(str(mapped))
    rows_by_fdc = load_rows_by_fdc(input_path, wanted)

    outputs: list[dict[str, object]] = read_jsonl(output_path) if output_path.exists() else []
    completed = {str(o.get("case", "")) for o in outputs if o.get("case")}

    for case in cases:
        case_name = case["name"]
        if case_name in completed:
            print(f"skip existing output: {case_name}")
            continue
        source = dict(case["source"])
        fdc_id = str(source.get("fdc_id", ""))
        real_fdc = fixture_map.get(fdc_id)
        if fdc_id in rows_by_fdc:
            row = rows_by_fdc[fdc_id]
        elif real_fdc and real_fdc in rows_by_fdc:
            row = graft_evidence(source, rows_by_fdc[real_fdc])
        else:
            row = source

        # Pass 1: identity
        msgs1 = build_prompt_identity(row)
        resp1 = create_completion_with_retries(
            client, {"messages": msgs1}, model, retry_attempts, retry_base_seconds
        )
        raw1 = resp1.choices[0].message.content or ""
        try:
            id_record = extract_json_object(raw1)
        except Exception as exc:
            print(f"pass1 parse error on {case_name}: {exc}")
            id_record = {}

        # Pass 2: facets, given locked identity
        msgs2 = build_prompt_facets(row, id_record)
        resp2 = create_completion_with_retries(
            client, {"messages": msgs2}, model, retry_attempts, retry_base_seconds
        )
        raw2 = resp2.choices[0].message.content or ""
        try:
            facet_record = extract_json_object(raw2)
        except Exception as exc:
            print(f"pass2 parse error on {case_name}: {exc}")
            facet_record = {}

        # Merge: pass 2 already echoes locked identity fields, but if the model
        # drifts we re-overwrite from pass 1 to keep them locked.
        merged = dict(facet_record)
        for k in ("retail_type", "category_path", "product_identity", "canonical_path", "mint_required"):
            if id_record.get(k) is not None:
                merged[k] = id_record[k]
        merged.setdefault("fdc_id", fdc_id)

        outputs.append({
            "case": case_name,
            "fdc_id": fdc_id,
            "raw_pass1": raw1,
            "raw_pass2": raw2,
            "pass1_record": id_record,
            "pass2_record": facet_record,
            "record": merged,
        })
        completed.add(case_name)
        write_jsonl(output_path, outputs)
        print(f"wrote two-pass output: {case_name}")
        if pause_seconds > 0:
            time.sleep(pause_seconds)
    return outputs


def model_slug(model: str) -> str:
    return normalize_token(model) or "model"


def score_outputs(path: Path, gold_path: Path, requested_cases: Iterable[str]) -> dict[str, object]:
    requested = list(requested_cases)
    sources_by_case = {}
    expected_by_case = {}
    for case in read_jsonl(gold_path):
        sources_by_case[case["name"]] = case["source"]
        expected_by_case[case["name"]] = case["expected"]

    rows = read_jsonl(path) if path.exists() else []
    by_case = {str(output.get("case", "")): output for output in rows}
    case_results: list[dict[str, object]] = []
    core_passed = 0
    exact_passed = 0
    for case_name in requested:
        output = by_case.get(case_name)
        if not output:
            case_results.append(
                {
                    "case": case_name,
                    "core_passed": False,
                    "exact_passed": False,
                    "core_errors": ["missing_output"],
                    "exact_errors": ["missing_output"],
                }
            )
            continue
        record = output.get("record", output)
        shape_errors = validate_record(record, sources_by_case.get(case_name))
        core_errors = core_shape_errors(shape_errors) + compare_core_record(record, expected_by_case[case_name])
        exact_errors = shape_errors + compare_record(record, expected_by_case[case_name])
        if not core_errors:
            core_passed += 1
        if not exact_errors:
            exact_passed += 1
        case_results.append(
            {
                "case": case_name,
                "core_passed": not core_errors,
                "exact_passed": not exact_errors,
                "core_errors": core_errors,
                "exact_errors": exact_errors,
            }
        )

    return {
        "output_path": str(path),
        "core_passed": core_passed,
        "core_failed": len(requested) - core_passed,
        "exact_passed": exact_passed,
        "exact_failed": len(requested) - exact_passed,
        "total": len(requested),
        "cases": case_results,
    }


def _evidence_text(source_row: dict[str, object] | None, scope: str = "all") -> str:
    """Title + BFC + product_form_guess + current_esha_desc.

    BFC is included because real BFCs like "Frozen Breakfast Sandwiches"
    legitimately authorize processing_storage=['frozen']. The cost is that
    over-broad BFCs ("Canned Soup") may keep a junk processing token; we
    accept that trade-off.
    """
    if not source_row:
        return ""
    keys = ("title", "branded_food_category", "product_form_guess", "current_esha_desc")
    parts: list[str] = []
    for key in keys:
        v = source_row.get(key)
        if v:
            parts.append(str(v))
    return normalize_token(" ".join(parts))


def _strip_junk_facets(values: list[str], junk_set: set[str], evidence_blob: str) -> list[str]:
    out: list[str] = []
    for v in values:
        if v in junk_set and evidence_blob and v not in evidence_blob:
            continue
        out.append(v)
    return out


def _merge_compound_facets(values: list[str]) -> list[str]:
    if not values:
        return values
    remaining = list(values)
    merged: list[str] = []
    while remaining:
        head = remaining.pop(0)
        partner_idx = None
        compound = None
        for idx, other in enumerate(remaining):
            key = tuple(sorted((head, other)))
            if key in COMPOUND_FACET_TOKENS:
                partner_idx = idx
                compound = COMPOUND_FACET_TOKENS[key]
                break
        if partner_idx is not None and compound is not None:
            merged.append(compound)
            remaining.pop(partner_idx)
        else:
            merged.append(head)
    # de-dup preserving order
    seen: set[str] = set()
    out: list[str] = []
    for v in merged:
        if v not in seen:
            seen.add(v)
            out.append(v)
    return out


def _normalize_identity_form(pid: str) -> tuple[str, str | None]:
    """Strip decorator suffixes AND apply plural fallbacks. Only commits a
    transformation when the result is a recognized canonical hint key, so
    legitimate compound identities (Pizza Crust Mix) are preserved.

    Returns (normalized_identity, stripped_decorator_token_or_None).
    The stripped token is the snake_case form of any suffix decorator that was
    removed, e.g. "Pretzel Pieces" -> ("Pretzels", "pieces"). The caller can
    then drop that token from form/variant arrays where it shouldn't echo.
    """
    original = normalize_space(pid)
    if not original:
        return pid, None
    if original in CANONICAL_CATEGORY_HINTS:
        return original, None
    plural = IDENTITY_PLURAL_FALLBACKS.get(original)
    if plural and plural in CANONICAL_CATEGORY_HINTS:
        return plural, None
    cleaned = original
    stripped_decorator: str | None = None
    for suffix in IDENTITY_DECORATOR_SUFFIXES:
        if cleaned.endswith(suffix):
            stripped_decorator = normalize_token(suffix.strip())
            cleaned = cleaned[: -len(suffix)].rstrip()
    if cleaned and cleaned != original:
        if cleaned in CANONICAL_CATEGORY_HINTS:
            return cleaned, stripped_decorator
        plural2 = IDENTITY_PLURAL_FALLBACKS.get(cleaned)
        if plural2 and plural2 in CANONICAL_CATEGORY_HINTS:
            return plural2, stripped_decorator
    return original, None


# Backwards-compatible wrapper that just returns the identity for callers that
# don't care about the stripped decorator.
def _strip_identity_decorators(pid: str) -> str:
    return _normalize_identity_form(pid)[0]


# Identities for which stand-alone single-flavor "components" should be demoted
# to the flavor array. Useful when the LLM treats a flavor accent like basil
# as a separable meal component.
INGREDIENT_FLAVOR_DEMOTE_IDENTITIES = {
    "Tomatoes", "Pasta Sauce", "Salsa", "Pizza Sauce", "Marinara",
    "Yogurt", "Ice Cream", "Sherbet", "Sorbet",
    "Cookies", "Cake", "Cupcakes", "Brownies",
}


def _demote_flavor_components(pid: str, components: list[dict[str, object]],
                              flavor: list[str]) -> tuple[list[dict[str, object]], list[str]]:
    if pid not in INGREDIENT_FLAVOR_DEMOTE_IDENTITIES:
        return components, flavor
    new_flavor = list(flavor)
    new_components: list[dict[str, object]] = []
    pid_token = normalize_token(pid)
    for c in components:
        identity = str(c.get("identity") or "")
        token = normalize_token(identity)
        if token in KNOWN_FLAVOR_TOKENS:
            if token not in new_flavor:
                new_flavor.append(token)
            continue
        # Components that ARE the identity itself (e.g., Tomatoes inside
        # Tomatoes SKU) are also pure noise.
        if token == pid_token:
            continue
        new_components.append(c)
    return new_components, new_flavor


MARKETING_DROP_PREFIXES = {
    "creamy", "premium", "classic", "original", "extra", "ultra",
    "select", "signature", "homestyle", "old_fashioned", "deluxe",
    "the_original", "natural",
}

# Identity prefix tokens that imply a specific claim (so we drop them from
# identity AND from variant, but ensure the corresponding claim is present).
PROTEIN_PREFIX_CLAIMS = {
    "protein": "high_protein",
    "high_protein": "high_protein",
}


def _demote_identity_prefix(
    pid: str, variant: list[str], claims: list[str] | None = None
) -> tuple[str, list[str], list[str]]:
    """If product_identity is a multi-word phrase whose LAST word is a
    canonical hint key, decide what to do with the leading prefix:

      - if prefix is a MARKETING_DROP_PREFIXES word -> drop (do not add anywhere).
      - if prefix is a PROTEIN_PREFIX_CLAIMS key   -> drop AND ensure the
        corresponding claim is present.
      - else                                       -> demote to variant.

    Returns (identity, variant, claims).
    """
    if claims is None:
        claims = []
    base = normalize_space(pid)
    if not base or base in CANONICAL_CATEGORY_HINTS:
        return pid, variant, claims
    parts = base.split()
    if len(parts) < 2:
        return pid, variant, claims
    last = parts[-1]
    if last not in CANONICAL_CATEGORY_HINTS:
        return pid, variant, claims
    prefix_token = normalize_token(" ".join(parts[:-1]))
    if not prefix_token:
        return last, variant, claims
    if prefix_token in MARKETING_DROP_PREFIXES:
        return last, variant, claims
    if prefix_token in PROTEIN_PREFIX_CLAIMS:
        claim = PROTEIN_PREFIX_CLAIMS[prefix_token]
        new_claims = list(claims)
        if claim not in new_claims:
            new_claims.append(claim)
        return last, variant, new_claims
    new_variant = list(variant)
    if prefix_token not in new_variant:
        new_variant.insert(0, prefix_token)
    return last, new_variant, claims


# Component identity decoration strip: convert ingredient line phrasing into
# canonical food noun. Applied AFTER LLM output so we don't depend on the
# model honoring the rule.
COMPONENT_IDENTITY_PREP_SUFFIXES = (
    " In Sauce",
    " In Syrup",
    " In Brine",
    " In Water",
    " Dices",
    " Strips",
    " Bits",
    " Bites",
    " Chunks",
    " Crumbles",
    " Cubes",
    " Slices",
    " Pieces",
    " Mince",
    " Wedges",
)
COMPONENT_IDENTITY_FLAVOR_PREFIXES = (
    # Pure flavor accents — strip. ("Cinnamon Granola Topping" -> "Granola Topping")
    "Cinnamon ",
    "Spicy ",
    "Honey ",
    "Buttery ",
    "Sweet ",
    "Salted ",
    "Garlic ",
    # NOTE: "Smoked", "Roasted", "Toasted", "Sea Salt" are intentionally NOT
    # stripped — they're part of canonical food nouns ("Smoked Ham" is its
    # own product, not just "Ham"). Same logic for "Roasted Red Peppers".
)


def _normalize_component_identity(identity: str) -> str:
    """Backwards-compatible: just return the cleaned identity (no facets)."""
    cleaned, _ = _normalize_component_identity_with_facets(identity)
    return cleaned


# Suffix decorations that get ROUTED into specific component facets when stripped
# from the identity. Example: "Apple Dices In Sauce" -> identity="Apple",
# component.form_texture_cut=['dices'], component.processing_storage=['in_sauce'].
COMPONENT_SUFFIX_ROUTER = {
    " In Sauce":  ("processing_storage", "in_sauce"),
    " In Syrup":  ("processing_storage", "in_syrup"),
    " In Brine":  ("processing_storage", "in_brine"),
    " In Water":  ("processing_storage", "in_water"),
    " Dices":     ("form_texture_cut", "dices"),
    " Strips":    ("form_texture_cut", "strips"),
    " Bites":     ("form_texture_cut", "bites"),
    " Bits":      ("form_texture_cut", "bits"),
    " Pieces":    ("form_texture_cut", "pieces"),
    " Chunks":    ("form_texture_cut", "chunks"),
    " Crumbles":  ("form_texture_cut", "crumbles"),
    " Cubes":     ("form_texture_cut", "cubes"),
    " Slices":    ("form_texture_cut", "slices"),
    " Wedges":    ("form_texture_cut", "wedges"),
    " Mince":     ("form_texture_cut", "minced"),
}

# Prefix decorations that get routed into component.flavor when stripped.
COMPONENT_PREFIX_ROUTER = {
    "Cinnamon ": ("flavor", "cinnamon"),
    "Spicy ":    ("flavor", "spicy"),
    "Honey ":    ("flavor", "honey"),
    "Buttery ":  ("flavor", "butter"),
    "Sweet ":    ("flavor", "sweet"),
    "Salted ":   ("flavor", "salted"),
    "Garlic ":   ("flavor", "garlic"),
}

# Words inside a component identity that should be MIRRORED into a component
# facet without removing them from identity (since they're part of the
# canonical product name). Example: "Chicken Apple Sausage Patty" stays as
# the identity, but flavor=['apple'] and form_texture_cut=['patty'] are derived.
COMPONENT_IDENTITY_FORM_WORDS = {
    "patty", "patties", "flatbread", "tortilla", "tortillas", "wrap",
    "ball", "balls", "bowl",
}


def _normalize_component_identity_with_facets(identity: str) -> tuple[str, dict[str, list[str]]]:
    """Strip decoration AND route the stripped tokens into facet buckets.

    Returns (canonical_identity, extracted_facets_dict). The dict has keys
    'flavor', 'form_texture_cut', 'processing_storage' with lists of tokens
    that were stripped off and belong on the component.
    """
    cleaned = normalize_space(identity)
    extracted: dict[str, list[str]] = {"flavor": [], "form_texture_cut": [], "processing_storage": []}
    if not cleaned:
        return cleaned, extracted
    changed = True
    while changed:
        changed = False
        for suffix, (facet, token) in COMPONENT_SUFFIX_ROUTER.items():
            if cleaned.endswith(suffix):
                cleaned = cleaned[: -len(suffix)].rstrip()
                if token not in extracted[facet]:
                    extracted[facet].append(token)
                changed = True
        for prefix, (facet, token) in COMPONENT_PREFIX_ROUTER.items():
            if cleaned.startswith(prefix):
                cleaned = cleaned[len(prefix):].lstrip()
                if token not in extracted[facet]:
                    extracted[facet].append(token)
                changed = True
    return (cleaned or identity), extracted


def _derive_component_facets_from_words(identity: str) -> dict[str, list[str]]:
    """Mirror form/flavor tokens that appear INSIDE the kept identity into
    component facets. e.g. 'Chicken Apple Sausage Patty' -> flavor=['apple'],
    form_texture_cut=['patty']. 'Coconut Pudding' -> flavor=['coconut'].
    """
    out: dict[str, list[str]] = {"flavor": [], "form_texture_cut": []}
    if not identity:
        return out
    words = normalize_token(identity).split("_")
    if not words:
        return out
    # Form words: any position
    for w in words:
        if w in COMPONENT_IDENTITY_FORM_WORDS and w not in out["form_texture_cut"]:
            # plurals -> singular for form normalization
            singular = "patty" if w == "patties" else (
                "tortilla" if w == "tortillas" else (
                "ball" if w == "balls" else w))
            if singular not in out["form_texture_cut"]:
                out["form_texture_cut"].append(singular)
    # Flavor words: only when NOT the head noun (last word). Apple in
    # "Chicken Apple Sausage Patty" is a flavor; Apple alone is the identity.
    if len(words) > 1:
        for w in words[:-1]:
            if w in KNOWN_FLAVOR_TOKENS and w not in out["flavor"]:
                out["flavor"].append(w)
        # Also check the FIRST word for flavors that occur as primary modifier
        # (e.g., 'Coconut Pudding' -> flavor=['coconut']).
        head_first = words[0]
        if head_first in KNOWN_FLAVOR_TOKENS and head_first not in out["flavor"]:
            out["flavor"].append(head_first)
    return out


def _drop_variant_echo_components(
    pid: str, variant: list[str], components: list[dict[str, object]]
) -> list[dict[str, object]]:
    """For SKUs like 'Cheese Crisps' with variant=['asiago'], drop any component
    whose identity is just the variant token plus a category-noun match (e.g.,
    'Asiago Cheese'). Those are echoes of the variant, not separate parts.
    """
    if not pid or not variant:
        return components
    pid_token = normalize_token(pid)
    pid_parts = set(pid_token.split("_"))
    variant_set = set(variant)
    out: list[dict[str, object]] = []
    for c in components:
        token = normalize_token(str(c.get("identity") or ""))
        if not token:
            out.append(c)
            continue
        # Drop if every part of the component identity is in (variant U identity-parts).
        comp_parts = set(token.split("_"))
        if comp_parts.issubset(pid_parts | variant_set):
            continue
        out.append(c)
    return out


# When the model returns a bare/generic identity ("Bar", "Candy"), look at
# the title and pick a specific identity. Order matters — first match wins,
# so put the most specific keywords first.
BAR_TITLE_RESOLVER: list[tuple[str, str]] = [
    # Most specific first
    ("yogurt bar", "Yogurt Bars"),
    ("cookie bar", "Cookie Bars"),
    ("energy gel", "Energy Gels"),
    ("marshmallow squares", "Marshmallow Squares"),
    ("crispy squares", "Marshmallow Squares"),
    ("fruit & grain", "Cereal Bars"),
    ("fruit and grain", "Cereal Bars"),
    ("cereal bar", "Cereal Bars"),
    ("fiber bar", "Cereal Bars"),
    ("kids", "Kids Bars"),
    ("meal replacement", "Meal Replacement Bars"),
    ("breakfast bar", "Breakfast Bars"),
    ("fruit bar", "Fruit Bars"),
    ("fruit & nut", "Fruit Bars"),
    ("fruit and nut", "Fruit Bars"),
    ("collagen protein", "Protein Bars"),
    ("whey protein", "Protein Bars"),
    ("plant-based bar", "Protein Bars"),
    ("plant based bar", "Protein Bars"),
    ("high protein", "Protein Bars"),
    ("protein bar", "Protein Bars"),
    ("protein chewy bars", "Protein Bars"),
    ("endurance", "Energy Bars"),
    ("performance", "Energy Bars"),
    ("energy bar", "Energy Bars"),
    ("energy snack bar", "Energy Bars"),
    ("granola bar", "Granola Bars"),
    ("nutrition bar", "Nutrition Bars"),
    ("snack bar", "Snack Bars"),
    ("trail bar", "Granola Bars"),
    ("nut butter bar", "Granola Bars"),
    ("nut bar", "Granola Bars"),
    ("oats bar", "Granola Bars"),
    ("oat bar", "Granola Bars"),
]

CANDY_TITLE_RESOLVER: list[tuple[str, str]] = [
    # Most specific first
    ("marshmallow", "Marshmallows"),
    ("circus peanuts", "Marshmallows"),  # circus peanuts ARE marshmallow candy
    ("fruit snack", "Fruit Snacks"),
    ("fruit flavored snack", "Fruit Snacks"),
    ("fruit & veggie snack", "Fruit Snacks"),
    ("gummi", "Gummy Candy"),
    ("gummy", "Gummy Candy"),
    ("jelly bean", "Jelly Beans"),
    ("jelly bird", "Jelly Beans"),
    ("ring pop", "Lollipops"),
    ("tulip pop", "Lollipops"),
    ("lollipop", "Lollipops"),
    ("lollipops", "Lollipops"),
    ("bubble gum", "Bubble Gum"),
    ("licorice", "Licorice"),
    ("truffle", "Truffle"),
    ("bark", "Bark"),
    ("toffee", "Toffee"),
    ("fudge", "Fudge"),
    ("cotton candy", "Cotton Candy"),
    ("salt water taffy", "Caramel Candy"),
    ("taffy", "Caramel Candy"),
    ("caramel cream", "Caramel Candy"),
    ("caramel", "Caramel Candy"),
    ("peppermint patti", "Chocolate Candy"),
    ("peanut butter cup", "Chocolate Candy"),
    ("chocolate egg", "Chocolate Candy"),
    ("chocolate hearts", "Chocolate Candy"),
    ("chocolate candies", "Chocolate Candy"),
    ("chocolate candy bar", "Candy Bar"),
    ("nougat bar", "Candy Bar"),
    ("candy bar", "Candy Bar"),
    ("crystallized ginger", "Candied Fruit"),
    ("candied ginger", "Candied Fruit"),
    ("orange slice", "Candied Fruit"),
    ("spice drop", "Hard Candy"),
    ("imperial", "Hard Candy"),
    ("disc", "Hard Candy"),
    ("barrel", "Hard Candy"),
    ("ball", "Hard Candy"),
    ("drop", "Hard Candy"),
    ("mint", "Hard Candy"),
    ("rings", "Hard Candy"),  # peach rings, sour rings
    ("popper", "Hard Candy"),
    ("bite size", "Hard Candy"),
    ("hard candy", "Hard Candy"),
    ("sour", "Sour Candy"),
]


def _resolve_generic_identity(pid: str, title: str, bfc: str) -> str:
    """If the LLM returned a bare 'Bar' or 'Candy' identity, look at the
    title and pick a more specific identity from our resolver tables.
    No-op if pid is already specific.
    """
    if not pid:
        return pid
    pid_norm = normalize_space(pid)
    if not title:
        return pid_norm
    title_lc = title.lower()
    bfc_lc = (bfc or "").lower()

    # Title-driven OVERRIDE for clear-cut identities the model often misses,
    # regardless of what identity the model picked. Title beats LLM choice
    # when title says EXACTLY what the SKU is.
    if "fruit flavored snack" in title_lc or "fruit snack" in title_lc:
        if pid_norm in {"Candy", "Hard Candy", "Gummy Candy", "Sour Candy", "Sweets"}:
            return "Fruit Snacks"

    # Bar variants
    if pid_norm in {"Bar", "Bars", "Granola Bar", "Protein Bar", "Energy Bar",
                    "Cereal Bar", "Fruit Bar", "Cookie Bar", "Yogurt Bar",
                    "Nutrition Bar", "Snack Bar", "Breakfast Bar", "Kids Bar"}:
        for kw, ident in BAR_TITLE_RESOLVER:
            if kw in title_lc:
                return ident
        return "Snack Bars"  # safe fallback when BFC is bars
    # Candy
    if pid_norm in {"Candy", "Sweets", "Confection", "Chocolate"}:
        for kw, ident in CANDY_TITLE_RESOLVER:
            if kw in title_lc:
                return ident
        # If BFC is chocolate-domain, default to Chocolate Candy
        if "chocolate" in bfc_lc:
            return "Chocolate Candy"
        return "Hard Candy"  # generic fallback for non-chocolate candy
    return pid_norm


# Identity-word -> synonym tokens that should also be stripped from form/variant
# when the identity contains the key. e.g., a "Chicken Burgers" SKU should not
# also have form=['patties'] because patty is implied by burger.
IDENTITY_FORM_SYNONYMS = {
    "burger":  {"patty", "patties"},
    "burgers": {"patty", "patties"},
    "sandwich": {"sandwich"},
    "sandwiches": {"sandwich"},
    "tortilla": {"wrap", "wraps", "flatbread"},
    "tortillas": {"wrap", "wraps"},
    "wrap": {"wrap", "wraps"},
    "wraps": {"wrap", "wraps"},
    "crisps": {"crisp"},
    "chips": {"chip"},
    "cookies": {"cookie"},
    "cookie": {"cookie"},
    "pretzels": {"pretzel"},
    "pretzel": {"pretzel"},
}


def _strip_identity_echoed_facets(pid: str, values: list[str]) -> list[str]:
    """Drop facet values that are already encoded into product_identity, including
    synonym forms (Chicken Burgers => strip 'patties' too).

    Example: identity='Cheese Crisps', form_texture_cut=['crisps'] -> [].
    Example: identity='Chicken Burgers', form_texture_cut=['patties'] -> [].
    """
    if not pid or not values:
        return values
    pid_token = normalize_token(pid)
    pid_parts = set(pid_token.split("_"))
    synonym_block: set[str] = set()
    for part in pid_parts:
        synonym_block |= IDENTITY_FORM_SYNONYMS.get(part, set())
    blocked = pid_parts | synonym_block
    out: list[str] = []
    for v in values:
        v_parts = v.split("_")
        if all(p in blocked for p in v_parts):
            continue
        out.append(v)
    return out


def _promote_identity_from_variant(pid: str, variant: list[str]) -> tuple[str, list[str]]:
    """If a variant token combined with the bare identity matches a richer
    identity in CANONICAL_CATEGORY_HINTS, promote it.

    Example: pid='Soup', variant=['broccoli_cheddar'] -> 'Broccoli Cheddar Soup'.
    """
    if not pid or not variant:
        return pid, variant
    base = normalize_space(pid)
    for idx, v in enumerate(variant):
        candidate = " ".join(part.capitalize() for part in v.split("_")) + " " + base
        candidate = normalize_space(candidate)
        if candidate in CANONICAL_CATEGORY_HINTS:
            new_variant = list(variant)
            new_variant.pop(idx)
            return candidate, new_variant
    return pid, variant


def _reclassify_known_flavors(variant: list[str], flavor: list[str]) -> tuple[list[str], list[str]]:
    """Move tokens that are unambiguously flavors out of variant into flavor."""
    if not variant:
        return variant, flavor
    new_variant: list[str] = []
    new_flavor = list(flavor)
    for token in variant:
        if token in KNOWN_FLAVOR_TOKENS and token not in new_flavor:
            new_flavor.append(token)
        elif token in KNOWN_FLAVOR_TOKENS:
            # already in flavor, drop from variant
            pass
        else:
            new_variant.append(token)
    return new_variant, new_flavor


def normalize_record(record: dict[str, object], source_row: dict[str, object] | None = None) -> dict[str, object]:
    """Deterministic post-LLM cleanup. Idempotent.

    Fixes the recurring mechanical failures: claim ordering, compound facet
    splitting, junk processing/form tokens, category routing, retail_type for
    meal kits, identity decorator stripping, identity promotion from variant,
    known-flavor reclassification, and canonical_label/tree_paths regeneration.
    """
    if not isinstance(record, dict):
        return record
    rec = dict(record)
    evidence = _evidence_text(source_row)

    # Coerce facet arrays into the cleaned form parse_record expects.
    for group in FACET_GROUPS:
        rec[group] = clean_list(rec.get(group, []))
    rec["components"] = clean_components(rec.get("components", []))
    rec["review_flags"] = clean_string_list(rec.get("review_flags", []))

    # Compound merger (whole + peeled -> whole_peeled etc.) on both lists,
    # because the LLM sometimes splits them under variant instead of form.
    rec["form_texture_cut"] = _merge_compound_facets(rec["form_texture_cut"])
    rec["variant"] = _merge_compound_facets(rec["variant"])

    # Move tokens that are unambiguously *form* descriptors out of variant.
    # (After compound merging so 'whole'+'peeled' has already become 'whole_peeled'.)
    moved_form: list[str] = []
    new_variant: list[str] = []
    for v in rec["variant"]:
        if v in KNOWN_FORM_TOKENS:
            moved_form.append(v)
        else:
            new_variant.append(v)
    rec["variant"] = new_variant
    if moved_form:
        for v in moved_form:
            if v not in rec["form_texture_cut"]:
                rec["form_texture_cut"].append(v)

    # If the source title contains "seasoned" and the LLM didn't capture it
    # in processing_storage (gold expects this for the Chicken Burgers case),
    # add it. Only fires when title has the literal word.
    if source_row:
        title_lc = str(source_row.get("title") or "").lower()
        if "seasoned" in title_lc and "seasoned" not in rec["processing_storage"]:
            rec["processing_storage"].append("seasoned")

    # Move dietary/nutrition tokens out of variant/flavor into claims.
    moved_to_claims: list[str] = []
    rec["variant"] = [v for v in rec["variant"] if not (v in CLAIM_ORDER and (moved_to_claims.append(v) or True))]
    rec["flavor"]  = [v for v in rec["flavor"]  if not (v in CLAIM_ORDER and (moved_to_claims.append(v) or True))]
    for c in moved_to_claims:
        if c not in rec["claims"]:
            rec["claims"].append(c)

    # Move processing tokens out of variant into processing_storage.
    moved_to_proc: list[str] = []
    rec["variant"] = [v for v in rec["variant"] if not (
        v in EVIDENCE_GATED_PROCESSING_TOKENS and (moved_to_proc.append(v) or True)
    )]
    for p in moved_to_proc:
        if p not in rec["processing_storage"]:
            rec["processing_storage"].append(p)

    # Drop marketing tokens unconditionally.
    rec["variant"] = [v for v in rec["variant"] if v not in MARKETING_DROP_TOKENS]
    rec["flavor"] = [v for v in rec["flavor"] if v not in MARKETING_DROP_TOKENS]
    rec["form_texture_cut"] = [v for v in rec["form_texture_cut"] if v not in MARKETING_DROP_TOKENS]

    # Strip evidence-gated junk
    if evidence:
        rec["processing_storage"] = _strip_junk_facets(
            rec["processing_storage"], EVIDENCE_GATED_PROCESSING_TOKENS, evidence
        )
        rec["form_texture_cut"] = _strip_junk_facets(
            rec["form_texture_cut"], EVIDENCE_GATED_FORM_TOKENS, evidence
        )

    # If the LLM returned a bare 'Bar' or 'Candy' identity, resolve from the
    # title before any other identity processing. This is the layer-2 fix for
    # the model defaulting to generic identities on real CSV SKUs.
    raw_pid = str(rec.get("product_identity") or "")
    title = str((source_row or {}).get("title", "") or "")
    bfc = str((source_row or {}).get("branded_food_category", "") or "")
    raw_pid = _resolve_generic_identity(raw_pid, title, bfc)

    # Strip decorator suffixes ('Pretzel Pieces' -> 'Pretzels'). For each
    # suffix consult DECORATOR_SUFFIX_DESTINATION:
    #   form -> ensure it's in form_texture_cut (pretzel pieces is a real form)
    #   drop -> remove from form/variant (Blend/Mix is filler)
    pid, stripped = _normalize_identity_form(raw_pid)
    if stripped:
        action = DECORATOR_SUFFIX_DESTINATION.get(stripped, "drop")
        if action == "drop":
            rec["form_texture_cut"] = [v for v in rec["form_texture_cut"] if v != stripped]
            rec["variant"] = [v for v in rec["variant"] if v != stripped]
        elif action == "form":
            if stripped not in rec["form_texture_cut"]:
                rec["form_texture_cut"].append(stripped)
            rec["variant"] = [v for v in rec["variant"] if v != stripped]

    # Demote leading prefix to variant/claims when last word is a canonical hint.
    # Marketing prefixes ('Creamy') are dropped. Protein prefixes drop and
    # ensure the corresponding claim is present.
    pid, rec["variant"], rec["claims"] = _demote_identity_prefix(
        pid, rec["variant"], rec["claims"]
    )

    # Promote bare identity to compound identity when variant unlocks a hint.
    pid, rec["variant"] = _promote_identity_from_variant(pid, rec["variant"])
    rec["product_identity"] = pid

    # Reclassify known flavors out of variant.
    rec["variant"], rec["flavor"] = _reclassify_known_flavors(rec["variant"], rec["flavor"])

    # Drop facet values that are already part of product_identity
    # ('Cheese Crisps' identity should not also have form_texture=['crisps']).
    rec["variant"] = _strip_identity_echoed_facets(pid, rec["variant"])
    rec["form_texture_cut"] = _strip_identity_echoed_facets(pid, rec["form_texture_cut"])
    rec["flavor"] = _strip_identity_echoed_facets(pid, rec["flavor"])

    # For ingredient-identity SKUs (Tomatoes, Cookies, Yogurt, ...), demote
    # single-flavor components into the flavor array.
    rec["components"], rec["flavor"] = _demote_flavor_components(
        pid, rec["components"], rec["flavor"]
    )

    # Component identity normalization + facet routing.
    # Step A: strip decorator prefix/suffix from identity AND route those
    #         stripped tokens into component facets (flavor / form / processing).
    # Step B: apply explicit canonicalization (Chicken Breast -> Chicken).
    # Step C: derive flavor/form facets from remaining identity words
    #         (Chicken Apple Sausage Patty -> flavor=['apple'], form=['patty']).
    cleaned_components: list[dict[str, object]] = []
    for c in rec["components"]:
        ident = str(c.get("identity") or "")
        cleaned, extracted = _normalize_component_identity_with_facets(ident)
        canonical = COMPONENT_IDENTITY_CANONICALIZE.get(cleaned, cleaned)
        if not canonical:
            continue
        new_c = dict(c)
        new_c["identity"] = canonical

        # Merge the stripped-decoration extracted facets into the component.
        for facet, tokens in extracted.items():
            existing = list(new_c.get(facet, []) or [])
            for tok in tokens:
                if tok not in existing:
                    existing.append(tok)
            new_c[facet] = existing

        # If canonicalization simplified a multi-word identity to a single word
        # (Chicken Strips -> Chicken), drop the form tokens that were part of
        # the original ingredient phrasing — they're not the SKU's name.
        if cleaned != canonical:
            for facet in ("form_texture_cut", "variant"):
                vals = new_c.get(facet, [])
                if isinstance(vals, list):
                    new_c[facet] = [v for v in vals if v not in {"strips","tenders","breast","thigh","loin","cubes"}]

        # Mirror form/flavor tokens that appear inside the kept identity.
        # Skip flavor derivation when role="ingredient" — the modifier is the
        # food noun itself ("Almond" in "Almond Flour" is the food, not a
        # flavor accent).
        derived = _derive_component_facets_from_words(canonical)
        if str(new_c.get("role") or "") == "ingredient":
            derived["flavor"] = []
        for facet, tokens in derived.items():
            existing = list(new_c.get(facet, []) or [])
            for tok in tokens:
                if tok not in existing:
                    existing.append(tok)
            new_c[facet] = existing

        # Migrate component variant entries that are really processing tokens
        # (Smoked, Roasted, Toasted, Smoked Ham -> processing_storage=['smoked']).
        cv = list(new_c.get("variant", []) or [])
        cp = list(new_c.get("processing_storage", []) or [])
        moved: list[str] = []
        for tok in list(cv):
            if tok in EVIDENCE_GATED_PROCESSING_TOKENS or tok in {"smoked","roasted","toasted","cured"}:
                cv.remove(tok)
                if tok not in cp:
                    cp.append(tok)
                moved.append(tok)
        new_c["variant"] = cv
        new_c["processing_storage"] = cp

        # Named flavor-accent tokens (sesame_garlic, garlic_herb, lemon_pepper,
        # honey_mustard, etc.) on a protein component belong in flavor, not
        # variant. Apply this regardless of retail_type — these are
        # unambiguously flavor compounds.
        PROTEIN_FLAVOR_ACCENTS = {
            "sesame_garlic", "garlic_herb", "honey_garlic", "lemon_pepper",
            "cajun", "honey_mustard", "buffalo", "ranch", "chipotle",
            "teriyaki", "tikka_masala", "korean_bbq", "bourbon",
        }
        cv = new_c.get("variant", []) or []
        cf = new_c.get("flavor", []) or []
        for token in list(cv):
            if token in PROTEIN_FLAVOR_ACCENTS:
                cv.remove(token)
                if token not in cf:
                    cf.append(token)
        new_c["variant"] = cv
        new_c["flavor"] = cf
        cleaned_components.append(new_c)
    rec["components"] = cleaned_components

    # For ingredient-identity SKUs (Soup, Dip, Tortillas), force component
    # role = 'ingredient' regardless of what the model said.
    INGREDIENT_ROLE_PIDS = {
        "Dip", "Spinach Artichoke Dip",
        "Soup", "Broccoli Cheddar Soup", "Tomato Basil Soup", "Chicken Noodle Soup",
        "Tortillas",
    }
    if pid in INGREDIENT_ROLE_PIDS:
        for c in rec["components"]:
            c["role"] = "ingredient"

    # For sandwich-class identities, normalize a few stable per-component roles.
    SANDWICH_TOPPING_COMPONENTS = {"Tomato", "Tomatoes", "Lettuce", "Onion",
                                    "Onions", "Pickle", "Pickles", "Sprouts",
                                    "Cucumber"}
    SANDWICH_LIKE_PIDS = COMPOSITE_DISH_IDENTITIES | {
        "Sandwich", "Sandwiches", "Breakfast Sandwich",
        "Flatbread Sandwich", "Wrap",
    }
    if pid in SANDWICH_LIKE_PIDS:
        for c in rec["components"]:
            cid = str(c.get("identity") or "")
            if cid in SANDWICH_TOPPING_COMPONENTS:
                c["role"] = "topping"

    # Drop components that just echo the variant (Cheese Crisps + asiago -> drop Asiago Cheese).
    rec["components"] = _drop_variant_echo_components(pid, rec["variant"], rec["components"])

    # Identity-based disallowed claims.
    disallowed = DISALLOWED_CLAIMS_BY_IDENTITY.get(pid, set())
    if disallowed:
        rec["claims"] = [c for c in rec["claims"] if c not in disallowed]

    # Claim ordering.
    rec["claims"] = order_claims(rec["claims"])

    # Force category_path from product_identity hint if available.
    hint = CANONICAL_CATEGORY_HINTS.get(pid)
    if hint:
        rec["category_path"] = hint

    # retail_type for meal kits.
    pid_token = normalize_token(pid)
    if pid_token in MEAL_KIT_IDENTITY_TOKENS or any(
        pid_token.endswith("_" + tail) for tail in ("kit", "starter")
    ):
        rec["retail_type"] = "meal_kit"
    # retail_type for composite dishes (sandwiches, parfaits, etc.).
    elif pid in COMPOSITE_DISH_IDENTITIES:
        rec["retail_type"] = "composite_dish"

    # mint_required: deterministic from product_identity.
    if pid in MINT_NOT_REQUIRED_IDENTITIES:
        rec["mint_required"] = False
    elif pid in CANONICAL_CATEGORY_HINTS:
        rec["mint_required"] = True
    # otherwise leave whatever the LLM said

    # For retail_type=single, drop components UNLESS:
    #   (a) the SKU is in COMPONENT_KEEP_SINGLE_IDENTITIES (compound-identity
    #       SKUs that legitimately list ingredients: Dip, Soup, Tortillas...)
    #   (b) the SKU is in COMPONENT_KEEP_SINGLE_PREPARED (sandwiches, burgers,
    #       breakfast sandwiches — single-row prepared items that have parts)
    #   (c) the component identity matches a distinctive variant token
    #       (Almond Flour Tortillas case).
    COMPONENT_KEEP_SINGLE_IDENTITIES = {
        "Dip", "Spinach Artichoke Dip",
        "Soup", "Broccoli Cheddar Soup", "Tomato Basil Soup", "Chicken Noodle Soup",
        "Tortillas",
    }
    COMPONENT_KEEP_SINGLE_PREPARED = {
        # NOTE: Chicken Burgers gold says components=[]; do NOT keep here.
        "Sandwich", "Sandwiches",
        "Breakfast Sandwich", "Flatbread Sandwich", "Wrap",
    }
    if rec.get("retail_type") == "single":
        if pid in COMPONENT_KEEP_SINGLE_IDENTITIES or pid in COMPONENT_KEEP_SINGLE_PREPARED:
            pass  # keep components as-is
        else:
            kept: list[dict[str, object]] = []
            variant_set = {v for v in rec["variant"]}
            for c in rec["components"]:
                comp_token = normalize_token(str(c.get("identity") or ""))
                if comp_token in variant_set:
                    kept.append(c)
            rec["components"] = kept

    # Regenerate canonical_path/canonical_label/tree_paths from final state.
    rec["canonical_path"] = build_canonical_path(
        str(rec.get("category_path") or ""), pid
    )
    rec["canonical_label"] = build_canonical_label(pid, rec)
    rec["tree_paths"] = build_tree_paths(rec)

    return rec


def rescore_live_outputs(
    live_path: Path,
    gold_path: Path,
    apply_normalizer: bool,
    summary_out: Path | None = None,
    diff_out: Path | None = None,
    rescore_out: Path | None = None,
    case_filters: set[str] | None = None,
) -> dict[str, object]:
    """Re-score an existing live JSONL against gold without making API calls.

    Optionally applies the deterministic normalizer first and writes a
    side-by-side per-case diff for the test session.
    """
    cases_by_name: dict[str, dict[str, object]] = {}
    for case in read_jsonl(gold_path):
        cases_by_name[str(case.get("name", ""))] = case

    if case_filters:
        case_names = [
            n for n, c in cases_by_name.items()
            if n in case_filters or str(c.get("source", {}).get("fdc_id", "")) in case_filters
        ]
    else:
        case_names = list(cases_by_name.keys())

    rows = read_jsonl(live_path) if live_path.exists() else []
    by_case = {str(output.get("case", "")): output for output in rows}

    case_results: list[dict[str, object]] = []
    diff_blocks: list[str] = []
    summary_lines: list[str] = []
    core_passed = 0
    exact_passed = 0

    for name in case_names:
        case = cases_by_name[name]
        expected = case["expected"]
        source = case.get("source", {})
        output = by_case.get(name)
        if not output:
            case_results.append({
                "case": name,
                "core_passed": False,
                "exact_passed": False,
                "core_errors": ["missing_output"],
                "exact_errors": ["missing_output"],
            })
            summary_lines.append(f"{name}: MISSING OUTPUT")
            continue

        record = output.get("record") or output
        if apply_normalizer:
            record = normalize_record(record, source)

        shape_errors = validate_record(record, source)
        core_errors = core_shape_errors(shape_errors) + compare_core_record(record, expected)
        exact_errors = shape_errors + compare_record(record, expected)
        core_ok = not core_errors
        exact_ok = not exact_errors
        if core_ok:
            core_passed += 1
        if exact_ok:
            exact_passed += 1

        case_results.append({
            "case": name,
            "core_passed": core_ok,
            "exact_passed": exact_ok,
            "core_errors": core_errors,
            "exact_errors": exact_errors,
        })
        summary_lines.append(
            f"{name}: core={'PASS' if core_ok else 'FAIL'} exact={'PASS' if exact_ok else 'FAIL'}"
        )

        if diff_out:
            block_lines = [f"## {name}"]
            block_lines.append(f"- core: **{'PASS' if core_ok else 'FAIL'}**")
            block_lines.append(f"- exact: **{'PASS' if exact_ok else 'FAIL'}**")
            block_lines.append("")
            block_lines.append("| field | expected | actual |")
            block_lines.append("|-------|----------|--------|")
            for fname in CORE_COMPARE_FIELDS + ["canonical_label", "tree_paths", "components"]:
                ev = expected.get(fname)
                av = record.get(fname)
                marker = "" if ev == av else " *"
                block_lines.append(
                    f"| `{fname}`{marker} | `{json.dumps(ev, sort_keys=True)}` | `{json.dumps(av, sort_keys=True)}` |"
                )
            if core_errors:
                block_lines.append("")
                block_lines.append("**core errors:**")
                for err in core_errors:
                    block_lines.append(f"- `{err}`")
            if exact_errors:
                block_lines.append("")
                block_lines.append("**exact errors:**")
                for err in exact_errors:
                    block_lines.append(f"- `{err}`")
            diff_blocks.append("\n".join(block_lines))

    summary_obj: dict[str, object] = {
        "live_path": str(live_path),
        "normalizer_applied": apply_normalizer,
        "core_passed": core_passed,
        "core_failed": len(case_names) - core_passed,
        "exact_passed": exact_passed,
        "exact_failed": len(case_names) - exact_passed,
        "total": len(case_names),
        "cases": case_results,
    }

    rescore_path = rescore_out or live_path.with_suffix(".rescore.json")
    rescore_path.parent.mkdir(parents=True, exist_ok=True)
    rescore_path.write_text(json.dumps(summary_obj, indent=2, sort_keys=True), encoding="utf-8")

    if summary_out:
        header = (
            f"live={live_path.name}  normalizer={'on' if apply_normalizer else 'off'}  "
            f"core={core_passed}/{len(case_names)}  exact={exact_passed}/{len(case_names)}\n"
            + "=" * 100 + "\n"
        )
        summary_out.parent.mkdir(parents=True, exist_ok=True)
        summary_out.write_text(header + "\n".join(summary_lines) + "\n", encoding="utf-8")

    if diff_out:
        diff_out.parent.mkdir(parents=True, exist_ok=True)
        diff_out.write_text(
            f"# Re-score diff: {live_path.name}\n\n"
            f"normalizer={'on' if apply_normalizer else 'off'}, "
            f"core={core_passed}/{len(case_names)}, exact={exact_passed}/{len(case_names)}\n\n"
            + "\n\n---\n\n".join(diff_blocks) + "\n",
            encoding="utf-8",
        )

    return summary_obj


def run_model_sweep(
    requests: list[dict[str, object]],
    gold_path: Path,
    models: list[str],
    sweep_out: Path,
    pause_seconds: float,
    retry_attempts: int,
    retry_base_seconds: float,
) -> list[dict[str, object]]:
    sweep_out.mkdir(parents=True, exist_ok=True)
    requested_cases = [str(request.get("case", "")) for request in requests]
    summary: list[dict[str, object]] = []
    for model in models:
        output_path = sweep_out / f"{model_slug(model)}.jsonl"
        error_path = sweep_out / f"{model_slug(model)}.error.json"
        model_summary: dict[str, object] = {"model": model, "output_path": str(output_path)}
        try:
            run_live(requests, model, output_path, pause_seconds, retry_attempts, retry_base_seconds)
        except Exception as exc:
            error = {"model": model, "error_type": type(exc).__name__, "error": str(exc)}
            error_path.write_text(json.dumps(error, indent=2, sort_keys=True), encoding="utf-8")
            model_summary["run_error"] = error
            print(f"model failed: {model}: {type(exc).__name__}: {exc}")
        model_summary.update(score_outputs(output_path, gold_path, requested_cases))
        summary.append(model_summary)
    summary_path = sweep_out / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(f"wrote model sweep summary: {summary_path}")
    return summary


def validate_gold(path: Path) -> int:
    failures = 0
    for case in read_jsonl(path):
        source = case["source"]
        expected = case["expected"]
        errors = validate_record(expected, source)
        if errors:
            failures += 1
            print(f"FAIL expected {case['name']}: {errors}")
        for idx, bad in enumerate(case.get("bad_outputs", []), start=1):
            bad_errors = validate_record(bad, source) + compare_record(bad, expected)
            if not bad_errors:
                failures += 1
                print(f"FAIL bad output accepted {case['name']} #{idx}")
    return failures


def compare_record(actual: dict[str, object], expected: dict[str, object]) -> list[str]:
    errors: list[str] = []
    actual_record = asdict(parse_record(actual))
    expected_record = asdict(parse_record(expected))
    for field_name in STRICT_COMPARE_FIELDS:
        if actual_record.get(field_name) != expected_record.get(field_name):
            errors.append(
                f"mismatch:{field_name}:expected={expected_record.get(field_name)!r}:actual={actual_record.get(field_name)!r}"
            )
    return errors


def component_identity_set(record: dict[str, object]) -> set[str]:
    parsed = parse_record(record)
    return {normalize_token(str(component.get("identity", ""))) for component in parsed.components if component.get("identity")}


def core_shape_errors(errors: Iterable[str]) -> list[str]:
    derivable_prefixes = ("canonical_label_mismatch:",)
    derivable_exact = {"tree_paths_mismatch"}
    return [error for error in errors if error not in derivable_exact and not error.startswith(derivable_prefixes)]


def compare_core_record(actual: dict[str, object], expected: dict[str, object]) -> list[str]:
    errors: list[str] = []
    actual_record = asdict(parse_record(actual))
    expected_record = asdict(parse_record(expected))
    for field_name in CORE_COMPARE_FIELDS:
        if actual_record.get(field_name) != expected_record.get(field_name):
            errors.append(
                f"core_mismatch:{field_name}:expected={expected_record.get(field_name)!r}:actual={actual_record.get(field_name)!r}"
            )
    actual_components = component_identity_set(actual)
    expected_components = component_identity_set(expected)
    if actual_components != expected_components:
        errors.append(f"core_mismatch:component_identities:expected={sorted(expected_components)!r}:actual={sorted(actual_components)!r}")
    return errors


def validate_outputs(path: Path, gold_path: Path | None = None) -> int:
    sources_by_case = {}
    expected_by_case = {}
    if gold_path:
        gold_cases = read_jsonl(gold_path)
        sources_by_case = {case["name"]: case["source"] for case in gold_cases}
        expected_by_case = {case["name"]: case["expected"] for case in gold_cases}
    failures = 0
    for output in read_jsonl(path):
        case_name = str(output.get("case", ""))
        record = output.get("record", output)
        source = sources_by_case.get(case_name)
        errors = validate_record(record, source)
        if case_name in expected_by_case:
            errors.extend(compare_record(record, expected_by_case[case_name]))
        if errors:
            failures += 1
            print(f"FAIL output {case_name or output.get('fdc_id', '')}: {errors}")
    return failures


def main() -> None:
    parser = argparse.ArgumentParser(description="Build, run, and validate LLM taxonomy cleanup requests.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--gold", type=Path, default=DEFAULT_GOLD)
    parser.add_argument("--requests-out", type=Path, default=DEFAULT_REQUESTS)
    parser.add_argument("--outputs-out", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--model", default=os.environ.get("NEBIUS_MODEL", "deepseek-ai/DeepSeek-V3.2-fast"))
    parser.add_argument("--api-key-stdin", action="store_true", help="Read NEBIUS_API_KEY from stdin for this process only.")
    parser.add_argument("--case", action="append", default=[], help="Only build/run a named gold case or fdc_id. Can be passed multiple times.")
    parser.add_argument("--pause-seconds", type=float, default=0.0, help="Sleep between live model calls to reduce rate-limit failures.")
    parser.add_argument("--retry-attempts", type=int, default=0, help="Retry live calls after 429 rate-limit errors.")
    parser.add_argument("--retry-base-seconds", type=float, default=10.0, help="Initial backoff delay for 429 retries.")
    parser.add_argument("--model-sweep", action="store_true", help="Run the same selected cases against multiple candidate models.")
    parser.add_argument("--sweep-model", action="append", default=[], help="Model to include in --model-sweep. Defaults to built-in candidates.")
    parser.add_argument("--sweep-out", type=Path, default=DEFAULT_SWEEP_OUT)
    parser.add_argument("--build-requests", action="store_true")
    parser.add_argument("--run-live", action="store_true")
    parser.add_argument("--validate-gold", action="store_true")
    parser.add_argument("--validate-outputs", type=Path)
    parser.add_argument(
        "--fixture-map",
        type=Path,
        default=DEFAULT_FIXTURE_EVIDENCE_MAP,
        help="JSON mapping fixture_fdc -> real_fdc for grafting evidence.",
    )
    parser.add_argument(
        "--no-fixture-map",
        action="store_true",
        help="Disable fixture evidence grafting (run with raw gold sources only).",
    )
    parser.add_argument(
        "--apply-normalizer",
        action="store_true",
        help="Apply deterministic post-processing to LLM records before scoring.",
    )
    parser.add_argument(
        "--rescore",
        type=Path,
        help="Re-score an existing live JSONL against gold (no API calls). Pair with --apply-normalizer.",
    )
    parser.add_argument(
        "--rescore-out",
        type=Path,
        help="Where to write the re-score JSON summary. Default: <rescore>.rescore.json",
    )
    parser.add_argument(
        "--diff-out",
        type=Path,
        help="Optional markdown diff file written by --rescore showing per-case expected vs actual.",
    )
    parser.add_argument(
        "--summary-out",
        type=Path,
        help="Optional plain-text per-case PASS/FAIL summary written by --rescore.",
    )
    parser.add_argument(
        "--two-pass",
        action="store_true",
        help="Two-pass prompt design (NOT RECOMMENDED for production; doubles cost).",
    )
    parser.add_argument(
        "--no-lean-evidence",
        action="store_true",
        help="Disable lean-evidence mode and send the full bloated payload (debug only).",
    )
    args = parser.parse_args()
    if args.no_lean_evidence:
        globals()["_LEAN_EVIDENCE_MODE"] = False

    if args.api_key_stdin:
        api_key = re.sub(r"\s+", "", sys.stdin.readline())
        if api_key:
            os.environ["NEBIUS_API_KEY"] = api_key

    if args.validate_gold:
        failures = validate_gold(args.gold)
        if failures:
            raise SystemExit(1)
        print(f"gold cases valid: {args.gold}")

    fixture_map_path: Path | None = None if args.no_fixture_map else args.fixture_map

    if args.rescore:
        rescore_summary = rescore_live_outputs(
            live_path=args.rescore,
            gold_path=args.gold,
            apply_normalizer=args.apply_normalizer,
            summary_out=args.summary_out,
            diff_out=args.diff_out,
            rescore_out=args.rescore_out,
            case_filters=set(args.case) if args.case else None,
        )
        print(
            f"rescore: core {rescore_summary['core_passed']}/{rescore_summary['total']}  "
            f"exact {rescore_summary['exact_passed']}/{rescore_summary['total']}  "
            f"normalizer={'on' if args.apply_normalizer else 'off'}"
        )
        return

    requests: list[dict[str, object]] = []
    if args.build_requests or args.run_live or args.model_sweep:
        requests = build_requests_from_gold(
            args.gold,
            args.input,
            set(args.case) if args.case else None,
            fixture_map_path=fixture_map_path,
        )
        write_jsonl(args.requests_out, requests)
        grafted = sum(1 for r in requests if r.get("evidence_source_fdc"))
        print(f"wrote requests: {args.requests_out} ({len(requests)} cases, {grafted} with grafted evidence)")

    if args.model_sweep:
        models = args.sweep_model or DEFAULT_MODEL_CANDIDATES
        run_model_sweep(
            requests,
            args.gold,
            models,
            args.sweep_out,
            args.pause_seconds,
            args.retry_attempts,
            args.retry_base_seconds,
        )

    if args.run_live:
        if args.two_pass:
            outputs = run_live_two_pass(
                gold_path=args.gold,
                input_path=args.input,
                case_filters=set(args.case) if args.case else None,
                fixture_map_path=fixture_map_path,
                model=args.model,
                output_path=args.outputs_out,
                pause_seconds=args.pause_seconds,
                retry_attempts=args.retry_attempts,
                retry_base_seconds=args.retry_base_seconds,
            )
        else:
            outputs = run_live(
                requests,
                args.model,
                args.outputs_out,
                args.pause_seconds,
                args.retry_attempts,
                args.retry_base_seconds,
            )
        print(f"wrote outputs: {args.outputs_out}")
        failures = validate_outputs(args.outputs_out, args.gold)
        if failures:
            raise SystemExit(1)

    if args.validate_outputs:
        failures = validate_outputs(args.validate_outputs, args.gold)
        if failures:
            raise SystemExit(1)
        print(f"outputs valid: {args.validate_outputs}")


if __name__ == "__main__":
    main()
