#!/usr/bin/env python3
"""Prototype semantic normalizer for retail leaf cleanup.

This is intentionally separate from ``clean_retail_leaf_v2.py``.  It tests the
shape we want from an LLM pass: normalize the product into a small semantic
record, then let deterministic code compile that record into an existing path
or a mint proposal.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


REPO = Path("/Users/jamiebarton/Desktop/esha_audit_bundle")
V2 = REPO / "retail_mapper" / "v2"
DEFAULT_INPUT = V2 / "retail_leaf_v2_enriched_v2.csv"
DEFAULT_TAXONOMY = REPO / "implementation" / "output" / "taxonomy_paths_cleaned.csv"
DEFAULT_JSONL = V2 / "semantic_labeler_trial.jsonl"
DEFAULT_MINTS = V2 / "semantic_labeler_mint_candidates.csv"

csv.field_size_limit(sys.maxsize)

TOKEN_RE = re.compile(r"[a-z0-9]+")
NON_WORD_RE = re.compile(r"[^a-z0-9]+")

DEFAULT_FDCS = [
    "564094",   # BAI clementine drink
    "2503987",  # grapefruit Perrier-ish drink
    "2448441",  # margarita mixer wrongly pulled to grapefruit/produce
    "758024",   # huevos rancheros frozen meal
    "2519795",  # SpaghettiOs
    "2103595",  # salad kit
    "2084923",  # Honey Crisp apples, not a dish
    "2114955",  # vegetable bowl with hummus
    "1998403",  # rooibos grapefruit infusion
    "2265845",  # grapefruit protein water
]

WEAK_TOKENS = {
    "added",
    "all",
    "and",
    "brand",
    "classic",
    "count",
    "ct",
    "each",
    "flavor",
    "flavored",
    "food",
    "foods",
    "free",
    "fresh",
    "natural",
    "naturally",
    "net",
    "new",
    "original",
    "oz",
    "pack",
    "premium",
    "quality",
    "real",
    "style",
    "the",
    "with",
}

PACKAGE_TOKENS = {
    "bottle",
    "box",
    "can",
    "carton",
    "case",
    "fluid",
    "lb",
    "lbs",
    "ml",
    "ounce",
    "ounces",
    "pack",
    "packet",
    "pet",
    "pk",
}

BRAND_TOKENS = {
    "bai",
    "campbell",
    "campbells",
    "hill",
    "country",
    "fare",
    "kellogg",
    "kelloggs",
    "perrier",
    "tetley",
    "welch",
    "welchs",
}

FRUIT_TOKENS = {
    "acai",
    "apple",
    "apricot",
    "banana",
    "blackberry",
    "blueberry",
    "cantaloupe",
    "cherry",
    "clementine",
    "cranberry",
    "grape",
    "grapefruit",
    "guava",
    "kiwi",
    "lemon",
    "lime",
    "mango",
    "mandarin",
    "orange",
    "peach",
    "pear",
    "pineapple",
    "pomegranate",
    "raspberry",
    "strawberry",
    "tangerine",
    "watermelon",
}

ICE_CREAM_FLAVOR_TOKENS = FRUIT_TOKENS | {
    "almond",
    "amaretto",
    "birthday",
    "brownie",
    "butter",
    "butterscotch",
    "caramel",
    "cheesecake",
    "chocolate",
    "cinnamon",
    "coffee",
    "cookie",
    "cookies",
    "cordial",
    "cream",
    "fudge",
    "leche",
    "marshmallow",
    "mint",
    "mocha",
    "neapolitan",
    "pecan",
    "peppermint",
    "pistachio",
    "rocky",
    "swirl",
    "toffee",
    "vanilla",
}

ICE_CREAM_FORM_WORDS = {
    "bar",
    "bars",
    "cake",
    "cakes",
    "cone",
    "cones",
    "cream",
    "creams",
    "frozen",
    "gelato",
    "ice",
    "mix",
    "sandwich",
    "sandwiches",
    "sherbet",
    "sorbet",
    "sundae",
    "sundaes",
    "yogurt",
}

PIZZA_TOPPING_TOKENS = {
    "asiago",
    "bacon",
    "beef",
    "buffalo",
    "cheese",
    "chicken",
    "ham",
    "jalapeno",
    "meatball",
    "mozzarella",
    "mushroom",
    "olive",
    "onion",
    "pepper",
    "pepperoni",
    "peppers",
    "provolone",
    "ranch",
    "sausage",
    "spinach",
    "steak",
    "vegetable",
}

CRUST_TOKENS = {
    "classic",
    "crispy",
    "deep",
    "flatbread",
    "gluten",
    "hand",
    "medium",
    "pan",
    "rising",
    "stuffed",
    "thick",
    "thin",
    "whole",
}

MEAL_BFC_HINTS = (
    "breakfast sandwiches",
    "dough based products meals",
    "entrees",
    "frozen breakfast",
    "frozen dinners",
    "frozen meals",
    "grain based products meals",
    "other deli",
    "prepared meals",
    "prepared subs",
    "prepared wraps",
    "vegetable based products meals",
)

MEAL_FALSE_FRIEND_BFC_HINTS = (
    "cereal",
    "cookies biscuits",
    "flours corn meal",
    "hot cereals",
)


@dataclass
class SemanticRecord:
    fdc_id: str
    title: str
    current_leaf: str
    category_path: str
    head: str
    filter_attributes: dict[str, object]
    retail_type: str
    supercategory: str
    family: str
    form: str
    base_identity: str
    modifiers: list[str]
    state: list[str]
    claims: list[str]
    parent_path: str
    proposed_path: str
    existing_path: str
    mint_required: bool
    parent_exists: bool
    confidence: float
    notes: list[str]


def ascii_fold(value: str) -> str:
    return unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode("ascii")


def normalize_text(value: str) -> str:
    value = ascii_fold(value).lower()
    value = value.replace("&", " and ").replace("+", " and ")
    value = value.replace("spaghettios", "spaghetti rings")
    value = NON_WORD_RE.sub(" ", value)
    return re.sub(r"\s+", " ", value).strip()


def row_value(row: dict[str, str], key: str) -> str:
    return row.get(key) or ""


def tokens_for(value: str) -> list[str]:
    return [token for token in TOKEN_RE.findall(normalize_text(value)) if len(token) >= 2]


def token_set(value: str) -> set[str]:
    return {singularize(token) for token in tokens_for(value)}


def singularize(token: str) -> str:
    if token.endswith("ies") and len(token) > 4:
        return token[:-3] + "y"
    if token.endswith("oes") and len(token) > 4:
        return token[:-2]
    if token.endswith("s") and len(token) > 3 and not token.endswith(("ss", "us")):
        return token[:-1]
    return token


def title_case(value: str) -> str:
    special = {"bbq": "BBQ", "pb": "PB"}
    return " ".join(special.get(part, part.capitalize()) for part in normalize_text(value).split())


def has_phrase(tokens: list[str], phrase: str) -> bool:
    wanted = phrase.split()
    return any(tokens[idx : idx + len(wanted)] == wanted for idx in range(len(tokens) - len(wanted) + 1))


def dedupe(values: Iterable[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        value = normalize_text(value)
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out


def strip_noise_tokens(tokens: Iterable[str], extra_noise: Iterable[str] = ()) -> list[str]:
    noise = WEAK_TOKENS | PACKAGE_TOKENS | BRAND_TOKENS | set(extra_noise)
    return [token for token in tokens if token not in noise and not token.isdigit()]


def load_taxonomy(path: Path) -> set[str]:
    paths: set[str] = set()
    with path.open(errors="replace", newline="") as handle:
        for row in csv.DictReader(handle):
            leaf = (row.get("retail_leaf") or "").strip()
            category_path = (row.get("category_path") or "").strip()
            head = (row.get("head") or "").strip()
            if leaf:
                paths.add(leaf)
            if category_path:
                paths.add(category_path)
                if head:
                    paths.add(f"{category_path} > {head}")
    return paths


def path_exists(path: str, taxonomy: set[str]) -> bool:
    return path in taxonomy


def compile_path(parent: str, segment: str, taxonomy: set[str]) -> tuple[str, str, bool, bool]:
    parent = parent.strip()
    segment = title_case(segment).strip()
    proposed = f"{parent} > {segment}" if segment else parent
    existing = proposed if proposed in taxonomy else ""
    return proposed, existing, not bool(existing), parent in taxonomy


def compact_filters(**values: object) -> dict[str, object]:
    out: dict[str, object] = {}
    for key, value in values.items():
        if value in ("", None, [], {}, False):
            continue
        out[key] = value
    return out


def beverage_head(identity: str, form: str) -> str:
    if not identity:
        return title_case(form)
    if identity in normalize_text(form).split():
        return title_case(form)
    return title_case(f"{identity} {form}")


def flavor_from_tokens(tokens: Iterable[str], *, drop: Iterable[str] = ()) -> str:
    drop_set = set(drop) | WEAK_TOKENS | PACKAGE_TOKENS | BRAND_TOKENS
    out: list[str] = []
    for token in tokens:
        token = singularize(token)
        if token in drop_set:
            continue
        if token in ICE_CREAM_FLAVOR_TOKENS or token in PIZZA_TOPPING_TOKENS:
            out.append(token)
    return " ".join(dedupe(out[:5]))


def first_fruit_from(texts: Iterable[str]) -> str:
    for text in texts:
        tokens = token_set(text)
        for fruit in sorted(FRUIT_TOKENS):
            if fruit in tokens:
                return fruit
    return ""


def fruit_modifiers(texts: Iterable[str], primary: str) -> list[str]:
    mods: list[str] = []
    for text in texts:
        for token in tokens_for(text):
            token = singularize(token)
            if token in FRUIT_TOKENS and token != primary:
                mods.append(token)
    return dedupe(mods)


def branded_noise(row: dict[str, str]) -> set[str]:
    raw = " ".join([row_value(row, "brand_name"), row_value(row, "brand_owner")])
    return set(tokens_for(raw))


def clean_detail(title: str, drop: Iterable[str] = ()) -> str:
    tokens = strip_noise_tokens(tokens_for(title), set(drop))
    return title_case(" ".join(tokens[:6]))


def beverage_record(row: dict[str, str], taxonomy: set[str]) -> SemanticRecord:
    title = row_value(row, "title")
    bfc = row_value(row, "branded_food_category")
    esha = row_value(row, "current_esha_desc")
    ing = row_value(row, "ing_full") or row_value(row, "ing_top5")
    tokens = tokens_for(" ".join([title, bfc, esha, ing]))
    token_set_ = set(tokens)
    bfc_norm = normalize_text(bfc)
    title_norm = normalize_text(title)
    ing_norm = normalize_text(ing)
    notes: list[str] = []

    identity = first_fruit_from([title, esha, ing])
    modifiers = fruit_modifiers([title, esha, ing], identity)
    state: list[str] = []
    claims: list[str] = []

    if {"sparkling", "carbonated", "seltzer"} & token_set_ or "carbon dioxide" in ing_norm:
        state.append("sparkling")
    if "antioxidant" in token_set_:
        claims.append("antioxidant")
    if "electrolyte" in token_set_ or "electrolytes" in token_set_:
        claims.append("electrolyte")

    if "protein" in token_set_ and "water" in token_set_:
        parent = "Beverage > Functional > Protein Water"
        family = "Functional"
        form = "protein water"
        notes.append("protein_water_form_from_title")
    elif "rooibos" in token_set_ or "yerba" in token_set_ or "mate" in token_set_:
        parent = "Beverage > Tea"
        family = "Tea"
        form = "herbal infusion"
        notes.append("tea_infusion_from_title_or_ingredients")
    elif "margarita" in token_set_ or "mixer" in token_set_ or "mixers" in token_set_:
        parent = "Beverage > Cocktail Mixers"
        family = "Cocktail Mixers"
        form = "cocktail mixer"
        identity = "margarita" if "margarita" in token_set_ else identity
        notes.append("mixer_form_beats_esha_grapefruit")
    elif "seltzer" in token_set_ or ("sparkling" in state and "juice" not in title_norm and "mineral water" in ing_norm):
        parent = "Beverage > Seltzer"
        family = "Seltzer"
        form = "seltzer"
        notes.append("carbonated_water_form_beats_esha_juice")
    elif "juice" in token_set_ or "juice" in bfc_norm or "juice" in normalize_text(esha):
        parent = "Beverage > Fruit-based Drinks > Juice"
        family = "Fruit-based Drinks"
        form = "juice drink" if "drink" in token_set_ else "juice"
        notes.append("juice_context")
    elif "water" in token_set_:
        parent = "Beverage > Water"
        family = "Water"
        form = "water"
        notes.append("water_context")
    else:
        parent = "Beverage > Drink"
        family = "Drink"
        form = "drink"
        notes.append("generic_beverage_context")

    if not identity:
        identity = clean_detail(title, branded_noise(row) | {form, "drink", "beverage"})
        notes.append("identity_from_title_fallback")

    proposed, existing, mint_required, parent_exists = compile_path(parent, identity, taxonomy)
    confidence = 0.82 if identity else 0.55
    if existing:
        confidence += 0.1
    return SemanticRecord(
        fdc_id=row.get("fdc_id", ""),
        title=title,
        current_leaf=row.get("retail_leaf", ""),
        category_path=parent,
        head=beverage_head(identity, form),
        filter_attributes=compact_filters(
            flavor=identity if identity else "",
            modifiers=modifiers,
            state=state,
            claims=claims,
            brand=row_value(row, "brand_name"),
        ),
        retail_type="single",
        supercategory="Beverage",
        family=family,
        form=form,
        base_identity=identity,
        modifiers=modifiers,
        state=state,
        claims=claims,
        parent_path=parent,
        proposed_path=proposed,
        existing_path=existing,
        mint_required=mint_required,
        parent_exists=parent_exists,
        confidence=round(min(confidence, 0.96), 3),
        notes=notes,
    )


def candy_record(row: dict[str, str], taxonomy: set[str]) -> SemanticRecord:
    title = row_value(row, "title")
    tokens = tokens_for(title)
    token_set_ = set(tokens)
    if {"gummy", "gummi", "gummies"} & token_set_:
        parent = "Snack > Candy > Gummy"
        form = "gummy candy"
    elif "gum" in token_set_:
        parent = "Snack > Candy > Gum"
        form = "gum"
    elif "jelly" in token_set_ and "bean" in token_set_:
        parent = "Snack > Candy > Jelly Bean"
        form = "jelly bean"
    elif "hard" in token_set_:
        parent = "Snack > Candy > Hard Candy"
        form = "hard candy"
    else:
        parent = "Snack > Candy"
        form = "candy"

    fruits = fruit_modifiers([title], "")
    identity = fruits[0] if len(fruits) == 1 else ""
    proposed, existing, mint_required, parent_exists = compile_path(parent, identity, taxonomy)
    if not identity:
        proposed, existing, mint_required, parent_exists = compile_path(parent, "", taxonomy)
    return SemanticRecord(
        fdc_id=row.get("fdc_id", ""),
        title=title,
        current_leaf=row.get("retail_leaf", ""),
        category_path=parent,
        head=title_case(form),
        filter_attributes=compact_filters(
            flavor=identity if identity else "",
            flavors=fruits if len(fruits) > 1 else [],
            brand=row_value(row, "brand_name"),
        ),
        retail_type="single",
        supercategory="Snack",
        family="Candy",
        form=form,
        base_identity=identity,
        modifiers=fruits,
        state=[],
        claims=[],
        parent_path=parent,
        proposed_path=proposed,
        existing_path=existing,
        mint_required=mint_required,
        parent_exists=parent_exists,
        confidence=0.9 if parent_exists else 0.78,
        notes=["candy_form_beats_flavor_list"],
    )


def ice_cream_record(row: dict[str, str], taxonomy: set[str]) -> SemanticRecord:
    title = row_value(row, "title")
    bfc = row_value(row, "branded_food_category")
    tokens = tokens_for(title)
    token_set_ = set(tokens)
    notes: list[str] = ["ice_cream_flavor_stays_filter"]
    category_path = "Frozen > Ice Cream"

    if has_phrase(tokens, "ice cream sandwich") or "sandwich" in token_set_ or "sandwiches" in token_set_:
        head = "Ice Cream Sandwich"
        form = "ice cream sandwich"
        notes.append("form_promoted_to_head")
    elif has_phrase(tokens, "ice cream cake") or ("cake" in token_set_ and "ice" in token_set_ and "cream" in token_set_):
        head = "Ice Cream Cake"
        form = "ice cream cake"
        notes.append("form_promoted_to_head")
    elif has_phrase(tokens, "ice cream bar") or "bar" in token_set_ or "bars" in token_set_:
        head = "Ice Cream Bar"
        form = "ice cream bar"
        notes.append("form_promoted_to_head")
    elif has_phrase(tokens, "ice cream cone") or "cone" in token_set_ or "cones" in token_set_:
        head = "Ice Cream Cone"
        form = "ice cream cone"
        notes.append("form_promoted_to_head")
    elif has_phrase(tokens, "ice cream mix") or ("mix" in token_set_ and "ice" in token_set_ and "cream" in token_set_):
        head = "Ice Cream Mix"
        form = "ice cream mix"
        notes.append("form_promoted_to_head")
    elif "gelato" in token_set_:
        head = "Gelato"
        form = "gelato"
    elif "sorbet" in token_set_:
        head = "Sorbet"
        form = "sorbet"
    elif "sherbet" in token_set_:
        head = "Sherbet"
        form = "sherbet"
    elif has_phrase(tokens, "frozen yogurt") or "froyo" in token_set_:
        head = "Frozen Yogurt"
        form = "frozen yogurt"
    elif "sundae" in token_set_ or "sundaes" in token_set_:
        head = "Ice Cream Sundae"
        form = "ice cream sundae"
        notes.append("form_promoted_to_head")
    else:
        head = "Ice Cream"
        form = "ice cream"

    fat = ""
    if "light" in token_set_:
        fat = "light"
    elif "reduced" in token_set_ and "fat" in token_set_:
        fat = "reduced fat"
    elif "low" in token_set_ and "fat" in token_set_:
        fat = "low fat"

    diet: list[str] = []
    if "sugar" in token_set_ and ("free" in token_set_ or "no" in token_set_):
        diet.append("sugar_free")
    if "gluten" in token_set_ and "free" in token_set_:
        diet.append("gluten_free")

    flavor = flavor_from_tokens(tokens, drop=ICE_CREAM_FORM_WORDS | {"premium", "super"})
    proposed, existing, mint_required, parent_exists = compile_path(category_path, head, taxonomy)
    return SemanticRecord(
        fdc_id=row.get("fdc_id", ""),
        title=title,
        current_leaf=row.get("retail_leaf", ""),
        category_path=category_path,
        head=head,
        filter_attributes=compact_filters(
            flavor=flavor,
            fat=fat,
            diet=diet,
            organic="organic" in token_set_,
            brand=row_value(row, "brand_name"),
        ),
        retail_type="single",
        supercategory="Frozen",
        family="Ice Cream",
        form=form,
        base_identity=normalize_text(head),
        modifiers=[flavor] if flavor else [],
        state=["frozen"],
        claims=diet,
        parent_path=category_path,
        proposed_path=proposed,
        existing_path=existing,
        mint_required=mint_required,
        parent_exists=parent_exists,
        confidence=0.92 if existing else 0.82,
        notes=notes,
    )


def pizza_record(row: dict[str, str], taxonomy: set[str]) -> SemanticRecord:
    title = row_value(row, "title")
    bfc = row_value(row, "branded_food_category")
    tokens = tokens_for(title)
    token_set_ = set(tokens)
    singular_tokens = {singularize(token) for token in tokens}
    bfc_norm = normalize_text(bfc)
    notes: list[str] = []
    pizza_crust_product = has_phrase(tokens, "pizza crust") or has_phrase(tokens, "pizza crusts") or "crusts dough" in bfc_norm

    if "lunch snacks" in bfc_norm or (
        "lunch" in token_set_ and ({"pack", "packs", "combination", "combinations"} & token_set_)
    ):
        category_path = "Meal > Meal Kits"
        head = "Pizza Lunch Kit"
        form = "pizza lunch kit"
        notes.append("pizza_lunch_kit_not_single_pizza_or_sauce")
    elif "sauce" in singular_tokens or "sauces" in bfc_norm:
        category_path = "Pantry > Sauces & Salsas"
        head = "Pizza Sauce"
        form = "sauce"
        notes.append("pizza_adjacent_sauce_not_meal")
    elif "dough" in singular_tokens:
        category_path = "Bakery > Crust & Dough"
        head = "Pizza Dough"
        form = "dough"
        notes.append("pizza_adjacent_dough_not_meal")
    elif (
        "crust" in singular_tokens
        and pizza_crust_product
        and ("mix" in token_set_ or "mixes" in bfc_norm)
    ):
        category_path = "Pantry > Baking > Mix"
        head = "Pizza Crust Mix"
        form = "mix"
        notes.append("pizza_crust_mix_not_pizza")
    elif "crust" in singular_tokens and pizza_crust_product:
        category_path = "Bakery > Crust & Dough"
        head = "Pizza Crust"
        form = "crust"
        notes.append("pizza_crust_not_pizza")
    elif "roll" in singular_tokens:
        category_path = "Frozen > Appetizers"
        head = "Pizza Roll"
        form = "pizza roll"
        notes.append("pizza_roll_form_promoted")
    else:
        category_path = "Meal > Pizza"
        head = "Pizza"
        form = "pizza"
        notes.append("pizza_toppings_stay_filter")

    toppings = dedupe(token for token in tokens if singularize(token) in PIZZA_TOPPING_TOKENS)
    crust = dedupe(token for token in tokens if singularize(token) in CRUST_TOKENS)
    cuisine = ""
    if "italian" in token_set_:
        cuisine = "italian"
    elif "california" in token_set_:
        cuisine = "california"
    elif "mexican" in token_set_:
        cuisine = "mexican"

    proposed, existing, mint_required, parent_exists = compile_path(category_path, head, taxonomy)
    return SemanticRecord(
        fdc_id=row.get("fdc_id", ""),
        title=title,
        current_leaf=row.get("retail_leaf", ""),
        category_path=category_path,
        head=head,
        filter_attributes=compact_filters(
            toppings=toppings,
            crust=crust,
            cuisine=cuisine,
            storage=["frozen"] if "frozen" in bfc_norm or "frozen" in token_set_ else [],
            brand=row_value(row, "brand_name"),
        ),
        retail_type="composite_meal" if category_path.startswith("Meal") else "single",
        supercategory=category_path.split(" > ", 1)[0],
        family=category_path.split(" > ", 1)[1] if " > " in category_path else category_path,
        form=form,
        base_identity=normalize_text(head),
        modifiers=toppings,
        state=["frozen"] if "frozen" in bfc_norm or "frozen" in token_set_ else [],
        claims=[],
        parent_path=category_path,
        proposed_path=proposed,
        existing_path=existing,
        mint_required=mint_required,
        parent_exists=parent_exists,
        confidence=0.9 if form == "pizza" else 0.86,
        notes=notes,
    )


def produce_or_salad_record(row: dict[str, str], taxonomy: set[str]) -> SemanticRecord | None:
    title = row_value(row, "title")
    bfc = row_value(row, "branded_food_category")
    tokens = tokens_for(title)
    token_set_ = set(tokens)
    bfc_norm = normalize_text(bfc)

    if has_phrase(tokens, "salad kit") or has_phrase(tokens, "salad kits"):
        parent = "Produce > Salad Kit"
        drop = {"salad", "kit", "kits"}
        identity = clean_detail(title, branded_noise(row) | drop)
        proposed, existing, mint_required, parent_exists = compile_path(parent, identity, taxonomy)
        return SemanticRecord(
            fdc_id=row.get("fdc_id", ""),
            title=title,
            current_leaf=row.get("retail_leaf", ""),
            category_path=parent,
            head="Salad Kit",
            filter_attributes=compact_filters(
                flavor=normalize_text(identity),
                brand=row_value(row, "brand_name"),
            ),
            retail_type="kit",
            supercategory="Produce",
            family="Salad Kit",
            form="salad kit",
            base_identity=normalize_text(identity),
            modifiers=[],
            state=[],
            claims=[],
            parent_path=parent,
            proposed_path=proposed,
            existing_path=existing,
            mint_required=mint_required,
            parent_exists=parent_exists,
            confidence=0.86,
            notes=["salad_kit_not_generic_meal"],
        )

    if "apple" in token_set_ or "apples" in token_set_:
        parent = "Produce > Fruit"
        identity = "apple"
        proposed, existing, mint_required, parent_exists = compile_path(parent, identity, taxonomy)
        if not existing and "Produce > Apple" in taxonomy:
            proposed = existing = "Produce > Apple"
            mint_required = False
            parent_exists = True
        notes = ["apple_identity"]
        if "crisp" in token_set_ and ("apple" in token_set_ or "apples" in token_set_):
            notes.append("crisp_kept_as_variety_not_dish")
        return SemanticRecord(
            fdc_id=row.get("fdc_id", ""),
            title=title,
            current_leaf=row.get("retail_leaf", ""),
            category_path=parent,
            head="Apple",
            filter_attributes=compact_filters(
                variety="honey crisp" if has_phrase(tokens, "honey crisp") else "",
                state=["dried"] if "dried" in token_set_ else [],
                brand=row_value(row, "brand_name"),
            ),
            retail_type="single",
            supercategory="Produce",
            family="Fruit",
            form="fruit",
            base_identity=identity,
            modifiers=[],
            state=["dried"] if "dried" in token_set_ else [],
            claims=[],
            parent_path=parent,
            proposed_path=proposed,
            existing_path=existing,
            mint_required=mint_required,
            parent_exists=parent_exists,
            confidence=0.9 if "produce" in bfc_norm or "fruit" in bfc_norm or "snack" in bfc_norm else 0.78,
            notes=notes,
        )

    return None


def meal_record(row: dict[str, str], taxonomy: set[str]) -> SemanticRecord:
    title = row_value(row, "title")
    tokens = tokens_for(title)
    token_set_ = set(tokens)
    singular_tokens = {singularize(token) for token in tokens}
    bfc_norm = normalize_text(row_value(row, "branded_food_category"))
    notes: list[str] = ["meal_context_blocks_single_ingredient_routers"]

    if "kit" in token_set_ or "kits" in token_set_:
        parent = "Meal > Meal Kits"
        form = "meal kit"
        drop = {"kit", "kits", "meal", "meals", "dinner"}
    elif (
        "sandwich" in singular_tokens
        or "sub" in singular_tokens
        or "prepared subs sandwiches" in bfc_norm
        or "prepared wraps" in bfc_norm
    ):
        parent = "Meal > Sandwich"
        form = "sandwich"
        drop = {"sandwich", "sandwiches", "sub", "subs"}
    elif "wrap" in singular_tokens:
        parent = "Meal > Sandwich > Wrap"
        form = "wrap"
        drop = {"wrap", "wraps"}
    elif "burrito" in singular_tokens:
        parent = "Meal > Burrito"
        form = "burrito"
        drop = {"burrito", "burritos"}
    elif "bowl" in singular_tokens:
        parent = "Meal > Bowls"
        form = "bowl"
        drop = {"bowl", "bowls"}
    elif {"spaghetti", "pasta", "manicotti"} & token_set_:
        parent = "Meal > Pasta Dishes"
        form = "pasta dish"
        drop = {"spaghetti", "pasta", "manicotti", "ring", "rings"}
    else:
        parent = "Meal > Entrees"
        form = "entree"
        drop = {"meal", "meals", "frozen"}

    if "huevos" in token_set_ and "rancheros" in token_set_:
        identity = "huevos rancheros"
        notes.append("dish_identity_from_title_phrase")
    elif "spaghetti" in token_set_ and ("ring" in token_set_ or "rings" in token_set_):
        identity = "spaghetti rings"
        notes.append("spaghettios_normalized_to_spaghetti_rings")
    else:
        identity = normalize_text(clean_detail(title, branded_noise(row) | drop))

    if identity in {"huevos rancheros", "spaghetti rings"}:
        head = title_case(identity)
    elif form in {"sandwich", "wrap", "burrito", "bowl", "meal kit"}:
        head = title_case(form)
    elif "meatloaf" in singular_tokens:
        head = "Meatloaf"
    elif "french" in singular_tokens and "toast" in singular_tokens:
        head = "French Toast Bake" if "bake" in singular_tokens else "French Toast"
    elif "kugel" in singular_tokens:
        head = "Kugel"
    elif "dip" in singular_tokens:
        head = "Dip"
    elif "bean" in singular_tokens:
        head = "Bean Entree"
    else:
        head = title_case(form)

    protein = dedupe(
        token
        for token in tokens
        if singularize(token) in {"beef", "chicken", "pork", "turkey", "lamb", "bean", "tofu"}
    )
    cuisine = ""
    if "mexican" in singular_tokens:
        cuisine = "mexican"
    elif "italian" in singular_tokens:
        cuisine = "italian"
    elif "hawaiian" in singular_tokens:
        cuisine = "hawaiian"
    elif "greek" in singular_tokens:
        cuisine = "greek"

    proposed, existing, mint_required, parent_exists = compile_path(parent, head, taxonomy)
    return SemanticRecord(
        fdc_id=row.get("fdc_id", ""),
        title=title,
        current_leaf=row.get("retail_leaf", ""),
        category_path=parent,
        head=head,
        filter_attributes=compact_filters(
            dish_detail=identity if normalize_text(head) != identity else "",
            protein=protein,
            cuisine=cuisine,
            storage=["frozen"] if "frozen" in token_set(row_value(row, "branded_food_category")) else [],
            brand=row_value(row, "brand_name"),
        ),
        retail_type="composite_meal",
        supercategory="Meal",
        family=parent.split(" > ", 1)[1] if " > " in parent else "Meal",
        form=form,
        base_identity=normalize_text(head),
        modifiers=[identity] if identity and normalize_text(head) != identity else [],
        state=["frozen"] if "frozen" in token_set(row_value(row, "branded_food_category")) else [],
        claims=[],
        parent_path=parent,
        proposed_path=proposed,
        existing_path=existing,
        mint_required=mint_required,
        parent_exists=parent_exists,
        confidence=0.84 if parent_exists else 0.76,
        notes=notes,
    )


def is_meal_context(row: dict[str, str]) -> bool:
    title = row_value(row, "title")
    title_tokens = set(tokens_for(title))
    title_norm = normalize_text(title)
    bfc_norm = normalize_text(row_value(row, "branded_food_category"))
    if (
        "cornmeal" in title_tokens
        or has_phrase(tokens_for(title), "corn meal")
        or has_phrase(tokens_for(title), "cake meal")
        or has_phrase(tokens_for(title), "matzo meal")
        or has_phrase(tokens_for(title), "matzoh meal")
        or "oatmeal" in title_tokens
        or has_phrase(tokens_for(title), "oat meal")
    ):
        return False
    if {"bar", "bars"} & title_tokens and ("bar" in bfc_norm or "snack energy granola bars" in bfc_norm):
        return False
    if "mix" in title_tokens and "cake cookie and cupcake mixes" in bfc_norm:
        return False
    if "grain" in title_tokens or "grains" in title_tokens:
        if "breakfast sandwiches" in bfc_norm:
            return False
    if {"biscuit", "biscuits"} & title_tokens and "breakfast sandwiches biscuits" in bfc_norm:
        return False
    if {"roll", "rolls", "bun", "buns", "bread", "breads"} & title_tokens and (
        "bread" in bfc_norm or "breads buns" in bfc_norm
    ):
        return False
    if "breakfast drinks" in bfc_norm and "meal" in title_tokens:
        return False
    if "meal" in title_tokens and any(hint in bfc_norm for hint in MEAL_FALSE_FRIEND_BFC_HINTS):
        return False
    if "meal" in title_norm and "replacement" in title_tokens:
        return False
    if any(hint in bfc_norm for hint in MEAL_BFC_HINTS):
        return True
    if "candy" in bfc_norm:
        return False
    return bool({"meal", "meals", "entree", "entrees", "bowl", "sandwich", "wrap", "burrito"} & title_tokens)


def is_beverage_context(row: dict[str, str]) -> bool:
    text = normalize_text(
        " ".join([row_value(row, "title"), row_value(row, "branded_food_category"), row_value(row, "current_esha_desc")])
    )
    return any(term in text for term in ["beverage", "drink", "juice", "water", "tea", "seltzer", "sparkling", "mixer", "infusion"])


def is_ice_cream_context(row: dict[str, str]) -> bool:
    title = row_value(row, "title")
    title_norm = normalize_text(title)
    tokens = tokens_for(title)
    bfc_norm = normalize_text(row_value(row, "branded_food_category"))
    if any(
        hint in bfc_norm
        for hint in (
            "biscuits cookies",
            "cookies biscuits",
            "energy protein muscle recovery",
            "protein muscle recovery",
        )
    ):
        return False
    if "candy" in bfc_norm and "ice cream" not in title_norm:
        return False
    if bfc_norm == "ice cream frozen yogurt":
        return True
    return (
        has_phrase(tokens, "ice cream")
        or has_phrase(tokens, "frozen yogurt")
        or bool({"gelato", "sorbet", "sherbet", "froyo"} & set(tokens))
    )


def is_pizza_context(row: dict[str, str]) -> bool:
    title_norm = normalize_text(row_value(row, "title"))
    bfc_norm = normalize_text(row_value(row, "branded_food_category"))
    if "candy" in bfc_norm:
        return False
    if "pizza" in title_norm:
        return True
    return bfc_norm == "pizza"


def classify_row(row: dict[str, str], taxonomy: set[str]) -> SemanticRecord:
    bfc_norm = normalize_text(row_value(row, "branded_food_category"))

    produce = produce_or_salad_record(row, taxonomy)
    if produce and ("salad_kit_not_generic_meal" in produce.notes or "crisp_kept_as_variety_not_dish" in produce.notes):
        return produce
    if "candy" in bfc_norm:
        return candy_record(row, taxonomy)
    if is_ice_cream_context(row):
        return ice_cream_record(row, taxonomy)
    if is_pizza_context(row):
        return pizza_record(row, taxonomy)
    if is_meal_context(row):
        return meal_record(row, taxonomy)
    if is_beverage_context(row):
        return beverage_record(row, taxonomy)
    if produce:
        return produce

    parent = row_value(row, "retail_leaf").rsplit(" > ", 1)[0] or "Other > Unclassified"
    identity = clean_detail(row_value(row, "title"), branded_noise(row))
    proposed, existing, mint_required, parent_exists = compile_path(parent, identity, taxonomy)
    return SemanticRecord(
        fdc_id=row_value(row, "fdc_id"),
        title=row_value(row, "title"),
        current_leaf=row_value(row, "retail_leaf"),
        category_path=parent,
        head=title_case(identity),
        filter_attributes=compact_filters(brand=row_value(row, "brand_name")),
        retail_type="unknown",
        supercategory=parent.split(" > ", 1)[0],
        family=parent,
        form="",
        base_identity=normalize_text(identity),
        modifiers=[],
        state=[],
        claims=[],
        parent_path=parent,
        proposed_path=proposed,
        existing_path=existing,
        mint_required=mint_required,
        parent_exists=parent_exists,
        confidence=0.45,
        notes=["fallback_record"],
    )


def read_target_rows(path: Path, fdc_ids: set[str], limit: int = 0) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with path.open(errors="replace", newline="") as handle:
        for row in csv.DictReader(handle):
            if fdc_ids and row.get("fdc_id") not in fdc_ids:
                continue
            rows.append(row)
            if limit and len(rows) >= limit:
                break
    return rows


def write_outputs(records: list[SemanticRecord], jsonl_path: Path, mints_path: Path) -> None:
    jsonl_path.parent.mkdir(parents=True, exist_ok=True)
    with jsonl_path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(asdict(record), sort_keys=True) + "\n")

    mint_fields = [
        "fdc_id",
        "title",
        "current_leaf",
        "category_path",
        "head",
        "filter_attributes",
        "parent_path",
        "proposed_path",
        "base_identity",
        "form",
        "retail_type",
        "parent_exists",
        "confidence",
        "notes",
    ]
    with mints_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=mint_fields)
        writer.writeheader()
        for record in records:
            if not record.mint_required:
                continue
            row = asdict(record)
            row["filter_attributes"] = json.dumps(record.filter_attributes, sort_keys=True)
            row["notes"] = "|".join(record.notes)
            writer.writerow({field: row.get(field, "") for field in mint_fields})


def main() -> None:
    parser = argparse.ArgumentParser(description="Prototype semantic labeler for retail leaves.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--taxonomy", type=Path, default=DEFAULT_TAXONOMY)
    parser.add_argument("--fdc-ids", default=",".join(DEFAULT_FDCS))
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--jsonl-out", type=Path, default=DEFAULT_JSONL)
    parser.add_argument("--mints-out", type=Path, default=DEFAULT_MINTS)
    args = parser.parse_args()

    taxonomy = load_taxonomy(args.taxonomy)
    fdc_ids = {value.strip() for value in args.fdc_ids.split(",") if value.strip()}
    rows = read_target_rows(args.input, fdc_ids, args.limit)
    records = [classify_row(row, taxonomy) for row in rows]
    records.sort(key=lambda record: DEFAULT_FDCS.index(record.fdc_id) if record.fdc_id in DEFAULT_FDCS else 9999)
    write_outputs(records, args.jsonl_out, args.mints_out)

    print(f"rows: {len(records)}")
    print(f"mint_required: {sum(1 for record in records if record.mint_required)}")
    print(f"jsonl: {args.jsonl_out}")
    print(f"mints: {args.mints_out}")
    for record in records:
        status = "MINT" if record.mint_required else "EXISTING"
        print(f"{record.fdc_id}: {status} {record.proposed_path}  notes={','.join(record.notes)}")


if __name__ == "__main__":
    main()
