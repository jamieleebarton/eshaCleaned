#!/usr/bin/env python3
"""Quantify recipe-side normalization risks in recipe_qa.db.

This is a deliberately conservative scanner. It is meant to size the failure
classes we should force the LLM prompt and validator to handle; it is not a
replacement for model review.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import Callable, Iterable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = Path("/Users/jamiebarton/Desktop/clean/data/recipe_qa.db")
DEFAULT_OUT = ROOT / "implementation" / "output" / "recipe_normalization_risk_quantification.csv"


@dataclass
class IngredientLine:
    recipe_id: int
    recipe_name: str
    line_index: int
    display: str
    item: str
    grams: float | None

    @cached_property
    def text(self) -> str:
        return f"{self.display} {self.item}".lower()

    def example(self) -> str:
        return (
            f"{self.recipe_id} {self.recipe_name}: {self.display}"
            f" -> item={self.item} grams={self.grams if self.grams is not None else ''}"
        )


@dataclass(frozen=True)
class RiskClass:
    name: str
    required_policy: str
    matcher: Callable[[IngredientLine], bool]


def rx(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern, re.I)


FRACTION_RANGE_RE = rx(r"\b\d+\s*(?:-|–|—|to)\s*\d+\b")
DECIMAL_RANGE_RE = rx(r"\b\d+(?:\.\d+)?\s*(?:-|–|—|to)\s*\d+(?:\.\d+)?\b")
QUANTITY_LB_RE = rx(r"\b\d+(?:\.\d+)?\s*(?:lb|lbs|pound|pounds)\b")
PROCESS_MEDIUM_FOOD_RE = rx(r"\b(?:oil|shortening|lard|fat)\b")
PROCESS_MEDIUM_ROLE_RE = rx(r"\b(?:for frying|deep[- ]frying|to fry|frying oil|for deep fryer)\b")
COATING_FOOD_RE = rx(r"\b(?:flour|cornmeal|starch|breadcrumbs?|bread crumbs?|sugar|powdered sugar)\b")
COATING_ROLE_RE = rx(r"\b(?:for dusting|for dredging|for coating|to dredge|to coat|work surface|rolling surface|seasoned with salt)")
SALT_RE = rx(r"\bsalt\b")
SALT_WATER_RE = rx(r"\b(?:boiling water|pasta water|cooking water|for boiling)\b")
GARNISH_RE = rx(r"\b(?:for garnish|garnish with|to garnish|as garnish|optional garnish)\b")
SERVING_RE = rx(r"\b(?:for serving|to serve|serve with|served with|for accompaniment)\b")
TRUE_ALT_RE = rx(r"\b(?:or|either|any of|your choice|substitute)\b")
ALT_NEGATION_RE = rx(r"\b(?:not|do not|without)\b")
STATE_WORD = r"(fresh|frozen|canned|dry|dried)"
STATE_ALT_NEAR_RE = rx(rf"\b{STATE_WORD}\b\s+(?:or|/)\s+\b{STATE_WORD}\b")
STATE_NOUN_ALT_RE = rx(rf"\b{STATE_WORD}\b\s+[a-z][a-z -]{{0,50}}\s+(?:or|/)\s+\b{STATE_WORD}\b")
NOUN_STATE_ALT_RE = rx(rf"\b[a-z][a-z -]{{0,50}},?\s+\b{STATE_WORD}\b\s+(?:or|/)\s+\b{STATE_WORD}\b")
SALT_AND_PEPPER_RE = rx(r"\bsalt\s*(?:and|&)\s*pepper\b|\bpepper\s*(?:and|&)\s*salt\b")
CITRUS_JUICE_ZEST_RE = rx(r"\b(?:juice\s*(?:and|&)\s*zest|zest\s*(?:and|&)\s*juice|rind\s*(?:and|&)\s*juice)\b")
CITRUS_RE = rx(r"\b(?:lemon|lime|orange|citrus)\b")
HAM_RE = rx(r"\bham\b|\bham hocks?\b")
APPLE_RE = rx(r"\bapples?\b")
APPLE_CONTEXT_RE = rx(r"\b(?:granny smith|honeycrisp|crabapples?|tart|cooking|baking|pie apples?)\b")
CORN_RE = rx(r"\bcorn\b")
CORN_STATE_RE = rx(r"\b(?:fresh|frozen|canned|creamed|whole kernel|niblets?)\b")

BRAND_RE = rx(
    r"\b("
    r"rotel|cool whip|philadelphia|jell-?o|ritz|kraft|oscar mayer|lipton|"
    r"campbell'?s?|lawry'?s?|tony chachere'?s?|splenda|crisco|velveeta|ragu"
    r")\b"
)

NON_FOOD_RE = rx(
    r"\b("
    r"barbecue skewers?|bamboo skewers?|wooden skewers?|metal skewers?|skewers?|"
    r"toothpicks?|aluminum foil|heavy-duty foil|foil|parchment(?: paper)?|"
    r"wax(?:ed)? paper|plastic wrap|cheesecloth|kitchen twine|butcher'?s twine|"
    r"cotton string|string|paper towels?|clean towels?|coffee filters?|"
    r"muffin liners?|cupcake liners?|casing|casings|hog casing|collagen casing|"
    r"dry rocks?|firewood|charcoal|newspaper|pencils?|jars? for canning|"
    r"lids?|rubber bands?"
    r")\b"
)

FOOD_CONTAINER_ONLY_RE = rx(
    r"\b(?:can|cans|jar|jars|package|packages|pkg|bottle|box|bag)\b"
)


def contains_any(text: str, words: Iterable[str]) -> bool:
    return any(word in text for word in words)


def is_process_medium_oil_for_frying(line: IngredientLine) -> bool:
    text = line.text
    return bool(PROCESS_MEDIUM_FOOD_RE.search(text) and PROCESS_MEDIUM_ROLE_RE.search(text))


def is_process_coating(line: IngredientLine) -> bool:
    text = line.text
    return bool(COATING_FOOD_RE.search(text) and COATING_ROLE_RE.search(text))


def is_salt_for_water(line: IngredientLine) -> bool:
    text = line.text
    return bool(SALT_RE.search(text) and SALT_WATER_RE.search(text))


def is_garnish(line: IngredientLine) -> bool:
    return bool(GARNISH_RE.search(line.text))


def is_serving_accompaniment(line: IngredientLine) -> bool:
    return bool(SERVING_RE.search(line.text))


def is_non_food(line: IngredientLine) -> bool:
    text = line.text
    if not NON_FOOD_RE.search(text):
        return False
    # Packaging words alone are not non-food. "1 jar marshmallow creme" is food
    # with package metadata, while "jars for canning" is equipment.
    if FOOD_CONTAINER_ONLY_RE.fullmatch(line.item.strip().lower()):
        return True
    return True


def is_true_alternative(line: IngredientLine) -> bool:
    text = line.text
    if not TRUE_ALT_RE.search(text):
        return False
    if ALT_NEGATION_RE.search(text):
        return False
    return True


def is_fresh_frozen_canned_alternative(line: IngredientLine) -> bool:
    text = line.text
    for pattern in (STATE_ALT_NEAR_RE, STATE_NOUN_ALT_RE, NOUN_STATE_ALT_RE):
        for match in pattern.finditer(text):
            states = {group for group in match.groups() if group}
            if len(states) >= 2:
                return True
    return False


def is_salt_and_pepper(line: IngredientLine) -> bool:
    return bool(SALT_AND_PEPPER_RE.search(line.text))


def is_citrus_juice_zest(line: IngredientLine) -> bool:
    text = line.text
    return bool(CITRUS_JUICE_ZEST_RE.search(text) and CITRUS_RE.search(text))


def is_quantity_range(line: IngredientLine) -> bool:
    return bool(FRACTION_RANGE_RE.search(line.display) or DECIMAL_RANGE_RE.search(line.display))


def is_large_ham_quantity(line: IngredientLine) -> bool:
    text = line.text
    return bool(HAM_RE.search(text) and QUANTITY_LB_RE.search(text))


def is_apple_baking_or_variety(line: IngredientLine) -> bool:
    text = line.text
    return bool(APPLE_RE.search(text) and APPLE_CONTEXT_RE.search(text))


def is_corn_storage_state(line: IngredientLine) -> bool:
    text = line.text
    return bool(CORN_RE.search(text) and CORN_STATE_RE.search(text))


def is_brand_cleanup(line: IngredientLine) -> bool:
    return bool(BRAND_RE.search(line.text))


def is_bare_ambiguous(line: IngredientLine) -> bool:
    item = line.item.strip().lower()
    return item in {
        "cheese",
        "nuts",
        "nut",
        "pasta",
        "cream",
        "chocolate",
        "berries",
        "berry",
        "oil",
        "pepper",
        "chili",
        "stock",
        "beans",
        "apple",
        "apples",
    }


def is_zero_or_missing_grams(line: IngredientLine) -> bool:
    return line.grams is None or line.grams <= 0


RISK_CLASSES = [
    RiskClass("process_medium_oil_for_frying", "uptake_policy_required", is_process_medium_oil_for_frying),
    RiskClass("process_coating_flour_dusting", "retention_policy_required", is_process_coating),
    RiskClass("process_cooking_water_salt", "sodium_absorption_policy_required", is_salt_for_water),
    RiskClass("garnish_herbs_or_visual", "garnish_policy_required", is_garnish),
    RiskClass("serving_accompaniment", "serving_selection_required", is_serving_accompaniment),
    RiskClass("non_food_equipment_supply", "excluded_non_food", is_non_food),
    RiskClass("true_alternative_or_any", "selected_option_required", is_true_alternative),
    RiskClass("fresh_frozen_canned_alternative", "state_alternative_required", is_fresh_frozen_canned_alternative),
    RiskClass("salt_and_pepper_component", "component_split_required", is_salt_and_pepper),
    RiskClass("citrus_juice_zest_split", "component_split_required", is_citrus_juice_zest),
    RiskClass("quantity_range", "range_policy_required", is_quantity_range),
    RiskClass("large_ham_quantity", "quantity_and_yield_preservation", is_large_ham_quantity),
    RiskClass("apple_baking_or_variety", "variety_or_culinary_use_preservation", is_apple_baking_or_variety),
    RiskClass("corn_storage_state", "storage_form_preservation", is_corn_storage_state),
    RiskClass("brand_cleanup_needed", "brand_to_generic_translation", is_brand_cleanup),
    RiskClass("bare_ambiguous_item", "recipe_context_required", is_bare_ambiguous),
    RiskClass("zero_or_missing_grams", "quantity_missing_or_zero", is_zero_or_missing_grams),
]


def iter_lines(db_path: Path) -> Iterable[IngredientLine]:
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.execute(
            """
            SELECT recipe_id, recipe_name, ingredients_json
            FROM recipe_verdicts
            WHERE ingredients_json IS NOT NULL AND ingredients_json != ''
            ORDER BY recipe_id
            """
        )
        for recipe_id, recipe_name, ingredients_json in cursor:
            try:
                ingredients = json.loads(ingredients_json)
            except json.JSONDecodeError:
                continue
            if not isinstance(ingredients, list):
                continue
            for idx, ing in enumerate(ingredients):
                if not isinstance(ing, dict):
                    continue
                grams = ing.get("grams")
                try:
                    grams = float(grams)
                except (TypeError, ValueError):
                    grams = None
                yield IngredientLine(
                    recipe_id=int(recipe_id),
                    recipe_name=str(recipe_name or ""),
                    line_index=idx,
                    display=str(ing.get("display") or ""),
                    item=str(ing.get("item") or ""),
                    grams=grams,
                )
    finally:
        conn.close()


def build_quantification(db_path: Path) -> tuple[int, list[dict[str, str | int | float]]]:
    stats = {
        risk.name: {
            "lines": 0,
            "recipes": set(),
            "examples": [],
            "required_policy": risk.required_policy,
        }
        for risk in RISK_CLASSES
    }
    total_lines = 0
    for line in iter_lines(db_path):
        total_lines += 1
        for risk in RISK_CLASSES:
            if not risk.matcher(line):
                continue
            bucket = stats[risk.name]
            bucket["lines"] += 1
            bucket["recipes"].add(line.recipe_id)
            if len(bucket["examples"]) < 5:
                bucket["examples"].append(line.example())

    rows: list[dict[str, str | int | float]] = []
    for risk in RISK_CLASSES:
        bucket = stats[risk.name]
        line_count = int(bucket["lines"])
        rows.append(
            {
                "class": risk.name,
                "line_count": line_count,
                "recipe_count": len(bucket["recipes"]),
                "line_percent": round((line_count / total_lines) * 100, 4) if total_lines else 0,
                "required_policy": str(bucket["required_policy"]),
                "examples": " || ".join(bucket["examples"]),
            }
        )
    return total_lines, rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    total_lines, rows = build_quantification(args.db)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["class", "line_count", "recipe_count", "line_percent", "required_policy", "examples"],
        )
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps({"total_lines": total_lines, "classes": len(rows), "out": str(args.out)}, indent=2))


if __name__ == "__main__":
    main()
