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
    "reduced_sugar": "reduced_sugar",
    "low_sugar": "reduced_sugar",
    "less_sugar": "reduced_sugar",
    "fortified_with_calcium": "fortified",
    "calcium_fortified": "fortified",
    "iron_fortified": "fortified",
    "vitamin_added": "fortified",
    "added_vitamins": "fortified",
    "no_added_sugar": "no_sugar_added",
    "no_added_salt": "no_salt_added",
    "no_msg": "no_msg",
    "msg_free": "no_msg",
    "no_artificial_colors": "no_artificial_colors",
    "no_artificial_sweeteners": "no_artificial_sweeteners",
    "no_added_flavors": "no_artificial_flavors",
    "low_calorie": "low_calorie",
    "reduced_calorie": "low_calorie",
    "no_calorie": "low_calorie",
    "low_carb": "low_carb",
    "low_glycemic": "low_glycemic",
    "high_calcium": "high_calcium",
    "high_iron": "high_iron",
    "high_omega": "high_omega",
    "rich_in_omega": "high_omega",
    "good_source_of_fiber": "high_fiber",
    "good_source_of_protein": "high_protein",
    "high_in_protein": "high_protein",
    "high_in_fiber": "high_fiber",
    "raw": "raw",
    "unrefined": "unrefined",
    "unbleached": "unbleached",
    "bleached": "bleached",
    "stone_ground": "stone_ground",
    "extra_virgin": "extra_virgin",
    # More common DeepSeek-extracted claims discovered by Kimi audit
    "diet": "diet",
    "grain_free": "grain_free",
    "lightly_sweetened": "lightly_sweetened",
    "lightly_salted": "lightly_salted",
    "salted": "salted",
    "unsalted": "unsalted",
    "no_added_salt": "no_salt_added",
    "less_salt": "low_sodium",
    "added_protein": "high_protein",
    "added_fiber": "high_fiber",
    "added_calcium": "high_calcium",
    "iced": "iced",
    "caffeinated": "caffeinated",
    "energy": "energy",
    "electrolyte": "electrolyte",
    "antioxidant": "antioxidant",
    "anti_oxidant": "antioxidant",
    "no_color_added": "no_artificial_colors",
    "no_colors_added": "no_artificial_colors",
    "no_flavors_added": "no_artificial_flavors",
    "no_artificial_color": "no_artificial_colors",
    "smoked": "smoked",
    "uncured": "uncured",
    "cured": "cured",
    "nitrite_free": "nitrite_free",
    "no_nitrites": "nitrite_free",
    "preservative_free": "no_preservatives",
}

# All non-empty claims are relevant for the modifier path. "Sweetened" used
# to be excluded as the unmarked default, but that caused 35k+ rows to lose
# their claim leaf entirely (path = "...> Plain" instead of "...> Sweetened"
# or "...> Unsweetened > Fortified"). Now it's preserved like any other claim.
RELEVANT_CLAIMS = set(CLAIM_ALIASES.values())

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
    "cookies_and_cream",
    "cookies_n_cream",
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

PLANT_BASED_CONTEXT_PREFIXES = (
    "beverage plant milk",
    "meat seafood meat alternative",
    "frozen plant based meat",
    "pantry plant based dairy",
    "dairy cheese alternative",
    "dairy cheese substitute",
)

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

SNACK_BAR_BFCS = {
    "snack, energy & granola bars",
    "cereal/muesli bars",
}

CEREAL_BFCS = {
    "cereal",
    "processed cereal products",
}

CHARCUTERIE_ROLL_BFCS = {
    "pepperoni, salami & cold cuts",
    "cooked & prepared",
}

ABBREVIATIONS = {
    "bbq": "BBQ",
    "pb&j": "PB&J",
    "nfs": "NFS",
    "nsa": "NSA",
}


# BFC retail-grouping labels that should NEVER appear at canonical_path's
# last segment when a more-specific identity exists. These are pluralized
# BFC names without &/, that the BFC-strip regex misses.
# Keep curated — adding too many breaks legitimate type segments.
_BFC_RETAIL_LABEL_LEAVES = frozenset({
    "baking mixes",          # Pantry > Baking Mixes > X is OK at depth 2,
                             # but "Pantry > Baking Mixes" alone (depth 2)
                             # leaves PI=Baking Mix as type → strip.
    "salad dressings",
    "appetizers & snacks",   # also caught by [&,/] but explicit for clarity
    "hot dogs & sausages",
    "patties & burgers",
    "frosting & icing",
    "wraps & burritos",
})


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
    canonical_segments = list(canonical_segments)
    path_key = _token_key(PATH_SEP.join(canonical_segments))
    if token in {"plant_based", "non_dairy"} and path_key.startswith(PLANT_BASED_CONTEXT_PREFIXES):
        return True
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


def _looks_like_breakfast_sandwich(title: str, reference_text: str = "") -> bool:
    title = title or ""
    reference_text = reference_text or ""
    evidence = f"{title} {reference_text}"
    if re.search(r"\bbreakfast\s+sandwich(?:es)?\b", evidence, re.I):
        return True
    carrier = r"(?:bagels?|biscuits?|croissants?|english\s+muffins?|muffins?|flatbreads?)"
    filling = r"(?:eggs?|egg\s+white|cheese|cheddar|mozzarella|sausage|bacon|ham|turkey|steak)"
    if re.search(rf"\bbreakfast\s+{carrier}\b", title, re.I) and re.search(rf"\b{filling}\b", title, re.I):
        return True
    if re.search(rf"\b{carrier}\b.*\bwith\b.*\b{filling}\b", title, re.I):
        return True
    if re.search(rf"\b{filling}\b.*\bon\s+(?:a\s+)?{carrier}\b", evidence, re.I):
        return True
    return False


def _sandwich_identity(title: str) -> str:
    t = title or ""
    if _looks_like_breakfast_sandwich(t):
        return "Breakfast Sandwich"
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
    if re.search(r"\bpita\b", t, re.I):
        return "Pita Sandwich"
    return "Sandwich"


def _is_sandwich_carrier_identity(identity: str) -> bool:
    return bool(re.search(
        r"\b(buns?|rolls?|croissants?|baguettes?|ciabatta|flatbread|"
        r"pita|bagels?|english\s+muffins?|bread)\b",
        identity or "",
        re.I,
    ))


def _bread_carrier_route(title: str, identity: str) -> tuple[str, str] | None:
    evidence = f"{title or ''} {identity or ''}"
    if re.search(r"\bsandwich\s+cookies?\b|\bcookie\s+sandwich\b|\bice\s+cream\s+sandwich\b", evidence, re.I):
        return None
    if re.search(r"\btortillas?\b", evidence, re.I):
        return "Bakery > Tortillas", "Tortillas"
    if re.search(r"\bnaan\b", evidence, re.I):
        return "Bakery > Naan", "Naan"
    if re.search(r"\bgyro\s+bread\b|\bpita\b", evidence, re.I):
        return "Bakery > Pita Bread", "Pita Bread" if re.search(r"\bpita\b", evidence, re.I) else "Gyro Bread"
    if re.search(r"\bflat\s*breads?\b|\bflatbread\b", evidence, re.I):
        return "Bakery > Flatbread", "Flatbread"
    if re.search(r"\benglish\s+muffins?\b", evidence, re.I):
        return "Bakery > English Muffins", "English Muffins"
    if re.search(r"\bbagels?\b", evidence, re.I):
        return "Bakery > Bagels", "Bagels"
    if re.search(r"\bhot\s*dog\b.*\b(?:buns?|rolls?)\b|\b(?:buns?|rolls?)\b.*\bhot\s*dog\b", evidence, re.I):
        return "Bakery > Buns", "Hot Dog Buns"
    if re.search(r"\b(?:hamburger|burger)\b.*\b(?:buns?|rolls?)\b|\b(?:buns?|rolls?)\b.*\b(?:hamburger|burger)\b", evidence, re.I):
        return "Bakery > Buns", "Hamburger Buns"
    if re.search(r"\bsliders?\b.*\b(?:buns?|rolls?)\b|\b(?:buns?|rolls?)\b.*\bsliders?\b", evidence, re.I):
        return "Bakery > Buns", "Slider Buns"
    if re.search(r"\bbrioche\s+buns?\b", evidence, re.I):
        return "Bakery > Buns", "Brioche Buns"
    if re.search(r"\bsandwich\s+buns?\b|\bbuns?\b.*\bsandwich\b", evidence, re.I):
        return "Bakery > Buns", "Sandwich Buns"
    if re.search(r"\bsandwich\s+rolls?\b|\brolls?\b.*\bsandwich\b", evidence, re.I):
        return "Bakery > Rolls", "Sandwich Rolls"
    if re.search(r"\b(?:sub|hoagie|hero)\s+rolls?\b|\brolls?\b.*\b(?:sub|hoagie|hero)\b", evidence, re.I):
        return "Bakery > Rolls", "Sub Rolls"
    if re.search(r"\bdinner\s+rolls?\b", evidence, re.I):
        return "Bakery > Rolls", "Dinner Rolls"
    if re.search(r"\brolls?\b", evidence, re.I):
        return "Bakery > Rolls", identity if re.search(r"\brolls?\b", identity or "", re.I) else "Rolls"
    if re.search(r"\bbuns?\b", evidence, re.I):
        return "Bakery > Buns", identity if re.search(r"\bbuns?\b", identity or "", re.I) else "Buns"
    if re.search(r"\bsandwich\s+bread\b|\bbread\b.*\bsandwich\b", evidence, re.I):
        return "Bakery > Bread", "Sandwich Bread"
    if re.search(r"\bbreads?\b|\bloaves?\b", evidence, re.I):
        return "Bakery > Bread", identity if re.search(r"\bbreads?\b", identity or "", re.I) else "Bread"
    return None


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
        (r"\bblack[\s-]*eye\s+peas?\b|\bfrijoles\s+carita\b", "Black-Eyed Peas"),
        (r"\bsmall\s+reds\b", "Small Red Beans"),
        (r"\bsmall\s+red\s+beans?\b", "Small Red Beans"),
        (r"\bred\s+kidney\s+beans?\b|\bkidney\s+beans?\b", "Kidney Beans"),
        (r"\bgreat\s+northern\s+beans?\b", "Great Northern Beans"),
        (r"\bbaby\s+lima\s+beans?\b", "Baby Lima Beans"),
        (r"\blima\s+beans?\b", "Lima Beans"),
        (r"\bblack\s+beans?\b", "Black Beans"),
        (r"\bpinto\s+beans?\b", "Pinto Beans"),
        (r"\bnavy\s+beans?\b", "Navy Beans"),
        (r"\bgarbanzo\s+beans?\b|\bchickpeas?\b", "Garbanzo Beans"),
        (r"\bchick\s+peas?\b|\bgarbanzos?\b", "Garbanzo Beans"),
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
        (r"\bmung\s+dal\b|\bmoong\s+dal\b", "Mung Dal"),
        (r"\burad\s+dal\b|\burad\s+gota\b", "Urad Dal"),
        (r"\btoor\s+dal\b", "Toor Dal"),
        (r"\bchana\s+dal\b", "Chana Dal"),
        (r"\bblack\s+gram\b", "Black Gram"),
        (r"\bsplit\s+peas?\b", "Split Peas"),
        (r"\bwhole\s+green\s+peas?\b|\bgreen\s+peas?\b", "Green Peas"),
        (r"\byellow\s+(?:split|spit)\s+peas?\b", "Yellow Split Peas"),
        (r"\byellow\s+peas?\b", "Yellow Peas"),
        (r"\byelloweye\s+peas?\b", "Yelloweye Peas"),
        (r"\bpigeon\s+peas?\b", "Pigeon Peas"),
        (r"\bpurple\s+hull\s+peas?\b", "Purple Hull Peas"),
        (r"\bsugar\s+snap\s+peas?\b", "Sugar Snap Peas"),
        (r"\bsweet\s+peas?\b", "Sweet Peas"),
        (r"\bfield\s+peas?\b", "Field Peas"),
        (r"\bcow\s*peas?\b|\bcowpeas?\b", "Cowpeas"),
        (r"\bedamame\b", "Edamame"),
        (r"\bpeeled\s+beans?\b", "Peeled Beans"),
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
        r"potato\s+(?:pancake|latke|slices?|shreds?|flakes?|salad|casserole|kugel|dumpling)|potatoes?)\b",
        evidence,
        re.I,
    ) and re.search(
        r"\b(potatoes?|potato\s+(?:mix|shreds?|flakes?|salad|casserole|kugel|dumpling|slices?)|"
        r"potato\s+(?:pancake|latke)\s+mix|scalloped\s+potatoes?\s+mix)\b",
        evidence,
        re.I,
    ):
        if re.search(r"\bpotato\s+(?:pancake|latke)\s+mix\b", evidence, re.I):
            return "Potato Pancake Mix"
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
    if re.search(r"\blaver\b", evidence, re.I):
        return "Laver"
    if re.search(r"\bsea\s+moss\b", evidence, re.I):
        return "Sea Moss"
    if re.search(r"\bdulse\b", evidence, re.I):
        return "Dulse"
    if re.search(r"\bkelps?\b", evidence, re.I):
        return "Kelp"
    if re.search(r"\bseaweed\s+snacks?\b", evidence, re.I):
        return "Seaweed Snacks"
    if re.search(r"\bseaweed\b", evidence, re.I):
        return "Seaweed"
    return None


def _grain_identity(title: str, identity: str) -> str | None:
    evidence = f"{title or ''} {identity or ''}"
    if re.search(r"\bfarro\b", evidence, re.I):
        return "Farro"
    if re.search(r"\bspelt\b", evidence, re.I):
        return "Spelt"
    if re.search(r"\bpearl\s+barley\b", evidence, re.I):
        return "Pearl Barley"
    if re.search(r"\bbarley\b", evidence, re.I):
        return "Barley"
    if re.search(r"\bquinoa\b", evidence, re.I):
        return "Quinoa"
    if re.search(r"\bdried\s+corn\b|\bcracked\s+corn\b|\bcancha\s+corn\b|\bcorn\s+cuzco\b|\bcorn\s+cancha\b|\bcorn\s+chulpe\b", evidence, re.I):
        return "Dried Corn"
    if re.search(r"\bpuffed\s+corn\s+cereal\b", evidence, re.I):
        return "Puffed Corn Cereal"
    if re.search(r"\barepa\b|\bmote'?s?\s+arepa\b", evidence, re.I):
        return "Arepa"
    if re.search(r"\bflax\s+chia\b", evidence, re.I):
        return "Seed Blend"
    return None


def _dried_vegetable_identity(title: str, identity: str) -> str | None:
    evidence = f"{title or ''} {identity or ''}"
    if re.search(r"\bdried\s+(?:morel\s+)?mushrooms?\b|\bair\s+dried\s+.*\bshiitake\b|\bmorel\b|\bshiitake\b|\bmushroom\s+(?:blend|mix)\b", evidence, re.I):
        return "Dried Mushrooms"
    if re.search(r"\bdehydrated\s+(?:chopped\s+)?onions?\b", evidence, re.I):
        return "Dried Onions"
    if re.search(r"\bdehydrated\s+.*\bcelery\b", evidence, re.I):
        return "Dried Celery"
    if re.search(r"\bdried\s+vegetables?\b|\bvegetable\s+(?:stew\s+)?blend\b", evidence, re.I):
        return "Dried Vegetables"
    if re.search(r"\bfreeze\s+dried\s+peas?\b", evidence, re.I):
        return "Dried Peas"
    if re.search(r"\binstant\s+(?:butternut\s+squash|pacific\s+sea\s+salad)\b", evidence, re.I):
        return "Dried Vegetables"
    if re.search(r"\bdried\s+lily\s+flower\b", evidence, re.I):
        return "Dried Lily Flower"
    return None


def _root_starch_side_identity(title: str, identity: str) -> str | None:
    evidence = f"{title or ''} {identity or ''}"
    if re.search(r"\bpounded\s+yam\b|\biyan\b", evidence, re.I):
        return "Pounded Yam"
    if re.search(r"\bmalanga\b", evidence, re.I):
        return "Malanga"
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


def _baking_mix_identity(title: str, identity: str) -> str | None:
    evidence = f"{title or ''} {identity or ''}"
    candidates = [
        (r"\bcorn\s*bread\s+mix\b|\bcornbread\s+mix\b", "Cornbread Mix"),
        (r"\bpancake\s+(?:and\s+waffle\s+)?mix\b", "Pancake Mix"),
        (r"\bwaffle\s+mix\b", "Waffle Mix"),
        (r"\bbrownie\s+mix\b", "Brownie Mix"),
        (r"\bcake\s+mix\b", "Cake Mix"),
        (r"\bcookie\s+mix\b", "Cookie Mix"),
        (r"\bmuffin\s+mix\b", "Muffin Mix"),
        (r"\bbiscuit\s+mix\b", "Biscuit Mix"),
        (r"\bbread\s+mix\b", "Bread Mix"),
    ]
    for pattern, label in candidates:
        if re.search(pattern, evidence, re.I):
            return label
    return None


def _coffee_creamer_route(title: str, identity: str) -> tuple[str, str] | None:
    evidence = f"{title or ''} {identity or ''}"
    if not re.search(r"\b(?:coffee\s+)?creamers?\b", evidence, re.I):
        return None
    return "Beverage > Coffee Creamer", "Coffee Creamer"


def _coffee_route(title: str, identity: str) -> tuple[str, str] | None:
    evidence = f"{title or ''} {identity or ''}"
    if not re.search(r"\b(coffee|cold\s*brew|espresso|cappuccino|latte|nitro)\b", evidence, re.I):
        return None
    if re.search(r"\b(?:coffee\s+)?creamers?\b", evidence, re.I):
        return _coffee_creamer_route(title, identity)
    if re.search(r"\bcold\s*brew\b", evidence, re.I):
        return "Beverage > Coffee", "Cold Brew Coffee"
    if re.search(r"\biced\s+coffee\b|\bcoffee\b.*\biced\b", evidence, re.I):
        return "Beverage > Coffee", "Iced Coffee"
    if re.search(r"\blatte\b", evidence, re.I):
        return "Beverage > Coffee", "Latte"
    if re.search(r"\bcappuccino\b", evidence, re.I):
        return "Beverage > Coffee", "Cappuccino"
    if re.search(r"\bespresso\b", evidence, re.I):
        return "Beverage > Coffee", "Espresso"
    if re.search(r"\bground\s+coffee\b", evidence, re.I):
        return "Beverage > Coffee", "Ground Coffee"
    if re.search(r"\binstant\s+coffee\b", evidence, re.I):
        return "Beverage > Coffee", "Instant Coffee"
    return "Beverage > Coffee", "Coffee"


def _snack_bar_route(title: str, identity: str) -> tuple[str, str]:
    evidence = f"{title or ''} {identity or ''}"
    if re.search(r"\bprotein\s+bars?\b", evidence, re.I):
        return "Snack > Bars", "Protein Bars"
    if re.search(r"\benergy\s+bars?\b", evidence, re.I):
        return "Snack > Bars", "Energy Bars"
    if re.search(r"\bgranola\s+bars?\b", evidence, re.I):
        return "Snack > Bars", "Granola Bars"
    if re.search(r"\bcereal\s+bars?\b", evidence, re.I):
        return "Snack > Bars", "Cereal Bars"
    if re.search(r"\bbreakfast\s+bars?\b", evidence, re.I):
        return "Snack > Bars", "Breakfast Bars"
    if re.search(r"\bfruit\s+bars?\b|\bfruits\s+sandwich\s+bars?\b", evidence, re.I):
        return "Snack > Bars", "Fruit Bars"
    if re.search(r"\bmeal\s+replacement\s+bars?\b", evidence, re.I):
        return "Snack > Bars", "Meal Replacement Bars"
    if re.search(r"\bnutrition\s+bars?\b", evidence, re.I):
        return "Snack > Bars", "Nutrition Bars"
    return "Snack > Bars", identity if re.search(r"\bbars?\b", identity or "", re.I) else "Snack Bar"


def _charcuterie_roll_route(title: str, identity: str, bfc_lower: str) -> tuple[str, str] | None:
    evidence = f"{title or ''} {identity or ''}"
    if not re.search(r"\b(roll\s*&\s*go|rolls?|rolled|roll-?ups?)\b", evidence, re.I):
        return None
    if bfc_lower == "cooked & prepared" and re.search(r"\bturkey\b", evidence, re.I):
        return "Meat & Seafood > Poultry > Turkey", "Turkey Roll"
    if re.search(r"\b(prosciutto|salami|salame|salumi|soppressata|pepperoni|mozzarella|provolone|charcuterie)\b", evidence, re.I):
        return "Meat & Seafood > Charcuterie", "Charcuterie Rolls"
    if re.search(r"\bbeef\b", evidence, re.I):
        return "Meat & Seafood > Beef", "Beef Roll"
    return "Meat & Seafood > Charcuterie", "Charcuterie Rolls"


def _bakery_churro_hijack_route(row: Mapping[str, str]) -> tuple[str, str] | None:
    title = row.get("title", "") or ""
    identity = row.get("product_identity_fixed", "") or ""
    bfc_lower = (row.get("branded_food_category", "") or "").strip().lower()
    category_key = _token_key(row.get("category_path_fixed", "") or "")
    canonical_key = _token_key(row.get("canonical_path", "") or "")
    if not (
        category_key.startswith("bakery pastry churro")
        or canonical_key.startswith("bakery pastry churro")
    ):
        return None

    evidence = f"{title} {identity}"
    if bfc_lower == "cake, cookie & cupcake mixes":
        return "Pantry > Baking Mixes", "Churro Mix"
    if bfc_lower == "crackers & biscotti" and re.search(r"\b(crisps?|crackers?)\b", evidence, re.I):
        return "Snack > Crackers", "Crisps"
    if bfc_lower == "fruit/nuts/seeds combination":
        if re.search(r"\bpopcorn\b", evidence, re.I):
            return "Snack > Popcorn", "Popcorn"
        if re.search(r"\bfava\s+bean\s+crisps?\b", evidence, re.I):
            return "Snack > Veggie Snacks", "Fava Bean Crisps"
        return "Snack > Trail Mix", "Trail Mix"
    if bfc_lower in {"cream/cream substitutes", "coffee/coffee substitutes"}:
        return _coffee_route(title, identity) or ("Beverage > Coffee Creamer", "Coffee Creamer")
    if bfc_lower == "energy, protein & muscle recovery drinks" and re.search(r"\bprotein\s+powder\b", evidence, re.I):
        return "Sports & Wellness > Protein Powders", "Protein Powder"
    if bfc_lower == "wholesome snacks" and re.search(r"\bplantain\s+chips?\b", evidence, re.I):
        return "Snack > Chips", "Plantain Chips"
    if bfc_lower == "snacks":
        if re.search(r"\b(bugles|corn\s+snacks?|fiesta\s+twists?)\b", evidence, re.I):
            return "Snack > Corn Snacks", "Corn Snacks"
        return "Snack > Snacks", "Snack"
    if bfc_lower == "entrees, sides & small meals" and re.search(r"\btoaster\s+pastries\b", evidence, re.I):
        return "Bakery > Toaster Pastries", "Toaster Pastries"
    if bfc_lower == "frozen bread & dough":
        if re.search(r"\bcheese\s+bread\b", evidence, re.I):
            return "Frozen > Bread & Dough", "Cheese Bread"
        if re.search(r"\bchurros?\b", evidence, re.I):
            return "Frozen > Churros", "Churros"
    if bfc_lower == "dips & salsa" and re.search(r"\bdip\b", evidence, re.I):
        return "Pantry > Dips & Spreads", "Dessert Dip"
    return None


def _churro_flavor_identity_route(row: Mapping[str, str]) -> tuple[str, str] | None:
    title = row.get("title", "") or ""
    identity = row.get("product_identity_fixed", "") or ""
    category = row.get("category_path_fixed", "") or ""
    canonical = row.get("canonical_path", "") or ""
    if not re.search(r"\bchurros?\b", f"{title} {identity} {category} {canonical}", re.I):
        return None
    evidence = f"{title} {identity}"

    product_cues: list[tuple[str, tuple[str, str]]] = [
        (r"\bprotein\s+powder\b", ("Sports & Wellness > Protein Powders", "Protein Powder")),
        (r"\bprotein\s+bars?\b", ("Snack > Bars", "Protein Bars")),
        (r"\bgranola\b", ("Snack > Granola", "Granola")),
        (r"\bcereal[0-9]*\b", ("Pantry > Cereal", "Cereal")),
        (r"\bfrozen\s+custard\b", ("Frozen > Ice Cream", "Frozen Custard")),
        (r"\bice\s+cream\b", ("Frozen > Ice Cream", "Ice Cream")),
        (r"\bcoffee\b|\bcold\s*brew\b|\blatte\b", ("Beverage > Coffee", "Coffee")),
        (r"\b(?:coffee\s+)?creamers?\b", ("Beverage > Coffee Creamer", "Coffee Creamer")),
        (r"\bcheesecake\b", ("Bakery > Cheesecake", "Cheesecake")),
        (r"\bcupcakes?\b", ("Bakery > Cupcakes", "Cupcakes")),
        (r"\btoaster\s+pastries\b", ("Bakery > Toaster Pastries", "Toaster Pastries")),
        (r"\bmuffins?\b", ("Bakery > Muffins", "Muffins")),
        (r"\bdonuts?\b|\bdoughnuts?\b", ("Bakery > Donuts", "Donuts")),
        (r"\b(?:marshmallow\s+)?rice\s+treats?\b|\bsmashcrispy\b", ("Snack > Crispy Rice Treats", "Crispy Rice Treats")),
        (r"\bwafers?\b", ("Bakery > Wafers", "Wafers")),
        (r"\bcotton\s+candy\b", ("Snack > Candy", "Cotton Candy")),
        (r"\bgum\b", ("Snack > Gum", "Gum")),
        (r"\bcandy\b|\begg\b", ("Snack > Candy", "Candy")),
        (r"\bchips?\b|\btortilla\s+chips?\b|\bstrips?\b", ("Snack > Chips", "Chips")),
        (r"\bpuffs?\b", ("Snack > Puffs", "Puffs")),
        (r"\b(?:corn\s+snacks?|fiesta\s+twists?|crispy\s+corn|corn\s*&\s*oat|corn\s+and\s+oat)\b", ("Snack > Corn Snacks", "Corn Snacks")),
        (r"\bpork\s+(?:rinds?|skins?)\b", ("Snack > Pork Rinds", "Pork Rinds")),
        (r"\bpopcorn\b|\bkettle\s+corn\b", ("Snack > Popcorn", "Popcorn")),
        (r"\btrail\s+mix\b", ("Snack > Trail Mix", "Trail Mix")),
        (r"\bwalnuts?\b", ("Snack > Nuts", "Walnuts")),
        (r"\balmonds?\b", ("Snack > Nuts", "Almonds")),
        (r"\bfava\s+bean\s+crisps?\b", ("Snack > Veggie Snacks", "Fava Bean Crisps")),
        (r"\bplantain\s+chips?\b", ("Snack > Chips", "Plantain Chips")),
        (r"\bbanana\s+bites?\b", ("Snack > Fruit Snacks", "Banana Bites")),
        (r"\brice\s+(?:rollers?|crisps?)\b", ("Snack > Rice Cakes", "Rice Snacks")),
        (r"\bsnack\s+mix\b", ("Snack > Mixes", "Snack Mix")),
        (r"\bjerky\b", ("Snack > Jerky", "Beef Jerky")),
        (r"\bpudding\b", ("Dairy > Pudding", "Pudding")),
        (r"\bdip\b", ("Pantry > Dips & Spreads", "Dessert Dip")),
    ]
    for pattern, route in product_cues:
        if re.search(pattern, evidence, re.I):
            return route
    return None


FROZEN_DESSERT_BFCS = {
    "ice cream & frozen yogurt",
    "frozen desserts",
    "other frozen desserts",
}

FROZEN_DESSERT_PATTERN = (
    r"\b(?:ice\s+cream|frozen\s+yogurt|gelato|sorbetto?|sherbet|"
    r"italian\s+ice|ice\s+pops?|freezer\s+pops?|freeze\s+pops?|"
    r"popsicles?|paletas?|fudge\s+bars?|fruit\s+bars?|"
    r"yogurt\s+bars?|frozen\s+kefir|kefir\s+bars?|"
    r"frozen\s+smoothie|smoothie\s+bowls?)\b"
)


def _looks_like_bakery_ice_cream_flavor_only(title: str, bfc_lower: str) -> bool:
    title = title or ""
    if re.search(r"\btoaster\s+(?:pastries|tarts)\b", title, re.I):
        return True
    if re.search(r"\b(?:pastries|toaster\s+(?:pastries|tarts)).*\bice\s+cream\s+sundae\b", title, re.I):
        return True
    if re.search(r"\bice\s+cream\s+sundae\b.*\b(?:pastries|toaster\s+(?:pastries|tarts))\b", title, re.I):
        return True
    if bfc_lower not in COOKIE_BFCS:
        return False
    if re.search(r"\bice\s+cream\s+(?:bars?|sandwich(?:es)?|cakes?)\b", title, re.I):
        return False
    if re.search(r"\bwith\b.{0,80}\bice\s+cream\b", title, re.I):
        return False
    return bool(re.search(
        r"\b(chips\s+ahoy|nabisco|oreo|sandwich\s+cookies?|"
        r"ice\s+cream\s+creations|ice\s+cream\s+cookies?|"
        r"sugar\s+cookie\s+decorating\s+kit)\b",
        title,
        re.I,
    ))


def _frozen_dessert_route(row: Mapping[str, str]) -> tuple[str, str] | None:
    title = row.get("title", "") or ""
    bfc_lower = (row.get("branded_food_category", "") or "").strip().lower()
    identity = row.get("product_identity_fixed", "") or ""
    category_key = _token_key(row.get("category_path_fixed", "") or "")
    canonical_key = _token_key(row.get("canonical_path", "") or "")
    reference = " ".join([
        row.get("fndds_desc", "") or "",
        row.get("esha_desc", "") or "",
        row.get("matched_key", "") or "",
    ])
    evidence = f"{title} {identity} {reference}"

    bfc_context = bfc_lower in FROZEN_DESSERT_BFCS
    title_has_frozen_dessert = bool(re.search(FROZEN_DESSERT_PATTERN, title, re.I))
    reference_has_frozen_dessert = bool(re.search(FROZEN_DESSERT_PATTERN, reference, re.I))
    evidence_has_frozen_dessert = bool(re.search(FROZEN_DESSERT_PATTERN, evidence, re.I))
    current_frozen_family = (
        category_key.startswith("frozen")
        or canonical_key.startswith("frozen")
    )
    current_bad_family = (
        category_key.startswith(("bakery", "meal sandwich", "snack", "dairy", "produce", "pantry"))
        or canonical_key.startswith(("bakery", "meal sandwich", "snack", "dairy", "produce", "pantry"))
    )
    strong_title_frozen_dessert = bool(re.search(
        r"\bice\s+cream\s+(?:cakes?|bars?|sandwich(?:es)?)\b|"
        r"\bice\s+cream\s+fill+ed\b|"
        r"\bcupcakes?\b.*\bice\s+cream\b|"
        r"\b(?:rolls?|buns?)\b.*\bice\s+cream\b",
        title,
        re.I,
    ))

    if not (
        (bfc_context and evidence_has_frozen_dessert)
        or (
            title_has_frozen_dessert
            and (current_bad_family or current_frozen_family)
            and (reference_has_frozen_dessert or strong_title_frozen_dessert)
        )
    ):
        return None

    if not bfc_context and _looks_like_bakery_ice_cream_flavor_only(title, bfc_lower):
        return None

    if not bfc_context and re.search(r"\bice\s+cream\s+(?:mix|base|powder|stabilizer)\b", evidence, re.I):
        return None
    if not bfc_context and bfc_lower in COOKIE_BFCS and re.search(
        r"\bice\s+cream\s+(?:cones?|cups?|cake\s+cups?)\b",
        title,
        re.I,
    ):
        return None

    if re.search(r"\bice\s+cream\s+sandwich(?:es)?\b|\bsandwich(?:es)?\b.*\bice\s+cream\b", title, re.I):
        return "Frozen > Ice Cream Sandwiches", "Ice Cream Sandwich"
    if re.search(r"\bice\s+cream\s+cake\b|\bice\s+cream\b.*\bcakes?\b|\bcakes?\b.*\bice\s+cream\b|\bcupcakes?\b.*\bice\s+cream\b", title, re.I):
        return "Frozen > Ice Cream Cakes", "Ice Cream Cake"
    if re.search(r"\bsmoothie\s+bowls?\b", title, re.I):
        return "Frozen > Smoothie Bowls", "Smoothie Bowl"
    if re.search(r"\bfrozen\s+kefir\b|\bkefir\s+bars?\b", title, re.I):
        return "Frozen > Frozen Kefir", "Frozen Kefir"
    if re.search(r"\b(?:frozen\s+yogurt|yogurt).*\bbars?\b", title, re.I):
        return "Frozen > Frozen Yogurt Bars", "Frozen Yogurt Bar"
    if re.search(r"\bfruit\s+bars?\b", title, re.I):
        return "Frozen > Fruit Bars", "Fruit Bar"
    if re.search(r"\b(?:ice\s+cream).*\bbars?\b|\bfudge\s+bars?\b", title, re.I):
        return "Frozen > Ice Cream Bars", "Ice Cream Bar"
    if bfc_context and re.search(r"\bice\s+cream\s+(?:cones?|cups?|cake\s+cups?)\b", title, re.I):
        return "Frozen > Ice Cream Cones", "Ice Cream Cone"
    if re.search(r"\b(?:ice\s+pops?|freezer\s+pops?|freeze\s+pops?|popsicles?|paletas?)\b", title, re.I):
        return "Frozen > Ice Pops", "Ice Pop"
    if re.search(r"\bitalian\s+ice\b", title, re.I):
        return "Frozen > Italian Ice", "Italian Ice"
    if re.search(r"\bgelato\b", evidence, re.I):
        return "Frozen > Gelato", "Gelato"
    if re.search(r"\bsorbetto?\b", evidence, re.I):
        return "Frozen > Sorbet", "Sorbet"
    if re.search(r"\bsherbet\b", evidence, re.I):
        return "Frozen > Sherbet", "Sherbet"
    if re.search(r"\bfrozen\s+yogurt\b", evidence, re.I):
        return "Frozen > Frozen Yogurt", "Frozen Yogurt"
    if re.search(r"\bice\s+cream\b", evidence, re.I) or bfc_context:
        return "Frozen > Ice Cream", "Ice Cream"
    return None


def _ice_cream_cone_identity(title: str, identity: str) -> str | None:
    evidence = f"{title or ''} {identity or ''}"
    if re.search(r"\b(sugar\s+cookie|decorating\s+kit)\b", evidence, re.I):
        return None
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


def _pie_crust_identity(title: str, identity: str) -> tuple[str, str] | None:
    evidence = f"{title or ''} {identity or ''}"
    if not re.search(r"\bpie\s*(?:crusts?|shells?|crust\s+mix)\b|\bpiecrusts?\b", evidence, re.I):
        return None
    if re.search(r"\bmix(?:es)?\b|\bdry\s+mix\b", evidence, re.I):
        return "Pantry > Baking Mixes", "Pie Crust Mix"
    if re.search(r"\bshells?\b", evidence, re.I):
        return "Bakery > Pie Crusts", "Pie Shells"
    return "Bakery > Pie Crusts", "Pie Crust"


def _cocktail_mixer_identity(title: str, identity: str) -> str | None:
    evidence = f"{title or ''} {identity or ''}"
    has_mix_cue = re.search(
        r"\b(cocktail\s+(?:mix|mixer)|mix(?:es|ers?)?|drink\s+mix|juice\s+mixers?|bar\s+juice|"
        r"rimm(?:er|ing)|rim\s+(?:sugar|salt|candy|dip|paste|dressing)|cocktail\s+garnish|"
        r"grenadine|bitters?|brine|syrup|beer\s+salt|margarita\s+salt|"
        r"bloody\s*mary\s+seasoning|michelada|rim\s+shot|cocktail\s+sea\s+salt|"
        r"chamoy|chamo\s+mix|picante|cream\s+of\s+coconut|coconut\s+cream)\b",
        evidence,
        re.I,
    )
    if not re.search(
        r"\b(cocktails?|margarita|pina\s*colada|daiquiri|bloody\s+mary|mojito|martini|"
        r"michelada|mule|paloma|cosmopolitan|old\s+fashioned|sweet\s*&?\s*sour|"
        r"whiskey\s+sour|grenadine|bitters?|rimm(?:er|ing)|rim\s+(?:sugar|salt|candy|dip|paste|dressing)|"
        r"bar\s+juice|brine|syrup|beer\s+salt|margarita\s+salt|bloody\s*mary\s+seasoning|"
        r"rim\s+shot|cocktail\s+sea\s+salt|chamoy|chamo\s+mix|picante|cream\s+of\s+coconut)\b",
        evidence,
        re.I,
    ):
        return None
    if re.search(r"\bbitters?\b", evidence, re.I):
        return "Cocktail Bitters"
    if re.search(
        r"\b(rimm(?:er|ing)|rim\s+(?:sugar|salt|candy|dip|paste|dressing)|cocktail\s+garnish|"
        r"beer\s+salt|margarita\s+salt|bloody\s*mary\s+seasoning|rim\s+shot|"
        r"cocktail\s+sea\s+salt|chamoy|chamo\s+mix|picante)\b",
        evidence,
        re.I,
    ):
        return "Cocktail Rimmer"
    if re.search(r"\b(grenadine|simple\s+syrup|cocktail\s+syrup|syrup)\b", evidence, re.I):
        return "Cocktail Syrup"
    if re.search(r"\b(brine|olive\s+brine|pickle\s+brine)\b", evidence, re.I):
        return "Cocktail Brine"
    if re.search(r"\b(cream\s+of\s+coconut|coconut\s+cream)\b", evidence, re.I):
        return "Cream of Coconut"
    if has_mix_cue and re.search(r"\b(bloody\s+mary)\b", evidence, re.I):
        return "Bloody Mary Mix"
    if has_mix_cue and re.search(r"\b(michelada)\b", evidence, re.I):
        return "Michelada Mix"
    if has_mix_cue and re.search(r"\b(margarita|pina\s*colada|daiquiri|mojito|martini|mule|paloma|cosmopolitan|"
                 r"old\s+fashioned|sweet\s*&?\s*sour|whiskey\s+sour|cocktail\s+(?:mix|mixer)|mixers?)\b", evidence, re.I):
        return "Cocktail Mix"
    return None


def _beverage_mix_route(title: str, identity: str) -> tuple[str, str] | None:
    evidence = f"{title or ''} {identity or ''}"
    if re.search(r"\bprotein\s+shake\s+mix\b|\bprotein\s+powder\s+drink\s+mix\b", evidence, re.I):
        return "Beverage > Protein Drinks", "Protein Shake Mix"
    if re.search(r"\bhot\s+cocoa\s+mix\b|\bhot\s+chocolate\s+mix\b", evidence, re.I):
        return "Beverage > Hot Cocoa", "Hot Cocoa Mix"
    if re.search(r"\biced\s+tea\s+mix\b|\btea\s+mix\b", evidence, re.I):
        return "Beverage > Tea", "Iced Tea Mix"
    if re.search(r"\blemonade\s+mix\b", evidence, re.I):
        return "Beverage > Mixes", "Lemonade Mix"
    if re.search(r"\blatte\s+mix\b|\biced\s+latte\b|\bcoffee\s+mix\b", evidence, re.I):
        return "Beverage > Coffee", "Latte Mix"
    if re.search(r"\b(sports?\s+drink|electrolyte|hydration|thirst\s+quencher)\b.*\bmix\b", evidence, re.I):
        return "Beverage > Sports Drinks", "Sports Drink Mix"
    if re.search(r"\b(?:drink|beverage|soda|smoothie)\s+mix\b|\bmix\s+for\s+beverage\b", evidence, re.I):
        return "Beverage > Mixes", "Drink Mix"
    return None


def _cocktail_style_variant(title: str) -> str:
    styles = [
        ("pina_colada", r"\bpina\s*colada\b|\bcoco[\s-]?lada\b"),
        ("bloody_mary", r"\bbloody\s+mary\b"),
        ("strawberry_daiquiri", r"\bstrawberry\s+daiquiri\b"),
        ("daiquiri", r"\bdaiquiri\b"),
        ("margarita", r"\bmargarita\b"),
        ("mojito", r"\bmojito\b"),
        ("dirty_martini", r"\bdirty\s+martini\b"),
        ("martini", r"\bmartini\b"),
        ("michelada", r"\bmichelada\b"),
        ("moscow_mule", r"\bmoscow\s+mule\b"),
        ("mule", r"\bmule\b"),
        ("paloma", r"\bpaloma\b"),
        ("cosmopolitan", r"\bcosmopolitan\b|\bcosmo\b"),
        ("old_fashioned", r"\bold\s+fashioned\b"),
        ("sweet_sour", r"\bsweet\s*&?\s*sour\b"),
        ("whiskey_sour", r"\bwhiskey\s+sour\b"),
        ("lemon_drop", r"\blemon\s+drop\b"),
        ("grenadine", r"\bgrenadine\b"),
    ]
    for token, pattern in styles:
        if re.search(pattern, title or "", re.I):
            return token
    return ""


def _bakery_path_hijacked(category: str, canonical_path: str) -> bool:
    key = _token_key(category or canonical_path)
    return key.startswith((
        "bakery bun",
        "bakery roll",
        "bakery bread",
        "bakery breadstick",
    ))


# PHASE 2: per-BFC title-cue sub-routers. For ambiguous BFCs that span
# multiple product types, use title cues to pick the right family>type.
# Returns (family>type, identity) when a rule matches; None otherwise.
def _bfc_title_subroute(bfc_lower: str, title: str, identity: str) -> tuple[str, str] | None:
    t = title.lower()

    if bfc_lower == "wholesome snacks":
        # 1.5k misrouted. Sub-routes by title cue.
        if re.search(r"\bapplesauce\b|\bapple\s+sauce\b", t):
            return "Pantry > Applesauce", "Applesauce"
        if re.search(r"\bsmoothie\b", t):
            return "Beverage > Smoothies", identity or "Smoothie"
        if re.search(r"\byogurt\b", t):
            return "Dairy > Yogurt", identity or "Yogurt"
        if re.search(r"\bjuice\b", t):
            return "Beverage > Juice", identity or "Juice"
        if re.search(r"\bgranola\s+bar\b|\bbar\b", t):
            return "Snack > Bars", identity or "Granola Bars"
        if re.search(r"\bbanana\s+bites?\b|\bfruit\s+bites?\b", t):
            return "Snack > Fruit Snacks", identity or "Fruit Snacks"
        if re.search(r"\bfruit\s+(snack|leather|strip)", t):
            return "Snack > Fruit Snacks", identity or "Fruit Snacks"

    if bfc_lower in ("breads & buns", "bread"):
        # This BFC is the carrier shelf. Words like "sandwich", "hamburger",
        # and "sub" describe bread/bun use here, not a prepared meal.
        carrier = _bread_carrier_route(title, identity)
        if carrier:
            return carrier
        if re.search(r"\bdinner\s+rolls?\b", t):
            return "Bakery > Rolls", identity or "Dinner Rolls"
        if re.search(r"\bpita\b", t):
            return "Bakery > Pita Bread", identity or "Pita"
        if re.search(r"\btortillas?\b", t):
            return "Bakery > Tortillas", identity or "Tortillas"
        if re.search(r"\bnaan\b", t):
            return "Bakery > Naan", identity or "Naan"
        if re.search(r"\bflatbread\b|\bflat\s+bread\b", t):
            return "Bakery > Flatbread", identity or "Flatbread"
        if re.search(r"\bbagels?\b", t):
            return "Bakery > Bagels", identity or "Bagels"
        if re.search(r"\benglish\s+muffins?\b", t):
            return "Bakery > English Muffins", identity or "English Muffins"
        if re.search(r"\brolls?\b", t):
            return "Bakery > Rolls", identity or "Rolls"
        if re.search(r"\bbuns?\b", t):
            return "Bakery > Buns", identity or "Buns"
        if re.search(r"\bbreads?\b|\bloaves?\b", t):
            return "Bakery > Bread", identity or "Bread"

    if bfc_lower == "pickles, olives, peppers & relishes":
        # 1.7k misrouted. Pantry-family default; sub-routed by product type.
        if re.search(r"\bolives?\b", t):
            return "Pantry > Olives", identity or "Olives"
        if re.search(r"\bpickles?\b", t):
            return "Pantry > Pickles", identity or "Pickles"
        if re.search(r"\bpeppers?\b", t) and not re.search(r"\bpepper\s+(sauce|seasoning|spice)\b", t):
            return "Pantry > Peppers", identity or "Peppers"
        if re.search(r"\brelish(?:es)?\b", t):
            return "Pantry > Relish", identity or "Relish"

    if bfc_lower == "other deli":
        # 1.7k SKUs span everything. Default by title.
        if re.search(r"\bhummus\b", t):
            return "Pantry > Dips & Spreads", "Hummus"
        if re.search(r"\bdip\b", t):
            return "Pantry > Dip", identity or "Dip"
        if re.search(r"\bsalad\b", t) and not re.search(r"\bsalad\s+dressing\b", t):
            return "Meal > Salads", identity or "Salad"
        if re.search(r"\bcheese\b", t) and not re.search(r"\b(plant[\s-]?based|vegan|alternative|dairy[\s-]?free)\b", t):
            return "Dairy > Cheese", identity or "Cheese"
        if re.search(r"\bdeli\s+meat\b|\bham\b|\bturkey\s+breast\b|\bsalami\b|\bpastrami\b|\bcorned\s+beef\b", t):
            return "Meat & Seafood > Charcuterie", identity or "Deli Meat"
        if re.search(r"\bsushi\b|\bsashimi\b|\bnigiri\b|\bmaki\b", t):
            return "Meal > Sushi", identity or "Sushi"

    if bfc_lower in ("frozen patties and burgers", "frozen patties & burgers"):
        # Sub-route by protein from title
        if re.search(r"\b(beef|hamburger)\b", t) and not re.search(r"\bcheeseburger\b", t):
            return "Meat & Seafood > Beef > Patties", identity or "Beef Patties"
        if re.search(r"\bcheeseburger\b", t):
            return "Meat & Seafood > Beef > Patties", "Cheeseburger Patties"
        if re.search(r"\bchicken\b", t):
            return "Meat & Seafood > Poultry > Chicken > Patties", identity or "Chicken Patties"
        if re.search(r"\bturkey\b", t):
            return "Meat & Seafood > Poultry > Turkey > Patties", identity or "Turkey Patties"
        if re.search(r"\b(veggie|black\s+bean|beyond|impossible|plant[\s-]?based|vegan)\b", t):
            return "Meal > Plant Based", identity or "Veggie Burgers"
        if re.search(r"\bsalmon\b", t):
            return "Meat & Seafood > Salmon > Patties", "Salmon Patties"

    if bfc_lower == "butter & spread":
        if re.search(r"\bpeanut\s+butter\b", t):
            return "Pantry > Nut Butters", "Peanut Butter"
        if re.search(r"\balmond\s+butter\b", t):
            return "Pantry > Nut Butters", "Almond Butter"
        if re.search(r"\bcashew\s+butter\b", t):
            return "Pantry > Nut Butters", "Cashew Butter"
        if re.search(r"\bsunflower\s+butter\b", t):
            return "Pantry > Nut Butters", "Sunflower Seed Butter"
        if re.search(r"\b(plant[\s-]?based|vegan|dairy[\s-]?free)\s+(butter|spread)\b", t):
            return "Pantry > Plant Based Butter", identity or "Plant Based Butter"
        if re.search(r"\bbutter\b", t):
            return "Dairy > Butter", identity or "Butter"

    if bfc_lower == "savoury bakery products":
        if re.search(r"\bpizza\b", t):
            return "Frozen > Pizza" if "frozen" in t else "Meal > Pizza", identity or "Pizza"
        if re.search(r"\bpretzel\s+(stick|bite|nugget)\b", t):
            return "Snack > Pretzels", identity or "Pretzels"
        if re.search(r"\bsausage\s+roll\b", t):
            return "Bakery > Sausage Rolls", identity or "Sausage Rolls"
        if re.search(r"\bquiche\b", t):
            return "Bakery > Quiche", identity or "Quiche"
        if re.search(r"\bempanada\b", t):
            return "Bakery > Empanadas", identity or "Empanadas"

    if bfc_lower == "frozen prepared sides":
        if re.search(r"\b(potato|fries|hash\s+brown|tater\s+tot)", t):
            return "Frozen > Potatoes", identity or "Potatoes"
        if re.search(r"\b(broccoli|cauliflower|spinach|kale|carrots?|peas|corn|brussels?|asparagus|green\s+beans?)\b", t):
            return "Frozen > Vegetables", identity or "Vegetables"
        if re.search(r"\brice\b", t):
            return "Frozen > Rice", identity or "Rice"
        if re.search(r"\bpasta\b|\bnoodle\b", t):
            return "Frozen > Pasta", identity or "Pasta"

    if bfc_lower == "lunch snacks & combinations":
        if re.search(r"\bsalad\b", t):
            return "Meal > Salads", identity or "Salad"
        if re.search(r"\bsandwich\b", t):
            return "Meal > Sandwiches", identity or "Sandwich"
        if re.search(r"\bwrap\b", t):
            return "Meal > Wraps", identity or "Wrap"
        if re.search(r"\b(lunchable|lunch\s+pack|protein\s+pack|snack\s+pack)\b", t):
            return "Meal > Lunch Packs", identity or "Lunch Pack"

    if bfc_lower == "baking decorations & dessert toppings":
        if re.search(r"\bsprinkles?\b|\bjimmies\b|\bnonpareils?\b|\bsanding\s+sugar\b", t):
            return "Pantry > Baking Decorations", identity or "Sprinkles"
        if re.search(r"\bfrosting\b|\bicing\b", t):
            return "Pantry > Frosting", identity or "Frosting"
        if re.search(r"\bsyrup\b|\btopping\b", t):
            return "Pantry > Sweeteners", identity or "Syrup"

    return None


_BFC_TO_FORCED_FAMILY: dict[str, tuple[str, str | None]] = {
    # When the cleanup pipeline routed an SKU to Bakery > Pastry > X based
    # on a TITLE flavor-word (Churro, Cookie, Pizza), but the BFC clearly
    # indicates a different product family, force the family.
    # Format: bfc_lower → (family, default_type_hint)
    "popcorn, peanuts, seeds & related snacks": ("Snack", "Trail Mix"),
    "snack, energy & granola bars":             ("Snack", "Bars"),
    "chips, pretzels & snacks":                 ("Snack", None),
    "chewing gum & mints":                      ("Snack", "Candy"),
    "ice cream & frozen yogurt":                ("Frozen", "Ice Cream"),
    "other frozen desserts":                    ("Frozen", None),
    "puddings & custards":                      ("Dairy", "Pudding"),
    "cereal":                                   ("Pantry", "Cereal"),
    "processed cereal products":                ("Pantry", "Cereal"),
    "other snacks":                             ("Snack", None),
    "chocolate":                                ("Snack", "Chocolate Candy"),
    # NOTE: BFCs with explicit specialized handlers later in _forced_base
    # (Candy, Powdered Drinks, Sushi, Cookies & Biscuits, Yogurt) are
    # intentionally NOT in this map — those have title-aware sub-routing below.
}


def _forced_base(row: Mapping[str, str]) -> tuple[str, str] | None:
    title = row.get("title", "") or ""
    bfc = row.get("branded_food_category", "") or ""
    category = row.get("category_path_fixed", "") or ""
    identity = row.get("product_identity_fixed", "") or ""
    blob = _title_blob(row)
    bfc_lower = bfc.strip().lower()

    frozen_dessert_route = _frozen_dessert_route(row)
    if frozen_dessert_route:
        return frozen_dessert_route

    # A2 (Codex insight): Title-level salad detection. When title says SALAD
    # (excluding salad-dressing, fruit-salad, salad-flavored snacks), route
    # to Meal > Salads regardless of BFC. Catches BFC=Pickles SKUs that are
    # actually salads (1,011 SKUs).
    if re.search(r"\bsalad\b", title, re.I) and \
       not re.search(r"\bsalad\s+dressing\b", title, re.I) and \
       not re.search(r"\bfruit\s+salad\b", title, re.I) and \
       not re.search(r"\bsalad\s+(chip|cracker|kit|mix|seasoning|topping)\b", title, re.I):
        return "Meal > Salads", identity or "Salad"

    # A3 (Codex insight): Real-churro detection. When the SKU is genuinely
    # a churro pastry product (not just churro-flavored), route to
    # Bakery > Pastry > Churros.
    if re.search(r"\bchurros?\b", title, re.I) and \
       (re.search(r"\bchurro\s+(doughnut|pastry|fritter|stick|bite|filled)\b", title, re.I) or
        re.search(r"\bbeyond\s+churros?\b|\btio\s+pepe\b|\bchurro\s+house\b", title, re.I) or
        re.search(r"^cinnamon\s+sugar\s+churros?\s*$", title, re.I)):
        if bfc_lower in {"croissants, sweet rolls, muffins & other pastries",
                         "bakery", "frozen bread & dough",
                         "savoury bakery products", ""}:
            return "Bakery > Pastry > Churros", "Churros"

    creamer_route = _coffee_creamer_route(title, identity)
    if creamer_route and (
        bfc_lower == "milk additives"
        or _token_key(category).startswith(("beverage plant milk", "bakery pastry", "bakery biscotti", "pantry creamer", "pantry mix"))
        or _token_key(row.get("canonical_path", "") or "").startswith(("beverage plant milk", "bakery pastry", "bakery biscotti", "pantry creamer", "pantry mix"))
    ):
        return creamer_route

    if bfc_lower in {"coffee", "other drinks"}:
        coffee_route = _coffee_route(title, identity)
        if coffee_route:
            return coffee_route

    if bfc_lower in SNACK_BAR_BFCS and re.search(r"\bbars?\b", f"{title} {identity}", re.I):
        return _snack_bar_route(title, identity)

    if bfc_lower in CHARCUTERIE_ROLL_BFCS:
        roll_route = _charcuterie_roll_route(title, identity, bfc_lower)
        if roll_route:
            return roll_route

    churro_flavor_route = _churro_flavor_identity_route(row)
    if churro_flavor_route:
        return churro_flavor_route

    churro_hijack_route = _bakery_churro_hijack_route(row)
    if churro_hijack_route:
        return churro_hijack_route

    if bfc_lower in CEREAL_BFCS:
        if re.search(r"\bgranola\b", f"{title} {identity}", re.I):
            return "Snack > Granola", "Granola"
        if re.search(r"\bcereal\b", f"{title} {identity}", re.I):
            return "Pantry > Cereal", "Cereal"

    if bfc_lower == "chocolate":
        return "Snack > Chocolate Candy", identity if identity and not re.search(r"\b(churros?|puffs?)\b", identity, re.I) else "Chocolate Candy"

    # Phase-2 per-BFC title-cue sub-router (Wholesome Snacks, Breads & Buns,
    # Pickles/Olives, Other Deli, Frozen Patties, Butter & Spread, Savoury
    # Bakery, Frozen Prepared Sides, Lunch Snacks, Baking Decorations).
    sub = _bfc_title_subroute(bfc_lower, title, identity)
    if sub:
        return sub

    # BFC family-veto: when the EXISTING category_path family conflicts with
    # the BFC's expected family, force-route to the BFC-expected family.
    # Catches cleanup-pipeline hijacks: "CHURRO TRAIL MIX" + BFC=Popcorn was
    # routed to Bakery > Pastry > Churros (wrong — should be Snack > Trail Mix).
    cur_family = category.split(" > ", 1)[0] if category else ""
    forced_family_info = _BFC_TO_FORCED_FAMILY.get(bfc_lower)
    if forced_family_info and cur_family == "Bakery":
        forced_family, type_hint = forced_family_info
        if forced_family != "Bakery":
            type_seg = type_hint or identity or "Other"
            return f"{forced_family} > {type_seg}", identity or type_seg

    plant_context = (
        bfc_lower == "plant based milk"
        or _token_key(category).startswith("beverage plant milk")
        or _token_key(row.get("canonical_path", "") or "").startswith("beverage plant milk")
    )
    if plant_context:
        return "Beverage > Plant Milk", _detect_plant_milk_identity(title + " " + identity)

    # BUG #6 + #9: plant-based cheese alternatives + vegetarian frozen meats
    # routed to Dairy/Meat. CHECKED BEFORE the BFC=Cheese rule so plant-based
    # cheese alternatives don't get force-routed to Dairy > Cheese.
    if re.search(r"\b(plant[\s-]?based|vegan|dairy[\s-]?free|alternative)\b", title, re.I) and \
       re.search(r"\bcheese\b", title, re.I):
        return "Pantry > Plant Based Cheese", identity or "Plant Based Cheese"
    if bfc_lower == "vegetarian frozen meats" or \
       (re.search(r"\b(meat[\s-]?less|plant[\s-]?based|vegan|vegetarian|impossible|beyond)\b", title, re.I) and
        re.search(r"\b(burger|sausage|chicken|beef|ground|crumbles?|patty|patties|nuggets?|meatball)", title, re.I)):
        return "Meal > Plant Based", identity or "Plant Based"

    # BUG #13: Hot dog ROLLS/BUNS routed to Meal > Sandwiches > Hot Dog.
    # When title contains "hot dog" AND "roll"/"bun"/"buns", it's the BREAD
    # (bun), not the meat. Goes to Bakery > Buns. CHECKED EARLY so it
    # overrides downstream homogenize and PI-based routing.
    if re.search(r"\bhot\s*dog\b", title, re.I) and \
       re.search(r"\b(rolls?|buns?)\b", title, re.I):
        return "Bakery > Buns", "Hot Dog Buns"

    # Sandwich title detection — title clearly says "SANDWICH(ES)" and
    # is not a sandwich-cookie/sandwich-cracker. Routes to Meal > Sandwiches
    # regardless of BFC=Breads & Buns hijack.
    if re.search(r"\bsandwich(?:es)?\b", title, re.I) and \
       not re.search(r"\b(sandwich\s+cookies?|cookie\s+sandwich|cracker\s+sandwich|"
                     r"ice\s+cream\s+sandwich|breakfast\s+sandwich)\b", title, re.I):
        if _is_sandwich_carrier_identity(identity):
            return "Meal > Sandwiches", _sandwich_identity(title)
        return "Meal > Sandwiches", identity if (identity and identity.lower() not in {"sandwich", "bread", "bun", "buns"}) else _sandwich_identity(title)

    breakfast_reference = " ".join([
        identity,
        row.get("fndds_desc", "") or "",
        row.get("esha_desc", "") or "",
        row.get("matched_key", "") or "",
    ])
    if _looks_like_breakfast_sandwich(title, breakfast_reference):
        root = "Frozen > Breakfast Sandwiches" if "frozen" in bfc_lower or re.search(r"\bfrozen\b", title, re.I) else "Meal > Breakfast Sandwiches"
        return root, "Breakfast Sandwich"

    # BUG #7: Danish blue cheese / cream cheese / etc. — "Danish" regex hijacks
    # towards Pastry. When BFC is Cheese AND title says cheese, force
    # Dairy > Cheese AND override any pastry-leaked product_identity
    # (e.g., PI="Danishes" is wrong for Danish Blue Cheese — should be Blue Cheese).
    # NOTE: "Cheese Danish" pastries have BFC="Cakes/Cupcakes/Snack Cakes" (not
    # "Cheese"), so this rule does NOT touch them — they stay in Bakery > Pastry.
    if bfc_lower == "cheese" and re.search(r"\bcheese\b", blob):
        # Detect specific cheese type from title; PI may be polluted with
        # pastry/danish words from earlier pipeline regex hijacks.
        cheese_type = "Cheese"
        # Specific cheese types — most-specific first
        if re.search(r"\bdanish\s+blue\s+cheese\b|\bdanablu\b|\bblue\s+cheese\b", title, re.I):
            cheese_type = "Blue Cheese"
        elif re.search(r"\bcream\s+cheese\b", title, re.I):
            cheese_type = "Cream Cheese"
        elif re.search(r"\bcottage\s+cheese\b", title, re.I):
            cheese_type = "Cottage Cheese"
        elif re.search(r"\bricotta\b", title, re.I):
            cheese_type = "Ricotta"
        elif re.search(r"\bgoat\s+cheese\b|\bchevre\b", title, re.I):
            cheese_type = "Goat Cheese"
        elif re.search(r"\bfeta\b", title, re.I):
            cheese_type = "Feta"
        elif re.search(r"\bmozzarella\b", title, re.I):
            cheese_type = "Mozzarella"
        elif re.search(r"\bcheddar\b", title, re.I):
            cheese_type = "Cheddar"
        elif re.search(r"\bparmesan\b|\bparmigiano\b", title, re.I):
            cheese_type = "Parmesan"
        elif re.search(r"\bswiss\b|\bemmental\b|\bemmenthaler\b", title, re.I):
            cheese_type = "Swiss"
        elif re.search(r"\bbrie\b", title, re.I):
            cheese_type = "Brie"
        elif re.search(r"\bcamembert\b", title, re.I):
            cheese_type = "Camembert"
        elif re.search(r"\bgouda\b", title, re.I):
            cheese_type = "Gouda"
        elif re.search(r"\bprovolone\b", title, re.I):
            cheese_type = "Provolone"
        elif re.search(r"\basiago\b", title, re.I):
            cheese_type = "Asiago"
        elif re.search(r"\bromano\b", title, re.I):
            cheese_type = "Romano"
        elif re.search(r"\bhavarti\b", title, re.I):
            cheese_type = "Havarti"
        elif re.search(r"\bgorgonzola\b", title, re.I):
            cheese_type = "Gorgonzola"
        elif re.search(r"\bmonterey\s*jack\b|\bpepper\s*jack\b", title, re.I):
            cheese_type = "Monterey Jack"
        elif identity and identity.lower() not in {"danishes", "danish", "pastry", "pastries", "cake", "cakes", "buns", "rolls"}:
            # Use existing PI if it's a sensible cheese-related word
            cheese_type = identity
        return "Dairy > Cheese", cheese_type

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

    if bfc_lower == "vegetable and lentil mixes":
        if re.search(r"\bwasabi\s+peas?\b", title, re.I):
            return "Snack > Veggie Snacks", "Wasabi Peas"
        if re.search(r"\bagar[\s-]?agar\b", f"{title} {identity}", re.I):
            return "Pantry > Baking Ingredients", "Agar Powder"

    bean_identity = _bean_legume_identity(title, identity)
    if bean_identity and (
        bfc_lower in BEAN_BFCS
        or _token_key(category).startswith("pantry baking mix")
        or _token_key(row.get("canonical_path", "") or "").startswith("pantry baking mix")
    ):
        return "Pantry > Beans", bean_identity

    if bfc_lower in {"cereal", "processed cereal products"}:
        if re.search(r"\bgranola\b", identity_evidence, re.I):
            return "Snack > Granola", "Granola"
        if re.search(r"\bcereal\b", identity_evidence, re.I):
            return "Pantry > Cereal", "Cereal"

    if bfc_lower == "chocolate":
        return "Snack > Chocolate Candy", identity if identity and not re.search(r"\b(churros?|puffs?)\b", identity, re.I) else "Chocolate Candy"

    baking_mix_identity = _baking_mix_identity(title, identity)
    if baking_mix_identity and (
        bfc_lower in {"baking/cooking mixes/supplies", "bread & muffin mixes", "cake, cookie & cupcake mixes"}
        or _token_key(category).startswith(("bakery pastry", "pantry baking mix"))
        or _token_key(row.get("canonical_path", "") or "").startswith(("bakery pastry", "pantry baking mix"))
    ) and bfc_lower != "vegetable and lentil mixes":
        return "Pantry > Baking Mixes", baking_mix_identity

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

    root_starch_identity = _root_starch_side_identity(title, identity)
    if root_starch_identity and (
        bfc_lower == "vegetable and lentil mixes"
        or _token_key(category).startswith("pantry baking mix")
        or _token_key(row.get("canonical_path", "") or "").startswith("pantry baking mix")
    ):
        return "Pantry > Packaged Sides", root_starch_identity

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

    dried_vegetable_identity = _dried_vegetable_identity(title, identity)
    if dried_vegetable_identity and (
        bfc_lower == "vegetable and lentil mixes"
        or _token_key(category).startswith("pantry baking mix")
        or _token_key(row.get("canonical_path", "") or "").startswith("pantry baking mix")
    ):
        return "Pantry > Dried Vegetables", dried_vegetable_identity

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

    pie_crust_route = _pie_crust_identity(title, identity)
    if pie_crust_route and (
        bfc_lower in {"crusts & dough", "sweet bakery products", "breads & buns", "flavored snack crackers", "cake, cookie & cupcake mixes"}
        or _token_key(category).startswith(("bakery pie", "bakery pie crust", "pantry baking mix"))
        or _token_key(row.get("canonical_path", "") or "").startswith(("bakery pie", "bakery pie crust", "pantry baking mix"))
    ):
        return pie_crust_route

    ice_cream_cone_identity = _ice_cream_cone_identity(title, identity)
    if ice_cream_cone_identity and (
        "ice cream" in bfc_lower
        or bfc_lower in COOKIE_BFCS
        or "crackers & biscotti" in bfc_lower
        or _token_key(category).startswith(("pantry baking mix", "snack ice cream cone", "frozen ice cream cone", "frozen ice cream"))
        or _token_key(row.get("canonical_path", "") or "").startswith(("pantry baking mix", "snack ice cream cone", "frozen ice cream cone", "frozen ice cream"))
    ):
        return "Snack > Ice Cream Cones", ice_cream_cone_identity

    cocktail_identity = _cocktail_mixer_identity(title, identity)
    if cocktail_identity and (
        bfc_lower == "alcohol"
        or _token_key(category).startswith((
            "pantry baking mix",
            "pantry mix",
            "pantry drink mix",
            "beverage mix",
            "beverage juice mix",
        ))
        or _token_key(row.get("canonical_path", "") or "").startswith((
            "pantry baking mix",
            "pantry mix",
            "pantry drink mix",
            "beverage mix",
            "beverage juice mix",
        ))
    ):
        return "Beverage > Cocktail Mixers", cocktail_identity

    beverage_mix_route = _beverage_mix_route(title, identity)
    if beverage_mix_route and (
        bfc_lower in {
            "alcohol",
            "liquid water enhancer",
            "sport drinks",
            "other drinks",
            "energy, protein & muscle recovery drinks",
        }
        or _token_key(category).startswith(("pantry mix", "pantry drink mix"))
        or _token_key(row.get("canonical_path", "") or "").startswith(("pantry mix", "pantry drink mix"))
    ):
        return beverage_mix_route

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
        if _looks_like_breakfast_sandwich(title, breakfast_reference):
            return "Frozen > Breakfast Sandwiches", "Breakfast Sandwich"
        return "Frozen > Breakfast", _sandwich_identity(title)

    if bfc_lower in BREAKFAST_SANDWICH_BFCS:
        if _looks_like_breakfast_sandwich(title, breakfast_reference):
            return "Meal > Breakfast Sandwiches", "Breakfast Sandwich"
        return "Meal > Breakfast", _sandwich_identity(title)

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
        if re.search(r"\bturkey\b", title, re.I):
            return "Snack > Jerky", "Turkey Jerky"
        if re.search(r"\bpork\b", title, re.I):
            return "Snack > Jerky", "Pork Jerky"
        if re.search(r"\bsalmon\b|\btuna\b|\bfish\b", title, re.I):
            return "Snack > Jerky", "Fish Jerky"
        return "Snack > Jerky", "Beef Jerky"

    # BUG #13: Hot dog ROLLS/BUNS routed to Meal > Sandwiches > Hot Dog.
    # When title contains "hot dog" AND "roll"/"bun"/"buns", it's the BREAD
    # (bun), not the meat. Goes to Bakery > Buns.
    if re.search(r"\bhot\s*dog\b", title, re.I) and \
       re.search(r"\b(rolls?|buns?)\b", title, re.I):
        return "Bakery > Buns", "Hot Dog Buns"

    # BUG #4: Title says FROZEN/FRESHLY FROZEN but path goes to Pantry > Canned.
    # When title clearly says frozen, route to Frozen family.
    if re.search(r"\b(freshly\s+frozen|fresh\s+frozen|just\s+(?:picked\s+and\s+)?(?:quickly\s+)?frozen|flash\s+frozen|individually\s+(?:quick\s+)?frozen|iqf)\b", title, re.I):
        # Determine sub-type from title
        if re.search(r"\b(green\s+beans?|peas|corn|carrots?|broccoli|spinach|cauliflower|edamame|brussel|asparagus)\b", title, re.I):
            return "Frozen > Vegetables", identity or "Vegetables"
        if re.search(r"\b(berries|berry|strawberr|blueberr|raspberr|blackberr|cherry|cherries|peach|mango|pineapple)\b", title, re.I):
            return "Frozen > Fruit", identity or "Fruit"

    # BUG #14: title says "Fresh" but path is Frozen. When title starts with
    # "FRESH " (not "FRESHLY FROZEN"), and current path is Frozen, force Produce.
    if re.match(r"^fresh\s", title.lower()) and not re.search(r"freshly\s+frozen|fresh\s+frozen", title, re.I):
        cp_now = (row.get("canonical_path", "") or "").strip()
        if cp_now.startswith("Frozen") and re.search(r"\b(fruit|vegetable|produce|herb|salad)\b", title, re.I):
            return "Produce > Fresh", identity or "Fresh"

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

    if _word_set(identity).issubset(category_words):
        if len(category_segments) >= 2 and re.search(r"[&,/]", category_segments[-1]):
            return PATH_SEP.join(dedupe_segments(category_segments + [identity]))
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
    variant = row.get("variant", "") or ""
    if category_path == "Beverage > Cocktail Mixers" and identity in {
        "Cocktail Mix",
        "Cocktail Rimmer",
        "Cocktail Syrup",
        "Cocktail Brine",
    }:
        style = _cocktail_style_variant(row.get("title", "") or "")
        if style:
            existing = {_normalize_token(token) for token in _facet_values(variant)}
            if _normalize_token(style) not in existing:
                variant = f"{style}|{variant}" if variant else style
    modifier = derive_modifier(
        variant=variant,
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

# ============================================================================
# RUNTIME GUARD — keep this in sync with _canonical_from_category_identity.
# Combined parent shelves such as "Sauces & Salsas", "Coatings & Breadings",
# and "Rice & Grains" are real retail parents. Do not strip them.
# ============================================================================

def _canonical_from_category_identity_GUARDED(category_path: str, identity: str) -> str:
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

    if _word_set(identity).issubset(category_words):
        if len(category_segments) >= 2 and re.search(r"[&,/]", category_segments[-1]):
            return PATH_SEP.join(dedupe_segments(category_segments + [identity]))
        return PATH_SEP.join(category_segments)

    return PATH_SEP.join(dedupe_segments(category_segments + [identity]))


# Replace the (linter-mangled) original with the guarded version
_canonical_from_category_identity = _canonical_from_category_identity_GUARDED
