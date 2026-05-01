#!/usr/bin/env python3
"""Build a semantic retail taxonomy table from existing retail-mapper evidence.

This compiler turns each product row into the contract documented in
``docs/retail_taxonomy_semantic_contract.md``:

    product identity + structured attributes + stable canonical path/label

It is intentionally additive. It does not modify the existing cleaned retail
leaf file; it writes a comparison artifact that can be audited before replacing
any upstream pipeline step.
"""
from __future__ import annotations

import argparse
import contextlib
import csv
import importlib.util
import io
import json
import re
import sys
import unicodedata
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


csv.field_size_limit(sys.maxsize)

REPO = Path(__file__).resolve().parents[2]
V2 = REPO / "retail_mapper" / "v2"

DEFAULT_CLEANED = V2 / "retail_leaf_v2_enriched_v2.cleaned.csv"
DEFAULT_PARSED = REPO / "retail_mapper" / "parsed_titles_with_ingredients.csv"
DEFAULT_TAXONOMY = REPO / "implementation" / "output" / "taxonomy_paths_cleaned.csv"
DEFAULT_OUTPUT = V2 / "semantic_product_taxonomy.csv"
DEFAULT_SUMMARY = V2 / "semantic_product_taxonomy_summary.json"
HEAD_DICT_PATH = REPO / "implementation" / "taxonomy_v3" / "head_dict.py"

TOKEN_RE = re.compile(r"[a-z0-9]+")
NON_WORD_RE = re.compile(r"[^a-z0-9]+")

TOP_LEVEL_ONLY = {
    "bakery",
    "beverage",
    "dairy",
    "frozen",
    "functional",
    "meal",
    "meat & seafood",
    "other",
    "pantry",
    "produce",
    "snack",
}

CATEGORY_PATH_ALIASES = {
    "Beverage > Plant-based Milk": "Beverage > Plant Milk",
    "Beverage > Dairy Milk": "Dairy > Milk",
    "Pantry > Legume > Beans": "Pantry > Legume",
}

DISPLAY_HEAD_ALIASES = {
    "BBQ Sauce": "Barbecue Sauce",
}

WEAK_FLAVOR_VALUES = {
    "classic",
    "fresh",
    "natural",
    "naturally",
    "old",
    "original",
    "premium",
    "real",
    "style",
}

IDENTITY_FORM_TOKENS = {
    "aioli",
    "bagels",
    "beans",
    "bread",
    "butter",
    "candy",
    "cereal",
    "cheese",
    "chips",
    "coffee",
    "cookies",
    "crackers",
    "dressing",
    "juice",
    "ketchup",
    "mayo",
    "mayonnaise",
    "milk",
    "mustard",
    "oil",
    "pasta",
    "pizza",
    "salsa",
    "sauce",
    "soda",
    "soup",
    "tea",
    "tomatoes",
    "vinegar",
    "yogurt",
}

FORM_TEXTURE_VALUES = {
    "chunky",
    "creamy",
    "diced",
    "ground",
    "high_pulp",
    "mini",
    "no_pulp",
    "shredded",
    "sliced",
    "smooth",
    "thick",
    "thin",
    "whole",
    "with_pulp",
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
    "fish_free": 18,
    "shellfish_free": 19,
    "caffeine_free": 20,
    "vegan": 100,
    "vegetarian": 101,
    "keto": 102,
    "paleo": 103,
    "whole30": 104,
    "kosher": 105,
    "halal": 106,
    "low_fodmap": 107,
    "sugar_free": 200,
    "zero_sugar": 201,
    "no_sugar_added": 202,
    "unsweetened": 203,
    "reduced_sugar": 204,
    "lightly_sweetened": 205,
    "sweetened": 206,
    "stevia": 207,
    "monk_fruit": 208,
    "sucralose": 209,
    "no_salt_added": 300,
    "unsalted": 301,
    "salt_free": 302,
    "low_sodium": 303,
    "reduced_sodium": 304,
    "sea_salt": 305,
    "salted": 306,
    "fat_free": 400,
    "nonfat": 401,
    "low_fat": 402,
    "reduced_fat": 403,
    "light": 404,
    "lite": 405,
    "lean": 406,
    "extra_lean": 407,
    "low_calorie": 408,
    "reduced_calorie": 409,
    "high_protein": 500,
    "probiotic": 501,
    "prebiotic": 502,
    "fortified": 503,
    "enriched": 504,
    "electrolyte": 505,
    "omega_3": 506,
    "fiber": 507,
    "whole_grain": 508,
    "sprouted": 509,
    "decaf": 510,
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
    "unrefined": 610,
    "unbleached": 611,
    "natural": 700,
    "all_natural": 701,
    "artisan": 702,
    "premium": 703,
    "gourmet": 704,
    "homestyle": 705,
    "authentic": 706,
    "hearty": 707,
    "clean_label": 708,
}

CLAIM_PATTERNS = [
    (re.compile(r"\bgluten[- ]?free\b|\bgf\b", re.I), "gluten_free"),
    (re.compile(r"\bdairy[- ]?free\b|\bnon[- ]?dairy\b", re.I), "dairy_free"),
    (re.compile(r"\blactose[- ]?free\b", re.I), "lactose_free"),
    (re.compile(r"\bnut[- ]?free\b", re.I), "nut_free"),
    (re.compile(r"\bpeanut[- ]?free\b", re.I), "peanut_free"),
    (re.compile(r"\btree[- ]?nut[- ]?free\b", re.I), "tree_nut_free"),
    (re.compile(r"\bsoy[- ]?free\b", re.I), "soy_free"),
    (re.compile(r"\begg[- ]?free\b", re.I), "egg_free"),
    (re.compile(r"\bfish[- ]?free\b", re.I), "fish_free"),
    (re.compile(r"\bshellfish[- ]?free\b", re.I), "shellfish_free"),
    (re.compile(r"\bcaffeine[- ]?free\b", re.I), "caffeine_free"),
    (re.compile(r"\bvegan\b", re.I), "vegan"),
    (re.compile(r"\bvegetarian\b", re.I), "vegetarian"),
    (re.compile(r"\bketo(?:genic)?\b", re.I), "keto"),
    (re.compile(r"\bpaleo\b", re.I), "paleo"),
    (re.compile(r"\bwhole30\b", re.I), "whole30"),
    (re.compile(r"\bkosher\b", re.I), "kosher"),
    (re.compile(r"\bhalal\b", re.I), "halal"),
    (re.compile(r"\blow[- ]?fodmap\b", re.I), "low_fodmap"),
    (re.compile(r"\bsugar[- ]?free\b", re.I), "sugar_free"),
    (re.compile(r"\bzero[- ]?sugar\b", re.I), "zero_sugar"),
    (re.compile(r"\bno[- ]?sugar[- ]?added\b", re.I), "no_sugar_added"),
    (re.compile(r"\bunsweet(?:ened)?\b", re.I), "unsweetened"),
    (re.compile(r"\breduced[- ]?sugar\b|\bless[- ]?sugar\b", re.I), "reduced_sugar"),
    (re.compile(r"\blightly[- ]?sweetened\b", re.I), "lightly_sweetened"),
    (re.compile(r"\bsweetened\b", re.I), "sweetened"),
    (re.compile(r"\bstevia\b", re.I), "stevia"),
    (re.compile(r"\bmonk[- ]?fruit\b", re.I), "monk_fruit"),
    (re.compile(r"\bsucralose\b|\bsplenda\b", re.I), "sucralose"),
    (re.compile(r"\bno[- ]?salt[- ]?added\b", re.I), "no_salt_added"),
    (re.compile(r"\bunsalted\b", re.I), "unsalted"),
    (re.compile(r"\bsalt[- ]?free\b|\bno[- ]?sodium\b", re.I), "salt_free"),
    (re.compile(r"\blow[- ]?sodium\b", re.I), "low_sodium"),
    (re.compile(r"\breduced[- ]?sodium\b", re.I), "reduced_sodium"),
    (re.compile(r"\bsea[- ]?salt\b", re.I), "sea_salt"),
    (re.compile(r"\bsalted\b", re.I), "salted"),
    (re.compile(r"\bfat[- ]?free\b", re.I), "fat_free"),
    (re.compile(r"\bnon[- ]?fat\b", re.I), "nonfat"),
    (re.compile(r"\blow[- ]?fat\b", re.I), "low_fat"),
    (re.compile(r"\breduced[- ]?fat\b", re.I), "reduced_fat"),
    (re.compile(r"\blite\b|\blight\b", re.I), "light"),
    (re.compile(r"\bextra[- ]?lean\b", re.I), "extra_lean"),
    (re.compile(r"\blean\b", re.I), "lean"),
    (re.compile(r"\blow[- ]?calorie\b", re.I), "low_calorie"),
    (re.compile(r"\breduced[- ]?calorie\b", re.I), "reduced_calorie"),
    (re.compile(r"\bhigh[- ]?protein\b", re.I), "high_protein"),
    (re.compile(r"\bprobiotic\b", re.I), "probiotic"),
    (re.compile(r"\bprebiotic\b", re.I), "prebiotic"),
    (re.compile(r"\bfortified\b", re.I), "fortified"),
    (re.compile(r"\benriched\b", re.I), "enriched"),
    (re.compile(r"\belectrolytes?\b", re.I), "electrolyte"),
    (re.compile(r"\bomega[- ]?3\b", re.I), "omega_3"),
    (re.compile(r"\bfiber\b", re.I), "fiber"),
    (re.compile(r"\bwhole[- ]?grain\b|\bwhole[- ]?wheat\b", re.I), "whole_grain"),
    (re.compile(r"\bsprouted\b", re.I), "sprouted"),
    (re.compile(r"\bdecaf(?:feinated)?\b", re.I), "decaf"),
    (re.compile(r"\borganic\b", re.I), "organic"),
    (re.compile(r"\bnon[- ]?gmo\b|\bnon[- ]?bioengineered\b", re.I), "non_gmo"),
    (re.compile(r"\bgrass[- ]?fed\b", re.I), "grass_fed"),
    (re.compile(r"\bpasture[- ]?raised\b", re.I), "pasture_raised"),
    (re.compile(r"\bfree[- ]?range\b", re.I), "free_range"),
    (re.compile(r"\bcage[- ]?free\b", re.I), "cage_free"),
    (re.compile(r"\bwild[- ]?caught\b", re.I), "wild_caught"),
    (re.compile(r"\bsustainable\b", re.I), "sustainable"),
    (re.compile(r"\bfair[- ]?trade\b", re.I), "fair_trade"),
    (re.compile(r"\bextra[- ]?virgin\b", re.I), "extra_virgin"),
    (re.compile(r"\bunrefined\b", re.I), "unrefined"),
    (re.compile(r"\bunbleached\b", re.I), "unbleached"),
    (re.compile(r"\ball[- ]?natural\b", re.I), "all_natural"),
    (re.compile(r"\bnatural\b", re.I), "natural"),
    (re.compile(r"\bartisan\b", re.I), "artisan"),
    (re.compile(r"\bpremium\b", re.I), "premium"),
    (re.compile(r"\bgourmet\b", re.I), "gourmet"),
    (re.compile(r"\bhomestyle\b", re.I), "homestyle"),
    (re.compile(r"\bauthentic\b", re.I), "authentic"),
    (re.compile(r"\bhearty\b", re.I), "hearty"),
    (re.compile(r"\bclean[- ]?label\b", re.I), "clean_label"),
]

FORM_TEXTURE_PATTERNS = [
    (re.compile(r"\b(no|without)\s+pulp\b|\bno[- ]?pulp\b|\bpulp[- ]?free\b", re.I), "no_pulp"),
    (re.compile(r"\b(with|some)\s+pulp\b", re.I), "with_pulp"),
    (re.compile(r"\b(extra|high)\s+pulp\b|\blots?\s+of\s+pulp\b", re.I), "high_pulp"),
    (re.compile(r"\bsmooth\b", re.I), "smooth"),
    (re.compile(r"\bchunky\b", re.I), "chunky"),
    (re.compile(r"\bcreamy\b", re.I), "creamy"),
    (re.compile(r"\bthin(?:ly)?\b", re.I), "thin"),
    (re.compile(r"\bthick(?:ly)?\b", re.I), "thick"),
    (re.compile(r"\bmini\b", re.I), "mini"),
]

PROCESS_PATTERNS = [
    (re.compile(r"\bnot from concentrate\b|\bnever from concentrate\b", re.I), "not_from_concentrate"),
    (re.compile(r"\bfrom concentrate\b", re.I), "from_concentrate"),
    (re.compile(r"\bcold[- ]?pressed\b", re.I), "cold_pressed"),
    (re.compile(r"\bpasteurized\b", re.I), "pasteurized"),
    (re.compile(r"\bultra[- ]?pasteurized\b|\buht\b", re.I), "ultra_pasteurized"),
    (re.compile(r"\bsparkling\b|\bcarbonated\b", re.I), "sparkling"),
    (re.compile(r"\bready[- ]?to[- ]?eat\b", re.I), "ready_to_eat"),
    (re.compile(r"\bfully[- ]?cooked\b", re.I), "fully_cooked"),
]

VALUE_ALIASES = {
    "almondmilk": "almond milk",
    "bbq": "barbecue",
    "barbeque": "barbecue",
    "cinn": "cinnamon",
    "fat free": "fat_free",
    "fat-free": "fat_free",
    "gluten free": "gluten_free",
    "gluten-free": "gluten_free",
    "low fat": "low_fat",
    "low-fat": "low_fat",
    "low sodium": "low_sodium",
    "low-sodium": "low_sodium",
    "no salt added": "no_salt_added",
    "no sugar added": "no_sugar_added",
    "non fat": "nonfat",
    "non-fat": "nonfat",
    "reduced fat": "reduced_fat",
    "reduced-fat": "reduced_fat",
    "reduced sodium": "reduced_sodium",
    "reduced-sodium": "reduced_sodium",
    "sea salt": "sea_salt",
    "sugar free": "sugar_free",
    "sugar-free": "sugar_free",
    "zero sugar": "zero_sugar",
}


@dataclass(frozen=True)
class HeadEntry:
    order: int
    head: str
    display_head: str
    category_path: str
    patterns: tuple[re.Pattern[str], ...]
    excludes: tuple[re.Pattern[str], ...]
    axes: tuple[str, ...]


@dataclass
class SemanticRecord:
    retail_type: str
    category_path: str
    taxonomy_head: str
    base_identity: str
    product_identity: str
    variant: list[str]
    flavor: list[str]
    form_texture_cut: list[str]
    processing_storage: list[str]
    claims: list[str]
    canonical_path: str
    existing_taxonomy_path: str
    canonical_label: str
    identity_source: str
    confidence: float
    mint_required: bool
    review_flags: list[str]
    notes: list[str]


def ascii_fold(value: str) -> str:
    return unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode("ascii")


def normalize_text(value: str) -> str:
    value = ascii_fold(value).lower()
    value = value.replace("&", " and ").replace("+", " and ")
    value = VALUE_ALIASES.get(value.strip(), value)
    value = NON_WORD_RE.sub(" ", value)
    return re.sub(r"\s+", " ", value).strip()


def snake(value: str) -> str:
    normalized = normalize_text(value)
    normalized = VALUE_ALIASES.get(normalized, normalized)
    return normalized.replace(" ", "_")


def tokens(value: str) -> set[str]:
    return set(TOKEN_RE.findall(normalize_text(value)))


def title_case(value: str) -> str:
    special = {
        "bbq": "BBQ",
        "mct": "MCT",
        "a2": "A2",
    }
    parts = normalize_text(value).split()
    return " ".join(special.get(part, part.capitalize()) for part in parts)


def display_value(value: str) -> str:
    special = {
        "bbq": "BBQ",
        "non_gmo": "Non-GMO",
        "omega_3": "Omega-3",
    }
    if value in special:
        return special[value]
    return title_case(value.replace("_", " "))


def dedupe(values: Iterable[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in values:
        value = snake(raw) if " " in raw or "-" in raw else raw.strip().lower()
        value = VALUE_ALIASES.get(value.replace("_", " "), value)
        value = value.replace(" ", "_")
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out


def load_head_entries(path: Path = HEAD_DICT_PATH) -> list[HeadEntry]:
    spec = importlib.util.spec_from_file_location("taxonomy_v3_head_dict", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load head dictionary from {path}")
    module = importlib.util.module_from_spec(spec)
    with contextlib.redirect_stdout(io.StringIO()):
        spec.loader.exec_module(module)
    entries: list[HeadEntry] = []
    for order, (head, category_path, patterns, excludes, axes) in enumerate(module.HEAD_DICT):
        entries.append(
            HeadEntry(
                order=order,
                head=head,
                display_head=DISPLAY_HEAD_ALIASES.get(head, head),
                category_path=category_path,
                patterns=tuple(re.compile(pattern, re.I) for pattern in patterns),
                excludes=tuple(re.compile(pattern, re.I) for pattern in excludes),
                axes=tuple(axes),
            )
        )
    return entries


def load_taxonomy_paths(path: Path) -> set[str]:
    paths: set[str] = set()
    with path.open(newline="", errors="replace") as handle:
        for row in csv.DictReader(handle):
            category_path = (row.get("category_path") or "").strip()
            head = (row.get("head") or "").strip()
            if category_path:
                paths.add(category_path)
            if category_path and head:
                paths.add(f"{category_path} > {head}")
                display_head = DISPLAY_HEAD_ALIASES.get(head, head)
                if display_head != head:
                    paths.add(f"{category_path} > {display_head}")
    return paths


def match_head(title: str, entries: list[HeadEntry], context: str = "") -> HeadEntry | None:
    context_tokens = tokens(context)
    matches: list[tuple[float, HeadEntry]] = []
    for entry in entries:
        pattern_matches = [match for pattern in entry.patterns for match in [pattern.search(title)] if match]
        if not pattern_matches:
            continue
        if any(exclude.search(title) for exclude in entry.excludes):
            continue
        best = max(pattern_matches, key=lambda match: len(match.group(0)))
        # Prefer the clearest product phrase in the title. This prevents an
        # ingredient mention like "white cheddar cheese" from beating the
        # product phrase "queso blanco".
        score = len(best.group(0)) * 10
        if best.start() <= 10:
            score += 80
        category_tokens = tokens(entry.category_path)
        head_tokens = tokens(entry.display_head)
        if head_tokens.intersection(IDENTITY_FORM_TOKENS):
            score += 60
        if category_tokens.intersection(context_tokens):
            score += 35
        if head_tokens.intersection(context_tokens):
            score += 10
        score -= best.start() * 0.05
        score -= entry.order * 0.001
        matches.append((score, entry))
    if not matches:
        return None
    matches.sort(key=lambda item: item[0], reverse=True)
    return matches[0][1]


def load_parsed_index(path: Path) -> dict[str, dict[str, str]]:
    fields = {
        "fdc_id",
        "product_description",
        "retail_type",
        "supercategory",
        "category_group",
        "category",
        "primary_food",
        "form",
        "cut",
        "prep_state",
        "storage",
        "flavor",
        "flavor_blend",
        "inclusions",
        "claims",
        "dish_type",
        "pack_format",
        "components",
        "retail_leaf",
        "confidence",
        "needs_review",
        "ing_top5",
        "ing_categories",
    }
    out: dict[str, dict[str, str]] = {}
    with path.open(newline="", errors="replace") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            fdc_id = row.get("fdc_id") or ""
            if not fdc_id:
                continue
            out[fdc_id] = {field: row.get(field, "") for field in fields}
    return out


def parse_json_list(value: str) -> list[str]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return [value]
    if isinstance(parsed, list):
        return [str(item) for item in parsed if str(item).strip()]
    return []


def flatten_claims(value: str) -> list[str]:
    if not value or value == "{}":
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return [value]
    out: list[str] = []
    if isinstance(parsed, dict):
        for key, raw_values in parsed.items():
            if isinstance(raw_values, list):
                for raw in raw_values:
                    out.append(str(raw))
                    out.append(f"{key}:{raw}")
            elif raw_values:
                out.append(str(raw_values))
                out.append(f"{key}:{raw_values}")
    elif isinstance(parsed, list):
        out.extend(str(item) for item in parsed)
    return out


def claims_from_text(*values: str) -> list[str]:
    text = " ".join(value or "" for value in values)
    claims = [claim for pattern, claim in CLAIM_PATTERNS if pattern.search(text)]
    return sort_claims(dedupe(claims))


def normalize_claims(parsed_claims: str, title: str, bfc: str, esha_desc: str) -> list[str]:
    values = flatten_claims(parsed_claims)
    raw_text = " ".join(values + [title, bfc, esha_desc])
    return claims_from_text(raw_text)


def sort_claims(values: Iterable[str]) -> list[str]:
    return sorted(dedupe(values), key=lambda value: (CLAIM_ORDER.get(value, 9999), value))


def values_from_patterns(patterns: list[tuple[re.Pattern[str], str]], text: str) -> list[str]:
    return [value for pattern, value in patterns if pattern.search(text)]


def clean_attr_value(value: str) -> str:
    value = snake(value)
    # Keep useful compounds; drop one-word junk that acts as marketing.
    if value in {"", "none", "null"}:
        return ""
    return value


def identity_token_filter(values: Iterable[str], product_identity: str) -> list[str]:
    identity_tokens = tokens(product_identity)
    identity_snake = snake(product_identity)
    out: list[str] = []
    for value in values:
        normalized = clean_attr_value(value)
        if not normalized:
            continue
        value_tokens = set(normalized.split("_"))
        if normalized == identity_snake:
            continue
        if value_tokens and value_tokens.issubset(identity_tokens):
            continue
        out.append(normalized)
    return dedupe(out)


def extract_flavor(parsed: dict[str, str], title: str, product_identity: str) -> list[str]:
    values: list[str] = []
    flavor = (parsed.get("flavor") or "").strip()
    if flavor and normalize_text(flavor) not in WEAK_FLAVOR_VALUES:
        values.append(flavor)
    values.extend(parse_json_list(parsed.get("flavor_blend", "")))

    text = normalize_text(title)
    phrase_flavors = [
        ("brown sugar", "brown_sugar"),
        ("sea salt caramel", "sea_salt_caramel"),
        ("salted caramel", "salted_caramel"),
        ("peanut butter", "peanut_butter"),
        ("sour cream", "sour_cream"),
        ("green chile", "green_chile"),
        ("green chiles", "green_chile"),
        ("chipotle", "chipotle"),
        ("hickory", "hickory"),
        ("applewood", "applewood"),
        ("maple", "maple"),
        ("honey", "honey"),
        ("garlic", "garlic"),
        ("ranch", "ranch"),
        ("buffalo", "buffalo"),
        ("spicy", "spicy"),
        ("vanilla", "vanilla"),
        ("chocolate", "chocolate"),
        ("strawberry", "strawberry"),
        ("cinnamon", "cinnamon"),
        ("lemon", "lemon"),
        ("lime", "lime"),
    ]
    for phrase, normalized in phrase_flavors:
        if phrase in text:
            values.append(normalized)
    return identity_token_filter(values, product_identity)


def extract_form_texture(parsed: dict[str, str], title: str, esha_desc: str, product_identity: str) -> list[str]:
    values: list[str] = []
    title_values = values_from_patterns(FORM_TEXTURE_PATTERNS, title)
    desc_values = values_from_patterns(FORM_TEXTURE_PATTERNS, esha_desc)
    values.extend(title_values)
    values.extend(desc_values)
    for field in ("cut",):
        raw = (parsed.get(field) or "").strip()
        if raw:
            values.append(raw)
    # ESHA often records black beans as "whole, canned" even when parser was
    # pulled toward the "salt" token.
    if "whole" in normalize_text(esha_desc):
        values.append("whole")
    if "no_pulp" in title_values:
        values = [value for value in values if value not in {"with_pulp", "high_pulp"}]
    return identity_token_filter(values, product_identity)


def extract_processing(parsed: dict[str, str], title: str, esha_desc: str, product_identity: str) -> list[str]:
    values: list[str] = []
    text = f"{title} {esha_desc}"
    values.extend(values_from_patterns(PROCESS_PATTERNS, text))
    for field in ("prep_state", "storage"):
        raw = (parsed.get(field) or "").strip()
        if snake(raw) in FORM_TEXTURE_VALUES:
            continue
        if raw:
            values.append(raw)
    if "not_from_concentrate" in values:
        values = [value for value in values if value != "from_concentrate"]
    return identity_token_filter(values, product_identity)


def base_identity_for(product_identity: str) -> str:
    normalized = normalize_text(product_identity)
    if normalized.endswith(" beans") and normalized not in {"coffee beans", "green beans"}:
        return "Beans"
    if normalized.endswith(" tomatoes") and normalized not in {"sun dried tomatoes"}:
        return "Tomatoes"
    if normalized in {"diet soda", "zero sugar soda"}:
        return "Soda"
    if normalized in {"skim milk", "low fat milk", "reduced fat milk", "whole milk"}:
        return "Milk"
    return product_identity


def fallback_identity(parsed: dict[str, str], cleaned: dict[str, str]) -> tuple[str, str, str]:
    category_path = ""
    supercategory = (parsed.get("supercategory") or cleaned.get("parser_supercategory") or "").strip()
    category_group = (parsed.get("category_group") or cleaned.get("parser_category_group") or "").strip()
    category = (parsed.get("category") or cleaned.get("parser_category") or "").strip()
    primary = (parsed.get("primary_food") or cleaned.get("parser_primary_food") or "").strip()
    form = (parsed.get("form") or cleaned.get("parser_form") or "").strip()

    if supercategory and category_group and category_group.lower() not in TOP_LEVEL_ONLY:
        category_path = f"{supercategory} > {category_group}"
    elif supercategory and category:
        category_path = f"{supercategory} > {category}"
    elif supercategory:
        category_path = supercategory

    if category and category.lower() not in {"unclassified", "other"}:
        identity = category
    elif primary and form and normalize_text(primary) != normalize_text(form):
        identity = f"{primary} {form}"
    elif primary:
        identity = primary
    elif form:
        identity = form
    else:
        identity = ""

    return category_path, title_case(identity), "parser_fallback"


def build_label(product_identity: str, *attribute_groups: list[str]) -> str:
    attrs: list[str] = []
    seen: set[str] = set()
    identity_tokens = tokens(product_identity)
    for group in attribute_groups:
        for value in group:
            if not value or value in seen:
                continue
            if set(value.split("_")).issubset(identity_tokens):
                continue
            seen.add(value)
            attrs.append(display_value(value))
    if not attrs:
        return product_identity
    return f"{product_identity} ({', '.join(attrs)})"


def is_too_shallow(path: str) -> bool:
    parts = [part.strip() for part in path.split(">") if part.strip()]
    return len(parts) <= 1 and (not parts or parts[-1].lower() in TOP_LEVEL_ONLY)


def normalize_category_path(path: str) -> str:
    path = " > ".join(part.strip() for part in path.split(">") if part.strip())
    return CATEGORY_PATH_ALIASES.get(path, path)


def compile_record(
    cleaned: dict[str, str],
    parsed: dict[str, str],
    head_entries: list[HeadEntry],
    taxonomy_paths: set[str],
) -> SemanticRecord:
    title = cleaned.get("title") or parsed.get("product_description") or ""
    current_esha_desc = cleaned.get("current_esha_desc") or ""
    bfc = cleaned.get("branded_food_category") or ""
    retail_type = parsed.get("retail_type") or cleaned.get("parser_retail_type") or "single"
    notes: list[str] = []
    review_flags: list[str] = []

    source_leaf = cleaned.get("clean_retail_leaf") or cleaned.get("retail_leaf") or ""
    head_context = " ".join(
        [
            cleaned.get("branded_food_category") or "",
            source_leaf,
        ]
    )
    head_entry = match_head(title, head_entries, head_context)
    if head_entry:
        category_path = normalize_category_path(head_entry.category_path)
        taxonomy_head = head_entry.head
        product_identity = head_entry.display_head
        identity_source = "head_dict"
        confidence = 0.95
    else:
        category_path, product_identity, identity_source = fallback_identity(parsed, cleaned)
        category_path = normalize_category_path(category_path)
        taxonomy_head = product_identity
        confidence = 0.55 if product_identity and category_path else 0.0
        review_flags.append("head_dict_no_match")

    if not product_identity:
        review_flags.append("identity_missing")
        product_identity = "Unclassified"
    if not category_path or is_too_shallow(category_path):
        review_flags.append("category_path_too_shallow")
        if not category_path:
            category_path = "Other > Unclassified"

    base_identity = base_identity_for(product_identity)
    variant: list[str] = []
    flavor = extract_flavor(parsed, title, product_identity)
    form_texture_cut = extract_form_texture(parsed, title, current_esha_desc, product_identity)
    processing_storage = extract_processing(parsed, title, current_esha_desc, product_identity)
    claims = normalize_claims(parsed.get("claims", ""), title, bfc, current_esha_desc)
    claims = identity_token_filter(claims, product_identity)
    claims = sort_claims(claims)

    canonical_path = f"{category_path} > {product_identity}"
    existing_taxonomy_path = canonical_path if canonical_path in taxonomy_paths else ""
    raw_taxonomy_path = f"{category_path} > {taxonomy_head}"
    if not existing_taxonomy_path and raw_taxonomy_path in taxonomy_paths:
        existing_taxonomy_path = raw_taxonomy_path

    mint_required = not bool(existing_taxonomy_path)
    if mint_required:
        review_flags.append("mint_required")

    if source_leaf and is_too_shallow(source_leaf):
        notes.append("source_path_too_shallow_repaired")

    parser_needs_review = parsed.get("needs_review") or cleaned.get("parser_needs_review") or ""
    if parser_needs_review and parser_needs_review not in {"[]", ""}:
        notes.append("parser_needs_review")

    if retail_type == "combo_pack":
        review_flags.append("combo_pack_component_schema_needed")
    elif retail_type == "composite_dish":
        review_flags.append("composite_dish_schema_needed")

    esha_tokens = tokens(current_esha_desc.split(",")[0] if current_esha_desc else "")
    identity_tokens = tokens(product_identity)
    if current_esha_desc and esha_tokens and identity_tokens and not esha_tokens.intersection(identity_tokens):
        if identity_source == "head_dict":
            notes.append("esha_identity_mismatch")

    canonical_label = build_label(
        product_identity,
        variant,
        flavor,
        form_texture_cut,
        processing_storage,
        claims,
    )

    return SemanticRecord(
        retail_type=retail_type,
        category_path=category_path,
        taxonomy_head=taxonomy_head,
        base_identity=base_identity,
        product_identity=product_identity,
        variant=variant,
        flavor=flavor,
        form_texture_cut=form_texture_cut,
        processing_storage=processing_storage,
        claims=claims,
        canonical_path=canonical_path,
        existing_taxonomy_path=existing_taxonomy_path,
        canonical_label=canonical_label,
        identity_source=identity_source,
        confidence=confidence,
        mint_required=mint_required,
        review_flags=dedupe(review_flags),
        notes=dedupe(notes),
    )


OUTPUT_FIELDS = [
    "fdc_id",
    "gtin_upc",
    "title",
    "branded_food_category",
    "current_esha",
    "current_esha_desc",
    "source_clean_retail_leaf",
    "source_parser_primary_food",
    "source_parser_form",
    "source_parser_flavor",
    "retail_type",
    "category_path",
    "taxonomy_head",
    "base_identity",
    "product_identity",
    "variant",
    "flavor",
    "form_texture_cut",
    "processing_storage",
    "claims",
    "canonical_path",
    "existing_taxonomy_path",
    "canonical_label",
    "identity_source",
    "confidence",
    "mint_required",
    "review_flags",
    "notes",
    "attributes_json",
]


def list_cell(values: Iterable[str]) -> str:
    return " | ".join(values)


def output_row(cleaned: dict[str, str], parsed: dict[str, str], record: SemanticRecord) -> dict[str, str]:
    attributes = {
        "variant": record.variant,
        "flavor": record.flavor,
        "form_texture_cut": record.form_texture_cut,
        "processing_storage": record.processing_storage,
        "claims": record.claims,
    }
    return {
        "fdc_id": cleaned.get("fdc_id", ""),
        "gtin_upc": cleaned.get("gtin_upc", ""),
        "title": cleaned.get("title") or parsed.get("product_description", ""),
        "branded_food_category": cleaned.get("branded_food_category", ""),
        "current_esha": cleaned.get("current_esha", ""),
        "current_esha_desc": cleaned.get("current_esha_desc", ""),
        "source_clean_retail_leaf": cleaned.get("clean_retail_leaf") or cleaned.get("retail_leaf", ""),
        "source_parser_primary_food": cleaned.get("parser_primary_food") or parsed.get("primary_food", ""),
        "source_parser_form": cleaned.get("parser_form") or parsed.get("form", ""),
        "source_parser_flavor": cleaned.get("parser_flavor") or parsed.get("flavor", ""),
        "retail_type": record.retail_type,
        "category_path": record.category_path,
        "taxonomy_head": record.taxonomy_head,
        "base_identity": record.base_identity,
        "product_identity": record.product_identity,
        "variant": list_cell(record.variant),
        "flavor": list_cell(record.flavor),
        "form_texture_cut": list_cell(record.form_texture_cut),
        "processing_storage": list_cell(record.processing_storage),
        "claims": list_cell(record.claims),
        "canonical_path": record.canonical_path,
        "existing_taxonomy_path": record.existing_taxonomy_path,
        "canonical_label": record.canonical_label,
        "identity_source": record.identity_source,
        "confidence": f"{record.confidence:.2f}",
        "mint_required": str(record.mint_required),
        "review_flags": list_cell(record.review_flags),
        "notes": list_cell(record.notes),
        "attributes_json": json.dumps(attributes, sort_keys=True, separators=(",", ":")),
    }


def update_counters(counters: dict[str, Counter], record: SemanticRecord) -> None:
    status = "review" if record.review_flags else "ok"
    counters["status"].update([status])
    counters["identity_source"].update([record.identity_source])
    counters["retail_type"].update([record.retail_type])
    counters["category_path"].update([record.category_path])
    counters["product_identity"].update([record.product_identity])
    counters["canonical_path"].update([record.canonical_path])
    for claim in record.claims:
        counters["claims"].update([claim])
    for flag in record.review_flags:
        counters["review_flags"].update([flag])
    for note in record.notes:
        counters["notes"].update([note])


def summary_payload(rows_total: int, counters: dict[str, Counter], output: Path) -> dict[str, object]:
    def top(counter_name: str, n: int = 30) -> dict[str, int]:
        return dict(counters[counter_name].most_common(n))

    singleton_paths = sum(1 for value in counters["canonical_path"].values() if value == 1)
    unique_paths = len(counters["canonical_path"])
    return {
        "rows_total": rows_total,
        "output": str(output),
        "status": top("status"),
        "identity_source": top("identity_source"),
        "retail_type": top("retail_type"),
        "review_flags": top("review_flags"),
        "notes": top("notes"),
        "claims": top("claims"),
        "category_path": top("category_path"),
        "product_identity": top("product_identity"),
        "unique_canonical_paths": unique_paths,
        "singleton_canonical_paths": singleton_paths,
        "singleton_canonical_path_rate": round(singleton_paths / unique_paths, 4) if unique_paths else 0,
    }


def build(args: argparse.Namespace) -> None:
    print("loading parsed index...", flush=True)
    parsed_index = load_parsed_index(args.parsed)
    print(f"  parsed rows: {len(parsed_index):,}", flush=True)

    print("loading taxonomy/head dictionary...", flush=True)
    head_entries = load_head_entries()
    taxonomy_paths = load_taxonomy_paths(args.taxonomy)
    print(f"  head entries: {len(head_entries):,}", flush=True)
    print(f"  taxonomy paths: {len(taxonomy_paths):,}", flush=True)

    counters: dict[str, Counter] = {
        "status": Counter(),
        "identity_source": Counter(),
        "retail_type": Counter(),
        "category_path": Counter(),
        "product_identity": Counter(),
        "canonical_path": Counter(),
        "claims": Counter(),
        "review_flags": Counter(),
        "notes": Counter(),
    }
    wanted_fdc = set(args.fdc_id or [])
    rows_total = 0
    rows_written = 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.cleaned.open(newline="", errors="replace") as fin, args.output.open("w", newline="") as fout:
        reader = csv.DictReader(fin)
        writer = csv.DictWriter(fout, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        for cleaned in reader:
            fdc_id = cleaned.get("fdc_id") or ""
            if wanted_fdc and fdc_id not in wanted_fdc:
                continue
            parsed = parsed_index.get(fdc_id, {})
            record = compile_record(cleaned, parsed, head_entries, taxonomy_paths)
            writer.writerow(output_row(cleaned, parsed, record))
            update_counters(counters, record)
            rows_total += 1
            rows_written += 1
            if args.limit and rows_written >= args.limit:
                break
            if rows_written % 50000 == 0:
                print(f"  wrote {rows_written:,}", flush=True)

    payload = summary_payload(rows_total, counters, args.output)
    args.summary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(f"wrote {args.output} ({rows_written:,} rows)", flush=True)
    print(f"wrote {args.summary}", flush=True)
    print(json.dumps(payload["status"], sort_keys=True), flush=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build semantic product taxonomy CSV.")
    parser.add_argument("--cleaned", type=Path, default=DEFAULT_CLEANED)
    parser.add_argument("--parsed", type=Path, default=DEFAULT_PARSED)
    parser.add_argument("--taxonomy", type=Path, default=DEFAULT_TAXONOMY)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--fdc-id", action="append", default=[])
    return parser.parse_args()


if __name__ == "__main__":
    build(parse_args())
