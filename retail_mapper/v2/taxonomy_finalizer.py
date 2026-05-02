#!/usr/bin/env python3
"""Authoritative retail taxonomy finalizer.

This module owns the final path contract used by the v2 retail corpus:

  category_path_fixed: retail category/family only
  product_identity_fixed: normalized product identity only
  canonical_path: category_path_fixed + product_identity_fixed
  modifier: derived once from structured facets
  retail_leaf_path: canonical_path + modifier

Facet values never belong in canonical_path. FNDDS/SR28/ESHA are reference
matches, not retail taxonomy truth.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable, Mapping


PATH_SEP = " > "


@dataclass(frozen=True)
class FinalizedTaxonomy:
    category_path_fixed: str
    product_identity_fixed: str
    canonical_path: str
    modifier: str
    retail_leaf_path: str


PLAIN_TOKENS = {
    "plain", "regular", "original", "classic", "natural",
    "unflavored", "unscented", "neutral",
    "enriched", "unenriched",
    "artisan", "rustic", "country", "homestyle", "traditional",
    "gourmet", "bakery", "style", "authentic", "old", "fashioned",
    "premium", "deluxe", "fancy", "handcrafted", "signature", "select",
}

CLAIM_ALIASES = {
    "lowfat": "low_fat",
    "low_fat": "low_fat",
    "fatfree": "fat_free",
    "fat_free": "fat_free",
    "nonfat": "fat_free",
    "non_fat": "fat_free",
    "skim": "fat_free",
    "reduced_fat": "reduced_fat",
    "lite": "light",
    "zero_sugar": "sugar_free",
    "0_sugar": "sugar_free",
    "sugarfree": "sugar_free",
    "sugar_free": "sugar_free",
    "no_sugar_added": "no_sugar_added",
    "unsweetened": "unsweetened",
    "sweetened": "sweetened",
    "low_sodium": "low_sodium",
    "reduced_sodium": "reduced_sodium",
    "less_sodium": "reduced_sodium",
    "no_salt_added": "no_salt_added",
    "decaf": "decaf",
    "decaffeinated": "decaf",
    "caffeine_free": "caffeine_free",
    "gluten_free": "gluten_free",
    "organic": "organic",
    "keto": "keto",
    "paleo": "paleo",
    "whole_grain": "whole_grain",
    "whole_wheat": "whole_wheat",
    # Additional claims commonly populated by DeepSeek that need to be
    # preserved in the modifier path.
    "fortified": "fortified",
    "vitamin_d": "vitamin_d",
    "vitamin_d_added": "vitamin_d",
    "high_protein": "high_protein",
    "high_fiber": "high_fiber",
    "low_carb": "low_carb",
    "kosher": "kosher",
    "halal": "halal",
    "vegan": "vegan",
    "vegetarian": "vegetarian",
    "plant_based": "plant_based",
    "non_gmo": "non_gmo",
    "no_preservatives": "no_preservatives",
    "no_artificial_flavors": "no_artificial_flavors",
    "lactose_free": "lactose_free",
    "non_dairy": "non_dairy",
    "probiotic": "probiotic",
    "grass_fed": "grass_fed",
    "free_range": "free_range",
    "cage_free": "cage_free",
    "wild_caught": "wild_caught",
    "fair_trade": "fair_trade",
    "no_hfcs": "no_hfcs",
    "shelf_stable": "shelf_stable",
    "cold_pressed": "cold_pressed",
    "all_natural": "all_natural",
}

# "Sweetened" is usually the unmarked/default state in retail data and is
# often inferred when a title merely lacks "unsweetened". Do not create a
# retail leaf for it; keep explicit negative claims like Unsweetened.
RELEVANT_CLAIMS = set(CLAIM_ALIASES.values()) - {"sweetened"}

FORM_ALIASES = {
    "pre_sliced": "sliced",
    "sliced": "sliced",
    "stuffed": "stuffed",
    "filled": "filled",
    "topped": "topped",
    "split": "split",
    "twisted": "twisted",
    "layered": "layered",
    "rolled": "rolled",
    "frosted": "frosted",
    "glazed": "glazed",
    "shredded": "shredded",
    "grated": "grated",
    "diced": "diced",
    "chopped": "chopped",
    "crumbled": "crumbled",
    "cubed": "cubed",
}

COMPOUND_TOKENS = {
    "barista_style",
    "black_cherry",
    "brown_rice",
    "brown_sugar",
    "butter_garlic",
    "cheddar_jack",
    "chocolate_chip",
    "cinnamon_raisin",
    "cinnamon_roll",
    "cinnamon_sugar",
    "dark_chocolate",
    "french_vanilla",
    "ginger_ale",
    "gluten_free",
    "green_tea",
    "hot_dog",
    "low_fat",
    "low_sodium",
    "macaroni_cheese",
    "milk_chocolate",
    "no_salt_added",
    "no_sugar_added",
    "peanut_butter",
    "reduced_fat",
    "reduced_sodium",
    "sour_cream",
    "sugar_free",
    "white_chocolate",
    "whole_grain",
    "whole_wheat",
}

PROTECTED_FLAVOR_TOKENS = {
    "dark_chocolate",
    "milk_chocolate",
    "white_chocolate",
    "peanut_butter",
    "almond_butter",
    "chocolate_chip",
}

CLAIM_ORDER = [
    "organic", "gluten_free", "whole_grain", "whole_wheat",
    "unsweetened", "no_sugar_added", "sugar_free", "sweetened",
    "low_fat", "fat_free", "reduced_fat", "light",
    "low_sodium", "reduced_sodium", "no_salt_added",
    "decaf", "caffeine_free", "keto", "paleo",
]

PLANT_MILK_TYPES = [
    ("macadamia", "Macadamia Milk"),
    ("hazelnut", "Hazelnut Milk"),
    ("pistachio", "Pistachio Milk"),
    ("almond", "Almond Milk"),
    ("cashew", "Cashew Milk"),
    ("coconut", "Coconut Milk"),
    ("peanut", "Peanut Milk"),
    ("soy", "Soy Milk"),
    ("oat", "Oat Milk"),
    ("rice", "Rice Milk"),
    ("hemp", "Hemp Milk"),
    ("flax", "Flax Milk"),
    ("pea", "Pea Milk"),
]

NUT_BUTTER_TYPES = [
    ("peanut", "Peanut Butter"),
    ("almond", "Almond Butter"),
    ("cashew", "Cashew Butter"),
    ("sunflower", "Sunflower Seed Butter"),
    ("hazelnut", "Hazelnut Butter"),
    ("tahini", "Tahini"),
]

SEAFOOD_TYPES = [
    ("mahi mahi", "Mahi Mahi"),
    ("swordfish", "Swordfish"),
    ("tilapia", "Tilapia"),
    ("catfish", "Catfish"),
    ("halibut", "Halibut"),
    ("salmon", "Salmon"),
    ("tuna", "Tuna"),
    ("hake", "Hake"),
    ("swai", "Swai"),
    ("cod", "Cod"),
    ("shrimp", "Shrimp"),
    ("squid", "Squid"),
    ("conch", "Conch"),
    ("crab", "Crab"),
    ("lobster", "Lobster"),
    ("scallop", "Scallop"),
    ("clam", "Clam"),
    ("mussel", "Mussel"),
]

PREPARED_SANDWICH_BFCS = {
    "prepared subs & sandwiches",
    "sandwiches/filled rolls/wraps",
    "prepared sandwiches",
    "sandwiches",
}

PREPARED_WRAP_BFCS = {
    "prepared wraps and burittos",
    "prepared wraps and burritos",
    "wraps & burritos",
}

FROZEN_BREAKFAST_BFCS = {
    "frozen breakfast sandwiches, biscuits & meals",
}

BREAKFAST_SANDWICH_BFCS = {
    "breakfast sandwiches, biscuits & meals",
}

FROZEN_APPETIZER_BFCS = {
    "frozen appetizers & hors d'oeuvres",
}

FROZEN_MEAL_BFCS = {
    "frozen dinners & entrees",
}

PREPARED_MEAT_BFCS = {
    "meat/poultry/other animals  prepared/processed",
    "meat/poultry/other animals sausages  prepared/processed",
}

COOKIE_BFCS = {
    "cookies & biscuits",
    "biscuits/cookies",
    "biscuits/cookies (shelf stable)",
}

PRE_PACKAGED_PRODUCE_BFCS = {
    "pre-packaged fruit & vegetables",
}

BEAN_BFCS = {
    "canned & bottled beans",
    "vegetable and lentil mixes",
    "vegetables  prepared/processed",
    "vegetables - prepared/processed",
    "vegetables  unprepared/unprocessed (shelf stable)",
}

ABBREVIATIONS = {
    "bbq": "BBQ",
    "pb&j": "PB&J",
    "nfs": "NFS",
    "nsa": "NSA",
}


def split_path(path: str) -> list[str]:
    return [p.strip() for p in re.split(r"\s*>\s*", path or "") if p.strip()]


def normalize_path(path: str) -> str:
    return PATH_SEP.join(dedupe_segments(split_path(path)))


def _token_key(text: str) -> str:
    words = re.findall(r"[a-z0-9]+", (text or "").lower())
    stemmed = []
    for word in words:
        if len(word) > 3 and word.endswith("ies"):
            word = word[:-3] + "y"
        elif len(word) > 3 and word.endswith("s") and not word.endswith(("ss", "us", "is")):
            word = word[:-1]
        stemmed.append(word)
    return " ".join(stemmed)


def _word_set(text: str) -> set[str]:
    return set(_token_key(text).split())


def _phrase_key(text: str) -> str:
    return "_".join(_token_key(text).split())


def _prettify(token: str) -> str:
    raw = (token or "").replace("-", "_").replace(" ", "_").strip("_")
    if not raw:
        return ""
    low = raw.lower()
    if low in ABBREVIATIONS:
        return ABBREVIATIONS[low]
    words = [w for w in raw.split("_") if w]
    return " ".join(ABBREVIATIONS.get(w.lower(), w.capitalize()) for w in words)


def _prettify_segment(segment: str) -> str:
    segment = re.sub(r"\s+", " ", (segment or "").strip())
    if not segment:
        return ""
    if any(c.islower() for c in segment[1:]):
        return segment
    return " ".join(_prettify(w) for w in re.split(r"\s+", segment))


def dedupe_segments(segments: Iterable[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in segments:
        seg = _prettify_segment(raw)
        key = _token_key(seg)
        if not seg or not key:
            continue
        if key in seen:
            continue
        seen.add(key)
        out.append(seg)
    return out


def _facet_values(value: str) -> list[str]:
    if not value:
        return []
    return [v.strip() for v in str(value).split("|") if v.strip()]


def _normalize_token(raw: str) -> str:
    token = re.sub(r"[^a-z0-9]+", "_", (raw or "").lower()).strip("_")
    token = re.sub(r"\bblack_?eye(?:d)?\b", "black_eyed", token)
    # "1" / "2" as standalone tokens — DeepSeek extracted "1%"/"2%" milk fat
    # variants but stripped the % sign. Convert to canonical "1_percent"/"2_percent".
    if token in ("1", "2"):
        token = f"{token}_percent"
    return CLAIM_ALIASES.get(token, FORM_ALIASES.get(token, token))


def _expand_token(raw: str) -> list[str]:
    token = _normalize_token(raw)
    if not token:
        return []
    if token in COMPOUND_TOKENS or token in CLAIM_ALIASES or token in FORM_ALIASES:
        return [CLAIM_ALIASES.get(token, FORM_ALIASES.get(token, token))]
    parts = [p for p in token.split("_") if p]
    out: list[str] = []
    i = 0
    while i < len(parts):
        matched = ""
        matched_len = 0
        for n in range(min(4, len(parts) - i), 0, -1):
            candidate = "_".join(parts[i:i + n])
            canonical = CLAIM_ALIASES.get(candidate, FORM_ALIASES.get(candidate, candidate))
            if candidate in COMPOUND_TOKENS or candidate in CLAIM_ALIASES or candidate in FORM_ALIASES:
                matched = canonical
                matched_len = n
                break
        if matched:
            out.append(matched)
            i += matched_len
        else:
            out.append(parts[i])
            i += 1
    return out


def _ordered_unique(tokens: Iterable[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        norm = _normalize_token(token)
        key = _phrase_key(norm)
        if not norm or key in seen:
            continue
        seen.add(key)
        out.append(norm)
    return out


def _identity_echo(token: str, identity: str, canonical_segments: Iterable[str]) -> bool:
    if token in PROTECTED_FLAVOR_TOKENS:
        return False
    token_words = _word_set(token)
    if not token_words:
        return True
    segment_keys = {_token_key(seg) for seg in canonical_segments if seg}
    if _token_key(token) in segment_keys:
        return True
    identity_words = _word_set(identity)
    if identity_words and token_words.issubset(identity_words):
        return True
    path_words = set()
    for seg in canonical_segments:
        path_words.update(_word_set(seg))
    return token_words.issubset(path_words)


def _claim_sort(tokens: Iterable[str]) -> list[str]:
    order = {token: i for i, token in enumerate(CLAIM_ORDER)}
    return sorted(_ordered_unique(tokens), key=lambda t: (order.get(t, 999), t))


def derive_modifier(
    *,
    variant: str = "",
    flavor: str = "",
    claims: str = "",
    form: str = "",
    identity: str = "",
    canonical_path: str = "",
) -> str:
    canonical_segments = split_path(canonical_path)
    l1: list[str] = []
    l2: list[str] = []
    l3: list[str] = []

    for raw in _facet_values(variant) + _facet_values(flavor):
        for token in _expand_token(raw):
            if token in PLAIN_TOKENS:
                continue
            if token in RELEVANT_CLAIMS:
                l2.append(token)
            elif token in FORM_ALIASES.values():
                l3.append(token)
            else:
                l1.append(token)

    for raw in _facet_values(claims):
        for token in _expand_token(raw):
            if token in RELEVANT_CLAIMS:
                l2.append(token)

    for raw in _facet_values(form):
        for token in _expand_token(raw):
            if token in FORM_ALIASES.values():
                l3.append(token)

    levels: list[str] = []
    used: set[str] = set()

    def add_level(tokens: list[str], *, sort_claims: bool = False, one_segment_per_token: bool = False) -> None:
        nonlocal levels, used
        ordered = _claim_sort(tokens) if sort_claims else _ordered_unique(tokens)
        kept: list[str] = []
        for token in ordered:
            key = _phrase_key(token)
            if key in used:
                continue
            if _identity_echo(token, identity, canonical_segments):
                continue
            used.add(key)
            kept.append(token)
        if kept:
            if one_segment_per_token:
                # Each claim/form gets its OWN path segment so they stack
                # cleanly: "Organic > Fat Free" not "Organic Fat Free".
                for token in kept:
                    levels.append(_prettify(token))
            else:
                # Variant/flavor tokens compose into one descriptive segment
                # (e.g., "Date Chia Almond" stays as one leaf).
                levels.append(" ".join(_prettify(token) for token in kept))

    add_level(l1)
    add_level(l2, sort_claims=True, one_segment_per_token=True)
    add_level(l3, one_segment_per_token=True)
    return PATH_SEP.join(levels) if levels else "Plain"


def _title_blob(row: Mapping[str, str]) -> str:
    return " ".join([
        row.get("title", "") or "",
        row.get("branded_food_category", "") or "",
        row.get("product_identity_fixed", "") or "",
        row.get("canonical_path", "") or "",
    ]).lower()


def _detect_plant_milk_identity(text: str) -> str:
    compact = re.sub(r"[^a-z0-9]+", "", text.lower())
    for key, identity in PLANT_MILK_TYPES:
        if f"{key}milk" in compact or f"{key}mylk" in compact:
            return identity
        if re.search(rf"\b{re.escape(key)}\s+(?:milk|mylk|beverage|drink)\b", text, re.I):
            return identity
        if key == "peanut" and re.search(r"\bmilked\s+peanuts?\b", text, re.I):
            return identity
    return "Plant Milk"


def _looks_like_prepared_sandwich(title: str) -> bool:
    if re.search(
        r"\b(?:sandwich\s+cookies?|cookie\s+sandwich(?:es)?|cracker\s+sandwich(?:es)?|"
        r"ice\s+cream\s+sandwich(?:es)?)\b",
        title or "",
        re.I,
    ):
        return False
    return bool(re.search(
        r"\b(sandwich|sub|hoagie|hero|panini|sliders?|burger|cheeseburger|"
        r"hamburger|hot\s*dog|frank(?:furter)?|gyro|banh\s*mi|on\s+(?:a\s+)?"
        r"(?:white\s+|wheat\s+|whole\s+grain\s+|sesame\s+|hoagie\s+|pretzel\s+)?"
        r"(?:bun|roll|hoagie|sub)|on\s+(?:a\s+)?[a-z\\s-]{0,40}\\b(?:bun|roll)|"
        r"with\s+(?:a\s+)?bun)\b",
        title or "",
        re.I,
    ))


def _sandwich_identity(title: str) -> str:
    t = title or ""
    if re.search(r"\bbanh\s*mi\b", t, re.I):
        return "Banh Mi Sandwich"
    if re.search(r"\bgyro\b", t, re.I):
        return "Gyro Sandwich"
    if re.search(r"\bpanini\b", t, re.I):
        return "Panini"
    if re.search(r"\bwraps?\b", t, re.I):
        return "Wrap Sandwich"
    if re.search(r"\b(?:sub|hoagie|hero)s?\b", t, re.I):
        return "Sub Sandwich"
    if re.search(r"\bsliders?\b", t, re.I):
        return "Slider Sandwich"
    if re.search(r"\bcheeseburger\b", t, re.I):
        return "Cheeseburger"
    if re.search(r"\bhamburger\b|\bburger\b", t, re.I):
        return "Hamburger"
    if re.search(r"\bhot\s*dogs?\b|\bfranks?\b|\bfrankfurters?\b", t, re.I):
        return "Hot Dog"
    if re.search(r"\bbreakfast\s+sandwich\b", t, re.I):
        return "Breakfast Sandwich"
    if re.search(r"\bpita\b", t, re.I):
        return "Pita Sandwich"
    return "Sandwich"


def _appetizer_identity(title: str) -> str:
    t = title or ""
    if re.search(r"\begg\s+rolls?\b", t, re.I):
        return "Egg Rolls"
    if re.search(r"\bspring\s+rolls?\b", t, re.I):
        return "Spring Rolls"
    if re.search(r"\bpizza\s+rolls?\b", t, re.I):
        return "Pizza Rolls"
    if re.search(r"\b(?:sausage|pork|beef|chicken)\s+rolls?\b", t, re.I):
        return "Meat Rolls"
    if re.search(r"\b(?:bao|baozi|steamed|asian|bbq|barbecue|pork|teriyaki).*\bbuns?\b|\bbuns?.*(?:pork|teriyaki|bbq|barbecue)\b", t, re.I):
        return "Stuffed Buns"
    if _looks_like_prepared_sandwich(t):
        ident = _sandwich_identity(t)
        return "Sliders" if ident == "Slider Sandwich" else ident
    if re.search(r"\bbread\s*st(?:ick|ix)s?\b|\bbreadsticks?\b", t, re.I):
        return "Breadsticks"
    return "Appetizers"


def _prepared_meal_identity(title: str) -> str:
    t = title or ""
    if re.search(r"\bstuffed\s+cabbage\s+rolls?\b|\bcabbage\s+rolls?\b", t, re.I):
        return "Stuffed Cabbage"
    if re.search(r"\bpizza\s+rolls?\b", t, re.I):
        return "Pizza Rolls"
    if _looks_like_prepared_sandwich(t):
        return _sandwich_identity(t)
    return "Entree"


def _packaged_tortilla_identity(title: str, identity: str) -> str | None:
    evidence = f"{title or ''} {identity or ''}"
    if re.search(r"\btortilla\s+(?:chips?|strips?)\b|\b(?:chips?|strips?)\s+.*\btortillas?\b", evidence, re.I):
        return None
    if re.search(r"\btaco\s+salad\s+shells?\b|\btaco\s+shells?\b", evidence, re.I):
        return "Taco Shells"
    if re.search(r"\btostada\s+shells?\b", evidence, re.I):
        return "Tostada Shells"
    if re.search(r"\btostada\s+bowls?\b", evidence, re.I):
        return "Tostada Bowls"
    if re.search(r"\btostadas?\b", evidence, re.I):
        return "Tostadas"
    if re.search(r"\btortillas?\b|\btortilla\s+wraps?\b", evidence, re.I):
        return "Tortillas"
    return None


def _bean_legume_identity(title: str, identity: str) -> str | None:
    evidence = f"{title or ''} {identity or ''}"
    if re.search(r"\b(jelly\s+beans?|coffee\s+beans?|cocoa\s+beans?|vanilla\s+beans?)\b", evidence, re.I):
        return None

    candidates = [
        (r"\bblack[\s-]?(?:eyed|eye)\s+peas?\b|\bblackeye\s+peas?\b", "Black-Eyed Peas"),
        (r"\bsmall\s+red\s+beans?\b", "Small Red Beans"),
        (r"\bred\s+kidney\s+beans?\b|\bkidney\s+beans?\b", "Kidney Beans"),
        (r"\bgreat\s+northern\s+beans?\b", "Great Northern Beans"),
        (r"\bbaby\s+lima\s+beans?\b", "Baby Lima Beans"),
        (r"\blima\s+beans?\b", "Lima Beans"),
        (r"\bblack\s+beans?\b", "Black Beans"),
        (r"\bpinto\s+beans?\b", "Pinto Beans"),
        (r"\bnavy\s+beans?\b", "Navy Beans"),
        (r"\bgarbanzo\s+beans?\b|\bchickpeas?\b", "Garbanzo Beans"),
        (r"\bcannellini\s+beans?\b", "Cannellini Beans"),
        (r"\bcranberry\s+beans?\b", "Cranberry Beans"),
        (r"\bbutter\s+beans?\b", "Butter Beans"),
        (r"\badzuki\s+beans?\b", "Adzuki Beans"),
        (r"\bmung\s+beans?\b", "Mung Beans"),
        (r"\bfava\s+beans?\b", "Fava Beans"),
        (r"\bpink\s+beans?\b", "Pink Beans"),
        (r"\bsoy\s+beans?\b|\bsoybeans?\b", "Soy Beans"),
        (r"\bred\s+beans?\b", "Red Beans"),
        (r"\brefried\s+beans?\b", "Refried Beans"),
        (r"\bbaked\s+beans?\b", "Baked Beans"),
        (r"\bpork\s+and\s+beans?\b", "Pork and Beans"),
        (r"\bchili\s+beans?\b", "Chili Beans"),
        (r"\bred\s+lentils?\b", "Red Lentils"),
        (r"\bgreen\s+lentils?\b", "Green Lentils"),
        (r"\blentils?\b", "Lentils"),
        (r"\bsplit\s+peas?\b", "Split Peas"),
        (r"\bwhole\s+green\s+peas?\b|\bgreen\s+peas?\b", "Green Peas"),
        (r"\byellow\s+peas?\b", "Yellow Peas"),
        (r"\bfield\s+peas?\b", "Field Peas"),
        (r"\bcow\s*peas?\b|\bcowpeas?\b", "Cowpeas"),
        (r"\bedamame\b", "Edamame"),
        (r"\bchana\s+dal\b", "Chana Dal"),
    ]
    for pattern, label in candidates:
        if re.search(pattern, evidence, re.I):
            return label
    if re.search(r"\bbeans?\b", identity, re.I):
        return identity or "Beans"
    if re.search(r"\blentils?\b", identity, re.I):
        return identity or "Lentils"
    return None


def _mexican_prepared_identity(title: str, identity: str) -> str | None:
    evidence = f"{title or ''} {identity or ''}"
    if re.search(r"\bbreakfast\s+burritos?\b", evidence, re.I):
        return "Breakfast Burrito"
    if re.search(r"\bburritos?\b", evidence, re.I):
        return "Burrito"
    if re.search(r"\bchimichangas?\b", evidence, re.I):
        return "Chimichanga"
    if re.search(r"\benchiladas?\b", evidence, re.I):
        return "Enchiladas"
    if re.search(r"\btaquitos?\b", evidence, re.I):
        return "Taquitos"
    if re.search(r"\btamales?\b", evidence, re.I):
        if re.search(r"\bmasa\b|\bmix\b", evidence, re.I):
            return None
        return "Tamales"
    if re.search(r"\bpupusas?\b", evidence, re.I):
        return "Pupusas"
    if re.search(r"\bgorditas?\b", evidence, re.I):
        return "Gorditas"
    return None


def _packaged_potato_side_identity(title: str, identity: str) -> str | None:
    evidence = f"{title or ''} {identity or ''}"
    if re.search(
        r"\b(potato\s+(?:starch|flour)|potato\s+bread|potato\s+rolls?|"
        r"potato\s+buns?|potato\s+chips?)\b",
        evidence,
        re.I,
    ):
        return None
    if re.search(
        r"\b(au\s+gratin|scalloped|mashed|hash\s*browns?|potato\s+mix|"
        r"potato\s+(?:slices?|shreds?|flakes?|salad|casserole|kugel|dumpling)|potatoes?)\b",
        evidence,
        re.I,
    ) and re.search(
        r"\b(potatoes?|potato\s+(?:mix|shreds?|flakes?|salad|casserole|kugel|dumpling|slices?)|"
        r"scalloped\s+potatoes?\s+mix)\b",
        evidence,
        re.I,
    ):
        return "Potatoes"
    return None


def _gravy_identity(title: str, identity: str) -> str | None:
    evidence = f"{title or ''} {identity or ''}"
    if not re.search(r"\b(gravy|au\s+jus)\b", evidence, re.I):
        return None
    if re.search(r"\bbiscuits?\s+and\s+gravy\b", evidence, re.I):
        return "Biscuits and Gravy"
    if re.search(r"\bsausage\s+gravy\b", evidence, re.I):
        return "Sausage Gravy"
    if re.search(r"\bturkey\s+gravy\b", evidence, re.I):
        return "Turkey Gravy"
    if re.search(r"\b(beef|roast\s+beef)\s+gravy\b", evidence, re.I):
        return "Beef Gravy"
    if re.search(r"\bchicken\s+gravy\b", evidence, re.I):
        return "Chicken Gravy"
    if re.search(r"\bau\s+jus\b", evidence, re.I):
        return "Au Jus"
    if re.search(r"\b(country|cream|white)\s+gravy\b", evidence, re.I):
        return "Country Gravy"
    if re.search(r"\bgravy\s+mix\b|\bmix\b", evidence, re.I):
        return "Gravy Mix"
    return "Gravy"


def _meal_kit_identity(title: str, identity: str) -> str | None:
    evidence = f"{title or ''} {identity or ''}"
    if re.search(r"\bhamburger\s+helper\b", evidence, re.I):
        return "Hamburger Helper"
    if re.search(r"\bpasta\s+salad\s+mix\b|\bsuddenly\s+salad\b", evidence, re.I):
        return "Pasta Salad Mix"
    if re.search(r"\bfalafel\s+mix\b|\bfalafel\b", evidence, re.I):
        return "Falafel Mix"
    if re.search(r"\btaco\s+dinner\s+kit\b", evidence, re.I):
        return "Taco Dinner Kit"
    if re.search(r"\btaco\s+kit\b", evidence, re.I):
        return "Taco Kit"
    if re.search(r"\bdinner\s+kit\b", evidence, re.I):
        return "Dinner Kit"
    if re.search(r"\bmeal\s+starter\b", evidence, re.I):
        return "Meal Starter"
    if re.search(r"\bskillet\s+meal\b", evidence, re.I):
        return "Skillet Meal"
    if re.search(r"\bcasserole\s+mix\b|\bkugel\s+mix\b|\bmeat\s*loaf\s+mix\b|\bmeatloaf\s+mix\b", evidence, re.I):
        return identity or "Meal Kit"
    return None


def _coating_breading_identity(title: str, identity: str) -> str | None:
    evidence = f"{title or ''} {identity or ''}"
    if re.search(r"\bbreading(?:\s+(?:mix|substitute))?\b|\bseafood\s+breading\b", evidence, re.I):
        return "Breading Mix"
    if re.search(r"\bbread\s+coating\b|\bcoating\s+mix\b|\bseasoned\s+coating\b", evidence, re.I):
        return "Coating Mix"
    if re.search(r"\b(chicken|fish|seafood|tempura|fry)\s+batter\s+mix\b|\bbatter\s+mix\b", evidence, re.I):
        return "Batter Mix"
    return None


def _seaweed_identity(title: str, identity: str) -> str | None:
    evidence = f"{title or ''} {identity or ''}"
    if re.search(r"\bnori\b", evidence, re.I):
        return "Nori"
    if re.search(r"\bseaweed\s+snacks?\b", evidence, re.I):
        return "Seaweed Snacks"
    if re.search(r"\bseaweed\b", evidence, re.I):
        return "Seaweed"
    return None


def _grain_identity(title: str, identity: str) -> str | None:
    evidence = f"{title or ''} {identity or ''}"
    if re.search(r"\bpearl\s+barley\b", evidence, re.I):
        return "Pearl Barley"
    if re.search(r"\bbarley\b", evidence, re.I):
        return "Barley"
    if re.search(r"\bquinoa\b", evidence, re.I):
        return "Quinoa"
    return None


def _soup_identity(title: str, identity: str) -> str | None:
    evidence = f"{title or ''} {identity or ''}"
    if re.search(r"\bpea\s+soup\b", evidence, re.I):
        return "Pea Soup"
    if re.search(r"\bsoup\b", evidence, re.I):
        return identity if re.search(r"\bsoup\b", identity, re.I) else "Soup"
    return None


def _hot_cereal_identity(title: str, identity: str) -> str | None:
    evidence = f"{title or ''} {identity or ''}"
    if re.search(r"\boatmeal\s+mix(?:-ins?)?\b|\boatmeal\b", evidence, re.I):
        return "Oatmeal"
    return None


def _dessert_mix_identity(title: str, identity: str) -> str | None:
    evidence = f"{title or ''} {identity or ''}"
    if re.search(r"\bice\s+cream\s+mix\b", evidence, re.I):
        return "Ice Cream Mix"
    if re.search(r"\bpudding\b", evidence, re.I):
        return identity if re.search(r"\bpudding\b", identity, re.I) else "Pudding Mix"
    return None


def _ice_cream_cone_identity(title: str, identity: str) -> str | None:
    evidence = f"{title or ''} {identity or ''}"
    if re.search(
        r"\b(candy|lollipops?|marshmallows?|truffles?|protein\s+bars?|"
        r"chocolate\s+bars?|latte|gum|cone\s+coating|cone\s+pieces?)\b",
        evidence,
        re.I,
    ):
        return None
    if re.search(r"\bwaffle\s+cones?\b", evidence, re.I):
        return "Waffle Cones"
    if re.search(r"\bsugar[\s-]?free\s+cones?\b", evidence, re.I):
        return "Ice Cream Cone"
    if re.search(r"\bsugar\s+cones?\b", evidence, re.I):
        return "Sugar Cones"
    if re.search(r"\bcake\s+cones?\b|\bcones?\s+cake\b", evidence, re.I):
        return "Ice Cream Cone"
    if re.search(r"\bice\s+cream\s+(?:cones?|cups?|cake\s+cups?)\b", evidence, re.I):
        return "Ice Cream Cone"
    if _token_key(identity) in {"ice cream cone", "ice cream cones"}:
        return "Ice Cream Cone"
    return None


def _bakery_path_hijacked(category: str, canonical_path: str) -> bool:
    key = _token_key(category or canonical_path)
    return key.startswith((
        "bakery bun",
        "bakery roll",
        "bakery bread",
        "bakery breadstick",
    ))


def _forced_base(row: Mapping[str, str]) -> tuple[str, str] | None:
    title = row.get("title", "") or ""
    bfc = row.get("branded_food_category", "") or ""
    category = row.get("category_path_fixed", "") or ""
    identity = row.get("product_identity_fixed", "") or ""
    blob = _title_blob(row)
    bfc_lower = bfc.strip().lower()

    plant_context = (
        bfc_lower == "plant based milk"
        or _token_key(category).startswith("beverage plant milk")
        or _token_key(row.get("canonical_path", "") or "").startswith("beverage plant milk")
    )
    if plant_context:
        return "Beverage > Plant Milk", _detect_plant_milk_identity(title + " " + identity)

    identity_evidence = f"{title} {identity}"

    if re.search(r"\b(biscotti|biscottini|cantuccini|biscotificio)\b", identity_evidence, re.I):
        return "Bakery > Biscotti", "Biscotti"

    if bfc_lower in PRE_PACKAGED_PRODUCE_BFCS and re.search(r"\bsalad\s+kits?\b|\bchopped\s+kits?\b", title, re.I):
        return "Produce > Salad Kits", "Salad Kit"

    lunch_kit_context = (
        bfc_lower in {"lunch snacks & combinations", "prepared subs & sandwiches"}
        or _token_key(category).startswith("meal lunch kit")
        or _token_key(row.get("canonical_path", "") or "").startswith("meal lunch kit")
    )
    if lunch_kit_context and re.search(
        r"\b(lunch\s+kits?|snack\s+kits?|snack\s+on\s+the\s+run|cracker\s+stackers|"
        r"(?:tuna|chicken|turkey)\s+salad\s+kit(?:\s+with\s+crackers?)?)\b",
        title,
        re.I,
    ):
        return "Meal > Lunch Kits", "Lunch Kit"

    bean_identity = _bean_legume_identity(title, identity)
    if bean_identity and (
        bfc_lower in BEAN_BFCS
        or _token_key(category).startswith("pantry baking mix")
        or _token_key(row.get("canonical_path", "") or "").startswith("pantry baking mix")
    ):
        return "Pantry > Beans", bean_identity

    if re.search(r"\b(crackers?|triscuit|triscuits|water\s+biscuits?|crispbreads?)\b", identity_evidence, re.I):
        cracker_identity = identity if re.search(r"\bcrackers?\b", identity, re.I) else "Crackers"
        return "Snack > Crackers", cracker_identity

    tortilla_identity = _packaged_tortilla_identity(title, identity)
    if tortilla_identity and (
        bfc_lower in COOKIE_BFCS | {"breads & buns", "bread", "mexican dinner mixes"}
        or _token_key(category).startswith(("bakery cookie", "bakery tortilla", "pantry grain shell"))
        or _token_key(row.get("canonical_path", "") or "").startswith(("bakery cookie", "bakery tortilla", "pantry grain shell"))
    ):
        return "Bakery > Tortillas", tortilla_identity

    mexican_identity = _mexican_prepared_identity(title, identity)
    if mexican_identity and (
        bfc_lower == "mexican dinner mixes"
        or _token_key(category).startswith("pantry baking mix")
        or _token_key(row.get("canonical_path", "") or "").startswith("pantry baking mix")
    ):
        if mexican_identity == "Breakfast Burrito":
            return "Meal > Breakfast Burritos", mexican_identity
        if mexican_identity == "Burrito":
            return "Meal > Burritos", mexican_identity
        return "Meal > Mexican Entrees", mexican_identity

    if re.search(r"\btacos?\b", identity_evidence, re.I) and (
        bfc_lower == "mexican dinner mixes"
        or _token_key(category).startswith("pantry baking mix")
        or _token_key(row.get("canonical_path", "") or "").startswith("pantry baking mix")
    ):
        return "Meal > Tacos", "Tacos"

    potato_side_identity = _packaged_potato_side_identity(title, identity)
    if potato_side_identity and (
        bfc_lower in {"vegetable and lentil mixes", "vegetables - prepared/processed (shelf stable)"}
        or _token_key(category).startswith("pantry baking mix")
        or _token_key(row.get("canonical_path", "") or "").startswith("pantry baking mix")
    ):
        return "Pantry > Packaged Sides", potato_side_identity

    gravy_identity = _gravy_identity(title, identity)
    if gravy_identity and (
        bfc_lower in {"gravy mix", "sauces/spreads/dips/condiments", "seasoning mixes, salts, marinades & tenderizers"}
        or _token_key(category).startswith("pantry baking mix")
        or _token_key(row.get("canonical_path", "") or "").startswith("pantry baking mix")
    ):
        return "Pantry > Gravy", gravy_identity

    meal_kit_identity = _meal_kit_identity(title, identity)
    if meal_kit_identity and (
        bfc_lower in {"baking/cooking mixes/supplies", "mexican dinner mixes", "pizza mixes & other dry dinners", "pasta dinners"}
        or _token_key(category).startswith("pantry baking mix")
        or _token_key(row.get("canonical_path", "") or "").startswith("pantry baking mix")
    ):
        return "Pantry > Meal Kits", meal_kit_identity

    coating_breading_identity = _coating_breading_identity(title, identity)
    if coating_breading_identity and (
        bfc_lower in {"seasoning mixes, salts, marinades & tenderizers", "bread & muffin mixes"}
        or _token_key(category).startswith("pantry baking mix")
        or _token_key(row.get("canonical_path", "") or "").startswith("pantry baking mix")
    ):
        return "Pantry > Coatings & Breadings", coating_breading_identity

    seaweed_identity = _seaweed_identity(title, identity)
    if seaweed_identity and (
        bfc_lower == "vegetable and lentil mixes"
        or _token_key(category).startswith("pantry baking mix")
        or _token_key(row.get("canonical_path", "") or "").startswith("pantry baking mix")
    ):
        return "Pantry > Seaweed", seaweed_identity

    grain_identity = _grain_identity(title, identity)
    if grain_identity and (
        bfc_lower == "vegetable and lentil mixes"
        or _token_key(category).startswith("pantry baking mix")
        or _token_key(row.get("canonical_path", "") or "").startswith("pantry baking mix")
    ):
        return "Pantry > Rice & Grains", grain_identity

    soup_identity = _soup_identity(title, identity)
    if soup_identity and (
        _token_key(category).startswith("pantry baking mix")
        or _token_key(row.get("canonical_path", "") or "").startswith("pantry baking mix")
    ):
        return "Pantry > Soup", soup_identity

    hot_cereal_identity = _hot_cereal_identity(title, identity)
    if hot_cereal_identity and (
        _token_key(category).startswith("pantry baking mix")
        or _token_key(row.get("canonical_path", "") or "").startswith("pantry baking mix")
    ):
        return "Pantry > Hot Cereal", hot_cereal_identity

    dessert_mix_identity = _dessert_mix_identity(title, identity)
    if dessert_mix_identity and (
        _token_key(category).startswith("pantry baking mix")
        or _token_key(row.get("canonical_path", "") or "").startswith("pantry baking mix")
    ):
        return "Pantry > Dessert Mixes", dessert_mix_identity

    ice_cream_cone_identity = _ice_cream_cone_identity(title, identity)
    if ice_cream_cone_identity and (
        "ice cream" in bfc_lower
        or "crackers & biscotti" in bfc_lower
        or _token_key(category).startswith(("pantry baking mix", "snack ice cream cone", "frozen ice cream cone", "frozen ice cream"))
        or _token_key(row.get("canonical_path", "") or "").startswith(("pantry baking mix", "snack ice cream cone", "frozen ice cream cone", "frozen ice cream"))
    ):
        return "Snack > Ice Cream Cones", ice_cream_cone_identity

    bakery_hijack = _bakery_path_hijacked(category, row.get("canonical_path", "") or "")

    if bakery_hijack and re.search(r"\bpizza\s+rolls?\b", title, re.I):
        return "Frozen > Appetizers", "Pizza Rolls"

    if bakery_hijack and re.search(r"\begg\s+rolls?\b|\bspring\s+rolls?\b", title, re.I):
        root = "Frozen > Appetizers" if "frozen" in bfc_lower else "Meal > Appetizers"
        return root, _appetizer_identity(title)

    if bakery_hijack and re.search(r"\bstuffed\s+cabbage\s+rolls?\b|\bcabbage\s+rolls?\b", title, re.I):
        root = "Frozen > Single Entrees" if "frozen" in bfc_lower else "Meal > Entrees"
        return root, "Stuffed Cabbage"

    if bakery_hijack and re.search(r"\bpork\s+roll\b|\btaylor\s+pork\s+roll\b", title, re.I):
        return "Meat & Seafood > Pork", "Pork Roll"

    if bakery_hijack and "sausage" in bfc_lower:
        if re.search(r"\bfranks?\b|\bhot\s*dogs?\b", title, re.I):
            return "Meat & Seafood > Hot Dogs", "Hot Dogs"
        if re.search(r"\bchorizo\b", title, re.I):
            return "Meat & Seafood > Sausage", "Chorizo"
        return "Meat & Seafood > Sausage", "Sausage"

    if bakery_hijack and re.search(r"\bsalami\s+roll\b", title, re.I):
        return "Meat & Seafood > Charcuterie", "Salami"

    if bakery_hijack and _looks_like_prepared_sandwich(title):
        if bfc_lower in FROZEN_APPETIZER_BFCS:
            return "Frozen > Appetizers", _appetizer_identity(title)
        if "frozen" in bfc_lower:
            return "Frozen > Single Entrees", _sandwich_identity(title)
        return "Meal > Sandwiches", _sandwich_identity(title)

    if bakery_hijack and re.search(r"\bbuns?\b", title, re.I) and any(
        cue in bfc_lower for cue in ("entrees", "ready-made", "cooked & prepared", "dinners")
    ):
        return "Meal > Entrees", "Stuffed Buns"

    if bfc_lower in PREPARED_SANDWICH_BFCS:
        return "Meal > Sandwiches", _sandwich_identity(title)

    if bfc_lower in PREPARED_WRAP_BFCS:
        if re.search(r"\bburritos?\b", title, re.I):
            return "Meal > Burritos", "Burrito"
        return "Meal > Wraps", "Wrap"

    if bfc_lower in FROZEN_BREAKFAST_BFCS:
        return "Frozen > Breakfast", _sandwich_identity(title)

    if bfc_lower in BREAKFAST_SANDWICH_BFCS:
        return "Meal > Sandwiches", _sandwich_identity(title)

    if bfc_lower in FROZEN_APPETIZER_BFCS:
        return "Frozen > Appetizers", _appetizer_identity(title)

    if bfc_lower in FROZEN_MEAL_BFCS:
        return "Frozen > Single Entrees", _prepared_meal_identity(title)

    if bfc_lower in PREPARED_MEAT_BFCS and _looks_like_prepared_sandwich(title):
        return "Meal > Sandwiches", _sandwich_identity(title)

    if bfc_lower == "pizza":
        if re.search(r"\bpizza\s+rolls?\b", title, re.I):
            return "Frozen > Appetizers", "Pizza Rolls"
        if re.search(r"\bbread\s*st(?:ick|ix)s?\b|\bbreadsticks?\b", title, re.I):
            return "Frozen > Pizza", "Breadsticks"
        return "Meal > Pizza", "Pizza"

    # Authoritative BFC-driven routes — when BFC alone fully determines
    # family+type, force the route regardless of title regex hijacks.
    if bfc_lower == "sushi":
        return "Meal > Sushi", identity or "Sushi"
    if bfc_lower in COOKIE_BFCS:
        cookie_evidence = f"{title} {identity}"
        if re.search(r"\bcookies?\b", cookie_evidence, re.I):
            cookie_identity = identity if re.search(r"\bcookies?\b", identity, re.I) else "Cookies"
            return "Bakery > Cookies", cookie_identity
        if re.search(r"\bbiscuits?\b", identity, re.I):
            return "Bakery > Biscuits", identity or "Biscuits"
    if bfc_lower == "powdered drinks":
        # Sub-route by identity / title cue
        if "hot cocoa" in blob or "hot chocolate" in blob:
            return "Beverage > Hot Cocoa", identity or "Hot Cocoa"
        if "lemonade" in blob:
            return "Beverage > Flavored Drinks", identity or "Lemonade"
        if "iced tea" in blob or "tea mix" in blob:
            return "Beverage > Tea", identity or "Tea"
        return "Beverage > Flavored Drinks", identity or "Drink Mix"
    if bfc_lower == "candy":
        # Subroute by title cue first (PI is unreliable for candy SKUs),
        # then identity. Title takes priority since it's the authoritative
        # source of what the product actually IS.
        title_low = title.lower()
        if "jelly bean" in title_low:
            return "Snack > Candy", "Jelly Beans"
        if re.search(r"\bgumm(y|i|ies)\b", title_low):
            return "Snack > Candy", "Gummy Candy"
        if "licorice" in title_low or "twizzler" in title_low:
            return "Snack > Candy", "Licorice"
        if "marshmallow" in title_low:
            return "Snack > Candy", "Marshmallows"
        if "lollipop" in title_low or "sucker" in title_low:
            return "Snack > Candy", "Lollipops"
        if "caramel" in title_low and "chocolate" not in title_low:
            return "Snack > Candy", "Caramels"
        if "taffy" in title_low:
            return "Snack > Candy", "Taffy"
        if "truffle" in title_low and "salt" not in title_low and "oil" not in title_low:
            return "Snack > Chocolate Candy", "Truffles"
        # Identity-based fallback
        id_lower = identity.lower()
        if "jelly bean" in id_lower:
            return "Snack > Candy", "Jelly Beans"
        if "gummy" in id_lower or "gummi" in id_lower:
            return "Snack > Candy", "Gummy Candy"
        if "chocolate" in id_lower or "chocolate" in title_low:
            return "Snack > Chocolate Candy", identity if "chocolate" in id_lower else "Chocolate Candy"
        if "mint" in id_lower or "peppermint" in id_lower or "peppermint" in title_low:
            return "Snack > Candy", identity if "mint" in id_lower else "Mints"
        if "licorice" in id_lower:
            return "Snack > Candy", "Licorice"
        # Generic candy fallthrough — only if identity isn't a complete mismatch
        if identity.lower() in ("buns", "bagels", "bread", "cake", ""):
            return "Snack > Candy", "Candy"
        return "Snack > Candy", identity

    # Title-driven jerky override: title says JERKY/SLIM JIM/JACK LINK →
    # force Snack > Jerky (overrides FNDDS "beef steak" miscoding)
    if re.search(r"\b(jerky|biltong|slim\s*jim|jack\s*link|chomps|krave)\b", title, re.I):
        # Determine protein from title
        if re.search(r"\bturkey\b", title, re.I):
            return "Snack > Jerky", "Turkey Jerky"
        if re.search(r"\bpork\b", title, re.I):
            return "Snack > Jerky", "Pork Jerky"
        if re.search(r"\bsalmon\b|\btuna\b|\bfish\b", title, re.I):
            return "Snack > Jerky", "Fish Jerky"
        # Default to beef
        return "Snack > Jerky", "Beef Jerky"

    if re.search(r"\byogurt\s+raisins?\b", blob):
        return "Snack > Dried Fruit", "Yogurt Raisins"

    butter_repair_context = (
        _token_key(category).startswith("dairy butter")
        or _token_key(row.get("canonical_path", "") or "").startswith("dairy butter")
        or bfc.strip().lower() in {
            "butter & spread",
            "honey, jam, marmalade & spreads",
            "jam, jelly & fruit spreads",
        }
    )

    if butter_repair_context and ("cookie butter" in blob or "cookie spread" in blob):
        return "Pantry > Spreads", "Cookie Butter"

    if butter_repair_context:
        for key, butter_identity in NUT_BUTTER_TYPES:
            if key == "tahini":
                if re.search(r"\btahini\b", blob):
                    return "Pantry > Nut Butters", butter_identity
            elif re.search(rf"\b{key}(?:\s+seed)?\s+butter\b", blob):
                return "Pantry > Nut Butters", butter_identity

    if "canned fruit" in bfc.lower():
        fruit_identity = identity
        if re.search(r"\bapple\s*sauce\b|\bapplesauce\b", title, re.I):
            fruit_identity = "Applesauce"
        elif re.search(r"\bfried\s+apples?\b|\bapple(s)?\b", title, re.I):
            fruit_identity = "Apples"
        elif re.search(r"\bpeaches?\b", title, re.I):
            fruit_identity = "Peaches"
        elif re.search(r"\bpears?\b", title, re.I):
            fruit_identity = "Pears"
        elif re.search(r"\bpineapple\b", title, re.I):
            fruit_identity = "Pineapple"
        if _token_key(fruit_identity) in {"mixed vegetable", "vegetable"}:
            fruit_identity = "Fruit"
        return "Pantry > Canned Fruit", fruit_identity or "Fruit"

    beef_steak_path = re.search(r"\bbeef\b.*\bsteaks?\b", row.get("canonical_path", "") or "", re.I)
    if beef_steak_path or any(species in blob for species, _ in SEAFOOD_TYPES):
        for species, seafood_identity in SEAFOOD_TYPES:
            if re.search(rf"\b{re.escape(species)}\b", blob):
                family = "Shellfish" if seafood_identity in {"Shrimp", "Squid", "Conch", "Crab", "Lobster", "Scallop", "Clam", "Mussel"} else "Fish"
                return f"Meat & Seafood > {family}", seafood_identity

    return None


def _canonical_from_category_identity(category_path: str, identity: str) -> str:
    category_segments = dedupe_segments(split_path(category_path))
    identity = _prettify_segment(identity)
    if not category_segments:
        return identity
    if not identity:
        return PATH_SEP.join(category_segments)

    identity_key = _token_key(identity)
    category_keys = {_token_key(seg) for seg in category_segments}
    category_words: set[str] = set()
    for seg in category_segments:
        category_words.update(_word_set(seg))

    if identity_key in category_keys:
        return PATH_SEP.join(category_segments)

    last_is_combined_bucket = bool(re.search(r"[&,/]", category_segments[-1]))
    if not last_is_combined_bucket and _word_set(identity).issubset(category_words):
        return PATH_SEP.join(category_segments)

    return PATH_SEP.join(dedupe_segments(category_segments + [identity]))


def finalize_taxonomy_row(row: Mapping[str, str]) -> FinalizedTaxonomy:
    forced = _forced_base(row)
    if forced:
        category_path, identity = forced
    else:
        category_path = row.get("category_path_fixed", "") or ""
        identity = row.get("product_identity_fixed", "") or ""
        if not category_path and row.get("canonical_path"):
            parts = split_path(row.get("canonical_path", "") or "")
            if identity and parts and _token_key(parts[-1]) == _token_key(identity):
                category_path = PATH_SEP.join(parts[:-1])
            else:
                category_path = PATH_SEP.join(parts)

    category_path = normalize_path(category_path)
    identity = _prettify_segment(identity)
    canonical_path = _canonical_from_category_identity(category_path, identity)
    modifier = derive_modifier(
        variant=row.get("variant", "") or "",
        flavor=row.get("flavor", "") or "",
        claims=row.get("claims", "") or "",
        form=row.get("form_texture_cut", "") or row.get("form", "") or "",
        identity=identity,
        canonical_path=canonical_path,
    )
    retail_leaf_path = canonical_path if not modifier else PATH_SEP.join(
        dedupe_segments(split_path(canonical_path) + split_path(modifier))
    )
    return FinalizedTaxonomy(
        category_path_fixed=category_path,
        product_identity_fixed=identity,
        canonical_path=canonical_path,
        modifier=modifier,
        retail_leaf_path=retail_leaf_path,
    )


def apply_finalized_taxonomy(row: dict[str, str]) -> dict[str, str]:
    finalized = finalize_taxonomy_row(row)
    row["category_path_fixed"] = finalized.category_path_fixed
    row["product_identity_fixed"] = finalized.product_identity_fixed
    row["canonical_path"] = finalized.canonical_path
    row["modifier"] = finalized.modifier
    row["retail_leaf_path"] = finalized.retail_leaf_path
    return row


def path_defects(row: Mapping[str, str]) -> list[str]:
    defects: list[str] = []
    category = normalize_path(row.get("category_path_fixed", "") or "")
    canonical = normalize_path(row.get("canonical_path", "") or "")
    retail_leaf = normalize_path(row.get("retail_leaf_path", "") or "")
    modifier = normalize_path(row.get("modifier", "") or "")

    for field, path in (
        ("category_path_fixed", category),
        ("canonical_path", canonical),
        ("retail_leaf_path", retail_leaf),
        ("modifier", modifier),
    ):
        parts = split_path(path)
        keys = [_token_key(p) for p in parts]
        if len(keys) != len(set(keys)):
            defects.append(f"{field}:duplicate_segment")
        if any(keys[i] == keys[i - 1] for i in range(1, len(keys))):
            defects.append(f"{field}:adjacent_duplicate_segment")

    if category and canonical and not (canonical == category or canonical.startswith(category + PATH_SEP)):
        defects.append("canonical_not_under_category")
    if canonical and retail_leaf and not (retail_leaf == canonical or retail_leaf.startswith(canonical + PATH_SEP)):
        defects.append("retail_leaf_not_under_canonical")

    canonical_keys = {_token_key(p) for p in split_path(canonical)}
    modifier_keys = {_token_key(p) for p in split_path(modifier)}
    if "plain" in modifier_keys and len(modifier_keys) > 1:
        defects.append("plain_mixed_with_modifier")
    if canonical_keys & modifier_keys:
        defects.append("modifier_repeats_canonical")
    return defects
