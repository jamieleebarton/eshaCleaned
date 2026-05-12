#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import csv
import json
import re
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from esha_nutrition import nutrition_for_esha
from schema import NutritionEstimate
from surface_lab_calculator import (
    LabProduct,
    _apply_surface_esha_override,
    _nutrition_from_row,
    _product_acceptance_reason,
    _resolve_surface,
    normalize_key,
)


ROOT = Path(__file__).resolve().parent.parent
IMPLEMENTATION = ROOT / "implementation"
OUT_DIR = IMPLEMENTATION / "output"
DEFAULT_RECIPES_CSV = Path("/Users/jamiebarton/Desktop/clean/recipe_pricing/output/recipes_final.csv")
DEFAULT_RETAIL_BRIDGE_CSV = OUT_DIR / "retail_canonical_surface_bridge.csv"
DEFAULT_OUT_RECIPES_CSV = OUT_DIR / "hestia_recipes_calculator_native.csv"
DEFAULT_OUT_RECIPES_SUMMARY = OUT_DIR / "hestia_recipes_calculator_native.summary.json"
DEFAULT_OUT_PACKAGE_DB = OUT_DIR / "food_packages_calculator_native.db"
DEFAULT_OUT_PACKAGE_SUMMARY = OUT_DIR / "food_packages_calculator_native.summary.json"
DEFAULT_OUT_INGREDIENT_META = OUT_DIR / "hestia_calculator_native_ingredient_meta.json"
DEFAULT_PRODUCT_IDENTITY_BRIDGE_CSV = OUT_DIR / "sparse_cascade_planner" / "product_identity_bridge.csv"
CANONICAL_ITEMS_CSV = IMPLEMENTATION / "canonical_items.csv"
SR28_FOOD_CSV = ROOT / "data" / "sr28_csv" / "food.csv"
FNDDS_MAIN_FOOD_DESC_CSV = ROOT / "data" / "fndds" / "MainFoodDesc16.csv"
PRODUCT_FIXY_V6_CSV = ROOT / "retail_mapper" / "product_esha_fixy.v6.csv"

IDENTITY_VERSION = "calculator_native_v2_esha_sr28_product_fndds_fallback"
MAX_PACKAGE_GRAMS = 50_000
MAX_PRICE_CENTS = 100_000

PACKAGE_SCHEMA = """
CREATE TABLE IF NOT EXISTS packages (
    fndds_code              TEXT    NOT NULL,
    food_description        TEXT,
    package_weight_grams    REAL,
    package_size_display    TEXT,
    product_count           INTEGER DEFAULT 1,
    is_plu                  INTEGER DEFAULT 0,
    plu_code                TEXT,
    plu_unit                TEXT,
    walmart_price_cents     INTEGER,
    kroger_price_cents      INTEGER,
    product_meta            TEXT,
    confidence_tier         INTEGER DEFAULT 0,
    source                  TEXT,
    created_at              TEXT    DEFAULT (datetime('now')),
    PRIMARY KEY (fndds_code, package_weight_grams)
);
CREATE INDEX IF NOT EXISTS idx_packages_key ON packages (fndds_code);
CREATE INDEX IF NOT EXISTS idx_packages_tier ON packages (confidence_tier);
CREATE INDEX IF NOT EXISTS idx_packages_source ON packages (source);
"""

WEAK_TOKENS = {
    "a",
    "an",
    "and",
    "with",
    "without",
    "for",
    "from",
    "fresh",
    "raw",
    "cooked",
    "prepared",
    "regular",
    "plain",
    "original",
    "natural",
    "organic",
    "food",
    "foods",
    "generic",
    "nfs",
    "nsv",
    "type",
}

WEAK_IDENTITY_OVERLAP_TOKENS = WEAK_TOKENS | {
    "baked",
    "boiled",
    "canned",
    "chopped",
    "cut",
    "drained",
    "dried",
    "fat",
    "frozen",
    "grilled",
    "ground",
    "large",
    "lean",
    "low",
    "mashed",
    "medium",
    "mix",
    "mixed",
    "powder",
    "reduced",
    "roasted",
    "salt",
    "salted",
    "small",
    "sugar",
    "sweetened",
    "unsalted",
    "unsweetened",
    "whole",
}

PREPARED_FORM_TOKENS = {
    "biscuit",
    "burger",
    "cake",
    "canned",
    "casserole",
    "cereal",
    "cooked",
    "cream",
    "dish",
    "fast",
    "frozen",
    "hamburger",
    "ice",
    "lunchmeat",
    "meal",
    "paste",
    "pizza",
    "recipe",
    "roast",
    "roasted",
    "roll",
    "salad",
    "sauteed",
    "sandwich",
    "soup",
    "spread",
    "taco",
    "topping",
    "whopper",
    "wrap",
}

SUBTYPE_TOKENS_BY_HEAD = {
    "muffin": {
        "almond",
        "banana",
        "blueberry",
        "bran",
        "chocolate",
        "corn",
        "cranberry",
        "english",
        "lemon",
        "nut",
        "nuts",
        "streusel",
    },
}

PACKAGE_TITLE_PREPARED_FOOD_TOKENS = {
    "muffin",
    "muffins",
    "topping",
    "toppings",
}

MAYO_FLAVOR_TOKENS = {
    "aioli",
    "avocado",
    "basil",
    "cajun",
    "canola",
    "cayenne",
    "chipotle",
    "curry",
    "dijon",
    "fat",
    "free",
    "garlic",
    "harissa",
    "horseradish",
    "japanese",
    "kewpie",
    "lemon",
    "light",
    "lite",
    "lime",
    "low",
    "mango",
    "nonfat",
    "oil",
    "olive",
    "peppercorn",
    "plant",
    "reduced",
    "rosemary",
    "soy",
    "sriracha",
    "tarragon",
    "vegan",
    "wasabi",
}

FORM_FAMILY_TOKENS = {
    "milk": {"buttermilk", "condensed", "evaporated", "filled", "goat", "oat", "almond", "coconut", "soy"},
    "mayonnaise": MAYO_FLAVOR_TOKENS | {"fat", "free", "light", "lite", "reduced", "vegan"},
    "bacon": {
        "back",
        "bit",
        "bits",
        "canadian",
        "flavor",
        "flavored",
        "grease",
        "imitation",
        "meatless",
        "powder",
        "real",
        "salt",
        "seasoning",
        "soy",
        "strip",
        "strips",
        "turkey",
        "vegan",
        "vegetarian",
        "veggie",
    },
    "chicken": {"lunchmeat", "sausage", "nugget", "tenderloin", "wing", "thigh"},
}

NONFOOD_PRODUCT_PHRASES = {
    "anti frizz",
    "anti-frizz",
    "aromatherapy",
    "bird food",
    "body spray",
    "body wash",
    "body oil",
    "candle making",
    "cat litter",
    "cat treat",
    "carrier oil",
    "conditioner",
    "cosmetic",
    "curl maker",
    "dry body oil",
    "diffuser",
    "brightening",
    "derma",
    "face and body",
    "face cream",
    "face skin",
    "for skin",
    "hair and body",
    "hair care",
    "hair gel",
    "hair growth",
    "hair mask",
    "hair oil",
    "hair remover",
    "hair serum",
    "hair spray",
    "hairitage",
    "hand soap",
    "liquid hand soap",
    "litter deodorizer",
    "lotion",
    "massage",
    "moisturizer",
    "nail",
    "nails",
    "pet food",
    "pet snack",
    "pet treat",
    "perfume",
    "shampoo",
    "skin care",
    "skin oil",
    "soap making",
    "wild bird food",
    "toning gloss",
}

NONFOOD_PRODUCT_TOKENS = {
    "candle",
    "deodorizer",
    "litter",
    "mouthwash",
    "petroleum",
    "shampoo",
    "soap",
    "supplement",
    "toothpaste",
    "unisex",
    "vaseline",
}

PACKAGE_MAYONNAISE_REJECT_TOKENS = MAYO_FLAVOR_TOKENS | {
    "fat",
    "flavor",
    "flavored",
    "flavour",
    "free",
    "light",
    "lite",
    "low",
    "lowfat",
    "nonfat",
    "plant",
    "reduced",
    "spicy",
    "vegan",
    "yolk",
}

PACKAGE_NATIVE_KEY_OVERRIDES = {
    "back bacon": ("ESHA:12008", "Canadian Bacon, cured", "surface_native_override:back_bacon"),
    "bacon bit": ("ESHA:27096", "Bacon, bits, real, serving", "surface_native_override:bacon_bits"),
    "bacon bits": ("ESHA:27096", "Bacon, bits, real, serving", "surface_native_override:bacon_bits"),
    "canadian bacon": ("ESHA:12008", "Canadian Bacon, cured", "surface_native_override:canadian_bacon"),
    "chipotle mayonnaise": ("ESHA:22937", "Dressing, mayonnaise, chipotle", "surface_native_override:chipotle_mayonnaise"),
    "egg": ("ESHA:19500", "Egg, whole, raw", "surface_native_override:egg"),
    "eggs": ("ESHA:19500", "Egg, whole, raw", "surface_native_override:egg"),
    "horseradish mayonnaise": ("ESHA:33347", "Dressing, mayonnaise, horseradish", "surface_native_override:horseradish_mayonnaise"),
    "ham": ("ESHA:12005", "Pork, cured ham, whole, roasted", "surface_native_override:ham"),
    "beef stew meat": ("ESHA:27997", "Beef, stew meat, chuck, raw", "surface_native_override:beef_stew_meat"),
    "boneless beef stew meat": ("ESHA:27997", "Beef, stew meat, chuck, raw", "surface_native_override:beef_stew_meat"),
    "beef chuck stew meat": ("ESHA:27997", "Beef, stew meat, chuck, raw", "surface_native_override:beef_stew_meat"),
    "chuck stew meat": ("ESHA:27997", "Beef, stew meat, chuck, raw", "surface_native_override:beef_stew_meat"),
    "stew meat": ("ESHA:27997", "Beef, stew meat, chuck, raw", "surface_native_override:beef_stew_meat"),
    "imitation bacon": ("ESHA:7509", "Vegetarian Meat, bacon, strips", "surface_native_override:imitation_bacon"),
    "imitation bacon bit": ("ESHA:27044", "Vegetarian Meat, bacon bits", "surface_native_override:imitation_bacon_bits"),
    "imitation bacon bits": ("ESHA:27044", "Vegetarian Meat, bacon bits", "surface_native_override:imitation_bacon_bits"),
    "mango mayonnaise": ("ESHA:22945", "Dressing, mayonnaise, mango", "surface_native_override:mango_mayonnaise"),
    "pork shoulder": ("ESHA:12221", "Pork, shoulder, whole, raw", "surface_native_override:pork_shoulder"),
    "pork shoulder butt": ("ESHA:12221", "Pork, shoulder, whole, raw", "surface_native_override:pork_shoulder"),
    "pork butt": ("ESHA:12221", "Pork, shoulder, whole, raw", "surface_native_override:pork_shoulder"),
    "pork chop": ("ESHA:12028", "Pork, chop, whole loin, raw", "surface_native_override:pork_chop"),
    "pork chops": ("ESHA:12028", "Pork, chop, whole loin, raw", "surface_native_override:pork_chop"),
    "real bacon bit": ("ESHA:27096", "Bacon, bits, real, serving", "surface_native_override:bacon_bits"),
    "real bacon bits": ("ESHA:27096", "Bacon, bits, real, serving", "surface_native_override:bacon_bits"),
    "soy mayonnaise": ("ESHA:8032", "Dressing, mayonnaise type, soybean", "surface_native_override:soy_mayonnaise"),
    "turkey bacon": ("ESHA:13125", "Bacon, turkey", "surface_native_override:turkey_bacon"),
    "vegan bacon": ("ESHA:7509", "Vegetarian Meat, bacon, strips", "surface_native_override:vegan_bacon"),
    "vegetarian bacon": ("ESHA:7509", "Vegetarian Meat, bacon, strips", "surface_native_override:vegetarian_bacon"),
    "vegetarian bacon bit": ("ESHA:27044", "Vegetarian Meat, bacon bits", "surface_native_override:vegetarian_bacon_bits"),
    "vegetarian bacon bits": ("ESHA:27044", "Vegetarian Meat, bacon bits", "surface_native_override:vegetarian_bacon_bits"),
    "veggie bacon": ("ESHA:7509", "Vegetarian Meat, bacon, strips", "surface_native_override:veggie_bacon"),
    "whole chicken": ("ESHA:15071", "Chicken, whole, unpeeled, raw", "surface_native_override:whole_chicken"),
    "skin on chicken": ("ESHA:15071", "Chicken, whole, unpeeled, raw", "surface_native_override:whole_chicken"),
}

MANUAL_PACKAGE_ROWS: list[dict[str, Any]] = [
    {
        "key": "ESHA:26013",
        "description": "Herb, parsley, sprigs, fresh",
        "grams": 21.263,
        "walmart_price_cents": 178,
        "kroger_price_cents": None,
        "samples": [
            {
                "source": "walmart",
                "upc": "818042022146",
                "name": "Fresh Parsley, 0.5 oz Clamshell",
                "canonical_surface": "fresh parsley sprig",
                "canonical_shopping_item": "fresh parsley",
                "search_term": "parsley",
                "cents": 178,
                "gate_reason": "manual_package_seed:fresh_parsley_sprigs",
            }
        ],
        "source": "manual_calculator_native_package_seed",
    },
    {
        "key": "ESHA:26013",
        "description": "Herb, parsley, sprigs, fresh",
        "grams": 45.359,
        "walmart_price_cents": None,
        "kroger_price_cents": 219,
        "samples": [
            {
                "source": "kroger",
                "upc": "1111018155",
                "name": "Simple Truth Organic Italian Parsley",
                "canonical_surface": "fresh parsley sprig",
                "canonical_shopping_item": "fresh parsley",
                "search_term": "parsley",
                "cents": 219,
                "gate_reason": "manual_package_seed:fresh_parsley_sprigs",
            }
        ],
        "source": "manual_calculator_native_package_seed",
    },
    {
        "key": "ESHA:12132",
        "description": "Pork, cured ham, steak, extra lean",
        "grams": 226.796,
        "walmart_price_cents": None,
        "kroger_price_cents": 250,
        "samples": [
            {
                "source": "kroger",
                "upc": "7080004879",
                "name": "Smithfield Anytime Favorites Boneless Hickory Smoked Ham Steak",
                "canonical_surface": "ham steak",
                "canonical_shopping_item": "ham steak",
                "search_term": "ham steak",
                "cents": 250,
                "gate_reason": "manual_package_seed:ham_steak",
            }
        ],
        "source": "manual_calculator_native_package_seed",
    },
    {
        "key": "ESHA:12132",
        "description": "Pork, cured ham, steak, extra lean",
        "grams": 535.239,
        "walmart_price_cents": None,
        "kroger_price_cents": 500,
        "samples": [
            {
                "source": "kroger",
                "upc": "4420086008",
                "name": "Cook's Hickory Ham Steak",
                "canonical_surface": "ham steak",
                "canonical_shopping_item": "ham steak",
                "search_term": "ham steak",
                "cents": 500,
                "gate_reason": "manual_package_seed:ham_steak",
            }
        ],
        "source": "manual_calculator_native_package_seed",
    },
    {
        "key": "ESHA:12132",
        "description": "Pork, cured ham, steak, extra lean",
        "grams": 907.184,
        "walmart_price_cents": None,
        "kroger_price_cents": 1249,
        "samples": [
            {
                "source": "kroger",
                "upc": "7590000088",
                "name": "Bob Evans Fully Cooked Ham Steaks",
                "canonical_surface": "ham steak",
                "canonical_shopping_item": "ham steak",
                "search_term": "ham steak",
                "cents": 1249,
                "gate_reason": "manual_package_seed:ham_steak",
            }
        ],
        "source": "manual_calculator_native_package_seed",
    },
    {
        "key": "ESHA:27997",
        "description": "Beef, stew meat, chuck, raw",
        "grams": 451.322,
        "walmart_price_cents": 878,
        "kroger_price_cents": None,
        "samples": [
            {
                "source": "walmart",
                "upc": "221495000003",
                "name": "Beef Stew Meat, Tray, Fresh, 0.75 - 1.25 lb",
                "canonical_surface": "beef stew meat",
                "canonical_shopping_item": "beef stew meat",
                "search_term": "beef stew meat",
                "cents": 878,
                "gate_reason": "manual_package_seed:beef_stew_meat",
            }
        ],
        "source": "manual_calculator_native_package_seed",
    },
    {
        "key": "ESHA:27997",
        "description": "Beef, stew meat, chuck, raw",
        "grams": 566.987,
        "walmart_price_cents": 955,
        "kroger_price_cents": None,
        "samples": [
            {
                "source": "walmart",
                "upc": "259825000003",
                "name": "Lean Beef Stew Meat, Tray, Fresh, 0.75 - 1.25 lb",
                "canonical_surface": "beef stew meat",
                "canonical_shopping_item": "beef stew meat",
                "search_term": "beef stew meat",
                "cents": 955,
                "gate_reason": "manual_package_seed:beef_stew_meat",
            }
        ],
        "source": "manual_calculator_native_package_seed",
    },
    {
        "key": "ESHA:27997",
        "description": "Beef, stew meat, chuck, raw",
        "grams": 1020.582,
        "walmart_price_cents": None,
        "kroger_price_cents": 899,
        "samples": [
            {
                "source": "kroger",
                "upc": "29101750000",
                "name": "Boneless Stew Beef Family Pack",
                "canonical_surface": "beef stew meat",
                "canonical_shopping_item": "beef stew meat",
                "search_term": "beef stew meat",
                "cents": 899,
                "gate_reason": "manual_package_seed:beef_stew_meat",
            }
        ],
        "source": "manual_calculator_native_package_seed",
    },
    {
        "key": "ESHA:12028",
        "description": "Pork, chop, whole loin, raw",
        "grams": 526.167,
        "walmart_price_cents": None,
        "kroger_price_cents": 479,
        "samples": [
            {
                "source": "kroger",
                "upc": "20324250000",
                "name": "Thin Cut Bone-In Pork Loin Center-Cut Chop",
                "canonical_surface": "pork chop",
                "canonical_shopping_item": "pork chop",
                "search_term": "pork chop",
                "cents": 479,
                "gate_reason": "manual_package_seed:pork_chop",
            }
        ],
        "source": "manual_calculator_native_package_seed",
    },
    {
        "key": "ESHA:12028",
        "description": "Pork, chop, whole loin, raw",
        "grams": 625.957,
        "walmart_price_cents": None,
        "kroger_price_cents": 500,
        "samples": [
            {
                "source": "kroger",
                "upc": "1111064148",
                "name": "Kroger Fresh Natural Pork Loin Chops Boneless",
                "canonical_surface": "pork chop",
                "canonical_shopping_item": "pork chop",
                "search_term": "pork chop",
                "cents": 500,
                "gate_reason": "manual_package_seed:pork_chop",
            }
        ],
        "source": "manual_calculator_native_package_seed",
    },
    {
        "key": "ESHA:12028",
        "description": "Pork, chop, whole loin, raw",
        "grams": 907.184,
        "walmart_price_cents": None,
        "kroger_price_cents": 1000,
        "samples": [
            {
                "source": "kroger",
                "upc": "1111063445",
                "name": "Kroger Boneless Center Cut Pork Loin Chops",
                "canonical_surface": "pork chop",
                "canonical_shopping_item": "pork chop",
                "search_term": "pork chop",
                "cents": 1000,
                "gate_reason": "manual_package_seed:pork_chop",
            }
        ],
        "source": "manual_calculator_native_package_seed",
    },
    {
        "key": "ESHA:12221",
        "description": "Pork, shoulder, whole, raw",
        "grams": 1474.174,
        "walmart_price_cents": None,
        "kroger_price_cents": 974,
        "samples": [
            {
                "source": "kroger",
                "upc": "25338300000",
                "name": "Kroger Bone-In Pork Shoulder Steaks (3 per pack)",
                "canonical_surface": "pork shoulder",
                "canonical_shopping_item": "pork shoulder",
                "search_term": "pork shoulder",
                "cents": 974,
                "gate_reason": "manual_package_seed:pork_shoulder",
            }
        ],
        "source": "manual_calculator_native_package_seed",
    },
    {
        "key": "ESHA:12221",
        "description": "Pork, shoulder, whole, raw",
        "grams": 2268.0,
        "walmart_price_cents": 1499,
        "kroger_price_cents": None,
        "samples": [
            {
                "source": "walmart",
                "upc": "225353000006",
                "name": "Pork Butt Shoulder Roast, Bone-In, about 5 lb",
                "canonical_surface": "pork shoulder",
                "canonical_shopping_item": "pork shoulder",
                "search_term": "pork shoulder",
                "cents": 1499,
                "gate_reason": "manual_package_seed:pork_shoulder",
            }
        ],
        "source": "manual_calculator_native_package_seed",
    },
    {
        "key": "ESHA:12221",
        "description": "Pork, shoulder, whole, raw",
        "grams": 3401.94,
        "walmart_price_cents": None,
        "kroger_price_cents": 2243,
        "samples": [
            {
                "source": "kroger",
                "upc": "20799300000",
                "name": "Kroger Fresh Natural Pork Shoulder Butt Bone In",
                "canonical_surface": "pork shoulder",
                "canonical_shopping_item": "pork shoulder",
                "search_term": "pork shoulder",
                "cents": 2243,
                "gate_reason": "manual_package_seed:pork_shoulder",
            }
        ],
        "source": "manual_calculator_native_package_seed",
    },
    {
        "key": "ESHA:15071",
        "description": "Chicken, whole, unpeeled, raw",
        "grams": 1886.943,
        "walmart_price_cents": None,
        "kroger_price_cents": 1660,
        "samples": [
            {
                "source": "kroger",
                "upc": "20891150000",
                "name": "Simple Truth Organic Fresh Organic Whole Chicken with Giblets",
                "canonical_surface": "whole chicken",
                "canonical_shopping_item": "whole chicken",
                "search_term": "whole chicken",
                "cents": 1660,
                "gate_reason": "manual_package_seed:whole_chicken",
            }
        ],
        "source": "manual_calculator_native_package_seed",
    },
    {
        "key": "ESHA:15071",
        "description": "Chicken, whole, unpeeled, raw",
        "grams": 2381.348,
        "walmart_price_cents": 695,
        "kroger_price_cents": None,
        "samples": [
            {
                "source": "walmart",
                "upc": "259407000001",
                "name": "Foster Farms Fresh & Natural Cage Free Whole Chicken",
                "canonical_surface": "whole chicken",
                "canonical_shopping_item": "whole chicken",
                "search_term": "whole chicken",
                "cents": 695,
                "gate_reason": "manual_package_seed:whole_chicken",
            }
        ],
        "source": "manual_calculator_native_package_seed",
    },
    {
        "key": "ESHA:19508",
        "description": "Egg Yolk, raw, large",
        "grams": 300.0,
        "walmart_price_cents": 96,
        "kroger_price_cents": None,
        "samples": [
            {
                "source": "walmart",
                "upc": "078742186839",
                "name": "Great Value Cage-Free Grade AA Large White Eggs, 6 Count",
                "canonical_surface": "egg yolk",
                "canonical_shopping_item": "eggs",
                "search_term": "egg yolks",
                "cents": 96,
                "gate_reason": "manual_package_seed:egg_yolk_buy_shell_eggs",
            }
        ],
        "source": "manual_calculator_native_package_seed",
    },
    {
        "key": "ESHA:19508",
        "description": "Egg Yolk, raw, large",
        "grams": 600.0,
        "walmart_price_cents": 167,
        "kroger_price_cents": None,
        "samples": [
            {
                "source": "walmart",
                "upc": "078742186839",
                "name": "Great Value Large White Eggs, 12 Count",
                "canonical_surface": "egg yolk",
                "canonical_shopping_item": "eggs",
                "search_term": "egg yolks",
                "cents": 167,
                "gate_reason": "manual_package_seed:egg_yolk_buy_shell_eggs",
            }
        ],
        "source": "manual_calculator_native_package_seed",
    },
]

COVERAGE_PACKAGE_SEED_RULES: list[dict[str, Any]] = [
    {
        "id": "yellow_onion",
        "key": "ESHA:7499",
        "description": "Onion, yellow, fresh, chopped",
        "any_phrases": ["yellow onion", "white onion", "cipollini onion"],
        "reject_phrases": [
            "french fried",
            "green onion",
            "onion dip",
            "onion powder",
            "onion ring",
            "onion soup",
            "seasoning",
        ],
        "min_grams": 100,
    },
    {
        "id": "red_onion",
        "key": "ESHA:7805",
        "description": "Onion, red, fresh, medium, whole, 2 1/2\"",
        "any_phrases": ["red onion"],
        "reject_phrases": ["french fried", "green onion", "onion dip", "onion powder", "onion ring", "onion soup"],
        "min_grams": 100,
    },
    {
        "id": "sour_cream",
        "key": "ESHA:555",
        "description": "Sour Cream",
        "any_phrases": ["sour cream"],
        "reject_phrases": ["chips", "dip", "onion", "pringles", "ruffles", "seasoning"],
        "min_grams": 100,
    },
    {
        "id": "vanilla_icing",
        "key": "ESHA:9081",
        "description": "Icing, vanilla",
        "any_phrases": ["vanilla frosting", "vanilla icing"],
        "reject_phrases": ["cake", "cookie", "donut", "ice cream", "protein"],
        "min_grams": 100,
    },
    {
        "id": "ground_oregano",
        "key": "ESHA:26009",
        "description": "Herb, oregano, ground",
        "any_phrases": ["ground oregano", "oregano leaves", "oregano leaf"],
        "reject_phrases": ["oil", "seasoning blend"],
        "min_grams": 5,
        "max_grams": 1000,
    },
    {
        "id": "old_fashioned_oats",
        "key": "ESHA:93116",
        "description": "Oats, rolled, old fashioned",
        "any_phrases": ["old fashioned oats", "old-fashioned oats", "rolled oats"],
        "reject_phrases": ["bar", "cereal", "cookie", "granola", "instant", "oatmeal cup", "protein"],
        "min_grams": 200,
    },
    {
        "id": "evaporated_milk",
        "key": "ESHA:20952",
        "description": "Milk, evaporated",
        "any_phrases": ["evaporated milk"],
        "reject_phrases": ["filled", "sweetened condensed"],
        "min_grams": 200,
    },
    {
        "id": "garlic_salt",
        "key": "ESHA:669",
        "description": "Seasoning, garlic salt",
        "any_phrases": ["garlic salt"],
        "reject_phrases": ["chips", "pretzel"],
        "min_grams": 10,
        "max_grams": 2000,
    },
    {
        "id": "sweetened_condensed_milk",
        "key": "ESHA:20950",
        "description": "Milk, condensed, sweetened",
        "any_phrases": ["sweetened condensed milk"],
        "reject_phrases": ["evaporated"],
        "min_grams": 200,
    },
    {
        "id": "fresh_leeks",
        "key": "ESHA:5206",
        "description": "Leeks, bulb & lower leaf, fresh",
        "any_phrases": ["fresh leek", "fresh leeks", "leeks"],
        "reject_phrases": ["soup", "seasoning"],
        "min_grams": 100,
    },
    {
        "id": "fresh_cabbage",
        "key": "ESHA:6765",
        "description": "Cabbage, fresh, leaf",
        "any_phrases": ["cabbage"],
        "reject_phrases": ["coleslaw", "kimchi", "salad", "sauerkraut", "slaw"],
        "min_grams": 200,
    },
    {
        "id": "dark_brown_sugar",
        "key": "ESHA:45896",
        "description": "Sugar, brown, dark",
        "any_phrases": ["dark brown sugar"],
        "reject_phrases": ["cereal", "oatmeal", "protein"],
        "min_grams": 200,
    },
    {
        "id": "cherry_tomatoes",
        "key": "ESHA:90530",
        "description": "Tomatoes, red, cherry, fresh, year round average",
        "any_phrases": ["cherry tomatoes", "grape tomatoes"],
        "reject_phrases": ["sauce", "seasoning"],
        "min_grams": 100,
    },
    {
        "id": "seasoned_salt",
        "key": "ESHA:91928",
        "description": "Seasoning, salt",
        "any_phrases": ["seasoned salt", "seasoning salt"],
        "reject_phrases": ["chips", "pretzel"],
        "min_grams": 10,
        "max_grams": 2000,
    },
    {
        "id": "self_rising_flour",
        "key": "ESHA:38033",
        "description": "Flour, all purpose, self rising, white, enriched",
        "any_phrases": ["self rising flour", "self-rising flour"],
        "min_grams": 500,
    },
    {
        "id": "sweet_onion",
        "key": "ESHA:9548",
        "description": "Onion, sweet, fresh",
        "any_phrases": ["sweet onion", "sweet onions"],
        "reject_phrases": ["dip", "french fried", "onion powder", "onion ring", "onion soup"],
        "min_grams": 100,
    },
    {
        "id": "raw_potatoes",
        "key": "SR28:170026",
        "description": "Potatoes, flesh and skin, raw",
        "any_phrases": ["gold potatoes", "white potatoes", "yellow potatoes"],
        "reject_phrases": ["chips", "french fries", "hash browns", "mashed", "salad", "tots"],
        "min_grams": 300,
    },
    {
        "id": "red_potatoes",
        "key": "ESHA:51333",
        "description": "Potatoes, red, unpeeled",
        "any_phrases": ["red potatoes"],
        "reject_phrases": ["chips", "mashed", "salad"],
        "min_grams": 300,
    },
    {
        "id": "fresh_rosemary",
        "key": "ESHA:26627",
        "description": "Herb, rosemary, fresh",
        "any_phrases": ["fresh rosemary"],
        "reject_phrases": ["dried", "ground", "seasoning"],
        "min_grams": 5,
        "max_grams": 200,
    },
    {
        "id": "dry_egg_noodles",
        "key": "SR28:169731",
        "description": "Noodles, egg, dry, enriched",
        "any_phrases": ["egg noodles"],
        "reject_phrases": ["angel hair", "keto", "ready", "soup"],
        "min_grams": 100,
    },
    {
        "id": "semisweet_baking_chocolate",
        "key": "ESHA:41524",
        "description": "Baking Chocolate, semisweet, bar",
        "any_phrases": ["semisweet baking chocolate", "semi sweet baking chocolate", "semi-sweet baking chocolate"],
        "reject_phrases": ["chips", "cookie"],
        "min_grams": 50,
    },
    {
        "id": "skinless_chicken_thighs",
        "key": "ESHA:15061",
        "description": "Chicken, thigh, skinless, raw",
        "any_phrases": ["boneless skinless chicken thighs", "skinless chicken thighs"],
        "reject_phrases": ["breaded", "cooked", "grilled", "seasoned"],
        "min_grams": 300,
    },
    {
        "id": "dry_pasta_generic",
        "key": "SR28:169736",
        "description": "Pasta, dry, enriched",
        "any_phrases": ["elbow macaroni", "penne pasta", "rotini pasta", "spaghetti", "spaghetti pasta"],
        "reject_phrases": [
            "canned",
            "cheese",
            "cheesy",
            "chickpea",
            "cooked",
            "edamame",
            "four cheese",
            "frozen",
            "gluten free",
            "gluten-free",
            "knorr",
            "meal",
            "meatballs",
            "microwave",
            "pasta sides",
            "protein pasta",
            "ravioli",
            "ready",
            "rings",
            "sauce",
            "side",
            "sides",
            "spaghetti o",
            "spaghettios",
        ],
        "min_grams": 100,
    },
    {
        "id": "ground_turmeric",
        "key": "ESHA:26034",
        "description": "Spice, turmeric, ground",
        "alias_keys": [
            {"key": "ESHA:35024", "description": "Herb, turmeric, dried"},
        ],
        "any_phrases": ["ground turmeric", "turmeric powder"],
        "reject_phrases": ["capsule", "supplement"],
        "min_grams": 10,
        "max_grams": 1000,
    },
    {
        "id": "fresh_ginger_root",
        "key": "ESHA:90442",
        "description": "Spice, ginger root, fresh",
        "any_phrases": ["fresh ginger", "ginger root", "minced ginger", "ginger paste", "ginger stir-in paste"],
        "reject_phrases": [
            "ale",
            "beer",
            "brew",
            "cookie",
            "cookies",
            "dressing",
            "dried",
            "dry",
            "garlic",
            "ground",
            "juice",
            "kit",
            "kombucha",
            "pickled",
            "powder",
            "powdered",
            "salad",
            "sauce",
            "shot",
            "snap",
            "snaps",
            "soda",
            "sushi",
            "syrup",
            "topper",
        ],
        "min_grams": 10,
        "max_grams": 1000,
    },
    {
        "id": "ground_ginger",
        "key": "ESHA:4086",
        "description": "Spice, ginger, ground",
        "any_phrases": ["ground ginger", "ginger powder", "powdered ginger"],
        "reject_phrases": [
            "ale",
            "beer",
            "brew",
            "capsule",
            "cookie",
            "cookies",
            "dressing",
            "extract",
            "fresh",
            "juice",
            "pickled",
            "root",
            "sauce",
            "shot",
            "snap",
            "snaps",
            "soda",
            "supplement",
            "sushi",
            "syrup",
        ],
        "min_grams": 10,
        "max_grams": 1000,
    },
    {
        "id": "sweetened_coconut_flakes",
        "key": "ESHA:4511",
        "description": "Coconut, dried, shredded, sweetened, 7oz package",
        "alias_keys": [
            {
                "key": "SR28:170578",
                "description": "Nuts, coconut meat, dried (desiccated), sweetened, flaked, canned",
            },
        ],
        "any_phrases": [
            "angel flake coconut",
            "angel flake",
            "sweetened coconut flakes",
            "sweetened shredded coconut",
        ],
        "reject_phrases": ["milk", "oil", "unsweetened", "water"],
        "min_grams": 50,
    },
    {
        "id": "whipped_topping",
        "key": "FNDDS:12220200",
        "description": "Whipped topping",
        "any_phrases": ["cool whip", "whipped topping"],
        "reject_phrases": ["can", "spray"],
        "min_grams": 100,
    },
    {
        "id": "rice_vinegar",
        "key": "ESHA:35186",
        "description": "Vinegar, rice, 42 grain",
        "any_phrases": ["rice vinegar"],
        "reject_phrases": ["chips"],
        "min_grams": 100,
    },
    {
        "id": "italian_dressing",
        "key": "SR28:171019",
        "description": "Salad dressing, italian dressing, commercial, regular",
        "any_phrases": ["italian dressing"],
        "reject_phrases": ["seasoning mix"],
        "min_grams": 100,
    },
    {
        "id": "powdered_sugar",
        "key": "SR28:169656",
        "description": "Sugars, powdered",
        "any_phrases": ["confectioners sugar", "powdered sugar"],
        "reject_phrases": ["donut"],
        "min_grams": 100,
    },
    {
        "id": "chili_sauce",
        "key": "ESHA:434",
        "description": "Sauce, chili",
        "any_phrases": ["chili sauce"],
        "reject_phrases": ["garlic", "sweet"],
        "min_grams": 100,
    },
    {
        "id": "ground_cardamom",
        "key": "ESHA:26039",
        "description": "Spice, cardamom, ground",
        "any_phrases": ["ground cardamom"],
        "min_grams": 5,
        "max_grams": 1000,
    },
    {
        "id": "whole_black_pepper",
        "key": "ESHA:26901",
        "description": "Spice, pepper, black, whole",
        "any_phrases": ["black peppercorns", "whole black pepper"],
        "reject_phrases": ["grinder"],
        "min_grams": 10,
        "max_grams": 1000,
    },
    {
        "id": "russet_potatoes",
        "key": "ESHA:48587",
        "description": "Potatoes, russet, fresh",
        "any_phrases": ["russet potatoes"],
        "reject_phrases": ["chips", "fries", "mashed"],
        "min_grams": 300,
    },
    {
        "id": "dill_weed",
        "key": "ESHA:26021",
        "description": "Herb, dill weed, dried",
        "any_phrases": ["dill weed"],
        "reject_phrases": ["dip", "pickle"],
        "min_grams": 5,
        "max_grams": 1000,
    },
    {
        "id": "quick_oats",
        "key": "ESHA:92017",
        "description": "Oats, rolled, quick, #21, non-gmo, dry",
        "any_phrases": ["1 minute oats", "quick oats"],
        "reject_phrases": ["bar", "cup", "instant oatmeal", "protein"],
        "min_grams": 200,
    },
    {
        "id": "roma_tomatoes",
        "key": "ESHA:6492",
        "description": "Tomatoes, roma, fresh, year round average, fresh",
        "any_phrases": ["roma tomatoes"],
        "reject_phrases": ["sauce"],
        "min_grams": 100,
    },
    {
        "id": "low_sodium_soy_sauce",
        "key": "ESHA:90035",
        "description": "Sauce, soy, low sodium, from soy & wheat",
        "any_phrases": ["low sodium soy sauce", "less sodium soy sauce"],
        "min_grams": 100,
    },
    {
        "id": "mini_marshmallows",
        "key": "ESHA:23008",
        "description": "Marshmallows, miniature",
        "any_phrases": ["mini marshmallows", "miniature marshmallows"],
        "reject_phrases": ["cereal", "hot cocoa"],
        "min_grams": 50,
    },
    {
        "id": "mixed_nuts",
        "key": "SR28:170585",
        "description": "Nuts, mixed nuts, dry roasted, with peanuts, without salt added",
        "any_phrases": ["mixed nuts"],
        "reject_phrases": ["chocolate", "trail mix"],
        "min_grams": 50,
    },
    {
        "id": "stewed_tomatoes",
        "key": "SR28:170052",
        "description": "Tomatoes, red, ripe, canned, stewed",
        "any_phrases": ["stewed tomatoes"],
        "min_grams": 200,
    },
    {
        "id": "fresh_tarragon",
        "key": "ESHA:52403",
        "description": "Herb, tarragon, fresh",
        "any_phrases": ["fresh tarragon"],
        "reject_phrases": ["dried"],
        "min_grams": 5,
        "max_grams": 200,
    },
    {
        "id": "prepared_mustard",
        "key": "ESHA:45336",
        "description": "Mustard, prepared, pure",
        "alias_keys": [
            {"key": "ESHA:18031", "description": "Mustard, yellow"},
        ],
        "any_phrases": ["prepared mustard", "yellow mustard"],
        "reject_phrases": ["honey mustard", "pretzel", "seed", "seeds"],
        "min_grams": 100,
    },
    {
        "id": "water_chestnuts",
        "key": "SR28:170067",
        "description": "Waterchestnuts, chinese, canned, solids and liquids",
        "any_phrases": ["water chestnuts"],
        "reject_phrases": ["flour"],
        "min_grams": 100,
    },
    {
        "id": "pinto_beans",
        "key": "ESHA:27335",
        "description": "Beans, pinto",
        "any_phrases": ["pinto beans"],
        "reject_phrases": ["dip", "soup"],
        "min_grams": 200,
    },
    {
        "id": "broccoli_florets",
        "key": "ESHA:36021",
        "description": "Broccoli, florets",
        "any_phrases": ["broccoli florets"],
        "reject_phrases": ["cheese sauce", "seasoned"],
        "min_grams": 100,
    },
    {
        "id": "ground_coriander_seed",
        "key": "SR28:170922",
        "description": "Spices, coriander seed",
        "any_phrases": ["coriander powder", "coriander seed", "ground coriander"],
        "reject_phrases": ["cilantro", "leaf", "leaves", "sauce"],
        "min_grams": 5,
        "max_grams": 1000,
    },
    {
        "id": "tomato_pasta_sauce",
        "key": "SR28:171192",
        "description": "Sauce, pasta, spaghetti/marinara, ready-to-serve",
        "any_phrases": ["marinara sauce", "pasta sauce", "spaghetti sauce", "tomato sauce"],
        "reject_phrases": [
            "base",
            "beans",
            "blend",
            "boyardee",
            "chef boyardee",
            "chili",
            "meatballs",
            "meatloaf",
            "mix",
            "pork",
            "powder",
            "ravioli",
            "seasoning",
            "soup",
            "soups",
        ],
        "min_grams": 200,
    },
    {
        "id": "mandarin_oranges",
        "key": "ESHA:31312",
        "description": "Mandarin Oranges",
        "any_phrases": ["mandarin orange", "mandarin oranges"],
        "reject_phrases": ["pancake", "pancakes", "vodka"],
        "min_grams": 200,
    },
    {
        "id": "spring_onions",
        "key": "ESHA:90485",
        "description": "Onion, spring, tops & bulb, fresh, large",
        "any_phrases": ["green onion", "green onions", "scallion", "scallions", "spring onion", "spring onions"],
        "reject_phrases": ["dip", "mix", "seasoning"],
        "min_grams": 50,
    },
    {
        "id": "baby_carrots",
        "key": "ESHA:9329",
        "description": "Carrot, baby, fresh",
        "any_phrases": ["baby carrot", "baby carrots"],
        "reject_phrases": ["baby food", "canned", "frozen", "pickled"],
        "min_grams": 100,
    },
    {
        "id": "tomato_puree",
        "key": "SR28:170460",
        "description": "Tomato products, canned, puree, without salt added",
        "any_phrases": ["passata", "pureed tomatoes", "tomato puree"],
        "reject_phrases": ["sun dried", "sun-dried"],
        "min_grams": 200,
    },
    {
        "id": "whole_kernel_corn",
        "key": "ESHA:45268",
        "description": "Corn, sweet, kernel",
        "any_phrases": ["kernel corn", "sweet corn", "whole kernel corn"],
        "reject_phrases": ["baby food", "chips", "creamed", "muffin", "popcorn"],
        "min_grams": 200,
    },
    {
        "id": "frozen_peas",
        "key": "ESHA:1817",
        "description": "Peas, frozen, FS",
        "any_phrases": ["frozen green peas", "frozen peas", "frozen sweet peas"],
        "reject_phrases": [
            "blackeye",
            "black-eyed",
            "carrot",
            "carrots",
            "dried",
            "edamame",
            "freeze dried",
            "freeze-dried",
            "mix",
            "mixed",
            "snap",
            "split",
            "stir-fry",
            "stir fry",
            "wasabi",
        ],
        "min_grams": 200,
    },
    {
        "id": "green_peas",
        "key": "ESHA:5116",
        "description": "Peas, green, fresh",
        "any_phrases": ["green peas", "sweet peas"],
        "reject_phrases": ["baby food", "crisps", "frozen", "snack", "snap", "split", "soup", "wasabi"],
        "min_grams": 200,
    },
    {
        "id": "fresh_bananas",
        "key": "ESHA:51329",
        "description": "Banana",
        "any_phrases": ["banana", "bananas"],
        "reject_phrases": [
            "baby food",
            "banana boat",
            "bar",
            "bars",
            "bread",
            "cheerios",
            "chips",
            "flower",
            "ice cream",
            "leaf",
            "lotion",
            "muffin",
            "pudding",
            "schnapps",
            "smoothie",
            "spf",
            "spray",
            "sunscreen",
            "yogurt",
        ],
        "min_grams": 100,
    },
    {
        "id": "puff_pastry",
        "key": "SR28:172790",
        "description": "Puff pastry, frozen, ready-to-bake",
        "any_phrases": ["puff pastry"],
        "reject_phrases": ["cream filled", "cream puff", "cream puffs", "cookie", "cookies"],
        "min_grams": 100,
    },
    {
        "id": "walnut_halves_pieces",
        "key": "ESHA:49277",
        "description": "Nuts, walnuts, halves & pieces, raw",
        "any_phrases": ["chopped walnuts", "walnut halves", "walnut pieces", "walnuts"],
        "reject_phrases": ["banana", "brownie", "candied", "cereal", "chocolate", "coated", "ice cream", "mixed nuts"],
        "min_grams": 50,
    },
    {
        "id": "golden_raisins",
        "key": "ESHA:3934",
        "description": "Raisins, golden, seedless",
        "any_phrases": ["golden raisins"],
        "reject_phrases": ["bread", "cereal"],
        "min_grams": 50,
    },
    {
        "id": "food_coloring",
        "key": "FNDDS:94000000",
        "description": "Food coloring",
        "any_phrases": ["food color", "food coloring", "food dye"],
        "reject_phrases": [
            "chips",
            "dragon fruit",
            "dragonfruit",
            "no food coloring",
            "powder",
            "smoothies",
            "sweet potato",
            "tortillas",
        ],
        "min_grams": 5,
        "max_grams": 1000,
    },
    {
        "id": "fresh_sage",
        "key": "ESHA:26311",
        "description": "Herb, sage, fresh, INTL",
        "any_phrases": ["fresh sage"],
        "reject_phrases": ["dried", "ground", "rubbed"],
        "min_grams": 5,
        "max_grams": 200,
    },
    {
        "id": "dried_sage",
        "key": "ESHA:35048",
        "description": "Herb, sage, leaf, dried",
        "any_phrases": ["dried sage", "ground sage", "rubbed sage", "sage leaves"],
        "reject_phrases": ["fresh", "pineapple"],
        "min_grams": 5,
        "max_grams": 1000,
    },
    {
        "id": "bread_crumbs",
        "key": "SR28:174928",
        "description": "Bread, crumbs, dry, grated, plain",
        "alias_keys": [
            {"key": "ESHA:24374", "description": "Bread Crumbs, panko, Italian"},
        ],
        "any_phrases": ["bread crumbs", "breadcrumbs", "panko bread crumbs", "panko breadcrumbs"],
        "reject_phrases": ["breaded fish", "breaded shrimp", "fish sticks", "portions", "shrimp", "stuffed"],
        "min_grams": 100,
    },
    {
        "id": "semisweet_baking_bar",
        "key": "ESHA:41524",
        "description": "Baking Chocolate, semisweet, bar",
        "any_phrases": [
            "baker s semi sweet chocolate",
            "baking bar semi sweet chocolate",
            "semi sweet chocolate baking bar",
            "semi sweet chocolate premium baking bar",
        ],
        "reject_phrases": ["chips", "cookie", "morsels"],
        "min_grams": 50,
    },
    {
        "id": "unsweetened_baking_bar",
        "key": "ESHA:24169",
        "description": "Baking Chocolate, unsweetened, bar",
        "any_phrases": [
            "baker s unsweetened chocolate",
            "unsweetened baking chocolate",
            "unsweetened chocolate baking bar",
            "unsweetened chocolate premium baking bar",
        ],
        "reject_phrases": ["almond milk", "chips", "powder"],
        "min_grams": 50,
    },
    {
        "id": "bittersweet_baking_bar",
        "key": "ESHA:4356",
        "description": "Baking Chocolate, bar, bittersweet",
        "any_phrases": ["bittersweet chocolate baking bar"],
        "reject_phrases": ["chips", "sauce", "topping"],
        "min_grams": 50,
    },
    {
        "id": "white_chocolate_baking_bar",
        "key": "ESHA:90659",
        "description": "Baking Chocolate, bar, white chocolate",
        "any_phrases": ["white baking bar", "white chocolate baking bar"],
        "reject_phrases": ["chips", "morsels"],
        "min_grams": 50,
    },
    {
        "id": "unflavored_gelatin",
        "key": "ESHA:23429",
        "description": "Gelatin, unsweetened, dry",
        "any_phrases": ["gelatin sheets", "plain gelatin", "unflavored gelatin"],
        "reject_phrases": ["agar", "dessert", "eggnog", "flavored", "parfait", "strawberry", "substitute"],
        "min_grams": 5,
        "max_grams": 1000,
    },
    {
        "id": "wheat_hamburger_buns",
        "key": "FNDDS:51320070",
        "description": "Roll, wheat or cracked wheat, hamburger bun",
        "any_phrases": [
            "cracked wheat sandwich buns",
            "wheat hamburger buns",
            "wheat sandwich buns",
            "whole wheat buns",
            "whole wheat hamburger buns",
        ],
        "reject_phrases": ["hawaiian", "onion", "pretzel", "sourdough"],
        "min_grams": 200,
    },
    {
        "id": "crabmeat",
        "key": "SR28:171966",
        "description": "Crustaceans, crab, blue, canned",
        "any_phrases": ["crab meat", "crabmeat", "lump crab"],
        "reject_phrases": ["dip", "flounder", "imitation", "stuffing"],
        "min_grams": 100,
    },
    {
        "id": "cooked_ham",
        "key": "ESHA:91505",
        "description": "Pork, ham, honey, smoked, cooked",
        "any_phrases": ["cooked ham", "fully cooked ham", "smoked ham steak"],
        "reject_phrases": ["hock", "hocks", "lunch meat", "luncheon"],
        "min_grams": 200,
    },
    {
        "id": "prepared_horseradish",
        "key": "ESHA:27004",
        "description": "Spice, horseradish, prepared",
        "any_phrases": ["prepared horseradish", "white horseradish"],
        "reject_phrases": ["chips", "sauce mix"],
        "min_grams": 100,
    },
    {
        "id": "crescent_roll_dough",
        "key": "ESHA:16638",
        "description": "Roll, crescent, original, refrigerated dough",
        "any_phrases": ["crescent dinner rolls", "crescent roll dough", "crescent rolls"],
        "reject_phrases": ["filled", "sandwich"],
        "min_grams": 100,
    },
    {
        "id": "whole_almonds",
        "key": "ESHA:4504",
        "description": "Nuts, almonds, whole",
        "any_phrases": ["blanched almonds", "roasted almonds", "toasted almonds", "whole almonds"],
        "reject_phrases": ["chocolate", "coated", "flaked", "milk", "slivered", "sliced"],
        "min_grams": 50,
    },
    {
        "id": "mustard_seed",
        "key": "ESHA:26110",
        "description": "Spice, mustard seed, yellow, ground",
        "any_phrases": ["mustard seed", "mustard seeds"],
        "reject_phrases": ["french s", "prepared"],
        "min_grams": 10,
        "max_grams": 2000,
    },
    {
        "id": "refried_beans",
        "key": "ESHA:13478",
        "description": "Refried Beans",
        "any_phrases": ["refried beans"],
        "reject_phrases": ["dip"],
        "min_grams": 200,
    },
    {
        "id": "graham_cracker_crust",
        "key": "SR28:167520",
        "description": "Pie Crust, Cookie-type, Graham Cracker, Ready Crust",
        "any_phrases": ["graham cracker crust", "graham cracker pie crust"],
        "reject_phrases": ["bar", "bars", "cereal"],
        "min_grams": 100,
    },
    {
        "id": "liquid_smoke",
        "key": "ESHA:53417",
        "description": "Sauce, barbecue, mesquite smoke",
        "any_phrases": ["liquid smoke"],
        "min_grams": 50,
        "max_grams": 2000,
    },
    {
        "id": "yellow_cornmeal",
        "key": "ESHA:38004",
        "description": "Cornmeal, yellow, degerminated, enriched",
        "any_phrases": ["yellow cornmeal"],
        "reject_phrases": ["mix"],
        "min_grams": 200,
    },
    {
        "id": "bean_sprouts",
        "key": "SR28:169957",
        "description": "Mung beans, mature seeds, sprouted, raw",
        "any_phrases": ["bean sprouts"],
        "reject_phrases": ["bun", "seed"],
        "min_grams": 100,
    },
    {
        "id": "ground_chuck",
        "key": "ESHA:47441",
        "description": "Beef, chuck, ground, extra lean, raw",
        "any_phrases": ["ground chuck", "ground beef chuck"],
        "reject_phrases": ["corned", "deli", "roast", "steak"],
        "min_grams": 300,
    },
    {
        "id": "grape_jelly",
        "key": "ESHA:23215",
        "description": "Jelly, grape",
        "any_phrases": ["grape jam", "grape jelly"],
        "reject_phrases": ["tomato", "tomatoes"],
        "min_grams": 100,
    },
    {
        "id": "chicken_broth",
        "key": "SR28:174536",
        "description": "Soup, chicken broth, ready-to-serve",
        "any_phrases": ["chicken broth"],
        "reject_phrases": [
            "baby food",
            "base",
            "bouillon",
            "concentrate",
            "gravy",
            "powder",
            "ramen",
            "seasoning",
            "soup mix",
            "stage 1",
            "stage 2",
        ],
        "min_grams": 200,
    },
    {
        "id": "green_bell_pepper",
        "key": "ESHA:6846",
        "description": "Peppers, sweet, bell, green, fresh, medium, 2 1/2\"",
        "any_phrases": ["green bell pepper"],
        "reject_phrases": ["canned", "dried", "fajita", "frozen", "mexicorn", "seed", "seasoning", "stuffed"],
        "min_grams": 100,
    },
    {
        "id": "ground_cumin",
        "key": "ESHA:26503",
        "description": "Spice, cumin, seeds, ground",
        "any_phrases": ["ground cumin"],
        "reject_phrases": ["conditioner", "dal", "meal", "paneer", "ready", "sauce"],
        "min_grams": 10,
        "max_grams": 1000,
    },
    {
        "id": "fresh_mushrooms",
        "key": "ESHA:7351",
        "description": "Mushrooms, white, fresh",
        "any_phrases": ["baby bella mushroom", "portabella mushroom", "portobello mushroom", "white mushroom"],
        "reject_phrases": ["burger", "creamer", "dried", "gravy", "jerky", "pizza", "powder", "sauce", "soup", "stuffed"],
        "min_grams": 100,
    },
    {
        "id": "chili_powder",
        "key": "SR28:171319",
        "description": "Spices, chili powder",
        "any_phrases": ["chile powder", "chili powder"],
        "reject_phrases": ["meal", "sauce", "seasoning mix"],
        "min_grams": 10,
        "max_grams": 1000,
    },
    {
        "id": "cornstarch",
        "key": "ESHA:30000",
        "description": "Cornstarch",
        "any_phrases": ["corn starch", "cornstarch"],
        "reject_phrases": ["alternative", "arrowroot", "baby powder", "konjac", "replacement", "substitute"],
        "min_grams": 100,
    },
    {
        "id": "pecan_halves",
        "key": "ESHA:4578",
        "description": "Nuts, pecans, halves",
        "any_phrases": ["halves pecans", "pecan halves"],
        "reject_phrases": ["candied", "cereal", "chocolate", "coffee", "cookie", "granola", "honey", "pie", "pieces", "roasted", "salted", "snack"],
        "min_grams": 50,
    },
    {
        "id": "table_salt",
        "key": "SR28:173468",
        "description": "Salt, table",
        "any_phrases": ["iodized salt", "table salt"],
        "reject_phrases": ["bath", "caramel", "chips", "coffee", "epsom", "lamp", "seasoning", "scrub", "softener"],
        "min_grams": 100,
    },
    {
        "id": "sea_salt",
        "key": "ESHA:49296",
        "description": "Salt, sea, California",
        "any_phrases": ["sea salt"],
        "reject_phrases": ["almonds", "bath", "caramel", "chips", "chocolate", "coffee", "epsom", "nuts", "pistachios", "seasoning", "toffee"],
        "min_grams": 100,
    },
    {
        "id": "liquid_egg_whites",
        "key": "ESHA:21111",
        "description": "Egg, white, raw, large",
        "any_phrases": ["liquid egg white", "liquid egg whites"],
        "reject_phrases": ["case", "dried", "pasta", "powder", "protein", "supplement"],
        "min_grams": 250,
    },
    {
        "id": "fresh_thyme",
        "key": "ESHA:26623",
        "description": "Herb, thyme, fresh",
        "any_phrases": ["fresh thyme"],
        "reject_phrases": ["dried", "ground", "seasoning"],
        "min_grams": 5,
        "max_grams": 200,
    },
    {
        "id": "ground_cloves",
        "key": "ESHA:26019",
        "description": "Spice, clove, ground",
        "any_phrases": ["ground clove", "ground cloves"],
        "reject_phrases": ["oil", "supplement"],
        "min_grams": 5,
        "max_grams": 1000,
    },
    {
        "id": "sliced_almonds",
        "key": "ESHA:49260",
        "description": "Nuts, almonds, sliced, raw",
        "any_phrases": ["sliced almond", "sliced almonds"],
        "reject_phrases": ["cereal", "chocolate", "cookie", "honey", "roasted", "snack"],
        "min_grams": 50,
    },
    {
        "id": "lemon_zest",
        "key": "ESHA:31962",
        "description": "Lemon Zest",
        "any_phrases": ["lemon zest"],
        "reject_phrases": ["tea"],
        "min_grams": 5,
        "max_grams": 1000,
    },
    {
        "id": "raisins",
        "key": "ESHA:3766",
        "description": "Raisins, seedless",
        "any_phrases": ["raisin", "raisins"],
        "reject_phrases": [
            "bran",
            "cereal",
            "cheese",
            "chocolate",
            "cookie",
            "craisins",
            "cranberries",
            "golden",
            "mincemeat",
            "oatmeal",
            "peanuts",
            "trail mix",
            "yogurt",
        ],
        "min_grams": 50,
    },
    {
        "id": "semi_sweet_chocolate_chips",
        "key": "ESHA:23442",
        "description": "Baking Chips, chocolate, semi sweet",
        "any_phrases": ["semi sweet chocolate chips", "semi-sweet chocolate chips"],
        "reject_phrases": ["cookie", "granola"],
        "min_grams": 50,
    },
    {
        "id": "colby_jack_cheese",
        "key": "ESHA:36958",
        "description": "Cheese, colby jack",
        "all_phrases": ["cheese"],
        "any_phrases": ["co jack", "colby jack", "colby-jack"],
        "reject_phrases": ["cracker", "lunchable", "macaroni", "pretzel", "snack stick"],
        "min_grams": 100,
    },
    {
        "id": "black_beans",
        "key": "ESHA:13477",
        "description": "Beans, black",
        "any_phrases": ["black bean", "black beans"],
        "reject_phrases": ["burger", "chips", "dip", "hummus", "salsa", "soup"],
        "min_grams": 200,
    },
    {
        "id": "ground_mustard",
        "key": "ESHA:26514",
        "description": "Spice, mustard seed, ground",
        "any_phrases": ["ground mustard"],
        "reject_phrases": ["condiment", "dressing", "honey mustard", "pretzel", "sauce"],
        "min_grams": 10,
        "max_grams": 1000,
    },
    {
        "id": "half_and_half",
        "key": "SR28:171255",
        "description": "Cream, fluid, half and half",
        "any_phrases": ["half and half", "half half"],
        "reject_phrases": ["almond", "coffee mate", "coconut", "creamer", "dairy free", "hard iced tea", "oat", "plant", "ripple", "tea"],
        "min_grams": 200,
    },
    {
        "id": "extra_lean_ground_beef",
        "key": "ESHA:47445",
        "description": "Beef, ground, extra lean, raw",
        "all_phrases": ["ground beef"],
        "any_phrases": ["93 7", "93 lean", "93% lean", "96 4", "96 lean", "96% lean", "extra lean"],
        "reject_phrases": ["burger", "meatball", "patties", "patty"],
        "min_grams": 300,
    },
]

PACKAGE_EGG_REJECT_TOKENS = {
    "beater",
    "beaters",
    "buttermilk",
    "candy",
    "chocolate",
    "cream",
    "gelatin",
    "milk",
    "nog",
    "roll",
    "rolls",
    "sandwich",
    "substitute",
    "syrup",
    "vegan",
}

PACKAGE_BACON_FORM_REJECT_TOKENS = {
    "bbq",
    "cheddar",
    "flavor",
    "flavored",
    "grease",
    "powder",
    "salt",
    "seasoning",
}


@dataclass(frozen=True)
class LineResolution:
    input: str
    grams: float
    ingredient_key: str
    key_source: str
    canonical_name: str
    shopping_canonical: str
    esha_code: str
    esha_description: str
    sr28_code: str
    sr28_description: str
    fndds_code: str
    fndds_description: str
    nutrition_source: str
    nutrition_state: str
    nutrition: NutritionEstimate | None
    path: list[str]
    gate_reason: str


_CANONICAL_REFERENCE_INDEX: dict[str, dict[str, str]] | None = None
_CANONICAL_NAME_INDEX: dict[str, dict[str, str]] | None = None
_SR28_DESCRIPTION_INDEX: dict[str, tuple[str, str]] | None = None
_FNDDS_DESCRIPTION_INDEX: dict[str, tuple[str, str]] | None = None
_PRODUCT_TITLE_INDEX: dict[str, dict[str, Any]] | None = None

MANUAL_EXACT_FNDDS_KEYS = {
    "almondraw": ("42101000", "Almonds, unroasted", "concatenated_almond_raw"),
    "banana muffin mix": ("58610004", "banana muffin mix", "banana_muffin_mix_exact"),
    "banana nut muffin mix": ("58610005", "banana nut muffin mix", "banana_nut_muffin_mix_exact"),
    "char siu": ("27120030", "Ham or pork with barbecue sauce", "char_siu_pork_barbecue"),
    "chocolate sandwich cookie": ("53209015", "Cookie, chocolate sandwich", "chocolate_sandwich_cookie"),
    "chocolate sandwich cookies": ("53209015", "Cookie, chocolate sandwich", "chocolate_sandwich_cookie"),
    "chocolate sandwich cooky": ("53209015", "Cookie, chocolate sandwich", "chocolate_sandwich_cookie"),
    "cilantro stemfresh": ("75109550", "Cilantro, raw", "concatenated_cilantro_stem_fresh"),
    "cilantro stem fresh": ("75109550", "Cilantro, raw", "cilantro_stem_fresh"),
    "cognac": ("93501000", "Brandy", "cognac_to_brandy"),
    "cool whip": ("12220200", "Whipped topping", "cool_whip_whipped_topping"),
    "cool whip fat free": ("12220270", "Whipped topping, fat free", "cool_whip_fat_free"),
    "cool whip sugar free": ("12220280", "Whipped topping, sugar free", "cool_whip_sugar_free"),
    "drambuie": ("93201000", "Cordial or liqueur", "drambuie_liqueur_to_cordial"),
    "galliano": ("93201000", "Cordial or liqueur", "galliano_liqueur_to_cordial"),
    "grand marnier": ("93201000", "Cordial or liqueur", "grand_marnier_orange_liqueur_to_cordial"),
    "irish cream liqueur cream": ("93301450", "Liqueur with cream", "irish_cream_liqueur"),
    "limoncello": ("93201000", "Cordial or liqueur", "limoncello_liqueur_to_cordial"),
    "mexican crema": ("12310100", "Sour cream", "mexican_crema_to_sour_cream"),
    "nestle coffee mate original powdered coffee creamer": ("12210400", "Coffee creamer, powder", "powdered_coffee_creamer"),
    "red radishes small": ("75125000", "Radish, raw", "small_red_radishes"),
    "schnapps": ("93201000", "Cordial or liqueur", "schnapps_liqueur_to_cordial"),
    "strawberry pie filling": ("63203701", "Pie filling, NFS", "strawberry_pie_filling_v6_fndds"),
    "stout": ("93101000", "Beer", "stout_to_beer"),
    "turkey carcass": ("28340120", "Chicken or turkey broth, without tomato, home recipe", "turkey_carcass_stock_proxy"),
}

NON_PURCHASABLE_EXACT_KEYS = {
    "boiling water",
    "cold water",
    "crushed ice",
    "hot water",
    "ice",
    "ice cube",
    "ice cubes",
    "ice water",
    "lukewarm water",
    "salted hot water",
    "tap water",
    "warm hot water",
    "warm water",
    "water",
    "water bottled generic",
}

MANUAL_EXACT_ESHA_KEYS = {
    "banana muffin": ("25738", "Muffin, banana", "banana_muffin_exact"),
    "banana muffins": ("25738", "Muffin, banana", "banana_muffin_exact"),
    "banana nut muffin": ("18966", "Muffin, banana nut", "banana_nut_muffin_exact"),
    "banana nut muffins": ("18966", "Muffin, banana nut", "banana_nut_muffin_exact"),
    "bonito flake": ("17165", "Fish, tuna, dried", "bonito_flakes_to_dried_tuna"),
    "button mushroom": ("7351", "Mushrooms, white, fresh", "button_mushroom_to_white_mushroom"),
    "button mushrooms": ("7351", "Mushrooms, white, fresh", "button_mushroom_to_white_mushroom"),
    "butterscotch sauce": ("54285", "Topping, butterscotch, spoonable", "butterscotch_sauce"),
    "corn canned cooked with oil": ("38910", "Corn, sweet, yellow, canned, drained", "canned_corn_cooked_with_oil"),
    "cornflour": ("30000", "Cornstarch", "cornflour_to_cornstarch"),
    "creme de cacao": ("15612", "Syrup, creme de cacao", "creme_de_cacao_label_median"),
    "dry oregano": ("26009", "Herb, oregano, ground", "dry_oregano_to_oregano"),
    "dry rubbed sage": ("35048", "Herb, sage, leaf, dried", "rubbed_sage_to_dried_sage"),
    "dried rubbed sage": ("35048", "Herb, sage, leaf, dried", "rubbed_sage_to_dried_sage"),
    "espresso instant powder espresso": ("20013", "Coffee, regular, instant powder", "espresso_instant_powder"),
    "firm white bread white white": ("36160", "Bread, white, commercially prepared", "white_bread_duplicate_tokens"),
    "bottled fresh ginger": ("90442", "Spice, ginger root, fresh", "fresh_ginger_to_root"),
    "chopped fresh ginger": ("90442", "Spice, ginger root, fresh", "fresh_ginger_to_root"),
    "crushed fresh ginger": ("90442", "Spice, ginger root, fresh", "fresh_ginger_to_root"),
    "fresh ginger": ("90442", "Spice, ginger root, fresh", "fresh_ginger_to_root"),
    "fresh ginger paste": ("90442", "Spice, ginger root, fresh", "fresh_ginger_to_root"),
    "fresh ginger root": ("90442", "Spice, ginger root, fresh", "fresh_ginger_to_root"),
    "fresh gingerroot": ("90442", "Spice, ginger root, fresh", "fresh_ginger_to_root"),
    "fresh grated ginger": ("90442", "Spice, ginger root, fresh", "fresh_ginger_to_root"),
    "fresh ground ginger": ("90442", "Spice, ginger root, fresh", "fresh_ginger_to_root"),
    "freshly grated ginger": ("90442", "Spice, ginger root, fresh", "fresh_ginger_to_root"),
    "ginger paste": ("90442", "Spice, ginger root, fresh", "fresh_ginger_to_root"),
    "ginger root": ("90442", "Spice, ginger root, fresh", "fresh_ginger_to_root"),
    "gingerroot": ("90442", "Spice, ginger root, fresh", "fresh_ginger_to_root"),
    "grated fresh ginger": ("90442", "Spice, ginger root, fresh", "fresh_ginger_to_root"),
    "grated ginger": ("90442", "Spice, ginger root, fresh", "fresh_ginger_to_root"),
    "minced fresh ginger": ("90442", "Spice, ginger root, fresh", "fresh_ginger_to_root"),
    "minced ginger": ("90442", "Spice, ginger root, fresh", "fresh_ginger_to_root"),
    "minced peeled fresh ginger": ("90442", "Spice, ginger root, fresh", "fresh_ginger_to_root"),
    "raw fresh ginger": ("90442", "Spice, ginger root, fresh", "fresh_ginger_to_root"),
    "root ginger": ("90442", "Spice, ginger root, fresh", "fresh_ginger_to_root"),
    "grape tomato": ("90530", "Tomatoes, red, cherry, fresh, year round average", "grape_tomato_to_cherry_tomato"),
    "grape tomatoes": ("90530", "Tomatoes, red, cherry, fresh, year round average", "grape_tomato_to_cherry_tomato"),
    "dry ginger powder": ("4086", "Spice, ginger, ground", "ground_ginger_to_ground_spice"),
    "dried ginger": ("4086", "Spice, ginger, ground", "ground_ginger_to_ground_spice"),
    "dried ginger powder": ("4086", "Spice, ginger, ground", "ground_ginger_to_ground_spice"),
    "ginger powder": ("4086", "Spice, ginger, ground", "ground_ginger_to_ground_spice"),
    "ground dry ginger": ("4086", "Spice, ginger, ground", "ground_ginger_to_ground_spice"),
    "ground dried ginger": ("4086", "Spice, ginger, ground", "ground_ginger_to_ground_spice"),
    "ground ginger": ("4086", "Spice, ginger, ground", "ground_ginger_to_ground_spice"),
    "pickled ginger": ("33708", "Ginger, pickled", "pickled_ginger_exact"),
    "ginger syrup": ("31748", "Syrup, ginger, FS", "ginger_syrup_exact"),
    "instant chocolate pudding mix sugar free": ("2720", "Pudding, chocolate, fat & sugar free, instant, serving", "sugar_free_chocolate_pudding_mix"),
    "oil cured black olive black": ("52396", "Olives, moroccan, pitted, oil-cured", "oil_cured_black_olive"),
    "oil cured black olives": ("52396", "Olives, moroccan, pitted, oil-cured", "oil_cured_black_olive"),
    "red grape tomatoes": ("90530", "Tomatoes, red, cherry, fresh, year round average", "grape_tomato_to_cherry_tomato"),
    "red onions": ("7805", "Onion, red, fresh, medium, whole, 2 1/2\"", "red_onions_plural"),
    "rubbed sage": ("35048", "Herb, sage, leaf, dried", "rubbed_sage_to_dried_sage"),
    "small red onions": ("7805", "Onion, red, fresh, medium, whole, 2 1/2\"", "red_onions_plural"),
    "strawberry gelatin sugar free": ("18368", "Gelatin, sugar free, strawberry, dry mix, SD", "sugar_free_strawberry_gelatin"),
    "sultanas": ("3934", "Raisins, golden, seedless", "sultanas_to_golden_raisins"),
    "sweet red onions": ("7805", "Onion, red, fresh, medium, whole, 2 1/2\"", "red_onions_plural"),
    "yellow grape tomatoes": ("90530", "Tomatoes, red, cherry, fresh, year round average", "grape_tomato_to_cherry_tomato"),
}

MANUAL_EXACT_SR28_KEYS = {
    "chili garlic paste": ("174527", "Sauce, ready-to-serve, pepper or hot", "chili_garlic_hot_sauce_proxy"),
    "chocolate protein powder": ("173180", "Beverages, Protein powder whey based", "chocolate_protein_powder_to_whey"),
    "coriander powder": ("170922", "Spices, coriander seed", "ground_coriander_to_coriander_seed"),
    "bread crumbs": ("174928", "Bread, crumbs, dry, grated, plain", "breadcrumbs"),
    "breadcrumbs": ("174928", "Bread, crumbs, dry, grated, plain", "breadcrumbs"),
    "dry bread crumbs": ("174928", "Bread, crumbs, dry, grated, plain", "breadcrumbs"),
    "dry breadcrumbs": ("174928", "Bread, crumbs, dry, grated, plain", "breadcrumbs"),
    "dried breadcrumbs": ("174928", "Bread, crumbs, dry, grated, plain", "dried_breadcrumbs"),
    "edible flower": ("169270", "Pumpkin flowers, raw", "edible_flower_to_pumpkin_flower"),
    "fresh bread crumbs": ("174928", "Bread, crumbs, dry, grated, plain", "breadcrumbs"),
    "fresh breadcrumbs": ("174928", "Bread, crumbs, dry, grated, plain", "breadcrumbs"),
    "ground coriander": ("170922", "Spices, coriander seed", "ground_coriander_to_coriander_seed"),
    "plain bread crumbs": ("174928", "Bread, crumbs, dry, grated, plain", "breadcrumbs"),
    "plain breadcrumbs": ("174928", "Bread, crumbs, dry, grated, plain", "breadcrumbs"),
    "spaghetti": ("169736", "Pasta, dry, enriched", "spaghetti_to_dry_pasta"),
    "spaghetti noodles": ("169736", "Pasta, dry, enriched", "spaghetti_to_dry_pasta"),
    "spaghettini": ("169736", "Pasta, dry, enriched", "spaghetti_to_dry_pasta"),
    "split red lentil red": ("174284", "Lentils, pink or red, raw", "split_red_lentils"),
    "whole grain spaghetti": ("169736", "Pasta, dry, enriched", "spaghetti_to_dry_pasta"),
    "whole-grain spaghetti": ("169736", "Pasta, dry, enriched", "spaghetti_to_dry_pasta"),
}

PRODUCT_V6_SOURCE_SCORE = {
    "fixy_done_truth_agree": 5,
    "fixy_done_truth_fill": 4,
    "title_exact": 3,
    "title_category_bridge": 2,
}


def _tokens(text: str) -> set[str]:
    out: set[str] = set()
    for token in re.findall(r"[a-z0-9]+", (text or "").lower()):
        if token in WEAK_TOKENS:
            continue
        out.add(token)
        if token == "can":
            out.add("canned")
        if token == "soybean":
            out.add("soy")
        if token in {"peppercorn", "peppercorns"}:
            out.add("pepper")
        if token in {"crabmeat", "crabmeats"}:
            out.add("crab")
            out.add("meat")
        if token in {"waterchestnut", "waterchestnuts"}:
            out.add("water")
            out.add("chestnut")
        if len(token) > 4 and token.endswith("milk"):
            milk_prefix = token[:-4]
            if milk_prefix:
                out.add(milk_prefix)
            out.add("milk")
        if len(token) > 4 and token.endswith("ies"):
            out.add(token[:-3] + "y")
        elif len(token) > 3 and token.endswith("es"):
            out.add(token[:-2])
            out.add(token[:-1])
        elif len(token) > 3 and token.endswith("s"):
            out.add(token[:-1])
    return out


def _has_token(text: str, token: str) -> bool:
    return bool(re.search(rf"\b{re.escape(token)}s?\b", (text or "").lower()))


def _esha_identity_gate(canonical: str, esha_description: str) -> tuple[bool, str]:
    """Reject ESHA leaves that add a prepared form or subtype not present in the recipe line."""
    canon_key = normalize_key(canonical)
    desc_key = normalize_key(esha_description)
    if not desc_key:
        return False, "missing_esha_description"

    canon_tokens = _tokens(canon_key)
    desc_tokens = _tokens(desc_key)
    canon_identity_tokens = canon_tokens - WEAK_IDENTITY_OVERLAP_TOKENS
    desc_identity_tokens = desc_tokens - WEAK_IDENTITY_OVERLAP_TOKENS
    if canon_identity_tokens and desc_identity_tokens and not (canon_identity_tokens & desc_identity_tokens):
        return False, "no_identity_overlap"

    if "mayonnaise" in desc_tokens and not (canon_tokens & {"mayonnaise", "mayo"}):
        return False, "esha_adds_mayonnaise_identity"

    allowed_prepared = set()
    if "ham" in canon_tokens:
        allowed_prepared.update({"roasted"})
    extra_prepared = sorted(
        token
        for token in PREPARED_FORM_TOKENS
        if token in desc_tokens and token not in canon_tokens and token not in allowed_prepared
    )
    if extra_prepared:
        return False, "esha_adds_prepared_form:" + ",".join(extra_prepared[:4])

    for head, subtype_tokens in SUBTYPE_TOKENS_BY_HEAD.items():
        if head not in canon_tokens:
            continue
        extra_subtypes = sorted((desc_tokens & subtype_tokens) - canon_tokens)
        if extra_subtypes:
            return False, f"esha_adds_{head}_subtype:" + ",".join(extra_subtypes[:4])

    if _has_token(canon_key, "chicken") and _has_token(canon_key, "breast") and "lunchmeat" in desc_tokens:
        return False, "raw_chicken_breast_to_lunchmeat"

    for head, subtype_tokens in FORM_FAMILY_TOKENS.items():
        if head not in canon_tokens:
            continue
        canon_subtypes = canon_tokens & subtype_tokens
        desc_subtypes = desc_tokens & subtype_tokens
        if head == "bacon" and "vegetarian" in desc_subtypes:
            if canon_subtypes & {"imitation", "vegan", "veggie"}:
                canon_subtypes = (canon_subtypes - {"imitation", "vegan", "veggie"}) | {"vegetarian"}
            if "vegetarian" in canon_subtypes:
                desc_subtypes = desc_subtypes - {"strip", "strips"}
        if head == "bacon" and canon_subtypes & {"bit", "bits"} and desc_subtypes & {"bit", "bits"}:
            canon_subtypes = canon_subtypes | {"bit", "bits"}
            desc_subtypes = desc_subtypes - {"real"}
        extra_subtypes = sorted(desc_subtypes - canon_subtypes)
        if extra_subtypes:
            return False, f"esha_adds_{head}_subtype:" + ",".join(extra_subtypes)
        missing_subtypes = sorted(canon_subtypes - desc_subtypes)
        if missing_subtypes and head != "chicken":
            return False, f"esha_drops_{head}_subtype:" + ",".join(missing_subtypes)

    return True, "esha_identity_ok"


def _sr28_fallback_allowed(canonical: str, sr28_description: str, gate_reason: str) -> bool:
    sr_tokens = _tokens(sr28_description)
    canon_tokens = _tokens(canonical)
    if not sr_tokens or not canon_tokens or not (sr_tokens & canon_tokens):
        return False
    canon_key = normalize_key(canonical)
    if (
        (canon_tokens & {"roasted", "rotisserie"} or canon_key.startswith("roast "))
        and _has_token(sr28_description, "raw")
    ):
        return False
    if gate_reason.startswith("esha_drops_"):
        missing = set((gate_reason.split(":", 1)[1] if ":" in gate_reason else "").split(","))
        missing = {token for token in missing if token}
        if (
            gate_reason.startswith("esha_drops_bacon_subtype:")
            and missing & {"imitation", "vegan", "vegetarian", "veggie"}
            and "meatless" in sr_tokens
        ):
            return True
        return bool(missing and missing <= sr_tokens)
    if gate_reason.startswith("esha_adds_prepared_form:"):
        added = set((gate_reason.split(":", 1)[1] if ":" in gate_reason else "").split(","))
        added = {token for token in added if token}
        blocking = added & {"burger", "casserole", "dish", "lunchmeat", "meal", "pizza", "roll", "sandwich", "taco", "wrap"}
        return not bool(blocking & sr_tokens)
    if gate_reason in {"no_esha_code", "missing_esha_description", "no_identity_overlap"}:
        return True
    return False


def _classify_fndds_code(code: str) -> str:
    if len(code or "") < 2:
        return ""
    p2 = code[:2]
    if p2 in ("21", "23"):
        return "beef"
    if p2 == "22":
        return "pork"
    if p2 == "24":
        return "poultry"
    if p2 == "26":
        return "fish"
    if p2 in ("31", "32", "33", "34"):
        return "eggs"
    if p2 == "41":
        p3 = code[:3]
        p5 = code[:5]
        if p3 in ("411", "412", "413") or p5 in ("41416", "41421", "41440") or p3 in ("418", "419"):
            return "legumes"
    return ""


def _classify_protein_source(text: str, fndds_code: str) -> str:
    key = normalize_key(text)
    tokens = set(key.split())
    if "bacon" in tokens and tokens & {"imitation", "meatless", "vegan", "vegetarian", "veggie"}:
        return "legumes"
    if tokens & {"bacon", "ham", "pork"}:
        return "pork"
    if tokens & {"chicken", "turkey", "poultry"}:
        return "poultry"
    if tokens & {"beef", "veal", "lamb"}:
        return "beef"
    if tokens & {"fish", "salmon", "tuna", "cod", "shrimp", "crab", "scallop", "clam", "oyster"}:
        return "fish"
    if tokens & {"egg", "eggs", "yolk", "yolks"}:
        return "eggs"
    if tokens & {"bean", "beans", "lentil", "lentils", "chickpea", "chickpeas", "tofu", "soy"}:
        return "legumes"
    return _classify_fndds_code(fndds_code)


def _allergen_flags(text: str, fndds_code: str) -> list[str]:
    key = normalize_key(text)
    flags: set[str] = set()
    prefix = (fndds_code or "")[:2]
    if prefix in {"11", "12", "13", "14", "15"} or any(t in key for t in ("milk", "cream", "cheese", "butter")):
        flags.add("milk")
    if prefix == "31" or _has_token(key, "egg"):
        flags.add("eggs")
    if prefix in {"50", "51", "52", "53", "55"} or any(t in key for t in ("wheat", "flour", "bread", "pasta")):
        flags.add("wheat")
    if prefix == "26" or any(t in key for t in ("fish", "shrimp", "crab", "scallop", "clam", "oyster")):
        flags.add("fish_or_shellfish")
    if "peanut" in key:
        flags.add("peanuts")
    if any(t in key for t in ("almond", "cashew", "walnut", "pecan", "hazelnut", "pistachio")):
        flags.add("tree_nuts")
    if "soy" in key or fndds_code.startswith("413"):
        flags.add("soy")
    if "sesame" in key:
        flags.add("sesame")
    return sorted(flags)


def _parse_dict(raw: str) -> dict[str, float]:
    if not (raw or "").strip():
        return {}
    try:
        parsed = ast.literal_eval(raw)
    except (SyntaxError, ValueError):
        return {}
    if not isinstance(parsed, dict):
        return {}
    out: dict[str, float] = {}
    for key, value in parsed.items():
        try:
            grams = float(value)
        except (TypeError, ValueError):
            continue
        if grams > 0:
            out[str(key)] = grams
    return out


def _canonical_reference_score(row: dict[str, str], reference_key: str) -> tuple[int, int, int, int, int, int]:
    status = (row.get("review_status") or "").strip()
    if status == "approved":
        status_score = 5
    elif status == "approved_proxy":
        status_score = 4
    elif status == "proxy_auto_batched":
        status_score = 2
    elif status.startswith("provisional"):
        status_score = 1
    else:
        status_score = 0
    source_score = 1 if (row.get("source") or "").strip() == "hestia_ingredient_lookup" else 0
    has_sr28 = 1 if (row.get("sr28_fdc_id") or "").strip() else 0
    canonical_key = normalize_key(row.get("canonical_name") or "")
    phrase_match = 1 if canonical_key and canonical_key in reference_key else 0
    token_subset = 1 if canonical_key and set(canonical_key.split()) <= set(reference_key.split()) else 0
    # Prefer generic labels over SKU-like accidental descendants when multiple
    # canonical rows share the same USDA reference description.
    short_name = -len((row.get("canonical_name") or "").strip())
    return phrase_match, token_subset, status_score, source_score, has_sr28, short_name


def _canonical_reference_index() -> dict[str, dict[str, str]]:
    """Exact USDA/FNDDS description -> best reviewed canonical_items row."""
    global _CANONICAL_REFERENCE_INDEX
    if _CANONICAL_REFERENCE_INDEX is not None:
        return _CANONICAL_REFERENCE_INDEX
    out: dict[str, dict[str, str]] = {}
    if CANONICAL_ITEMS_CSV.exists():
        with CANONICAL_ITEMS_CSV.open(newline="", encoding="utf-8-sig", errors="replace") as handle:
            for row in csv.DictReader(handle):
                canonical = (row.get("canonical_name") or "").strip()
                if not canonical:
                    continue
                for column in ("sr28_description", "fndds_description"):
                    description = (row.get(column) or "").strip()
                    key = normalize_key(description)
                    if not key:
                        continue
                    current = out.get(key)
                    if current is None or _canonical_reference_score(row, key) > _canonical_reference_score(current, key):
                        out[key] = row
    _CANONICAL_REFERENCE_INDEX = out
    return out


def _canonical_name_index() -> dict[str, dict[str, str]]:
    """Exact approved canonical name -> canonical_items row."""
    global _CANONICAL_NAME_INDEX
    if _CANONICAL_NAME_INDEX is not None:
        return _CANONICAL_NAME_INDEX
    out: dict[str, dict[str, str]] = {}
    if CANONICAL_ITEMS_CSV.exists():
        with CANONICAL_ITEMS_CSV.open(newline="", encoding="utf-8-sig", errors="replace") as handle:
            for row in csv.DictReader(handle):
                if (row.get("review_status") or "").strip() != "approved":
                    continue
                canonical = (row.get("canonical_name") or "").strip()
                key = normalize_key(canonical)
                if key and ((row.get("sr28_fdc_id") or "").strip() or (row.get("fndds_code") or "").strip()):
                    out.setdefault(key, row)
    _CANONICAL_NAME_INDEX = out
    return out


def _sr28_description_index() -> dict[str, tuple[str, str]]:
    """Exact SR Legacy description -> (fdc_id, description)."""
    global _SR28_DESCRIPTION_INDEX
    if _SR28_DESCRIPTION_INDEX is not None:
        return _SR28_DESCRIPTION_INDEX
    out: dict[str, tuple[str, str]] = {}
    if SR28_FOOD_CSV.exists():
        with SR28_FOOD_CSV.open(newline="", encoding="utf-8-sig", errors="replace") as handle:
            for row in csv.DictReader(handle):
                if (row.get("data_type") or "").strip() != "sr_legacy_food":
                    continue
                fdc_id = (row.get("fdc_id") or "").strip()
                description = (row.get("description") or "").strip()
                key = normalize_key(description)
                if fdc_id and key:
                    out.setdefault(key, (fdc_id, description))
    _SR28_DESCRIPTION_INDEX = out
    return out


def _fndds_description_index() -> dict[str, tuple[str, str]]:
    """Exact FNDDS main-food description -> (food_code, description)."""
    global _FNDDS_DESCRIPTION_INDEX
    if _FNDDS_DESCRIPTION_INDEX is not None:
        return _FNDDS_DESCRIPTION_INDEX
    out: dict[str, tuple[str, str]] = {}
    if FNDDS_MAIN_FOOD_DESC_CSV.exists():
        with FNDDS_MAIN_FOOD_DESC_CSV.open(newline="", encoding="utf-8-sig", errors="replace") as handle:
            for row in csv.DictReader(handle):
                code = (row.get("Food code") or "").strip()
                description = (row.get("Main food description") or "").strip()
                key = normalize_key(description)
                if not code or not key:
                    continue
                out.setdefault(key, (code, description))
                # Common recipe exports pluralize a singular FNDDS head, e.g.
                # "WATER CHESTNUTS" for "Water chestnut".
                if not key.endswith("s"):
                    out.setdefault(key + "s", (code, description))
    _FNDDS_DESCRIPTION_INDEX = out
    return out


def _product_v6_source_score(source: str) -> int:
    parts = [part.strip() for part in (source or "").split("+") if part.strip()]
    if not parts:
        return 0
    return max(PRODUCT_V6_SOURCE_SCORE.get(part, 0) for part in parts)


def _product_title_index() -> dict[str, dict[str, Any]]:
    """Exact normalized branded title -> consensus v6 FNDDS mapping.

    The v6 retail map contains reviewed fixes and title-derived FNDDS targets.
    This index is intentionally conservative: it only uses exact product-title
    matches and keeps a title only when a high-confidence row or clear
    same-title consensus points at one FNDDS code.
    """
    global _PRODUCT_TITLE_INDEX
    if _PRODUCT_TITLE_INDEX is not None:
        return _PRODUCT_TITLE_INDEX

    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    if PRODUCT_FIXY_V6_CSV.exists():
        with PRODUCT_FIXY_V6_CSV.open(newline="", encoding="utf-8-sig", errors="replace") as handle:
            for row in csv.DictReader(handle):
                title = (row.get("product_description") or "").strip()
                title_key = normalize_key(title)
                fndds_code = (row.get("v6_fndds_code") or row.get("fndds_main_code") or "").strip()
                fndds_description = (row.get("v6_fndds_description") or row.get("fndds_main_description") or "").strip()
                source = (row.get("v6_source") or row.get("fndds_main_match_type") or "").strip()
                source_score = _product_v6_source_score(source)
                if not title_key or not fndds_code or not fndds_description or source_score <= 0:
                    continue
                groups[title_key].append(
                    {
                        "product_description": title,
                        "fndds_code": fndds_code,
                        "fndds_description": fndds_description,
                        "v6_source": source,
                        "source_score": source_score,
                    }
                )

    out: dict[str, dict[str, Any]] = {}
    for title_key, candidates in groups.items():
        high_confidence = [candidate for candidate in candidates if candidate["source_score"] >= 4]
        medium_confidence = [candidate for candidate in candidates if candidate["source_score"] >= 3]
        if high_confidence:
            pool = high_confidence
            min_share = 0.67
        elif medium_confidence:
            pool = medium_confidence
            min_share = 0.67
        else:
            pool = candidates
            min_share = 0.90

        target_counts: dict[tuple[str, str], dict[str, Any]] = {}
        for candidate in pool:
            target = (candidate["fndds_code"], candidate["fndds_description"])
            item = target_counts.setdefault(
                target,
                {
                    "fndds_code": candidate["fndds_code"],
                    "fndds_description": candidate["fndds_description"],
                    "product_description": candidate["product_description"],
                    "v6_sources": Counter(),
                    "support_count": 0,
                    "source_score": 0,
                },
            )
            item["support_count"] += 1
            item["source_score"] = max(item["source_score"], candidate["source_score"])
            item["v6_sources"][candidate["v6_source"]] += 1

        if not target_counts:
            continue
        best = max(
            target_counts.values(),
            key=lambda item: (item["support_count"], item["source_score"], item["fndds_code"]),
        )
        share = best["support_count"] / max(1, len(pool))
        if best["source_score"] < 3 and best["support_count"] < 3:
            continue
        if share < min_share:
            continue
        out[title_key] = {
            "product_description": best["product_description"],
            "fndds_code": best["fndds_code"],
            "fndds_description": best["fndds_description"],
            "support_count": best["support_count"],
            "candidate_count": len(pool),
            "support_share": share,
            "v6_sources": dict(best["v6_sources"]),
        }

    _PRODUCT_TITLE_INDEX = out
    return out


def _non_purchasable_exact_resolution(label: str, grams: float, *, path: list[str]) -> LineResolution | None:
    key = normalize_key(label)
    if key not in NON_PURCHASABLE_EXACT_KEYS:
        return None
    canonical = (label or "").strip() or key
    return LineResolution(
        input=label,
        grams=grams,
        ingredient_key="",
        key_source="excluded_non_purchasable",
        canonical_name=canonical,
        shopping_canonical=canonical,
        esha_code="",
        esha_description="",
        sr28_code="",
        sr28_description="",
        fndds_code="",
        fndds_description="",
        nutrition_source="excluded_zero_nutrition",
        nutrition_state="excluded",
        nutrition=None,
        path=path + [f"excluded_non_purchasable_exact:{key}:water_is_not_a_planner_purchase"],
        gate_reason="excluded_non_purchasable:water",
    )


def _manual_exact_resolution(label: str, grams: float, *, path: list[str]) -> LineResolution | None:
    key = normalize_key(label)
    if not key:
        return None

    manual_fndds = MANUAL_EXACT_FNDDS_KEYS.get(key)
    if manual_fndds:
        fndds_code, fndds_description, reason = manual_fndds
        row = {
            "canonical_normalized": fndds_description,
            "canonical_shopping_item": label,
            "fndds_code": fndds_code,
            "fndds_description": fndds_description,
            "nutrition_match_state": "fndds_match",
            "nutrition_code_type": "fndds_reference_match",
            "esha_code": "",
            "esha_description": "",
        }
        nutrition, nutrition_source, nutrition_state = _nutrition_from_row(row, grams)
        if nutrition is None:
            return None
        return LineResolution(
            input=label,
            grams=grams,
            ingredient_key=f"FNDDS:{fndds_code}",
            key_source="manual_exact_fndds",
            canonical_name=fndds_description,
            shopping_canonical=label,
            esha_code="",
            esha_description="",
            sr28_code="",
            sr28_description="",
            fndds_code=fndds_code,
            fndds_description=fndds_description,
            nutrition_source=nutrition_source,
            nutrition_state=nutrition_state.value,
            nutrition=nutrition,
            path=path + [f"manual_exact_fndds:{key}:{fndds_code}:{reason}"],
            gate_reason=f"manual_exact_fndds:{reason}",
        )

    manual_sr28 = MANUAL_EXACT_SR28_KEYS.get(key)
    if manual_sr28:
        sr28_code, sr28_description, reason = manual_sr28
        row = {
            "canonical_normalized": sr28_description,
            "canonical_shopping_item": label,
            "sr28_code": sr28_code,
            "sr28_description": sr28_description,
            "nutrition_match_state": "sr28_match",
            "nutrition_code_type": "sr28_reference_match",
            "esha_code": "",
            "esha_description": "",
        }
        nutrition, nutrition_source, nutrition_state = _nutrition_from_row(row, grams)
        if nutrition is None:
            return None
        return LineResolution(
            input=label,
            grams=grams,
            ingredient_key=f"SR28:{sr28_code}",
            key_source="manual_exact_sr28",
            canonical_name=sr28_description,
            shopping_canonical=label,
            esha_code="",
            esha_description="",
            sr28_code=sr28_code,
            sr28_description=sr28_description,
            fndds_code="",
            fndds_description="",
            nutrition_source=nutrition_source,
            nutrition_state=nutrition_state.value,
            nutrition=nutrition,
            path=path + [f"manual_exact_sr28:{key}:{sr28_code}:{reason}"],
            gate_reason=f"manual_exact_sr28:{reason}",
        )

    manual_esha = MANUAL_EXACT_ESHA_KEYS.get(key)
    if manual_esha:
        esha_code, esha_description, reason = manual_esha
        row = {
            "canonical_normalized": esha_description,
            "canonical_shopping_item": label,
            "esha_code": esha_code,
            "esha_description": esha_description,
            "nutrition_match_state": "esha_match",
            "nutrition_code_type": "esha_label_median",
        }
        nutrition, nutrition_source, nutrition_state = _nutrition_from_row(row, grams)
        if nutrition is None:
            return None
        return LineResolution(
            input=label,
            grams=grams,
            ingredient_key=f"ESHA:{esha_code}",
            key_source="manual_exact_esha",
            canonical_name=esha_description,
            shopping_canonical=label,
            esha_code=esha_code,
            esha_description=esha_description,
            sr28_code="",
            sr28_description="",
            fndds_code="",
            fndds_description="",
            nutrition_source=nutrition_source,
            nutrition_state=nutrition_state.value,
            nutrition=nutrition,
            path=path + [f"manual_exact_esha:{key}:{esha_code}:{reason}"],
            gate_reason=f"manual_exact_esha:{reason}",
        )

    return None


def _product_title_resolution(label: str, grams: float, *, path: list[str]) -> LineResolution | None:
    key = normalize_key(label)
    mapping = _product_title_index().get(key)
    if not mapping:
        return None
    fndds_code = mapping["fndds_code"]
    fndds_description = mapping["fndds_description"]
    row = {
        "canonical_normalized": fndds_description,
        "canonical_shopping_item": mapping["product_description"],
        "fndds_code": fndds_code,
        "fndds_description": fndds_description,
        "nutrition_match_state": "fndds_match",
        "nutrition_code_type": "fndds_reference_match",
        "esha_code": "",
        "esha_description": "",
    }
    nutrition, nutrition_source, nutrition_state = _nutrition_from_row(row, grams)
    if nutrition is None:
        return None
    source_summary = ",".join(sorted(mapping["v6_sources"].keys()))
    return LineResolution(
        input=label,
        grams=grams,
        ingredient_key=f"FNDDS:{fndds_code}",
        key_source="product_title_fndds_exact",
        canonical_name=fndds_description,
        shopping_canonical=mapping["product_description"],
        esha_code="",
        esha_description="",
        sr28_code="",
        sr28_description="",
        fndds_code=fndds_code,
        fndds_description=fndds_description,
        nutrition_source=nutrition_source,
        nutrition_state=nutrition_state.value,
        nutrition=nutrition,
        path=path
        + [
            "product_title_fndds_exact:"
            f"{label!r}->{fndds_code}:{fndds_description!r}:"
            f"support={mapping['support_count']}/{mapping['candidate_count']}:"
            f"sources={source_summary}"
        ],
        gate_reason="product_title_fndds_exact",
    )


def _direct_reference_resolution(
    label: str,
    grams: float,
    *,
    allow_sr28_fallback: bool,
    allow_fndds_fallback: bool,
    path: list[str],
) -> LineResolution | None:
    """Resolve exact USDA reference descriptions when the surface layer cannot.

    Full recipe exports sometimes contain raw SR28/FNDDS descriptions rather
    than Hestia surface names. Those strings are already authoritative
    nutrition identities, so falling back to their exact reference row is safer
    than adding broad aliases or weakening ESHA identity gates.
    """
    key = normalize_key(label)
    if not key:
        return None

    manual = _manual_exact_resolution(label, grams, path=path)
    if manual is not None:
        return manual

    canonical_row = _canonical_reference_index().get(key)
    if canonical_row:
        canonical = (canonical_row.get("canonical_name") or label).strip()
        shopping = (canonical_row.get("shopping_label") or canonical).strip()
        sr28_code = (canonical_row.get("sr28_fdc_id") or "").strip()
        sr28_description = (canonical_row.get("sr28_description") or "").strip()
        fndds_code = (canonical_row.get("fndds_code") or "").strip()
        fndds_description = (canonical_row.get("fndds_description") or "").strip()
        row = {
            "canonical_normalized": canonical,
            "canonical_shopping_item": shopping,
            "sr28_code": sr28_code,
            "sr28_description": sr28_description,
            "fndds_code": fndds_code,
            "fndds_description": fndds_description,
            "nutrition_match_state": "sr28_match" if sr28_code else "fndds_match" if fndds_code else "",
            "nutrition_code_type": "sr28_reference_match" if sr28_code else "fndds_reference_match" if fndds_code else "",
            "esha_code": "",
            "esha_description": "",
        }
        if allow_sr28_fallback and sr28_code:
            nutrition, nutrition_source, nutrition_state = _nutrition_from_row(row, grams)
            return LineResolution(
                input=label,
                grams=grams,
                ingredient_key=f"SR28:{sr28_code}",
                key_source="sr28_reference_exact",
                canonical_name=canonical,
                shopping_canonical=shopping,
                esha_code="",
                esha_description="",
                sr28_code=sr28_code,
                sr28_description=sr28_description,
                fndds_code=fndds_code,
                fndds_description=fndds_description,
                nutrition_source=nutrition_source,
                nutrition_state=nutrition_state.value,
                nutrition=nutrition,
                path=path + [f"canonical_reference_sr28_exact:{label!r}->{canonical!r}:{sr28_code}"],
                gate_reason="sr28_reference_exact",
            )
        if allow_fndds_fallback and fndds_code:
            nutrition, nutrition_source, nutrition_state = _nutrition_from_row(row, grams)
            return LineResolution(
                input=label,
                grams=grams,
                ingredient_key=f"FNDDS:{fndds_code}",
                key_source="fndds_reference_exact",
                canonical_name=canonical,
                shopping_canonical=shopping,
                esha_code="",
                esha_description="",
                sr28_code=sr28_code,
                sr28_description=sr28_description,
                fndds_code=fndds_code,
                fndds_description=fndds_description,
                nutrition_source=nutrition_source,
                nutrition_state=nutrition_state.value,
                nutrition=nutrition,
                path=path + [f"canonical_reference_fndds_exact:{label!r}->{canonical!r}:{fndds_code}"],
                gate_reason="fndds_reference_exact",
            )

    if allow_sr28_fallback:
        sr28 = _sr28_description_index().get(key)
        if sr28:
            sr28_code, sr28_description = sr28
            row = {
                "canonical_normalized": sr28_description,
                "canonical_shopping_item": sr28_description,
                "sr28_code": sr28_code,
                "sr28_description": sr28_description,
                "nutrition_match_state": "sr28_match",
                "nutrition_code_type": "sr28_reference_match",
                "esha_code": "",
                "esha_description": "",
            }
            nutrition, nutrition_source, nutrition_state = _nutrition_from_row(row, grams)
            return LineResolution(
                input=label,
                grams=grams,
                ingredient_key=f"SR28:{sr28_code}",
                key_source="sr28_description_exact",
                canonical_name=sr28_description,
                shopping_canonical=sr28_description,
                esha_code="",
                esha_description="",
                sr28_code=sr28_code,
                sr28_description=sr28_description,
                fndds_code="",
                fndds_description="",
                nutrition_source=nutrition_source,
                nutrition_state=nutrition_state.value,
                nutrition=nutrition,
                path=path + [f"sr28_description_exact:{label!r}:{sr28_code}"],
                gate_reason="sr28_description_exact",
            )

    canonical_name_row = _canonical_name_index().get(key)
    if canonical_name_row:
        canonical = (canonical_name_row.get("canonical_name") or label).strip()
        shopping = (canonical_name_row.get("shopping_label") or canonical).strip()
        sr28_code = (canonical_name_row.get("sr28_fdc_id") or "").strip()
        sr28_description = (canonical_name_row.get("sr28_description") or "").strip()
        fndds_code = (canonical_name_row.get("fndds_code") or "").strip()
        fndds_description = (canonical_name_row.get("fndds_description") or "").strip()
        row = {
            "canonical_normalized": canonical,
            "canonical_shopping_item": shopping,
            "sr28_code": sr28_code,
            "sr28_description": sr28_description,
            "fndds_code": fndds_code,
            "fndds_description": fndds_description,
            "nutrition_match_state": "sr28_match" if sr28_code else "fndds_match" if fndds_code else "",
            "nutrition_code_type": "sr28_reference_match" if sr28_code else "fndds_reference_match" if fndds_code else "",
            "esha_code": "",
            "esha_description": "",
        }
        if allow_sr28_fallback and sr28_code:
            nutrition, nutrition_source, nutrition_state = _nutrition_from_row(row, grams)
            return LineResolution(
                input=label,
                grams=grams,
                ingredient_key=f"SR28:{sr28_code}",
                key_source="canonical_name_sr28_exact",
                canonical_name=canonical,
                shopping_canonical=shopping,
                esha_code="",
                esha_description="",
                sr28_code=sr28_code,
                sr28_description=sr28_description,
                fndds_code=fndds_code,
                fndds_description=fndds_description,
                nutrition_source=nutrition_source,
                nutrition_state=nutrition_state.value,
                nutrition=nutrition,
                path=path + [f"canonical_name_sr28_exact:{label!r}->{canonical!r}:{sr28_code}"],
                gate_reason="canonical_name_sr28_exact",
            )
        if (allow_sr28_fallback or allow_fndds_fallback) and fndds_code:
            nutrition, nutrition_source, nutrition_state = _nutrition_from_row(row, grams)
            return LineResolution(
                input=label,
                grams=grams,
                ingredient_key=f"FNDDS:{fndds_code}",
                key_source="canonical_name_fndds_exact",
                canonical_name=canonical,
                shopping_canonical=shopping,
                esha_code="",
                esha_description="",
                sr28_code=sr28_code,
                sr28_description=sr28_description,
                fndds_code=fndds_code,
                fndds_description=fndds_description,
                nutrition_source=nutrition_source,
                nutrition_state=nutrition_state.value,
                nutrition=nutrition,
                path=path + [f"canonical_name_fndds_exact:{label!r}->{canonical!r}:{fndds_code}"],
                gate_reason="canonical_name_fndds_exact",
            )

    if allow_sr28_fallback or allow_fndds_fallback:
        fndds = _fndds_description_index().get(key)
        if fndds:
            fndds_code, fndds_description = fndds
            row = {
                "canonical_normalized": fndds_description,
                "canonical_shopping_item": fndds_description,
                "fndds_code": fndds_code,
                "fndds_description": fndds_description,
                "nutrition_match_state": "fndds_match",
                "nutrition_code_type": "fndds_reference_match",
                "esha_code": "",
                "esha_description": "",
            }
            nutrition, nutrition_source, nutrition_state = _nutrition_from_row(row, grams)
            return LineResolution(
                input=label,
                grams=grams,
                ingredient_key=f"FNDDS:{fndds_code}",
                key_source="fndds_description_exact",
                canonical_name=fndds_description,
                shopping_canonical=fndds_description,
                esha_code="",
                esha_description="",
                sr28_code="",
                sr28_description="",
                fndds_code=fndds_code,
                fndds_description=fndds_description,
                nutrition_source=nutrition_source,
                nutrition_state=nutrition_state.value,
                nutrition=nutrition,
                path=path + [f"fndds_description_exact:{label!r}:{fndds_code}"],
                gate_reason="fndds_description_exact",
            )

    product_title = _product_title_resolution(label, grams, path=path)
    if product_title is not None:
        return product_title

    return None


def _resolve_item(
    label: str,
    grams: float,
    *,
    allow_sr28_fallback: bool,
    allow_fndds_fallback: bool,
) -> LineResolution:
    non_purchasable = _non_purchasable_exact_resolution(label, grams, path=["non_purchasable_exact_pre_surface"])
    if non_purchasable is not None:
        return non_purchasable

    manual = _manual_exact_resolution(label, grams, path=["manual_exact_pre_surface"])
    if manual is not None:
        return manual

    row, path = _resolve_surface(label, label)
    if not row:
        direct = _direct_reference_resolution(
            label,
            grams,
            allow_sr28_fallback=allow_sr28_fallback,
            allow_fndds_fallback=allow_fndds_fallback,
            path=path,
        )
        if direct is not None:
            return direct
        return LineResolution(
            input=label,
            grams=grams,
            ingredient_key="",
            key_source="unresolved",
            canonical_name="",
            shopping_canonical="",
            esha_code="",
            esha_description="",
            sr28_code="",
            sr28_description="",
            fndds_code="",
            fndds_description="",
            nutrition_source="nutrition_unknown",
            nutrition_state="nutrition_unknown",
            nutrition=None,
            path=path,
            gate_reason="no_surface",
        )

    if (row.get("record_type") or "").strip() == "non_ingredient":
        return LineResolution(
            input=label,
            grams=grams,
            ingredient_key="",
            key_source="non_food",
            canonical_name="",
            shopping_canonical="",
            esha_code="",
            esha_description="",
            sr28_code="",
            sr28_description="",
            fndds_code="",
            fndds_description="",
            nutrition_source="non_ingredient_surface",
            nutrition_state="non_food",
            nutrition=None,
            path=path,
            gate_reason="non_ingredient",
        )

    row = _apply_surface_esha_override(row, label, label, path)
    if any("surface_nutrition_clear:" in item and "water_is_not_a_planner_purchase" in item for item in path):
        canonical = (row.get("canonical_normalized") or row.get("canonical_surface") or label).strip()
        shopping = (row.get("canonical_shopping_item") or canonical).strip()
        return LineResolution(
            input=label,
            grams=grams,
            ingredient_key="",
            key_source="excluded_non_purchasable",
            canonical_name=canonical,
            shopping_canonical=shopping,
            esha_code="",
            esha_description="",
            sr28_code="",
            sr28_description="",
            fndds_code="",
            fndds_description="",
            nutrition_source="excluded_zero_nutrition",
            nutrition_state="excluded",
            nutrition=None,
            path=path,
            gate_reason="excluded_non_purchasable:water",
        )
    canonical = (row.get("canonical_normalized") or row.get("canonical_surface") or label).strip()
    shopping = (row.get("canonical_shopping_item") or canonical).strip()
    esha_code = (row.get("esha_code") or "").strip()
    esha_description = (row.get("esha_description") or "").strip()
    sr28_code = (row.get("sr28_code") or "").strip()
    fndds_code = (row.get("fndds_code") or "").strip()

    ingredient_key = ""
    key_source = "unresolved"
    gate_reason = "no_esha_code"
    if esha_code:
        ok, gate_reason = _esha_identity_gate(canonical, esha_description)
        if ok:
            ingredient_key = f"ESHA:{esha_code}"
            key_source = "esha"
    if (
        not ingredient_key
        and allow_sr28_fallback
        and sr28_code
        and _sr28_fallback_allowed(canonical, row.get("sr28_description") or "", gate_reason)
    ):
        ingredient_key = f"SR28:{sr28_code}"
        key_source = "sr28_fallback"
        if not gate_reason:
            gate_reason = "sr28_fallback"
    if not ingredient_key and allow_fndds_fallback and fndds_code:
        ingredient_key = f"FNDDS:{fndds_code}"
        key_source = "fndds_fallback"
        if not gate_reason:
            gate_reason = "fndds_fallback"

    if not ingredient_key and not any(item.startswith("surface_nutrition_clear:") for item in path):
        direct = _direct_reference_resolution(
            label,
            grams,
            allow_sr28_fallback=allow_sr28_fallback,
            allow_fndds_fallback=allow_fndds_fallback,
            path=path + [f"surface_route_unresolved:{gate_reason}"],
        )
        if direct is not None:
            return direct

    nutrition, nutrition_source, nutrition_state = _nutrition_from_row(row, grams)
    return LineResolution(
        input=label,
        grams=grams,
        ingredient_key=ingredient_key,
        key_source=key_source,
        canonical_name=canonical,
        shopping_canonical=shopping,
        esha_code=esha_code,
        esha_description=esha_description,
        sr28_code=sr28_code,
        sr28_description=(row.get("sr28_description") or "").strip(),
        fndds_code=fndds_code,
        fndds_description=(row.get("fndds_description") or "").strip(),
        nutrition_source=nutrition_source,
        nutrition_state=nutrition_state.value,
        nutrition=nutrition,
        path=path,
        gate_reason=gate_reason,
    )


def _resolution_json(line: LineResolution) -> dict[str, Any]:
    nutrition = None
    if line.nutrition is not None:
        nutrition = {
            "kcal": round(line.nutrition.kcal, 4),
            "protein_g": round(line.nutrition.protein_g, 4),
            "fat_g": round(line.nutrition.fat_g, 4),
            "carbs_g": round(line.nutrition.carbs_g, 4),
        }
    return {
        "input": line.input,
        "grams": round(line.grams, 4),
        "ingredient_key": line.ingredient_key,
        "key_source": line.key_source,
        "canonical_name": line.canonical_name,
        "shopping_canonical": line.shopping_canonical,
        "esha_code": line.esha_code,
        "esha_description": line.esha_description,
        "sr28_code": line.sr28_code,
        "sr28_description": line.sr28_description,
        "fndds_code": line.fndds_code,
        "fndds_description": line.fndds_description,
        "nutrition_source": line.nutrition_source,
        "nutrition_state": line.nutrition_state,
        "nutrition": nutrition,
        "gate_reason": line.gate_reason,
        "path": line.path,
    }


def _with_grams(template: LineResolution, grams: float) -> LineResolution:
    nutrition = None
    if template.nutrition is not None:
        scale = grams / 100.0
        nutrition = NutritionEstimate(
            kcal=template.nutrition.kcal * scale,
            protein_g=template.nutrition.protein_g * scale,
            fat_g=template.nutrition.fat_g * scale,
            carbs_g=template.nutrition.carbs_g * scale,
        )
    return replace(template, grams=grams, nutrition=nutrition)


def _add_meta(meta: dict[str, dict[str, Any]], line: LineResolution) -> None:
    if not line.ingredient_key:
        return
    item = meta.setdefault(
        line.ingredient_key,
        {
            "ingredient_key": line.ingredient_key,
            "key_source": line.key_source,
            "canonical_names": Counter(),
            "shopping_canonicals": Counter(),
            "esha_code": line.esha_code,
            "esha_description": line.esha_description,
            "sr28_code": line.sr28_code,
            "sr28_description": line.sr28_description,
            "fndds_proxy": line.fndds_code,
            "fndds_description": line.fndds_description,
            "protein_source": "",
            "allergens": set(),
        },
    )
    item["canonical_names"][line.canonical_name] += 1
    item["shopping_canonicals"][line.shopping_canonical] += 1
    if not item.get("protein_source"):
        proxy = line.fndds_code
        if line.esha_code:
            esha = nutrition_for_esha(line.esha_code) or {}
            proxy = esha.get("fndds_proxy") or proxy
        item["protein_source"] = _classify_protein_source(
            " ".join([line.canonical_name, line.esha_description, line.sr28_description]),
            proxy,
        )
    item["allergens"].update(_allergen_flags(" ".join([line.canonical_name, line.esha_description, line.sr28_description]), line.fndds_code))


def _finalize_meta(meta: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for key, item in sorted(meta.items()):
        out[key] = {
            "ingredient_key": key,
            "key_source": item.get("key_source", ""),
            "canonical_names": [name for name, _count in item["canonical_names"].most_common(8) if name],
            "shopping_canonicals": [name for name, _count in item["shopping_canonicals"].most_common(8) if name],
            "esha_code": item.get("esha_code", ""),
            "esha_description": item.get("esha_description", ""),
            "sr28_code": item.get("sr28_code", ""),
            "sr28_description": item.get("sr28_description", ""),
            "fndds_proxy": item.get("fndds_proxy", ""),
            "fndds_description": item.get("fndds_description", ""),
            "protein_source": item.get("protein_source", ""),
            "allergens": sorted(item.get("allergens", set())),
        }
    return out


def build_recipes(
    *,
    recipes_csv: Path,
    out_csv: Path,
    out_summary: Path,
    out_ingredient_meta: Path,
    limit_recipes: int = 0,
    recipe_ids: set[str] | None = None,
    allow_sr28_fallback: bool = True,
    allow_fndds_fallback: bool = False,
    include_line_json: bool = False,
) -> dict[str, Any]:
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    recipe_ids = recipe_ids or set()

    resolution_cache: dict[str, LineResolution] = {}
    meta: dict[str, dict[str, Any]] = {}
    stats: Counter[str] = Counter()
    gate_reasons: Counter[str] = Counter()
    unresolved_inputs: Counter[str] = Counter()
    key_sources: Counter[str] = Counter()
    nutrition_sources: Counter[str] = Counter()
    selected_ids: list[str] = []

    tmp = out_csv.with_suffix(out_csv.suffix + ".tmp")
    with recipes_csv.open(newline="", encoding="utf-8-sig", errors="replace") as in_handle, tmp.open(
        "w", newline="", encoding="utf-8"
    ) as out_handle:
        reader = csv.DictReader(in_handle)
        base_fields = list(reader.fieldnames or [])
        extra_fields = [
            "calculator_native_grams_dict",
            "esha_grams_dict",
            "sr28_grams_dict",
            "calculator_line_resolutions_json",
            "calculator_unresolved_lines_json",
            "calculator_identity_version",
            "calculator_resolved_line_count",
            "calculator_unresolved_line_count",
            "calculator_resolved_grams_pct",
        ]
        writer = csv.DictWriter(out_handle, fieldnames=base_fields + [f for f in extra_fields if f not in base_fields])
        writer.writeheader()

        for row in reader:
            rid = str(row.get("recipeNum") or "").strip()
            if recipe_ids and rid not in recipe_ids:
                continue
            if limit_recipes and stats["recipes_written"] >= limit_recipes:
                break

            stats["recipes_seen"] += 1
            shopping_items = _parse_dict(row.get("shopping_items_dict") or "")
            if not shopping_items:
                stats["recipes_without_shopping_items"] += 1
                continue

            native_grams: dict[str, float] = defaultdict(float)
            esha_grams: dict[str, float] = defaultdict(float)
            sr28_grams: dict[str, float] = defaultdict(float)
            line_records: list[dict[str, Any]] = []
            unresolved_records: list[dict[str, Any]] = []
            nutrition_totals = {"kcal": 0.0, "protein_g": 0.0, "fat_g": 0.0, "carbs_g": 0.0}
            resolved_grams = 0.0
            total_grams = sum(shopping_items.values())
            nutrition_grams = 0.0

            for label, grams in shopping_items.items():
                cache_key = normalize_key(label)
                cached = resolution_cache.get(cache_key)
                if cached is None:
                    cached = _resolve_item(
                        label,
                        100.0,
                        allow_sr28_fallback=allow_sr28_fallback,
                        allow_fndds_fallback=allow_fndds_fallback,
                    )
                    resolution_cache[cache_key] = cached
                line = _with_grams(cached, grams)
                stats["lines"] += 1
                gate_reasons[line.gate_reason] += 1
                key_sources[line.key_source] += 1
                nutrition_sources[line.nutrition_source] += 1
                record = _resolution_json(line)
                line_records.append(record)
                if line.ingredient_key:
                    native_grams[line.ingredient_key] += grams
                    resolved_grams += grams
                    _add_meta(meta, line)
                    if line.ingredient_key.startswith("ESHA:"):
                        esha_grams[line.ingredient_key[5:]] += grams
                    elif line.ingredient_key.startswith("SR28:"):
                        sr28_grams[line.ingredient_key[5:]] += grams
                elif line.key_source in {"non_food", "excluded_non_purchasable"}:
                    resolved_grams += grams
                    stats["excluded_lines"] += 1
                else:
                    unresolved_records.append(record)
                    unresolved_inputs[label] += 1
                if line.nutrition is not None:
                    nutrition_grams += grams
                    nutrition_totals["kcal"] += line.nutrition.kcal
                    nutrition_totals["protein_g"] += line.nutrition.protein_g
                    nutrition_totals["fat_g"] += line.nutrition.fat_g
                    nutrition_totals["carbs_g"] += line.nutrition.carbs_g

            if not native_grams:
                stats["recipes_without_native_grams"] += 1
                continue

            out_row = dict(row)
            native_dict = {k: round(v, 4) for k, v in sorted(native_grams.items()) if v > 0}
            out_row["fndds_grams_dict"] = repr(native_dict)
            out_row["calculator_native_grams_dict"] = repr(native_dict)
            out_row["esha_grams_dict"] = repr({k: round(v, 4) for k, v in sorted(esha_grams.items()) if v > 0})
            out_row["sr28_grams_dict"] = repr({k: round(v, 4) for k, v in sorted(sr28_grams.items()) if v > 0})
            out_row["calculator_line_resolutions_json"] = (
                json.dumps(line_records, sort_keys=True, separators=(",", ":")) if include_line_json else ""
            )
            out_row["calculator_unresolved_lines_json"] = (
                json.dumps(unresolved_records, sort_keys=True, separators=(",", ":")) if unresolved_records else ""
            )
            out_row["calculator_identity_version"] = IDENTITY_VERSION
            out_row["calculator_resolved_line_count"] = str(len(line_records) - len(unresolved_records))
            out_row["calculator_unresolved_line_count"] = str(len(unresolved_records))
            out_row["calculator_resolved_grams_pct"] = f"{(resolved_grams / total_grams * 100.0) if total_grams else 0.0:.2f}"
            out_row["total_mass_g"] = f"{sum(native_dict.values()):.4f}"
            out_row["calories_total_kcal"] = f"{nutrition_totals['kcal']:.4f}"
            out_row["protein_total_g"] = f"{nutrition_totals['protein_g']:.4f}"
            out_row["fat_total_g"] = f"{nutrition_totals['fat_g']:.4f}"
            out_row["carbs_total_g"] = f"{nutrition_totals['carbs_g']:.4f}"
            out_row["nutrition_source"] = "calculator_native"
            out_row["nutrition_source_note"] = (
                f"{IDENTITY_VERSION}; nutrition_grams_pct="
                f"{(nutrition_grams / total_grams * 100.0) if total_grams else 0.0:.2f}"
            )
            out_row["nutrition_resolved_pct"] = f"{(nutrition_grams / total_grams * 100.0) if total_grams else 0.0:.2f}"
            writer.writerow(out_row)
            selected_ids.append(rid)
            stats["recipes_written"] += 1

    tmp.replace(out_csv)
    finalized_meta = _finalize_meta(meta)
    out_ingredient_meta.write_text(json.dumps(finalized_meta, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    summary = {
        "recipes_csv": str(recipes_csv),
        "out_csv": str(out_csv),
        "out_ingredient_meta": str(out_ingredient_meta),
        "identity_version": IDENTITY_VERSION,
        "allow_sr28_fallback": allow_sr28_fallback,
        "allow_fndds_fallback": allow_fndds_fallback,
        "include_line_json": include_line_json,
        "stats": dict(stats),
        "key_sources": dict(key_sources),
        "nutrition_sources": dict(nutrition_sources),
        "top_gate_reasons": gate_reasons.most_common(50),
        "top_unresolved_inputs": unresolved_inputs.most_common(50),
        "ingredient_key_count": len(finalized_meta),
        "sample_recipe_ids": selected_ids[:20],
    }
    out_summary.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def _package_key(row: dict[str, str], *, allow_sr28_fallback: bool, allow_fndds_fallback: bool) -> tuple[str, str, str]:
    canonical = (row.get("canonical_normalized") or row.get("canonical_surface") or row.get("search_term") or "").strip()
    canonical_key = normalize_key(canonical)
    if canonical_key in PACKAGE_NATIVE_KEY_OVERRIDES:
        return PACKAGE_NATIVE_KEY_OVERRIDES[canonical_key]

    esha_code = (row.get("esha_code") or "").strip()
    esha_desc = (row.get("esha_description") or "").strip()
    if esha_code:
        ok, reason = _esha_identity_gate(canonical, esha_desc)
        if ok:
            return f"ESHA:{esha_code}", esha_desc or canonical, reason
    else:
        reason = "no_esha_code"

    sr28 = (row.get("sr28_code") or "").strip()
    if allow_sr28_fallback and sr28 and _sr28_fallback_allowed(canonical, row.get("sr28_description") or "", reason):
        return f"SR28:{sr28}", (row.get("sr28_description") or canonical), reason
    fndds = (row.get("fndds_code") or "").strip()
    if allow_fndds_fallback and fndds:
        return f"FNDDS:{fndds}", (row.get("fndds_description") or canonical), reason
    return "", "", reason


def _phrase_in_text(text: str, phrase: str) -> bool:
    phrase_key = normalize_key(phrase)
    if not phrase_key:
        return False
    return f" {phrase_key} " in f" {text} "


def _coverage_package_seed_rule(row: dict[str, str]) -> dict[str, Any] | None:
    product = normalize_key(row.get("name") or "")
    if not product:
        return None
    try:
        grams = float(row.get("grams") or 0)
    except ValueError:
        grams = 0.0
    matches: list[dict[str, Any]] = []
    for rule in COVERAGE_PACKAGE_SEED_RULES:
        min_grams = float(rule.get("min_grams") or 0)
        max_grams = float(rule.get("max_grams") or MAX_PACKAGE_GRAMS)
        if grams and grams < min_grams:
            continue
        if grams and grams > max_grams:
            continue
        if any(_phrase_in_text(product, phrase) for phrase in rule.get("reject_phrases", [])):
            continue
        if any(not _phrase_in_text(product, phrase) for phrase in rule.get("all_phrases", [])):
            continue
        any_phrases = rule.get("any_phrases", [])
        if any_phrases and not any(_phrase_in_text(product, phrase) for phrase in any_phrases):
            continue
        matches.append(rule)
    if len(matches) != 1:
        return None
    return matches[0]


def _nonfood_product_reason(name: str) -> str:
    key = normalize_key(name)
    if not key:
        return "missing_product_name"
    if "angel hair" in key and any(food in key for food in ("pasta", "spaghetti")):
        return ""
    if _has_token(key, "hair"):
        return "nonfood_personal_care:hair"
    key_tokens = set(key.split())
    if key_tokens & NONFOOD_PRODUCT_TOKENS:
        return "nonfood_product_token:" + ",".join(sorted(key_tokens & NONFOOD_PRODUCT_TOKENS)[:6])
    if "body" in key_tokens and key_tokens & {"oil", "wash"}:
        return "nonfood_personal_care:body_" + sorted(key_tokens & {"oil", "wash"})[0]
    if "bird" in key_tokens and key_tokens & {"feed", "food", "suet"}:
        return "nonfood_pet_product:bird"
    if key_tokens & {"cat", "cats", "dog", "dogs"} and key_tokens & {"food", "snack", "snacks", "treat", "treats", "training"}:
        return "nonfood_pet_product"
    for phrase in sorted(NONFOOD_PRODUCT_PHRASES):
        if _has_token(key, phrase) or phrase in key:
            return "nonfood_personal_care:" + phrase.replace(" ", "_")
    return ""


def _package_product_reason(row: dict[str, str]) -> str:
    name = (row.get("name") or "").strip()
    nonfood_reason = _nonfood_product_reason(name)
    if nonfood_reason:
        return nonfood_reason

    canonical = (row.get("canonical_normalized") or row.get("canonical_surface") or row.get("search_term") or "").strip()
    canonical_key = normalize_key(canonical)
    product_key = normalize_key(name)
    product_tokens = set(product_key.split())
    canonical_tokens = set(canonical_key.split())

    product_has_mayo = bool(product_tokens & {"mayonnaise", "mayo"})
    canonical_has_mayo = bool(canonical_tokens & {"mayonnaise", "mayo"})
    canonical_has_bacon = "bacon" in canonical_tokens
    canonical_has_round_steak = {"round", "steak"} <= canonical_tokens
    canonical_has_beef_stew_meat = {"stew", "meat"} <= canonical_tokens
    canonical_has_pork_shoulder = "pork" in canonical_tokens and bool(canonical_tokens & {"butt", "shoulder"})
    canonical_has_pork_chop = "pork" in canonical_tokens and bool(canonical_tokens & {"chop", "chops"})
    canonical_has_whole_chicken = "chicken" in canonical_tokens and bool(canonical_tokens & {"whole", "skin", "skin-on"})

    if canonical_tokens == {"meat"}:
        return "generic_meat_surface_not_purchase_specific_enough"

    extra_prepared_title = sorted(
        (product_tokens & PACKAGE_TITLE_PREPARED_FOOD_TOKENS) - canonical_tokens
    )
    if extra_prepared_title:
        return "product_title_adds_prepared_food:" + ",".join(extra_prepared_title[:6])

    if product_has_mayo and not canonical_has_mayo and "aioli" not in canonical_tokens:
        return "mayo_product_for_non_mayo_canonical"

    if canonical_has_beef_stew_meat:
        prepared_extra = product_tokens & {
            "armour",
            "can",
            "canned",
            "castleberry",
            "dinty",
            "elk",
            "frozen",
            "gravy",
            "homestyle",
            "kinder",
            "kit",
            "meal",
            "mix",
            "moore",
            "roast",
            "sauce",
            "seasoning",
            "shelf",
            "soup",
            "stable",
        }
        if prepared_extra:
            return "beef_stew_meat_product_adds_prepared_form:" + ",".join(sorted(prepared_extra)[:6])
        if not ("beef" in product_tokens and "stew" in product_tokens and (product_tokens & {"boneless", "meat"})):
            return "missing_beef_stew_meat_product_identity"

    if canonical_has_pork_chop:
        if not ("pork" in product_tokens and (product_tokens & {"chop", "chops"})):
            return "missing_pork_chop_product_identity"
        prepared_extra = product_tokens & {
            "applewood",
            "bacon",
            "bbq",
            "breaded",
            "cheddar",
            "cooked",
            "country",
            "filet",
            "fried",
            "fritter",
            "frozen",
            "garlic",
            "gravy",
            "herb",
            "hickory",
            "marinated",
            "meal",
            "patty",
            "rubbed",
            "seasoned",
            "smoked",
            "stuffed",
        }
        if prepared_extra:
            return "pork_chop_product_adds_prepared_form:" + ",".join(sorted(prepared_extra)[:6])

    if canonical_has_pork_shoulder:
        if not ("pork" in product_tokens and (product_tokens & {"butt", "shoulder"})):
            return "missing_pork_shoulder_product_identity"
        reject = product_tokens & {
            "carnitas",
            "chop",
            "chops",
            "cooked",
            "ham",
            "hickory",
            "hock",
            "hocks",
            "liver",
            "loin",
            "neckbones",
            "ready",
            "refrigerated",
            "shank",
            "smoked",
            "tamale",
            "tamales",
            "wine",
        }
        if reject:
            return "pork_shoulder_product_adds_wrong_form:" + ",".join(sorted(reject)[:6])

    if canonical_has_whole_chicken:
        if not ("chicken" in product_tokens and "whole" in product_tokens):
            return "missing_whole_chicken_product_identity"
        reject = product_tokens & {"cooked", "hot", "lemon", "pepper", "rotisserie", "seasoned", "smoked"}
        if reject:
            return "whole_chicken_product_adds_prepared_form:" + ",".join(sorted(reject)[:6])

    if canonical_has_round_steak:
        if not {"beef", "round", "steak"} <= product_tokens:
            return "missing_round_steak_product_identity"
        prepared_extra = product_tokens & {
            "corned",
            "deli",
            "fry",
            "ground",
            "milanesa",
            "pastrami",
            "roast",
            "sabana",
            "seasoned",
            "stir",
        }
        if prepared_extra:
            return "round_steak_product_adds_prepared_form:" + ",".join(sorted(prepared_extra)[:6])

    if canonical_has_bacon:
        if "bacon" not in product_tokens:
            return "missing_bacon_product_identity"
        bacon_synonyms = {
            "imitation": {"imitation", "meatless", "plant", "plant-based", "vegan", "vegetarian", "veggie"},
            "vegan": {"imitation", "meatless", "plant", "plant-based", "vegan", "vegetarian", "veggie"},
            "vegetarian": {"imitation", "meatless", "plant", "plant-based", "vegan", "vegetarian", "veggie"},
            "veggie": {"imitation", "meatless", "plant", "plant-based", "vegan", "vegetarian", "veggie"},
        }
        for subtype in ("canadian", "turkey"):
            if subtype in canonical_tokens and subtype not in product_tokens:
                return f"bacon_product_drops_subtype:{subtype}"
        for subtype, allowed in bacon_synonyms.items():
            if subtype in canonical_tokens and not (product_tokens & allowed):
                return f"bacon_product_drops_subtype:{subtype}"
        if canonical_tokens & {"bit", "bits"} and not (
            product_tokens & {"bit", "bits", "piece", "pieces", "crumbled", "chopped", "topping"}
        ):
            return "bacon_product_drops_subtype:bits"
        if canonical_tokens & {"bit", "bits"} and product_tokens & {"burger", "soup"}:
            return "bacon_product_adds_prepared_food:" + ",".join(sorted(product_tokens & {"burger", "soup"}))
        if not (canonical_tokens & {"imitation", "meatless", "vegan", "vegetarian", "veggie"}):
            meatless_extra = product_tokens & {"imitation", "meatless", "vegan", "vegetarian", "veggie"}
            if meatless_extra:
                return "bacon_product_adds_meatless_subtype:" + ",".join(sorted(meatless_extra)[:6])
        if not (canonical_tokens & {"grease", "seasoning"}):
            form_extra = product_tokens & PACKAGE_BACON_FORM_REJECT_TOKENS
            if form_extra:
                return "bacon_product_adds_form:" + ",".join(sorted(form_extra)[:6])
        if not (canonical_tokens & {"canadian", "turkey", "vegan", "vegetarian", "veggie", "imitation", "meatless"}):
            extra = product_tokens & {"canadian", "turkey", "vegan", "vegetarian", "veggie", "meatless"}
            if extra:
                return "bacon_product_adds_subtype:" + ",".join(sorted(extra)[:6])

    canonical_has_ham = "ham" in canonical_tokens and "hamburger" not in canonical_tokens
    if canonical_has_ham:
        if "ham" not in product_tokens:
            return "missing_ham_product_identity"
        if "steak" in canonical_tokens and "steak" not in product_tokens:
            return "ham_product_drops_subtype:steak"
        prepared_extra = product_tokens & {"base", "hamburger", "pickle", "pickles", "salad", "seasoning", "soup"}
        if prepared_extra:
            return "ham_product_adds_prepared_form:" + ",".join(sorted(prepared_extra)[:6])
        if (
            "lunchmeat" in product_tokens
            or {"lunch", "meat"} <= product_tokens
            or {"deli", "sliced"} <= product_tokens
        ) and not (canonical_tokens & {"deli", "lunchmeat", "sliced"}):
            return "ham_product_adds_lunchmeat_form"

    if {"chicken", "breast"} <= canonical_tokens:
        if not {"chicken", "breast"} <= product_tokens:
            return "chicken_breast_product_drops_identity"
        reject = product_tokens & {
            "breaded",
            "cooked",
            "crispy",
            "deli",
            "fully",
            "frozen",
            "grilled",
            "lunchmeat",
            "nugget",
            "nuggets",
            "rotisserie",
            "sausage",
            "tender",
            "tenderloin",
            "tenderloins",
            "tenders",
        }
        if reject:
            return "chicken_breast_product_adds_prepared_form:" + ",".join(sorted(reject)[:6])

    if "aioli" in canonical_tokens and "aioli" not in product_tokens:
        return "missing_aioli_identity"

    canonical_has_egg = bool(canonical_tokens & {"egg", "eggs", "eggnog", "yolk", "yolks"})
    if canonical_has_egg:
        product_has_egg = bool(product_tokens & {"egg", "eggs", "eggnog", "yolk", "yolks"})
        if not product_has_egg:
            return "missing_egg_product_identity"
        if "quail" in canonical_tokens and "quail" not in product_tokens:
            return "egg_product_drops_quail_identity"
        if canonical_tokens <= {"egg", "eggs"}:
            reject = product_tokens & PACKAGE_EGG_REJECT_TOKENS
            if reject:
                return "egg_product_adds_subtype:" + ",".join(sorted(reject)[:6])
        if "eggnog" in canonical_tokens:
            reject = product_tokens & {"buttermilk", "candy", "candle", "gelatin", "goat", "jelly", "lotion", "milk", "soap", "syrup"}
            if reject:
                return "eggnog_product_adds_subtype:" + ",".join(sorted(reject)[:6])

    canonical_has_milk = "milk" in canonical_tokens or "buttermilk" in canonical_tokens
    if canonical_has_milk:
        if "buttermilk" in canonical_tokens:
            if "buttermilk" not in product_tokens:
                return "missing_buttermilk_product_identity"
            if not (canonical_tokens & {"powder", "mix"}):
                reject = product_tokens & {"goat", "mix", "pancake", "powder", "waffle"}
                if reject:
                    return "buttermilk_product_adds_form:" + ",".join(sorted(reject)[:6])
        if "evaporated" in canonical_tokens:
            if "evaporated" not in product_tokens:
                return "missing_evaporated_milk_product_identity"
            if "filled" not in canonical_tokens and "filled" in product_tokens:
                return "evaporated_milk_product_adds_subtype:filled"

    if canonical_has_mayo:
        if "mayonnaise" not in product_tokens and "mayo" not in product_tokens:
            return "missing_mayonnaise_identity"
        canonical_subtypes = canonical_tokens & PACKAGE_MAYONNAISE_REJECT_TOKENS
        product_subtypes = product_tokens & PACKAGE_MAYONNAISE_REJECT_TOKENS
        extra = product_subtypes - canonical_subtypes
        missing = canonical_subtypes - product_subtypes
        if extra:
            return "mayonnaise_product_adds_subtype:" + ",".join(sorted(extra)[:6])
        if missing:
            return "mayonnaise_product_drops_subtype:" + ",".join(sorted(missing)[:6])

    local_gate_owns_surface = (
        canonical_has_mayo
        or canonical_has_egg
        or "parsley" in canonical_tokens
    )
    if canonical_key and not local_gate_owns_surface:
        lab_product = LabProduct(
            gtin_upc=(row.get("upc") or "").strip(),
            description=name,
            brand_name="",
            category="",
            source="retail_surface_bridge_package_gate",
        )
        accepted, accept_reason = _product_acceptance_reason(lab_product, canonical_key)
        if not accepted:
            return "product_title_gate:" + accept_reason

    return ""


PACKAGE_NATIVE_KEY_PRODUCT_SURFACES = {
    "ESHA:502": "cream",
    "ESHA:633": "cheddar cheese",
    "ESHA:1015": "cream cheese",
    "ESHA:1064": "ricotta cheese",
    "ESHA:1251": "parmesan cheese",
    "ESHA:1280": "cheddar cheese",
    "ESHA:10480": "beef suet",
    "ESHA:12005": "ham",
    "ESHA:12132": "ham steak",
    "ESHA:12028": "pork chop",
    "ESHA:12221": "pork shoulder",
    "ESHA:13367": "chile pepper",
    "ESHA:13477": "black beans",
    "ESHA:15060": "chicken thigh",
    "ESHA:15071": "whole chicken",
    "ESHA:25006": "granulated sugar",
    "ESHA:25765": "butter",
    "ESHA:26015": "poppy seed",
    "ESHA:26013": "fresh parsley",
    "ESHA:26037": "white pepper",
    "ESHA:26624": "vanilla extract",
    "ESHA:28003": "baking soda",
    "ESHA:27997": "beef stew meat",
    "ESHA:3036": "cherry",
    "ESHA:33320": "pesto",
    "ESHA:36160": "white bread",
    "ESHA:36958": "colby jack cheese",
    "ESHA:37056": "kielbasa",
    "ESHA:3766": "raisins",
    "ESHA:38579": "dry pasta",
    "ESHA:39180": "jalapeno",
    "ESHA:4578": "pecans",
    "ESHA:5001": "asparagus",
    "ESHA:5116": "green peas",
    "ESHA:51685": "coconut water",
    "ESHA:5715": "potato",
    "ESHA:63413": "brown sugar",
    "ESHA:90965": "vegetable oil",
    "SR28:168450": "pumpkin",
    "SR28:169655": "sugar",
    "SR28:169731": "egg noodles",
    "SR28:171192": "tomato sauce",
    "SR28:171413": "olive oil",
    "SR28:173448": "velveeta cheese",
}


def _package_native_key_product_reason(row: dict[str, str], key: str) -> str:
    product = normalize_key(row.get("name") or "")
    product_tokens = set(product.split())

    if key == "ESHA:33320":
        if "pesto" not in product_tokens:
            return "missing_pesto_product_identity"
        reject = product_tokens & {
            "bowl",
            "chicken",
            "dry",
            "frozen",
            "kit",
            "meal",
            "mix",
            "salad",
            "seasoning",
            "spices",
            "tortellini",
        }
        if reject:
            return "pesto_product_adds_wrong_form:" + ",".join(sorted(reject)[:6])
        return ""

    if key == "ESHA:17230":
        if "salmon" not in product_tokens:
            return "missing_salmon_product_identity"
        reject = product_tokens & {"burger", "burgers", "can", "canned", "chunk", "dip", "patty", "pouch", "smoked"}
        if reject:
            return "salmon_product_adds_wrong_form:" + ",".join(sorted(reject)[:6])
        return ""

    if key == "ESHA:3072":
        if "lime" not in product_tokens or "juice" not in product_tokens:
            return "missing_lime_juice_product_identity"
        reject = product_tokens & {"cocktail", "cordial", "rose", "sweetened"}
        if reject:
            return "lime_juice_product_adds_wrong_form:" + ",".join(sorted(reject)[:6])
        return ""

    if key == "ESHA:31748":
        if "ginger" not in product_tokens or "syrup" not in product_tokens:
            return "missing_ginger_syrup_product_identity"
        reject = product_tokens & {"blend", "greens", "juice"}
        if reject:
            return "ginger_syrup_product_adds_wrong_form:" + ",".join(sorted(reject)[:6])
        return ""

    if key == "ESHA:4086":
        if "ginger" not in product_tokens or not (product_tokens & {"ground", "powder", "powdered"}):
            return "missing_ground_ginger_product_identity"
        reject = product_tokens & {
            "ale",
            "beer",
            "brew",
            "capsule",
            "cookie",
            "cookies",
            "dressing",
            "extract",
            "fresh",
            "juice",
            "pickled",
            "sauce",
            "shot",
            "snap",
            "snaps",
            "soda",
            "supplement",
            "sushi",
            "syrup",
        }
        if reject:
            return "ground_ginger_product_adds_wrong_form:" + ",".join(sorted(reject)[:6])
        return ""

    if key == "ESHA:90442":
        if "ginger" not in product_tokens:
            return "missing_fresh_ginger_product_identity"
        if not (product_tokens & {"fresh", "gingerroot", "minced", "organic", "paste", "peeled", "root"}):
            return "missing_fresh_ginger_product_identity"
        reject = product_tokens & {
            "ale",
            "beer",
            "brew",
            "cookie",
            "cookies",
            "dressing",
            "dried",
            "dry",
            "ground",
            "juice",
            "kit",
            "kombucha",
            "pickled",
            "powder",
            "powdered",
            "salad",
            "sauce",
            "shot",
            "snap",
            "snaps",
            "soda",
            "sushi",
            "syrup",
            "topper",
        }
        if reject:
            return "fresh_ginger_product_adds_wrong_form:" + ",".join(sorted(reject)[:6])
        return ""

    if key == "ESHA:33708":
        if "ginger" not in product_tokens or not (product_tokens & {"gari", "pickled", "sushi"}):
            return "missing_pickled_ginger_product_identity"
        reject = product_tokens & {
            "ale",
            "beer",
            "brew",
            "cookie",
            "cookies",
            "dressing",
            "fresh",
            "ground",
            "juice",
            "powder",
            "powdered",
            "root",
            "sauce",
            "shot",
            "snap",
            "snaps",
            "soda",
            "syrup",
        }
        if reject:
            return "pickled_ginger_product_adds_wrong_form:" + ",".join(sorted(reject)[:6])
        return ""

    if key == "ESHA:1817":
        if not (product_tokens & {"pea", "peas"}):
            return "missing_frozen_pea_product_identity"
        if not (product_tokens & {"frozen", "steamable", "steamfresh"}):
            return "missing_frozen_pea_product_form"
        reject = product_tokens & {
            "blackeye",
            "blackeyed",
            "carrot",
            "carrots",
            "dried",
            "edamame",
            "freeze",
            "freeze-dried",
            "fried",
            "mix",
            "mixed",
            "snap",
            "split",
            "stir",
            "wasabi",
        }
        if reject:
            return "frozen_pea_product_adds_wrong_form:" + ",".join(sorted(reject)[:6])
        return ""

    if key == "ESHA:26003":
        if "cinnamon" not in product_tokens:
            return "missing_ground_cinnamon_product_identity"
        reject = product_tokens & {
            "apple",
            "bakery",
            "baby",
            "blend",
            "cereal",
            "cinnabon",
            "cream",
            "creamer",
            "crunch",
            "drink",
            "icing",
            "roll",
            "rolls",
            "stick",
            "sticks",
            "sugar",
            "syrup",
            "toast",
            "yogurt",
        }
        if reject:
            return "ground_cinnamon_product_adds_wrong_form:" + ",".join(sorted(reject)[:6])
        if not (product_tokens & {"cinnamon", "ground", "powder"}):
            return "missing_ground_cinnamon_product_identity"
        return ""

    if key == "ESHA:90212":
        if not (product_tokens & {"pepper", "peppercorn", "peppercorns"}):
            return "missing_black_pepper_product_identity"
        if not (product_tokens & {"black", "malabar", "tellicherry"}):
            return "missing_black_pepper_product_identity"
        reject = product_tokens & {
            "chips",
            "cracker",
            "crackers",
            "crisp",
            "crisps",
            "dressing",
            "filet",
            "loin",
            "marinade",
            "medley",
            "pork",
            "poppy",
            "rub",
            "seasoned",
            "water",
        }
        if reject:
            return "black_pepper_product_adds_wrong_form:" + ",".join(sorted(reject)[:6])
        return ""

    if key == "ESHA:28000":
        if "yeast" not in product_tokens:
            return "missing_active_dry_yeast_product_identity"
        reject = product_tokens & {
            "bakery",
            "brewers",
            "cream",
            "donuts",
            "dough",
            "extract",
            "frozen",
            "infection",
            "miconazole",
            "nutritional",
            "rolls",
            "seasoning",
            "suppositories",
        }
        if reject:
            return "active_dry_yeast_product_adds_wrong_form:" + ",".join(sorted(reject)[:6])
        if not (product_tokens & {"active", "activedry", "dry", "instant", "rapidrise"}):
            return "missing_active_dry_yeast_product_identity"
        return ""

    if key == "ESHA:4557":
        if not (product_tokens & {"walnut", "walnuts"}):
            return "missing_walnut_product_identity"
        reject = product_tokens & {
            "banana",
            "cake",
            "cereal",
            "coffee",
            "cookie",
            "cranberries",
            "fudge",
            "granola",
            "ice",
            "loaf",
            "mixed",
            "oatmeal",
            "raisin",
            "snack",
            "topping",
        }
        if reject:
            return "walnut_product_adds_wrong_form:" + ",".join(sorted(reject)[:6])
        return ""

    if key == "ESHA:15762":
        if "chicken" not in product_tokens:
            return "missing_chicken_bouillon_product_identity"
        if not (product_tokens & {"base", "bouillon", "cubes", "granulated", "powder"}):
            return "missing_chicken_bouillon_product_identity"
        reject = product_tokens & {"bone", "broth", "carton", "stock", "tomato"}
        if reject:
            return "chicken_bouillon_product_adds_wrong_form:" + ",".join(sorted(reject)[:6])
        return ""

    if key == "ESHA:24144":
        if "chocolate" not in product_tokens:
            return "missing_milk_chocolate_product_identity"
        if not (product_tokens & {"bar", "bars", "candy", "chocolate"}):
            return "missing_milk_chocolate_product_identity"
        reject = product_tokens & {
            "baking",
            "cake",
            "chip",
            "chips",
            "cookie",
            "cookies",
            "cream",
            "frosting",
            "ice",
            "mix",
            "morsels",
            "semi",
            "semisweet",
        }
        if reject:
            return "milk_chocolate_product_adds_wrong_form:" + ",".join(sorted(reject)[:6])
        return ""

    if key == "ESHA:1235":
        if "blue" not in product_tokens or "cheese" not in product_tokens:
            return "missing_blue_cheese_product_identity"
        reject = product_tokens & {
            "almond",
            "crackers",
            "cracker",
            "dip",
            "dressing",
            "jack",
            "kit",
            "nut",
            "nuts",
            "olives",
            "pepper",
            "rice",
            "salad",
            "sauce",
            "spread",
            "thins",
            "yogurt",
        }
        if reject:
            return "blue_cheese_product_adds_wrong_form:" + ",".join(sorted(reject)[:6])
        return ""

    if key == "ESHA:5116":
        if not (product_tokens & {"pea", "peas"}):
            return "missing_green_pea_product_identity"
        reject = product_tokens & {"crisps", "food", "snack", "snap", "snaps", "soup", "split", "wasabi"}
        if reject:
            return "green_pea_product_adds_wrong_form:" + ",".join(sorted(reject)[:6])
        return ""

    required_surface = PACKAGE_NATIVE_KEY_PRODUCT_SURFACES.get(key)
    if not required_surface:
        return ""

    gate_row = dict(row)
    gate_row["canonical_normalized"] = required_surface
    reason = _package_product_reason(gate_row)
    if reason:
        return reason

    if key in {"ESHA:633", "ESHA:1280"}:
        reject = product_tokens & {
            "almond",
            "almonds",
            "breaks",
            "case",
            "cheetos",
            "cheez",
            "chip",
            "chips",
            "cracker",
            "crackers",
            "cranberries",
            "cranberry",
            "macaroni",
            "nacho",
            "pasta",
            "sauce",
            "spread",
            "spreadable",
            "wedge",
            "wedges",
        }
        if reject:
            return "cheddar_product_adds_wrong_form:" + ",".join(sorted(reject)[:6])

    if key == "ESHA:1015":
        reject = product_tokens & {"chive", "flavored", "whipped"}
        if reject:
            return "cream_cheese_product_adds_wrong_form:" + ",".join(sorted(reject)[:6])

    if key == "ESHA:1064":
        reject = product_tokens & {"pasta", "ravioli", "raviolis", "spinach"}
        if reject:
            return "ricotta_product_adds_wrong_form:" + ",".join(sorted(reject)[:6])

    if key == "ESHA:1251":
        reject = product_tokens & {"dairy", "free", "vegan"}
        if reject:
            return "parmesan_product_adds_wrong_form:" + ",".join(sorted(reject)[:6])

    if key == "ESHA:502":
        if "cream" not in product_tokens:
            return "missing_heavy_cream_product_identity"
        if not (product_tokens & {"heavy", "whipping"}):
            return "missing_heavy_cream_product_identity"
        reject = product_tokens & {"alternative", "condensed", "corn", "dairy", "free", "powder", "soup", "sour", "topping", "whipped"}
        if reject:
            return "heavy_cream_product_adds_wrong_form:" + ",".join(sorted(reject)[:6])

    if key == "ESHA:13367":
        pepper_identity = product_tokens & {"chile", "chiles", "chili", "chilies", "pepper", "peppers", "habanero", "jalapeno", "serrano"}
        if not pepper_identity:
            return "missing_hot_chile_pepper_product_identity"
        reject = product_tokens & {"beans", "carne", "con", "dog", "ground", "marinade", "paste", "powder", "sauce", "soups"}
        if reject:
            return "hot_chile_pepper_product_adds_wrong_form:" + ",".join(sorted(reject)[:6])

    if key == "ESHA:13477":
        if "black" not in product_tokens or not (product_tokens & {"bean", "beans"}):
            return "missing_black_bean_product_identity"
        reject = product_tokens & {"borlotti", "burger", "burgers", "butter", "cannellini", "chickpeas", "kidney", "medley", "red"}
        if reject:
            return "black_bean_product_adds_wrong_form:" + ",".join(sorted(reject)[:6])

    if key == "ESHA:33320":
        if "pesto" not in product_tokens:
            return "missing_pesto_product_identity"
        reject = product_tokens & {
            "bowl",
            "chicken",
            "dry",
            "frozen",
            "kit",
            "meal",
            "mix",
            "salad",
            "seasoning",
            "spices",
            "tortellini",
        }
        if reject:
            return "pesto_product_adds_wrong_form:" + ",".join(sorted(reject)[:6])

    if key == "ESHA:5116":
        if not (product_tokens & {"pea", "peas"}):
            return "missing_green_pea_product_identity"
        reject = product_tokens & {"crisps", "food", "snack", "snaps", "soup", "split", "wasabi"}
        if reject:
            return "green_pea_product_adds_wrong_form:" + ",".join(sorted(reject)[:6])

    if key == "ESHA:15060":
        if "chicken" not in product_tokens or not (product_tokens & {"thigh", "thighs"}):
            return "missing_chicken_thigh_product_identity"
        reject = product_tokens & {"cooked", "grilled", "heat", "ready", "strips"}
        if reject:
            return "chicken_thigh_product_adds_prepared_form:" + ",".join(sorted(reject)[:6])

    if key == "ESHA:25765":
        reject = product_tokens & {"liquid", "alternative"}
        if reject:
            return "butter_product_adds_wrong_form:" + ",".join(sorted(reject)[:6])

    if key == "ESHA:25006":
        if "sugar" not in product_tokens:
            return "missing_granulated_sugar_product_identity"
        reject = product_tokens & {"chip", "chips", "chocolate", "monkfruit", "stevia", "substitute", "sweetener"}
        if reject:
            return "granulated_sugar_product_adds_wrong_form:" + ",".join(sorted(reject)[:6])

    if key == "ESHA:26015":
        if "poppy" not in product_tokens or "seed" not in product_tokens:
            return "missing_poppy_seed_product_identity"
        reject = product_tokens & {"filling"}
        if reject:
            return "poppy_seed_product_adds_wrong_form:" + ",".join(sorted(reject)[:6])

    if key == "ESHA:26013":
        if "parsley" not in product_tokens:
            return "missing_fresh_parsley_product_identity"
        dried_or_nonculinary = product_tokens & {
            "bulk",
            "case",
            "dried",
            "flakes",
            "freeze",
            "freeze-dried",
            "jar",
            "plant",
            "plants",
            "seasoning",
            "spice",
        }
        if dried_or_nonculinary:
            return "fresh_parsley_product_adds_wrong_form:" + ",".join(sorted(dried_or_nonculinary)[:6])

    if key == "ESHA:26037":
        if "white" not in product_tokens or not (product_tokens & {"pepper", "peppercorn", "peppercorns"}):
            return "missing_white_pepper_product_identity"
        reject = product_tokens & {"bite", "bites", "cheese", "egg", "red"}
        if reject:
            return "white_pepper_product_adds_wrong_form:" + ",".join(sorted(reject)[:6])

    if key == "ESHA:3036":
        if not (product_tokens & {"cherry", "cherries"}):
            return "missing_cherry_product_identity"
        reject = product_tokens & {"candle", "scent", "wax"}
        if reject:
            return "cherry_product_adds_nonfood_form:" + ",".join(sorted(reject)[:6])

    if key == "ESHA:36160":
        reject = product_tokens & {"bun", "buns", "dough", "hamburger", "hawaiian", "petite"}
        if reject:
            return "white_bread_product_adds_wrong_form:" + ",".join(sorted(reject)[:6])

    if key == "ESHA:37056":
        if "kielbasa" not in product_tokens and not ({"polish", "sausage"} <= product_tokens):
            return "missing_kielbasa_product_identity"
        reject = product_tokens & {"breakfast", "brown", "gravy", "links", "serve"}
        if reject:
            return "kielbasa_product_adds_wrong_form:" + ",".join(sorted(reject)[:6])

    if key == "ESHA:3766":
        if not (product_tokens & {"raisin", "raisins"}):
            return "missing_raisin_product_identity"
        reject = product_tokens & {"bran", "bread", "cereal", "oatmeal"}
        if reject:
            return "raisin_product_adds_wrong_form:" + ",".join(sorted(reject)[:6])

    if key == "ESHA:38579":
        reject = product_tokens & {"cooked", "frozen", "marinara", "meal", "microwave", "penne", "ready", "rotini", "spaghetti"}
        if reject:
            return "dry_pasta_product_adds_wrong_form:" + ",".join(sorted(reject)[:6])
        if not (product_tokens & {"elbow", "macaroni"}):
            return "missing_elbow_macaroni_product_identity"

    if key == "ESHA:39180":
        if "jalapeno" not in product_tokens or not (product_tokens & {"chile", "chili", "pepper", "peppers"}):
            return "missing_jalapeno_pepper_product_identity"
        reject = product_tokens & {"bar", "bars", "cheese", "jack", "monterey", "sauce", "snack"}
        if reject:
            return "jalapeno_pepper_product_adds_wrong_form:" + ",".join(sorted(reject)[:6])

    if key == "ESHA:4578":
        if not (product_tokens & {"pecan", "pecans"}):
            return "missing_pecan_product_identity"
        reject = product_tokens & {"honey", "piece", "pieces", "roasted", "snacking"}
        if reject:
            return "pecan_halves_product_adds_wrong_form:" + ",".join(sorted(reject)[:6])

    if key == "ESHA:5001":
        reject = product_tokens & {"air", "fryer", "seasoned"}
        if reject:
            return "asparagus_product_adds_wrong_form:" + ",".join(sorted(reject)[:6])

    if key == "ESHA:51685":
        if not ("coconut" in product_tokens and "water" in product_tokens):
            return "missing_coconut_water_product_identity"
        reject = product_tokens & {"flake", "flakes", "powder", "sweetened", "toasted"}
        if reject:
            return "coconut_water_product_adds_wrong_form:" + ",".join(sorted(reject)[:6])

    if key == "ESHA:5715":
        reject = product_tokens & {"can", "canned", "diced"}
        if reject:
            return "fresh_potato_product_adds_wrong_form:" + ",".join(sorted(reject)[:6])

    if key == "ESHA:63413":
        if not {"brown", "sugar"} <= product_tokens:
            return "missing_brown_sugar_product_identity"
        reject = product_tokens & {"cereal", "oatmeal", "oats", "protein"}
        if reject:
            return "brown_sugar_product_adds_wrong_form:" + ",".join(sorted(reject)[:6])

    if key == "ESHA:90965":
        reject = product_tokens & {"butter", "carrier", "doo", "gro", "infusion", "newton", "painting", "skin", "sticks", "styling", "winsor"}
        if reject:
            return "vegetable_oil_product_adds_wrong_form:" + ",".join(sorted(reject)[:6])

    if key == "SR28:168450":
        if "pumpkin" not in product_tokens:
            return "missing_canned_pumpkin_product_identity"
        if not (product_tokens & {"can", "canned", "puree", "pure", "solid", "solids"}):
            return "missing_canned_pumpkin_product_form"
        reject = product_tokens & {"baby", "food", "pouch", "seed", "seeds"}
        if reject:
            return "canned_pumpkin_product_adds_wrong_form:" + ",".join(sorted(reject)[:6])

    if key == "SR28:169655":
        if "sugar" not in product_tokens:
            return "missing_sugar_product_identity"
        reject = product_tokens & {
            "apple",
            "applesauce",
            "bar",
            "bars",
            "cereal",
            "chobani",
            "cookie",
            "cookies",
            "cup",
            "cups",
            "dot",
            "dots",
            "free",
            "frosted",
            "fruit",
            "gum",
            "mott",
            "oatmeal",
            "pastries",
            "pastry",
            "pita",
            "pop",
            "popped",
            "pretzel",
            "pretzels",
            "protein",
            "puffed",
            "sauce",
            "snack",
            "snacks",
            "square",
            "squares",
            "toaster",
            "tart",
            "tarts",
            "twists",
            "yogurt",
        }
        if reject:
            return "sugar_product_adds_wrong_form:" + ",".join(sorted(reject)[:6])
        return ""

    if key == "SR28:169731":
        if "egg" not in product_tokens or not (product_tokens & {"noodle", "noodles"}):
            return "missing_dry_egg_noodle_product_identity"
        reject = product_tokens & {"angel", "eat", "hair", "keto", "protein", "ready"}
        if reject:
            return "dry_egg_noodle_product_adds_wrong_form:" + ",".join(sorted(reject)[:6])

    if key == "SR28:171192":
        if "tomato" not in product_tokens or "sauce" not in product_tokens:
            return "missing_tomato_sauce_product_identity"
        reject = product_tokens & {"blend", "mix", "seasoning"}
        if reject:
            return "tomato_sauce_product_adds_wrong_form:" + ",".join(sorted(reject)[:6])

    if key == "SR28:173448":
        if "velveeta" not in product_tokens:
            return "missing_velveeta_product_identity"
        reject = product_tokens & {
            "bacon",
            "broccoli",
            "chicken",
            "cup",
            "cups",
            "dinner",
            "kit",
            "macaroni",
            "microwaveable",
            "pasta",
            "shell",
            "shells",
            "skillets",
        }
        if reject:
            return "velveeta_product_adds_wrong_form:" + ",".join(sorted(reject)[:6])

    return ""


def _egg_count_package_grams(row: dict[str, str], key: str, grams: float) -> float:
    if key not in {"ESHA:19500", "ESHA:19508", "ESHA:35876"}:
        return grams
    canonical = normalize_key(row.get("canonical_normalized") or row.get("canonical_surface") or row.get("search_term") or "")
    product = normalize_key(row.get("name") or "")
    canonical_tokens = set(canonical.split())
    product_tokens = set(product.split())
    if not (canonical_tokens & {"egg", "eggs", "yolk", "yolks"} or product_tokens & {"egg", "eggs"}):
        return grams
    match = re.search(r"\b(\d{1,3})\s*(?:count|ct)\b", row.get("name") or "", re.IGNORECASE)
    if not match:
        return grams
    count = int(match.group(1))
    if count <= 0 or count > 60:
        return grams
    corrected = float(count * 50)
    if grams > corrected * 3:
        return corrected
    return grams


def _package_price_reason(row: dict[str, str], key: str, grams: float, cents: int) -> str:
    canonical = normalize_key(row.get("canonical_normalized") or row.get("canonical_surface") or row.get("search_term") or "")
    canonical_tokens = set(canonical.split())
    product = normalize_key(row.get("name") or "")
    product_tokens = set(product.split())
    if (key in {"ESHA:12005", "ESHA:12132"} or "ham" in canonical_tokens) and key.startswith("ESHA:"):
        if {"limit", "sale"} <= product_tokens or "random weight" in product:
            return "ham_probable_unit_price:not_package_total"
        cpg = cents / grams if grams > 0 else 0.0
        if grams > 1000 and cpg < 0.5:
            return "ham_implausible_large_package_unit_price"
    if (key == "ESHA:12028" or ("pork" in canonical_tokens and (canonical_tokens & {"chop", "chops"}))) and key.startswith("ESHA:"):
        cpg = cents / grams if grams > 0 else 0.0
        if grams > 2500 and cpg < 0.4:
            return "pork_chop_implausible_large_package_unit_price"
        if cpg < 0.7:
            return "pork_chop_implausible_low_unit_price"
    if (key == "ESHA:12221" or ("pork" in canonical_tokens and (canonical_tokens & {"butt", "shoulder"}))) and key.startswith("ESHA:"):
        cpg = cents / grams if grams > 0 else 0.0
        if cpg < 0.5:
            return "pork_shoulder_implausible_low_unit_price"
    if key == "ESHA:26013":
        if grams > 100:
            return "fresh_parsley_implausible_large_package"
    if key == "ESHA:33320":
        if grams > 1000:
            return "pesto_implausible_large_package"
    return ""


def build_package_db(
    *,
    bridge_csv: Path,
    out_db: Path,
    out_summary: Path,
    product_identity_bridge_csv: Path | None = DEFAULT_PRODUCT_IDENTITY_BRIDGE_CSV,
    allow_sr28_fallback: bool = True,
    allow_fndds_fallback: bool = False,
    max_per_key_store: int = 12,
) -> dict[str, Any]:
    out_db.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_db.with_suffix(out_db.suffix + ".tmp")
    if tmp.exists():
        tmp.unlink()
    conn = sqlite3.connect(str(tmp))
    conn.executescript(PACKAGE_SCHEMA)

    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    stats: Counter[str] = Counter()
    gate_reasons: Counter[str] = Counter()

    with bridge_csv.open(newline="", encoding="utf-8-sig", errors="replace") as handle:
        reader = csv.DictReader((line.replace("\x00", "") for line in handle))
        for row in reader:
            stats["rows"] += 1
            if (row.get("canonical_match_status") or "").strip() != "assigned":
                stats["skip_not_assigned"] += 1
                continue
            product_reason = _package_product_reason(row)
            if product_reason:
                stats["skip_product_gate"] += 1
                gate_reasons[product_reason] += 1
                continue
            key, description, reason = _package_key(
                row,
                allow_sr28_fallback=allow_sr28_fallback,
                allow_fndds_fallback=allow_fndds_fallback,
            )
            gate_reasons[reason] += 1
            if not key:
                stats["skip_no_native_key"] += 1
                continue
            native_key_product_reason = _package_native_key_product_reason(row, key)
            if native_key_product_reason:
                stats["skip_native_key_product_gate"] += 1
                gate_reasons[native_key_product_reason] += 1
                continue
            try:
                grams = round(float(row.get("grams") or 0), 3)
                cents = int(round(float(row.get("cents") or 0)))
            except ValueError:
                stats["skip_bad_numeric"] += 1
                continue
            corrected_grams = round(_egg_count_package_grams(row, key, grams), 3)
            if corrected_grams != grams:
                stats["correct_egg_count_grams"] += 1
                grams = corrected_grams
            if grams <= 0 or grams > MAX_PACKAGE_GRAMS:
                stats["skip_bad_grams"] += 1
                continue
            if cents <= 0 or cents > MAX_PRICE_CENTS:
                stats["skip_bad_cents"] += 1
                continue
            price_reason = _package_price_reason(row, key, grams, cents)
            if price_reason:
                stats["skip_price_gate"] += 1
                gate_reasons[price_reason] += 1
                continue
            source = (row.get("retail_source") or "").strip()
            if source not in {"kroger", "walmart"}:
                stats["skip_bad_source"] += 1
                continue
            grouped[(key, source)].append(
                {
                    "key": key,
                    "description": description,
                    "grams": grams,
                    "cents": cents,
                    "source": source,
                    "upc": (row.get("upc") or "").strip(),
                    "name": (row.get("name") or "").strip(),
                    "canonical_surface": (row.get("canonical_surface") or "").strip(),
                    "canonical_shopping_item": (row.get("canonical_shopping_item") or "").strip(),
                    "search_term": (row.get("search_term") or "").strip(),
                    "gate_reason": reason,
                }
            )

    limited: list[dict[str, Any]] = []
    for (_key, _source), rows in grouped.items():
        seen_sizes: set[float] = set()
        for row in sorted(rows, key=lambda item: (item["cents"] / item["grams"], item["cents"], item["grams"])):
            if row["grams"] in seen_sizes:
                continue
            seen_sizes.add(row["grams"])
            limited.append(row)
            if len(seen_sizes) >= max_per_key_store:
                break

    by_key_size: dict[tuple[str, float], dict[str, Any]] = {}
    for row in limited:
        item = by_key_size.setdefault(
            (row["key"], row["grams"]),
            {
                "key": row["key"],
                "description": row["description"],
                "grams": row["grams"],
                "walmart_price_cents": None,
                "kroger_price_cents": None,
                "samples": [],
                "source": "calculator_native_retail_bridge",
            },
        )
        price_col = f"{row['source']}_price_cents"
        item[price_col] = row["cents"] if item[price_col] is None else min(item[price_col], row["cents"])
        if len(item["samples"]) < 6:
            item["samples"].append(
                {
                    "source": row["source"],
                    "upc": row["upc"],
                    "name": row["name"],
                    "canonical_surface": row["canonical_surface"],
                    "canonical_shopping_item": row["canonical_shopping_item"],
                    "search_term": row["search_term"],
                    "cents": row["cents"],
                    "gate_reason": row["gate_reason"],
                }
            )

    coverage_seed_stats: Counter[str] = Counter()
    coverage_grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    with bridge_csv.open(newline="", encoding="utf-8-sig", errors="replace") as handle:
        reader = csv.DictReader((line.replace("\x00", "") for line in handle))
        for row in reader:
            coverage_seed_stats["rows"] += 1
            rule = _coverage_package_seed_rule(row)
            if not rule:
                continue
            coverage_seed_stats["matched"] += 1
            coverage_seed_stats[f"matched:{rule['id']}"] += 1
            source = (row.get("retail_source") or "").strip()
            if source not in {"kroger", "walmart"}:
                coverage_seed_stats["skip_bad_source"] += 1
                continue
            nonfood_reason = _nonfood_product_reason(row.get("name") or "")
            if nonfood_reason:
                coverage_seed_stats["skip_nonfood"] += 1
                gate_reasons[nonfood_reason] += 1
                continue
            try:
                grams = round(float(row.get("grams") or 0), 3)
                cents = int(round(float(row.get("cents") or 0)))
            except ValueError:
                coverage_seed_stats["skip_bad_numeric"] += 1
                continue
            if grams <= 0 or grams > MAX_PACKAGE_GRAMS:
                coverage_seed_stats["skip_bad_grams"] += 1
                continue
            if cents <= 0 or cents > MAX_PRICE_CENTS:
                coverage_seed_stats["skip_bad_cents"] += 1
                continue
            targets: list[tuple[str, str]] = [(str(rule["key"]), str(rule["description"]))]
            for alias in rule.get("alias_keys", []):
                if not isinstance(alias, dict):
                    continue
                alias_key = str(alias.get("key") or "").strip()
                alias_description = str(alias.get("description") or "").strip()
                if alias_key and alias_description:
                    targets.append((alias_key, alias_description))

            for key, description in targets:
                gate_row = {
                    "canonical_normalized": description,
                    "name": row.get("name") or "",
                }
                price_reason = _package_price_reason(gate_row, key, grams, cents)
                if price_reason:
                    coverage_seed_stats["skip_price_gate"] += 1
                    gate_reasons[price_reason] += 1
                    continue
                coverage_grouped[(key, source)].append(
                    {
                        "key": key,
                        "description": description,
                        "grams": grams,
                        "cents": cents,
                        "source": source,
                        "upc": (row.get("upc") or "").strip(),
                        "name": (row.get("name") or "").strip(),
                        "canonical_surface": str(rule["id"]),
                        "canonical_shopping_item": description,
                        "search_term": (row.get("search_term") or "").strip(),
                        "gate_reason": f"coverage_package_seed:{rule['id']}",
                    }
                )

    for (_key, _source), rows in coverage_grouped.items():
        seen_sizes: set[float] = set()
        for row in sorted(rows, key=lambda item: (item["cents"] / item["grams"], item["cents"], item["grams"])):
            if row["grams"] in seen_sizes:
                continue
            seen_sizes.add(row["grams"])
            item = by_key_size.setdefault(
                (row["key"], row["grams"]),
                {
                    "key": row["key"],
                    "description": row["description"],
                    "grams": row["grams"],
                    "walmart_price_cents": None,
                    "kroger_price_cents": None,
                    "samples": [],
                    "source": "coverage_package_seed",
                },
            )
            price_col = f"{row['source']}_price_cents"
            item[price_col] = row["cents"] if item[price_col] is None else min(item[price_col], row["cents"])
            if item["source"] == "calculator_native_retail_bridge":
                item["source"] = "calculator_native_retail_bridge+coverage_package_seed"
            if len(item["samples"]) < 6:
                item["samples"].append(
                    {
                        "source": row["source"],
                        "upc": row["upc"],
                        "name": row["name"],
                        "canonical_surface": row["canonical_surface"],
                        "canonical_shopping_item": row["canonical_shopping_item"],
                        "search_term": row["search_term"],
                        "cents": row["cents"],
                        "gate_reason": row["gate_reason"],
                    }
                )
            coverage_seed_stats["accepted"] += 1
            coverage_seed_stats[f"accepted:{row['key']}"] += 1
            if len(seen_sizes) >= max_per_key_store:
                break

    product_identity_bridge_stats: Counter[str] = Counter()
    if product_identity_bridge_csv is None:
        product_identity_bridge_stats["disabled"] += 1
    elif not product_identity_bridge_csv.exists():
        product_identity_bridge_stats["missing"] += 1
    else:
        with product_identity_bridge_csv.open(newline="", encoding="utf-8-sig", errors="replace") as handle:
            reader = csv.DictReader((line.replace("\x00", "") for line in handle))
            for row in reader:
                product_identity_bridge_stats["rows"] += 1
                key = (row.get("ingredient_key") or "").strip()
                description = (row.get("food_description") or row.get("product_identity") or "").strip()
                if not key or not description:
                    product_identity_bridge_stats["skip_missing_key"] += 1
                    continue
                source = (row.get("retail_source") or row.get("source") or "").strip()
                if source not in {"kroger", "walmart"}:
                    product_identity_bridge_stats["skip_bad_source"] += 1
                    continue
                name = (row.get("name") or "").strip()
                nonfood_reason = _nonfood_product_reason(name)
                if nonfood_reason:
                    product_identity_bridge_stats["skip_nonfood"] += 1
                    gate_reasons[nonfood_reason] += 1
                    continue
                try:
                    grams = round(float(row.get("grams") or 0), 3)
                    cents = int(round(float(row.get("cents") or 0)))
                except ValueError:
                    product_identity_bridge_stats["skip_bad_numeric"] += 1
                    continue
                if grams <= 0 or grams > MAX_PACKAGE_GRAMS:
                    product_identity_bridge_stats["skip_bad_grams"] += 1
                    continue
                if cents <= 0 or cents > MAX_PRICE_CENTS:
                    product_identity_bridge_stats["skip_bad_cents"] += 1
                    continue
                gate_row = {
                    "canonical_normalized": (row.get("product_identity") or description).strip(),
                    "name": name,
                }
                price_reason = _package_price_reason(gate_row, key, grams, cents)
                if price_reason:
                    product_identity_bridge_stats["skip_price_gate"] += 1
                    gate_reasons[price_reason] += 1
                    continue
                item = by_key_size.setdefault(
                    (key, grams),
                    {
                        "key": key,
                        "description": description,
                        "grams": grams,
                        "walmart_price_cents": None,
                        "kroger_price_cents": None,
                        "samples": [],
                        "source": "product_identity_bridge",
                    },
                )
                price_col = f"{source}_price_cents"
                item[price_col] = cents if item[price_col] is None else min(item[price_col], cents)
                if item["source"] == "calculator_native_retail_bridge":
                    item["source"] = "calculator_native_retail_bridge+product_identity_bridge"
                if len(item["samples"]) < 6:
                    item["samples"].append(
                        {
                            "source": source,
                            "upc": (row.get("upc") or "").strip(),
                            "name": name,
                            "canonical_surface": (row.get("product_identity") or "").strip(),
                            "canonical_shopping_item": (row.get("product_identity") or "").strip(),
                            "search_term": (row.get("search_terms") or "").strip(),
                            "cents": cents,
                            "gate_reason": (row.get("classification_reason") or "product_identity_bridge").strip(),
                        }
                    )
                product_identity_bridge_stats["accepted"] += 1
                product_identity_bridge_stats[f"accepted:{key}"] += 1

    for manual in MANUAL_PACKAGE_ROWS:
        item = by_key_size.setdefault(
            (manual["key"], manual["grams"]),
            {
                "key": manual["key"],
                "description": manual["description"],
                "grams": manual["grams"],
                "walmart_price_cents": manual.get("walmart_price_cents"),
                "kroger_price_cents": manual.get("kroger_price_cents"),
                "samples": [],
                "source": manual.get("source") or "manual_calculator_native_package_seed",
            },
        )
        if item["walmart_price_cents"] is None:
            item["walmart_price_cents"] = manual.get("walmart_price_cents")
        if item["kroger_price_cents"] is None:
            item["kroger_price_cents"] = manual.get("kroger_price_cents")
        item["source"] = manual.get("source") or item["source"]
        for sample in manual.get("samples", []):
            if len(item["samples"]) < 6:
                item["samples"].append(sample)

    for item in by_key_size.values():
        conn.execute(
            """
            INSERT INTO packages (
                fndds_code, food_description, package_weight_grams, package_size_display,
                product_count, is_plu, walmart_price_cents, kroger_price_cents,
                product_meta, confidence_tier, source
            )
            VALUES (?, ?, ?, ?, 1, 0, ?, ?, ?, 1, ?)
            """,
            (
                item["key"],
                item["description"],
                item["grams"],
                f"{item['grams']:g}g",
                item["walmart_price_cents"],
                item["kroger_price_cents"],
                json.dumps({"calculator_native_samples": item["samples"]}, sort_keys=True),
                item["source"],
            ),
        )
    conn.commit()
    row_count, key_count = conn.execute("SELECT COUNT(*), COUNT(DISTINCT fndds_code) FROM packages").fetchone()
    conn.close()
    tmp.replace(out_db)

    summary = {
        "bridge_csv": str(bridge_csv),
        "out_db": str(out_db),
        "identity_version": IDENTITY_VERSION,
        "allow_sr28_fallback": allow_sr28_fallback,
        "allow_fndds_fallback": allow_fndds_fallback,
        "max_per_key_store": max_per_key_store,
        "coverage_seed_stats": dict(coverage_seed_stats),
        "product_identity_bridge_csv": str(product_identity_bridge_csv) if product_identity_bridge_csv else "",
        "product_identity_bridge_stats": dict(product_identity_bridge_stats),
        "stats": dict(stats),
        "top_gate_reasons": gate_reasons.most_common(50),
        "candidates_after_cap": len(limited),
        "package_rows": int(row_count),
        "ingredient_keys": int(key_count),
    }
    out_summary.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build ESHA-first Hestia recipe/package artifacts from the calculator.")
    parser.add_argument("--recipes-csv", type=Path, default=DEFAULT_RECIPES_CSV)
    parser.add_argument("--bridge-csv", type=Path, default=DEFAULT_RETAIL_BRIDGE_CSV)
    parser.add_argument("--out-recipes-csv", type=Path, default=DEFAULT_OUT_RECIPES_CSV)
    parser.add_argument("--out-recipes-summary", type=Path, default=DEFAULT_OUT_RECIPES_SUMMARY)
    parser.add_argument("--out-package-db", type=Path, default=DEFAULT_OUT_PACKAGE_DB)
    parser.add_argument("--out-package-summary", type=Path, default=DEFAULT_OUT_PACKAGE_SUMMARY)
    parser.add_argument("--out-ingredient-meta", type=Path, default=DEFAULT_OUT_INGREDIENT_META)
    parser.add_argument("--product-identity-bridge-csv", type=Path, default=DEFAULT_PRODUCT_IDENTITY_BRIDGE_CSV)
    parser.add_argument("--limit-recipes", type=int, default=0)
    parser.add_argument("--recipe-id", action="append", dest="recipe_ids", default=[])
    parser.add_argument("--strict-esha-only", action="store_true", help="Do not fall back to SR28 keys when ESHA is missing or gated.")
    parser.add_argument("--allow-fndds-fallback", action="store_true", help="Last-resort FNDDS:<code> keys. Off by default.")
    parser.add_argument("--include-line-json", action="store_true", help="Embed every line resolution in the output CSV. Large on full corpus.")
    parser.add_argument("--max-per-key-store", type=int, default=12)
    parser.add_argument("--skip-recipes", action="store_true")
    parser.add_argument("--skip-packages", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    allow_sr28 = not args.strict_esha_only
    summaries: dict[str, Any] = {}
    if not args.skip_recipes:
        summaries["recipes"] = build_recipes(
            recipes_csv=args.recipes_csv.expanduser(),
            out_csv=args.out_recipes_csv.expanduser(),
            out_summary=args.out_recipes_summary.expanduser(),
            out_ingredient_meta=args.out_ingredient_meta.expanduser(),
            limit_recipes=args.limit_recipes,
            recipe_ids=set(args.recipe_ids),
            allow_sr28_fallback=allow_sr28,
            allow_fndds_fallback=args.allow_fndds_fallback,
            include_line_json=args.include_line_json,
        )
    if not args.skip_packages:
        summaries["packages"] = build_package_db(
            bridge_csv=args.bridge_csv.expanduser(),
            out_db=args.out_package_db.expanduser(),
            out_summary=args.out_package_summary.expanduser(),
            product_identity_bridge_csv=args.product_identity_bridge_csv.expanduser(),
            allow_sr28_fallback=allow_sr28,
            allow_fndds_fallback=args.allow_fndds_fallback,
            max_per_key_store=args.max_per_key_store,
        )
    print(json.dumps(summaries, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
