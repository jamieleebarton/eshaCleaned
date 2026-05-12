#!/usr/bin/env python3
"""Shared HTC/tree helpers for the explicit v1 resolver path.

This module is deliberately small and deterministic.  It does not read the
learned contract artifacts.  Retail products get an HTC code from the product
tree identity, not from noisy title/component text.
"""
from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from htc.encoder import (
    FAMILY_RULES,
    FORM_RULES,
    PROC_RULES,
    PTYPE_RULES,
    HTC,
    code_from_parts,
    crockford_check,
    encode,
)
from htc.food_slots import default_registry  # noqa: E402

WS_RE = re.compile(r"[^a-z0-9]+")
HTC_CODE_RE = re.compile(r"([0-9A-Z][0-9A-Z]{6}[$=0-9A-Z])")

TREE_SPICE_HERB_IDENTITIES = {
    "allspice", "anise", "asafoetida", "basil", "bay leaf", "bay leave",
    "bay leaves", "cardamom", "cilantro", "clove", "cloves", "coriander",
    "cumin", "dill", "fennel", "fenugreek", "ginger", "ginger root",
    "gingerroot", "mace", "marjoram", "mint", "nutmeg", "oregano",
    "paprika", "parsley", "rosemary", "saffron", "sage", "tarragon",
    "thyme", "turmeric", "vanilla", "vanilla extract",
}

TOKEN_ALIASES = {
    "breadcrumb": {"bread", "crumb"},
    "breadcrumbs": {"bread", "crumb"},
    "cornstarch": {"corn", "starch"},
    "gingerroot": {"ginger", "root"},
    "scallion": {"green", "onion"},
}

IDENTITY_STOP = {
    "a", "an", "and", "brand", "chopped", "coarse", "coarsely", "cold",
    "cooked", "cracked", "crushed", "cubed", "diced", "divided", "drained",
    "dry", "dried", "extra", "finely", "fresh", "frozen", "good", "grade",
    "ground", "halved", "hot", "large", "lean", "lightly", "medium",
    "melted", "minced", "natural", "of", "organic", "peeled", "pitted",
    "premium", "raw", "ripe", "roughly", "seeded", "skinless", "sliced",
    "small", "softened", "stemmed", "the", "thinly", "to", "trimmed",
    "washed", "whole", "with",
}

PACKAGING_NOISE = {
    "0", "1", "10", "100", "12", "14", "15", "16", "18", "2", "20", "24",
    "25", "3", "32", "4", "40", "5", "50", "6", "64", "7", "75", "8", "9",
    "bag", "bottle", "box", "brand", "can", "carton", "count", "ct", "each",
    "family", "fl", "food", "foods", "fresh", "great", "grocery", "kroger",
    "lb", "lbs", "oz", "pack", "pkg", "select", "size", "truth", "value",
    "walmart",
}

GENERIC_MODIFIER_IDENTITIES = {
    "dip", "sauce", "seasoning", "spice blend", "salsa", "soup",
    "single entree", "family entree", "pasta dish", "salad", "sandwich",
    "pizza", "marinade",
}

FLAVOR_SLOT_IDENTITIES = {
    "sparkling water",
}

FLAVOR_SLOT_MODIFIER_NOISE = {
    "caffeinated", "caffeine free", "diet", "flavored", "natural",
    "naturally flavored", "organic", "original", "plain", "sparkling",
    "seltzer", "sugar free", "unsweetened", "zero", "zero calorie",
    "zero sugar",
}

DRIED_FRUIT_IDENTITIES = {
    "apricot", "apricots", "currant", "currants", "date", "dates",
    "fig", "figs", "prune", "prunes", "raisin", "raisins", "sultana",
    "sultanas",
}


@dataclass(frozen=True)
class HtcParts:
    code: str
    group: str
    family: str
    food: str
    form: str
    processing: str
    ptype: str
    check: str
    confidence: float
    source: str


def normalize_surface(value: str) -> str:
    folded = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode("ascii")
    return " ".join(WS_RE.sub(" ", folded.lower()).split())


def singular_word(value: str) -> str:
    if value in {"chilies", "chillis", "chiles"}:
        return "chili"
    if value == "leaves":
        return "leaf"
    if value.endswith("oes") and len(value) > 4:
        return value[:-2]
    if value.endswith("ies") and len(value) > 4:
        return value[:-3] + "y"
    if value.endswith("es") and len(value) > 3 and value[-3] in "sxz":
        return value[:-2]
    if value.endswith("s") and len(value) > 2 and not value.endswith("ss"):
        return value[:-1]
    return value


def normalize_key(value: str) -> str:
    return " ".join(singular_word(part) for part in normalize_surface(value).split())


def identity_tokens(value: str) -> set[str]:
    surface = normalize_surface(value)
    tokens = {
        singular_word(part)
        for part in surface.split()
        if len(part) > 1 and part not in IDENTITY_STOP
    }
    expanded = set(tokens)
    for token in tokens:
        expanded.update(TOKEN_ALIASES.get(token, ()))
    if "corn starch" in surface:
        expanded.add("cornstarch")
    if "bread crumb" in surface or "bread crumbs" in surface:
        expanded.add("breadcrumb")
    if "green onion" in surface or "spring onion" in surface:
        expanded.add("scallion")
    if "bay leaf" in surface or "bay leaves" in surface:
        expanded.add("leaf")
    return expanded


def primary_identity_token(value: str) -> str:
    toks = [
        singular_word(part)
        for part in normalize_surface(value).split()
        if len(part) > 1 and part not in IDENTITY_STOP
    ]
    return toks[-1] if toks else ""


def normalize_htc_code(value: str) -> str:
    code = (value or "").strip().upper()
    if code.startswith("~"):
        code = code[1:]
    match = HTC_CODE_RE.search(code)
    return match.group(1) if match else code[:8]


def decode_htc(code: str, confidence: float = 0.0, source: str = "") -> HtcParts:
    code = normalize_htc_code(code)
    if len(code) >= 8:
        return HtcParts(
            code=code[:8],
            group=code[0],
            family=code[1],
            food=code[2:4],
            form=code[4],
            processing=code[5],
            ptype=code[6],
            check=code[7],
            confidence=confidence,
            source=source,
        )
    return HtcParts("", "", "", "", "", "", "", "", confidence, source)


def _match_first_for_group(group: str, text: str) -> str:
    for pattern, code in FAMILY_RULES.get(group, []):
        if pattern.search(text or ""):
            return code
    return "0"


def _match_first(rules: list[tuple[re.Pattern, str]], text: str) -> str:
    for pattern, code in rules:
        if pattern.search(text or ""):
            return code
    return "0"


def modifier_can_fill_food_slot(canonical_path: str, product_identity: str, modifier: str) -> bool:
    pid_key = normalize_key(product_identity)
    modifier_key = normalize_key(modifier)
    if not modifier_key or modifier_key in FLAVOR_SLOT_MODIFIER_NOISE:
        return False
    if all(part in PACKAGING_NOISE for part in modifier_key.split()):
        return False
    path = normalize_surface(canonical_path)
    return pid_key in FLAVOR_SLOT_IDENTITIES or path.startswith("beverage sparkling water")


def flavor_slot_identity_key(canonical_path: str, product_identity: str) -> str:
    pid_key = normalize_key(product_identity)
    path = normalize_surface(canonical_path)
    if pid_key in FLAVOR_SLOT_IDENTITIES:
        return pid_key
    if path.startswith("beverage sparkling water"):
        return "sparkling water"
    return ""


def food_slot_modifier_from_text(canonical_path: str, product_identity: str, text: str) -> str:
    """Infer a flavor modifier from the HTC food-slot registry.

    This is for products whose tree identity is known but whose flavor facet was
    dropped by upstream evidence.  It uses the registry's existing slot
    vocabulary, so "lemon lime" wins over the shorter "lime" slot.
    """
    target_pid_key = flavor_slot_identity_key(canonical_path, product_identity)
    if not target_pid_key:
        return ""

    text_key = normalize_key(text)
    if not text_key:
        return ""
    haystack = f" {text_key} "

    best: tuple[int, int, str] | None = None
    for entry in default_registry().entries:
        if normalize_key(entry.product_identity_fixed) != target_pid_key:
            continue
        modifier = (entry.primary_modifier or "").strip()
        modifier_key = normalize_key(modifier)
        if not modifier_key or modifier_key in FLAVOR_SLOT_MODIFIER_NOISE:
            continue
        if f" {modifier_key} " not in haystack:
            continue
        candidate = (len(modifier_key.split()), entry.row_count, modifier)
        if best is None or candidate > best:
            best = candidate
    return best[2] if best else ""


def group_from_tree_path(canonical_path: str, identity: str = "") -> str:
    """Map Hestia tree path/domain to an HTC group.

    This is path-first and intentionally more specific than raw title encoding.
    For example, `Snack > Nuts > Almonds` is group A, while
    `Snack > Chocolate Candy > Almonds` is group J.
    """
    path = normalize_surface(canonical_path)
    blob = f"{path} {normalize_surface(identity)}"

    if not path:
        return ""
    if "non food" in path:
        return "N"
    if "egg" in path and not re.search(r"egg noodle|egg roll|easter", blob):
        return "5"
    if "poultry" in path or re.search(r"\b(chicken|turkey|duck|goose)\b", blob):
        if "plant based" not in path:
            return "3"
    if "seafood" in path or re.search(r"\b(fish|shrimp|salmon|tuna|crab|lobster|clam|oyster)\b", blob):
        return "4"
    if path.startswith("meat seafood") or re.search(r"\b(beef|pork|bacon|ham|sausage|steak)\b", blob):
        if "plant based" not in path:
            return "2"
    if path.startswith("snack candy") or "candy" in path or "gum" in path:
        return "J"
    identity_key = normalize_key(identity)
    if identity_key in TREE_SPICE_HERB_IDENTITIES:
        return "E"
    if "nuts" in path or re.search(r"\b(nut|nuts|almond|cashew|pecan|walnut|pistachio|peanut|seed|seeds)\b", blob):
        if path.startswith("snack nuts") or path.startswith("pantry nuts") or "nut butter" in path:
            return "A"
    if "herb" in path or "spices seasonings" in path or "baking extracts" in path:
        return "E"
    if path.startswith("produce vegetables") or path.startswith("frozen vegetables") or "canned vegetables" in path:
        return "6"
    if path.startswith("produce fruit") or path.startswith("frozen frozen fruit") or "canned fruit" in path:
        return "7"
    if path.startswith("snack dried fruit") or "dried fruit" in path:
        if "chocolate candy" not in path and "candy" not in path:
            return "7"
    if normalize_key(identity) in DRIED_FRUIT_IDENTITIES and "candy" not in path:
        return "7"
    if "oil" in path or "cooking oil" in path or "ghee" in path:
        return "B"
    if path.startswith("dairy") or re.search(r"\b(milk|cheese|cream|butter|yogurt|yoghurt|kefir)\b", blob):
        return "1"
    if "sweetener" in path or "sugar" in path or "honey" in path or "syrup" in path:
        return "C"
    if path.startswith("beverage"):
        return "D"
    if "condiment" in path or "sauce" in path or "salsa" in path or "dressing" in path or "pickle" in path or "olive" in path or "vinegar" in path:
        return "F"
    if path.startswith("pantry beans") or "legume" in path or re.search(r"\b(bean|beans|lentil|chickpea)\b", blob):
        return "9"
    if (
        "rice" in path or "pasta" in path or "noodle" in path or "grain" in path
        or "flour" in path or "cereal" in path or "bread" in path
    ):
        return "8"
    if path.startswith("bakery") and re.search(r"\b(cookie|cake|pie|pastry|donut|cracker)\b", blob):
        return "G"
    if path.startswith("meal") or "prepared" in path or "frozen dinner" in path or "appetizer" in path:
        return "H"
    if path.startswith("snack"):
        return "J"
    if path.startswith("baby"):
        return "M"
    return ""


def recipe_group_hint(item: str, raw_group: str) -> str:
    key = normalize_surface(item)
    if re.search(r"\b(chili|chile|bell|jalapeno|serrano|poblano|habanero|anaheim|fresno)\s+peppers?\b", key):
        return "6"
    if re.search(r"\b(green|red|yellow|orange)\s+peppers?\b", key):
        return "6"
    if raw_group and raw_group != "0":
        return raw_group
    return ""


def htc_from_tree_identity(
    canonical_path: str,
    product_identity: str,
    modifier: str = "",
    *,
    raw_code: str = "",
    confidence: float = 0.95,
    source: str = "tree_identity",
) -> HtcParts:
    """Create an HTC code from tree identity plus optional raw form slots."""
    raw = decode_htc(raw_code)
    pid_key = normalize_key(product_identity)
    modifier_text = modifier if (
        pid_key in GENERIC_MODIFIER_IDENTITIES
        or modifier_can_fill_food_slot(canonical_path, product_identity, modifier)
    ) else ""
    identity_text = " ".join(part for part in (product_identity, modifier_text) if part).strip()
    if not identity_text:
        identity_text = product_identity or modifier or canonical_path

    base: HTC = encode(category="", description=identity_text, extra="")
    group = group_from_tree_path(canonical_path, product_identity) or base.group or raw.group
    if not group:
        group = "0"

    family_match_text = f"{identity_text} {normalize_key(identity_text)}"
    family = _match_first_for_group(group, family_match_text)
    if family == "0":
        family = _match_first_for_group(group, canonical_path)
    if family == "0" and base.group == group:
        family = base.family
    if family == "0" and raw.group == group:
        family = raw.family

    form = raw.form or _match_first(FORM_RULES, f"{identity_text} {canonical_path}")
    processing = raw.processing or _match_first(PROC_RULES, f"{identity_text} {canonical_path}")
    ptype = raw.ptype or _match_first(PTYPE_RULES, f"{identity_text} {canonical_path}")
    form = form or "0"
    processing = processing or "0"
    ptype = ptype or "0"
    registry = default_registry()
    entry = registry.lookup(group, family, identity_text)
    if not entry:
        any_entry = registry.lookup_any(identity_text)
        if any_entry and (
            not group
            or group == "0"
            or (
                any_entry.htc_group == group
                and (not family or family == "0" or any_entry.htc_family in {"", "0", family})
            )
        ):
            entry = any_entry
    if entry:
        if not group or group == "0":
            group = entry.htc_group
        if not family or family == "0":
            family = entry.htc_family
        food = entry.food_slot
    else:
        food = "00"
    code = code_from_parts(group, family, food)
    return HtcParts(
        code=code,
        group=group,
        family=family,
        food=food,
        form="0",
        processing="0",
        ptype="0",
        check=code[-1],
        confidence=confidence,
        source=source,
    )


def htc_compatible(
    recipe_group: str,
    recipe_family: str,
    product_group: str,
    product_family: str,
    *,
    require_family: bool = True,
) -> bool:
    if not recipe_group or recipe_group in {"0", "N"}:
        return False
    if recipe_group != product_group:
        return False
    if require_family and recipe_family and recipe_family != "0" and product_family and product_family != "0":
        return recipe_family == product_family
    return True


def path_bonus_for_group(group: str, canonical_path: str) -> float:
    path = normalize_surface(canonical_path)
    if not path:
        return 0.0
    if group == "A":
        return 50.0 if "nuts" in path or "seeds" in path else -50.0
    if group == "E":
        if "spices seasonings" in path or "herb" in path or "baking extracts" in path:
            return 50.0
        if "candy" in path or "gum" in path or "snack" in path:
            return -80.0
    if group == "3":
        return 50.0 if "poultry" in path or "chicken" in path else -80.0 if "dairy cheese" in path else 0.0
    if group == "5":
        return 50.0 if "egg" in path else -100.0 if "candy" in path or "easter" in path else 0.0
    if group == "6":
        return 35.0 if "vegetable" in path or "pepper" in path or "produce" in path else -50.0 if "snack" in path else 0.0
    if group == "7":
        if "dried fruit" in path:
            return 45.0
        return 35.0 if "fruit" in path or "produce" in path else -60.0 if "candy" in path or "snack" in path else 0.0
    if group == "1":
        return 35.0 if "dairy" in path or "ice cream" in path else -60.0 if "snack" in path else 0.0
    return 0.0


def sku_count_bonus(value: int) -> float:
    if value <= 0:
        return 0.0
    return min(20.0, math.log10(value + 1) * 8.0)


def title_noise_tokens(title: str, allowed: set[str]) -> set[str]:
    first = (title or "").split(",", 1)[0]
    return identity_tokens(first) - allowed - PACKAGING_NOISE


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]
