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

    def add_level(tokens: list[str], *, sort_claims: bool = False) -> None:
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
            levels.append(" ".join(_prettify(token) for token in kept))

    add_level(l1)
    add_level(l2, sort_claims=True)
    add_level(l3)
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

    # Authoritative BFC-driven routes — when BFC alone fully determines
    # family+type, force the route regardless of title regex hijacks.
    if bfc_lower == "sushi":
        return "Meal > Sushi", identity or "Sushi"
    if bfc_lower in {"cookies & biscuits", "biscuits/cookies",
                     "biscuits/cookies (shelf stable)"}:
        return "Bakery > Cookies", identity or "Cookies"
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

    # Combined-parent BFC names ("Sauces & Salsas", "Hot Dogs & Sausages",
    # "Salad Dressing & Mayonnaise", etc.) must NOT appear in canonical_path.
    # When the category last segment contains '&', ',', or '/', REPLACE it
    # with the more-specific identity rather than appending.
    if len(category_segments) >= 2:
        last_seg = category_segments[-1]
        if re.search(r"[&,/]", last_seg):
            return PATH_SEP.join(
                dedupe_segments(category_segments[:-1] + [identity])
            )

    identity_key = _token_key(identity)
    category_keys = {_token_key(seg) for seg in category_segments}
    category_words: set[str] = set()
    for seg in category_segments:
        category_words.update(_word_set(seg))

    if identity_key in category_keys:
        return PATH_SEP.join(category_segments)

    if _word_set(identity).issubset(category_words):
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
