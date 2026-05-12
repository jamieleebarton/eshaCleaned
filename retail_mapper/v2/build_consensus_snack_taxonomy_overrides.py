#!/usr/bin/env python3
"""Build snack taxonomy overrides for false Veggie Straws identities."""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Iterable, Mapping

from taxonomy_finalizer import PATH_SEP, dedupe_segments, normalize_path, split_path


V2 = Path(__file__).resolve().parent
DEFAULT_AUDIT = V2 / "consensus_full_corpus_audit.csv"
DEFAULT_ACTIVE_OUT = V2 / "consensus_snack_taxonomy_overrides.csv"
DEFAULT_REVIEW_OUT = V2 / "consensus_snack_taxonomy_review.csv"
DEFAULT_REPORT_OUT = V2 / "consensus_snack_taxonomy_report.json"
DEFAULT_MD_OUT = V2 / "consensus_snack_taxonomy.md"

csv.field_size_limit(sys.maxsize)

FIELDS = [
    "fdc_id",
    "status",
    "owner",
    "title",
    "branded_food_category",
    "current_canonical_path",
    "current_retail_leaf_path",
    "category_path_fixed",
    "product_identity_fixed",
    "modifier",
    "new_canonical_path",
    "new_product_identity",
    "issue_family",
    "reason",
    "evidence",
]

REVIEW_FIELDS = [
    "fdc_id",
    "status",
    "owner",
    "title",
    "branded_food_category",
    "current_canonical_path",
    "current_retail_leaf_path",
    "issue_family",
    "likely_fix",
    "evidence",
]

TRUE_VEGGIE_STRAWS_RE = re.compile(
    r"\b(?:garden\s+)?(?:veggie|vegetable)(?:\s+\w+){0,2}\s+str(?:aw|ew)s?\b",
    re.I,
)

FLAVOR_WORDS = {
    "bbq",
    "barbeque",
    "barbecue",
    "balsamic",
    "buffalo",
    "cheddar",
    "cheese",
    "chile",
    "chili",
    "chipotle",
    "cinnamon",
    "fiery",
    "flamin",
    "garlic",
    "herb",
    "hot",
    "jalapeno",
    "ketchup",
    "lime",
    "onion",
    "pepper",
    "ranch",
    "salt",
    "sriracha",
    "sweet",
    "vinegar",
}

GENERIC_MODIFIER_TOKENS = {
    "bean",
    "beans",
    "chip",
    "chips",
    "crisp",
    "crisps",
    "crunch",
    "crunchy",
    "flavored",
    "green",
    "organic",
    "pea",
    "peas",
    "plain",
    "potato",
    "snack",
    "snacks",
    "straw",
    "straws",
    "vegetable",
    "veggie",
}

MODIFIER_SUPPORT_STOPWORDS = {
    "a",
    "and",
    "flavor",
    "flavored",
    "of",
    "the",
    "with",
}

WORD_ALIASES = {
    "barbecue": "bbq",
    "barbeque": "bbq",
    "cheesy": "cheese",
    "chilli": "chili",
}

ROUTE_PATTERNS: list[tuple[str, str, str, str]] = [
    (r"\b(?:pickled|dilled)\b.*\bbrussels?\s+sprouts?\b|\bbrussels?\s+sprouts?\b.*\b(?:pickled|dilled)\b", "Pantry > Pickles", "Pickled Brussels Sprouts", "pickled_vegetable_routed_as_veggie_straws"),
    (r"\b(?:turmeric\s+cauliflower|moringa\s+green\s+pea).*soup\b|\bsoup\b", "Pantry", "Soup", "soup_routed_as_veggie_straws"),
    (r"\bwonton\s+strips?\b", "Meal > Salads > Salad Topper", "Wonton Strips", "salad_topping_routed_as_veggie_straws"),
    (r"\b(?:crispy|fried|pickle\s+flavored|pickle\s+seasoned)\s+(?:jalapenos?|cucumbers?)\b|\bcrunchy\s+toppers?\b", "Meal > Salads", "Salad Topping", "salad_topping_routed_as_veggie_straws"),
    (r"\bsalad\s+snax\b", "Meal > Salads", "Salad Snack", "salad_snack_routed_as_veggie_straws"),
    (r"\bseaweed\b|\bnori\b", "Snack", "Seaweed Snacks", "seaweed_snack_routed_as_veggie_straws"),
    (r"\bfunyuns?\b|\bonion\s+(?:flavored\s+)?rings?\b|\bring\s+o'?s\b", "Snack", "Onion Rings", "onion_rings_routed_as_veggie_straws"),
    (r"\bpigless\s+pork\s+rinds?\b|\bpork\s+rinds?\b", "Snack", "Pork Rinds", "pork_rinds_routed_as_veggie_straws"),
    (r"\b(?:yuca\s+)?cassava\s+chips?\b|\byuca\s+chips?\b", "Snack > Chips", "Cassava Chips", "cassava_chips_routed_as_veggie_straws"),
    (r"\b(?:artichoke\s+chyps?|artichoke\s+chips?)\b", "Snack > Chips", "Artichoke Chips", "artichoke_chips_routed_as_veggie_straws"),
    (r"\bcoconut\s+chips?\b", "Snack > Chips", "Coconut Chips", "coconut_chips_routed_as_veggie_straws"),
    (r"\b(?:beet|beets)\b.*\b(?:chips?|crisps?|crunchies|freeze\s+dried)\b|\bcrispy\s+beets?\b", "Snack > Chips", "Beet Chips", "beet_chips_routed_as_veggie_straws"),
    (r"\bpringles\b", "Snack > Chips", "Potato Crisps", "potato_crisps_routed_as_veggie_straws"),
    (r"\bsweet\s+potato\s+(?:chips?|crisps?)\b", "Snack > Chips", "Sweet Potato Chips", "sweet_potato_chips_routed_as_veggie_straws"),
    (r"\bsweet\s+potato\b.*\b(?:snack\s+)?sticks?\b|\b(?:snack\s+)?sticks?\b.*\bsweet\s+potato\b", "Snack > Sticks", "Sweet Potato Sticks", "sweet_potato_sticks_routed_as_veggie_straws"),
    (r"\bbutternut\s+squash\s+stalks?\b", "Snack > Veggie Snacks", "Butternut Squash Stalks", "vegetable_snack_routed_as_veggie_straws"),
    (r"\bcauliflower\s+stalks?\b", "Snack > Veggie Snacks", "Cauliflower Stalks", "vegetable_snack_routed_as_veggie_straws"),
    (r"\bveggie\s+stix\b|\bveggie\s+sticks?\b|\bveggie\s+stci?ks?\b|\bvegetable\s+stix\b|\bvegetable\s+sticks?\b", "Snack > Veggie Snacks", "Veggie Sticks", "veggie_sticks_routed_as_veggie_straws"),
    (r"\bapple\s+straws?\b|\bmultigrain\s+straw\s+snacks?\b", "Snack > Sticks", "Apple Straws", "apple_straws_routed_as_veggie_straws"),
    (r"\bpenne\s+straws?\b", "Snack > Sticks", "Pasta Straws", "pasta_straws_routed_as_veggie_straws"),
    (r"\bsuperfood\s+sticks?\b", "Snack > Sticks", "Superfood Sticks", "superfood_sticks_routed_as_veggie_straws"),
    (r"\b(?:quinoa|quinoa\s*&\s*chia|quinoa\s+and\s+chia).*snack\s+sticks?\b|\bquinoa\s+sticks?\b", "Snack > Sticks", "Quinoa Chia Sticks", "quinoa_sticks_routed_as_veggie_straws"),
    (r"\bamaranth\s+sticks?\b", "Snack > Sticks", "Amaranth Sticks", "amaranth_sticks_routed_as_veggie_straws"),
    (r"\bprotein\s+stix\b|\bprotein\s+sticks?\b", "Snack > Sticks", "Protein Sticks", "protein_sticks_routed_as_veggie_straws"),
    (r"\bsesame\s+sticks?\b", "Snack > Sticks", "Sesame Sticks", "sesame_sticks_routed_as_veggie_straws"),
    (r"\bpuffed\s+wheat\s+snacks?\b", "Snack > Chips", "Puffed Wheat Snack", "puffed_wheat_snack_routed_as_veggie_straws"),
    (r"\bpuffed\s+rings?\b", "Snack", "Puffed Rings", "puffed_ring_routed_as_veggie_straws"),
    (r"\b(?:crunchy\s+)?puffed\s+snacks?\b|\bpuffed\s+.*\bsnacks?\b", "Snack > Puffs", "Puffed Snacks", "puffed_snack_routed_as_veggie_straws"),
    (r"\bpirate'?s\s+booty\b", "Snack", "Puffs", "puffs_routed_as_veggie_straws"),
    (r"\b(?:corn|quinoa|veggie|carrot|peanut\s+butter|sweet\s+potato)?\s*puffs?\b|\bpuffcorn\b", "Snack", "Puffs", "puffs_routed_as_veggie_straws"),
    (r"\bcheese\s+curls?\b|\bcurls?\b", "Snack", "Snack Curls", "snack_curls_routed_as_veggie_straws"),
    (r"\bmunchos\b|\bpotato\s+crisps?\b", "Snack > Chips", "Potato Crisps", "potato_crisps_routed_as_veggie_straws"),
    (r"\bpotato\s+sticks?\b", "Snack > Chips", "Potato Sticks", "potato_sticks_routed_as_veggie_straws"),
    (r"\bfries?\s+corn\s*(?:&|and)\s*potato\b|\bcorn\s*(?:&|and)?\s*potato\b.*\bfries?\b|\bchester'?s\b.*\bfries?\b", "Snack > Chips", "Corn and Potato Fries", "corn_potato_fries_routed_as_veggie_straws"),
    (r"\bandy\s+capp\b.*\bfries?\b|\b(?:hot|cheese|cheddar|bacon\s+cheddar|cheddar\s+(?:and\s+)?bacon|flavored)\s+fries?\b", "Snack > Chips", "Snack Fries", "snack_fries_routed_as_veggie_straws"),
    (r"\bpotato\s+twigs?\b|\bpotato\s+snacks?\b|\bpotato\s*&\s*veggie\s+snacks?\b", "Snack", "Potato Snacks", "potato_snack_routed_as_veggie_straws"),
    (r"\bpotato\s+chips?\b", "Snack > Chips", "Potato Chips", "potato_chips_routed_as_veggie_straws"),
    (r"\bcorn\s+sticks?\b", "Snack", "Corn Sticks", "corn_sticks_routed_as_veggie_straws"),
    (r"\bcorn\s+snacks?\b", "Snack", "Corn Snacks", "corn_snack_routed_as_veggie_straws"),
    (r"\borganic\s+sweet\s+corn\b|\bsweet\s+corn\b", "Snack", "Corn Snacks", "corn_snack_routed_as_veggie_straws"),
    (r"\b(?:rice|brown\s+rice)\s+crisps?\b|\bquaker\b.*\bcrisps?\b", "Snack > Crisps", "Rice Crisps", "rice_crisps_routed_as_veggie_straws"),
    (r"\brice\s+snacks?\b", "Snack", "Rice Snacks", "rice_snack_routed_as_veggie_straws"),
    (r"\bwasabi\s+peas?\b", "Snack > Veggie Snacks", "Wasabi Peas", "pea_snack_routed_as_veggie_straws"),
    (r"\bgreen\s+pea\s+(?:crisps?|snacks?)\b|\bwhole\s+green\s+peas\b|\bfried\s+green\s+peas\b|\bgreen\s+peas\b", "Snack > Veggie Snacks", "Green Pea Snacks", "pea_snack_routed_as_veggie_straws"),
    (r"\bworld\s+peas\b|\b(?:yellow|seasoned|flavored|sriracha)\s+peas?\b|\bpeas?,", "Snack > Veggie Snacks", "Pea Snacks", "pea_snack_routed_as_veggie_straws"),
    (r"\bpea\s+(?:crisps?|snacks?)\b|\bbaked\s+pea\s+snacks?\b|\bcrunchy\s+pea\s+snacks?\b", "Snack > Veggie Snacks", "Pea Snacks", "pea_snack_routed_as_veggie_straws"),
    (r"\blentil\s+snaps?\b|\bmighty\s+lil'?[\s-]*lentils\b", "Snack > Veggie Snacks", "Lentil Snacks", "lentil_snack_routed_as_veggie_straws"),
    (r"\bchickpeas?\b|chickpeatos|bean\s+pops?\b", "Snack > Veggie Snacks", "Chickpea Snacks", "chickpea_snack_routed_as_veggie_straws"),
    (r"\bfavas?\s+peas?\b", "Snack > Veggie Snacks", "Fava Bean Snacks", "fava_bean_snack_routed_as_veggie_straws"),
    (r"\bbean\s+crisps?\b|\bbeautiful\s+beans\b", "Snack > Veggie Snacks", "Bean Crisps", "bean_crisps_routed_as_veggie_straws"),
    (r"\bedamame\b", "Snack > Veggie Snacks", "Edamame Snacks", "edamame_snack_routed_as_veggie_straws"),
    (r"\bkale\s+chips?\b", "Snack > Veggie Snacks", "Kale Chips", "kale_snack_routed_as_veggie_straws"),
    (r"\bkale\s+crisps?\b|\bcrunchy\s+kale\b|\broasted\s+kale\b", "Snack > Veggie Snacks", "Kale Crisps", "kale_snack_routed_as_veggie_straws"),
    (r"\bplantain\s+(?:chips?|crisps?)\b", "Snack > Chips", "Plantain Chips", "plantain_snack_routed_as_veggie_straws"),
    (r"\bplantain\s+(?:strips?|stix)\b", "Snack > Chips", "Plantain Strips", "plantain_snack_routed_as_veggie_straws"),
    (r"\bplantain\s+(?:bits?|nuggets?)\b", "Snack > Chips", "Plantain Snacks", "plantain_snack_routed_as_veggie_straws"),
    (r"\btostones?\b|patacones", "Snack > Chips", "Tostones", "plantain_snack_routed_as_veggie_straws"),
    (r"\bveggie\s+sticks?\b|\bvegetable\s+sticks?\b", "Snack > Veggie Snacks", "Veggie Sticks", "veggie_sticks_routed_as_veggie_straws"),
    (r"\b(?:real\s+)?vegetable\b.*\bchips?\b|\bvegetables?\s+chips?\b|\bveggie\s+chi+ps?\b", "Snack > Chips", "Vegetable Chips", "veggie_chips_routed_as_veggie_straws"),
    (r"\b(?:veggie|vegetable)\s+chips?\b", "Snack > Veggie Snacks", "Veggie Chips", "veggie_chips_routed_as_veggie_straws"),
    (r"\b(?:veggie|vegetable)\s+crisps?\b", "Snack > Veggie Snacks", "Veggie Crisps", "veggie_crisps_routed_as_veggie_straws"),
    (r"\bvegetable\s+and\s+potato\s+snacks?\b|\bvegetable\s*&\s*potato\s+snacks?\b|\bpotato\s+&\s+veggie\s+snacks?\b", "Snack > Veggie Snacks", "Vegetable and Potato Snacks", "vegetable_potato_snack_routed_as_veggie_straws"),
    (r"\bveggie\s+flutes?\b", "Snack > Veggie Snacks", "Veggie Flutes", "vegetable_snack_routed_as_veggie_straws"),
    (r"\bveggie\s+pops?\b", "Snack > Veggie Snacks", "Veggie Pops", "vegetable_snack_routed_as_veggie_straws"),
    (r"\bveggie\s+littles\b|\bveggie\s+snacks?\b|\bzesty\s+garden\s+veggie\s+snacks?\b", "Snack > Veggie Snacks", "Veggie Snacks", "vegetable_snack_routed_as_veggie_straws"),
    (r"\b(?:ranch\s+)?mixed\s+veggies\b|\bcarrots?\s*&\s*broccoli\b|\bmixed\s+vegetable\s+cubes?\b|\bdried\s+vegetable\s+supersnacks?\b|\bvegetable\s+snacks?\b", "Snack > Veggie Snacks", "Vegetable Snacks", "vegetable_snack_routed_as_veggie_straws"),
    (r"\bbroccoli\s+chips?\b", "Snack > Veggie Snacks", "Broccoli Chips", "vegetable_chips_routed_as_veggie_straws"),
    (r"\bcrispy\s+broccoli\b|\bbroccoli\s+(?:bites?|snacks?)\b", "Snack > Veggie Snacks", "Broccoli Snacks", "vegetable_snack_routed_as_veggie_straws"),
    (r"\bcarrot\s+chips?\b", "Snack > Veggie Snacks", "Carrot Chips", "vegetable_chips_routed_as_veggie_straws"),
    (r"\bcarrot\s+(?:sticks?|snacks?|mini\s+wafers?)\b", "Snack > Veggie Snacks", "Carrot Snacks", "vegetable_snack_routed_as_veggie_straws"),
    (r"\bgreen\s+bean\s+chips?\b", "Snack > Veggie Snacks", "Green Bean Chips", "vegetable_chips_routed_as_veggie_straws"),
    (r"\bgreen\s+bean\s+(?:crunch|snacks?)\b|\bgreen\s+beans\b", "Snack > Veggie Snacks", "Green Bean Snacks", "vegetable_snack_routed_as_veggie_straws"),
    (r"\bokra\s+chips?\b", "Snack > Veggie Snacks", "Okra Chips", "vegetable_chips_routed_as_veggie_straws"),
    (r"\b(?:dried\s+)?okra\b", "Snack > Veggie Snacks", "Okra Snacks", "vegetable_snack_routed_as_veggie_straws"),
    (r"\bcrispy\s+mushrooms?\b|\bmushroom\s+snacks?\b", "Snack > Veggie Snacks", "Mushroom Snacks", "vegetable_snack_routed_as_veggie_straws"),
    (r"\basparagus\s+chips?\b", "Snack > Veggie Snacks", "Asparagus Chips", "vegetable_chips_routed_as_veggie_straws"),
    (r"\bzucchini\s+chips?\b", "Snack > Veggie Snacks", "Zucchini Chips", "vegetable_chips_routed_as_veggie_straws"),
    (r"\bcauliflower\s+(?:bites?|snacks?|florets?)\b", "Snack > Veggie Snacks", "Cauliflower Snacks", "vegetable_snack_routed_as_veggie_straws"),
    (r"\bbrussels?\s+sprout\s+chips?\b", "Snack > Veggie Snacks", "Brussels Sprout Chips", "vegetable_chips_routed_as_veggie_straws"),
    (r"\bbrussels?\s+sprouts?\b", "Snack > Veggie Snacks", "Brussels Sprout Snacks", "vegetable_snack_routed_as_veggie_straws"),
    (r"\bkale\s+poppers?\b", "Snack > Veggie Snacks", "Kale Poppers", "vegetable_snack_routed_as_veggie_straws"),
    (r"\bpopcorners\b|\bpopped\s+corn\s+chips?\b", "Snack > Chips", "Popped Corn Chips", "popped_corn_chips_routed_as_veggie_straws"),
    (r"\bcheese\s+balls?\b", "Snack > Cheese Snacks", "Cheese Balls", "cheese_snack_routed_as_veggie_straws"),
    (r"\bcheese\s+flavored\s+crunchy\s+snacks?\b", "Snack", "Cheese Snacks", "cheese_snack_routed_as_veggie_straws"),
    (r"\bcrunchy\s+bites?\b", "Snack", "Crunchy Bites", "crunchy_bites_routed_as_veggie_straws"),
    (r"\b(?:fiesta|baked)\s+twists?\b", "Snack", "Snack Twists", "snack_twists_routed_as_veggie_straws"),
    (r"\bmixed\s+artisan\s+strips?\b", "Snack > Chips", "Snack Strips", "snack_strips_routed_as_veggie_straws"),
    (r"\bspirulina\s+crunchies\b", "Sports & Wellness > Supplements", "Spirulina", "spirulina_routed_as_veggie_straws"),
    (r"\bplant\s+thins?\b", "Snack > Chips", "Plant Thins", "plant_thins_routed_as_veggie_straws"),
    (r"\bramen\s+snacks?\b", "Snack", "Ramen Snacks", "ramen_snack_routed_as_veggie_straws"),
    (r"\bwater\s+lily\s+pops?\b", "Snack", "Water Lily Pops", "water_lily_pops_routed_as_veggie_straws"),
    (r"\b(?:sweet\s+crinkle\s+cut\s+potato|sweet\s+potatos?)\b", "Produce > Vegetables", "Sweet Potatoes", "produce_potato_routed_as_veggie_straws"),
    (r"\b(?:gourmet\s+)?potato\s+nibbles\b|\btiny\s+tates\b", "Produce > Vegetables", "Potatoes", "produce_potato_routed_as_veggie_straws"),
    (r"\bchips?\b", "Snack > Chips", "Chips", "chips_routed_as_veggie_straws"),
    (r"\b(?:salad\s+)?dressing\b", "Pantry > Salad Dressings", "Salad Dressing", "salad_dressing_routed_as_veggie_straws"),
    (r"\b(?:dressing|dip)\s+mix\b", "Pantry > Dips & Spreads", "Dip Mix", "dip_or_dressing_mix_routed_as_veggie_straws"),
    (r"\bcrisp[s]?\b", "Snack", "Crisps", "crisps_routed_as_veggie_straws"),
]


def load_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", errors="replace", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def write_csv(path: Path, fieldnames: list[str], rows: Iterable[Mapping[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def sort_fdc(row: Mapping[str, str]) -> tuple[int, int | str]:
    value = (row.get("fdc_id") or "").strip()
    return (0, int(value)) if value.isdigit() else (1, value)


def has_veggie_straws_path(row: Mapping[str, str]) -> bool:
    value = " ".join([
        row.get("product_identity_fixed", "") or "",
        row.get("canonical_path", "") or "",
        row.get("retail_leaf_path", "") or "",
    ])
    return "Veggie Straws" in value


def normalize_token(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def normalize_word(value: str) -> str:
    return WORD_ALIASES.get(value, value)


def normalized_words(value: str) -> list[str]:
    return [normalize_word(word) for word in normalize_token(value).split()]


def supported_modifier_text(row: Mapping[str, str]) -> set[str]:
    # The old canonical/reference fields often contain the bad Veggie Straws
    # route and stale flavor tails. Only the branded title is safe support for
    # carrying a modifier into the corrected snack path.
    return set(normalized_words(row.get("title", "") or ""))


def filter_supported_modifier(row: Mapping[str, str], value: str) -> str:
    source_words = supported_modifier_text(row)
    if not source_words:
        return value
    words = normalized_words(value)
    kept = [
        word
        for word in words
        if word in source_words and word not in MODIFIER_SUPPORT_STOPWORDS
    ]
    if not kept:
        return ""
    return " ".join(word.capitalize() for word in kept)


def identity_alias_tokens(identity: str) -> set[str]:
    tokens = {normalize_token(identity)}
    words = set(tokens.pop().split()) if tokens else set()
    tokens = {normalize_token(identity)}
    tokens.update(words)
    if identity.lower().endswith(" snacks"):
        tokens.add(normalize_token(identity[:-7]))
    if identity.lower().endswith(" chips"):
        tokens.add(normalize_token(identity[:-6]))
    if identity.lower().endswith(" crisps"):
        tokens.add(normalize_token(identity[:-7]))
    return {token for token in tokens if token}


def clean_modifier(row: Mapping[str, str], identity: str) -> str:
    aliases = identity_alias_tokens(identity)
    kept: list[str] = []
    for part in split_path(row.get("modifier", "") or ""):
        cleaned = normalize_path(part)
        token = normalize_token(cleaned)
        if not token or token == "plain":
            continue
        words = set(token.split())
        if token in aliases:
            continue
        if words and words <= GENERIC_MODIFIER_TOKENS:
            continue
        for alias in sorted(aliases, key=len, reverse=True):
            if alias and alias in token:
                remainder_words = set(token.replace(alias, " ").split())
                if not remainder_words or remainder_words <= GENERIC_MODIFIER_TOKENS:
                    token = ""
                    break
                cleaned = " ".join(word.capitalize() for word in token.replace(alias, " ").split())
                token = normalize_token(cleaned)
                break
        if not token:
            continue
        cleaned = filter_supported_modifier(row, cleaned)
        token = normalize_token(cleaned)
        if not token:
            continue
        if cleaned not in kept:
            kept.append(cleaned)
    return PATH_SEP.join(dedupe_segments(kept)) if kept else "<blank>"


def route_for_row(row: Mapping[str, str]) -> tuple[str, str, str] | None:
    title = row.get("title", "") or ""
    if TRUE_VEGGIE_STRAWS_RE.search(title):
        return None
    text = " ".join([
        title,
        row.get("canonical_label", "") or "",
        row.get("fndds_desc", "") or "",
    ]).lower()
    for pattern, category, identity, issue_family in ROUTE_PATTERNS:
        if re.search(pattern, text, re.I):
            return category, identity, issue_family
    current_path = " ".join([
        row.get("category_path_fixed", "") or "",
        row.get("canonical_path", "") or "",
        row.get("retail_leaf_path", "") or "",
    ])
    if "Produce > Vegetables > Veggie Straws" in current_path:
        return "Produce > Vegetables", "Vegetables", "produce_vegetable_routed_as_veggie_straws"
    if "Pantry > Grain > Veggie Straws" in current_path:
        return "Pantry > Grain", "Grain Mix", "grain_mix_routed_as_veggie_straws"
    if "Snack > Veggie Snacks > Veggie Straws" in current_path:
        return "Snack > Veggie Snacks", "Veggie Snacks", "generic_veggie_snack_routed_as_veggie_straws"
    return None


def build_override(row: Mapping[str, str]) -> dict[str, str] | None:
    if not has_veggie_straws_path(row):
        return None
    routed = route_for_row(row)
    if routed is None:
        return None
    category, identity, issue_family = routed
    modifier = clean_modifier(row, identity)
    return {
        "fdc_id": row.get("fdc_id", "") or "",
        "status": "approved",
        "owner": "codex",
        "title": row.get("title", "") or "",
        "branded_food_category": row.get("branded_food_category", "") or "",
        "current_canonical_path": row.get("canonical_path", "") or "",
        "current_retail_leaf_path": row.get("retail_leaf_path", "") or "",
        "category_path_fixed": category,
        "product_identity_fixed": identity,
        "modifier": modifier,
        "new_canonical_path": category,
        "new_product_identity": identity,
        "issue_family": issue_family,
        "reason": "Title describes a snack form other than veggie straws; route by actual shopper-facing snack identity.",
        "evidence": (
            f"title={row.get('title', '')} | bfc={row.get('branded_food_category', '')} | "
            f"current_path={row.get('retail_leaf_path', '')} | target={category} > {identity}"
        ),
    }


def review_row(row: Mapping[str, str]) -> dict[str, str]:
    return {
        "fdc_id": row.get("fdc_id", "") or "",
        "status": "review",
        "owner": "codex",
        "title": row.get("title", "") or "",
        "branded_food_category": row.get("branded_food_category", "") or "",
        "current_canonical_path": row.get("canonical_path", "") or "",
        "current_retail_leaf_path": row.get("retail_leaf_path", "") or "",
        "issue_family": "veggie_straws_identity_review",
        "likely_fix": "Review actual snack form; do not keep Veggie Straws unless title says veggie/vegetable straws.",
        "evidence": f"title={row.get('title', '')} | current_path={row.get('retail_leaf_path', '')}",
    }


def build(rows: list[dict[str, str]]) -> tuple[list[dict[str, str]], list[dict[str, str]], Counter[str]]:
    active: list[dict[str, str]] = []
    review: list[dict[str, str]] = []
    stats: Counter[str] = Counter()
    for row in rows:
        if not has_veggie_straws_path(row):
            continue
        if TRUE_VEGGIE_STRAWS_RE.search(row.get("title", "") or ""):
            stats["true_veggie_straws_kept"] += 1
            continue
        override = build_override(row)
        if override:
            active.append(override)
            stats[override["issue_family"]] += 1
        else:
            review.append(review_row(row))
            stats["veggie_straws_identity_review"] += 1
    active.sort(key=sort_fdc)
    review.sort(key=sort_fdc)
    return active, review, stats


def build_markdown(report: Mapping[str, object]) -> str:
    lines = [
        "# Consensus Snack Taxonomy Overrides",
        "",
        "Approved rows fix false `Veggie Straws` identities by routing to the actual snack form.",
        "",
        f"Approved overrides: `{report['approved_rows']:,}`",
        f"Review rows: `{report['review_rows']:,}`",
        "",
        "## Issue Counts",
        "",
    ]
    for key, value in sorted(report["issue_counts"].items()):  # type: ignore[index,union-attr]
        lines.append(f"- `{key}`: `{value:,}`")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", type=Path, default=DEFAULT_AUDIT)
    parser.add_argument("--active-out", type=Path, default=DEFAULT_ACTIVE_OUT)
    parser.add_argument("--review-out", type=Path, default=DEFAULT_REVIEW_OUT)
    parser.add_argument("--report-out", type=Path, default=DEFAULT_REPORT_OUT)
    parser.add_argument("--markdown-out", type=Path, default=DEFAULT_MD_OUT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    active, review, stats = build(load_rows(args.audit))
    write_csv(args.active_out, FIELDS, active)
    write_csv(args.review_out, REVIEW_FIELDS, review)
    report = {
        "sources": {"audit": str(args.audit)},
        "outputs": {
            "active": str(args.active_out),
            "review": str(args.review_out),
            "report": str(args.report_out),
            "markdown": str(args.markdown_out),
        },
        "approved_rows": len(active),
        "review_rows": len(review),
        "issue_counts": dict(stats.most_common()),
    }
    args.report_out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    args.markdown_out.write_text(build_markdown(report), encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
