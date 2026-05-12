from __future__ import annotations

import argparse
import csv
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

import build_ingredient_fingerprint_clusters as ingredient_clusters
import build_product_to_best_esha_full_map as full_map
import match_esha_to_products as matcher


ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "implementation" / "output"
DEFAULT_INPUT = OUT_DIR / "product_to_best_esha_full_map.vM.csv"
OUT_REPAIRED = OUT_DIR / "product_to_best_esha_full_map.vM2.csv"
OUT_PROPOSALS = OUT_DIR / "head_remap_proposals.csv"
OUT_NO_VALID = OUT_DIR / "head_remap_no_valid_esha.csv"
OUT_SUMMARY = OUT_DIR / "head_remap_summary.json"

LOW_MARGIN_OK_HEADS = {
    "bacon",
    "bagel",
    "bar",
    "beans",
    "biscuit",
    "candy",
    "candy bar",
    "chips",
    "chocolate",
    "chocolate bar",
    "cone",
    "cookie",
    "cracker",
    "fish",
    "flour",
    "french toast",
    "hummus",
    "ketchup",
    "muffin",
    "mustard",
    "pancakes",
    "pretzels",
    "salsa",
    "shrimp",
    "soda",
    "waffles",
}

SOFT_EXTRA_IDENTITY = {
    "base",
    "chef",
    "citru",
    "citrus",
    "del",
    "dippers",
    "dipping",
    "dry",
    "fs",
    "g",
    "g7082",
    "label",
    "mix",
    "own",
    "powder",
    "ready",
    "refrigerated",
    "serving",
    "soda",
    "use",
}

BROAD_HEADS_NEED_TITLE_OVERLAP = {
    "bread",
    "cereal",
    "dish",
    "drink",
    "juice drink",
    "meal",
    "roll",
    "sauce",
    "smoothie",
    "snack",
    "soup",
}


HEAD_ALIASES = {
    "chips": {"Chips", "Snack"},
    "chip": {"Chips", "Snack"},
    "crisp": {"Chips", "Snack"},
    "crisps": {"Chips", "Snack"},
    "dip": {"Dip"},
    "dips": {"Dip"},
    "dressing": {"Dressing", "Salad Dressing", "Salad Dressing/Dip"},
    "dressings": {"Dressing", "Salad Dressing", "Salad Dressing/Dip"},
    "vinaigrette": {"Salad Dressing"},
    "mayonnaise": {"Dressing"},
    "mayo": {"Dressing"},
    "hummus": {"Hummus", "Dip"},
    "salsa": {"Salsa", "Dip"},
    "sauce": {"Sauce"},
    "ketchup": {"Ketchup", "Sauce"},
    "mustard": {"Mustard", "Sauce"},
    "gravy": {"Gravy", "Sauce"},
    "bar": {"Bar"},
    "bars": {"Bar"},
    "cookie": {"Cookie"},
    "cookies": {"Cookie"},
    "biscuit": {"Biscuit", "Cookie"},
    "biscuits": {"Biscuit", "Cookie"},
    "cracker": {"Cracker"},
    "crackers": {"Cracker"},
    "candy": {"Candy", "Candy Bar"},
    "gum": {"Gum", "Candy"},
    "gummy": {"Candy"},
    "gummi": {"Candy"},
    "truffle": {"Candy", "Chocolate", "Chocolate Bar"},
    "truffles": {"Candy", "Chocolate", "Chocolate Bar"},
    "chocolate": {"Chocolate", "Chocolate Bar", "Candy"},
    "muffin": {"Muffin"},
    "muffins": {"Muffin"},
    "croissant": {"Croissant", "Pastry"},
    "croissants": {"Croissant", "Pastry"},
    "scone": {"Scone"},
    "scones": {"Scone"},
    "strudel": {"Pastry"},
    "fritter": {"Doughnut", "Pastry"},
    "fritters": {"Doughnut", "Pastry"},
    "puff": {"Pastry"},
    "puffs": {"Pastry"},
    "pastry": {"Pastry"},
    "pastries": {"Pastry"},
    "dough": {"Dough"},
    "waffle": {"Waffles"},
    "waffles": {"Waffles"},
    "pancake": {"Pancakes"},
    "pancakes": {"Pancakes"},
    "toast": {"French Toast"},
    "crepe": {"Crepe"},
    "crepes": {"Crepe"},
    "soup": {"Soup"},
    "chili": {"Chili", "Soup"},
    "creamer": {"Cream Substitute"},
    "creamers": {"Cream Substitute"},
    "milk": {"Milk"},
    "buttermilk": {"Milk"},
    "eggnog": {"Eggnog"},
    "juice": {"Juice", "Juice Drink"},
    "drink": {"Drink", "Blended Drink"},
    "smoothie": {"Smoothie"},
    "soda": {"Soda"},
    "coffee": {"Coffee", "Blended Coffee"},
    "tea": {"Tea"},
    "beans": {"Beans"},
    "bean": {"Beans"},
    "burrito": {"Burrito"},
    "wrap": {"Wrap"},
    "taco": {"Taco", "Dish"},
    "filling": {"Dish", "Meal"},
    "pizza": {"Pizza"},
    "quiche": {"Quiche", "Meal", "Pie"},
    "sandwich": {"Sandwich"},
    "meal": {"Meal", "Dish"},
    "dish": {"Dish", "Meal"},
    "entree": {"Dish", "Meal"},
    "entrée": {"Dish", "Meal"},
    "pasta": {"Pasta", "Pasta Dish", "Dumpling"},
    "gnocchi": {"Dumpling", "Pasta", "Pasta Dish"},
    "macaroni": {"Pasta Dish", "Macaroni & Cheese"},
    "cheese": {"Cheese"},
    "yogurt": {"Yogurt"},
    "pudding": {"Pudding"},
    "custard": {"Pudding"},
    "flour": {"Flour"},
    "mix": {"Baking Mix", "Seasoning", "Drink", "Meal"},
    "batter": {"Batter"},
    "fish": {"Fish"},
    "shrimp": {"Shrimp", "Fish"},
    "chicken": {"Chicken", "Dish"},
    "beef": {"Beef", "Dish"},
    "pork": {"Pork", "Dish"},
    "ham": {"Ham", "Lunchmeat", "Pork"},
    "bacon": {"Bacon", "Pork"},
    "pepperoni": {"Sausage", "Lunchmeat"},
    "turkey": {"Turkey", "Lunchmeat"},
    "salad": {"Salad"},
    "topping": {"Topping"},
    "bread": {"Bread"},
    "loaf": {"Bread"},
    "loaves": {"Bread"},
    "bun": {"Bun", "Bread"},
    "roll": {"Roll", "Bread"},
    "syrup": {"Syrup", "Sweetener"},
    "cake": {"Cake"},
    "pie": {"Pie"},
    "cereal": {"Cereal"},
    "oatmeal": {"Cereal"},
    "popcorn": {"Popcorn", "Snack"},
    "pretzel": {"Pretzels"},
    "pretzels": {"Pretzels"},
    "cone": {"Cone"},
    "cones": {"Cone"},
    "fruit": {"Fruit"},
    "jam": {"Jam", "Spread"},
    "jelly": {"Jelly", "Spread"},
    "preserves": {"Preserves", "Jam", "Spread"},
}

CATEGORY_HEADS = {
    "chips": {"Chips", "Snack"},
    "pretzels": {"Pretzels", "Snack"},
    "snacks": {"Snack", "Chips", "Cracker", "Pretzels"},
    "dips & salsa": {"Dip", "Salsa", "Hummus"},
    "salsa": {"Salsa", "Dip"},
    "sauces": {"Sauce", "Dip", "Salsa"},
    "condiments": {"Sauce", "Ketchup", "Mustard", "Dip", "Salsa"},
    "salad dressing": {"Dressing", "Salad Dressing", "Salad Dressing/Dip"},
    "mayonnaise": {"Dressing", "Salad Dressing"},
    "snack, energy & granola bars": {"Bar"},
    "bars": {"Bar"},
    "cookies": {"Cookie", "Biscuit"},
    "biscuits": {"Cookie", "Biscuit", "Cracker"},
    "crackers": {"Cracker"},
    "candy": {"Candy", "Candy Bar", "Chocolate", "Chocolate Bar"},
    "chocolate": {"Chocolate", "Chocolate Bar", "Candy", "Candy Bar"},
    "puddings": {"Pudding"},
    "custards": {"Pudding"},
    "milk additives": {"Cream Substitute"},
    "cream substitutes": {"Cream Substitute"},
    "plant based milk": {"Milk", "Juice Drink", "Drink"},
    "milk": {"Milk", "Eggnog"},
    "fruit & vegetable juice": {"Juice", "Juice Drink", "Smoothie", "Drink"},
    "juice": {"Juice", "Juice Drink", "Smoothie"},
    "soda": {"Soda"},
    "coffee": {"Coffee", "Blended Coffee"},
    "tea": {"Tea"},
    "canned & bottled beans": {"Beans"},
    "vegetable and lentil mixes": {"Beans", "Vegetables"},
    "frozen dinners": {"Dish", "Meal", "Pasta Dish", "Pizza", "Burrito", "Wrap", "Sandwich"},
    "entrees": {"Dish", "Meal", "Pasta Dish", "Pizza", "Burrito", "Wrap", "Sandwich"},
    "prepared meals": {"Dish", "Meal", "Pasta Dish", "Pizza", "Burrito", "Wrap", "Sandwich"},
    "pasta": {"Pasta", "Pasta Dish", "Dumpling", "Macaroni & Cheese"},
    "pizza": {"Pizza"},
    "frozen fish": {"Fish", "Shrimp"},
    "fish & seafood": {"Fish", "Shrimp"},
    "pepperoni": {"Sausage", "Lunchmeat"},
    "salami": {"Sausage", "Lunchmeat"},
    "cold cuts": {"Lunchmeat"},
    "bacon": {"Bacon", "Pork"},
    "sausages": {"Sausage"},
    "flours": {"Flour"},
    "corn meal": {"Flour"},
    "baking": {"Baking Mix", "Flour", "Cake", "Cookie", "Muffin", "Pancakes", "Waffles"},
    "pancakes": {"Pancakes", "Waffles", "French Toast", "Baking Mix"},
    "waffles": {"Waffles", "Pancakes", "Baking Mix"},
    "french toast": {"French Toast"},
    "croissants": {"Croissant", "Muffin", "Pastry", "Sweet Roll", "Doughnut"},
    "muffins": {"Muffin", "Croissant", "Pastry", "Sweet Roll", "Doughnut"},
    "pastries": {"Pastry", "Muffin", "Croissant", "Sweet Roll", "Doughnut"},
    "breads & buns": {"Bread", "Bun", "Roll", "Bagel"},
    "frozen fruit": {"Fruit", "Smoothie", "Juice"},
    "pre-packaged fruit": {"Fruit", "Apple", "Banana", "Salad"},
    "ice cream/i": {"Ice Cream", "Cone"},
    "ice cream": {"Ice Cream", "Cone"},
    "wholesome snacks": {"Fruit", "Bar", "Snack", "Nuts"},
    "seasoning": {"Seasoning", "Spice", "Sauce"},
    "spices": {"Spice", "Seasoning"},
}

REASON_HEADS = {
    "chip_product_without_chip_anchor": {"Chips", "Snack", "Cracker"},
    "dip_product_without_dip_anchor": {"Dip", "Salsa", "Hummus", "Sauce"},
    "bar_anchor_without_bar_product": {"Snack", "Candy", "Chocolate", "Juice Drink", "Soda", "Cereal", "Fruit"},
    "bar_anchor_on_nonbar_mix_product": {"Snack", "Nuts", "Trail Mix"},
    "energy_bar_anchor_without_energy_bar_product": {"Candy", "Chocolate", "Bar"},
    "cookie_product_without_cookie_anchor": {"Cookie", "Biscuit", "Cracker"},
    "single_fruit_anchor_on_mixed_fruit_product": {"Fruit", "Salad", "Smoothie", "Juice", "Juice Drink"},
    "candy_product_without_candy_anchor": {"Candy", "Candy Bar", "Chocolate", "Chocolate Bar", "Gum"},
    "muffin_product_without_muffin_anchor": {"Muffin", "Croissant", "Pastry", "Sweet Roll", "Doughnut"},
    "prepared_meal_product_to_component_anchor": {"Dish", "Meal", "Pasta Dish", "Pizza", "Burrito", "Wrap", "Sandwich"},
    "dough_product_without_dough_anchor": {"Pasta Dish", "Pasta", "Macaroni & Cheese", "Dough"},
    "soup_product_without_soup_anchor": {"Soup", "Chili"},
    "salsa_product_without_salsa_anchor": {"Salsa", "Dip", "Snack"},
    "creamer_product_without_creamer_anchor": {"Cream Substitute", "Coffee", "Drink"},
    "waffle_product_without_waffle_anchor": {"Waffles", "Pancakes", "Baking Mix"},
    "truffle_product_without_truffle_anchor": {"Candy", "Chocolate", "Chocolate Bar", "Candy Bar"},
    "custard_product_without_custard_anchor": {"Pudding", "Yogurt"},
    "pancake_product_without_pancake_anchor": {"Pancakes", "Waffles", "Baking Mix"},
    "bagel_anchor_without_bagel_product": {"Bread", "Bun", "Roll", "Cracker", "Pastry"},
    "pastry_product_without_pastry_anchor": {"Pastry", "Muffin", "Croissant", "Sweet Roll", "Doughnut"},
    "milk_product_without_milk_anchor": {"Milk", "Eggnog", "Cream Substitute", "Drink"},
    "plant_milk_anchor_on_non_milk_product": {"Candy", "Chocolate", "Pudding", "Cream Substitute", "Drink"},
    "puff_product_without_puff_anchor": {"Pastry", "Snack"},
    "flour_product_without_flour_anchor": {"Flour"},
    "beans_anchor_subtype_mismatch": {"Beans"},
    "bean_product_without_bean_anchor": {"Fruit", "Apple", "Beans"},
    "baking_chips_anchor_without_baking_chip_product": {"Cream Substitute", "Milk", "Drink", "Candy", "Chocolate"},
    "fritter_product_without_fritter_anchor": {"Doughnut", "Pastry"},
    "hummus_product_without_hummus_anchor": {"Hummus", "Dip"},
    "generic_bacon_anchor_on_turkey_bacon_product": {"Bacon", "Turkey", "Lunchmeat"},
    "bacon_anchor_on_pepperoni_product": {"Sausage", "Lunchmeat"},
    "bacon_anchor_on_component_product": {"Chicken", "Dish", "Meal", "Quiche", "Salad Dressing", "Sandwich", "Turkey", "Wrap"},
    "bacon_anchor_poultry_subtype_mismatch": {"Chicken", "Turkey", "Lunchmeat"},
    "bacon_anchor_without_bacon_product": {"Chicken", "Dish", "Meal", "Sandwich", "Syrup", "Turkey"},
    "burrito_product_without_burrito_anchor": {"Burrito", "Wrap", "Dish", "Meal"},
    "croissant_product_without_croissant_anchor": {"Croissant", "Sandwich"},
    "dressing_product_without_dressing_anchor": {"Dressing", "Salad Dressing", "Salad Dressing/Dip"},
    "quiche_product_without_quiche_anchor": {"Quiche", "Meal", "Pie"},
    "roll_product_without_roll_anchor": {"Roll", "Sandwich", "Bread"},
    "sandwich_product_without_sandwich_anchor": {"Sandwich", "Wrap"},
    "taco_product_without_taco_anchor": {"Taco", "Dish", "Meal"},
    "wrap_product_without_wrap_anchor": {"Wrap", "Sandwich"},
    "beans_and_rice_anchor_without_rice_product": {"Beans"},
    "beans_and_rice_anchor_on_prepared_entree_product": {"Burrito", "Dish", "Meal"},
    "plant_milk_anchor_on_pudding_product": {"Pudding"},
    "dry_batter_mix_anchor_on_prepared_fish_product": {"Fish", "Shrimp"},
    "baking_mix_anchor_on_plain_flour_product": {"Flour"},
    "applesauce_anchor_on_cider_product": {"Juice", "Juice Drink"},
    "fresh_sliced_apple_anchor_on_composite_apple_product": {"Fruit", "Candy", "Snack"},
    "bean_anchor_on_without_beans_product": {"Chili", "Dish", "Meal"},
    "french_toast_anchor_without_french_toast_product": {"Pancakes", "Waffles", "Baking Mix"},
    "infant_anchor_without_infant_product": {"Fruit", "Apple", "Banana", "Juice", "Cereal", "Dish", "Meal"},
    "pizza_anchor_without_pizza_product": {"Bacon", "Dish", "Meal", "Pasta Dish", "Sandwich", "Wrap"},
    "sauce_anchor_on_plain_pasta_product": {"Dumpling", "Pasta", "Pasta Dish"},
}


def esha_head(description: str) -> str:
    return str(description or "").split(",", 1)[0].strip()


def norm_head(head: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(head or "").lower()).strip()


def title_token_set(row: pd.Series) -> set[str]:
    return set(row.get("_title_tokens") or ())


def is_real_bar_product(desc: str, category: str) -> bool:
    return ingredient_clusters.is_real_bar_product(desc, category)


def is_manufactured_fruit_snack(desc_l: str, category_l: str) -> bool:
    """Fruit-flavored snacks are candy/snack formats, not fruit/smoothie/juice."""
    text = f"{desc_l} {category_l}"
    return bool(
        any(
            term in text
            for term in (
                "fruit by the foot",
                "fruit roll",
                "fruit roll-up",
                "fruit roll ups",
                "fruit rollups",
                "fruit rope",
                "fruit ropes",
                "fruit snack",
                "fruit snacks",
                "fruit flavored snack",
                "fruit flavoured snack",
                "gushers",
            )
        )
        or ("fruit" in text and "snacks" in category_l and any(term in text for term in ("rope", "roll", "gummy", "gummi")))
    )


def is_soda_or_energy_drink(desc_l: str, category_l: str, tokens: set[str]) -> bool:
    text = f"{desc_l} {category_l}"
    return bool(
        "energy drink" in text
        or "soft drink" in text
        or "carbonated" in text
        or {"soda", "cola"} & tokens
        or any(
            brand in text
            for brand in (
                "mtn dew",
                "mountain dew",
                "coca cola",
                "coca-cola",
                "diet coke",
                "dr pepper",
                "dr. pepper",
                "pepsi",
                "sprite",
                "7up",
                "7 up",
                "root beer",
                "ginger ale",
                "monster energy",
                "red bull",
                "amp energy",
            )
        )
    )


def is_cone_product(desc_l: str, category_l: str, tokens: set[str]) -> bool:
    return bool("cone" in tokens or "cones" in tokens or "waffle cone" in desc_l) and (
        "ice cream" in category_l or "novelties" in category_l or "cone" in desc_l
    )


def meal_heads_for(tokens: set[str]) -> set[str]:
    heads = {"Dish", "Meal"}
    if any(t in tokens for t in ("pasta", "fettuccini", "fettuccine", "macaroni", "spaghetti", "lasagna", "gnocchi")):
        heads.add("Pasta Dish")
    if "gnocchi" in tokens:
        heads.add("Dumpling")
    if "macaroni" in tokens and "cheese" in tokens:
        heads.add("Macaroni & Cheese")
    if "pizza" in tokens:
        heads.add("Pizza")
    if "burrito" in tokens:
        heads.add("Burrito")
    if "wrap" in tokens:
        heads.add("Wrap")
    if "sandwich" in tokens:
        heads.add("Sandwich")
    return heads


def infer_heads(row: pd.Series, quarantine_reason: str) -> set[str]:
    desc = str(row.get("product_description") or "")
    category = str(row.get("branded_food_category") or "")
    desc_l = desc.lower()
    cat_l = category.lower()
    tokens = title_token_set(row)
    heads: set[str] = set()

    if is_manufactured_fruit_snack(desc_l, cat_l):
        return {"Snack"}
    if "syrup" in tokens or "syrup" in desc_l:
        return {"Syrup", "Sweetener"}
    if "baking chips" in desc_l or "baking decorations" in cat_l or "dessert toppings" in cat_l:
        heads = {"Baking Chips"}
        if "chocolate" in tokens or "cocoa" in tokens:
            heads.update({"Chocolate", "Baking Chocolate"})
        return heads
    if "salad dressing" in cat_l or "mayonnaise" in cat_l:
        if {"dressing", "dressings", "vinaigrette", "ranch", "french", "caesar", "italian", "mayonnaise", "mayo"} & tokens or any(
            term in desc_l for term in ("dressing", "vinaigrette", " ranch", " french", " caesar", " italian", "mayonnaise", "mayo")
        ):
            heads = {"Dressing", "Salad Dressing", "Salad Dressing/Dip"}
            if "dip" in tokens or "dip" in desc_l:
                heads.add("Dip")
            return heads
    if "quiche" in tokens or "quiche" in desc_l:
        return {"Quiche", "Meal", "Pie"}
    if "trail mix" in desc_l:
        return {"Trail Mix", "Nuts", "Snack"}
    if "popcorn" in desc_l:
        return {"Popcorn", "Snack"}
    if any(term in cat_l for term in ("jam, jelly", "jelly & fruit spreads", "fruit spreads")) or ("jam" in tokens and "bacon" not in tokens):
        return {"Jam", "Jelly", "Spread"}
    if is_cone_product(desc_l, cat_l, tokens):
        return {"Cone"}
    if is_soda_or_energy_drink(desc_l, cat_l, tokens):
        return {"Soda", "Drink"}

    for token, mapped in HEAD_ALIASES.items():
        if token in tokens or re.search(rf"\b{re.escape(token)}\b", desc_l):
            heads.update(mapped)
    for fragment, mapped in CATEGORY_HEADS.items():
        if fragment in cat_l:
            heads.update(mapped)

    if "energy drink" in desc_l or ("energy" in tokens and any(t in desc_l for t in ("fluid ounce", "fl oz", "can", "bottle"))):
        heads.update({"Drink", "Soda"})
    if "french" in tokens and "toast" in tokens:
        heads.add("French Toast")
    if "ice" in tokens and "cream" in tokens:
        heads.add("Ice Cream")
    if "macaroni" in tokens and "cheese" in tokens:
        heads.add("Macaroni & Cheese")
    if "trail" in tokens and "mix" in tokens:
        heads.update({"Snack", "Nuts"})
        heads.discard("Bar")
    if "bar" in heads and not is_real_bar_product(desc, category):
        heads.discard("Bar")

    # Category/form overrides. These prevent the original bad reason from
    # dragging products back into the wrong head pool.
    if "frozen fish" in cat_l or "fish & seafood" in cat_l:
        fish_heads = {"Fish"}
        if "shrimp" in tokens:
            fish_heads.add("Shrimp")
        heads = fish_heads
    elif "meat/poultry" in cat_l or "prepared/processed" in cat_l:
        if "stick" in tokens or "sticks" in tokens or "slim jim" in desc_l:
            heads = {"Meat Stick", "Sausage", "Lunchmeat"}
            if "pepperoni" in tokens:
                heads.add("Pepperoni")
            return heads
        meat_heads = {"Dish", "Meal"}
        for token, mapped in {
            "chicken": {"Chicken", "Dish"},
            "beef": {"Beef", "Dish"},
            "pork": {"Pork", "Dish"},
            "ham": {"Ham", "Lunchmeat"},
            "turkey": {"Turkey", "Lunchmeat"},
            "pepperoni": {"Sausage", "Lunchmeat"},
            "salami": {"Sausage", "Lunchmeat"},
            "bacon": {"Bacon", "Pork"},
        }.items():
            if token in tokens or token in desc_l:
                meat_heads.update(mapped)
        heads = meat_heads
    elif any(term in cat_l for term in ("frozen dinners", "entrees", "prepared meals", "prepared/preserved foods variety packs", "dough based products / meals", "grain based products / meals")):
        heads = meal_heads_for(tokens)
    elif "non alcoholic beverages" in cat_l or "ready to drink" in cat_l or "not ready to drink" in cat_l:
        beverage_heads = {"Drink"}
        if "juice" in tokens or "juice" in desc_l:
            beverage_heads.update({"Juice", "Juice Drink"})
        if "soda" in tokens or "carbonated" in desc_l:
            beverage_heads.add("Soda")
        if "coffee" in tokens:
            beverage_heads.update({"Coffee", "Blended Coffee"})
        if "tea" in tokens:
            beverage_heads.add("Tea")
        if "milk" in tokens or "soy" in tokens or "almond" in tokens:
            beverage_heads.update({"Milk", "Cream Substitute"})
        heads = beverage_heads
    elif "processed cereal" in cat_l:
        if is_real_bar_product(desc, category):
            cereal_heads = {"Bar", "Snack"}
            if "chocolate" in tokens:
                cereal_heads.add("Chocolate Bar")
        else:
            cereal_heads = {"Cereal", "Snack"}
        heads = cereal_heads
    elif "ice cream" in cat_l or "frozen yogurt" in cat_l:
        heads = {"Ice Cream"}
        if "cone" in tokens or "cones" in tokens:
            heads.add("Cone")
        if "yogurt" in tokens or "yogurt" in cat_l:
            heads.add("Yogurt")
    elif any(term in cat_l for term in ("seasoning", "salts", "spices", "marinades", "tenderizers", "herbs/spices")):
        heads = {"Seasoning", "Spice"}
        if "sauce" in tokens:
            heads.add("Sauce")
    elif "snacks" in cat_l and is_manufactured_fruit_snack(desc_l, cat_l):
        heads = {"Snack"}
    elif "dips & salsa" in cat_l or "dips" in cat_l or "salsa" in cat_l:
        if "salsa" in tokens:
            heads = {"Salsa"}
        elif "hummus" in tokens:
            heads = {"Hummus"}
        elif "dip" in tokens:
            heads = {"Dip"}
        else:
            heads = {"Dip", "Salsa", "Hummus"}
    elif "prepared soups" in cat_l and "sauce" in tokens and "soup" not in tokens:
        heads = {"Sauce", "Chili"}
    elif "meals" in cat_l or " meal" in cat_l or "based products / meals" in cat_l:
        heads = meal_heads_for(tokens)
    elif "breads & buns" in cat_l or cat_l.strip() in {"bread", "breads", "bakery bread"}:
        if "bagel" in tokens or "bagels" in tokens:
            heads = {"Bagel"}
        elif "bun" in tokens or "buns" in tokens:
            heads = {"Bun"}
        elif "roll" in tokens or "rolls" in tokens:
            heads = {"Roll"}
        elif "bread" in tokens or "loaf" in tokens or "loaves" in tokens:
            heads = {"Bread"}
        else:
            heads = {"Bread"}
    elif "sauces" in cat_l or "condiments" in cat_l or "spreads/dips" in cat_l:
        sauce_heads: set[str] = set()
        if "salsa" in tokens:
            sauce_heads.add("Salsa")
        if "dip" in tokens:
            sauce_heads.add("Dip")
        if "ketchup" in tokens:
            sauce_heads.add("Ketchup")
        if "mustard" in tokens:
            sauce_heads.add("Mustard")
        if "gravy" in tokens:
            sauce_heads.add("Gravy")
        if "sauce" in tokens or not sauce_heads:
            sauce_heads.add("Sauce")
        heads = sauce_heads
    elif "ice cream" in cat_l and "cone" in tokens:
        heads = {"Cone"}

    if not heads:
        heads.update(REASON_HEADS.get(quarantine_reason, set()))

    # Reason-specific heads can add precision for known structural cases, but
    # only after category/title has established the lane.
    if quarantine_reason in {
        "beans_anchor_subtype_mismatch",
        "bean_product_without_bean_anchor",
        "flour_product_without_flour_anchor",
        "baking_mix_anchor_on_plain_flour_product",
        "generic_bacon_anchor_on_turkey_bacon_product",
        "bacon_anchor_on_pepperoni_product",
        "beans_and_rice_anchor_without_rice_product",
        "beans_and_rice_anchor_on_prepared_entree_product",
        "dry_batter_mix_anchor_on_prepared_fish_product",
    }:
        heads.update(REASON_HEADS.get(quarantine_reason, set()))

    primary = str(row.get("_primary") or "")
    primary_allowed = (
        not heads
        or any(fragment in cat_l for fragment in ("fruit", "vegetable", "beans", "nuts", "seeds", "peanuts"))
    )
    if primary and primary_allowed:
        primary_head = {
            "apple": "Apple",
            "banana": "Banana",
            "orange": "Orange",
            "tomato": "Tomatoes",
            "potato": "Potatoes",
            "corn": "Corn",
            "pea": "Peas",
            "bean": "Beans",
            "chicken": "Chicken",
            "beef": "Beef",
            "pork": "Pork",
            "turkey": "Turkey",
            "fish": "Fish",
            "shrimp": "Shrimp",
            "almond": "Nuts",
            "peanut": "Nuts",
            "oat": "Cereal",
            "rice": "Rice",
        }.get(primary)
        if primary_head:
            heads.add(primary_head)

    return {h for h in heads if h}


def build_head_index(candidates: dict[str, full_map.Candidate]) -> dict[str, list[str]]:
    by_head: dict[str, list[str]] = defaultdict(list)
    for code, candidate in candidates.items():
        by_head[norm_head(esha_head(candidate.description))].append(code)
    return by_head


def code_pool_for_heads(heads: set[str], head_index: dict[str, list[str]], candidates: dict[str, full_map.Candidate]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    normalized = {norm_head(h) for h in heads}
    for h in normalized:
        for code in head_index.get(h, []):
            if code not in seen:
                seen.add(code)
                out.append(code)
    # Allow plural/singular-ish containment for heads missing exact aliases.
    if len(out) < 20:
        for h in normalized:
            for head_norm, codes in head_index.items():
                if head_norm == h or head_norm.startswith(h + " ") or h.startswith(head_norm + " "):
                    for code in codes:
                        if code not in seen:
                            seen.add(code)
                            out.append(code)
    return [code for code in out if code in candidates]


def score_candidate_for_row(
    row: pd.Series,
    candidate: full_map.Candidate,
    heads: set[str],
    idf: dict[str, float],
) -> tuple[float, str]:
    title_tokens = set(row.get("_title_tokens") or ())
    ingredient_tokens = set(row.get("_ingredient_tokens") or ())
    evidence = title_tokens | ingredient_tokens
    head = esha_head(candidate.description)
    target_head_match = norm_head(head) in {norm_head(h) for h in heads}
    shared_title = title_tokens & candidate.meaningful_terms
    shared_ingredients = ingredient_tokens & candidate.meaningful_terms
    shared_identity = evidence & candidate.identity_terms
    extra_identity = candidate.identity_terms - evidence - matcher.GENERIC_FILLER_TOKENS

    score = 0.0
    if target_head_match:
        score += 12.0
    score += 4.0 * len(shared_title)
    score += 1.25 * len(shared_ingredients)
    score += 3.0 * len(shared_identity)
    score += sum(idf.get(tok, 1.0) for tok in shared_title)
    score += 0.4 * math.log1p(candidate.category_support)
    score -= 1.2 * len(extra_identity)
    if candidate.needs_fix:
        score -= 2.0
    reason = f"head={head};title_hits={len(shared_title)};ingredient_hits={len(shared_ingredients)};identity_hits={len(shared_identity)};extra_identity={len(extra_identity)}"
    return score, reason


def choose_replacement(
    row: pd.Series,
    heads: set[str],
    pool: list[str],
    candidates: dict[str, full_map.Candidate],
    anchors: dict[str, ingredient_clusters.EshaAnchor],
    idf: dict[str, float],
) -> tuple[full_map.Candidate | None, float, str, int]:
    scored: list[tuple[float, str, full_map.Candidate]] = []
    for code in pool:
        candidate = candidates[code]
        anchor = anchors.get(code)
        if anchor is None:
            continue
        ok, _reason = ingredient_clusters.candidate_gate(row, anchor)
        if not ok:
            continue
        score, score_reason = score_candidate_for_row(row, candidate, heads, idf)
        scored.append((score, score_reason, candidate))

    if not scored:
        return None, 0.0, "no_candidate_passed_gate", len(pool)
    scored.sort(
        key=lambda item: (
            item[0],
            -len(item[2].identity_terms),
            -int(item[2].code) if item[2].code.isdigit() else -10**9,
        ),
        reverse=True,
    )
    best_score, score_reason, best = scored[0]
    second = scored[1][0] if len(scored) > 1 else 0.0
    margin = best_score - second
    # Conservative: require a compatible head and some product evidence overlap.
    has_evidence = bool((set(row.get("_title_tokens") or ()) | set(row.get("_ingredient_tokens") or ())) & best.meaningful_terms)
    evidence = set(row.get("_title_tokens") or ()) | set(row.get("_ingredient_tokens") or ())
    best_head = norm_head(esha_head(best.description))
    min_margin = 0.25 if best_head in LOW_MARGIN_OK_HEADS else 1.0
    strong_extra_identity = (
        set(best.identity_terms)
        - evidence
        - matcher.GENERIC_FILLER_TOKENS
        - SOFT_EXTRA_IDENTITY
    )
    desc_l = str(row.get("product_description") or "").lower()
    cat_l = str(row.get("branded_food_category") or "").lower()
    title_hits = set(row.get("_title_tokens") or ()) & best.meaningful_terms
    if best_head in BROAD_HEADS_NEED_TITLE_OVERLAP and not title_hits:
        return None, best_score, f"broad_head_without_title_overlap;{score_reason};margin={margin:.3f}", len(pool)
    if best_head in BROAD_HEADS_NEED_TITLE_OVERLAP and strong_extra_identity:
        return None, best_score, f"broad_head_extra_identity={','.join(sorted(strong_extra_identity))};{score_reason};margin={margin:.3f}", len(pool)
    if len(strong_extra_identity) >= 3:
        return None, best_score, f"extra_identity_too_specific={','.join(sorted(strong_extra_identity))};{score_reason};margin={margin:.3f}", len(pool)
    if best_head == "smoothie" and "smoothie" not in evidence and "smoothie" not in cat_l:
        return None, best_score, f"smoothie_without_smoothie_product;{score_reason};margin={margin:.3f}", len(pool)
    if best_head == "juice drink" and not ({"juice", "drink"} & evidence or "juice" in cat_l or "beverage" in cat_l):
        return None, best_score, f"juice_drink_without_beverage_product;{score_reason};margin={margin:.3f}", len(pool)
    if best_head == "fruit" and (
        is_manufactured_fruit_snack(desc_l, cat_l)
        or not any(fragment in cat_l for fragment in ("fruit", "produce", "vegetable", "frozen fruit", "wholesome snacks"))
    ):
        return None, best_score, f"fruit_without_fruit_lane;{score_reason};margin={margin:.3f}", len(pool)
    if len(strong_extra_identity) >= 2 and margin < 2.0:
        return None, best_score, f"extra_identity_conflict={','.join(sorted(strong_extra_identity))};{score_reason};margin={margin:.3f}", len(pool)
    if best_score < 12.0 or margin < min_margin or not has_evidence:
        return None, best_score, f"low_confidence;{score_reason};margin={margin:.3f}", len(pool)
    return best, best_score, f"{score_reason};margin={margin:.3f}", len(pool)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-map", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-map", type=Path, default=OUT_REPAIRED)
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print("loading rebuilt map", flush=True)
    current = ingredient_clusters.load_current_map(args.input_map)
    print(f"  rows: {len(current):,}", flush=True)
    print("loading products/features", flush=True)
    products = ingredient_clusters.load_products()
    features = ingredient_clusters.build_product_features(products, current)
    q = features[features["assignment_source"].astype(str).eq("ingredient_candidate_gate_quarantine")].copy()
    if args.limit:
        q = q.head(args.limit).copy()
    print(f"  quarantined rows to remap: {len(q):,}", flush=True)

    reason_frames = []
    for reason_path in (OUT_DIR / "post_remap_hard_quarantine.csv", OUT_DIR / "ingredient_assignment_quarantine.csv"):
        if reason_path.exists():
            reason_frames.append(
                pd.read_csv(reason_path, dtype=str, keep_default_na=False, low_memory=False)[
                    ["gtin_upc", "quarantine_reason"]
                ]
            )
    q_reason = (
        pd.concat(reason_frames, ignore_index=True).drop_duplicates("gtin_upc", keep="first")
        if reason_frames
        else pd.DataFrame(columns=["gtin_upc", "quarantine_reason"])
    )
    q = q.merge(q_reason, on="gtin_upc", how="left")
    q["quarantine_reason"] = q["quarantine_reason"].fillna("")

    print("loading candidates/anchors", flush=True)
    candidates, _category_to_codes, _family_to_codes, idf = full_map.build_candidates()
    anchors = ingredient_clusters.load_esha_anchors()
    head_index = build_head_index(candidates)
    print(f"  candidates: {len(candidates):,}; heads: {len(head_index):,}", flush=True)

    proposals: list[dict[str, object]] = []
    no_valid: list[dict[str, object]] = []
    for i, (_, row) in enumerate(q.iterrows(), start=1):
        if i % 5000 == 0:
            print(f"  remapped scan: {i:,}/{len(q):,}", flush=True)
        heads = infer_heads(row, str(row.get("quarantine_reason") or ""))
        pool = code_pool_for_heads(heads, head_index, candidates) if heads else []
        best, score, why, pool_n = choose_replacement(row, heads, pool, candidates, anchors, idf) if pool else (None, 0.0, "no_compatible_heads", 0)
        base = {
            "gtin_upc": row["gtin_upc"],
            "fdc_id": row["fdc_id"],
            "product_description": row["product_description"],
            "branded_food_category": row["branded_food_category"],
            "brand_owner": row["brand_owner"],
            "brand_name": row["brand_name"],
            "quarantine_reason": row.get("quarantine_reason", ""),
            "candidate_heads": "|".join(sorted(heads)),
            "candidate_pool_size": pool_n,
            "score": round(float(score), 4),
            "score_reason": why,
        }
        if best is None:
            no_valid.append(base)
            continue
        proposals.append(
            {
                **base,
                "proposed_esha_code": best.code,
                "proposed_esha_description": best.description,
                "proposed_esha_head": esha_head(best.description),
                "proposed_esha_family": best.family,
                "proposal_source": "head_remap_v1",
            }
        )

    proposals_df = pd.DataFrame(proposals)
    no_valid_df = pd.DataFrame(no_valid)
    proposals_df.to_csv(OUT_PROPOSALS, index=False)
    no_valid_df.to_csv(OUT_NO_VALID, index=False)
    print(f"  wrote {OUT_PROPOSALS.relative_to(ROOT)} ({len(proposals_df):,})", flush=True)
    print(f"  wrote {OUT_NO_VALID.relative_to(ROOT)} ({len(no_valid_df):,})", flush=True)

    out = current.copy()
    if not proposals_df.empty:
        apply = proposals_df.drop_duplicates("fdc_id", keep="first").set_index("fdc_id")
        matched = out["fdc_id"].isin(apply.index)
        out.loc[matched, "best_esha_code"] = out.loc[matched, "fdc_id"].map(apply["proposed_esha_code"])
        out.loc[matched, "best_esha_description"] = out.loc[matched, "fdc_id"].map(apply["proposed_esha_description"])
        out.loc[matched, "best_esha_head"] = out.loc[matched, "fdc_id"].map(apply["proposed_esha_head"])
        out.loc[matched, "best_esha_family"] = out.loc[matched, "fdc_id"].map(apply["proposed_esha_family"])
        out.loc[matched, "score"] = out.loc[matched, "fdc_id"].map(apply["score"]).astype(str)
        out.loc[matched, "n_candidates"] = out.loc[matched, "fdc_id"].map(apply["candidate_pool_size"]).astype(str)
        out.loc[matched, "assignment_source"] = "head_remap_v1"

    output_cols = list(out.columns)
    if "best_esha_head" not in output_cols:
        out["best_esha_head"] = out["best_esha_description"].astype(str).map(lambda v: esha_head(v) if v.strip() else "")
        output_cols = list(out.columns)
    out.to_csv(args.output_map, index=False)
    assigned = int((out["best_esha_code"].astype(str).str.strip() != "").sum())
    remaining_quarantine = int((out["assignment_source"].astype(str) == "ingredient_candidate_gate_quarantine").sum())
    summary = {
        "input_map": str(args.input_map),
        "output_map": str(args.output_map),
        "input_rows": int(len(current)),
        "quarantined_input_rows": int(len(q)),
        "proposals": int(len(proposals_df)),
        "no_valid": int(len(no_valid_df)),
        "assigned_output_rows": assigned,
        "remaining_quarantine_rows": remaining_quarantine,
        "proposal_heads": proposals_df["proposed_esha_head"].value_counts().head(50).to_dict() if not proposals_df.empty else {},
        "no_valid_reasons": no_valid_df["quarantine_reason"].value_counts().head(50).to_dict() if not no_valid_df.empty else {},
    }
    OUT_SUMMARY.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"  wrote {args.output_map.relative_to(ROOT) if args.output_map.is_absolute() else args.output_map}", flush=True)
    print(json.dumps(summary, indent=2, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
