#!/usr/bin/env python3
"""Find real CSV rows that match each v2 diabolical case.

Each case has a synthetic fdc_id (diabolical_v2_*) and a fixture title. We scan
retail_leaf_v2_enriched_v2.csv for a real product that closest matches the
case's intent so the LLM gets ingredient evidence at runtime, just like v1.

Match strategy per case:
  - must: every keyword in title (lowercased) must appear in CSV row title
  - must_not: tokens that disqualify (e.g., 'sandwich' for a chicken-only meat case)
  - bfc_required: any-of substring match on branded_food_category
  - score: prefer rows with rich evidence (ing_full, ing_top5)

Output: retail_mapper/v2/fixture_real_evidence_map_v2.json
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
V2 = REPO / "retail_mapper" / "v2"
CSV_PATH = V2 / "retail_leaf_v2_enriched_v2.csv"
GOLD_PATH = V2 / "llm_taxonomy_diabolical_v2_cases.jsonl"
OUT_PATH = V2 / "fixture_real_evidence_map_v2.json"

csv.field_size_limit(sys.maxsize)


# Per-case match specs — keyed by case name. Authoritative dict; cases not
# listed here will be skipped (will run with fixture-only evidence).
SPECS: dict[str, dict] = {
    # ---- A. Hybrid beverages
    "oat_milk_eggnog": {
        "must": ["oat", "egg"], "any_must": [["nog"], ["eggnog"]],
        "bfc_any": ["plant", "beverage", "milk", "egg nog", "eggnog"],
        "must_not": ["chocolate", "ice cream"],
    },
    "almond_milk_eggnog": {
        "must": ["almond"], "any_must": [["nog"], ["eggnog"]],
        "bfc_any": ["plant", "beverage", "milk", "egg nog", "eggnog"],
        "must_not": ["chocolate", "ice cream"],
    },
    "blueberry_probiotic_seltzer": {
        "must": ["blueberry", "probiotic"],
        "bfc_any": ["water", "beverage", "sparkling"],
        "must_not": ["yogurt", "ice cream", "kefir"],
    },
    "pineapple_turmeric_kombucha": {
        "must": ["kombucha"],
        "any_must": [["pineapple", "turmeric"], ["pineapple"], ["turmeric"]],
        "bfc_any": ["beverage", "kombucha", "functional", "tea"],
        "must_not": [],
    },
    "apple_cider_vinegar_drink_elderberry": {
        "must": ["apple cider vinegar"],
        "bfc_any": ["beverage", "drink", "vinegar", "functional"],
        "must_not": ["jelly", "gummy"],
    },
    "chocolate_oat_milk_cold_brew": {
        "must": ["cold brew"],
        "any_must": [["chocolate", "oat"], ["oat", "milk"], ["chocolate"]],
        "bfc_any": ["coffee", "beverage"],
        "must_not": ["ice cream", "yogurt"],
    },
    "watermelon_mint_coconut_water": {
        "must": ["coconut water"],
        "any_must": [["watermelon"], ["mint"]],
        "bfc_any": ["water", "beverage"],
        "must_not": [],
    },
    "beet_ginger_lemon_shot": {
        "must": ["shot"],
        "any_must": [["beet", "ginger"], ["ginger", "lemon"], ["beet"]],
        "bfc_any": ["beverage", "wellness", "drink", "juice"],
        "must_not": ["espresso", "coffee shot"],
    },
    "mushroom_adaptogen_latte_dry_mix": {
        "must": ["mushroom"],
        "any_must": [["latte", "mix"], ["powder"], ["adaptogen"]],
        "bfc_any": ["coffee", "powder", "mix", "beverage"],
        "must_not": ["soup", "broth"],
    },
    "crystal_light_lemonade_dry_mix": {
        "must": ["crystal light", "lemonade"],
        "bfc_any": ["mix", "drink mix", "beverage"],
        "must_not": ["liquid"],
    },
    "hot_cocoa_dry_mix": {
        "must": ["hot cocoa", "mix"],
        "bfc_any": ["mix", "cocoa", "beverage", "powder"],
        "must_not": [],
    },
    "gatorade_powder": {
        "must": ["gatorade", "powder"],
        "bfc_any": ["sport", "beverage", "drink", "mix", "powder"],
        "must_not": ["bottle"],
    },
    "kefir_strawberry_probiotic": {
        "must": ["kefir", "strawberry"],
        "bfc_any": ["yogurt", "kefir", "dairy"],
        "must_not": [],
    },
    "matcha_protein_shake": {
        "must": ["matcha"],
        "any_must": [["protein"]],
        "bfc_any": ["beverage", "protein", "drink"],
        "must_not": ["powder", "tea bag", "ice cream"],
    },

    # ---- B. Chocolate ambiguity
    "hersheys_milk_chocolate_bar": {
        "must": ["milk chocolate"],
        "any_must": [["bar"], ["candy bar"]],
        "bfc_any": ["chocolate", "candy", "confection"],
        "must_not": ["milk drink", "milk beverage", "almondmilk", "oatmilk"],
    },
    "nesquik_chocolate_milk_powder": {
        "must": ["chocolate", "powder"],
        "any_must": [["nesquik"], ["chocolate milk"]],
        "bfc_any": ["mix", "beverage", "powder", "cocoa"],
        "must_not": [],
    },
    "hersheys_chocolate_milk_rtd": {
        "must": ["chocolate milk"],
        "any_must": [["2%"], ["whole"], ["1%"], ["lowfat"], ["low fat"]],
        "bfc_any": ["milk", "flavored milk", "dairy"],
        "must_not": ["powder", "mix", "ice cream"],
    },
    "dark_chocolate_almond_milk": {
        "must": ["almond"],
        "any_must": [["dark chocolate"], ["chocolate"]],
        "bfc_any": ["milk", "plant", "beverage"],
        "must_not": ["bar", "ice cream"],
    },
    "ghirardelli_dark_chocolate_squares": {
        "must": ["dark chocolate"],
        "any_must": [["squares"], ["square"]],
        "bfc_any": ["chocolate", "candy", "confection"],
        "must_not": ["milk", "drink", "ice cream"],
    },
    "white_chocolate_macadamia_cookies": {
        "must": ["white chocolate", "macadamia"],
        "any_must": [["cookies"], ["cookie"]],
        "bfc_any": ["cookie", "biscuit"],
        "must_not": [],
    },

    # ---- C. Pizza
    "cauliflower_crust_pepperoni_pizza": {
        "must": ["cauliflower", "pepperoni", "pizza"],
        "bfc_any": ["pizza"],
        "must_not": [],
    },
    "thin_crust_four_cheese_pizza": {
        "must": ["thin", "cheese", "pizza"],
        "any_must": [["four cheese"], ["4 cheese"], ["five cheese"]],
        "bfc_any": ["pizza"],
        "must_not": [],
    },
    "stuffed_crust_supreme_pizza": {
        "must": ["stuffed", "pizza"],
        "any_must": [["supreme"]],
        "bfc_any": ["pizza"],
        "must_not": [],
    },
    "gluten_free_margherita_pizza": {
        "must": ["gluten free", "pizza"],
        "any_must": [["margherita"]],
        "bfc_any": ["pizza"],
        "must_not": [],
    },
    "detroit_style_deep_dish_pepperoni_pizza": {
        "must": ["pizza", "pepperoni"],
        "any_must": [["detroit"], ["deep dish"]],
        "bfc_any": ["pizza"],
        "must_not": [],
    },
    "french_bread_pepperoni_pizza": {
        "must": ["french bread", "pizza"],
        "any_must": [["pepperoni"]],
        "bfc_any": ["pizza"],
        "must_not": [],
    },
    "cauliflower_crust_bbq_chicken_pizza": {
        "must": ["cauliflower", "pizza"],
        "any_must": [["bbq chicken"], ["barbecue chicken"]],
        "bfc_any": ["pizza"],
        "must_not": [],
    },
    "personal_pepperoni_pizza": {
        "must": ["pepperoni", "pizza"],
        "any_must": [["personal"], ["mini"], ["small"]],
        "bfc_any": ["pizza"],
        "must_not": [],
    },
    "hot_pocket_pepperoni": {
        "must": ["pepperoni"],
        "any_must": [["hot pocket"], ["pizza pocket"], ["stuffed sandwich"]],
        "bfc_any": ["frozen", "sandwich", "pizza pocket"],
        "must_not": [],
    },
    "frozen_garlic_bread_pizza": {
        "must": ["garlic bread"],
        "any_must": [["pizza"]],
        "bfc_any": ["pizza", "frozen"],
        "must_not": [],
    },

    # ---- D. Compound meals
    "newmans_skillet_meal_chicken_alfredo": {
        "must": ["skillet"],
        "any_must": [["chicken", "fettuccini"], ["chicken", "alfredo"]],
        "bfc_any": ["frozen", "dinner", "entree", "skillet"],
        "must_not": [],
    },
    "banquet_meatloaf_mashed_potatoes_dinner": {
        "must": ["meatloaf"],
        "any_must": [["mashed"], ["dinner"]],
        "bfc_any": ["frozen", "dinner", "entree"],
        "must_not": ["sandwich"],
    },
    "stouffers_lasagna_meat_sauce": {
        "must": ["lasagna"],
        "any_must": [["meat sauce"], ["meat"]],
        "bfc_any": ["frozen", "dinner", "entree", "pasta"],
        "must_not": ["roll", "soup"],
    },
    "marie_callenders_chicken_pot_pie": {
        "must": ["pot pie", "chicken"],
        "bfc_any": ["frozen", "dinner", "entree", "pot pie"],
        "must_not": [],
    },
    "hungryman_salisbury_steak_dinner": {
        "must": ["salisbury", "steak"],
        "any_must": [["dinner"]],
        "bfc_any": ["frozen", "dinner", "entree"],
        "must_not": [],
    },
    "lean_cuisine_garlic_beef": {
        "must": ["beef"],
        "any_must": [["garlic", "beef"], ["broccoli", "beef"]],
        "bfc_any": ["frozen", "dinner", "entree"],
        "must_not": ["sandwich", "soup", "kit"],
    },
    "amy_mac_and_cheese_bowl": {
        "must": ["mac", "cheese"],
        "any_must": [["bowl"], ["amy"]],
        "bfc_any": ["frozen", "dinner", "entree", "macaroni"],
        "must_not": [],
    },
    "kids_meal_mac_cheese_nuggets_apples": {
        "must": ["nuggets"],
        "any_must": [["mac", "cheese"], ["apples"]],
        "bfc_any": ["frozen", "kids", "kid", "dinner", "entree"],
        "must_not": [],
    },
    "pf_changs_beef_with_broccoli_frozen": {
        "must": ["beef", "broccoli"],
        "bfc_any": ["frozen", "dinner", "entree", "asian"],
        "must_not": ["soup"],
    },
    "stouffers_french_bread_pizza_pepperoni": {
        "must": ["french bread", "pizza", "pepperoni"],
        "bfc_any": ["pizza", "frozen"],
        "must_not": [],
    },

    # ---- E. Trail mix
    "tropical_trail_mix": {
        "must": ["trail mix"],
        "any_must": [["tropical"], ["mango"], ["pineapple"]],
        "bfc_any": ["trail", "snack", "nuts"],
        "must_not": [],
    },
    "energy_trail_mix_pb_raisin_mm": {
        "must": ["trail mix"],
        "any_must": [["energy"], ["m&m"], ["peanut", "raisin"]],
        "bfc_any": ["trail", "snack", "nuts"],
        "must_not": [],
    },
    "mixed_nuts_no_peanuts": {
        "must": ["mixed nuts"],
        "must_not": ["peanut"],
        "bfc_any": ["nut", "snack"],
    },
    "sweet_and_salty_trail_mix": {
        "must": ["trail mix"],
        "any_must": [["sweet and salty"], ["sweet & salty"]],
        "bfc_any": ["trail", "snack", "nuts"],
        "must_not": [],
    },
    "fruit_and_nut_mix": {
        "must": ["fruit", "nut"],
        "any_must": [["mix"], ["medley"]],
        "bfc_any": ["trail", "snack", "nut", "dried fruit"],
        "must_not": ["bar"],
    },

    # ---- F. Meat
    "boneless_skinless_chicken_breast": {
        "must": ["boneless", "chicken breast"],
        "any_must": [["skinless"]],
        "bfc_any": ["poultry", "chicken"],
        "must_not": ["nugget", "tender", "patty", "sausage", "marinated"],
    },
    "bone_in_pork_chops": {
        "must": ["pork", "chops"],
        "any_must": [["bone-in"], ["bone in"]],
        "bfc_any": ["pork", "meat"],
        "must_not": [],
    },
    "ground_beef_80_20": {
        "must": ["ground beef"],
        "any_must": [["80/20"], ["80%"]],
        "bfc_any": ["beef", "meat", "ground"],
        "must_not": [],
    },
    "ground_turkey_93_7": {
        "must": ["ground turkey"],
        "any_must": [["93/7"], ["93%"]],
        "bfc_any": ["poultry", "turkey", "ground"],
        "must_not": [],
    },
    "boneless_pork_ribs": {
        "must": ["pork", "ribs"],
        "any_must": [["country style"], ["country-style"], ["boneless"]],
        "bfc_any": ["pork", "meat"],
        "must_not": ["sauce"],
    },
    "skirt_steak": {
        "must": ["skirt steak"],
        "bfc_any": ["beef", "meat"],
        "must_not": ["seasoned", "marinated", "carne asada"],
    },
    "filet_mignon_beef_tenderloin": {
        "must": ["filet mignon"],
        "any_must": [["tenderloin"], ["beef"]],
        "bfc_any": ["beef", "meat"],
        "must_not": [],
    },
    "whole_chicken": {
        "must": ["whole chicken"],
        "bfc_any": ["poultry", "chicken"],
        "must_not": ["soup", "broth", "rotisserie", "seasoned"],
    },
    "chicken_thighs_bone_in_skin_on": {
        "must": ["chicken thighs"],
        "any_must": [["bone-in"], ["bone in"], ["skin-on"], ["skin on"]],
        "bfc_any": ["poultry", "chicken"],
        "must_not": [],
    },
    "ribeye_steak": {
        "must": ["ribeye"],
        "any_must": [["steak"]],
        "bfc_any": ["beef", "meat"],
        "must_not": [],
    },

    # ---- G. Flavored milks
    "strawberry_whole_milk": {
        "must": ["strawberry"],
        "any_must": [["whole milk"], ["milk"]],
        "bfc_any": ["milk", "flavored", "dairy"],
        "must_not": ["yogurt", "ice cream", "kefir", "shake"],
    },
    "vanilla_lowfat_milk": {
        "must": ["vanilla"],
        "any_must": [["1%"], ["low fat"], ["lowfat"]],
        "bfc_any": ["milk", "flavored", "dairy"],
        "must_not": ["yogurt", "ice cream", "kefir", "shake"],
    },
    "banana_milk": {
        "must": ["banana"],
        "any_must": [["milk"]],
        "bfc_any": ["milk", "flavored", "dairy"],
        "must_not": ["yogurt", "ice cream", "shake", "smoothie", "bread"],
    },
    "cookies_and_cream_chocolate_milk": {
        "must": ["chocolate milk"],
        "any_must": [["cookies"]],
        "bfc_any": ["milk", "flavored", "dairy"],
        "must_not": ["powder", "mix", "ice cream"],
    },
    "vanilla_oat_milk": {
        "must": ["vanilla", "oat"],
        "any_must": [["milk"]],
        "bfc_any": ["plant", "beverage", "milk"],
        "must_not": ["bar", "yogurt", "ice cream"],
    },

    # ---- H. Vegetables
    "frozen_broccoli_florets_plain": {
        "must": ["broccoli"],
        "any_must": [["florets"]],
        "bfc_any": ["frozen vegetable", "vegetable"],
        "must_not": ["sauce", "cheese", "seasoned", "mix", "soup"],
    },
    "fresh_broccoli_crowns": {
        "must": ["broccoli"],
        "any_must": [["crowns"]],
        "bfc_any": ["produce", "vegetable", "fresh"],
        "must_not": ["frozen", "canned", "sauce"],
    },
    "canned_green_beans_plain": {
        "must": ["green beans"],
        "any_must": [["cut"], ["whole"], ["french"]],
        "bfc_any": ["canned vegetable", "vegetable"],
        "must_not": ["seasoned", "bacon", "sauce", "soup"],
    },
    "seasoned_green_beans_canned": {
        "must": ["green beans"],
        "any_must": [["seasoned"], ["bacon"], ["southern"]],
        "bfc_any": ["canned vegetable", "vegetable"],
        "must_not": [],
    },
    "italian_style_frozen_veggies": {
        "must": ["italian"],
        "any_must": [["vegetable"], ["veggies"], ["blend"]],
        "bfc_any": ["frozen vegetable", "vegetable"],
        "must_not": ["pasta", "lasagna", "ravioli"],
    },
    "steamfresh_broccoli_cheese_sauce": {
        "must": ["broccoli", "cheese"],
        "any_must": [["sauce"], ["steamfresh"]],
        "bfc_any": ["frozen vegetable", "vegetable"],
        "must_not": [],
    },
    "canned_diced_tomatoes_italian_seasoning": {
        "must": ["diced tomatoes"],
        "any_must": [["italian"], ["seasoning"], ["herb"]],
        "bfc_any": ["canned vegetable", "tomato"],
        "must_not": [],
    },
    "frozen_peas_plain": {
        "must": ["peas"],
        "any_must": [["frozen"], ["green peas"]],
        "bfc_any": ["frozen vegetable", "vegetable"],
        "must_not": ["soup", "sauce", "cheese"],
    },
    "fresh_baby_carrots": {
        "must": ["baby carrots"],
        "bfc_any": ["produce", "vegetable", "fresh"],
        "must_not": ["frozen", "canned", "sauce"],
    },
    "frozen_seasoned_potatoes": {
        "must": ["potatoes"],
        "any_must": [["seasoned"], ["diced"]],
        "bfc_any": ["frozen vegetable", "vegetable", "potato"],
        "must_not": ["mash", "sweet potato"],
    },

    # ---- I. Candy
    "skittles_original_assorted": {
        "must": ["skittles"],
        "bfc_any": ["candy", "non chocolate"],
        "must_not": [],
    },
    "starburst_original_4flavor": {
        "must": ["starburst"],
        "bfc_any": ["candy", "non chocolate"],
        "must_not": [],
    },
    "sour_patch_kids_assorted": {
        "must": ["sour patch"],
        "bfc_any": ["candy", "non chocolate"],
        "must_not": [],
    },
    "lifesavers_5flavor": {
        "must": ["life savers"],
        "any_must": [["5 flavor"], ["five flavor"]],
        "bfc_any": ["candy", "non chocolate"],
        "must_not": [],
    },
    "jelly_belly_50_flavors": {
        "must": ["jelly belly"],
        "bfc_any": ["candy", "non chocolate"],
        "must_not": [],
    },
    "mm_peanut_chocolate": {
        "must": ["m&m"],
        "any_must": [["peanut"]],
        "bfc_any": ["candy", "chocolate"],
        "must_not": [],
    },

    # ---- J. Spices
    "montreal_steak_seasoning": {
        "must": ["montreal", "steak"],
        "any_must": [["seasoning"], ["spice"]],
        "bfc_any": ["seasoning", "spice"],
        "must_not": [],
    },
    "salt_and_pepper_combo": {
        "must": ["salt", "pepper"],
        "any_must": [["grinder"], ["combo"], ["set"]],
        "bfc_any": ["salt", "pepper", "spice", "seasoning"],
        "must_not": ["roll", "popcorn", "chip"],
    },
    "taco_seasoning_mix": {
        "must": ["taco", "seasoning"],
        "any_must": [["mix"]],
        "bfc_any": ["seasoning", "spice"],
        "must_not": [],
    },
    "italian_herb_blend": {
        "must": ["italian"],
        "any_must": [["herb"], ["seasoning"], ["blend"]],
        "bfc_any": ["seasoning", "spice", "herb"],
        "must_not": ["dressing", "sauce", "pasta"],
    },
    "lemon_pepper_seasoning": {
        "must": ["lemon pepper"],
        "any_must": [["seasoning"]],
        "bfc_any": ["seasoning", "spice"],
        "must_not": [],
    },
    "memphis_bbq_rub": {
        "must": ["bbq"],
        "any_must": [["rub"]],
        "bfc_any": ["seasoning", "spice", "rub"],
        "must_not": ["sauce"],
    },
    "cajun_blackening_seasoning": {
        "must": ["cajun"],
        "any_must": [["blackening"], ["seasoning"]],
        "bfc_any": ["seasoning", "spice"],
        "must_not": [],
    },
    "pumpkin_pie_spice": {
        "must": ["pumpkin pie spice"],
        "bfc_any": ["seasoning", "spice"],
        "must_not": [],
    },
    "curry_powder": {
        "must": ["curry"],
        "any_must": [["powder"]],
        "bfc_any": ["seasoning", "spice"],
        "must_not": ["sauce", "soup"],
    },
    "chicken_seasoning": {
        "must": ["chicken seasoning"],
        "bfc_any": ["seasoning", "spice"],
        "must_not": ["broth", "soup", "sauce"],
    },

    # ---- K. Ice cream
    "ben_jerry_chunky_monkey": {
        "must": ["chunky monkey"],
        "bfc_any": ["ice cream", "frozen"],
        "must_not": [],
    },
    "ben_jerry_cherry_garcia": {
        "must": ["cherry garcia"],
        "bfc_any": ["ice cream", "frozen"],
        "must_not": [],
    },
    "ben_jerry_half_baked": {
        "must": ["half baked"],
        "bfc_any": ["ice cream", "frozen"],
        "must_not": [],
    },
    "haagen_dazs_vanilla_swiss_almond": {
        "must": ["vanilla swiss almond"],
        "bfc_any": ["ice cream", "frozen"],
        "must_not": [],
    },
    "talenti_sea_salt_caramel_gelato": {
        "must": ["sea salt caramel"],
        "any_must": [["gelato"]],
        "bfc_any": ["ice cream", "gelato", "frozen"],
        "must_not": [],
    },
    "vanilla_ice_cream_plain": {
        "must": ["vanilla", "ice cream"],
        "bfc_any": ["ice cream", "frozen"],
        "must_not": ["chocolate", "strawberry", "swirl", "fudge"],
    },

    # ---- L. Condiments
    "horseradish_aioli_sauce": {
        "must": ["horseradish", "aioli"],
        "bfc_any": ["sauce", "condiment", "dressing"],
        "must_not": [],
    },
    "sriracha_mayo": {
        "must": ["sriracha"],
        "any_must": [["mayo"], ["mayonnaise"]],
        "bfc_any": ["sauce", "condiment", "mayo"],
        "must_not": [],
    },
    "honey_mustard_dressing": {
        "must": ["honey mustard"],
        "any_must": [["dressing"]],
        "bfc_any": ["dressing", "salad"],
        "must_not": [],
    },
    "chipotle_ranch_dressing": {
        "must": ["chipotle"],
        "any_must": [["ranch"]],
        "bfc_any": ["dressing", "salad"],
        "must_not": [],
    },
    "garlic_herb_butter": {
        "must": ["garlic"],
        "any_must": [["herb"], ["butter"]],
        "bfc_any": ["butter", "dairy"],
        "must_not": ["margarine", "spread"],
    },

    # ---- M. Breads
    "12_grain_bread": {
        "must": ["12 grain"],
        "any_must": [["bread"]],
        "bfc_any": ["bread", "bakery"],
        "must_not": [],
    },
    "15_grain_bread": {
        "must": ["15 grain"],
        "any_must": [["bread"]],
        "bfc_any": ["bread", "bakery"],
        "must_not": [],
    },
    "whole_wheat_sourdough": {
        "must": ["whole wheat", "sourdough"],
        "bfc_any": ["bread", "bakery"],
        "must_not": [],
    },
    "multi_seed_sandwich_bread": {
        "must": ["bread"],
        "any_must": [["multi seed"], ["multi-seed"], ["seeded"]],
        "bfc_any": ["bread", "bakery"],
        "must_not": [],
    },
    "sprouted_grain_bread": {
        "must": ["sprouted"],
        "any_must": [["grain"], ["bread"]],
        "bfc_any": ["bread", "bakery"],
        "must_not": [],
    },
    "ezekiel_4_9_sprouted_bread": {
        "must": ["ezekiel"],
        "bfc_any": ["bread", "bakery"],
        "must_not": [],
    },

    # ---- N. Fruit leather
    "sweet_potato_apple_spice_strips": {
        "must": ["sweet potato", "apple"],
        "any_must": [["strips"]],
        "bfc_any": ["snack", "fruit", "wholesome"],
        "must_not": [],
    },
    "fruit_leather_strawberry": {
        "must": ["fruit leather", "strawberry"],
        "bfc_any": ["snack", "fruit"],
        "must_not": [],
    },
    "freeze_dried_apple_chips": {
        "must": ["freeze", "apple"],
        "any_must": [["chips"]],
        "bfc_any": ["snack", "fruit", "dried"],
        "must_not": [],
    },
    "veggie_straws": {
        "must": ["veggie straws"],
        "bfc_any": ["snack", "chip"],
        "must_not": [],
    },

    # ---- O. Snack pack combos
    "peeled_apples_butterscotch_dip": {
        "must": ["peeled", "apples", "butterscotch"],
        "bfc_any": ["fruit", "produce", "snack"],
        "must_not": [],
    },
    "apples_caramel_snack_pack": {
        "must": ["apple", "caramel"],
        "any_must": [["dip"], ["snack"]],
        "bfc_any": ["fruit", "produce", "snack"],
        "must_not": [],
    },
    "cheese_crackers_snack_pack": {
        "must": ["cheese", "cracker"],
        "any_must": [["snack pack"], ["pack"]],
        "bfc_any": ["snack", "cracker", "cheese"],
        "must_not": [],
    },
    "lunchable_pizza": {
        "must": ["lunchables"],
        "any_must": [["pizza"]],
        "bfc_any": ["lunch kit", "lunch", "kit", "refrigerated"],
        "must_not": [],
    },

    # ---- P. Apple-named non-fruit
    "culinary_crisps_apple_oat_crunch": {
        "must": ["culinary crisps"],
        "any_must": [["apple"]],
        "bfc_any": ["cracker", "biscotti", "snack"],
        "must_not": [],
    },
    "apple_pie_filling_canned": {
        "must": ["apple", "pie filling"],
        "bfc_any": ["pie filling", "baking"],
        "must_not": [],
    },
    "apple_butter": {
        "must": ["apple butter"],
        "bfc_any": ["jam", "jelly", "spread", "preserve"],
        "must_not": [],
    },
    "apple_juice_concentrate": {
        "must": ["apple", "concentrate"],
        "bfc_any": ["juice", "frozen", "beverage"],
        "must_not": [],
    },
    "applesauce_unsweetened": {
        "must": ["applesauce"],
        "any_must": [["unsweetened"]],
        "bfc_any": ["applesauce", "fruit"],
        "must_not": [],
    },

    # ---- Q. Cakes vs cupcakes
    "vanilla_cupcakes_six_pack": {
        "must": ["vanilla", "cupcake"],
        "bfc_any": ["cake", "cupcake", "bakery"],
        "must_not": [],
    },
    "chocolate_cupcakes_buttercream": {
        "must": ["chocolate", "cupcake"],
        "bfc_any": ["cake", "cupcake", "bakery"],
        "must_not": [],
    },
    "sour_cream_pound_cake": {
        "must": ["sour"],
        "any_must": [["pound cake"], ["cake"]],
        "bfc_any": ["cake", "bakery"],
        "must_not": [],
    },
    "chocolate_layer_cake": {
        "must": ["chocolate"],
        "any_must": [["layer cake"]],
        "bfc_any": ["cake", "bakery"],
        "must_not": [],
    },
    "carrot_cake_with_cream_cheese_frosting": {
        "must": ["carrot cake"],
        "any_must": [["cream cheese"]],
        "bfc_any": ["cake", "bakery"],
        "must_not": [],
    },
    "snack_cake_oatmeal_creme_pie": {
        "must": ["oatmeal"],
        "any_must": [["creme pie"], ["pie"]],
        "bfc_any": ["snack cake", "cake"],
        "must_not": [],
    },
    "angel_food_cake": {
        "must": ["angel food"],
        "bfc_any": ["cake", "bakery"],
        "must_not": [],
    },
    "muffins_blueberry": {
        "must": ["blueberry", "muffin"],
        "bfc_any": ["muffin", "bakery"],
        "must_not": ["mix", "bread"],
    },
}


def normalize_specs(specs: dict[str, dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for name, spec in specs.items():
        out[name] = {
            "must": [k.lower() for k in spec.get("must", [])],
            "must_not": [k.lower() for k in spec.get("must_not", [])],
            "any_must": [[k.lower() for k in g] for g in spec.get("any_must", [])],
            "bfc_any": [k.lower() for k in spec.get("bfc_any", [])],
        }
    return out


def score_row(spec: dict, title: str, bfc: str, has_ing_full: bool, has_ing_top5: bool) -> int | None:
    if not all(kw in title for kw in spec["must"]):
        return None
    if spec["any_must"] and not any(all(kw in title for kw in g) for g in spec["any_must"]):
        return None
    if any(bad in title for bad in spec["must_not"]):
        return None
    if spec["bfc_any"] and not any(b in bfc for b in spec["bfc_any"]):
        return None
    score = 10
    score -= len(title) // 50
    if has_ing_full:
        score += 4
    if has_ing_top5:
        score += 2
    return score


def main() -> None:
    cases = [json.loads(l) for l in GOLD_PATH.open(encoding="utf-8")]
    case_to_fixture_fdc = {c["name"]: c["source"]["fdc_id"] for c in cases}
    norm_specs = normalize_specs(SPECS)
    best: dict[str, dict] = {name: {"score": -1, "row": None} for name in norm_specs}

    print(f"single-pass CSV scan, {len(norm_specs)} specs to match...")
    rows_scanned = 0
    with CSV_PATH.open(encoding="utf-8", errors="replace", newline="") as fh:
        for row in csv.DictReader(fh):
            title = (row.get("title") or "").lower()
            if not title:
                continue
            bfc = (row.get("branded_food_category") or "").lower()
            has_ing_full = bool(row.get("ing_full"))
            has_ing_top5 = bool(row.get("ing_top5"))
            for name, spec in norm_specs.items():
                s = score_row(spec, title, bfc, has_ing_full, has_ing_top5)
                if s is None:
                    continue
                if s > best[name]["score"]:
                    best[name] = {
                        "score": s,
                        "row": {
                            "fdc_id": row.get("fdc_id"),
                            "title": row.get("title"),
                            "bfc": row.get("branded_food_category"),
                        },
                    }
            rows_scanned += 1
            if rows_scanned % 100000 == 0:
                got = sum(1 for v in best.values() if v["row"])
                print(f"  scanned {rows_scanned:>8d} rows  matched {got}/{len(norm_specs)}")

    out: dict[str, str] = {}
    misses: list[str] = []
    for name in [c["name"] for c in cases]:
        spec = norm_specs.get(name)
        if not spec:
            misses.append(name + "  (no spec)")
            continue
        b = best.get(name, {})
        row = b.get("row")
        if row and row["fdc_id"]:
            fixture_fdc = case_to_fixture_fdc[name]
            out[fixture_fdc] = row["fdc_id"]
            print(f"  MATCH {name:55s} -> fdc {row['fdc_id']:>8s}  {row['title'][:55]}")
        else:
            misses.append(name)

    OUT_PATH.write_text(json.dumps(out, indent=2, sort_keys=True), encoding="utf-8")
    print()
    print(f"matched: {len(out)} / {len(cases)}")
    print(f"misses: {len(misses)}")
    if misses:
        for m in misses:
            print(f"  - {m}")
    print(f"\nwrote {OUT_PATH}")


if __name__ == "__main__":
    main()
