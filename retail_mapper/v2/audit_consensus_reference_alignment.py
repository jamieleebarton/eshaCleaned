#!/usr/bin/env python3
"""Audit FNDDS/SR28/ESHA conceptual alignment for consensus rows.

This does not assume the retail path is always correct. It uses the SKU title,
BFC, consensus path, and the prior right-place issue inventory as context, then
flags reference mappings that look like component/proxy matches instead of the
closest conceptual food.
"""
from __future__ import annotations

import csv
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable


V2 = Path(__file__).resolve().parent
SRC = V2 / "consensus_full_corpus_audit.csv"
RIGHT_PLACE = V2 / "consensus_right_place_issue_inventory.csv"
OUT_CSV = V2 / "consensus_reference_alignment_issue_inventory.csv"
OUT_REMAP = V2 / "consensus_reference_remap_candidates.csv"
OUT_SUMMARY = V2 / "consensus_reference_alignment_summary.json"
OUT_MD = V2 / "consensus_reference_alignment.md"

csv.field_size_limit(sys.maxsize)

REFERENCE_FIELDS = {
    "fndds": "fndds_desc",
    "sr28": "sr28_desc",
    "esha": "esha_desc",
    "matched_key": "matched_key",
}

COOKIE_CRACKER_BFCS = {
    "biscuits/cookies",
    "biscuits/cookies (shelf stable)",
    "cookies & biscuits",
    "crackers & biscotti",
}

PREPARED_SANDWICH_BFCS = {
    "prepared subs & sandwiches",
    "prepared sandwiches",
    "sandwiches/filled rolls/wraps",
}

STOPWORDS = {
    "and",
    "with",
    "the",
    "for",
    "from",
    "style",
    "flavor",
    "flavored",
    "plain",
    "original",
    "regular",
    "classic",
    "prepared",
    "commercially",
    "includes",
    "include",
    "food",
    "foods",
    "product",
    "products",
    "frozen",
    "fresh",
    "raw",
    "cooked",
    "ready",
    "to",
    "eat",
    "oz",
    "lb",
    "ct",
    "count",
}


@dataclass(frozen=True)
class ReferenceRule:
    issue_family: str
    severity: str
    confidence: str
    action_type: str
    likely_fix: str
    rationale: str
    row_predicate: Callable[[dict[str, str]], bool]
    field_predicate: Callable[[dict[str, str], str, str], bool]


def has(text: str, pattern: str) -> bool:
    return bool(re.search(pattern, text or "", re.I))


def row_has(row: dict[str, str], field: str, pattern: str) -> bool:
    return has(row.get(field, "") or "", pattern)


def title_has(row: dict[str, str], pattern: str) -> bool:
    return row_has(row, "title", pattern)


def bfc(row: dict[str, str]) -> str:
    return (row.get("branded_food_category") or "").strip()


def bfc_lower(row: dict[str, str]) -> str:
    return bfc(row).lower()


def path(row: dict[str, str]) -> str:
    return row.get("retail_leaf_path", "") or ""


def canonical(row: dict[str, str]) -> str:
    return row.get("canonical_path", "") or ""


def path_starts(row: dict[str, str], *prefixes: str) -> bool:
    p = path(row)
    return any(p.startswith(prefix) for prefix in prefixes)


def canonical_starts(row: dict[str, str], *prefixes: str) -> bool:
    p = canonical(row)
    return any(p.startswith(prefix) for prefix in prefixes)


def any_row_text(row: dict[str, str]) -> str:
    return " ".join([
        row.get("title", "") or "",
        row.get("branded_food_category", "") or "",
        row.get("canonical_path", "") or "",
        row.get("retail_leaf_path", "") or "",
        row.get("product_identity_fixed", "") or "",
    ])


def token_key(text: str) -> set[str]:
    tokens = re.findall(r"[a-z0-9]+", (text or "").lower())
    out: set[str] = set()
    for token in tokens:
        if token in STOPWORDS or len(token) <= 2:
            continue
        if len(token) > 4 and token.endswith("ies"):
            token = token[:-3] + "y"
        elif len(token) > 4 and token.endswith("s") and not token.endswith(("ss", "us", "is")):
            token = token[:-1]
        out.add(token)
    return out


def overlap_score(row: dict[str, str], text: str) -> float:
    target = token_key(" ".join([
        row.get("title", "") or "",
        row.get("canonical_path", "") or "",
        row.get("retail_leaf_path", "") or "",
        row.get("product_identity_fixed", "") or "",
    ]))
    ref = token_key(text)
    if not target or not ref:
        return 0.0
    return len(target & ref) / len(ref)


def ref_value(row: dict[str, str], ref_name: str) -> str:
    return row.get(REFERENCE_FIELDS[ref_name], "") or ""


def bad_reference_blob(row: dict[str, str], bad_fields: Iterable[str]) -> str:
    return " | ".join(
        f"{field}: {ref_value(row, field)}"
        for field in bad_fields
        if ref_value(row, field)
    )


def has_bread_carrier_reference(text: str) -> bool:
    return (
        has(text, r"\b(bun|buns|rolls?|bagels?|bread|croissant|english\s+muffin|hamburger\s+bun|hot\s*dog\s+bun)\b")
        and not has(text, r"\b(sandwich|sub|burger|hot\s*dog|burrito|wrap|pocket|bao|stuffed|barbecue\s+pork)\b")
        and not has(text, r"\bfast\s+foods?\b")
        and not has(text, r"\b(with|and)\s+(egg|eggs|cheese|sausage|bacon|ham|canadian\s+bacon|chicken|beef|pepperoni)\b")
    )


def has_wrong_stuffed_bun_reference(text: str) -> bool:
    return has(text, r"\b(cinnamon\s+buns?|honey\s+buns?|hamburger\s+bun|sandwich\s+bun|dinner\s+rolls?)\b")


def has_plain_seafood_reference(text: str) -> bool:
    return (
        has(text, r"\b(clam|lobster|shrimp|crab|oyster|squid|salmon|tuna|cod|fish|shellfish)\b")
        and not has(text, r"\b(soup|chowder|bisque|gumbo|broth|stock|bouillon|consomme|base|dip|sauce|seasoning|rub|marinade|boil|paste)\b")
    )


def has_plain_meat_reference(text: str) -> bool:
    return (
        has(text, r"\b(chicken|beef|pork|turkey|ham|sausage|bacon)\b")
        and not has(text, r"\b(sandwich|soup|salad|dip|sauce|seasoning|rub|marinade|boil|paste|meal|entree|burrito|taco|broth|stock|bouillon|consomme|base)\b")
    )


def has_component_salad_kit_reference(text: str) -> bool:
    return has(text, r"\b(croutons?|dressing|parmesan|romaine lettuce|lettuce|tortilla strips?|salad topping|salad topper)\b") and not has(text, r"\bsalad\b")


def has_dairy_milk_reference(text: str) -> bool:
    return has(text, r"\b(milk|dairy)\b") and not has(
        text,
        r"\b(non[-\s]?dairy|dairy[-\s]?free|milk\s+substitute|almond|oat|soy|soya|cashew|coconut|rice|pea|hemp|flax|macadamia|walnut|plant)\b",
    )


def has_dairy_butter_reference(text: str) -> bool:
    return has(text, r"\bbutter\b") and not has(text, r"\b(peanut|almond|cashew|hazelnut|seed|sunflower|sesame|tahini|nut)\b")


def has_baking_mix_proxy_reference(text: str) -> bool:
    return has(text, r"\b(wheat\s+flour|all-purpose\s+flour|baking\s+powder|starch\s+with\s+baking|cake\s+mix|muffin\s+mix)\b")


def has_meal_sandwich_reference(text: str) -> bool:
    return has(text, r"\b(sandwich|sub|burger|hamburger|cheeseburger|hot\s*dog)\b") and not has(
        text,
        r"\b(cookie|cookies|cracker|crackers|biscuit|biscotti|creme)\b",
    )


def is_beverage_creamer_or_coffee(row: dict[str, str]) -> bool:
    return (
        path_starts(row, "Beverage > Coffee Creamer", "Beverage > Coffee")
        or title_has(row, r"\b(creamer|coffee|latte|cold\s*brew|espresso|cappuccino|iced\s+coffee)\b")
        and bfc(row) in {"Milk Additives", "Other Drinks", "Coffee", "Powdered Drinks"}
    )


def is_sandwich_or_filled_bun_product(row: dict[str, str]) -> bool:
    return (
        bfc_lower(row) in PREPARED_SANDWICH_BFCS
        or bfc(row)
        in {
            "Breakfast Sandwiches, Biscuits & Meals",
            "Frozen Breakfast Sandwiches, Biscuits & Meals",
            "Frozen Appetizers & Hors D'oeuvres",
            "Ready-Made Combination Meals",
        }
        or path_starts(row, "Frozen > Appetizers > Stuffed Buns")
        or (
            title_has(row, r"\b(sandwich|sub|panini|stuffed\s+bun|pork\s+bun|bao)\b")
            and not bfc_lower(row) in COOKIE_CRACKER_BFCS
            and not bfc(row) in {"Breads & Buns", "Frozen Bread & Dough", "Bread & Muffin Mixes"}
            and not path_starts(row, "Bakery > Tortillas")
        )
        or (
            path_starts(row, "Meal > Breakfast Sandwiches")
            and title_has(row, r"\b(egg|eggs|cheese|sausage|bacon|ham|turkey|steak|canadian\s+bacon)\b")
        )
    )


def is_salad_kit_product(row: dict[str, str]) -> bool:
    return title_has(row, r"\bsalad\s+kit\b") or path_starts(row, "Produce > Salad Kits")


def is_soup_or_chowder_product(row: dict[str, str]) -> bool:
    return (
        bfc(row) in {"Other Soups", "Canned Soup"}
        or (title_has(row, r"\b(soup|chowder|bisque|gumbo)\b") and not title_has(row, r"\bcrackers?\b"))
        or path_starts(row, "Pantry > Soup", "Pantry > Soups")
    )


def is_dip_sauce_seasoning_product(row: dict[str, str]) -> bool:
    return (
        bfc(row)
        in {
            "Dips & Salsa",
            "Dips & Spreads",
            "Herbs & Spices",
            "Herbs/Spices/Extracts",
            "Other Cooking Sauces",
            "Seasoning Mixes, Salts, Marinades & Tenderizers",
        }
        or path_starts(row, "Pantry > Dips", "Pantry > Sauces", "Pantry > Spices & Seasonings")
    )


def is_cookie_or_cracker_product(row: dict[str, str]) -> bool:
    return bfc_lower(row) in COOKIE_CRACKER_BFCS or path_starts(row, "Bakery > Cookies", "Snack > Crackers")


def is_tortilla_product(row: dict[str, str]) -> bool:
    return path_starts(row, "Bakery > Tortillas") or (
        title_has(row, r"\b(tortilla|taco\s+shell|wraps?)\b")
        and not title_has(row, r"\b(chips?|strips?|crisps?|snack\s+mix|party\s+mix)\b")
    )


def is_nut_butter_product(row: dict[str, str]) -> bool:
    return bfc(row) == "Nut & Seed Butters" or path_starts(row, "Pantry > Nut Butters")


def is_canned_or_frozen_vegetable_product(row: dict[str, str]) -> bool:
    return (
        path_starts(row, "Pantry > Canned Vegetables", "Frozen > Vegetables")
        or bfc(row) in {"Canned Vegetables", "Frozen Vegetables"}
    )


def is_ice_cream_cone_product(row: dict[str, str]) -> bool:
    return path_starts(row, "Snack > Ice Cream Cones") or title_has(row, r"\bice\s+cream\s+cones?\b")


def is_pie_crust_or_shell_product(row: dict[str, str]) -> bool:
    return path_starts(row, "Bakery > Pie Crusts", "Pantry > Baking Mixes > Pie Crust Mix") or title_has(
        row,
        r"\bpie\s+(crust|crusts|shell|shells)\b",
    )


RULES: list[ReferenceRule] = [
    ReferenceRule(
        issue_family="beverage_or_creamer_has_bakery_flour_reference",
        severity="high",
        confidence="high",
        action_type="reference_remap_candidate",
        likely_fix="Remap beverage/coffee/creamer rows to coffee, creamer, or drink references; keep bakery words only as flavor.",
        rationale="The SKU is a beverage/creamer but a reference is flour, churro, pastry, cake, cookie, bun, or bread.",
        row_predicate=is_beverage_creamer_or_coffee,
        field_predicate=lambda _r, text, _field: (
            has(text, r"\b(wheat\s+flour|flour|churro|pastry|cake|cookie|bun|roll|bread|biscotti)\b")
            and not has(text, r"\b(coffee|creamer|creamers|latte|espresso|beverage|drink|cocoa)\b")
        ),
    ),
    ReferenceRule(
        issue_family="plant_milk_has_dairy_milk_reference",
        severity="high",
        confidence="high",
        action_type="reference_remap_candidate",
        likely_fix="Remap plant milks to plant-milk/nut/soy/oat beverage references, not cow milk.",
        rationale="The SKU is plant milk but a reference is generic dairy/cow milk.",
        row_predicate=lambda r: path_starts(r, "Beverage > Plant Milk"),
        field_predicate=lambda _r, text, _field: has_dairy_milk_reference(text),
    ),
    ReferenceRule(
        issue_family="sandwich_or_filled_bun_has_bread_carrier_reference",
        severity="high",
        confidence="high",
        action_type="reference_remap_candidate",
        likely_fix="Use sandwich/stuffed-bun/prepared-meal references instead of plain bun, roll, bagel, or bread references.",
        rationale="The reference describes a carrier component rather than the prepared product.",
        row_predicate=is_sandwich_or_filled_bun_product,
        field_predicate=lambda r, text, _field: has_bread_carrier_reference(text) or (
            path_starts(r, "Frozen > Appetizers > Stuffed Buns") and has_wrong_stuffed_bun_reference(text)
        ),
    ),
    ReferenceRule(
        issue_family="salad_kit_has_component_reference",
        severity="high",
        confidence="high",
        action_type="reference_remap_candidate",
        likely_fix="Use salad-kit/salad references instead of croutons, dressing, lettuce, cheese, or topping references.",
        rationale="The reference describes a salad kit component rather than the whole kit.",
        row_predicate=is_salad_kit_product,
        field_predicate=lambda _r, text, _field: has_component_salad_kit_reference(text),
    ),
    ReferenceRule(
        issue_family="soup_chowder_has_plain_seafood_or_meat_reference",
        severity="high",
        confidence="high",
        action_type="reference_remap_candidate",
        likely_fix="Use soup/chowder/bisque references; keep seafood/meat as variant/component.",
        rationale="The reference describes a plain protein instead of the soup/chowder product.",
        row_predicate=is_soup_or_chowder_product,
        field_predicate=lambda _r, text, _field: has_plain_seafood_reference(text) or has_plain_meat_reference(text),
    ),
    ReferenceRule(
        issue_family="dip_sauce_seasoning_has_plain_meat_or_seafood_reference",
        severity="high",
        confidence="high",
        action_type="reference_remap_candidate",
        likely_fix="Use dip, sauce, seasoning, marinade, or boil references instead of raw/plain protein references.",
        rationale="The target protein named in the product title stole the reference mapping.",
        row_predicate=is_dip_sauce_seasoning_product,
        field_predicate=lambda _r, text, _field: has_plain_seafood_reference(text) or has_plain_meat_reference(text),
    ),
    ReferenceRule(
        issue_family="cookie_cracker_has_meal_sandwich_reference",
        severity="high",
        confidence="high",
        action_type="reference_remap_candidate",
        likely_fix="Use cookie/cracker references for sandwich cookies/crackers, not prepared sandwich references.",
        rationale="Sandwich is a cookie/cracker form here, not a meal.",
        row_predicate=is_cookie_or_cracker_product,
        field_predicate=lambda _r, text, _field: has_meal_sandwich_reference(text),
    ),
    ReferenceRule(
        issue_family="cracker_has_bakery_carrier_reference",
        severity="high",
        confidence="high",
        action_type="reference_remap_candidate",
        likely_fix="Use cracker references instead of buns, rolls, cakes, or plain cookies.",
        rationale="The SKU/path is a cracker but a reference describes a bakery carrier or cookie.",
        row_predicate=lambda r: (
            (title_has(r, r"\b(crackers?|crckrs)\b") and not title_has(r, r"\b(cookies?|biscotti)\b"))
            or bfc_lower(r) == "crackers & biscotti"
            and not title_has(r, r"\b(cookies?|biscotti|biscottini)\b")
            or (
                path_starts(r, "Snack > Crackers")
                and not title_has(r, r"\b(cookies?|biscotti|wafers?)\b")
            )
        ),
        field_predicate=lambda _r, text, _field: (
            has(text, r"\b(cinnamon\s+buns?|hamburger\s+bun|rolls?|cake|cakes|cookies?)\b")
            and not has(text, r"\b(cracker|crackers|triscuit|water\s+biscuits)\b")
        ),
    ),
    ReferenceRule(
        issue_family="tortilla_has_cookie_cracker_or_bun_reference",
        severity="high",
        confidence="high",
        action_type="reference_remap_candidate",
        likely_fix="Use tortilla/taco-shell/wrap references instead of cookie, cracker, or bun references.",
        rationale="The SKU is a tortilla/taco shell/wrap but a reference points to a different bakery/snack family.",
        row_predicate=is_tortilla_product,
        field_predicate=lambda _r, text, _field: (
            has(text, r"\b(cookie|cookies|cracker|crackers|cinnamon\s+buns?|hamburger\s+bun)\b")
            and not has(text, r"\b(tortilla|taco|wrap)\b")
        ),
    ),
    ReferenceRule(
        issue_family="nut_butter_has_dairy_butter_reference",
        severity="high",
        confidence="high",
        action_type="reference_remap_candidate",
        likely_fix="Use nut/seed butter or spread references; reserve dairy butter references for dairy butter.",
        rationale="The reference treats nut/seed butter as dairy butter.",
        row_predicate=is_nut_butter_product,
        field_predicate=lambda _r, text, _field: has_dairy_butter_reference(text),
    ),
    ReferenceRule(
        issue_family="vegetable_or_potato_side_has_baking_mix_proxy_reference",
        severity="high",
        confidence="high",
        action_type="reference_remap_candidate",
        likely_fix="Use vegetable, canned/frozen vegetable, or packaged potato side references instead of flour/starch/baking mix proxies.",
        rationale="A vegetable/side product is mapped to a baking proxy.",
        row_predicate=lambda r: is_canned_or_frozen_vegetable_product(r)
        or path_starts(r, "Pantry > Packaged Sides > Potatoes"),
        field_predicate=lambda _r, text, _field: has_baking_mix_proxy_reference(text),
    ),
    ReferenceRule(
        issue_family="ice_cream_cone_has_baking_mix_or_cookie_reference",
        severity="high",
        confidence="high",
        action_type="reference_remap_candidate",
        likely_fix="Use ice-cream-cone references, not baking mix or cookie references.",
        rationale="The SKU is an ice cream cone/cup product; bakery mix/cookie references are wrong conceptually.",
        row_predicate=is_ice_cream_cone_product,
        field_predicate=lambda _r, text, _field: (
            has(text, r"\b(baking\s+mix|cake\s+mix|cookie|cookies)\b")
            and not has(text, r"\bice\s+cream\s+cones?\b|\bcone\b")
        ),
    ),
    ReferenceRule(
        issue_family="pie_crust_or_shell_has_finished_pie_reference",
        severity="medium",
        confidence="medium",
        action_type="reference_review_candidate",
        likely_fix="Use pie crust/shell references; finished pie references are only acceptable when no crust/shell proxy exists.",
        rationale="Crust/shell components are not finished pies.",
        row_predicate=is_pie_crust_or_shell_product,
        field_predicate=lambda _r, text, _field: (
            has(text, r"\bpie\b")
            and not has(text, r"\b(crust|shell|dough|pastry\s+shell)\b")
        ),
    ),
    ReferenceRule(
        issue_family="cheese_has_meal_sandwich_reference",
        severity="high",
        confidence="high",
        action_type="reference_remap_candidate",
        likely_fix="Use cheese references for cheese slices; sandwich is only a use/form cue.",
        rationale="The reference describes a prepared sandwich rather than cheese.",
        row_predicate=lambda r: bfc(r) == "Cheese" or path_starts(r, "Dairy > Cheese"),
        field_predicate=lambda _r, text, _field: has_meal_sandwich_reference(text) and not has(text, r"\bcheese\b"),
    ),
    ReferenceRule(
        issue_family="frozen_ice_cream_has_bakery_roll_reference",
        severity="high",
        confidence="high",
        action_type="reference_remap_candidate",
        likely_fix="Use frozen dessert references for ice cream rolls/bars; do not map to bread rolls or dough.",
        rationale="Roll is a presentation word for the frozen dessert, not a bakery roll.",
        row_predicate=lambda r: path_starts(r, "Frozen > Ice Cream", "Frozen > Frozen Yogurt", "Frozen > Gelato")
        or (title_has(r, r"\bice\s+cream\b") and path_starts(r, "Frozen")),
        field_predicate=lambda _r, text, _field: (
            has(text, r"\b(rolls?|bun|buns|bread|dough)\b")
            and not has(text, r"\b(ice\s+cream|frozen\s+yogurt|gelato|frozen\s+dessert)\b")
        ),
    ),
    ReferenceRule(
        issue_family="meat_or_charcuterie_roll_has_bakery_roll_reference",
        severity="high",
        confidence="high",
        action_type="reference_remap_candidate",
        likely_fix="Use meat, poultry, or charcuterie roll references; do not map to bread rolls/buns.",
        rationale="Roll means rolled meat/cheese or prepared meat form here, not a bakery carrier.",
        row_predicate=lambda r: path_starts(r, "Meat & Seafood > Charcuterie > Charcuterie Rolls", "Meat & Seafood > Poultry > Turkey > Turkey Roll")
        or (
            title_has(r, r"\b(roll\s*&\s*go|salumi\s+rolls?|turkey\s+roll)\b")
            and path_starts(r, "Meat & Seafood")
        ),
        field_predicate=lambda _r, text, _field: (
            has(text, r"\b(rolls?|bun|buns|bread|dough)\b")
            and not has(text, r"\b(turkey|prosciutto|pepperoni|salami|ham|beef|chicken|pork|meat|charcuterie)\b")
        ),
    ),
    ReferenceRule(
        issue_family="candy_has_frozen_dessert_reference",
        severity="medium",
        confidence="medium",
        action_type="source_or_reference_review",
        likely_fix="Review whether the BFC/path is dirty or whether the reference should be candy/chocolate instead of ice cream.",
        rationale="Candy rows mapped to frozen desserts are usually source conflict or flavor hijack.",
        row_predicate=lambda r: bfc(r) == "Candy" or path_starts(r, "Snack > Candy", "Snack > Chocolate Candy"),
        field_predicate=lambda _r, text, _field: has(text, r"\b(ice\s+cream|gelato|frozen\s+yogurt|ice\s+pops?)\b")
        and not has(text, r"\b(candy|chocolate|confection)\b"),
    ),
    ReferenceRule(
        issue_family="low_token_overlap_reference_review",
        severity="low",
        confidence="review",
        action_type="manual_review",
        likely_fix="Review low-overlap reference mappings, especially parent-default and provisional proxies.",
        rationale="The reference description has almost no product tokens in common with title/path.",
        row_predicate=lambda r: bool(ref_value(r, "esha") or ref_value(r, "sr28") or ref_value(r, "fndds")),
        field_predicate=lambda r, text, field: (
            field != "matched_key"
            and bool(text.strip())
            and overlap_score(r, text) == 0.0
            and (
                "parent-default" in (r.get("matched_key") or "").lower()
                or (r.get("match_source") or "").lower() in {"canonical_tree", "provisional_desc_proxy"}
            )
            and not has(text, r"\b(water|salt|sugar)\b")
        ),
    ),
]


def load_right_place_issues(path: Path) -> dict[str, set[str]]:
    by_fdc: dict[str, set[str]] = defaultdict(set)
    if not path.exists():
        return by_fdc
    with path.open(newline="", encoding="utf-8", errors="replace") as handle:
        for row in csv.DictReader(handle):
            fdc = (row.get("fdc_id") or "").strip()
            family = (row.get("issue_family") or "").strip()
            if fdc and family:
                by_fdc[fdc].add(family)
    return by_fdc


def evaluate_rule(row: dict[str, str], rule: ReferenceRule) -> list[str]:
    if not rule.row_predicate(row):
        return []
    bad: list[str] = []
    for field in REFERENCE_FIELDS:
        text = ref_value(row, field)
        if text and rule.field_predicate(row, text, field):
            bad.append(field)
    return bad


def issue_row(
    row: dict[str, str],
    rule: ReferenceRule,
    bad_fields: list[str],
    taxonomy_issues: dict[str, set[str]],
) -> dict[str, str]:
    fdc = (row.get("fdc_id") or "").strip()
    return {
        "issue_family": rule.issue_family,
        "severity": rule.severity,
        "confidence": rule.confidence,
        "action_type": rule.action_type,
        "suspect_reference_fields": ";".join(bad_fields),
        "suspect_reference_values": bad_reference_blob(row, bad_fields),
        "likely_fix": rule.likely_fix,
        "rationale": rule.rationale,
        "taxonomy_issue_families": ";".join(sorted(taxonomy_issues.get(fdc, set()))),
        "fdc_id": fdc,
        "title": row.get("title", ""),
        "branded_food_category": row.get("branded_food_category", ""),
        "canonical_path": row.get("canonical_path", ""),
        "retail_leaf_path": row.get("retail_leaf_path", ""),
        "fndds_code": row.get("fndds_code", ""),
        "fndds_desc": row.get("fndds_desc", ""),
        "sr28_code": row.get("sr28_code", ""),
        "sr28_desc": row.get("sr28_desc", ""),
        "esha_code": row.get("esha_code", ""),
        "esha_desc": row.get("esha_desc", ""),
        "match_source": row.get("match_source", ""),
        "match_score": row.get("match_score", ""),
        "matched_key": row.get("matched_key", ""),
        "consensus_reason": row.get("consensus_reason", ""),
    }


def markdown_examples(rows: list[dict[str, str]]) -> list[str]:
    out = [
        "| fdc_id | suspect refs | path | title |",
        "|---|---|---|---|",
    ]
    for row in rows:
        refs = (row["suspect_reference_values"] or "").replace("|", "\\|")[:150]
        path_value = (row["retail_leaf_path"] or "").replace("|", "\\|")[:120]
        title = (row["title"] or "").replace("|", "\\|")[:140]
        out.append(f"| {row['fdc_id']} | {refs} | {path_value} | {title} |")
    return out


def main() -> None:
    if not SRC.exists():
        raise SystemExit(f"missing {SRC}; run build_consensus_full_corpus_audit.py first")
    taxonomy_issues = load_right_place_issues(RIGHT_PLACE)

    issue_rows: list[dict[str, str]] = []
    issue_counts: Counter[str] = Counter()
    severity_counts: Counter[str] = Counter()
    action_counts: Counter[str] = Counter()
    field_counts: Counter[str] = Counter()
    examples: dict[str, list[dict[str, str]]] = defaultdict(list)
    rows_seen = 0

    with SRC.open(newline="", encoding="utf-8", errors="replace") as handle:
        for row in csv.DictReader(handle):
            rows_seen += 1
            for rule in RULES:
                bad_fields = evaluate_rule(row, rule)
                if not bad_fields:
                    continue
                out = issue_row(row, rule, bad_fields, taxonomy_issues)
                issue_rows.append(out)
                issue_counts[rule.issue_family] += 1
                severity_counts[rule.severity] += 1
                action_counts[rule.action_type] += 1
                field_counts.update(bad_fields)
                if len(examples[rule.issue_family]) < 8:
                    examples[rule.issue_family].append(out)

    fields = list(issue_row({}, RULES[0], [], taxonomy_issues).keys())
    with OUT_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(issue_rows)

    remap_rows = [row for row in issue_rows if row["action_type"] == "reference_remap_candidate"]
    with OUT_REMAP.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(remap_rows)

    unique_fdcs = {row["fdc_id"] for row in issue_rows if row["fdc_id"]}
    high_conf_fdcs = {
        row["fdc_id"]
        for row in issue_rows
        if row["fdc_id"] and row["severity"] == "high" and row["confidence"] == "high"
    }
    taxonomy_overlap_fdcs = {
        row["fdc_id"]
        for row in issue_rows
        if row["fdc_id"] and row["taxonomy_issue_families"]
    }
    remap_fdcs = {
        row["fdc_id"]
        for row in issue_rows
        if row["fdc_id"] and row["action_type"] == "reference_remap_candidate"
    }

    summary = {
        "source": str(SRC),
        "right_place_source": str(RIGHT_PLACE),
        "outputs": {
            "csv": str(OUT_CSV),
            "reference_remap_candidates": str(OUT_REMAP),
            "json": str(OUT_SUMMARY),
            "markdown": str(OUT_MD),
        },
        "rows": rows_seen,
        "issue_rows": len(issue_rows),
        "unique_issue_fdc_ids": len(unique_fdcs),
        "high_high_confidence_unique_fdc_ids": len(high_conf_fdcs),
        "reference_remap_unique_fdc_ids": len(remap_fdcs),
        "overlap_with_right_place_issue_fdc_ids": len(taxonomy_overlap_fdcs),
        "issue_counts": dict(issue_counts.most_common()),
        "severity_counts": dict(severity_counts.most_common()),
        "action_counts": dict(action_counts.most_common()),
        "suspect_reference_field_counts": dict(field_counts.most_common()),
    }
    OUT_SUMMARY.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")

    lines = [
        "# Consensus Reference Alignment Audit",
        "",
        f"Source: `{SRC.name}`",
        f"Rows: `{rows_seen:,}`",
        f"Unique issue FDC ids: `{len(unique_fdcs):,}`",
        f"High severity + high confidence FDC ids: `{len(high_conf_fdcs):,}`",
        f"Reference-remap candidate FDC ids: `{len(remap_fdcs):,}`",
        f"Overlap with right-place issue FDC ids: `{len(taxonomy_overlap_fdcs):,}`",
        "",
        "## Suspect Reference Fields",
        "",
    ]
    for field, count in field_counts.most_common():
        lines.append(f"- `{field}`: `{count:,}`")
    lines.extend(["", "## Issue Counts", ""])
    for family, count in issue_counts.most_common():
        rule = next(rule for rule in RULES if rule.issue_family == family)
        lines.extend([
            f"### {family}",
            "",
            f"- rows: `{count:,}`",
            f"- severity: `{rule.severity}`",
            f"- confidence: `{rule.confidence}`",
            f"- action: `{rule.action_type}`",
            f"- likely fix: {rule.likely_fix}",
            "",
        ])
        lines.extend(markdown_examples(examples[family]))
        lines.append("")
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")

    print(json.dumps({
        "rows": rows_seen,
        "unique_issue_fdc_ids": len(unique_fdcs),
        "high_high_confidence_unique_fdc_ids": len(high_conf_fdcs),
        "reference_remap_unique_fdc_ids": len(remap_fdcs),
        "overlap_with_right_place_issue_fdc_ids": len(taxonomy_overlap_fdcs),
        "top_issues": dict(issue_counts.most_common(15)),
        "suspect_reference_field_counts": dict(field_counts.most_common()),
        "outputs": summary["outputs"],
    }, indent=2))


if __name__ == "__main__":
    main()
