from __future__ import annotations

import csv
import re
from collections import defaultdict
from pathlib import Path

try:
    from identity_poison import poison_findings_for_base
except ModuleNotFoundError:
    from implementation.identity_poison import poison_findings_for_base


ROOT = Path(__file__).resolve().parent
INPUT_CSV = ROOT / "output" / "sr28_BASE_DICTIONARY_FINAL.csv"
OUTPUT_CSV = ROOT / "output" / "sr28_BASE_DICTIONARY_CODEX.csv"
REVIEW_CSV = ROOT / "output" / "sr28_BASE_DICTIONARY_CODEX_REVIEW.csv"
REPORT_MD = ROOT / "output" / "sr28_BASE_DICTIONARY_CODEX_report.md"


SECTION_EXACT = {
    "ingredients",
    "remaining ingredients",
    "toppings",
    "cookies",
    "cupcakes",
    "cakes",
    "bars",
    "brownies",
    "meatballs",
    "crust",
    "filling",
    "glaze",
    "topping",
    "sauce",
    "frosting",
    "icing",
    "garnish",
}

PACKAGING_PREFIXES = (
    "can ",
    "cans ",
    "bag ",
    "bags ",
    "box ",
    "boxes ",
    "basket ",
    "baskets ",
    "bushel ",
    "bottle ",
    "bottles ",
    "pkg. ",
    "package ",
    "packages ",
    "jar ",
    "carton ",
    "container ",
    "containers ",
    "tub ",
    "tubs ",
    "dozen ",
    "doz. ",
    "pt. ",
    "qt. ",
    "block ",
    "blocks ",
    "bowl ",
    "bowls ",
    "cartons ",
    "bottled ",
    "bar ",
    "bars ",
    "slice ",
    "slices ",
    "big slice ",
    "big slices ",
    "tube ",
    "tubes ",
    "roll ",
    "rolls ",
    "sleeve ",
    "sleeves ",
    "stack ",
    "stacks ",
    "pack ",
    "packet ",
    "packets ",
    "envelope ",
    "envelopes ",
)

STATE_PREFIXES = {
    "fresh": "fresh",
    "dried": "dried",
    "canned": "canned",
    "frozen": "frozen",
    "smoked": "smoked",
    "pickled": "pickled",
    "prepared": "prepared",
    "roasted": "roasted",
    "stewed": "stewed",
}

PREP_PREFIXES_TO_FORM = {
    "ground": "ground",
    "cracked": "cracked",
    "chopped": "chopped",
    "diced": "diced",
    "sliced": "sliced",
    "shredded": "shredded",
    "grated": "grated",
    "minced": "minced",
    "mashed": "mashed",
    "crushed": "crushed",
    "powdered": "powder",
    "flaked": "flakes",
}

PREP_PREFIXES_TO_DROP = {
    "peeled",
    "trimmed",
    "drained",
    "rinsed",
    "seeded",
    "squeezed",
    "deboned",
    "boneless",
    "skinless",
}

COLOR_VARIANTS = {"black", "brown", "green", "red", "white", "yellow"}
SIZE_VARIANTS = {"large", "medium", "small", "mini", "jumbo", "tiny"}
FAT_VARIANT_PREFIXES = {
    "fat-free": "fat-free",
    "fat free": "fat-free",
    "low-fat": "low-fat",
    "low fat": "low-fat",
    "nonfat": "nonfat",
    "reduced-fat": "reduced-fat",
    "reduced fat": "reduced-fat",
    "aluminum-free": "aluminum-free",
}

EXACT_BASE_MAP = {
    "half & half": "half-and-half",
    "half and half": "half-and-half",
    "half and half cream": "half-and-half",
    "half-and-half cream": "half-and-half",
    "bbq sauce": "barbecue sauce",
    "apple-cider vinegar": "apple cider vinegar",
    "pple": "apple",
    "pples": "apple",
    "apple sauce": "applesauce",
    "cool whip": "whipped topping",
    "thawed cool whip whipped topping": "whipped topping",
    "cool whip whipped topping": "whipped topping",
    "miracle whip": "salad dressing",
    "miracle whip salad dressing": "salad dressing",
    "miracle whip original spread": "salad dressing",
    "bisquick": "baking mix",
    "bisquick baking mix": "baking mix",
    "philadelphia cream cheese": "cream cheese",
    "velveeta": "processed cheese",
    "velveeta cheese": "processed cheese",
    "cheez whiz": "cheese spread",
    "eagle brand milk": "sweetened condensed milk",
    "eagle brand condensed milk": "sweetened condensed milk",
    "eagle brand sweetened condensed milk": "sweetened condensed milk",
    "ritz cracker": "cracker",
    "ritz crackers": "cracker",
    "curd cottage cheese": "cottage cheese",
    "ap flour": "all-purpose flour",
    "baking power": "baking powder",
    "baking pwdr": "baking powder",
    "blended oatmeal": "oatmeal",
    "blended miso": "miso",
    "blended scotch": "scotch",
    "a carrot carrot": "carrot",
    "a lemon": "lemon",
    "a lemon zest": "lemon",
    "montreal brand steak seasoning": "steak seasoning",
    "dry sherry wine": "dry sherry",
    "argo corn starch": "corn starch",
    "argo cornstarch": "cornstarch",
    "medium grain white rice": "white rice",
}

NONFOOD_EXACT = {
    "aluminum foil",
    "uminum foil",
    "reynolds wrap foil",
    "reynolds wrap aluminum foil",
    "heavy duty aluminum foil",
    "wax paper",
    "waxed paper",
    "paraffin",
    "paraffin wax",
    "bar paraffin",
    "bar paraffin wax",
    "wooden skewer",
    "bamboo skewer",
    "skewer",
    "toothpick",
    "kitchen string",
    "barrel laughter",
    "barrel of laughter",
    "laughter",
}

OCR_PREFIX_FIXES = {
    "amb ": "lamb ",
    "ean ": "lean ",
    "pple ": "apple ",
    "pples ": "apples ",
    "uminum ": "aluminum ",
    "presliced ": "sliced ",
    "canchopped ": "canned chopped ",
    "canschopped ": "canned chopped ",
}

LEADING_ADVERBS = (
    "freshly ",
    "coarsely ",
    "finely ",
    "lightly ",
)

TRAILING_CONTEXT_PATTERNS = (
    (re.compile(r"\s+for garnish$"), ""),
    (re.compile(r"\s+to garnish$"), ""),
    (re.compile(r"\s+to serve$"), ""),
    (re.compile(r"\s+for serving$"), ""),
    (re.compile(r"\s+for garnish only$"), ""),
    (re.compile(r"\s+to taste(?: if desired)?$"), ""),
    (re.compile(r"\s+\(optional\)$"), ""),
    (re.compile(r"\s+optional$"), ""),
    (re.compile(r"\s+if possible$"), ""),
    (re.compile(r"\s+for frying$"), ""),
    (re.compile(r"\s+for deep-frying$"), ""),
    (re.compile(r"\s+for deep fat frying$"), ""),
    (re.compile(r"\s+for dusting$"), ""),
    (re.compile(r"\s+for dredging$"), ""),
)

LEADING_BRANDS = (
    "kraft ",
    "philadelphia ",
    "land o lakes ",
    "breakstone's ",
    "knudsen ",
    "taco bell ",
    "betty crocker ",
    "best foods ",
    "campbell's ",
    "campbells ",
    "maxwell house ",
    "simply potatoes ",
    "a.1. ",
    "ritz ",
    "absolut ",
    "argo ",
    "mccormick's ",
    "mccormick ",
    "breyers ",
    "campbell's ",
    "campbells ",
    "griffin's ",
    "heinz ",
    "spice islands ",
    "jell-o ",
    "jello ",
    "knorr ",
    "kraft ",
    "philadelphia ",
    "pillsbury ",
    "simply ",
    "swanson ",
    "duncan ",
    "athenos ",
    "bertolli ",
    "classico ",
    "franco-american ",
    "progresso ",
    "master ",
    "maxwell ",
    "manwich ",
    "polly-o ",
    "betty crocker ",
    "wyler's ",
    "williams ",
    "good seasonings ",
    "good seasons ",
    "supermoist ",
)

NOISE_PREFIXES = (
    "of ",
    "size ",
    "regular size ",
    "touch of ",
    "your favorite ",
)

GENERIC_ENDINGS = (
    " cheese",
    " dressing",
    " sauce",
    " salsa",
    " butter",
    " milk",
    " coffee",
    " mayonnaise",
    " broth",
    " stock",
    " cracker",
    " crackers",
    " cake mix",
    " pudding",
    " topping",
    " whipped topping",
    " juice",
)

MISSPELLINGS = {
    "tomatoe": "tomato",
    "potatoe": "potato",
    "leave": "leaf",
    "imes": "limes",
    "ime": "lime",
    "eek": "leek",
    "oat": "oat",
    "amb": "lamb",
    "ean": "lean",
    "uminum": "aluminum",
    "l-purpose": "all-purpose",
    "consomm": "consomme",
    "consommé": "consomme",
}

TEMP_STRIPPABLE_BASES = {
    "milk",
    "water",
    "butter",
    "cream",
    "coffee",
    "tea",
    "cereal",
}

ALLOWED_AND_BASES = {
    "half-and-half",
    "sweet-and-sour mix",
    "prepared sweet-and-sour mix",
    "pork and beans",
    "macaroni and cheese",
}

NON_FOOD_EXACT = {
    "barrel laughter",
    "barrel of laughter",
    "laughter",
    "fresh",
    "coarsely",
}

PROTECTED_HYPHEN_PHRASES = (
    "half-and-half",
    "all-purpose",
    "self-rising",
    "flat-leaf",
    "sun-dried",
    "fat-free",
    "low-fat",
    "extra-virgin",
    "sweet-and-sour",
    "cook-and-serve",
    "canning-and-pickling",
    "aluminum-free",
)

PROTECTED_FORM_SUFFIX_BASES = {
    "baking powder",
    "chili powder",
    "curry powder",
    "cocoa powder",
    "onion powder",
    "garlic powder",
    "mustard powder",
    "cumin powder",
    "coriander powder",
    "turmeric powder",
    "milk powder",
    "custard powder",
    "espresso powder",
}

JUICE_PATTERNS = [
    re.compile(r"^juice (?:of|from) (?:half (?:a|an) |1/2 |1 |2 |the )?(lemon|lime|orange|grapefruit)$"),
]
ZEST_PATTERNS = [
    re.compile(r"^(?:zest|rind) of (?:half (?:a|an) |1/2 |1 |2 |the )?(lemon|lime|orange|grapefruit)$"),
]


def normalize_spaces(text: str) -> str:
    text = text.strip().lower()
    text = text.replace("\u2019", "'")
    text = text.replace("&", " and ")
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s*-\s*", "-", text)
    return text.strip(" ,;:")


def normalize_words(text: str) -> str:
    parts = text.split()
    fixed = [MISSPELLINGS.get(part, part) for part in parts]
    fixed_text = " ".join(fixed)
    fixed_text = fixed_text.replace("leaves", "leaf")
    return fixed_text


def normalize_special_base(text: str) -> str:
    text = text.replace("consommé", "consomme")
    text = text.replace("consomm√©", "consomme")
    text = text.replace("jell-o", "jello")
    text = re.sub(r"\bbbq\b", "barbecue", text)
    text = re.sub(r"\bgrnd\b", "ground", text)
    text = re.sub(r"\bpch\b", "", text)
    text = re.sub(r"\bdsh\b", "", text)
    text = text.replace("garnishe", "garnish")

    if text.startswith("amb "):
        text = "l" + text
    if text.startswith("ean "):
        text = "l" + text

    protected: dict[str, str] = {}
    for index, phrase in enumerate(PROTECTED_HYPHEN_PHRASES):
        token = f"__HYPHEN_{index}__"
        if phrase in text:
            text = text.replace(phrase, token)
            protected[token] = phrase

    text = re.sub(r"(?<=[a-z])-(?=[a-z])", " ", text)

    for token, phrase in protected.items():
        text = text.replace(token, phrase)

    text = text.replace("(peeled", "").replace("( peeled", "").strip()
    text = text.strip("() ")
    return text


def strip_prefixes(text: str, prefixes: tuple[str, ...]) -> tuple[str, bool]:
    changed = False
    while True:
        matched = False
        for prefix in prefixes:
            if text.startswith(prefix):
                text = text[len(prefix) :].strip()
                changed = True
                matched = True
                break
        if not matched:
            break
    return text, changed


def likely_section_header(base: str) -> bool:
    return (
        base.endswith(":")
        or base in SECTION_EXACT
        or base.startswith("for ")
        or base.startswith("for the ")
    )


def clean_row(row: dict[str, str]) -> tuple[dict[str, str] | None, dict[str, str] | None]:
    base = normalize_special_base(normalize_words(normalize_spaces(row["base_food"])))
    variant = normalize_spaces(row.get("variant", ""))
    form = normalize_spaces(row.get("form", ""))
    state = normalize_spaces(row.get("state", ""))
    reasons: list[str] = []

    for bad_prefix, fixed_prefix in OCR_PREFIX_FIXES.items():
        if base.startswith(bad_prefix):
            base = fixed_prefix + base[len(bad_prefix) :]
            reasons.append("ocr_prefix_fix")
            break

    if not base:
        review = dict(row)
        review["codex_reason"] = "blank_base"
        return None, review

    if base in NON_FOOD_EXACT or base in NONFOOD_EXACT:
        review = dict(row)
        review["codex_reason"] = "non_food"
        return None, review

    if likely_section_header(base):
        review = dict(row)
        review["codex_reason"] = "section_header"
        return None, review

    if base.startswith("a "):
        base = base[len("a ") :].strip()
        reasons.append("stripped_article_prefix")

    # Collapse duplicate trailing words like "carrot carrot"
    parts = base.split()
    if len(parts) >= 2 and parts[-1] == parts[-2]:
        base = " ".join(parts[:-1])
        reasons.append("collapsed_duplicate_word")

    if base.startswith("additional "):
        base = base[len("additional ") :].strip()
        reasons.append("stripped_additional")

    if base.startswith("and "):
        base = base[len("and ") :].strip()
        reasons.append("stripped_leading_and")

    if base.startswith("as needed "):
        base = base[len("as needed ") :].strip()
        reasons.append("stripped_as_needed_prefix")

    if base.startswith("ready to serve "):
        base = base[len("ready to serve ") :].strip()
        state = state or "ready-to-serve"
        reasons.append("moved_ready_to_serve_prefix")

    if base.startswith("bar "):
        base = base[len("bar ") :].strip()
        reasons.append("stripped_bar_prefix")

    if base.startswith("big slice "):
        base = base[len("big slice ") :].strip()
        reasons.append("stripped_size_prefix")

    if base.startswith("bite-size "):
        base = base[len("bite-size ") :].strip()
        reasons.append("stripped_size_prefix")

    if base.startswith("bite size "):
        base = base[len("bite size ") :].strip()
        reasons.append("stripped_size_prefix")

    if base.startswith("whole ") and ("(peeled" in row["base_food"].lower() or "-peeled" in row["base_food"].lower()):
        base = base[len("whole ") :].strip()
        state = state or "peeled"
        reasons.append("stripped_whole_prefix")

    if base.startswith("whole peeled "):
        base = base[len("whole peeled ") :].strip()
        state = state or "peeled"
        reasons.append("stripped_whole_prefix")

    if base.startswith("unpeeled "):
        base = base[len("unpeeled ") :].strip()
        state = state or "unpeeled"
        reasons.append("moved_state_prefix")

    if base.startswith("garnish: "):
        base = base[len("garnish: ") :].strip()
        reasons.append("stripped_garnish_label")

    if base in {"garnish", "garnishes", "optional", "optional topping", "optional garnish", "optional addition", "optional toppings", "optional glaze", "optional additions"}:
        review = dict(row)
        review["codex_reason"] = "context_only"
        return None, review

    base, packaging_changed = strip_prefixes(base, PACKAGING_PREFIXES)
    if packaging_changed:
        reasons.append("stripped_packaging")

    base, noise_changed = strip_prefixes(base, NOISE_PREFIXES)
    if noise_changed:
        reasons.append("stripped_noise_prefix")

    if base in EXACT_BASE_MAP:
        base = EXACT_BASE_MAP[base]
        reasons.append("exact_base_map")

    if base.startswith("aluminum-free "):
        base = base[len("aluminum-free ") :].strip()
        variant = variant or "aluminum-free"
        reasons.append("moved_aluminum_free")

    if re.search(r"\bhalf and half\b", base):
        base = "half-and-half"
        reasons.append("normalized_half_and_half")

    if " with a touch of philadelphia" in base:
        base = base.replace(" with a touch of philadelphia", "").strip()
        reasons.append("stripped_marketing_suffix")

    if "miracle whip" in base:
        base = "salad dressing"
        reasons.append("brand_to_generic")
        if "fat-free" in row["base_food"].lower() or "fat free" in row["base_food"].lower():
            variant = variant or "fat-free"
        elif "light" in row["base_food"].lower() or "lite" in row["base_food"].lower():
            variant = variant or "light"
    elif base.startswith("kraft "):
        base = base[len("kraft ") :].strip()
        reasons.append("stripped_kraft_brand")
    elif any(base.startswith(prefix) for prefix in LEADING_BRANDS):
        for prefix in LEADING_BRANDS:
            if base.startswith(prefix):
                stripped = base[len(prefix) :].strip()
                if stripped:
                    base = stripped
                    reasons.append("stripped_brand_prefix")
                break

    base, packaging_changed = strip_prefixes(base, PACKAGING_PREFIXES)
    if packaging_changed:
        reasons.append("stripped_packaging_after_brand")

    base, noise_changed = strip_prefixes(base, NOISE_PREFIXES)
    if noise_changed:
        reasons.append("stripped_noise_prefix_after_brand")

    if base.startswith("bar "):
        base = base[len("bar ") :].strip()
        reasons.append("stripped_bar_prefix")

    if base.startswith("big slice "):
        base = base[len("big slice ") :].strip()
        reasons.append("stripped_size_prefix")

    if base.startswith("bite-size "):
        base = base[len("bite-size ") :].strip()
        reasons.append("stripped_size_prefix")

    lowered_source = row["base_food"].lower()
    if "cool whip" in base:
        base = "whipped topping"
        reasons.append("brand_to_generic")
        if "fat-free" in lowered_source or "fat free" in lowered_source:
            variant = variant or "fat-free"
        elif "lite" in lowered_source or "light" in lowered_source:
            variant = variant or "light"
        if "thawed" in lowered_source:
            state = state or "thawed"
    elif "bisquick" in base:
        base = "baking mix"
        reasons.append("brand_to_generic")
        if "reduced-fat" in lowered_source or "reduced fat" in lowered_source:
            variant = variant or "reduced-fat"
        elif "heart smart" in lowered_source:
            variant = variant or "heart smart"
        elif "original" in lowered_source:
            variant = variant or "original"
    elif "philadelphia" in base and "cream cheese" in base:
        base = "cream cheese"
        reasons.append("brand_to_generic")
    elif "land o lakes" in base and "butter" in base:
        base = "butter"
        reasons.append("brand_to_generic")
    elif base == "eagle brand":
        review = dict(row)
        review["codex_reason"] = "brand_only"
        return None, review
    elif "eagle brand" in base and "milk" in base:
        base = "sweetened condensed milk"
        reasons.append("brand_to_generic")
        if "lowfat" in lowered_source or "low-fat" in lowered_source:
            variant = variant or "lowfat"
    elif "eagle brand" in base:
        review = dict(row)
        review["codex_reason"] = "brand_compound_unresolved"
        return None, review
    elif "lea and perrins" in base and "worcestershire sauce" in base:
        base = "worcestershire sauce"
        reasons.append("brand_to_generic")
    elif "taco bell" in base and "salsa" in base:
        base = "salsa"
        reasons.append("brand_to_generic")
    elif "maxwell house" in base and "coffee" in base:
        base = "coffee"
        reasons.append("brand_to_generic")
    elif "simply potatoes" in base and "hash brown" in base:
        base = "hash brown"
        reasons.append("brand_to_generic")
    elif "velveeta" in base:
        if "shells and cheese" in base or "dinner" in base:
            review = dict(row)
            review["codex_reason"] = "brand_prepared_dish"
            return None, review
        base = "processed cheese"
        reasons.append("brand_to_generic")
    elif re.search(r"\brotel\b", base):
        review = dict(row)
        review["codex_reason"] = "brand_compound_unresolved"
        return None, review
    elif "m and m" in base:
        review = dict(row)
        review["codex_reason"] = "brand_candy_unresolved"
        return None, review

    for pattern in JUICE_PATTERNS:
        match = pattern.match(base)
        if match:
            base = match.group(1)
            if not form:
                form = "juice"
            reasons.append("juice_pattern")
            break

    for pattern in ZEST_PATTERNS:
        match = pattern.match(base)
        if match:
            base = match.group(1)
            if not form:
                form = "zest"
            reasons.append("zest_pattern")
            break

    for pattern, replacement in TRAILING_CONTEXT_PATTERNS:
        if pattern.search(base):
            base = pattern.sub(replacement, base).strip()
            reasons.append("stripped_trailing_context")

    for pattern, replacement in TRAILING_CONTEXT_PATTERNS:
        updated = pattern.sub(replacement, base)
        if updated != base:
            base = updated.strip()
            reasons.append("stripped_context_suffix")

    if " prefer " in base:
        base = base.split(" prefer ", 1)[0].strip()
        reasons.append("stripped_commentary_suffix")

    if base.endswith(" if possible"):
        base = base[: -len(" if possible")].strip()
        reasons.append("stripped_commentary_suffix")

    if base.endswith(" if desired"):
        base = base[: -len(" if desired")].strip()
        reasons.append("stripped_commentary_suffix")

    if base.startswith("optional "):
        base = base[len("optional ") :].strip()
        reasons.append("stripped_optional_prefix")

    for adverb in LEADING_ADVERBS:
        if base.startswith(adverb):
            base = base[len(adverb) :].strip()
            reasons.append("stripped_leading_adverb")
            break

    if base.endswith(" unsweetened"):
        base = base[: -len(" unsweetened")].strip()
        variant = variant or "unsweetened"
        reasons.append("moved_quality_suffix")
        if base.endswith(" to taste"):
            base = base[: -len(" to taste")].strip()
            reasons.append("stripped_to_taste")

    for prefix, mapped_state in STATE_PREFIXES.items():
        if base.startswith(prefix + " "):
            base = base[len(prefix) + 1 :].strip()
            if not state:
                state = mapped_state
            reasons.append("moved_state_prefix")
            break

    for prefix, mapped_form in PREP_PREFIXES_TO_FORM.items():
        if base.startswith(prefix + " "):
            base = base[len(prefix) + 1 :].strip()
            if not form:
                form = mapped_form
            reasons.append("moved_prep_prefix")
            break

    for prefix in PREP_PREFIXES_TO_DROP:
        if base.startswith(prefix + " "):
            base = base[len(prefix) + 1 :].strip()
            reasons.append("stripped_prep_prefix")
            break

    if base.endswith(" peeled"):
        base = base[: -len(" peeled")].strip()
        state = state or "peeled"
        reasons.append("stripped_prep_suffix")

    if base.endswith(" drained"):
        base = base[: -len(" drained")].strip()
        state = state or "drained"
        reasons.append("stripped_prep_suffix")

    if base.endswith(" chopped"):
        base = base[: -len(" chopped")].strip()
        form = form or "chopped"
        reasons.append("moved_form_suffix")

    if base.endswith(" fresh") and base != "fresh":
        base = base[: -len(" fresh")].strip()
        state = state or "fresh"
        reasons.append("moved_state_suffix")

    if base.endswith(" freshly"):
        base = base[: -len(" freshly")].strip()
        state = state or "fresh"
        reasons.append("moved_state_suffix")

    if base.endswith(" freshly ground"):
        base = base[: -len(" freshly ground")].strip()
        form = form or "ground"
        state = state or "fresh"
        reasons.append("moved_freshly_ground_suffix")

    if base.endswith(" cracked"):
        base = base[: -len(" cracked")].strip()
        form = form or "cracked"
        reasons.append("moved_form_suffix")

    if base.endswith(" coarsely"):
        base = base[: -len(" coarsely")].strip()
        form = form or "coarse"
        reasons.append("moved_form_suffix")

    for suffix, mapped_form in (
        (" cubes", "cube"),
        (" cube", "cube"),
        (" granules", "granule"),
        (" granule", "granule"),
        (" powder", "powder"),
        (" crumbs", "crumb"),
        (" crumb", "crumb"),
        (" slices", "slice"),
        (" slice", "slice"),
    ):
        if base in PROTECTED_FORM_SUFFIX_BASES:
            break
        if base.endswith(suffix):
            base = base[: -len(suffix)].strip()
            form = form or mapped_form
            reasons.append("moved_form_suffix")
            break

    if base.endswith(" consomm"):
        base = base[: -len(" consomm")].strip() + " consomme"
        reasons.append("normalized_consomme")

    bouillon_match = re.match(r"^(.* bouillon) cubes?(?: low sodium)?$", base)
    if bouillon_match:
        base = bouillon_match.group(1).strip()
        form = form or "cube"
        if "low sodium" in row["base_food"].lower():
            variant = variant or "low-sodium"
        reasons.append("normalized_bouillon_cube")

    bouillon_match = re.match(r"^(.* bouillon) granules?$", base)
    if bouillon_match:
        base = bouillon_match.group(1).strip()
        form = form or "granules"
        reasons.append("normalized_bouillon_granules")

    bouillon_match = re.match(r"^(.* bouillon) powder$", base)
    if bouillon_match:
        base = bouillon_match.group(1).strip()
        form = form or "powder"
        reasons.append("normalized_bouillon_powder")

    if base.endswith(" consomme") or " consomme " in base:
        base = re.sub(r"\bconsomm(?:e|é)\b", "consomme", base)
        reasons.append("normalized_consomme")

    if base.endswith(" cheese slice"):
        base = base[: -len(" slice")].strip()
        form = "slice"
        reasons.append("normalized_cheese_slice")

    pudding_match = re.match(r"^jello (.+?) (?:flavor )?instant pudding$", base)
    if pudding_match:
        base = "instant pudding"
        variant = variant or pudding_match.group(1).strip()
        reasons.append("normalized_jello_pudding")
    elif base == "jello":
        base = "gelatin dessert"
        reasons.append("normalized_jello")
    else:
        jello_match = re.match(r"^(.+?) jello(?: gelatin dessert)?$", base)
        if jello_match:
            base = "gelatin dessert"
            variant = variant or jello_match.group(1).strip()
            reasons.append("normalized_jello")
        else:
            jello_match = re.match(r"^(.+?) (?:flavored )?jello(?: (?:gelatin|jelly|mix))?$", base)
            if jello_match:
                base = "gelatin dessert"
                variant = variant or jello_match.group(1).strip()
                reasons.append("normalized_jello")
            elif base.startswith("jello "):
                if "cheesecake dessert" in base or "no bake" in base:
                    review = dict(row)
                    review["codex_reason"] = "brand_prepared_dessert"
                    return None, review
                stripped = re.sub(r"^jello\s+", "", base)
                stripped = re.sub(r"\b(?:flavor|gelatin|jelly|mix|sugar free)\b", "", stripped).strip()
                base = "gelatin dessert"
                variant = variant or stripped
                reasons.append("normalized_jello")

    if "ritz cracker" in base:
        if "crumb" in base:
            base = "cracker crumb"
        else:
            base = "cracker"
        reasons.append("normalized_ritz")

    base, packaging_changed = strip_prefixes(base, PACKAGING_PREFIXES)
    if packaging_changed:
        reasons.append("stripped_packaging_late")

    base, noise_changed = strip_prefixes(base, NOISE_PREFIXES)
    if noise_changed:
        reasons.append("stripped_noise_prefix_late")

    for temp_prefix in ("hot", "cold", "warm"):
        if base.startswith(temp_prefix + " "):
            candidate = base[len(temp_prefix) + 1 :].strip()
            if candidate in TEMP_STRIPPABLE_BASES or candidate.endswith(" milk") or candidate.endswith(" water"):
                base = candidate
                reasons.append("stripped_temp_prefix")
            break

    if base.startswith("extra virgin "):
        base = base[len("extra virgin ") :].strip()
        variant = variant or "extra virgin"
        reasons.append("moved_extra_virgin")

    if base.startswith("extra-virgin "):
        base = base[len("extra-virgin ") :].strip()
        variant = variant or "extra virgin"
        reasons.append("moved_extra_virgin")

    if not variant:
        for fat_prefix, mapped_variant in FAT_VARIANT_PREFIXES.items():
            if base.startswith(fat_prefix + " ") and len(base.split()) > 1:
                base = base[len(fat_prefix) + 1 :].strip()
                variant = mapped_variant
                reasons.append("moved_fat_variant_prefix")
                break

    if not variant:
        for color in COLOR_VARIANTS | SIZE_VARIANTS:
            if base.startswith(color + " ") and len(base.split()) > 1:
                base = base[len(color) + 1 :].strip()
                variant = color
                reasons.append("moved_variant_prefix")
                break

    if base.startswith("ground ") and not form:
        base = base[len("ground ") :].strip()
        form = "ground"
        reasons.append("moved_ground_prefix")

    if base.startswith("sun-dried "):
        base = base[len("sun-dried ") :].strip()
        state = state or "dried"
        variant = variant or "sun-dried"
        reasons.append("moved_sun_dried")

    base = normalize_words(normalize_spaces(base))
    variant = normalize_words(normalize_spaces(variant))
    form = normalize_words(normalize_spaces(form))
    state = normalize_words(normalize_spaces(state))

    if base in NON_FOOD_EXACT or base in NONFOOD_EXACT:
        review = dict(row)
        review["codex_reason"] = "|".join(reasons + ["non_food"])
        return None, review

    if not base or likely_section_header(base):
        review = dict(row)
        review["codex_reason"] = "|".join(reasons or ["unsalvageable"])
        return None, review

    if base in {"ingredients", "remaining ingredients", "for decorating", "for garnish"}:
        review = dict(row)
        review["codex_reason"] = "|".join(reasons + ["header_or_context"])
        return None, review

    poison_findings = poison_findings_for_base(base)
    if any(finding.severity == "P0" for finding in poison_findings):
        review = dict(row)
        review["codex_reason"] = "|".join(reasons + [finding.issue for finding in poison_findings])
        return None, review

    if base == "optional":
        review = dict(row)
        review["codex_reason"] = "|".join(reasons + ["context_only"])
        return None, review

    if re.search(r"\d", base) or "$" in base or "thru" in base:
        review = dict(row)
        review["codex_reason"] = "|".join(reasons + ["numeric_or_ad_leak"])
        return None, review

    if re.match(r"^-\w+", base):
        review = dict(row)
        review["codex_reason"] = "|".join(reasons + ["measurement_fragment"])
        return None, review

    if base in {"garnish", "garnishe", "topping", "toppings", "addition", "additions"}:
        review = dict(row)
        review["codex_reason"] = "|".join(reasons + ["context_only"])
        return None, review

    if "salt" in base and "pepper" in base and ("oil" in base or "olive oil" in base):
        review = dict(row)
        review["codex_reason"] = "|".join(reasons + ["composite_phrase"])
        return None, review

    if "reg;" in base:
        review = dict(row)
        review["codex_reason"] = "|".join(reasons + ["html_entity_leak"])
        return None, review

    if "grnd" in base:
        review = dict(row)
        review["codex_reason"] = "|".join(reasons + ["parser_fragment"])
        return None, review

    if base in {"kraft"}:
        review = dict(row)
        review["codex_reason"] = "|".join(reasons + ["brand_only"])
        return None, review

    if base.endswith((" and", " or", " of", " with")):
        review = dict(row)
        review["codex_reason"] = "|".join(reasons + ["dangling_suffix"])
        return None, review

    if " and " in base and base not in ALLOWED_AND_BASES:
        review = dict(row)
        review["codex_reason"] = "|".join(reasons + ["composite_and"])
        return None, review

    if form and (base == form or base.endswith(" " + form)):
        form = ""
        reasons.append("blanked_redundant_form")

    if base == "half-and-half" and form == "cream":
        form = ""
        reasons.append("blanked_half_and_half_cream")

    if variant and (base == variant or base.startswith(variant + " ") or base.endswith(" " + variant)):
        variant = ""
        reasons.append("blanked_redundant_variant")

    if state and (base == state or base.startswith(state + " ") or base.endswith(" " + state)):
        state = ""
        reasons.append("blanked_redundant_state")

    cleaned = {
        "base_food": base,
        "variant": variant,
        "form": form,
        "state": state,
        "total_recipes": row["total_recipes"],
        "surface_count": row["surface_count"],
        "example_surfaces": row["example_surfaces"],
        "codex_fix_notes": "|".join(reasons),
    }
    return cleaned, None


def main() -> None:
    aggregated: dict[tuple[str, str, str, str], dict[str, object]] = {}
    review_rows: list[dict[str, str]] = []

    with INPUT_CSV.open(newline="") as handle:
        for row in csv.DictReader(handle):
            cleaned, review = clean_row(row)
            if review is not None:
                review_rows.append(review)
                continue

            assert cleaned is not None
            key = (
                cleaned["base_food"],
                cleaned["variant"],
                cleaned["form"],
                cleaned["state"],
            )
            total = int(cleaned["total_recipes"])
            surfaces = int(cleaned["surface_count"])
            examples = [part.strip() for part in cleaned["example_surfaces"].split(";") if part.strip()]

            if key not in aggregated:
                aggregated[key] = {
                    "base_food": cleaned["base_food"],
                    "variant": cleaned["variant"],
                    "form": cleaned["form"],
                    "state": cleaned["state"],
                    "total_recipes": 0,
                    "surface_count": 0,
                    "examples": [],
                    "fix_notes": set(),
                }
            target = aggregated[key]
            target["total_recipes"] += total
            target["surface_count"] += surfaces
            target["fix_notes"].update(filter(None, cleaned["codex_fix_notes"].split("|")))
            for example in examples:
                if example not in target["examples"]:
                    target["examples"].append(example)
                    if len(target["examples"]) >= 5:
                        break

    clean_rows = sorted(
        aggregated.values(),
        key=lambda row: int(row["total_recipes"]),
        reverse=True,
    )

    with OUTPUT_CSV.open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "base_food",
                "variant",
                "form",
                "state",
                "total_recipes",
                "surface_count",
                "example_surfaces",
                "codex_fix_notes",
            ],
        )
        writer.writeheader()
        for row in clean_rows:
            writer.writerow(
                {
                    "base_food": row["base_food"],
                    "variant": row["variant"],
                    "form": row["form"],
                    "state": row["state"],
                    "total_recipes": row["total_recipes"],
                    "surface_count": row["surface_count"],
                    "example_surfaces": "; ".join(row["examples"]),
                    "codex_fix_notes": "|".join(sorted(row["fix_notes"])),
                }
            )

    with REVIEW_CSV.open("w", newline="") as handle:
        fieldnames = list(review_rows[0].keys()) + ["codex_reason"] if review_rows else ["codex_reason"]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in review_rows:
            writer.writerow(row)

    report = f"""# Codex Base Dictionary Build

Source: `{INPUT_CSV}`

Outputs:
- `{OUTPUT_CSV}`
- `{REVIEW_CSV}`

## Counts

- Source rows: `{sum(1 for _ in csv.DictReader(INPUT_CSV.open(newline=''))):,}`
- Clean rows: `{len(clean_rows):,}`
- Review rows dropped: `{len(review_rows):,}`

## What This Build Does

- keeps valid food concepts from `FINAL`
- strips packaging prefixes when the underlying food is obvious
- strips section/header junk
- moves simple state prefixes like `fresh` and `dried` into `state`
- moves simple prep prefixes like `ground` and `mashed` into `form`
- blanks redundant `form` / `variant` / `state` echoes instead of deleting the row
- normalizes obvious brand rows when the underlying food is clear
"""
    REPORT_MD.write_text(report)

    print(OUTPUT_CSV)
    print(REVIEW_CSV)
    print(REPORT_MD)


if __name__ == "__main__":
    main()
