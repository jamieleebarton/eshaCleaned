from __future__ import annotations

import argparse
import csv
import fcntl
import html
import json
import re
import sqlite3
from collections import Counter
from pathlib import Path

# This mapper intentionally has many reviewed regex cleanup rules. Python's
# default re cache is too small and recompiles them per line, which makes full
# queue rebuilds look hung. Keep the reviewed one-source rules, but cache them.
try:
    re._MAXCACHE = max(getattr(re, "_MAXCACHE", 512), 8192)
except Exception:
    pass

try:
    from build_codex_base_dictionary import clean_row
    from export_full_funnel_csv import simple_surface_candidate
    from resolver_context import DEFAULT_ARTIFACTS
    from identity_poison import is_poison_base
except ModuleNotFoundError:
    from implementation.build_codex_base_dictionary import clean_row
    from implementation.export_full_funnel_csv import simple_surface_candidate
    from implementation.resolver_context import DEFAULT_ARTIFACTS
    from implementation.identity_poison import is_poison_base


ROOT = Path(__file__).resolve().parent
DEFAULT_INPUT_DB = DEFAULT_ARTIFACTS.recipe_funnel_db
DEFAULT_DICTIONARY_CSV = DEFAULT_ARTIFACTS.dictionary_csv
DEFAULT_SUPPLEMENTAL_CSV = DEFAULT_ARTIFACTS.supplemental_concepts_csv
DEFAULT_APPROVED_RULES_CSV = DEFAULT_ARTIFACTS.approved_normalization_rules_csv
DEFAULT_OUTPUT_CSV = DEFAULT_ARTIFACTS.ge10_line_mapping_csv
DEFAULT_SUMMARY_JSON = DEFAULT_ARTIFACTS.ge10_line_mapping_summary_json
DEFAULT_MISSES_CSV = DEFAULT_ARTIFACTS.ge10_line_mapping_misses_csv
DEFAULT_REPORT_MD = DEFAULT_ARTIFACTS.ge10_line_mapping_report_md
DEFAULT_FULL_OUTPUT_CSV = DEFAULT_ARTIFACTS.full_line_mapping_csv
DEFAULT_FULL_SUMMARY_JSON = DEFAULT_ARTIFACTS.full_line_mapping_summary_json
DEFAULT_FULL_MISSES_CSV = DEFAULT_ARTIFACTS.full_line_mapping_misses_csv
DEFAULT_FULL_REPORT_MD = DEFAULT_ARTIFACTS.full_line_mapping_report_md

SIZE_VARIANTS = {"large", "medium", "small", "mini", "jumbo", "tiny"}
PREP_FORMS = {
    "chopped",
    "minced",
    "diced",
    "sliced",
    "slice",
    "grated",
    "shredded",
    "coarse",
    "cracked",
    "crushed",
    "mashed",
}
SAFE_FALLBACK_STATES = {"", "fresh"}

MECHANICAL_SOURCE_REPLACEMENTS = (
    (re.compile(r"\bgrnd\b"), "ground"),
    (re.compile(r"\bfresh-ground\b"), "fresh ground"),
    (re.compile(r"\bfreshly-grnd\b"), "freshly ground"),
    (re.compile(r"\bsemi-sweet\b"), "semisweet"),
    (re.compile(r"\bchily\b"), "chili"),
    (re.compile(r"\bchilly\b"), "chili"),
    (re.compile(r"\bboullion\b"), "bouillon"),
    (re.compile(r"\bbullion\b"), "bouillon"),
    (re.compile(r"\bchedder\b"), "cheddar"),
    (re.compile(r"\bcondense\b"), "condensed"),
    (re.compile(r"\bcooky\b"), "cookie"),
    (re.compile(r"\bcouscou\b"), "couscous"),
    (re.compile(r"\boilve\b"), "olive"),
    (re.compile(r"\brugula\b"), "arugula"),
    (re.compile(r"\btumeric\b"), "turmeric"),
)
MATCHED_STATUSES = {
    "approved_alias_match",
    "approved_alternative_match",
    "approved_manual_quantity_match",
    "approved_split_match",
    "surface_alias_match",
    "qualified_match",
    "singular_alias_match",
    "base_row_fallback_match",
    "compound_alias_match",
    "base_alias_fallback_match",
    "supplemental_exact_usda_anchor_match",
    "supplemental_reviewed_local_label_anchor_match",
    "supplemental_reviewed_proxy_match",
}


def acquire_output_lock(lock_path: Path):
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = lock_path.open("w", encoding="utf-8")
    fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
    return handle


def release_output_lock(handle) -> None:
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    finally:
        handle.close()


def temporary_output_path(path: Path) -> Path:
    return path.with_name(f".{path.name}.tmp")
BLOCKED_FRAGMENT_SURFACES = {
    "black",
    "brown",
    "fresh",
    "frozen",
    "powder",
    "white",
    "yellow",
}
NON_FOOD_SURFACES = {
    "optional",
    "toothpick",
    "toothpicks",
    "(see note)",
    "remaining ingredient:",
    "remaining ingredient.",
    # Kitchen equipment / wrapping materials
    "wooden skewer",
    "wooden skewers",
    "bamboo skewer",
    "bamboo skewers",
    "skewers",
    "metal skewers",
    "aluminum foil",
    "foil",
    "plastic wrap",
    "parchment paper",
    "wax paper",
    "cheesecloth",
    "kitchen twine",
    "butcher's twine",
    "butchers twine",
    "kitchen string",
    "rubber band",
    "toothpick or skewer",
    "paper towel",
    "paper towels",
    "cupcake liner",
    "cupcake liners",
    "muffin liner",
    "muffin liners",
    "paper liners",
    # Assorted / generic non-ingredients
    "assorted crackers",
    "assorted cracker",
    "assorted fresh fruit",
    "assorted fresh vegetables",
    "assorted fresh fruits",
    "assorted fresh vegetable",
    "assorted fruit",
    "assorted vegetables",
    "assorted toppings",
    "assorted",
    # Standalone qualifiers that resolved to nothing
    "additional",
    "extra",
    "more",
    "remaining",
    "other",
    "misc",
    "miscellaneous",
}
NON_FOOD_PATTERNS = [
    re.compile(r"^_{3,}$"),
    re.compile(r"^-{3,}$"),
    re.compile(r"^={3,}$"),
    re.compile(r"^\*{3,}$"),
    re.compile(r"^[~`]{2,}"),
    re.compile(r"^~\s*\S"),
    re.compile(r"^copyright\b"),
    re.compile(r"all rights reserved\.?$"),
    re.compile(r"^this recipe (?:was|has been)\b"),
    re.compile(r"^additional required ingredients"),
    re.compile(r"^required ingredients"),
    re.compile(r"\bingredients specified\b"),
    re.compile(r"^serving size[:\s]"),
    re.compile(r"^nutrition (?:information|facts)"),
    re.compile(r"\b(?:wooden|bamboo|metal)\s+skewers?\b"),
    re.compile(r"\baluminum\s+foil\b"),
    re.compile(r"\bparchment\s+paper\b"),
    re.compile(r"\bplastic\s+wrap\b"),
    re.compile(r"\bwax\s+paper\b"),
    re.compile(r"\bcheesecloth\b"),
    re.compile(r"\bkitchen\s+(?:twine|string)\b"),
    re.compile(r"\bbutcher'?s?\s+twine\b"),
    re.compile(r"\b(?:cupcake|muffin|paper)\s+liners?\b"),
    re.compile(r"^assorted\s+"),
    re.compile(r"^additional\s+required\b"),
    re.compile(r"^\d+(?:[./]\d+)?\s*(?:teaspoons?|tsps?|tablespoons?|tbsps?|tbs\.?|cups?|c\.?|ounces?|oz\.?|pounds?|lbs?\.?|pints?|pts?|quarts?|qts?|gallons?|gals?)\s*$"),
    re.compile(r"^chopped$|^diced$|^sliced$|^minced$|^grated$|^shredded$|^cubed$|^crushed$|^softened$|^melted$|^beaten$|^drained$|^cooked$|^uncooked$|^raw$"),
]
SECTION_HEADER_PATTERNS = [
    re.compile(r":\s*$"),
    re.compile(r"^for\s+the\s+.+:?$"),
    re.compile(r"^(?:dry|wet|salad|cake|crust|frosting|filling|main|other|optional)\s+ingredients:?$"),
    re.compile(r"^(?:to|for)\s+(?:assemble|serve|finish|garnish|decorate):?$"),
    re.compile(r"^(?:accompaniments?|toppings?|optional toppings?|garnishes?|assembly):?$"),
    re.compile(r"^serve\s+with:?$"),
    re.compile(r"^\s*or\s*$"),
    re.compile(r"^\s*and\s*$"),
    re.compile(r"^\s*:\s*$"),
    re.compile(r"^\s*\.\s*$"),
    re.compile(r"^\s*,\s*$"),
    re.compile(r"^\s*\)\s*$"),
    re.compile(r"^\s*\(\s*$"),
    re.compile(r"^\s*$"),
]
VEGETABLE_PEPPER_CUES = {
    "chopped",
    "diced",
    "large",
    "medium",
    "minced",
    "sliced",
    "small",
    "whole",
}

SUPPLEMENTAL_FIELDS = [
    "supplemental_canonical_concept",
    "supplemental_family",
    "supplemental_trust_state",
    "supplemental_nutrition_state",
    "supplemental_shopping_state",
    "supplemental_anchor_system",
    "supplemental_anchor_code",
    "supplemental_anchor_description",
    "supplemental_product_query",
    "supplemental_evidence_notes",
]

ROUTING_FIELDS = [
    "resolution_route",
    "resolution_action",
    "resolution_reason",
]

APPROVED_RULE_FIELDS = [
    "approved_rule_id",
    "approved_rule_type",
    "approved_rule_components",
]


UNITS = (
    "tablespoons",
    "tablespoon",
    "teaspoons",
    "teaspoon",
    "packages",
    "package",
    "ounces",
    "ounce",
    "pounds",
    "pound",
    "cloves",
    "clove",
    "sprigs",
    "sprig",
    "slices",
    "slice",
    "sticks",
    "stick",
    "quarts",
    "quart",
    "qts",
    "qt",
    "pints",
    "pint",
    "pts",
    "pt",
    "cups",
    "cup",
    "c",
    "cans",
    "can",
    "grams",
    "gram",
    "kilograms",
    "kg",
    "milliliters",
    "ml",
    "liters",
    "liter",
    "lbs",
    "lb",
    "oz",
    "tbsp",
    "tbs",
    "tbls",
    "tbl",
    "tsp",
    "t",
    "dash",
    "pinch",
    "bunches",
    "bunch",
    "piece",
    "pieces",
    "fluid ounces",
    "fluid ounce",
    "fl oz",
    "each",
    "x",
    "pkg",
    "pkgs",
    "pkt",
    "pkts",
    "pack",
    "packs",
    "packets",
    "packet",
    "envelopes",
    "envelope",
    "boxes",
    "box",
    "jars",
    "jar",
    "bottles",
    "bottle",
    "tubs",
    "tub",
    "bags",
    "bag",
    "loaves",
    "loaf",
    "heads",
    "head",
    "bundles",
    "bundle",
    "recipes",
    "recipe",
    "stalks",
    "stalk",
    "ribs",
    "rib",
    "rounds",
    "round",
    "gallons",
    "gallon",
    "gal",
    "g",
    "l",
)

NUMBER_ATOM = r"(?:\d+(?:[./⁄]\d+)?|\.\d+|[¼½¾⅓⅔⅛⅜⅝⅞]|one|two|three|four|five|six|seven|eight|nine|ten|a|an)"
NUMBER_TOKEN = rf"(?:{NUMBER_ATOM}(?:\s+{NUMBER_ATOM})?)"
LEADING_MEASURE_RE = re.compile(
    rf"""
    ^\s*
    (?P<quantity>{NUMBER_TOKEN}(?:\s*(?:-|to|or)\s*{NUMBER_TOKEN})?)
    \s*
    (?P<unit>{'|'.join(re.escape(unit) for unit in UNITS)})?
    [\.,]?
    \s+
    (?P<food>.+?)
    \s*$
    """,
    re.IGNORECASE | re.VERBOSE,
)

CITRUS_WORD_PATTERN = r"(?P<citrus>lemon|lime|orange|grapefruit)s?"

UNICODE_FRACTIONS = {
    "¼": 0.25,
    "½": 0.5,
    "¾": 0.75,
    "⅓": 1 / 3,
    "⅔": 2 / 3,
    "⅛": 0.125,
    "⅜": 0.375,
    "⅝": 0.625,
    "⅞": 0.875,
}

WORD_NUMBERS = {
    "a": 1.0,
    "an": 1.0,
    "one": 1.0,
    "two": 2.0,
    "three": 3.0,
    "four": 4.0,
    "five": 5.0,
    "six": 6.0,
    "seven": 7.0,
    "eight": 8.0,
    "nine": 9.0,
    "ten": 10.0,
}


def numeric_quantity_token(value: str) -> float | None:
    total = 0.0
    found = False
    for token in (value or "").strip().lower().replace("⁄", "/").split():
        if token in UNICODE_FRACTIONS:
            total += UNICODE_FRACTIONS[token]
            found = True
        elif token in WORD_NUMBERS:
            total += WORD_NUMBERS[token]
            found = True
        elif re.fullmatch(r"(?:\d+(?:\.\d+)?|\.\d+)", token):
            total += float(token)
            found = True
        elif re.fullmatch(r"\d+/\d+", token):
            numerator, denominator = token.split("/", 1)
            total += float(numerator) / float(denominator)
            found = True
    return total if found else None


def format_quantity(value: float) -> str:
    if abs(value - round(value)) < 0.000001:
        return str(int(round(value)))
    return f"{value:.4f}".rstrip("0").rstrip(".")


PACKAGE_SIZE_UNIT_PATTERN = (
    r"fluid\ ounces?\.?|fl\.?\s*oz\.?|ounces?\.?|oz\.?|"
    r"pounds?\.?|lbs?\.?|grams?\.?|g|kilograms?\.?|kg|"
    r"milliliters?\.?|ml|liters?\.?|l"
)
PACKAGE_CONTAINER_PATTERN = (
    r"cans?|packages?|pkgs?\.?|packets?|jars?|bottles?|"
    r"box(?:es)?|bags?|tubs?|containers?|cartons?|envelopes?"
)


def normalize_package_size_unit(unit: str) -> str:
    unit = (unit or "").lower().replace(".", "")
    unit = re.sub(r"\s+", " ", unit).strip()
    if unit in {"fl oz", "fluid ounce", "fluid ounces"}:
        return "fluid ounce"
    if unit in {"oz", "ounce", "ounces"}:
        return "ounce"
    if unit in {"lb", "lbs", "pound", "pounds"}:
        return "pound"
    if unit in {"g", "gram", "grams"}:
        return "gram"
    if unit in {"kg", "kilogram", "kilograms"}:
        return "kg"
    if unit in {"ml", "milliliter", "milliliters"}:
        return "ml"
    if unit in {"l", "liter", "liters"}:
        return "liter"
    return unit


def package_weight_parse_result(
    *,
    count_text: str,
    size_text: str,
    size_unit_text: str,
    food_phrase: str,
) -> dict[str, str] | None:
    count = numeric_quantity_token(count_text or "1") or 1.0
    size = numeric_quantity_token(size_text or "")
    if size is None:
        return None
    size_unit = normalize_package_size_unit(size_unit_text)
    food_phrase = food_phrase.strip(" ,.-")
    surface = refine_surface(surface_candidate_from_parsed_food(food_phrase))
    return {
        "parsed_quantity": format_quantity(count * size),
        "parsed_unit": size_unit,
        "parsed_food_phrase": food_phrase,
        "cleaned_surface": surface,
    }


def package_pounds_ounces_parse_result(
    *,
    count_text: str,
    pounds_text: str,
    ounces_text: str,
    food_phrase: str,
) -> dict[str, str] | None:
    count = numeric_quantity_token(count_text or "1") or 1.0
    pounds = numeric_quantity_token(pounds_text or "")
    ounces = numeric_quantity_token(ounces_text or "")
    if pounds is None or ounces is None:
        return None
    food_phrase = food_phrase.strip(" ,.-")
    surface = refine_surface(surface_candidate_from_parsed_food(food_phrase))
    return {
        "parsed_quantity": format_quantity(count * ((pounds * 16.0) + ounces)),
        "parsed_unit": "ounce",
        "parsed_food_phrase": food_phrase,
        "cleaned_surface": surface,
    }
CITRUS_AMOUNT_PATTERN = rf"(?:{NUMBER_TOKEN}\s+)?(?:(?:large|medium|small)\s+)?"
CITRUS_PREP_PATTERN = r"(?:(?:finely|freshly)\s+)?(?:grated|shredded)\s+"
CITRUS_ZEST_WORD_PATTERN = r"(?:zest|rind|peel)"

CITRUS_ZEST_ONLY_PATTERNS = [
    rf"^{CITRUS_PREP_PATTERN}{CITRUS_ZEST_WORD_PATTERN}\s+of\s+{CITRUS_AMOUNT_PATTERN}{CITRUS_WORD_PATTERN}$",
    rf"^{CITRUS_ZEST_WORD_PATTERN}\s+of\s+{CITRUS_AMOUNT_PATTERN}{CITRUS_WORD_PATTERN}(?:,\s*(?:finely\s+)?grated)?$",
    rf"^{CITRUS_PREP_PATTERN}{CITRUS_WORD_PATTERN},\s*{CITRUS_ZEST_WORD_PATTERN}\s+of$",
    rf"^{CITRUS_WORD_PATTERN},\s*(?:grated\s+)?{CITRUS_ZEST_WORD_PATTERN}\s+of(?:,\s*(?:finely\s+)?grated)?$",
    rf"^{CITRUS_WORD_PATTERN},\s*grated\s+{CITRUS_ZEST_WORD_PATTERN}\s+of$",
]

CITRUS_JUICE_ZEST_PATTERNS = [
    rf"^juice\s+and\s+(?:{CITRUS_PREP_PATTERN})?{CITRUS_ZEST_WORD_PATTERN}\s+of\s+{CITRUS_AMOUNT_PATTERN}{CITRUS_WORD_PATTERN}$",
    rf"^(?:{CITRUS_PREP_PATTERN})?{CITRUS_WORD_PATTERN},\s*juice\s+and\s+(?:{CITRUS_PREP_PATTERN})?{CITRUS_ZEST_WORD_PATTERN}\s+of(?:,\s*(?:finely\s+)?grated)?$",
    rf"^{CITRUS_WORD_PATTERN},\s*juice\s+and\s+(?:{CITRUS_PREP_PATTERN})?{CITRUS_ZEST_WORD_PATTERN}\s+of(?:,\s*(?:finely\s+)?grated)?$",
    rf"^{CITRUS_ZEST_WORD_PATTERN}\s+and\s+juice\s+of\s+{CITRUS_AMOUNT_PATTERN}{CITRUS_WORD_PATTERN}$",
]


def normalize_citrus_zest_phrase(text: str) -> str:
    for pattern in CITRUS_JUICE_ZEST_PATTERNS:
        match = re.fullmatch(pattern, text)
        if match:
            citrus = match.group("citrus")
            return f"{citrus} juice and {citrus} zest"
    for pattern in CITRUS_ZEST_ONLY_PATTERNS:
        match = re.fullmatch(pattern, text)
        if match:
            return f"{match.group('citrus')} zest"
    return text

TRAILING_PREP_RE = re.compile(
    r"""
    (?:,\s*|\s+)
    (?:
        thawed\ and\ drained|
        softened\ to\ room\ temperature|
        at\ room\ temperature|
        (?:cold|chilled)\ and\ cut\ into\ [a-z0-9\s\".-]+|
        shelled\ and\ deveined|
        peeled\ and\ deveined|
        peeled\ and\ cored|
        (?:de)?seeded\ and\ (?:finely\ |coarsely\ |roughly\ |thinly\ )?(?:chopped|diced|sliced|minced|grated|shredded)|
        (?:de)?seeded\ and\ (?:chopped|diced|sliced|minced|grated|shredded)|
        cored\ and\ (?:finely\ |coarsely\ |roughly\ |thinly\ )?(?:chopped|diced|sliced|minced|grated|shredded)|
        pitted\ and\ (?:finely\ |coarsely\ |roughly\ |thinly\ )?(?:chopped|diced|sliced|minced|grated|shredded)|
        peeled\ and\ (?:finely\ |coarsely\ |roughly\ |thinly\ )?(?:chopped|diced|sliced|minced|grated|shredded|crushed|cored|deveined)|
        drained\ and\ (?:finely\ |coarsely\ |roughly\ )?(?:chopped|diced|sliced|minced|rinsed)|
        rinsed\ and\ drained|
        drained\ and\ rinsed|
        quartered\ and\ (?:finely\ |coarsely\ |roughly\ |thinly\ )?(?:chopped|diced|sliced|minced)|
        halved\ and\ (?:finely\ |coarsely\ |roughly\ |thinly\ )?(?:chopped|diced|sliced|minced)|
        cloves\ separated\ and\ peeled|
        cut\ up\ into\ pieces|
        diced\ after\ cooking|
        cooked\ and\ (?:finely\ |coarsely\ |roughly\ )?(?:chopped|diced|sliced|minced|cubed)|
        boiled\ and\ (?:finely\ |coarsely\ |roughly\ )?(?:chopped|diced|sliced|minced|cubed|mashed)|
        peeled\ and\ grated|
        peeled\ and\ cubed|
        peeled\ and\ chopped|
        peeled\ and\ diced|
        peeled\ and\ sliced|
        peeled\ and\ minced|
        finely\ chopped\ to\ yield\ [0-9/\s]+(?:cups?|c\.?|tablespoons?|tbsps?|teaspoons?|tsps?)|
        finely\ chopped|finely\ diced|finely\ sliced|finely\ minced|finely\ grated|
        coarsely\ chopped|coarsely\ diced|coarsely\ ground|
        roughly\ chopped|roughly\ diced|
        thinly\ sliced|sliced\ thinly|sliced\ thin|
        thickly\ sliced|
        very\ finely\ chopped|
        very\ thinly\ sliced|
        broken\ into\ [a-z\s-]+|
        torn\ into\ [a-z\s-]+|
        cut\ into\ [a-z\s-]+|
        sliced\ into\ [a-z\s-]+|
        diced\ after\ [a-z\s-]+|
        thawed|snipped|warmed|defrosted|scalded|
        chopped|diced|minced|beaten|softened|melted|drained|rinsed|peeled|
        crushed|ground|divided|sliced|cubed|grated|shredded|mashed|pressed|
        smashed|halved|quartered|finely|thinly|coarsely|lightly|well|
        seeded|deseeded|cored|pitted|husked|shelled|deveined|
        optional|to\ taste|as\ needed
    )
    \s*$
    """,
    re.IGNORECASE | re.VERBOSE,
)

LEADING_PREP_RE = re.compile(
    r"""
    ^(?:
        (?:cooked|mashed|boiled|steamed|peeled|chopped|diced|sliced|minced|grated|shredded|crushed|
        cubed|softened|melted|roasted|toasted|grilled|fried|broiled|baked|stewed|sauteed|sautéed|
        blanched|poached|braised|pan-fried|pan\ fried|stir-fried)
        (?:\ and\ (?:cooked|mashed|boiled|steamed|peeled|chopped|diced|sliced|minced|grated|shredded|crushed|cubed|softened|melted|roasted|toasted|cooled))?
        ,?\s+
    )+
    """,
    re.IGNORECASE | re.VERBOSE,
)

FIELDS = [
    "normalized_line",
    "recipe_count",
    "example_raw_line",
    "parsed_quantity",
    "parsed_unit",
    "parsed_food_phrase",
    "cleaned_surface",
    "normalized_base_food",
    "normalized_variant",
    "normalized_form",
    "normalized_state",
    "concept_base_food",
    "concept_variant",
    "concept_form",
    "concept_state",
    "dictionary_match_status",
    "dictionary_match_reason",
    "dictionary_base_food",
    "dictionary_variant",
    "dictionary_form",
    "dictionary_state",
    "dictionary_total_recipes",
    "dictionary_surface_count",
    "dictionary_example_surfaces",
    *APPROVED_RULE_FIELDS,
    *ROUTING_FIELDS,
    *SUPPLEMENTAL_FIELDS,
]


def canonicalize_source_spelling(surface: str) -> str:
    text = html.unescape((surface or "").strip().lower())
    text = text.replace("®", "").replace("™", "")
    text = text.replace("...", " ")
    for pattern, replacement in MECHANICAL_SOURCE_REPLACEMENTS:
        text = pattern.sub(replacement, text)
    return re.sub(r"\s+", " ", text).strip(" ,;.")


def surface_candidate_from_parsed_food(food_phrase: str) -> str:
    text = canonicalize_source_spelling(food_phrase)
    citrus = r"(lemon|lime|orange|grapefruit)s?"
    if re.match(rf"^whole {citrus},\s*zested$", text):
        return re.sub(rf"^whole {citrus},\s*zested$", r"\1 zest", text)
    if re.match(rf"^{citrus},\s*zested$", text):
        return re.sub(rf"^{citrus},\s*zested$", r"\1 zest", text)
    if re.match(rf"^{citrus},\s*(?:juiced|juice of)$", text):
        return re.sub(rf"^{citrus},\s*(?:juiced|juice of)$", r"\1 juice", text)
    if re.match(rf"^{citrus},\s*zested and juiced$", text):
        return re.sub(rf"^{citrus},\s*zested and juiced$", r"\1 juice and \1 zest", text)
    if re.match(rf"^{citrus},\s*juice and zest of$", text):
        return re.sub(rf"^{citrus},\s*juice and zest of$", r"\1 juice and \1 zest", text)
    if re.match(rf"^{citrus},\s*zest of$", text):
        return re.sub(rf"^{citrus},\s*zest of$", r"\1 zest", text)
    changed = True
    while changed and text:
        new_text = TRAILING_PREP_RE.sub("", text).strip(" ,.-")
        changed = new_text != text
        text = new_text
    return canonicalize_source_spelling(text)


def refine_surface(surface: str) -> str:
    text = canonicalize_source_spelling(surface)
    text = text.replace("⁄", "/")
    text = re.sub(r"^(?:7[- ]?up|seven[- ]up)$", "lemon lime soda", text)
    text = re.sub(r"^v[- ]?8(?:\s+vegetable)?\s+juice$", "vegetable juice", text)
    text = re.sub(r"^fleischmann's(?:\(r\))?\s+rapid\s*rise\s+yeast$", "rapidrise yeast", text)
    text = re.sub(r"^nabisco\s+100%\s+bran$", "100% bran", text)
    text = re.sub(
        r"^philadelphia\s+chive\s+&\s+onion\s+cream cheese\s+(?:spread|product)$",
        "chive onion cream cheese spread",
        text,
    )
    text = re.sub(
        r"^philadelphia\s+chive\s+&\s+onion\s+1/3 less fat than cream cheese(?: spread)?$",
        "light chive onion cream cheese spread",
        text,
    )
    text = re.sub(r"\s*\((?:optional,\s*)?if needed\)\s*$", "", text)
    text = re.sub(
        r"^inch(?:es)?\s+(?:piece\s+(?:of\s+)?)?(?:fresh\s+)?ginger(?:root|\s+root)?(?:\b.*)?$",
        "fresh ginger",
        text,
    )
    text = re.sub(r"^\(\d+[- ]?(?:inch|in\.?)\)\s+", "", text)
    text = re.sub(r"^to\s+\d+(?:[./]\d+)?\s+(?:cups?|c\.)\s+", "", text)
    text = re.sub(r",\s*dissolved\s+in\s+.*$", "", text)
    text = re.sub(r"\s*\(\d+°[^)]*\)\s*", " ", text).strip()
    text = re.sub(r"^\d+-(?:ounce|oz\.?)\s+(?:can|package|pkg|jar|bottle|box|bag|container)\s+", "", text)
    text = re.sub(r"^\(\d+(?:\.\d+)?\s*(?:oz|ounce|g|ml)\.?\)\s+", "", text)
    text = re.sub(r"^block\s+", "", text)
    text = re.sub(r"^of\s+water\b.*$", "water", text)
    # Handle "prep1, prep2 X" / "prep1 and prep2 X" → "X" (e.g. "cooked, mashed sweet potatoes")
    text = re.sub(
        r"^(?:peeled|chopped|diced|sliced|minced|grated|shredded|cubed|crushed|cooked|boiled|steamed|roasted|baked|grilled|sauteed|sautéed|mashed|softened|melted|drained|rinsed|thawed|uncooked|fresh|frozen)(?:\s*,\s*|\s+and\s+)(?:peeled|chopped|diced|sliced|minced|grated|shredded|cubed|crushed|cooked|boiled|steamed|roasted|baked|grilled|sauteed|sautéed|mashed|softened|melted|drained|rinsed|thawed|uncooked|fresh|frozen)\s+(.+)$",
        r"\1",
        text,
    )
    text = re.sub(
        r"\s+(?:whole foods|rite aid|safeway|king sooper's|king soopers|kroger|ralphs|vons|albertsons|publix|walmart|target)\b.*(?:\$|thru).*$",
        "",
        text,
    )
    text = re.sub(r"\s+\d+\s+ct\s+for\s+\$.*$", "", text)
    text = re.sub(r"\bnone\s+", "", text)
    text = re.sub(r"^%\S*\s+", "", text)
    text = re.sub(r"^(?:ounce|oz\.?)\s+cans?\s+", "", text)
    text = re.sub(r"^fluid\s+", "", text)
    text = re.sub(r",\s*with\s+juice$", "", text)
    text = re.sub(r",\s*crusts?\s+removed$", "", text)
    # Phase 2: strip trailing parser fragments from truncated recipe phrases
    text = re.sub(
        r",\s*(?:husks?|peels?|stems?|seeds?|pits?|ends?|skins?)\s+"
        r"(?:removed|discarded|trimmed)(?:\s+and)?\s*$",
        "",
        text,
    )
    text = re.sub(
        r",\s*(?:bottom|top)?\s*stems?\s+(?:discarded|removed|trimmed)(?:,\s*leaves\s+loosely\s+packed)?\s*$",
        "",
        text,
    )
    text = re.sub(
        r",\s*each\s+cut\s+into\s+\d+\s+(?:wedges|pieces|slices|chunks|halves|quarters)(?:\s+and)?\s*$",
        "",
        text,
    )
    text = re.sub(
        r",\s*sliced\s+into\s+\d+(?:/\d+)?\s*(?:-\s*\d+(?:/\d+)?)?\s*[-\s]?(?:inch|in\.?|cm|mm)(?:[-\s]thick)?\s*(?:slices|rounds|pieces)?\s*$",
        "",
        text,
    )
    text = re.sub(
        r",\s*(?:diced|chopped|cubed|torn|sliced)\s+into\s+[\d/-]+\s*[-\s]?(?:inch|in\.?|cm|mm)\s*(?:pieces|chunks|cubes)?\s*$",
        "",
        text,
    )
    text = re.sub(
        r",\s*pounded\s+to\s+[\d/-]+(?:\s*-\s*[\d/-]+)?\s+inch\s+thickness\s*$",
        "",
        text,
    )
    text = re.sub(
        r",\s*plus\s+(?:more|extra|additional)(?:\s+\w+){0,6}\s*$",
        "",
        text,
    )
    text = re.sub(r"\s+and\s+juiced\s*$", "", text)
    text = re.sub(r",\s*(?:washed|stemmed|cored|skinned|soaked|pitted|stoned|rind removed)(?:\s+in\s+[^,]+)?(?:\s+and)?\s*$", "", text)
    text = re.sub(r"\s+for\s+dredging\s*$", "", text)
    text = re.sub(r",\s*juice\s+reserved\s*$", "", text)
    text = re.sub(r",\s*(?:un[-\s]?drained|drained)\s+(?:with|and)\s+juice\s+reserved\s*$", "", text)
    text = re.sub(r"^\((?:\d+[- ]?layer size|\d+[- ]?layer)\)\s*", "", text)
    text = re.sub(r"\s+\((?:dry|regular size)\)$", "", text)
    text = re.sub(
        r"\s+about\s+\d+(?:[./]\d+)?\s*(?:oz\.?|ounces?|g|grams?|lb|lbs|pounds?)$",
        "",
        text,
    )
    text = re.sub(
        r"\s*\+\s*\d+(?:[./]\d+)?\s*(?:tbsp\.?|tbsps?|tablespoons?|tsp\.?|tsps?|teaspoons?|cups?|c\.?)$",
        "",
        text,
    )
    text = re.sub(
        r",\s*plus\s+\d+(?:[./]\d+)?\s*(?:tbsp\.?|tbsps?|tablespoons?|tsp\.?|tsps?|teaspoons?|cups?|c\.?)$",
        "",
        text,
    )
    text = re.sub(
        r"^(?:container|carton|package|pkg\.?|box|can|jar)\s*\([^)]*\)\s+",
        "",
        text,
    )
    text = re.sub(
        r"^\d+\s*(?:\([^)]+\)\s*)?(?:container|carton|package|pkg\.?|tub|box|jar|can|bottle|bowl|loaf|bar|pint|pt|quart|qt|pound|lb|ounce|oz)s?\s+",
        "",
        text,
    )
    text = re.sub(r"^of\s+water\b.*$", "water", text)
    text = re.sub(
        r"^\([^)]+\)\s*(?:container|carton|package|pkg\.?|tub|box|jar|can|bottle|bowl|loaf|bar)s?\s+",
        "",
        text,
    )
    text = re.sub(r"\s+or\s+possibly\s+\w+(?:\s+\w+)?$", "", text)
    text = re.sub(
        r"\s+or\s+(?:\d+(?:[./]\d+)?\s*(?:lb|lbs|pound|pounds|cup|cups|tbsp|tablespoons?|tsp|teaspoons?|oz|ounces?|g|grams?|ml|liters?|quarts?|qt)\.?\s+)?(?:ground turkey|ground chicken|ground pork|ground beef|chicken broth|beef broth|vegetable broth|chicken stock|beef stock|dry white wine|dry red wine|low-sodium broth|low sodium broth|low[- ]sodium (?:chicken|beef) (?:broth|stock))$",
        "",
        text,
    )
    text = re.sub(r",\s*(?:deseeded|seeded|cored|pitted)(?:\s+and\s+(?:finely\s+)?(?:chopped|diced|sliced|minced|grated))?$", "", text)
    text = re.sub(r"^assorted (?:crackers?|fresh fruit|fresh vegetables|vegetables|fruit)$", "", text)
    text = re.sub(r",\s*(?:deseeded|seeded)\s+and\s+finely\s+chopped$", "", text)
    text = re.sub(r",\s*finely\s+chopped$", "", text)
    text = re.sub(r",\s*roughly\s+chopped$", "", text)
    text = re.sub(r"^\d+\s+clove\s+garlic\s*\([^)]*\)$", "garlic clove", text)
    text = re.sub(r"\s*\((?:optional\s+)?or\s+(?:more\s+)?to\s+(?:taste|tast|tate)\)\s*", " ", text)
    text = re.sub(r"\s*\([\d/\s]*(?:cups?|c\.|tablespoons?|tbsps?|tbsp\.?|teaspoons?|tsps?|tsp\.?|ounces?|oz\.?|pounds?|lbs?\.?|sticks?|packets?|pkts?|cloves?|grams?|g\.?|inch(?:es)?)[\s.]*\)\s*", " ", text)
    text = re.sub(r"\s*\(do not drain\)\s*", "", text)
    text = re.sub(r"\s*\(undrained\)\s*", "", text)
    text = re.sub(r"\s*\(not\s+(?:evaporated|condensed)\s*(?:milk)?\)\s*", "", text)
    text = re.sub(r"\s*\(packed\)\s*", "", text)
    text = re.sub(r"\s*\(lightly packed\)\s*", "", text)
    text = re.sub(r",?\s+or\s+(?:more\s+)?to\s+(?:taste|tast|tate)$", "", text)
    text = re.sub(r",?\s+or\s+more$", "", text)
    text = re.sub(r",?\s+or$", "", text)
    text = re.sub(r"^juice of \d+(?:[./]\d+)? (?:(?:large|medium|small)\s+)?(lemon|lime|orange|grapefruit)s?$", r"\1 juice", text)
    text = re.sub(r"^2%\s+milk$", "reduced-fat milk", text)
    text = re.sub(r"^2%\s+low-fat milk$", "reduced-fat milk", text)
    text = re.sub(r"^2%\s+reduced-fat milk$", "reduced-fat milk", text)
    text = re.sub(r"^1%\s+milk$", "low-fat milk", text)
    text = re.sub(r"^%\s+reduced-fat milk$", "reduced-fat milk", text)
    text = re.sub(r"^%\s+low-fat milk$", "reduced-fat milk", text)
    text = re.sub(r"^1%\s+low-fat milk$", "low-fat milk", text)
    text = re.sub(r"^milk,\s*scalded$", "milk", text)
    text = re.sub(r"^(?:med|md)\.\s+", "medium ", text)
    text = re.sub(r"^(?:lg|lrg)\.\s+", "large ", text)
    text = re.sub(r"^(?:sm)\.\s+", "small ", text)
    text = re.sub(r"^(?:lg|lg\.|sm|sm\.)\s+(onions?)$", r"\1", text)
    text = re.sub(r"^(?:minced|chopped|crushed)\s+fresh\s+(garlic(?: cloves?)?)$", r"fresh \1", text)
    text = re.sub(r"^thinly\s+(sliced\s+.+)$", r"\1", text)
    text = re.sub(r"^thinly\s+(sliced\s+(?:green|red)\s+onions?)$", r"\1", text)
    text = re.sub(r"^(?:ice|iced|cold|cool|hot|warm|boiling|boiled|lukewarm)\s+water$", "water", text)
    text = re.sub(r"^water,\s*(?:ice|iced|cold|cool|hot|warm|boiling|boiled|lukewarm)$", "water", text)
    text = re.sub(r"^water\s+to\s+cover$", "water", text)
    text = re.sub(r"^(.+),\s*plus more(?:\s+(?:to taste|for brushing|for dusting|for drizzling|for serving))?$", r"\1", text)
    text = re.sub(r"^(.+),\s*plus$", r"\1", text)
    text = re.sub(
        r"^((?:all[- ]purpose flour|kosher salt|granulated sugar|powdered sugar)),\s*(?:plus (?:extra|more) for (?:dusting|seasoning|rolling)|for (?:dusting|rolling))$",
        r"\1",
        text,
    )
    text = re.sub(r"^diced tomatoes,?\s+with juice$", "tomatoes with juice", text)
    text = re.sub(r"^canned tomatoes$", "tomatoes with juice", text)
    text = re.sub(r"^flour\s+\(all[- ]purpose\)$", "all purpose flour", text)
    text = re.sub(r"^flour\s+\(self[- ]rising\)$", "self rising flour", text)
    text = re.sub(r"^\([^)]*(?:oz|ounce|ounces|g|gram|grams|ml|liter|liters|lb|lbs|pound|pounds|cup|cups|inch|inches|no\.|tsp|teaspoon|tbsp|tablespoon|tbs\.)[^)]*\)\s*", "", text)
    text = re.sub(
        r"^(?:pkg|pkg\.|pkgs|pkt|pkt\.|package|packages|packet|packets|envelope|envelopes|can|cans|box|boxes|bottle|bottles|container|containers|carton|jar|bundle|stalk|stalks|loaf|loaves|each|x|weight|head|soup can|gal|gal\.|gallon|gallons|qt|qt\.|qts|pt|pt\.|pts)\s+",
        "",
        text,
    )
    text = re.sub(
        r"^\([^)]*(?:stick|sticks|lb|pound|pounds|oz|ounce|ounces|g|gram|grams|ml|cup|cups|tsp|teaspoon|tbsp|tablespoon|tbs\.)[^)]*\)\s*",
        "",
        text,
    )
    text = re.sub(
        r"\s*\([^)]*(?:each|stick|sticks|lb|lbs|pound|pounds|oz|ounce|ounces|g|gram|grams|ml|milliliter|milliliters|liter|liters|cup|cups|inch|inches|tsp|teaspoon|tbsp|tablespoon|tbs\.)[^)]*\)\s*$",
        "",
        text,
    )
    text = re.sub(r"^(?:small|medium|large)\s+cans?\s+", "", text)
    text = re.sub(r"^(?:small|medium|large)\s+(?:pkg|pkg\.|package|packet|envelope|box|jar)\s+", "", text)
    text = re.sub(r"\s+(?:pkg|package|packet|envelope|box|jar)$", "", text)
    text = re.sub(r"\b\d+(?:[./]\d+)?-inch\s+", "", text)
    text = re.sub(r"^(?:beaten|slightly beaten|lightly beaten|well beaten|well-beaten)\s+", "", text)
    text = re.sub(r"\s*\(for (?:deep frying|frying|brushing|dusting|dredging|sprinkling)\)\s*", " ", text)
    text = re.sub(r"\s*\((?:optional|to taste|chopped|sliced|diced|minced|crushed|grated|shredded|peeled|beaten|pressed|mashed|smashed|halved|quartered|melted|softened|room temperature|at room temperature|finely chopped|finely diced|finely sliced|finely minced|finely grated|coarsely chopped|roughly chopped|thinly sliced|thickly sliced|cut into pieces|cut into strips|cut into chunks|deseeded|seeded|cored|pitted|drained|rinsed)\)\s*", " ", text).strip()
    text = re.sub(r"\s*\(whole egg\)\s*", " ", text)
    text = re.sub(r"^(eggs?|egg whites?|oil|water)\s+\(or as called for by your cake mix\)$", r"\1", text)
    text = re.sub(r",\s*(?:slightly|lightly|well|finely|thinly|coarsely)$", "", text)
    text = re.sub(r",\s*(?:cold|chilled)\s+and$", "", text)
    text = re.sub(r",\s*(?:trimmed|mixed|cleaned|rinsed|scalded|melted|hard[- ]boiled)\s+and$", "", text)
    text = re.sub(r",\s*each$", "", text)
    text = re.sub(r",\s*(?:roughly)$", "", text)
    text = re.sub(r",\s*(?:divided|optional|separated|undrained)$", "", text)
    text = re.sub(r",\s*for\s+brushing\s+grill$", "", text)
    text = re.sub(r"\s+separated$", "", text)
    text = re.sub(r",\s*juiced$", " juice", text)
    text = re.sub(r",\s*juice of$", " juice", text)
    text = re.sub(r"^(lemon|lime|orange|grapefruit),\s*zested$", r"\1 zest", text)
    text = re.sub(r",\s*(?:deseeded|seeded|cored|pitted|husked|shelled)\s+and\s+(?:finely\s+|coarsely\s+|roughly\s+|thinly\s+|thickly\s+)?(?:chopped|diced|sliced|minced|grated|shredded)$", "", text)
    text = re.sub(r",\s*(?:for garnish|to garnish|for topping|for serving|to serve|to dust|for brushing|for drizzling|for frying|for sauteing|for sautéing|for sauté(?:ing)?|for sprinkling(?:\s+on\s+top)?|for dusting(?:\s+pan)?|for dredging|for rolling|for cooking|for browning|for shaking(?:\s+and\s+chilling)?|for grilling|for coating|for spraying|for chilling|for pan|for (?:egg\s+)?wash|for sauté|for dotting|for dotting over top|for sealing(?:\s+(?:wrappers?|edges?))?|for rimming(?:\s+(?:the\s+)?(?:glass|rim))?|for greasing(?:\s+(?:pan|bowl))?|for molding|for flouring|for seasoning|for thickening|for boiling|for tossing|for baking|for decoration|for batter|for filling|for crust|for dredge)(?:\s*\(optional\))?\s*$", "", text)
    text = re.sub(r"^\([^)]+\)\s+", "", text).strip()
    # Strip leading dimensions, but do not eat meaningful product tokens like
    # 7-Up, 10x powdered sugar, 4% cottage cheese, or 90% lean ground beef.
    text = re.sub(r'^\d+(?:[./]\d+)?["\']\s*-?\s*(?:inch\s+)?', "", text).strip()
    text = re.sub(r"^\d+(?:[./]\d+)?\s*-?\s*inch\s+", "", text).strip()
    text = re.sub(r"^%\S*\s+", "", text)
    text = re.sub(r"^x\s+", "", text)
    text = re.sub(r"^(?:ounce|oz\.?)\s+cans?\s+", "", text)
    text = re.sub(r"^(?:envelope|envelopes|packet|packets|pkg|pkgs|pkg\.|pkgs\.|package|packages|box|boxes|jar|jars|can|cans|tub|tubs|bottle|bottles|bag|bags)\s+", "", text)
    text = re.sub(r",\s*baked$", "", text)
    text = re.sub(r",\s*unbaked$", "", text)
    text = re.sub(r"^unbaked\s+", "", text)
    text = re.sub(r"^baked\s+", "", text)
    text = re.sub(r"^frozen\s+(pie|pastry|crust|tart|puff|bread|dinner roll|dough)\b", r"\1", text)
    text = re.sub(r"^refrigerated\s+(pie|pastry|crust|dough|biscuit|crescent|cookie|puff)\b", r"\1", text)
    text = re.sub(r"^broiler[/-]?fryer\s+chicken$", "chicken", text)
    text = re.sub(r",\s*(?:rinsed,?\s*drained\s*and\s*chopped|rinsed\s*and\s*drained|drained\s*and\s*rinsed|broken\s+in\s+half|cut\s+up|cut\s+in\s+half|boneless,?\s*skinless|skinless,?\s*boneless|cooked\s+and\s+mashed|mashed\s+and\s+cooked|cooked\s+and\s+cooled|cooked\s+and\s+drained|peeled\s+and\s+grated|peeled\s+and\s+cubed|peeled\s+and\s+diced|peeled\s+and\s+chopped|peeled\s+and\s+sliced|peeled\s+and\s+minced)$", "", text)
    text = re.sub(r"^water[- ]packed\s+", "", text)
    text = re.sub(r"^oil[- ]packed\s+", "", text)
    text = re.sub(r"^syrup[- ]packed\s+", "", text)
    text = re.sub(r",\s*(?:cooked|boiled|steamed|roasted|baked|grilled|fried|sauteed|sautéed|blanched|poached|braised)\s+and$", "", text)
    text = re.sub(r",\s*(?:peeled|chopped|diced|sliced|minced|crushed|grated|shredded|cubed|softened|melted|drained)\s+and$", "", text)
    text = re.sub(r",\s*and$", "", text)
    text = re.sub(r"^(\w+)\s*\([^)]+\)$", r"\1", text)  # strip trailing "(medium)" parenthetical
    text = re.sub(r"\s*\(\s*(?:small|medium|large|size\s+of\s+\w+|\d+[-\s]?(?:inch|oz|ounce))\s*\)\s*$", "", text)
    text = re.sub(r"^\d+[- ]?inch\s+stick\s+cinnamon$", "cinnamon stick", text)
    text = re.sub(r"^\(\d+[- ]?inch\)\s+stick\s+cinnamon$", "cinnamon stick", text)
    text = re.sub(r"^stick\s+cinnamon$", "cinnamon stick", text)
    text = re.sub(r"^roasted\s+(garlic|tomato|pepper|bell pepper|red pepper|chicken|beef|pork)$", r"\1", text)
    text = re.sub(r"^lemon,\s*juice$", "lemon juice", text)
    text = re.sub(r"^(lemon|lime|orange|grapefruit),\s*juice$", r"\1 juice", text)
    text = re.sub(r"^(?:whole\s+)?garlic\s+bulb$", "garlic", text)
    text = re.sub(r"^head\s+(?:of\s+)?roasted\s+garlic$", "garlic", text)
    text = re.sub(r"^whole\s+egg,\s*room\s+temperature$", "egg", text)
    text = re.sub(r"^long[- ]grain\s+rice,\s*uncooked$", "long grain rice", text)
    text = re.sub(r"^canned\s+chicken\s+broth$", "chicken broth", text)
    text = re.sub(r"^canned\s+tomato\s+sauce$", "tomato sauce", text)
    text = re.sub(r"^canned\s+(.+?)$", r"\1", text)  # generic "canned X" → "X"
    text = re.sub(r"^vertically\s+sliced\s+(.+)$", r"\1", text)
    text = re.sub(r"^accompaniment:\s*", "", text)
    text = re.sub(r",\s*to\s+drizzle$", "", text)
    text = re.sub(r"^sprinkle\s+of\s+", "", text)
    text = re.sub(r",\s*julienned$", "", text)
    text = re.sub(r"^diced,\s*cooked\s+(ham|chicken|turkey|beef|pork)$", r"\1", text)
    text = re.sub(r"^grated\s+raw\s+(.+)$", r"\1", text)
    text = re.sub(r"^(.+)\s+grated$", r"\1", text)  # "parmesan cheese grated" → "parmesan cheese"
    text = re.sub(r"^(\d+\s+)?medium,?\s+chopped\s+(onion|onions)$", r"\2", text)
    text = re.sub(r"^\d+\s+loaves\s+frozen\s+bread$", "bread", text)
    text = re.sub(r"^boiling\s+salted\s+water$", "water", text)
    text = re.sub(r"^minced\s+dried\s+onion$", "dried onion flakes", text)
    text = re.sub(r",\s*cold$", "", text)
    text = re.sub(r",\s*preferably\s+.*$", "", text)
    text = re.sub(r",\s*(?:frozen|raw|packed|separated|seperated|unpeeled|cold|chilled|warm|hot|lukewarm|room temperature|room temp)$", "", text)
    text = re.sub(r",\s*(?:to cook|for cooking|to fry|for frying|for sauteing|for sautéing)$", "", text)
    text = re.sub(r",\s*(?:cooked|boiled|fried|steamed|baked|grilled|blanched|sauteed|sautéed)$", "", text)
    text = re.sub(r",\s*(?:strips?|rings?|cubes?|chunks?|wedges?|rounds?|small dice|large dice|medium dice)$", "", text)
    text = re.sub(r",\s*(?:sliced (?:in|into) (?:rings?|strips?|rounds?|wedges?))$", "", text)
    text = re.sub(r",\s*sliced\s+(?:in|into)$", "", text)
    text = re.sub(r",\s*(?:split (?:in half|lengthwise|crosswise))(?:\s+and\s+(?:seeded|scraped))?$", "", text)
    text = re.sub(r",\s*(?:well[- ]beaten|slightly beaten|lightly beaten)$", "", text)
    text = re.sub(r",\s*(?:sweetened condensed)$", "", text)
    text = re.sub(r",\s*(?:more|undiluted|uncooked|skinned|drained|boned|torn|segmented|cored|seeded)$", "", text)
    text = re.sub(r",\s*(?:cored,?\s*seeded|seeded,?\s*cored|cored and seeded|seeded and cored)$", "", text)
    text = re.sub(r",\s*(?:with skin|bone[- ]in|skin[- ]on)$", "", text)
    text = re.sub(r",\s*(?:lightly packed|firmly packed|loosely packed)$", "", text)
    text = re.sub(r",\s*separated into (?:florets?|pieces?)$", "", text)
    text = re.sub(r",\s*(?:for rubbing|for dusting(?:\s+the\s+pan)?|for oiling|for greasing|for coating)$", "", text)
    text = re.sub(r",\s*(?:plus more if needed|plus extra|or as needed)$", "", text)
    text = re.sub(r",\s*(?:zest only|juice only|rind only)$", "", text)
    text = re.sub(r",\s*(?:cloves?|large|small|medium)$", "", text)
    text = re.sub(r",\s*(?:leaves|leaf)$", "", text)
    text = re.sub(r",\s*(?:slivered|split|sliced|minced|diced small|diced|chopped)$", "", text)
    text = re.sub(r",\s*(?:to coat|to taste|to cover)$", "", text)
    text = re.sub(r",\s*(?:cooled|cooling|at room temp(?:erature)?)$", "", text)
    text = re.sub(r"\s+\[(?:minced|chopped|sliced|diced|pressed|crushed)\]$", "", text)
    text = re.sub(r"\s+-\s+(?:peeled,?\s*)?(?:pitted|seeded|cored|deveined)$", "", text)
    text = re.sub(r",\s*(?:sliced in half|halved|quartered|broken up|crumbled|butterflied|flaked)$", "", text)
    text = re.sub(r",\s*(?:sectioned|segmented)$", "", text)
    text = re.sub(r"\s*\(fresh is best\)$", "", text)
    text = re.sub(r"\s*\(not pumpkin pie (?:mix|filling)\)$", "", text)
    text = re.sub(r",\s*hard[- ]?(?:boil|cook)ed$", "", text)
    text = re.sub(r"^salted\s+water$", "water", text)
    text = re.sub(r"^whole\s+head\s+(?:of\s+)?garlic$", "garlic", text)
    text = re.sub(r"^garlic\s+bulb$", "garlic", text)
    text = re.sub(r"^cloves?\s+garlic,\s*unpeeled$", "garlic", text)
    text = re.sub(r"^water\s*\(to\s+cover\)$", "water", text)
    text = re.sub(r"^butter/margarine$", "butter", text)
    text = re.sub(r"^onion\s*\((?:small|medium|large)\)$", "onion", text)
    text = re.sub(r"^purple\s+onion$", "red onion", text)
    text = re.sub(r"^(?:pre)?chopped\s+onion$", "onion", text)
    text = re.sub(r"^vertically\s+sliced\s+onion$", "onion", text)
    text = re.sub(r"^slivered\s+red\s+onions?$", "red onion", text)
    text = re.sub(r"^chopped\s+roasted\s+red\s+peppers?$", "roasted red peppers", text)
    text = re.sub(r"^bunch\s+green\s+onions?$", "green onions", text)
    text = re.sub(r"^dry\s+onion\s+flakes?$", "dried onion flakes", text)
    text = re.sub(r"^skinless\s+chicken\s+breast\s+halves?$", "chicken breast", text)
    text = re.sub(r"^(?:\d+\s+)?bay\s+leaf$", "bay leaf", text)
    text = re.sub(r"^fried\s+onions?$", "french fried onions", text)
    text = re.sub(r"^chopped\s+raw\s+apples?$", "apples", text)
    text = re.sub(r"^fluid\s+simple\s+syrup$", "simple syrup", text)
    text = re.sub(r"^vanilla\s+bean,\s*scraped$", "vanilla bean", text)
    text = re.sub(r"^fresh\s+basil\s+leaves?$", "fresh basil", text)
    text = re.sub(r",\s*scraped$", "", text)
    text = re.sub(r",\s*for\s+juicing$", "", text)
    text = re.sub(r"^level\s+tsp\.?\s+", "", text)
    text = re.sub(r"^litre\s+", "", text)
    text = re.sub(r"^juice\s+(?:of|from)\s+\d+(?:\s+\d+)?(?:[./]\d+)?\s+(lemon|lime|orange|grapefruit)s?(?:\s*\([^)]*\))?$", r"\1 juice", text)
    if re.match(
        r"^(?:(?:finely|coarsely|roughly)\s+)?(?:chopped|diced|cubed|shredded)\s+(?:cooked|boiled)\s+chickens?$",
        text,
    ):
        return "cooked chicken"
    if re.match(r"^(?:cooked|boiled)\s+chickens?$", text):
        return "cooked chicken"
    if re.match(
        r"^(?:(?:finely|coarsely|roughly)\s+)?(?:chopped|diced|cubed|shredded)\s+(?:cooked|boiled)\s+chicken\s+breasts?$",
        text,
    ):
        return "cooked chicken breast"
    if re.match(r"^(?:cooked|boiled)\s+chicken\s+breasts?$", text):
        return "cooked chicken breast"
    if re.match(r"^(?:hot\s+)?(?:cooked|boiled|steamed)\s+(?:white\s+)?rice$", text):
        return "cooked rice"
    if re.match(r"^(?:hot\s+)?(?:cooked|boiled|steamed)\s+brown\s+rice$", text):
        return "cooked brown rice"
    text = re.sub(r"^(?:peeled|chopped|diced|sliced|minced|grated|shredded|cubed|crushed|cooked|boiled|steamed|roasted|baked|grilled|sauteed|sautéed|mashed)\s+and\s+(?:peeled|chopped|diced|sliced|minced|grated|shredded|cubed|crushed|cooked|boiled|steamed|roasted|baked|grilled|sauteed|sautéed|mashed)\s+", "", text)
    text = re.sub(r"^(?:peeled|chopped|diced|sliced|minced|grated|shredded|cubed|crushed|cooked|boiled|steamed|mashed|cooled|raw|organic|unsliced|seeded|caramelized|poached)\s+", "", text)
    text = re.sub(r"^(?:and\s+)?deveined\s+", "", text)
    text = re.sub(r"^pods?\s+(garlic|vanilla|cardamom)$", r"\1", text)
    text = re.sub(r"^(?:little|some|a little)\s+", "", text)
    text = re.sub(r"^(?:glass|glasses)\s+(water|milk|wine|juice)$", r"\1", text)
    text = re.sub(r"^(?:shakes?|dashes?)\s+(garlic salt|garlic powder|pepper|paprika|cayenne|cinnamon|nutmeg|onion powder)$", r"\1", text)
    text = re.sub(r"^c\.\s+", "", text)
    text = re.sub(r"^doz\.?\s+", "", text)
    text = re.sub(r"^cloves?\s+(?:of\s+)?garlic$", "garlic", text)
    text = re.sub(r"^sticks?\s+cinnamon$", "cinnamon stick", text)
    text = re.sub(r"^(?:medium[- ]?size|medium[- ]?sized|medium to large|large to medium)\s+", "medium ", text)
    text = re.sub(r"^bone[- ]in\s+(?!ham\b)", "", text)
    text = re.sub(r"^reserved\s+(?:pasta\s+)?water$", "water", text)
    text = re.sub(r"^(?:sheets?|rounds?)\s+(?:frozen\s+)?(?:phyllo|filo|puff\s+pastry)\s+(?:dough|pastry)$", "phyllo dough", text)
    text = re.sub(r"^(?:medium|small|large)\s+can\s+", "", text)
    text = re.sub(r"^(?:env|env\.|envs)\s+", "", text)
    text = re.sub(r"^(?:roughly|coarsely|finely)\s+(?:chopped|diced|minced|grated|shredded)\s+(?:fresh\s+)?", "", text)
    text = re.sub(r"^(?:tsp|tbsp|tablespoon|teaspoon)s?\s+", "", text)
    text = re.sub(r"^(?:small|large)\s+piece\s+(?:of\s+)?", "", text)
    text = re.sub(r"^garlic[- ]flavored\s+", "", text)
    text = re.sub(r"^(?:pre)?baked\s+(?:thin\s+)?(?:pizza\s+)?crust$", "pizza crust", text)
    text = re.sub(r"\*+$", "", text).strip()
    text = re.sub(r"^(?:\d+\s+)?broiler[/-]?fryer\s+chicken(?:\s*\([^)]*\))?(?:,?\s*cut\s+up)?$", "chicken", text)
    text = re.sub(r"^(\d+\s+)?small,?\s+chopped\s+onion$", "onion", text)
    text = re.sub(r",\s*(?:cooked\s+and\s+mashed|mashed\s+and\s+cooked)$", "", text)
    text = re.sub(r"\s*\(for\s+(?:pan|bowl|greasing|serving|topping|garnish|drizzling|brushing|dipping|coating|sealing(?:\s+[a-z\s]+)?|dotting|rolling|chilling|dredging|rimming(?:\s+[a-z\s]+)?|sauté(?:ing)?|sauteing)\)\s*$", " ", text).strip()
    text = re.sub(r"\s*\((?:about|from|preferably|such\s+as|or\s+more\s+to\s+taste|or\s+more)\s+[^)]*\)\s*", " ", text).strip()
    text = re.sub(r',\s*(?:cold|chilled)\s+and\s+cut\s+into\s+(?:small\s+|large\s+|\d+\s*(?:["”]|inches?|inch)\s+)?pieces?$', "", text)
    text = re.sub(r",\s*dissolved\s+in\s+[\d/\s]+(?:tablespoons?|tbsps?|teaspoons?|tsps?|cups?|c\.?)\s+water$", "", text)
    text = re.sub(r",\s*dissolved\s+in\s+(?:water|warm\s+water|cold\s+water|milk|a\s+little\s+water)$", "", text)
    text = re.sub(r"^assorted\s+(?!seasoning|beans|nuts)", "", text)
    text = re.sub(r"^(garlic\s+cloves?|garlic),\s*whole$", "garlic", text)
    text = re.sub(r"^(salt|pepper|black\s+pepper|sugar|brown\s+sugar|flour|salt\s+and\s+pepper),\s*\d+(?:[./]\d+)?\s*(?:teaspoons?|tsps?|tablespoons?|tbsps?|tbs\.?)$", r"\1", text)
    text = re.sub(r"^(salt|pepper|black\s+pepper|sugar|brown\s+sugar|flour|salt\s+and\s+pepper),\s*\d+⁄\d+\s*(?:teaspoons?|tsps?|tablespoons?|tbsps?)$", r"\1", text)
    text = re.sub(r",\s*bone[- ]in\s+or\s+boneless$", "", text)
    text = re.sub(r",\s*raw$", "", text)
    text = re.sub(r",\s*pounded\s+to\s+(?:even\s+)?thickness$", "", text)
    text = re.sub(r"^\d+\s*\(\s*\d+\.?\d*\s*(?:oz|ounce|gram|g)\s*(?:each)?\s*\)\s*", "", text)
    text = re.sub(r"^heads?\s+(garlic|cabbage|lettuce|romaine|iceberg|broccoli|cauliflower|celery)$", r"\1", text)
    text = re.sub(r"^leaves?\s+(cabbage|lettuce|romaine|basil|bay|mint|sage)$", r"\1", text)
    text = re.sub(r"^(?:small|medium|large)\s+bunch\s+", "", text)
    text = re.sub(r"^bunch\s+", "", text)
    text = re.sub(r"^virgin\s+(olive oil)$", r"\1", text)
    text = re.sub(r"^(lemon|lime|orange|grapefruit),\s*squeezed$", r"\1 juice", text)
    text = re.sub(r"\s+(?:for drizzling|for dipping|for brushing|for greasing|to drizzle)$", "", text)
    text = re.sub(r"\s*\(divided\)\s*$", "", text)
    text = re.sub(r",\s*roasted$", "", text)
    text = re.sub(r"^(?:juice of|juice from)\s+\d+(?:[./]\d+)?\s+(lemons?|limes?|oranges?|grapefruits?)(?:\s*\([^)]*\))?$", r"\1 juice", text)
    text = re.sub(r",\s*plus\s+(?:more|extra)(?:\s+for\s+[a-z\s]+)?$", "", text)
    text = re.sub(r",\s*(?:cut|thinly sliced|sliced thinly|sliced thin|sliced diagonally|very thinly sliced|halved|halved lengthwise|mashed|smashed|pressed|peeled|zested).*$", "", text)
    text = re.sub(r",\s*(?:chopped|diced|sliced|minced|grated)\s+(?:fine|finely)$", "", text)
    text = re.sub(r",\s*pounded(?:\s+(?:to\s+)?(?:thin(?:ness)?|[\d/]+(?:\s+inch(?:es)?)?(?:\s+thick(?:ness)?)?))?$", "", text)
    text = re.sub(r",\s*(?:thawed\s+and\s+drained|softened\s+to\s+room\s+temperature|broken\s+into\s+[a-z\s-]+|torn\s+into\s+[a-z\s-]+|at\s+room\s+temperature|thawed|snipped|drained|softened)$", "", text)
    text = re.sub(r"\s*\((?:such\s+as|if\s+needed|if\s+desired|or\s+more|or\s+to\s+taste)\s*[^)]*\)\s*$", "", text)
    text = re.sub(r"^(?:additional|extra)\s+", "", text)
    text = re.sub(r"\s+(?:pressed|peeled|zested|sifted|sliced thin|thinly sliced|sliced thinly|room temperature|at room temperature)$", "", text)
    text = re.sub(r",\s*(?:finely|coarsely|roughly)?\s*(?:chopped|diced|minced|grated)$", "", text)
    text = re.sub(r"^(?:whole|plump|large|medium|small|extra[- ]large)\s+(eggs?|egg whites?|egg yolks?|garlic cloves?)$", r"\1", text)
    text = re.sub(r"^(?:large|medium|small)\s+(tomato|tomatoes|apple|apples|onion|onions|potato|potatoes|carrot|carrots|lemon|lemons|lime|limes|orange|oranges|peach|peaches|pear|pears|avocado|avocados|cucumber|cucumbers|zucchini|zucchinis)$", r"\1", text)
    text = re.sub(r"^whole\s+(?:large|medium|small)\s+(eggs?|egg whites?|egg yolks?)$", r"\1", text)
    text = re.sub(r"^whole\s+(onions?)$", r"\1", text)
    text = re.sub(r"^(?:large|medium|small)?\s*sweet onions?$", "onion", text)
    text = re.sub(r"^(?:scallions?|spring onions?)$", "green onion", text)
    text = re.sub(r"^(?:whole|plump)\s+(garlic cloves?)\b", r"\1", text)
    text = re.sub(r"^(?:large|medium|small)\s+clove garlic$", "garlic clove", text)
    text = re.sub(r"^clove garlic$", "garlic clove", text)
    text = re.sub(r"^(?:hard[- ](?:boiled|cooked)|boiled) eggs?$", "egg", text)
    text = re.sub(r"^(?:unbeaten|slightly beaten|lightly beaten|well beaten|well-beaten|beaten|whisked)\s+(eggs?|egg whites?|egg yolks?)$", r"\1", text)
    text = re.sub(r"^stiffly\s+beaten\s+(egg whites?)$", r"\1", text)
    text = re.sub(
        r"^(eggs?|egg whites?|egg yolks?)\s*\((?:unbeaten|beaten|slightly beaten|lightly beaten|well beaten|whisked)\)$",
        r"\1",
        text,
    )
    text = re.sub(
        r"^(?:(?:large|medium|small|lrg)\s+)?(eggs?|egg whites?|egg yolks?),\s*(?:unbeaten|beaten|beaten slightly|slightly beaten|lightly beaten|well beaten|whisked|beaten to blend)(?:,?\s*for\s+(?:egg wash|brushing|glaze))?$",
        r"\1",
        text,
    )
    text = re.sub(r"^(?:skinless,\s*boneless|boneless,\s*skinless)\s+chicken breast halves$", "boneless skinless chicken breast halves", text)
    text = re.sub(r"^(?:skinless,\s*boneless|boneless,\s*skinless)\s+chicken breasts$", "boneless skinless chicken breasts", text)
    text = re.sub(r"^(?:dash|dashes|pinch)\s+(?:of\s+)?", "", text)
    text = re.sub(r"^pinches\s+(?:of\s+)?", "", text)
    text = re.sub(r"^(.+),\s*(?:a\s+)?pinch$", r"\1", text)
    text = re.sub(r"^(.+),\s*\d+\s+pinch$", r"\1", text)
    text = re.sub(r"^(salt|black pepper),\s*a\s+dash$", r"\1", text)
    text = re.sub(r",\s*about\s+.*$", "", text)
    text = re.sub(r"^\(or more\)\s+", "", text)
    text = re.sub(r"\s*\([^)]*(?:tsp|teaspoon|tbsp|tablespoon|tbs\.)[^)]*\)\s*$", "", text)
    text = re.sub(r"^(?:minced|chopped|crushed)\s+fresh\s+(garlic(?: cloves?)?)$", r"fresh \1", text)
    text = re.sub(r"^(?:whole\s+)?(?:large|medium|small)?\s*cloves?\s+garlic(?:\s*,?\s*(?:minced|pressed|crushed).*)?$", "garlic", text)
    text = re.sub(r"^garlic\s+cloves?\s*,?\s*(?:minced|pressed|crushed).*$", "garlic", text)
    text = re.sub(r"^garlic\s+cloves?\s*,?\s*(?:unpeeled|roughly)$", "garlic", text)
    text = re.sub(r"^garlic,\s*separated into cloves(?:\s+and)?$", "garlic", text)
    text = re.sub(r"^(vanilla bean),\s*seeds scraped out$", r"\1", text)
    text = re.sub(r"^(.+),\s*flesh scooped out$", r"\1", text)
    text = re.sub(r"^(english muffin),\s*split,?\s*toasted$", r"\1", text)
    text = re.sub(r"^garlic\s*,?\s*(?:minced|pressed|crushed).*$", "garlic", text)
    text = re.sub(r"^garlic\s*,?\s*roughly$", "garlic", text)
    text = re.sub(r"^garlic\s+(?:minced|pressed|crushed).*$", "garlic", text)
    text = re.sub(r"^gloves?\s+garlic(?:\s*,?\s*minced)?$", "garlic", text)
    text = re.sub(r"^lukewarm water$", "water", text)
    text = re.sub(r"^(?:cold|warm|hot)\s+2%\s+milk$", "reduced-fat milk", text)
    text = re.sub(r"^2%\s+cheddar cheese$", "reduced-fat cheddar cheese", text)
    text = re.sub(r"^frozen whipped topping,?\s*thawed$", "whipped topping", text)
    text = re.sub(r"^frozen chopped spinach,\s*thawed,?\s*squeezed dry$", "frozen chopped spinach", text)
    text = re.sub(r"^cream of (mushroom|chicken) soup,?\s*undiluted$", r"cream of \1 soup", text)
    text = re.sub(r"^cream of (mushroom|chicken) soup\s+\(undiluted\)$", r"cream of \1 soup", text)
    text = re.sub(r"^tomato soup,?\s*undiluted$", "tomato soup", text)
    text = re.sub(r"^tomato soup\s+\(undiluted\)$", "tomato soup", text)
    text = re.sub(r"^butter,\s*(?:cold|melted|unsalted)$", "butter", text)
    text = re.sub(r"^butter,\s*melted and cooled$", "butter", text)
    text = re.sub(r"^unsalted butter,\s*melted and cooled$", "unsalted butter", text)
    text = re.sub(r"^butter\s+\((?:cold|melted|unsalted)\)$", "butter", text)
    text = re.sub(r"^butter\s+\(\d+\s+sticks?\)$", "butter", text)
    text = re.sub(r"^melted butter\s+\(\d+\s+sticks?\)$", "butter", text)
    text = re.sub(r"^unsalted butter\s+\(\d+\s+sticks?\)$", "unsalted butter", text)
    text = re.sub(r"^unsalted butter,\s*cold$", "butter", text)
    text = re.sub(r"^olive oil,\s*extra[- ]virgin$", "extra virgin olive oil", text)
    text = re.sub(r"^hot(?:\s+pepper)?\s+sauce(?:,?\s*(?:such as|preferably)\s+tabasco|\s*\(such as tabasco\)|\s*\(tabasco\))$", "hot sauce", text)
    text = re.sub(r"^tabasco sauce,\s*to taste\s*\(about \d+ drops\)$", "tabasco sauce", text)
    text = re.sub(r"^worcestershire sauce(?:,?\s*eyeball it|\s*\(eyeball it\))$", "worcestershire sauce", text)
    text = re.sub(r"^flour\s+\(plain\)$", "flour", text)
    text = re.sub(r"^brown sugar\s+\(packed\)$", "brown sugar", text)
    text = re.sub(r"^\(packed\)\s+golden brown sugar$", "golden brown sugar", text)
    text = re.sub(r"^egg whites?,\s*beaten stiff$", "egg white", text)
    text = re.sub(r"^(egg whites?),\s*beaten\s+(?:until stiff|stiffly|to stiff peaks)$", r"\1", text)
    text = re.sub(r"^egg white,\s*stiffly$", "egg white", text)
    text = re.sub(r"^raw eggs?$", "egg", text)
    text = re.sub(r"^large whole eggs?$", "egg", text)
    text = re.sub(r"^eggs?,\s*large$", "egg", text)
    text = re.sub(r"^eggs?,\s*(?:lightly\s+)?whisked$", "egg", text)
    text = re.sub(r"^eggs?,\s*beaten with$", "egg", text)
    text = re.sub(r"^lrg large eggs?$", "eggs", text)
    text = re.sub(r"^lrg eggs?$", "eggs", text)
    text = re.sub(r"^(?:large|medium|small)\s+eggs?$", "eggs", text)
    text = re.sub(r"^parmesan,\s*parmigiano[- ]reggiano cheese$", "parmesan cheese", text)
    text = re.sub(r"^whole chicken breasts?$", "chicken breast", text)
    text = re.sub(r"^chicken breasts$", "chicken breast", text)
    text = re.sub(r"^chicken breasts?\s*\(boneless and skinless\)$", "chicken breast", text)
    text = re.sub(r"^chicken breast halves$", "chicken breast", text)
    text = re.sub(r"^chicken breast fillets?$", "chicken breast", text)
    text = re.sub(r"^(?:skinless\s+boneless|skinned,\s*boned|boneless\s+skinless)\s+chicken breast halves$", "chicken breast", text)
    text = re.sub(r"^(?:skinless\s+boneless|boneless\s+skinless)\s+chicken breasts?$", "chicken breast", text)
    text = re.sub(r"^boneless skinless chicken breasts?,\s*pounded to thickness$", "chicken breast", text)
    text = re.sub(r"^boneless skinless chicken breasts?,\s*each about \d+(?:[./]\d+)? oz$", "chicken breast", text)
    text = re.sub(r"^boneless skinless chicken breast(?:s| halves),\s*each$", "chicken breast", text)
    text = re.sub(r"^chopped walnuts?,\s*toasted$", "toasted walnuts", text)
    text = re.sub(r"^frozen strawberries,\s*thawed$", "frozen strawberries", text)
    text = re.sub(r"^rice,\s*uncooked$", "rice", text)
    text = re.sub(r"^rice\s+\(uncooked\)$", "rice", text)
    text = re.sub(r"^ground beef,\s*browned$", "ground beef", text)
    text = re.sub(r"^frozen chopped spinach,\s*thawed$", "frozen chopped spinach", text)
    text = re.sub(r"^cubed potatoes$", "potatoes", text)
    text = re.sub(r"^purple onion$", "red onion", text)
    text = re.sub(r"^vidalia onion$", "onion", text)
    text = re.sub(r"^instant minced onion$", "dried onion flakes", text)
    text = re.sub(r"^onion pwdr$", "onion powder", text)
    text = re.sub(r"^(?:diced|chopped),\s*cooked chicken$", "cooked chicken", text)
    text = re.sub(r"^(?:cubed|chopped),?\s*cooked chicken$", "cooked chicken", text)
    text = re.sub(r"^cubed cooked ham$", "ham", text)
    text = re.sub(r"^bacon,\s*crumbled$", "bacon", text)
    text = re.sub(r"^bay (?:leaf|leaves),\s*crumbled$", "bay leaf", text)
    text = re.sub(r"^leaf bay leaf$", "bay leaf", text)
    text = re.sub(r"^dried bay leaves?$", "bay leaf", text)
    text = re.sub(r"^carrot,\s*julienned$", "carrot", text)
    text = re.sub(r"^bulb of garlic$", "garlic", text)
    text = re.sub(r"^bulb garlic$", "garlic", text)
    text = re.sub(r"^(?:finely|coarsely|roughly)\s+chopped fresh garlic$", "garlic", text)
    text = re.sub(r"^minced clove garlic$", "garlic", text)
    text = re.sub(r"^leaves fresh basil$", "fresh basil", text)
    text = re.sub(r"^milk,\s*warmed$", "milk", text)
    text = re.sub(r"^milk,\s*scalded and cooled$", "milk", text)
    text = re.sub(r"^hard[- ]boiled large eggs?$", "eggs", text)
    text = re.sub(r"^walnuts,\s*toasted$", "toasted walnuts", text)
    text = re.sub(r"^onion,\s*roughly$", "onion", text)
    text = re.sub(r"^medium size onion$", "onion", text)
    text = re.sub(r"^butter,\s*for greasing pan$", "butter", text)
    text = re.sub(r"^butter,\s*(?:soft|cold and cut into small pieces)$", "butter", text)
    text = re.sub(r"^unsalted butter,\s*cold and cut into small pieces$", "unsalted butter", text)
    text = re.sub(r"^unsalted butter,\s*melted and cooled slightly$", "unsalted butter", text)
    text = re.sub(r"^frozen chopped spinach,\s*thawed and squeezed dry$", "frozen chopped spinach", text)
    text = re.sub(r"^frozen spinach,\s*thawed and$", "frozen spinach", text)
    text = re.sub(r"^frozen chopped broccoli,\s*thawed(?: and)?$", "frozen chopped broccoli", text)
    text = re.sub(r"^strawberries,\s*hulled and$", "strawberries", text)
    text = re.sub(r"^(?:fresh\s+)?strawberries,\s*hulled(?: and)?$", "strawberries", text)
    text = re.sub(r"^(?:(?:small|medium|large)\s+)?(?:tomato|tomatoes),\s*seeded and$", "tomato", text)
    text = re.sub(r"^chickpeas,\s*rinsed and$", "chickpeas", text)
    text = re.sub(r"^kidney beans?,\s*drained and(?:\s+(?:rinsed|chopped|sliced))?$", "kidney beans", text)
    text = re.sub(r"^water chestnuts?,\s*drained and(?:\s+(?:rinsed|chopped|sliced))?$", "water chestnuts", text)
    text = re.sub(r"^mushroom stems and pieces(?:,\s*drained)?$", "mushrooms", text)
    text = re.sub(r"^plus\s+\d+(?:[./]\d+)?\s+(?:cups?|c\.?|tablespoons?|tbsp\.?|tbs\.?|teaspoons?|tsp\.?)\s+sugar$", "sugar", text)
    text = re.sub(r"^plus\s+\d+(?:[./]\d+)?\s+(?:cups?|c\.?|tablespoons?|tbsp\.?|tbs\.?|teaspoons?|tsp\.?)\s+(.+)$", r"\1", text)
    text = re.sub(r"^lemon,\s*zest of$", "lemon zest", text)
    text = re.sub(r"^zest of \d+(?:[./]\d+)?\s+(lemon|lime|orange|grapefruit)s?,\s*finely$", r"\1 zest", text)
    text = re.sub(r"^(?:grated\s+|large\s+|small\s+)?lemon,\s*zest of(?:,\s*only)?$", "lemon zest", text)
    text = re.sub(r"^(lemon|lime|orange|grapefruit),\s*(?:rind|peel)$", r"\1 zest", text)
    text = re.sub(r"^(lemon|lime|orange|grapefruit),\s*zest(?: only)?$", r"\1 zest", text)
    text = re.sub(r"^(lemon|lime|orange|grapefruit),\s*juice only$", r"\1 juice", text)
    text = re.sub(r"^(lemon|lime|orange|grapefruit),\s*juice of,?\s*only$", r"\1 juice", text)
    text = re.sub(r"^whole\s+(lemons?|limes?|oranges?|grapefruits?)\s+juice$", lambda match: f"{match.group(1).rstrip('s')} juice", text)
    text = re.sub(r"^juice of \d+(?:[./]\d+)?\s+a\s+(lemon|lime|orange|grapefruit)$", r"\1 juice", text)
    text = re.sub(r"^zest from \d+(?:[./]\d+)?\s+(lemon|lime|orange|grapefruit)$", r"\1 zest", text)
    text = re.sub(
        r"^(?:whole\s+)?(?P<citrus>lemons?|limes?|oranges?|grapefruits?),\s*juiced and$",
        lambda match: f"{match.group('citrus').rstrip('s')} juice and {match.group('citrus').rstrip('s')} zest",
        text,
    )
    text = re.sub(r"^toothpicks?,\s*for securing$", "toothpicks", text)
    text = re.sub(r"^uncooked\s+(?:small|medium|large)?\s*shrimp$", "raw shrimp", text)
    text = re.sub(r"^(?:(?:small|medium|large|jumbo)\s+)?shrimp,\s*(?:shelled|peeled)\s+and\s+deveined$", "shrimp", text)
    text = re.sub(r"^cubed ham$", "ham", text)
    text = re.sub(r"^garlic\s+peeled and$", "garlic", text)
    text = re.sub(r"^heads?\s+garlic$", "garlic", text)
    text = re.sub(r"^eggs,\s*unbeaten$", "eggs", text)
    text = re.sub(r"^(oregano|thyme|basil)\s+dried$", r"\1", text)
    text = re.sub(r"^(oregano|thyme|basil),\s*dried$", r"\1", text)
    text = re.sub(r"^10x sugar$", "powdered sugar", text)
    text = re.sub(r"^10x confectioners sugar$", "powdered sugar", text)
    text = re.sub(r"^fluid sweetened,\s*condensed milk$", "sweetened condensed milk", text)
    text = re.sub(r"^7[- ]?up$", "lemon lime soda", text)
    text = re.sub(r"^to taste (salt|pepper|black pepper|white pepper)$", r"\1", text)
    text = re.sub(r"^(salt|pepper|black pepper|white pepper),\s*to taste\s*\(for [^)]+\)$", r"\1", text)
    text = re.sub(r"^fluid ounces?\s+", "", text)
    text = normalize_citrus_zest_phrase(text)
    text = re.sub(r"^extra[- ]virgin olive oil,\s*\d+\s+turns? of the pan$", "extra virgin olive oil", text)
    for plural_nut, singular_nut in (("pecans", "pecan"), ("walnuts", "walnut"), ("almonds", "almond")):
        if re.fullmatch(rf"(?:(?:finely|coarsely)\s+)?(?:(?:chopped|sliced)\s+)?{plural_nut},\s*(?:chopped\s+and\s+)?(?:lightly\s+)?toasted(?:\s+and)?", text):
            text = f"toasted {singular_nut}"
            break
    text = re.sub(r"^(sesame seeds?|flaked coconut),\s*toasted(?:\s+and)?$", r"\1", text)
    text = re.sub(
        r"^(?:(?:large|medium|small)\s+)?((?:tomato|tomatoes)|apples?|carrots?|red bell peppers?|green bell peppers?|bell peppers?|green peppers?|red peppers?|green beans?),\s*(?:seeded|cored|julienned|hulled|trimmed|peeled)(?:\s+and)?$",
        r"\1",
        text,
    )
    text = re.sub(
        r"^(?:fresh\s+)?(asparagus|cucumbers?|jalapeno peppers?|green beans?),\s*(?:trimmed|seeded)(?:\s+and(?:\s+cut\s+into\s+pieces)?)?$",
        r"\1",
        text,
    )
    text = re.sub(r"^(green beans?|asparagus),\s*trimmed and cut into pieces$", r"\1", text)
    text = re.sub(r"^frozen,\s*chopped\s+(broccoli|spinach)$", r"frozen chopped \1", text)
    text = re.sub(r"^(frozen\s+(?:chopped\s+)?(?:broccoli|spinach|whole kernel corn)),\s*thawed(?:\s+and\s+squeezed dry)?$", r"\1", text)
    text = re.sub(r"^whipped topping,\s*thawed$", "whipped topping", text)
    text = re.sub(r"^heavy cream,\s*chilled$", "heavy cream", text)
    text = re.sub(r"^(?:canned\s+)?((?:black|red kidney|kidney|garbanzo)\s+beans?),\s*rinsed and(?:\s+drained)?$", r"\1", text)
    text = re.sub(r"^(chickpeas),\s*rinsed and(?:\s+drained)?$", r"\1", text)
    text = re.sub(
        r"^(?:(?:light|white)\s+)?water[- ]packed tuna,\s*drained and flaked$",
        "tuna in water",
        text,
    )
    if "water" in text:
        text = re.sub(r"\s*\([^)]*(?:°|degrees?|~|f/|c/|[-]\d|\bto\s+\d)[^)]*\)\s*", " ", text)
        text = re.sub(
            r"^(?:very\s+)?(?:ice[- ]cold|ice|iced|cold|cool|hot|warm|boiling|boiled|luke warm|lukewarm|tepid)\s+water$",
            "water",
            text,
        )
        text = re.sub(r"^(?:filtered|drinking|tap|bottled|distilled|purified)\s+water$", "water", text)
        text = re.sub(r"^(?:hot|cold|warm)\s+tap\s+water$", "water", text)
        text = re.sub(
            r"^water,\s*(?:very\s+)?(?:ice[- ]cold|ice|iced|cold|cool|hot|warm|boiling|boiled|luke warm|lukewarm|tepid)$",
            "water",
            text,
        )
        text = re.sub(
            r"^water\s+(?:very\s+)?(?:ice[- ]cold|ice|iced|cold|cool|hot|warm|boiling|boiled|luke warm|lukewarm|tepid)$",
            "water",
            text,
        )
        text = re.sub(r"^soup cans?\s+water$", "water", text)
        text = re.sub(r"^water,\s*(?:as\s+needed|if\s+needed|for\s+(?:boiling|cooking|soaking|egg wash|slurry))$", "water", text)
        text = re.sub(r"^water,\s*(?:enough\s+)?to\s+(?:cover|mix|knead)$", "water", text)
        text = re.sub(
            r"^(?:very\s+)?(?:ice[- ]cold|ice|iced|cold|cool|hot|warm|boiling|boiled|luke warm|lukewarm|tepid)\s+water\s+(?:enough\s+)?to\s+(?:cover|mix|knead)$",
            "water",
            text,
        )

    text = re.sub(r"^(?:petite\s+)?(?:canned\s+)?diced tomatoes,?\s+with juices?$", "tomatoes with juice", text)
    text = re.sub(r"^can tomatoes$", "tomatoes with juice", text)
    text = re.sub(r"^whole canned tomatoes(?:,?\s+with juices?)?$", "tomatoes with juice", text)
    text = re.sub(r"^crushed canned tomatoes$", "crushed tomatoes", text)
    text = re.sub(r"^(?:whole\s+)?(?:small|medium|large|med|lrg)\s+onions?$", "onion", text)
    text = re.sub(r"^big\s+onions?$", "onion", text)
    text = re.sub(r"^(?:large|medium|small)\s+spanish onion$", "onion", text)
    text = re.sub(r"^brown onion$", "onion", text)
    text = re.sub(r"^onions?\s+(?:small|medium|large|med|lrg)$", "onion", text)
    text = re.sub(r"^(?:whole\s+)?(?:small|medium|large|med|lrg)\s+(red|yellow|white)\s+onions?$", r"\1 onion", text)
    text = re.sub(r"^(?:whole\s+)?(?:small|medium|large|med|lrg)\s+green\s+onions?$", "green onion", text)
    text = re.sub(r"^whole\s+(red|yellow|white)\s+onions?$", r"\1 onion", text)
    text = re.sub(r"^whole\s+green\s+onions?$", "green onion", text)
    text = re.sub(
        r"^(?:(?:finely|thinly|roughly|coarsely)\s+)?(chopped|diced|minced|sliced)\s+(?:large\s+|medium\s+|small\s+|whole\s+|yellow\s+)?sweet onions?$",
        r"\1 onion",
        text,
    )
    text = re.sub(
        r"^(?:large|medium|small)\s+(?:(?:finely|thinly|roughly|coarsely)\s+)?(chopped|diced|minced|grated|sliced)\s+(.+)$",
        r"\1 \2",
        text,
    )
    text = re.sub(r"^(?:whole\s+)?(?:(?:large|medium|small)\s+)?(?:yellow|vidalia|medium[- ]size)?\s*sweet onions?$", "onion", text)
    text = re.sub(r"^sweet onion\s+(?:large|medium|small)$", "onion", text)
    text = re.sub(
        r"^(?:large|medium|small)\s+sweet onion,\s*(?:quartered and|sliced and separated into rings|sliced into rings)$",
        "onion",
        text,
    )
    text = re.sub(r"^sweet onion,\s*diced small$", "onion", text)
    text = re.sub(
        r"^(?:(?:finely|thinly|roughly|coarsely)\s+)?(chopped|diced|minced|sliced)\s+scallion(?:s| greens?)?$",
        r"\1 green onion",
        text,
    )
    text = re.sub(
        r"^(?:(?:finely|thinly|roughly|coarsely)\s+)?(chopped|diced|minced|sliced)\s+spring onions?$",
        r"\1 green onion",
        text,
    )
    text = re.sub(r"^scallions?,\s*spring or green onions?$", "green onion", text)
    text = re.sub(r"^green onions?\s+or\s+scallions?$", "green onion", text)
    text = re.sub(r"^scallions?\s+or\s+green onions?$", "green onion", text)
    text = re.sub(r"^(?:scallions?|spring onions?),\s*trimmed(?:\s+and)?$", "green onion", text)
    text = re.sub(r"^scallions?,\s*(?:roughly|including green tops)$", "green onion", text)
    text = re.sub(
        r"^scallions?,\s*(?:both\s+)?(?:white\s+and\s+green|white\s+and\s+light\s+green|green)\s+parts(?:\s+only)?$",
        "green onion",
        text,
    )
    text = re.sub(r"^(?:whole\s+|bunch(?:es)?\s+|trimmed\s+|large\s+|medium\s+|small\s+)?scallion(?:s| stalks?| greens?)?$", "green onion", text)
    text = re.sub(r"^(?:whole\s+|bunch(?:es)?\s+|trimmed\s+|large\s+|medium\s+|small\s+)?spring onions?$", "green onion", text)
    text = re.sub(r"^onions?,\s*sliced into rings$", "onion", text)
    text = re.sub(r"^(?:large|medium|small)\s+onions?,\s*sliced into rings$", "onion", text)
    text = re.sub(r"^onion peeled and$", "onion", text)
    text = re.sub(r"^medium onion,\s*chopped(?:\s*\([^)]*\))?$", "onion", text)
    text = re.sub(r"^(?:recipe\s+)?pastry for (?:a\s+)?\d+\s+inch (?:single|double) crust pie$", "pie crust", text)
    text = re.sub(r"^pastry for (?:\d+[- ]?)?crust pie$", "pie crust", text)
    text = re.sub(r"^pastry for pie$", "pie crust", text)
    text = re.sub(r"^pie crusts?,\s*(?:baked|unbaked)$", "pie crust", text)
    text = re.sub(r"^pie shell\s*\((?:unbaked|baked)\)$", "pie crust", text)
    text = re.sub(r"^pie shell\s+\d+[- ]?inch$", "pie crust", text)
    text = re.sub(r"^unbaked\s+\(\d+[- ]inch\)\s+pie shell$", "pie crust", text)
    text = re.sub(r"^(?:skinned and boned|boned and skinned) chicken breasts?(?: halves)?$", "chicken breast", text)
    text = re.sub(r"^(?:red\s+)?onions?,\s*separated into rings$", "red onion", text)
    text = re.sub(r"^red onion,\s*separated into rings$", "red onion", text)
    text = re.sub(r"^vanilla bean,\s*split(?: lengthwise)?(?: and|,)?\s*(?:seeds scraped(?: out)?|seeded)(?: and reserved)?$", "vanilla bean", text)
    text = re.sub(r"^pork chops?,\s*(?:about\s*)?\d+(?:[./]\d+)?\s*inch(?:es)? thick(?:,.*)?$", "pork chop", text)
    text = re.sub(r"^taco seasoning,\s*\d+(?:[./]\d+)?\s*ounces?(?: packet)?$", "taco seasoning", text)
    text = re.sub(r"\s+with tops$", "", text)
    text = re.sub(
        r"^(?:(?:large|medium|small|whole|none)\s+)?(lemons|limes|oranges|grapefruits)\s+(juice|zest)$",
        lambda match: f"{match.group(1).rstrip('s')} {match.group(2)}",
        text,
    )
    # Broad trailing compound prep strips — ", X and Y into Z" patterns
    text = re.sub(r",\s*(?:chilled|cold|frozen)\s+and\s+(?:cut|diced|chopped|sliced|cubed)\s+into\s+[a-z][a-z /'-]+$", "", text)
    text = re.sub(r",\s*(?:washed|cleaned|rinsed|trimmed|drained)(?:,?\s*(?:and\s+)?(?:trimmed|sliced|chopped|diced|dried|patted dry|squeezed dry)(?:,?\s*and\s+[a-z]+(?:\s+[a-z]+)*)?)?$", "", text)
    text = re.sub(r",\s*(?:melted|cooled)\s+(?:and\s+cooled|slightly|and\s+cooled\s+slightly)$", "", text)
    text = re.sub(r",\s*(?:ends?\s+)?(?:trimmed|washed)\s+and\s+(?:cut|sliced|chopped|diced)\s+into\s+[a-z][a-z /'-]+$", "", text)
    # ", seeded and cut into X" / ", cored and sliced into X"
    text = re.sub(r",\s*(?:seeded|cored|pitted|peeled|stemmed)\s+and\s+(?:cut|sliced|chopped|diced)\s+into\s+[a-z0-9][a-z0-9 /'-]+$", "", text)
    # ", sliced X inch thick" / ", cut into X-inch pieces"
    text = re.sub(r",\s*(?:sliced|cut)\s+\d+[/.]?\d*\s*(?:inch|cm|mm)\s+(?:thick|pieces?)$", "", text)
    # ", pureed or blended" / ", mashed or pureed"
    text = re.sub(r",\s*(?:pureed|mashed|blended)\s+or\s+(?:pureed|mashed|blended)$", "", text)
    # ", 1% lowfat" / ", 2% reduced-fat" — trailing fat spec on milk
    text = re.sub(r",\s*\d+%\s*(?:low[- ]?fat|reduced[- ]?fat|fat[- ]?free|nonfat)$", "", text)
    # ", each about X ounces" / ", each X oz"
    text = re.sub(r",\s*each\s+(?:about\s+)?\d+(?:[./]\d+)?\s*(?:ounces?|oz\.?|lbs?\.?|pounds?|grams?|g)$", "", text)
    # Broad trailing context strips — recipe instructions, not food identifiers
    # ", for [any purpose]" — catches greasing, sauce, glaze, syrup, filling, etc.
    text = re.sub(r",\s*for\s+[a-z][a-z /'-]+$", "", text)
    # ", chopped/sliced/cubed/cut into [detail]"
    text = re.sub(r",\s*(?:chopped|sliced|cubed|cut|diced)\s+into\s+[a-z][a-z /'-]+$", "", text)
    text = re.sub(r",\s*(?:sliced|cut)\s+into\s+\d+(?:[./]\d+)?[- ]?(?:inch|inches|cm|mm)(?:[- ](?:rounds?|slices?|pieces?|strips?|wedges?|chunks?))?$", "", text)
    # ", with liquid/juices" (canned goods trailing context)
    text = re.sub(r",\s*with\s+(?:liquid|juices|liquor)s?$", "", text)
    # ", drained (reserve juice/liquid)" or ", drained (reserve the juice)"
    text = re.sub(r",?\s*drained\s*\(reserve\s+(?:the\s+)?(?:juice|liquid|broth)s?\)$", "", text)
    # ", as needed" / ", approximately" / ", enough to cover" / ", to fill"
    text = re.sub(r",\s*(?:as needed|approximately|enough to cover|to fill)$", "", text)
    # ", stems removed" / ", stem removed" / ", stems trimmed" / ", stems removed and halved if large"
    text = re.sub(r",\s*(?:stems?\s+(?:removed|trimmed|discarded)|tough ends?\s+(?:snapped off|trimmed|removed|broken off))(?:\s+and\s+[a-z]+(?:\s+[a-z]+)*)?$", "", text)
    # ", leaf only" / ", leaves only" / ", white part only" / ", white parts only"
    text = re.sub(r",\s*(?:lea(?:f|ves)\s+only|white\s+parts?\s+only|tops?\s+only|florets?\s+only|green parts?\s+only)$", "", text)
    # ", patted dry" / ", skin removed" / ", rind removed"
    text = re.sub(r",\s*(?:patted dry|skin removed|rind removed|seeds? removed|membrane removed|paper removed)$", "", text)
    # ", thawed if frozen" / ", if frozen thawed"
    text = re.sub(r",\s*(?:thawed if frozen|if frozen,?\s*thawed|thawed from frozen)$", "", text)
    # ", chiffonade" / ", diagonally" / ", pureed" / ", very ripe"
    text = re.sub(r",\s*(?:chiffonade|diagonally|pureed|very ripe|well drained|lightly packed)$", "", text)
    # ", each cut in half" / ", each halved"
    text = re.sub(r",\s*each\s+(?:cut\s+in\s+half|halved|quartered|split)$", "", text)
    # ", depending on [anything]"
    text = re.sub(r",\s*depending on\s+[a-z][a-z /'-]+$", "", text)
    # Parenthetical purpose — "(for cornstarch slurry)" etc.
    text = re.sub(r"\s*\(for\s+[a-z][a-z /'-]+\)$", "", text)
    # "(plus more if needed)" / "(or as needed)"
    text = re.sub(r"\s*\((?:plus\s+)?(?:more|extra)\s+(?:if\s+needed|as\s+needed|for\s+[a-z]+)\)\s*$", "", text)
    # ", defatted" / ", heated" / ", warmed" / ", low sodium"
    text = re.sub(r",\s*(?:defatted|heated|warmed|low[- ]sodium|reduced[- ]sodium)$", "", text)
    # Strip trailing "piece " prefix from ginger-like items (e.g. "piece ginger" → "ginger")
    text = re.sub(r"^piece\s+(?:of\s+)?(?:fresh\s+)?", "", text)
    # "leaves X" → "X" for herbs/greens
    text = re.sub(r"^leaves?\s+(boston\s+lettuce|chinese\s+cabbage|romaine|iceberg|cabbage|bibb\s+lettuce|butter\s+lettuce|napa\s+cabbage|kale|chard|collard\s+greens?)$", r"\1", text)
    # "xxx sugar" / "xxxx sugar" → powdered sugar
    text = re.sub(r"^x{2,4}\s+sugar$", "powdered sugar", text)
    # "egg egg" doubled word → "egg"
    text = re.sub(r"^(egg|eggs)\s+\1$", r"\1", text)
    # "teaspoon(s) X" / "tablespoon(s) X" — unit prefix not stripped
    text = re.sub(r"^(?:teaspoon|tablespoon|tsp|tbsp)s?\s*\(s\)\s+", "", text)
    # "small amount X" → "X"
    text = re.sub(r"^(?:small|large)\s+amount\s+(?:of\s+)?", "", text)
    # "such as safflower/canola/etc." trailing
    text = re.sub(r",\s*such\s+as\s+[a-z][a-z /'-]+$", "", text)
    # "knox unflavored gelatin" → brand strip
    text = re.sub(r"^knox\s+", "", text)
    # "soup cans of water" → "water"
    text = re.sub(r"^(?:soup\s+)?cans?\s+of\s+(water|milk|broth|stock)$", r"\1", text)
    # "butter for cooking" → "butter"
    text = re.sub(r"^(butter|oil|olive oil|vegetable oil)\s+for\s+(?:cooking|frying|greasing|sauteing|baking)$", r"\1", text)
    text = re.sub(r"\s+", " ", text).strip(" ,.-")
    return canonicalize_source_spelling(text)


def parse_line(line: str) -> dict[str, str]:
    normalized = (line or "").strip()
    normalized = normalized.replace("–", "-").replace("—", "-")
    normalized = re.sub(r"(?<=\d)\\(?=\d)", "/", normalized)
    normalized = re.sub(r"^(?:about|approximately|approx\.?)\s+", "", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"^(?:scant|level|heaping|rounded)\s+(?=(?:\d|[¼½¾⅓⅔⅛⅜⅝⅞]))", "", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"^no\.?\s*\d+\s+can\s+", "1 can ", normalized, flags=re.IGNORECASE)
    sized_package_match = re.match(
        rf"^\s*(?P<count>{NUMBER_ATOM})\s+(?P<size>{NUMBER_TOKEN})[-\s]*(?P<size_unit>{PACKAGE_SIZE_UNIT_PATTERN})\s+(?P<container>{PACKAGE_CONTAINER_PATTERN})\s+(?P<food>.+?)\s*$",
        normalized,
        flags=re.IGNORECASE,
    )
    if sized_package_match:
        result = package_weight_parse_result(
            count_text=sized_package_match.group("count"),
            size_text=sized_package_match.group("size"),
            size_unit_text=sized_package_match.group("size_unit"),
            food_phrase=sized_package_match.group("food"),
        )
        if result is not None:
            return result
    container_parenthetical_match = re.match(
        rf"^\s*(?P<count>{NUMBER_ATOM})\s+(?P<container>{PACKAGE_CONTAINER_PATTERN})\s+\((?P<size>{NUMBER_TOKEN})[-\s]*(?P<size_unit>{PACKAGE_SIZE_UNIT_PATTERN})\)\s+(?P<food>.+?)\s*$",
        normalized,
        flags=re.IGNORECASE,
    )
    if container_parenthetical_match:
        result = package_weight_parse_result(
            count_text=container_parenthetical_match.group("count"),
            size_text=container_parenthetical_match.group("size"),
            size_unit_text=container_parenthetical_match.group("size_unit"),
            food_phrase=container_parenthetical_match.group("food"),
        )
        if result is not None:
            return result
    parenthetical_pounds_ounces_match = re.match(
        rf"""
        ^\s*
        (?:(?P<count>{NUMBER_TOKEN})\s+)?
        \(
            (?P<pounds>{NUMBER_TOKEN})[-\s]*lbs?\.?
            \s+
            (?P<ounces>{NUMBER_TOKEN})[-\s]*oz\.?
        \)
        \s*
        (?:(?P<container>{PACKAGE_CONTAINER_PATTERN})\s+)?
        (?P<food>.+?)
        \s*$
        """,
        normalized,
        flags=re.IGNORECASE | re.VERBOSE,
    )
    if parenthetical_pounds_ounces_match:
        result = package_pounds_ounces_parse_result(
            count_text=parenthetical_pounds_ounces_match.group("count") or "1",
            pounds_text=parenthetical_pounds_ounces_match.group("pounds"),
            ounces_text=parenthetical_pounds_ounces_match.group("ounces"),
            food_phrase=parenthetical_pounds_ounces_match.group("food"),
        )
        if result is not None:
            return result
    normalized = re.sub(
        r"^(?P<count>\d+)\s+\d+(?:\s+\d+/\d+)?[- ](?:ounce|oz\.?)\s+(?P<container>cans?|packages?|pkgs?\.?|jars?|bottles?|boxes?|bags?|tubs?)\s+",
        r"\g<count> \g<container> ",
        normalized,
        flags=re.IGNORECASE,
    )
    normalized = re.sub(
        r"^(?P<count>\d+)\s+\d+(?:[./]\d+)?[-\s]?(?:inch|inches|cm|mm)\s+",
        r"\g<count> ",
        normalized,
        flags=re.IGNORECASE,
    )
    # Collapse range quantities "4 to 4-1/2 cups X" / "3 to 4 cups X" → "4 cups X"
    normalized = re.sub(
        r"^(\d+(?:[./]\d+)?)\s+to\s+\d+(?:[-/]\d+)?(?:[./]\d+)?(\s+(?:cups?|c\.?|teaspoons?|tsps?|tablespoons?|tbsps?|tbs\.?|ounces?|oz\.?|pounds?|lbs?\.?|grams?|g|pints?|pts?|quarts?|qts?|gallons?|gals?))",
        r"\1\2",
        normalized,
        flags=re.IGNORECASE,
    )
    # Strip leading dimension markers "1 inch X", "2-inch X", "(1 inch) X"
    normalized = re.sub(r"^\d+(?:[./]\d+)?[-\s]?(?:inch|inches|cm|mm)\s+", "", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"^\(\d+(?:[./]\d+)?[-\s]?(?:inch|inches|cm|mm)\)\s+", "", normalized, flags=re.IGNORECASE)
    juice_count_match = re.match(
        rf"^\s*juice\s+(?:of\s+|from\s+)?(?P<quantity>{NUMBER_TOKEN})\s+(?:(?:large|medium|small)\s+)?(?P<citrus>lemon|lime|orange|grapefruit)s?\s*$",
        normalized,
        flags=re.IGNORECASE,
    )
    if juice_count_match:
        citrus = juice_count_match.group("citrus").lower()
        return {
            "parsed_quantity": juice_count_match.group("quantity").strip(),
            "parsed_unit": "count",
            "parsed_food_phrase": f"{citrus} juice",
            "cleaned_surface": f"{citrus} juice",
        }
    parenthetical_package_match = re.match(
        rf"""
        ^\s*
        (?:(?P<count>{NUMBER_TOKEN})\s+)?
        \(
            (?P<size>{NUMBER_TOKEN})
            [-\s]*
            (?P<size_unit>
                fluid\ ounces?\.?|fl\.?\s*oz\.?|ounces?\.?|oz\.?|
                pounds?\.?|lbs?\.?|grams?\.?|g|kilograms?\.?|kg|
                milliliters?\.?|ml|liters?\.?|l
            )
        \)
        \s*
        (?:
            (?P<container>
                cans?|packages?|pkgs?\.?|packets?|jars?|bottles?|box(?:es)?|bags?|tubs?|containers?|cartons?|envelopes?
            )
            \s+
        )?
        (?P<food>.+?)
        \s*$
        """,
        normalized,
        flags=re.IGNORECASE | re.VERBOSE,
    )
    if parenthetical_package_match:
        count = numeric_quantity_token(parenthetical_package_match.group("count") or "1") or 1.0
        size = numeric_quantity_token(parenthetical_package_match.group("size") or "")
        size_unit = parenthetical_package_match.group("size_unit").lower().replace(".", "")
        if size is not None:
            if size_unit in {"fl oz", "fl  oz", "fluid ounce", "fluid ounces"}:
                size_unit = "fluid ounce"
            elif size_unit in {"oz", "ounce", "ounces"}:
                size_unit = "ounce"
            elif size_unit in {"lb", "lbs", "pound", "pounds"}:
                size_unit = "pound"
            elif size_unit in {"g", "gram", "grams"}:
                size_unit = "gram"
            elif size_unit in {"kg", "kilogram", "kilograms"}:
                size_unit = "kg"
            elif size_unit in {"ml", "milliliter", "milliliters"}:
                size_unit = "ml"
            elif size_unit in {"l", "liter", "liters"}:
                size_unit = "liter"
            food_phrase = parenthetical_package_match.group("food").strip(" ,.-")
            surface = refine_surface(surface_candidate_from_parsed_food(food_phrase))
            return {
                "parsed_quantity": format_quantity(count * size),
                "parsed_unit": size_unit,
                "parsed_food_phrase": food_phrase,
                "cleaned_surface": surface,
            }
    unit_of_match = re.match(
        r"^\s*(?P<unit>sprigs?|stalks?|cloves?|slices?|pieces?)\s+of\s+(?P<food>.+?)\s*$",
        normalized,
        flags=re.IGNORECASE,
    )
    if unit_of_match:
        unit = unit_of_match.group("unit").lower()
        food_phrase = unit_of_match.group("food").strip(" ,.-")
        surface = refine_surface(surface_candidate_from_parsed_food(food_phrase))
        return {
            "parsed_quantity": "1",
            "parsed_unit": unit[:-1] if unit.endswith("s") else unit,
            "parsed_food_phrase": food_phrase,
            "cleaned_surface": surface,
        }
    match = LEADING_MEASURE_RE.match(normalized)
    if match:
        quantity = (match.group("quantity") or "").strip()
        unit = (match.group("unit") or "").strip().lower()
        if unit in {"tbl", "tbls"}:
            unit = "tablespoons"
        food_phrase = (match.group("food") or "").strip(" ,.-")
        food_phrase = re.sub(r"\s*\([^)]*\)", " ", food_phrase).strip(" ,.-")
        if unit in {"clove", "cloves"} and food_phrase.lower() in {"whole", "ground", "powdered"}:
            food_phrase = f"{food_phrase} clove"
            unit = ""
        if not unit:
            lowered_food_phrase = food_phrase.lower()
            for suffix_pattern, inferred_unit in (
                (r"\s+rounds?(?:,.*)?$", "round"),
                (r"\s+ribs?(?:,.*)?$", "rib"),
            ):
                match_suffix = re.search(suffix_pattern, lowered_food_phrase)
                if match_suffix:
                    prefix = lowered_food_phrase[: match_suffix.start()]
                    if inferred_unit == "round" and re.search(r"\b(?:sliced|cut)\s+(?:in|into)\b", prefix):
                        continue
                    unit = inferred_unit
                    food_phrase = food_phrase[: match_suffix.start()].strip(" ,.-")
                    break
    else:
        quantity = ""
        unit = ""
        food_phrase = normalized.strip(" ,.-")

    if match:
        surface = surface_candidate_from_parsed_food(food_phrase)
    else:
        surface = simple_surface_candidate(food_phrase)
    if not surface:
        surface = simple_surface_candidate(normalized)
    if not surface:
        surface = food_phrase.lower()
    surface = refine_surface(surface)
    if unit in {"pkg", "pkgs", "package", "packages", "packet", "packets", "envelope", "envelopes"}:
        if surface == "onion soup":
            surface = "onion soup mix"
        elif surface == "lipton onion soup":
            surface = "lipton onion soup mix"
    for prefix in ("dash of ", "pinch of ", "dash ", "pinch ", "dsh ", "pch "):
        if surface.startswith(prefix):
            surface = surface[len(prefix) :].strip()
            break

    return {
        "parsed_quantity": quantity,
        "parsed_unit": unit,
        "parsed_food_phrase": food_phrase,
        "cleaned_surface": surface,
    }


def clean_example_surface(surface: str) -> str:
    surface = (surface or "").strip().lower()
    surface = surface.replace("...", "").strip(" ,;.")
    return surface


def parse_concept_key(value: str) -> dict[str, str]:
    parts = (value or "").split("|")
    parts = (parts + ["", "", "", ""])[:4]
    return {
        "base_food": parts[0],
        "variant": parts[1],
        "form": parts[2],
        "state": parts[3],
        "total_recipes": "",
        "surface_count": "",
        "example_surfaces": value,
    }


_COLOR_TOKENS = {"white", "red", "yellow", "green", "brown", "black", "blue", "pink", "purple", "orange"}
BLOCKED_APPROVED_RULE_SURFACES = {
    "green bean casserole, leftover",
}


def concept_key_from_parts(base_food: str, variant: str = "", form: str = "", state: str = "") -> str:
    """Build canonical concept_key with color-duplication guard.

    If a color token appears in `base_food`, strip that same token from
    `variant`, `form`, and `state` to prevent `white bread|white|white|`
    style duplication. The color already lives in the base; repeating it in
    other slots creates ambiguity and produces multiple concept_keys for
    the same logical concept.
    """
    base_low_tokens = set(base_food.lower().split())
    color_in_base = base_low_tokens & _COLOR_TOKENS
    if color_in_base:
        def _strip(slot: str) -> str:
            if not slot:
                return slot
            parts = [p for p in slot.split() if p.lower() not in color_in_base]
            return " ".join(parts)
        variant = _strip(variant)
        form = _strip(form)
        state = _strip(state)
    return "|".join([base_food, variant, form, state])


def load_approved_normalization_rules(path: Path) -> dict[str, object]:
    rules: dict[str, object] = {"exact": {}, "regex": []}
    if not path.exists():
        return rules
    allowed_rule_types = {"alias", "alternative", "manual_quantity", "split", "reject", "manual"}
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if None in row:
                raise ValueError(f"Malformed CSV row in {path}: extra columns in rule {row.get('rule_id')}")
            if row.get("status") != "approved":
                continue
            rule_id = row.get("rule_id")
            rule_type = (row.get("rule_type") or "").strip()
            canonical_key = (row.get("canonical_concept_key") or "").strip()
            canonical_surface = (row.get("canonical_surface") or "").strip()
            components = [part.strip() for part in (row.get("components") or "").split(";") if part.strip()]
            if rule_type not in allowed_rule_types:
                raise ValueError(f"Unsupported approved normalization rule_type {rule_type!r} for {rule_id} in {path}")
            if rule_type == "alias" and not canonical_key:
                raise ValueError(f"Approved alias rule {rule_id} in {path} must have canonical_concept_key")
            if rule_type == "manual_quantity" and (not canonical_key or not canonical_surface):
                raise ValueError(
                    f"Approved manual_quantity rule {rule_id} in {path} must have canonical_concept_key and canonical_surface"
                )
            if rule_type in {"split", "alternative"} and (
                (rule_type == "split" and not components) or (rule_type == "alternative" and len(components) < 2)
            ):
                raise ValueError(
                    f"Approved {rule_type} rule {rule_id} in {path} must have semicolon-delimited components"
                )
            if rule_type in {"reject", "manual"} and not canonical_surface:
                raise ValueError(f"Approved {rule_type} rule {rule_id} in {path} must have canonical_surface reason")
            evidence = (row.get("evidence") or "").lower()
            if rule_type == "alias" and re.search(r"\bor\b", row.get("input_surface", "")):
                if "silent" in evidence or "pick first" in evidence or "choose one" in evidence:
                    raise ValueError(
                        f"Unsafe alias-or rule {rule_id} in {path}: alternatives must use rule_type=alternative"
                    )
            match_type = row.get("match_type")
            if match_type == "exact":
                surface = clean_example_surface(row.get("input_surface", ""))
                if not surface:
                    continue
                if surface in BLOCKED_APPROVED_RULE_SURFACES:
                    continue
                rules["exact"][surface] = row
            elif match_type == "regex":
                pattern = row.get("input_surface", "")
                if not pattern:
                    continue
                row = dict(row)
                row["_compiled_pattern"] = re.compile(pattern)
                rules["regex"].append(row)
    return rules


def expand_rule_template(value: str, match: re.Match[str]) -> str:
    if not value:
        return value
    return match.expand(value).strip()


def approved_rule_for_surface(
    cleaned_surface: str,
    approved_rules: dict[str, object],
    *,
    include_exact: bool = True,
    include_regex: bool = True,
) -> dict[str, str] | None:
    surface = clean_example_surface(cleaned_surface)
    exact_rules = approved_rules.get("exact", {})
    exact_match = None
    if include_exact and isinstance(exact_rules, dict) and surface in exact_rules:
        exact_match = exact_rules[surface]
        if exact_match.get("rule_type") == "reject":
            return exact_match
    if not include_regex:
        return exact_match
    regex_rules = approved_rules.get("regex", [])
    if not isinstance(regex_rules, list):
        return exact_match
    first_regex_match = None
    for row in regex_rules:
        pattern = row.get("_compiled_pattern")
        if pattern is None:
            continue
        match = pattern.match(surface)
        if not match:
            continue
        expanded = {key: value for key, value in row.items() if not key.startswith("_")}
        for key in ("canonical_concept_key", "canonical_surface", "components"):
            value = expanded.get(key, "")
            if isinstance(value, str):
                expanded[key] = expand_rule_template(value, match)
        expanded["input_surface"] = surface
        if expanded.get("rule_type") == "reject":
            return expanded
        if first_regex_match is None:
            first_regex_match = expanded
    if exact_match is not None:
        return exact_match
    return first_regex_match


def resolve_approved_rule(
    approved_rule: dict[str, str],
) -> tuple[dict[str, str] | None, str, str, str, dict[str, str] | None]:
    rule_type = approved_rule.get("rule_type", "")
    rule_id = approved_rule.get("rule_id", "")
    if rule_type == "alias":
        return (
            parse_concept_key(approved_rule.get("canonical_concept_key", "")),
            "",
            "approved_alias_match",
            f"approved normalization rule: {rule_id}",
            None,
        )
    if rule_type == "alternative":
        return None, "", "approved_alternative_match", f"approved normalization rule: {rule_id}", None
    if rule_type == "manual_quantity":
        return (
            parse_concept_key(approved_rule.get("canonical_concept_key", "")),
            approved_rule.get("canonical_surface") or "manual_quantity_required",
            "approved_manual_quantity_match",
            f"approved normalization rule: {rule_id}",
            None,
        )
    if rule_type == "split":
        return None, "", "approved_split_match", f"approved normalization rule: {rule_id}", None
    if rule_type == "reject":
        review_reason = approved_rule.get("canonical_surface") or "approved_reject"
        return None, review_reason, "needs_review", review_reason, None
    if rule_type == "manual":
        review_reason = approved_rule.get("canonical_surface") or "approved_manual"
        return None, review_reason, "needs_review", review_reason, None
    raise ValueError(f"Unsupported approved normalization rule_type {rule_type!r} for {rule_id}")


def load_dictionary(
    path: Path,
) -> tuple[dict[tuple[str, str, str, str], dict[str, str]], set[str], dict[str, dict[str, str]]]:
    qualified: dict[tuple[str, str, str, str], dict[str, str]] = {}
    bases: set[str] = set()
    aliases: dict[str, dict[str, str]] = {}
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if is_poison_base(row.get("base_food", "")):
                continue
            key = (row["base_food"], row["variant"], row["form"], row["state"])
            qualified[key] = row
            bases.add(row["base_food"])
            aliases.setdefault(row["base_food"], row)
            for example in row.get("example_surfaces", "").split(";"):
                alias = clean_example_surface(example)
                if alias:
                    aliases.setdefault(alias, row)
    return qualified, bases, aliases


def load_supplemental_concepts(path: Path) -> dict[str, dict[str, str]]:
    aliases: dict[str, dict[str, str]] = {}
    if not path.exists():
        return aliases
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row.get("review_status") != "approved":
                continue
            alias = clean_example_surface(row.get("alias", ""))
            if alias:
                aliases[alias] = row
    return aliases


def alias_lookup(
    candidates: list[str],
    qualified: dict[tuple[str, str, str, str], dict[str, str]],
    aliases: dict[str, dict[str, str]],
) -> dict[str, str] | None:
    for candidate in candidates:
        candidate = clean_example_surface(candidate)
        if not candidate:
            continue
        alias = aliases.get(candidate)
        if alias is not None:
            return alias
        singular = candidate[:-1] if candidate.endswith("s") else candidate
        if singular != candidate:
            alias = aliases.get(singular)
            if alias is not None:
                return alias
        row = qualified.get((candidate, "", "", ""))
        if row is not None:
            return row
        if singular != candidate:
            row = qualified.get((singular, "", "", ""))
            if row is not None:
                return row
    return None


def match_supplemental_concept(
    cleaned_surface: str,
    normalized: dict[str, str] | None,
    supplemental_aliases: dict[str, dict[str, str]],
) -> tuple[str, dict[str, str] | None, str]:
    candidates = [cleaned_surface]
    if normalized is not None:
        compound_candidate = " ".join(
            token
            for token in [
                normalized["variant"],
                normalized["form"],
                normalized["state"],
                normalized["base_food"],
            ]
            if token
        )
        if compound_candidate and compound_candidate != normalized["base_food"]:
            candidates.append(compound_candidate)
    for candidate in candidates:
        entry = supplemental_aliases.get(clean_example_surface(candidate))
        if not entry:
            continue
        nutrition_state = entry.get("nutrition_state", "")
        if nutrition_state == "exact_usda_anchor":
            status = "supplemental_exact_usda_anchor_match"
        elif nutrition_state == "reviewed_local_label_anchor":
            status = "supplemental_reviewed_local_label_anchor_match"
        elif nutrition_state == "reviewed_proxy":
            status = "supplemental_reviewed_proxy_match"
        else:
            status = "supplemental_concept_review"
        reason = f"supplemental concept: {entry.get('trust_state', '')}"
        return status, entry, reason
    return "", None, ""


def compound_alias_candidates(normalized: dict[str, str]) -> list[str]:
    base = normalized["base_food"]
    variant = normalized["variant"]
    if not variant or variant in SIZE_VARIANTS:
        return []

    candidates = [f"{variant} {base}"]
    if base.endswith("s"):
        candidates.append(f"{variant} {base[:-1]}")
    return candidates


def _collapse_alternative(surface: str) -> str | None:
    # Same-concept form collapses only (fresh/dried/frozen of the SAME base food).
    # Different-food alternatives (butter or margarine, pecans or walnuts) must NOT
    # be silently picked here — they go to approved_normalization_rules.csv as
    # rule_type=alternative with semicolon-delimited components, or stay unresolved.
    stripped = re.sub(r"\s+or\s+possibly\s+", " or ", surface)
    if stripped != surface:
        surface = stripped
    m = re.fullmatch(r"(?:fresh\s+)?([a-z][a-z\s-]*?)\s+or\s+(?:dried|fresh|frozen)\s+\1", surface)
    if m:
        return m.group(1).strip()
    m = re.fullmatch(r"(?:dried|fresh|frozen)\s+([a-z][a-z\s-]*?)\s+or\s+\1", surface)
    if m:
        return m.group(1).strip()
    m = re.fullmatch(
        r"(?:minced\s+|chopped\s+)?fresh\s+([a-z][a-z\s-]*?)(?:\s+leaves)?\s*,?\s+or\s+[\d/\s]*(?:teaspoons?|tsps?|tablespoons?|tbsps?|tbs\.?)\s+dried\s+\1(?:\s*,?\s*crushed)?",
        surface,
    )
    if m:
        return f"fresh {m.group(1).strip()}"
    return None


def normalize_surface(surface: str) -> tuple[dict[str, str] | None, str]:
    if re.search(r"\bor\b", surface or ""):
        collapsed = _collapse_alternative(surface)
        if collapsed is None:
            return None, "composite_or"
        surface = collapsed

    row = {
        "base_food": surface,
        "variant": "",
        "form": "",
        "state": "",
        "total_recipes": "0",
        "surface_count": "0",
        "example_surfaces": surface,
    }
    cleaned, review = clean_row(row)
    if review is not None:
        return None, review.get("codex_reason", "review")
    return cleaned, ""


def match_dictionary(
    normalized: dict[str, str] | None,
    review_reason: str,
    qualified: dict[tuple[str, str, str, str], dict[str, str]],
    bases: set[str],
    aliases: dict[str, dict[str, str]],
    cleaned_surface: str,
) -> tuple[str, dict[str, str] | None, str]:
    surface_alias = clean_example_surface(cleaned_surface)
    if surface_alias in NON_FOOD_SURFACES:
        return "needs_review", None, "non_food"
    if any(p.search(surface_alias) for p in NON_FOOD_PATTERNS):
        return "needs_review", None, "non_food"
    if any(p.search(surface_alias) for p in SECTION_HEADER_PATTERNS):
        return "needs_review", None, "section_header"
    if re.fullmatch(r"salt,?\s+(?:to taste\s+)?\(?for\s+(?:boiling|pasta|cooking)\s+water\)?(?:\s*\([^)]*\))?", surface_alias):
        return "needs_review", None, "cooking_context_skip: salt_for_boiling_water"
    if re.fullmatch(
        r"(?:vegetable\s+)?oil,?\s+for\s+(?:deep[- ]frying|deep[- ]fat frying|frying)",
        surface_alias,
    ):
        return "needs_review", None, "shopping_contract_needed: oil_absorption_model_required"
    if surface_alias in BLOCKED_FRAGMENT_SURFACES:
        return "needs_review", None, "parser_fragment_review: fragment_only"
    if re.fullmatch(rf"(?:(?:{'|'.join(sorted(VEGETABLE_PEPPER_CUES))})\s+)?peppers?", surface_alias) and surface_alias != "pepper":
        return "needs_review", None, "ambiguous_pepper_surface: vegetable pepper cue needs color/type review"

    alias = aliases.get(surface_alias)
    if alias is not None:
        return "surface_alias_match", alias, ""

    if normalized is None:
        return "needs_review", None, review_reason

    key = (
        normalized["base_food"],
        normalized["variant"],
        normalized["form"],
        normalized["state"],
    )
    if key in qualified:
        return "qualified_match", qualified[key], ""

    compound_alias = alias_lookup(compound_alias_candidates(normalized), qualified, aliases)
    if compound_alias is not None:
        return "compound_alias_match", compound_alias, "protected compound recovered from variant + base"

    base = normalized["base_food"]
    base_key = (base, "", "", "")
    if base_key in qualified:
        variant = normalized["variant"]
        form = normalized["form"]
        state = normalized["state"]
        if variant in SIZE_VARIANTS and not form and not state:
            return "base_row_fallback_match", qualified[base_key], "size qualifier kept outside nutrition concept"
        if state == "fresh" and not variant and not form:
            return "base_row_fallback_match", qualified[base_key], "fresh state kept outside nutrition concept"
        if form in PREP_FORMS and state in SAFE_FALLBACK_STATES and (not variant or variant in SIZE_VARIANTS):
            return "base_row_fallback_match", qualified[base_key], "prep/form qualifier kept outside nutrition concept"

    if (not normalized["variant"] or normalized["variant"] in SIZE_VARIANTS) and normalized["form"] in PREP_FORMS and normalized["state"] in SAFE_FALLBACK_STATES:
        base_alias = alias_lookup([base], qualified, aliases)
        if base_alias is not None:
            return "base_alias_fallback_match", base_alias, "prep/size qualifier kept outside nutrition concept"

    if normalized["variant"] in SIZE_VARIANTS and not normalized["form"] and normalized["state"] in SAFE_FALLBACK_STATES:
        base_alias = alias_lookup([base], qualified, aliases)
        if base_alias is not None:
            return "base_alias_fallback_match", base_alias, "size qualifier kept outside nutrition concept"

    if normalized["state"] == "fresh" and not normalized["variant"] and not normalized["form"]:
        base_alias = alias_lookup([base], qualified, aliases)
        if base_alias is not None:
            return "base_alias_fallback_match", base_alias, "fresh state kept outside nutrition concept"

    if base in bases:
        return "base_only_match", None, "qualified tuple not present; base exists"

    if base.endswith("s"):
        singular = base[:-1]
        alias = aliases.get(singular)
        if alias is not None:
            return "singular_alias_match", alias, ""
        if singular in bases:
            return "base_only_match", None, "singular base exists"

    return "no_dictionary_match", None, "base not present in dictionary"


def route_resolution(status: str, reason: str, review_reason: str) -> tuple[str, str, str]:
    detail = "; ".join(part for part in [reason, review_reason] if part)
    if status == "approved_alias_match":
        return "reviewed_resolved", "approved_alias", detail
    if status == "approved_alternative_match":
        return "reviewed_resolved", "approved_alternative_options", detail
    if status == "approved_manual_quantity_match":
        return "reviewed_resolved", "manual_quantity_required", detail
    if status == "approved_split_match":
        return "reviewed_resolved", "approved_split", detail
    if status in {
        "surface_alias_match",
        "qualified_match",
        "singular_alias_match",
        "base_row_fallback_match",
        "compound_alias_match",
        "base_alias_fallback_match",
    }:
        return "auto_resolved", "dictionary_match", detail
    if status == "supplemental_exact_usda_anchor_match":
        return "reviewed_resolved", "exact_usda_anchor", detail
    if status == "supplemental_reviewed_local_label_anchor_match":
        return "reviewed_resolved", "reviewed_local_label_anchor", detail
    if status == "supplemental_reviewed_proxy_match":
        return "reviewed_resolved", "reviewed_proxy", detail
    if "section_header" in detail:
        return "unresolved_explicit", "section_header", detail
    if "intentional_skip" in detail:
        return "unresolved_explicit", "intentional_skip", detail
    if "parser_fragment" in detail and "parser_fragment_review" not in detail:
        return "unresolved_explicit", "non_food", detail
    if "non_food" in detail or "parser_error" in detail or "recipe_metadata" in detail or "recipe_instruction" in detail:
        return "unresolved_explicit", "non_food", detail
    if "cooking_context_skip" in detail:
        return "unresolved_explicit", "cooking_context_skip", detail
    if "shopping_contract_needed" in detail:
        return "unresolved_explicit", "shopping_contract_needed", detail
    if "composite_or" in detail:
        return "unresolved_explicit", "true_alternative_review", detail
    if "composite_and" in detail:
        return "unresolved_explicit", "component_split_review", detail
    if "numeric_or_ad_leak" in detail or "parser_fragment_review" in detail:
        return "unresolved_explicit", "parser_fragment_review", detail
    if "brand" in detail:
        return "unresolved_explicit", "brand_compound_review", detail
    if status == "base_only_match":
        return "unresolved_explicit", "qualified_tuple_unapproved", detail
    if status == "no_dictionary_match":
        return "unresolved_explicit", "promotion_review_needed", detail
    return "unresolved_explicit", "parser_review_needed", detail


def iter_ingredient_lines(connection: sqlite3.Connection, min_recipe_count: int, limit: int | None):
    sql = """
        SELECT normalized_line, recipe_count, example_raw_line
        FROM ingredient_lines
        WHERE recipe_count >= ?
        ORDER BY recipe_count DESC, normalized_line ASC
    """
    if limit:
        sql += " LIMIT ?"
        return connection.execute(sql, (min_recipe_count, limit))
    return connection.execute(sql, (min_recipe_count,))


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Map recurring recipe ingredient lines to normalized concepts and qualified dictionary rows."
    )
    parser.add_argument("--input-db", type=Path, default=DEFAULT_INPUT_DB)
    parser.add_argument("--dictionary-csv", type=Path, default=DEFAULT_DICTIONARY_CSV)
    parser.add_argument("--supplemental-csv", type=Path, default=DEFAULT_SUPPLEMENTAL_CSV)
    parser.add_argument("--approved-rules-csv", type=Path, default=DEFAULT_APPROVED_RULES_CSV)
    parser.add_argument("--output-csv", type=Path, default=None)
    parser.add_argument("--summary-json", type=Path, default=None)
    parser.add_argument("--misses-csv", type=Path, default=None)
    parser.add_argument("--report-md", type=Path, default=None)
    parser.add_argument("--min-recipe-count", type=int, default=10)
    parser.add_argument("--limit", type=int, default=None)
    return parser


def apply_output_defaults(args: argparse.Namespace) -> argparse.Namespace:
    if args.min_recipe_count == 1:
        args.output_csv = args.output_csv or DEFAULT_FULL_OUTPUT_CSV
        args.summary_json = args.summary_json or DEFAULT_FULL_SUMMARY_JSON
        args.misses_csv = args.misses_csv or DEFAULT_FULL_MISSES_CSV
        args.report_md = args.report_md or DEFAULT_FULL_REPORT_MD
    else:
        args.output_csv = args.output_csv or DEFAULT_OUTPUT_CSV
        args.summary_json = args.summary_json or DEFAULT_SUMMARY_JSON
        args.misses_csv = args.misses_csv or DEFAULT_MISSES_CSV
        args.report_md = args.report_md or DEFAULT_REPORT_MD
    return args


def main() -> None:
    parser = build_arg_parser()
    args = apply_output_defaults(parser.parse_args())

    qualified, bases, aliases = load_dictionary(args.dictionary_csv)
    supplemental_aliases = load_supplemental_concepts(args.supplemental_csv)
    approved_rules = load_approved_normalization_rules(args.approved_rules_csv)
    status_counts: Counter[str] = Counter()
    status_occurrences: Counter[str] = Counter()
    miss_reason_counts: Counter[str] = Counter()
    miss_reason_occurrences: Counter[str] = Counter()
    route_counts: Counter[str] = Counter()
    route_occurrences: Counter[str] = Counter()
    action_counts: Counter[str] = Counter()
    action_occurrences: Counter[str] = Counter()
    rows_written = 0
    total_occurrences = 0

    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    lock_handle = acquire_output_lock(args.output_csv.parent / ".recipe_line_to_concept.lock")
    temp_output_csv = temporary_output_path(args.output_csv)
    temp_misses_csv = temporary_output_path(args.misses_csv)
    connection = sqlite3.connect(args.input_db)
    try:
        with temp_output_csv.open("w", newline="", encoding="utf-8") as handle, temp_misses_csv.open(
            "w", newline="", encoding="utf-8"
        ) as misses_handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDS)
            misses_writer = csv.DictWriter(misses_handle, fieldnames=FIELDS)
            writer.writeheader()
            misses_writer.writeheader()

            for normalized_line, recipe_count, example_raw_line in iter_ingredient_lines(
                connection, args.min_recipe_count, args.limit
            ):
                parsed = parse_line(normalized_line)
                supplemental_row: dict[str, str] | None = None
                approved_rule = approved_rule_for_surface(
                    parsed["cleaned_surface"],
                    approved_rules,
                    include_regex=True,
                )
                approved_rule_id = approved_rule.get("rule_id", "") if approved_rule else ""
                approved_rule_type = approved_rule.get("rule_type", "") if approved_rule else ""
                approved_rule_components = approved_rule.get("components", "") if approved_rule else ""

                if approved_rule:
                    normalized, review_reason, status, reason, dictionary_row = resolve_approved_rule(approved_rule)
                else:
                    normalized, review_reason = normalize_surface(parsed["cleaned_surface"])
                    supplemental_status, supplemental_row, supplemental_reason = match_supplemental_concept(
                        parsed["cleaned_surface"],
                        normalized,
                        supplemental_aliases,
                    )
                    if supplemental_status in MATCHED_STATUSES:
                        status = supplemental_status
                        dictionary_row = None
                        reason = supplemental_reason
                    else:
                        status, dictionary_row, reason = match_dictionary(
                            normalized,
                            review_reason,
                            qualified,
                            bases,
                            aliases,
                            parsed["cleaned_surface"],
                        )
                        if status in {"no_dictionary_match", "base_only_match"} and supplemental_status:
                            status = supplemental_status
                            reason = supplemental_reason
                            dictionary_row = None
                    if status not in MATCHED_STATUSES:
                        approved_rule = approved_rule_for_surface(
                            parsed["cleaned_surface"],
                            approved_rules,
                            include_exact=False,
                        )
                        if approved_rule:
                            approved_rule_id = approved_rule.get("rule_id", "")
                            approved_rule_type = approved_rule.get("rule_type", "")
                            approved_rule_components = approved_rule.get("components", "")
                            normalized, review_reason, status, reason, dictionary_row = resolve_approved_rule(
                                approved_rule
                            )
                            supplemental_row = None
                concept = dictionary_row or normalized
                if supplemental_row is not None:
                    concept = {
                        "base_food": supplemental_row["canonical_concept"],
                        "variant": "",
                        "form": "",
                        "state": "",
                    }
                resolution_route, resolution_action, resolution_reason = route_resolution(
                    status,
                    reason,
                    review_reason,
                )
                status_counts[status] += 1
                status_occurrences[status] += int(recipe_count)
                route_counts[resolution_route] += 1
                route_occurrences[resolution_route] += int(recipe_count)
                action_counts[resolution_action] += 1
                action_occurrences[resolution_action] += int(recipe_count)
                rows_written += 1
                total_occurrences += int(recipe_count)

                output_row = {
                    "normalized_line": normalized_line,
                    "recipe_count": recipe_count,
                    "example_raw_line": example_raw_line,
                    **parsed,
                    "normalized_base_food": normalized["base_food"] if normalized else "",
                    "normalized_variant": normalized["variant"] if normalized else "",
                    "normalized_form": normalized["form"] if normalized else "",
                    "normalized_state": normalized["state"] if normalized else "",
                    "concept_base_food": concept["base_food"] if concept else "",
                    "concept_variant": concept["variant"] if concept else "",
                    "concept_form": concept["form"] if concept else "",
                    "concept_state": concept["state"] if concept else "",
                    "dictionary_match_status": status,
                    "dictionary_match_reason": reason,
                    "dictionary_base_food": dictionary_row["base_food"] if dictionary_row else "",
                    "dictionary_variant": dictionary_row["variant"] if dictionary_row else "",
                    "dictionary_form": dictionary_row["form"] if dictionary_row else "",
                    "dictionary_state": dictionary_row["state"] if dictionary_row else "",
                    "dictionary_total_recipes": dictionary_row["total_recipes"] if dictionary_row else "",
                    "dictionary_surface_count": dictionary_row["surface_count"] if dictionary_row else "",
                    "dictionary_example_surfaces": dictionary_row["example_surfaces"] if dictionary_row else "",
                    "approved_rule_id": approved_rule_id,
                    "approved_rule_type": approved_rule_type,
                    "approved_rule_components": approved_rule_components,
                    "resolution_route": resolution_route,
                    "resolution_action": resolution_action,
                    "resolution_reason": resolution_reason,
                    "supplemental_canonical_concept": supplemental_row["canonical_concept"] if supplemental_row else "",
                    "supplemental_family": supplemental_row["family"] if supplemental_row else "",
                    "supplemental_trust_state": supplemental_row["trust_state"] if supplemental_row else "",
                    "supplemental_nutrition_state": supplemental_row["nutrition_state"] if supplemental_row else "",
                    "supplemental_shopping_state": supplemental_row["shopping_state"] if supplemental_row else "",
                    "supplemental_anchor_system": supplemental_row["anchor_system"] if supplemental_row else "",
                    "supplemental_anchor_code": supplemental_row["anchor_code"] if supplemental_row else "",
                    "supplemental_anchor_description": supplemental_row["anchor_description"] if supplemental_row else "",
                    "supplemental_product_query": supplemental_row["product_query"] if supplemental_row else "",
                    "supplemental_evidence_notes": supplemental_row["evidence_notes"] if supplemental_row else "",
                }
                writer.writerow(output_row)
                if status not in MATCHED_STATUSES and resolution_action not in {
                    "section_header",
                    "non_food",
                    "cooking_context_skip",
                    "intentional_skip",
                }:
                    miss_key = f"{status}: {reason or review_reason or 'unclassified'}"
                    miss_reason_counts[miss_key] += 1
                    miss_reason_occurrences[miss_key] += int(recipe_count)
                    misses_writer.writerow(output_row)
        temp_output_csv.replace(args.output_csv)
        temp_misses_csv.replace(args.misses_csv)
    finally:
        connection.close()
        release_output_lock(lock_handle)

    matched_rows = sum(status_counts[status] for status in MATCHED_STATUSES)
    matched_occurrences = sum(status_occurrences[status] for status in MATCHED_STATUSES)
    summary = {
        "input_db": str(args.input_db),
        "dictionary_csv": str(args.dictionary_csv),
        "supplemental_csv": str(args.supplemental_csv),
        "approved_rules_csv": str(args.approved_rules_csv),
        "output_csv": str(args.output_csv),
        "misses_csv": str(args.misses_csv),
        "report_md": str(args.report_md),
        "min_recipe_count": args.min_recipe_count,
        "limit": args.limit,
        "rows_written": rows_written,
        "total_occurrences": total_occurrences,
        "matched_rows": matched_rows,
        "matched_occurrences": matched_occurrences,
        "matched_row_percent": round(matched_rows / rows_written * 100, 2) if rows_written else 0,
        "matched_occurrence_percent": round(matched_occurrences / total_occurrences * 100, 2)
        if total_occurrences
        else 0,
        "status_counts": dict(status_counts),
        "status_occurrences": dict(status_occurrences),
        "miss_reason_counts": dict(miss_reason_counts),
        "miss_reason_occurrences": dict(miss_reason_occurrences),
        "route_counts": dict(route_counts),
        "route_occurrences": dict(route_occurrences),
        "action_counts": dict(action_counts),
        "action_occurrences": dict(action_occurrences),
    }
    args.summary_json.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    write_report(args, summary)
    print(json.dumps(summary, indent=2))


def write_report(args: argparse.Namespace, summary: dict[str, object]) -> None:
    status_counts = summary["status_counts"]
    status_occurrences = summary["status_occurrences"]
    miss_reason_counts = summary["miss_reason_counts"]
    miss_reason_occurrences = summary["miss_reason_occurrences"]
    route_counts = summary["route_counts"]
    route_occurrences = summary["route_occurrences"]
    action_counts = summary["action_counts"]
    action_occurrences = summary["action_occurrences"]
    assert isinstance(status_counts, dict)
    assert isinstance(status_occurrences, dict)
    assert isinstance(miss_reason_counts, dict)
    assert isinstance(miss_reason_occurrences, dict)
    assert isinstance(route_counts, dict)
    assert isinstance(route_occurrences, dict)
    assert isinstance(action_counts, dict)
    assert isinstance(action_occurrences, dict)

    lines = [
        "# Recipe Line To Concept Mapping",
        "",
        "## Inputs",
        "",
        f"- Recipe funnel DB: `{args.input_db}`",
        f"- Qualified dictionary: `{args.dictionary_csv}`",
        f"- Supplemental concept seed: `{args.supplemental_csv}`",
        f"- Approved normalization rules: `{args.approved_rules_csv}`",
        "",
        "## Outputs",
        "",
        f"- Full mapping: `{args.output_csv}`",
        f"- Miss/review set: `{args.misses_csv}`",
        f"- Summary JSON: `{args.summary_json}`",
        "",
        "## Scope",
        "",
        f"- Minimum ingredient-line frequency: `{args.min_recipe_count}`",
        f"- Mapped recurring ingredient lines: `{summary['rows_written']:,}`",
        f"- Total recipe-line occurrence volume represented: `{summary['total_occurrences']:,}`",
        "",
        "## Match Counts",
        "",
        "| Status | Rows | Occurrences |",
        "|---|---:|---:|",
    ]
    for status, count in sorted(status_counts.items(), key=lambda item: (-int(item[1]), item[0])):
        occurrences = int(status_occurrences.get(status, 0))
        lines.append(f"| `{status}` | `{int(count):,}` | `{occurrences:,}` |")

    lines.extend(
        [
            "",
            "## Coverage",
            "",
            f"- Matched rows: `{summary['matched_rows']:,} / {summary['rows_written']:,}` = `{summary['matched_row_percent']}%`",
            f"- Matched occurrence volume: `{summary['matched_occurrences']:,} / {summary['total_occurrences']:,}` = `{summary['matched_occurrence_percent']}%`",
            "",
            "Matched means one of:",
        ]
    )
    for status in sorted(MATCHED_STATUSES):
        lines.append(f"- `{status}`")
    lines.extend(
        [
            "",
            "`base_only_match` is not counted as fully matched because the base exists but the qualifier tuple is not approved.",
            "",
            "Supplemental matches are approved concept anchors, not rows from the SR28-derived dictionary. Their trust state is carried in the `supplemental_*` columns.",
            "",
            "## Explicit Routing",
            "",
            "| Route | Rows | Occurrences |",
            "|---|---:|---:|",
        ]
    )
    for route, count in sorted(route_counts.items(), key=lambda item: (-int(item[1]), item[0])):
        lines.append(f"| `{route}` | `{int(count):,}` | `{int(route_occurrences.get(route, 0)):,}` |")

    lines.extend(
        [
            "",
            "| Action | Rows | Occurrences |",
            "|---|---:|---:|",
        ]
    )
    for action, count in sorted(action_counts.items(), key=lambda item: (-int(item[1]), item[0]))[:30]:
        lines.append(f"| `{action}` | `{int(count):,}` | `{int(action_occurrences.get(action, 0)):,}` |")

    lines.extend(
        [
            "",
            "## Remaining Failure Classes",
            "",
            "| Failure class | Rows | Occurrences |",
            "|---|---:|---:|",
        ]
    )
    for reason, occurrences in sorted(
        miss_reason_occurrences.items(), key=lambda item: (-int(item[1]), item[0])
    )[:30]:
        lines.append(f"| `{reason}` | `{int(miss_reason_counts.get(reason, 0)):,}` | `{int(occurrences):,}` |")

    lines.extend(
        [
            "",
            "These rows stay out of the matched set until a splitter, dictionary addition, or explicit review rule handles them.",
            "",
        ]
    )
    args.report_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
