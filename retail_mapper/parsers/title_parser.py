#!/usr/bin/env python3
"""Stage 2 retail title parser.

This parser turns a branded-food title into the axis vector described in
PLAN.md. It is deliberately deterministic: all vocabulary comes from axes/*.tsv
and all routing decisions are written as small, auditable heuristics.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable


AXIS_FILES = {
    "FORM": "form.tsv",
    "CUT": "cut.tsv",
    "STORAGE": "storage.tsv",
    "PREPARATION_STATE": "preparation_state.tsv",
    "SWEETENER": "sweetener.tsv",
    "FAT": "fat.tsv",
    "SODIUM": "sodium.tsv",
    "DIET": "diet.tsv",
    "AUDIENCE": "audience.tsv",
    "DISH_TYPE": "dish_type.tsv",
    "COMBO_FORMAT": "combo_format.tsv",
    "FLAVOR_UNIVERSAL": "flavor_universal.tsv",
    "CATEGORY": "category.tsv",
    "COLOR": "color.tsv",
    "CUISINE": "cuisine.tsv",
    "BRAND_NOISE": "brand_noise.tsv",
    "STOPWORD": "stopwords.tsv",
}

OUTPUT_FIELDS = [
    "gtin_upc",
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
    "debug_matches",
    "axis_review_issues",
    "category_candidates",
    "form_candidates",
    "flavor_candidates",
    "unselected_category_candidates",
    "unselected_form_candidates",
    "unselected_flavor_candidates",
    "ambiguous_axis_terms",
    "unaccounted_tokens",
    "axis_coverage_score",
]

WORD_RE = re.compile(r"[a-z][a-z0-9]+")
NON_WORD_RE = re.compile(r"[^a-z0-9]+")

GENERIC_CATEGORY = {
    "beverage",
    "beverages",
    "drink",
    "drinks",
    "food",
    "foods",
    "juice",
    "smoothie",
    "milk",
    "powder",
    "mix",
    "mixes",
    "blend",
    "blends",
    "kit",
    "kits",
    "meal",
    "meals",
    "snack",
    "snacks",
    "water",
}

PLANT_MILK_BASES = {
    "almond",
    "oat",
    "soy",
    "coconut",
    "cashew",
    "pea",
    "rice",
    "hemp",
    "flax",
    "hazelnut",
    "sunflower",
}

PLANT_MILK_BASE_ALIASES = {
    "almonds": "almond",
    "oats": "oat",
    "soybeans": "soy",
    "coconuts": "coconut",
    "cashews": "cashew",
    "peas": "pea",
    "rices": "rice",
    "hazelnuts": "hazelnut",
    "sunflowers": "sunflower",
}

CLAIMY_CATEGORY = {"fiber", "protein", "collagen"}

IGNORED_UNACCOUNTED = {
    "added",
    "all",
    "and",
    "artificial",
    "brand",
    "classic",
    "count",
    "each",
    "flavor",
    "flavored",
    "foods",
    "free",
    "fresh",
    "grade",
    "great",
    "made",
    "natural",
    "net",
    "new",
    "old",
    "original",
    "oz",
    "per",
    "premium",
    "quality",
    "real",
    "style",
    "the",
    "with",
}

GENERIC_FORMS = {"beverage", "drink", "mix", "blend", "mixed", "food"}
BEVERAGE_CONTEXT_FORMS = {"coffee", "tea", "latte", "espresso", "juice", "soda"}
SOLID_FORMS = {
    "bar",
    "bars",
    "bread",
    "breads",
    "brownie",
    "brownies",
    "cake",
    "cakes",
    "candy",
    "candies",
    "cereal",
    "cookie",
    "cookies",
    "crackers",
    "cupcake",
    "cupcakes",
    "gum",
    "mints",
    "muffin",
    "muffins",
    "pancake",
    "pancakes",
    "roll",
    "rolls",
}

FORM_AS_PRIMARY_CATEGORY = {
    "bagel",
    "bagels",
    "cake",
    "cakes",
    "cereal",
    "cupcake",
    "cupcakes",
    "bread",
    "breads",
    "bun",
    "buns",
    "muffin",
    "muffins",
    "cookie",
    "cookies",
    "candy",
    "candies",
    "gummy",
    "gummi",
    "gum",
    "mints",
    "bar",
    "bars",
    "pancake",
    "pancakes",
    "roll",
    "rolls",
}

BEVERAGE_FORMS = {
    "juice",
    "smoothie",
    "shake",
    "beverage",
    "drink",
    "tea",
    "coffee",
    "latte",
    "espresso",
    "soda",
    "seltzer",
    "kombucha",
    "kefir",
}

WITH_INGREDIENT_TAIL_HINTS = {
    "cinnamon",
    "extract",
    "extracts",
    "frosting",
    "icing",
    "juice",
    "oat",
    "oats",
    "powder",
    "powders",
    "salt",
    "spice",
    "spices",
    "sugar",
}

CHOCOLATE_CONFECTION_FORMS = [
    "bar",
    "bars",
    "chips",
    "chip",
    "candies",
    "candy",
    "chocolates",
    "cups",
    "cup",
    "truffle",
    "truffles",
    "bites",
    "bite",
    "pieces",
    "topping",
    "toppings",
    "chocolate",
]

SINGLE_WITH_INCLUSION_FORMS = {
    "smoothie",
    "shake",
    "juice",
    "drink",
    "beverage",
    "coffee",
    "tea",
    "latte",
    "espresso",
    "soda",
    "seltzer",
    "kombucha",
    "yogurt",
    "ice cream",
    "bar",
    "bars",
    "cereal",
    "granola",
    "trail mix",
    "salad",
    "soup",
    "pizza",
    "chocolate",
    "candy",
    "cookie",
    "cookies",
    "cake",
    "cakes",
    "muffin",
    "muffins",
    "bread",
    "pancakes",
    "waffles",
    "pie",
    "brownie",
    "donut",
    "donuts",
    "popcorn",
    "chips",
    "pretzel",
    "pretzels",
    "milk",
    "creamer",
    "pudding",
    "sandwich",
    "wrap",
    "mints",
    "gum",
}

FORM_RANK = defaultdict(
    int,
    {
        "ice cream": 120,
        "protein powder": 115,
        "water enhancer": 115,
        "coffee creamer": 115,
        "milk": 110,
        "juice": 110,
        "smoothie": 110,
        "powder": 105,
        "butter": 100,
        "hummus": 100,
        "chips": 95,
        "chip": 95,
        "crackers": 95,
        "bar": 95,
        "bars": 95,
        "candy": 95,
        "candies": 95,
        "chocolate": 95,
        "chocolates": 95,
        "truffle": 95,
        "truffles": 95,
        "cake": 95,
        "cakes": 95,
        "cupcake": 95,
        "cupcakes": 95,
        "muffin": 95,
        "muffins": 95,
        "cookie": 95,
        "cookies": 95,
        "gum": 95,
        "mints": 95,
        "yogurt": 95,
        "cereal": 95,
        "bread": 95,
        "breads": 95,
        "bagel": 95,
        "bagels": 95,
        "roll": 95,
        "rolls": 95,
        "bun": 95,
        "buns": 95,
        "pancake": 95,
        "pancakes": 95,
        "sauce": 90,
        "dressing": 90,
        "salsa": 90,
        "soup": 90,
        "stew": 90,
        "pizza": 90,
        "sandwich": 90,
        "wrap": 90,
        "bowl": 85,
        "kit": 80,
        "tray": 75,
        "blend": 30,
        "mixed": 25,
    },
)

COMPOSITE_BFC_PATTERNS = {
    "frozen dinners entrees",
    "frozen dinners and entrees",
    "other soups",
    "canned soup",
    "chili stew",
    "casseroles",
    "deli salads",
    "prepared subs sandwiches",
    "frozen breakfast sandwiches",
    "entrees sides small meals",
    "entrees sides and small meals",
    "pasta dinners",
    "pizza",
}

COMBO_BFC_PATTERNS = {
    "lunch snacks combinations",
    "pre packaged fruit vegetables",
    "pre packaged fruit and vegetables",
}


@dataclass(frozen=True)
class Match:
    axis: str
    value: str
    start: int
    end: int


@dataclass(frozen=True)
class CategoryMeta:
    supercategory: str
    category_group: str


def repo_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def ascii_fold(value: str) -> str:
    return unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode("ascii")


def base_normalize(value: str) -> str:
    value = ascii_fold(value).lower()
    value = value.replace("&", " and ").replace("+", " and ")
    value = NON_WORD_RE.sub(" ", value)
    return re.sub(r"\s+", " ", value).strip()


def apply_spelling(value: str, spelling_pairs: list[tuple[str, str]]) -> str:
    value = base_normalize(value)
    for src, dst in spelling_pairs:
        value = re.sub(rf"\b{re.escape(src)}\b", dst, value)
    return re.sub(r"\s+", " ", value).strip()


def tokens_for(value: str) -> list[str]:
    return [tok for tok in WORD_RE.findall(value) if len(tok) >= 2]


def dedupe_ordered(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out


def unselected_values(candidates: list[str], selected: Iterable[str]) -> list[str]:
    selected_set = {value for value in selected if value}
    return [value for value in candidates if value not in selected_set]


def matched_token_spans(matches: dict[str, list["Match"]]) -> set[int]:
    covered: set[int] = set()
    for axis, axis_matches in matches.items():
        if axis == "__dish_strength__":
            continue
        for match in axis_matches:
            covered.update(range(match.start, match.end))
    return covered


def significant_unaccounted_tokens(tokens: list[str], matches: dict[str, list["Match"]]) -> list[str]:
    covered = matched_token_spans(matches)
    out: list[str] = []
    for idx, token in enumerate(tokens):
        if idx in covered or token in IGNORED_UNACCOUNTED:
            continue
        if len(token) <= 2 or token.isdigit():
            continue
        out.append(token)
    return dedupe_ordered(out)


def axis_coverage_score(tokens: list[str], unaccounted: list[str]) -> float:
    significant = [
        token
        for token in tokens
        if token not in IGNORED_UNACCOUNTED and len(token) > 2 and not token.isdigit()
    ]
    if not significant:
        return 1.0
    return round((len(significant) - len(unaccounted)) / len(significant), 3)


def ambiguous_axis_terms(matches: dict[str, list["Match"]]) -> list[str]:
    by_span_value: dict[tuple[int, int, str], set[str]] = defaultdict(set)
    for axis, axis_matches in matches.items():
        if axis in {"STOPWORD", "BRAND_NOISE", "__dish_strength__"}:
            continue
        for match in axis_matches:
            by_span_value[(match.start, match.end, match.value)].add(axis)
    terms: list[str] = []
    for (_, _, value), axes in by_span_value.items():
        if len(axes) > 1:
            terms.append(f"{value}:{'|'.join(sorted(axes))}")
    return sorted(set(terms))


def candidate_values_for_axis(matches: dict[str, list["Match"]], axis: str) -> list[str]:
    return dedupe_ordered(match.value for match in matches.get(axis, []))


def title_case(value: str) -> str:
    special = {
        "bbq": "BBQ",
        "gmo": "GMO",
        "non": "Non",
        "rtd": "RTD",
        "usda": "USDA",
    }
    parts = []
    for part in value.replace("-", " ").split():
        low = part.lower()
        parts.append(special.get(low, low.capitalize()))
    return " ".join(parts)


def clean_duplicate_tail(raw: str) -> str:
    parts = [part.strip() for part in (raw or "").split(",") if part.strip()]
    if not parts:
        return raw or ""
    while len(parts) > 1:
        head_norm = base_normalize(" ".join(parts[:-1]))
        tail_norm = base_normalize(parts[-1])
        if tail_norm and (head_norm.endswith(tail_norm) or tail_norm in head_norm):
            parts.pop()
        else:
            break
    return ", ".join(parts)


def load_spelling(path: str) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    if not os.path.exists(path):
        return pairs
    with open(path, newline="") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) < 2:
                continue
            src = base_normalize(parts[0])
            dst = base_normalize(parts[1])
            if src and dst:
                pairs.append((src, dst))
    pairs.sort(key=lambda item: -len(item[0]))
    return pairs


class AxisLexicon:
    def __init__(self, root: str):
        self.root = root
        self.axes_dir = os.path.join(root, "axes")
        self.spelling_pairs = load_spelling(os.path.join(self.axes_dir, "spelling.tsv"))
        self.axis_terms: dict[str, set[str]] = {axis: set() for axis in AXIS_FILES}
        self.axis_max_n: dict[str, int] = defaultdict(lambda: 1)
        self.category_meta: dict[str, CategoryMeta] = {}
        self.dish_strength: dict[str, bool] = {}
        self._load_axes()

    def _load_axes(self) -> None:
        for axis, filename in AXIS_FILES.items():
            path = os.path.join(self.axes_dir, filename)
            if not os.path.exists(path):
                continue
            with open(path, newline="") as fh:
                for line in fh:
                    line = line.rstrip("\n")
                    if not line or line.startswith("#"):
                        continue
                    parts = line.split("\t")
                    value = apply_spelling(parts[0], self.spelling_pairs)
                    if not value:
                        continue
                    self.axis_terms[axis].add(value)
                    self.axis_max_n[axis] = max(self.axis_max_n[axis], len(value.split()))
                    if axis == "CATEGORY" and len(parts) >= 3:
                        supercategory = (parts[1].split("|")[0] or "").strip()
                        category_group = (parts[2].split("|")[0] or "").strip()
                        if supercategory or category_group:
                            self.category_meta.setdefault(
                                value,
                                CategoryMeta(supercategory or "Other", category_group or "Other"),
                            )
                    if axis == "DISH_TYPE" and len(parts) >= 3:
                        self.dish_strength[value] = parts[2].strip() == "1"

    def normalize(self, value: str) -> str:
        return apply_spelling(value, self.spelling_pairs)

    def tokens(self, value: str) -> list[str]:
        return tokens_for(self.normalize(value))

    def matches(self, tokens: list[str], axis: str) -> list[Match]:
        terms = self.axis_terms.get(axis, set())
        max_n = self.axis_max_n.get(axis, 1)
        out: list[Match] = []
        seen: set[tuple[str, int, int]] = set()
        for start in range(len(tokens)):
            for size in range(min(max_n, len(tokens) - start), 0, -1):
                value = " ".join(tokens[start : start + size])
                key = (value, start, start + size)
                if value in terms and key not in seen:
                    seen.add(key)
                    out.append(Match(axis, value, start, start + size))
        return out

    def all_matches(self, tokens: list[str]) -> dict[str, list[Match]]:
        return {axis: self.matches(tokens, axis) for axis in AXIS_FILES}


def values(matches: dict[str, list[Match]], axis: str) -> list[str]:
    return dedupe_ordered(match.value for match in matches.get(axis, []))


def has_phrase(tokens: list[str], phrase: str) -> bool:
    wanted = phrase.split()
    if not wanted:
        return False
    for idx in range(len(tokens) - len(wanted) + 1):
        if tokens[idx : idx + len(wanted)] == wanted:
            return True
    return False


def first_phrase(tokens: list[str], phrases: Iterable[str]) -> str:
    for phrase in phrases:
        if has_phrase(tokens, phrase):
            return phrase
    return ""


def has_milk_chocolate_context(tokens: list[str]) -> bool:
    if has_phrase(tokens, "dairy milk chocolate"):
        return True
    for idx in range(len(tokens) - 1):
        if (
            tokens[idx] == "milk"
            and tokens[idx + 1] in {"chocolate", "chocolates", "chocolatey", "chocolatety"}
        ):
            if idx + 2 < len(tokens) and tokens[idx + 2] == "milk":
                continue
            return True
    for idx in range(len(tokens) - 3):
        if (
            tokens[idx] == "milk"
            and tokens[idx + 1] == "and"
            and tokens[idx + 2] in {"dark", "white"}
            and tokens[idx + 3] in {"chocolate", "chocolates", "chocolatey", "chocolatety"}
        ):
            return True
    return False


def has_chocolate_confection_context(tokens: list[str]) -> bool:
    if has_milk_chocolate_context(tokens):
        return True
    confection_markers = {
        "candy",
        "candies",
        "bar",
        "bars",
        "chips",
        "chocolates",
        "truffle",
        "truffles",
        "bites",
        "pieces",
        "coated",
        "covered",
    }
    return bool({"chocolate", "chocolatey", "chocolatety"} & set(tokens)) and bool(
        confection_markers & set(tokens)
    )


def plant_milk_base_from_tokens(tokens: list[str]) -> str:
    bases = plant_milk_bases_from_tokens(tokens)
    return bases[0] if bases else ""


def plant_milk_bases_from_tokens(tokens: list[str]) -> list[str]:
    bases: list[str] = []
    for token in tokens:
        base = PLANT_MILK_BASE_ALIASES.get(token, token)
        if base in PLANT_MILK_BASES:
            bases.append(base)
    return dedupe_ordered(bases)


def evidence_fields(row: dict[str, str]) -> tuple[str, str, str, str, str]:
    return (
        base_normalize(row.get("branded_food_category", "")),
        base_normalize(row.get("fixy_category", "")),
        base_normalize(row.get("v6_fndds_description", "")),
        base_normalize(row.get("best_esha_description", "")),
        base_normalize(row.get("wweia_category_description", "")),
    )


def plant_milk_evidence_text(row: dict[str, str]) -> str:
    return " ".join(evidence_fields(row))


def evidence_has_base_milk(evidence_text: str, base: str) -> bool:
    return f"{base} milk" in evidence_text or f"{base}milk" in evidence_text


def select_plant_milk_base(row: dict[str, str], tokens: list[str]) -> str:
    bases = plant_milk_bases_from_tokens(tokens)
    if not bases:
        return ""
    evidence_text = plant_milk_evidence_text(row)
    for base in bases:
        if evidence_has_base_milk(evidence_text, base):
            return base
    return bases[0]


def plant_milk_evidence(row: dict[str, str], tokens: list[str], base: str) -> bool:
    if not base:
        return False
    if "juice" in tokens or "water" in tokens:
        return False
    bfc, fixy, fndds, esha, wweia = evidence_fields(row)
    evidence_text = " ".join([bfc, fixy, fndds, esha, wweia])
    creamer_context = (
        bfc in {"cream", "milk additives"}
        or fixy in {"cream", "milk additives"}
        or "coffee creamer" in fndds
        or "cream substitute" in esha
    )
    trusted_plant_milk_bucket = bfc in {
        "plant based milk",
        "plant based milk alternatives",
    } or fixy in {
        "plant based milk",
        "plant based milk alternatives",
    }
    blocker_context = (
        bfc in {
            "plant based water",
            "liquid water enhancer",
            "powdered drinks",
            "energy protein muscle recovery drinks",
        }
        or fixy in {
            "plant based water",
            "liquid water enhancer",
            "powdered drinks",
            "energy protein muscle recovery drinks",
        }
        or "enhancer" in tokens
        or "horchata" in tokens
        or ("protein" in tokens and "milk" not in tokens)
        or has_phrase(tokens, "drink mix")
        or has_phrase(tokens, "food drink")
        or has_with_plant_milk_component(tokens)
        or "water enhancer" in fndds
        or "fruit juice" in fndds
        or "protein shake" in fndds
        or "nutritional drink" in fndds
        or "coconut water" in esha
    )
    if blocker_context and not trusted_plant_milk_bucket:
        return False
    if creamer_context and not trusted_plant_milk_bucket:
        return False

    if trusted_plant_milk_bucket or wweia == "milk substitutes":
        return True
    if evidence_has_base_milk(evidence_text, base):
        return True
    if "non dairy milk" in evidence_text or "milk substitute" in evidence_text or "milk imitation" in evidence_text:
        return True
    return False


def has_positive_dairy_context(tokens: list[str]) -> bool:
    for idx, token in enumerate(tokens):
        if token != "dairy":
            continue
        previous_token = tokens[idx - 1] if idx > 0 else ""
        next_token = tokens[idx + 1] if idx + 1 < len(tokens) else ""
        if previous_token in {"non", "no"} or next_token == "free":
            continue
        return True
    return False


def has_with_plant_milk_component(tokens: list[str]) -> bool:
    for idx, token in enumerate(tokens):
        if token != "with":
            continue
        tail = tokens[idx + 1 : idx + 6]
        if "milk" in tail and plant_milk_bases_from_tokens(tail):
            return True
    return False


def select_form(tokens: list[str], matches: dict[str, list[Match]]) -> str:
    if has_chocolate_confection_context(tokens):
        form_values = {match.value for match in matches.get("FORM", [])}
        for preferred in CHOCOLATE_CONFECTION_FORMS:
            if preferred in form_values:
                return preferred
        return "chocolate"

    compound = first_phrase(
        tokens,
        [
            "ice cream",
            "protein shake",
            "milk shake",
            "coffee cake",
            "tea cake",
            "tea cakes",
            "cake mix",
            "cupcake mix",
            "pancake mix",
            "drink mix",
            "latte mix",
            "tea mix",
            "soda bread",
            "protein powder",
            "water enhancer",
            "coffee creamer",
            "trail mix",
            "fruit snack",
            "granola bar",
            "energy bar",
            "protein bar",
            "pot pie",
        ],
    )
    if compound:
        if compound in {"protein shake", "milk shake"}:
            return "shake"
        if compound == "coffee cake":
            return "cake"
        if compound == "tea cake":
            return "cake"
        if compound == "tea cakes":
            return "cakes"
        if compound in {"cake mix", "cupcake mix", "pancake mix", "drink mix", "latte mix", "tea mix"}:
            return "mix"
        if compound == "soda bread":
            return "bread"
        return compound
    form_matches = matches.get("FORM", [])
    form_matches = main_form_matches(tokens, matches, form_matches)
    if not form_matches:
        return ""
    form_values = {match.value for match in form_matches}
    beverage_blockers = {
        "cake",
        "cakes",
        "cupcake",
        "cupcakes",
        "muffin",
        "muffins",
        "cookie",
        "cookies",
        "candy",
        "candies",
        "gummy",
        "gummi",
        "gum",
        "mints",
        "bar",
        "bars",
        "chews",
        "chew",
        "icing",
        "frosting",
        "mix",
        "cereal",
        "granola",
        "bread",
        "breads",
        "bagel",
        "bagels",
        "roll",
        "rolls",
        "bun",
        "buns",
        "pancake",
        "pancakes",
    }
    if not (form_values & beverage_blockers):
        for preferred in ["smoothie", "shake", "juice", "kefir", "coffee", "tea", "latte", "espresso", "soda", "seltzer", "kombucha"]:
            if preferred in form_values:
                return preferred
    for preferred in [
        "cereal",
        "granola",
        "bread",
        "breads",
        "bagel",
        "bagels",
        "roll",
        "rolls",
        "bun",
        "buns",
        "pancake",
        "pancakes",
        "cake",
        "cakes",
        "cupcake",
        "cupcakes",
        "muffin",
        "muffins",
        "cookie",
        "cookies",
        "gum",
        "mints",
        "candy",
        "candies",
    ]:
        if preferred in form_values:
            return preferred
    ranked = sorted(
        form_matches,
        key=lambda match: (FORM_RANK[match.value], match.end - match.start, match.start),
        reverse=True,
    )
    if ranked[0].value == "chocolate":
        for preferred in ["beverage", "drink"]:
            if preferred in form_values:
                return preferred
    return ranked[0].value


def main_form_matches(
    tokens: list[str],
    matches: dict[str, list[Match]],
    form_matches: list[Match],
) -> list[Match]:
    if "with" not in tokens:
        return form_matches
    with_index = tokens.index("with")
    before = [match for match in form_matches if match.start < with_index]
    if before:
        return before

    has_before_category = any(
        match.start < with_index and match.value not in GENERIC_CATEGORY
        for match in matches.get("CATEGORY", [])
    )
    after_tokens = set(tokens[with_index + 1 :])
    if has_before_category and after_tokens & WITH_INGREDIENT_TAIL_HINTS:
        return []
    return form_matches


def has_with_ingredient_tail(tokens: list[str], matches: dict[str, list[Match]]) -> bool:
    if "with" not in tokens:
        return False
    with_index = tokens.index("with")
    has_before_product = any(
        match.start < with_index and match.value not in GENERIC_CATEGORY
        for axis in ("CATEGORY", "FORM")
        for match in matches.get(axis, [])
    )
    if not has_before_product:
        return False
    return bool(set(tokens[with_index + 1 :]) & WITH_INGREDIENT_TAIL_HINTS)


def select_first_axis(matches: dict[str, list[Match]], axis: str) -> str:
    axis_matches = matches.get(axis, [])
    return axis_matches[0].value if axis_matches else ""


def select_prep_state(tokens: list[str], matches: dict[str, list[Match]]) -> str:
    compound = first_phrase(
        tokens,
        [
            "fully cooked",
            "cold pressed",
            "ready to drink",
            "ready to eat",
            "ready to heat",
            "hard boiled",
            "soft boiled",
            "oven roasted",
            "slow cooked",
            "flame grilled",
            "wood fired",
            "cold smoked",
            "hot smoked",
        ],
    )
    if compound:
        return compound
    skip = {"fully", "ready", "heat", "extra", "oven", "slow", "flame", "cold", "hot"}
    for match in matches.get("PREPARATION_STATE", []):
        if match.value not in skip:
            return match.value
    return ""


def select_storage(tokens: list[str], matches: dict[str, list[Match]], branded_category: str) -> str:
    text = " ".join(tokens + tokens_for(base_normalize(branded_category)))
    for phrase in ["shelf stable", "freeze dried"]:
        if has_phrase(text.split(), phrase):
            return phrase
    for storage in ["frozen", "refrigerated", "chilled", "canned", "jarred", "dried", "fresh"]:
        if storage in text.split():
            return storage
    skip = {"cold", "pressed", "hot", "heavy", "light", "spring", "mountain"}
    for match in matches.get("STORAGE", []):
        if match.value not in skip:
            return match.value
    return ""


def primary_food_from_categories(
    tokens: list[str],
    matches: dict[str, list[Match]],
    form: str,
) -> str:
    category_matches = [
        match
        for match in matches.get("CATEGORY", [])
        if match.value not in GENERIC_CATEGORY and match.value not in CLAIMY_CATEGORY
    ]
    if not category_matches:
        return ""

    if has_chocolate_confection_context(tokens):
        for match in category_matches:
            if match.value == "chocolate":
                return "chocolate"

    if "beans" in {match.value for match in category_matches} and (
        has_phrase(tokens, "baked beans")
        or has_phrase(tokens, "baked bean")
        or has_phrase(tokens, "bean pot")
    ):
        return "beans"

    if "bacon" in {match.value for match in category_matches} and (
        "topping" in tokens or "toppings" in tokens
    ):
        return "bacon"

    if form in FORM_AS_PRIMARY_CATEGORY:
        for match in category_matches:
            if match.value == form:
                return match.value

    form_match = None
    for match in matches.get("FORM", []):
        if match.value == form or (form.endswith(match.value) and match.value in form.split()):
            form_match = match
            break
    if form_match:
        before = [match for match in category_matches if match.end <= form_match.start]
        if before:
            return sorted(before, key=lambda match: (match.end, match.start), reverse=True)[0].value

    if form == "milk":
        for match in category_matches:
            if match.value in PLANT_MILK_BASES:
                return match.value

    return category_matches[0].value


def flavor_values(
    tokens: list[str],
    matches: dict[str, list[Match]],
    primary_food: str,
    form: str,
) -> tuple[str, list[str]]:
    flavor_matches = matches.get("FLAVOR_UNIVERSAL", [])
    excluded = {primary_food, form, "flavored", "flavor"}
    ordered = [match.value for match in flavor_matches if match.value not in excluded]

    if has_milk_chocolate_context(tokens):
        return "milk chocolate", []
    if has_phrase(tokens, "dark chocolate"):
        return "dark chocolate", []
    if has_phrase(tokens, "pumpkin spice"):
        return "pumpkin spice", []
    if has_phrase(tokens, "lemon ginger"):
        return "lemon ginger", []
    if has_phrase(tokens, "caramel macchiato"):
        return "caramel macchiato", []

    flavor = ""
    for candidate in ordered:
        if candidate in {"plain", "original", "unflavored"}:
            flavor = candidate
            break
    if not flavor:
        flavor = ordered[0] if ordered else ""

    blend_source = ordered
    if form in {"smoothie", "juice", "drink", "beverage"}:
        form_starts = [match.start for match in matches.get("FORM", []) if match.value == form]
        if form_starts:
            first_form = min(form_starts)
            blend_source = [
                match.value
                for match in flavor_matches
                if match.start < first_form and match.value not in {form, "flavored", "flavor"}
            ]

    fruit_like = [
        value
        for value in blend_source
        if value
        not in {
            "plain",
            "original",
            "flavored",
            "flavor",
            "spice",
            "sweet",
            "savory",
            "hot",
            "mild",
            "medium",
        }
    ]
    blend = dedupe_ordered(fruit_like)
    if form in {"smoothie", "juice", "drink", "beverage"} and len(blend) >= 2:
        return "", blend
    return flavor, []


def detect_inclusions(tokens: list[str], matches: dict[str, list[Match]], retail_type: str) -> list[str]:
    if retail_type == "combo_pack" or "with" not in tokens:
        return []
    with_index = tokens.index("with")
    after = tokens[with_index + 1 :]
    inclusions: list[str] = []
    for phrase in ["chia seeds", "chocolate chips", "walnuts", "almonds", "granola", "fruit pieces"]:
        if has_phrase(after, phrase):
            inclusions.append(phrase)
    if not inclusions:
        after_matches = [
            match.value
            for axis in ("CATEGORY", "FORM", "FLAVOR_UNIVERSAL")
            for match in matches.get(axis, [])
            if match.start > with_index and match.value not in GENERIC_CATEGORY
        ]
        inclusions.extend(after_matches[:2])
    return dedupe_ordered(inclusions)


def detect_claims(tokens: list[str], matches: dict[str, list[Match]]) -> dict[str, list[str]]:
    diet_fragments = {"dairy", "gluten", "plant", "free", "no", "fed", "range", "cage", "lactose"}
    claims = {
        "sweetener": values(matches, "SWEETENER"),
        "fat": values(matches, "FAT"),
        "sodium": values(matches, "SODIUM"),
        "diet": [value for value in values(matches, "DIET") if value not in diet_fragments],
        "audience": values(matches, "AUDIENCE"),
    }
    compound_diet = [
        "gluten free",
        "dairy free",
        "plant based",
        "non gmo",
        "grass fed",
        "cage free",
        "free range",
        "lactose free",
    ]
    for claim in compound_diet:
        if has_phrase(tokens, claim):
            claims["diet"].append(claim)
    if has_phrase(tokens, "no sugar added"):
        claims["sweetener"].append("no sugar added")
    if has_phrase(tokens, "no salt added"):
        claims["sodium"].append("no salt added")
    return {key: dedupe_ordered(vals) for key, vals in claims.items() if vals}


def component_phrases(tokens: list[str], matches: dict[str, list[Match]]) -> list[str]:
    category_matches = matches.get("CATEGORY", [])
    form_matches = matches.get("FORM", [])
    cut_matches = matches.get("CUT", [])
    components: list[str] = []

    for cat in category_matches:
        if cat.value in GENERIC_CATEGORY:
            continue
        next_form = next(
            (
                form
                for form in form_matches
                if 0 <= form.start - cat.end <= 2 and form.value not in {"mix", "blend"}
                and not ({"with", "and"} & set(tokens[cat.end : form.start]))
            ),
            None,
        )
        next_cut = next((cut for cut in cut_matches if 0 <= cut.start - cat.end <= 1), None)
        if next_form:
            components.append(f"{cat.value} {next_form.value}")
        elif next_cut:
            components.append(f"{cat.value} {next_cut.value}")
        else:
            components.append(cat.value)

    for form in form_matches:
        if form.value in {"hummus", "guacamole"} and form.value not in components:
            components.append(form.value)
    deduped = dedupe_ordered(components)
    pruned: list[str] = []
    for component in deduped:
        if any(component != other and component in other.split() for other in deduped):
            continue
        pruned.append(component)
    return pruned


def detect_pack_format(tokens: list[str], matches: dict[str, list[Match]], components: list[str]) -> str:
    combo_values = values(matches, "COMBO_FORMAT")
    for preferred in ["lunchables", "dipper", "dippers", "dippables", "bento", "tray", "platter"]:
        if preferred in combo_values:
            return "dipper" if preferred in {"dipper", "dippers", "dippables"} else preferred
    if "with" in tokens and len(components) >= 2:
        return "dipper"
    return combo_values[0] if combo_values else "combo"


def detect_type(
    tokens: list[str],
    matches: dict[str, list[Match]],
    branded_category: str,
    components: list[str],
    form: str,
) -> str:
    bfc = base_normalize(branded_category)
    if form == "milk" and bfc in {"milk", "plant based milk", "plant based milk alternatives"}:
        return "single"
    if (
        "candy" in bfc
        or "confectionery" in bfc
        or "chewing gum" in bfc
        or form in {"candy", "candies", "gummy", "gummi", "gum", "mints"}
        or {"candy", "candies", "gummy", "gummi", "gummies", "gum", "mints"} & set(tokens)
    ):
        return "single"
    if any(pattern in bfc for pattern in COMPOSITE_BFC_PATTERNS):
        return "composite_dish"

    strong_dish = any(
        matches_value and matches_value.value and matches_value.value != "kit"
        and lexicon_dish_is_strong(matches, matches_value)
        for matches_value in matches.get("DISH_TYPE", [])
    )
    if strong_dish:
        return "composite_dish"

    combo_format = values(matches, "COMBO_FORMAT")
    strong_combo_format = [
        value
        for value in combo_format
        if value
        not in {
            "cup",
            "cups",
            "pack",
            "packs",
            "serving",
            "servings",
            "sides",
            "toppers",
            "toppings",
        }
    ]
    combo_bfc = any(pattern in bfc for pattern in COMBO_BFC_PATTERNS)
    with_components = "with" in tokens and len(components) >= 2
    if has_with_ingredient_tail(tokens, matches) and not strong_combo_format and not combo_bfc:
        with_components = False
    if form in SINGLE_WITH_INCLUSION_FORMS and not strong_combo_format and not combo_bfc:
        with_components = False
    if strong_combo_format or combo_bfc or with_components:
        return "combo_pack"
    return "single"


def lexicon_dish_is_strong(matches: dict[str, list[Match]], match: Match) -> bool:
    strength = matches.get("__dish_strength__", [])
    if "__dish_strength__" not in matches:
        return True
    return match.value in {item.value for item in strength}


def dish_strength_matches(lexicon: AxisLexicon, matches: dict[str, list[Match]]) -> list[Match]:
    return [match for match in matches.get("DISH_TYPE", []) if lexicon.dish_strength.get(match.value, True)]


def resolve_taxonomy(
    tokens: list[str],
    lexicon: AxisLexicon,
    retail_type: str,
    primary_food: str,
    form: str,
    dish_type: str,
    pack_format: str,
    components: list[str],
    flavor: str,
    flavor_blend: list[str],
    inclusions: list[str],
    claims: dict[str, list[str]],
    prep_state: str,
) -> tuple[str, str, str, str]:
    if retail_type == "composite_dish":
        dish = dish_type or form or "dish"
        leaf_title = summarize_title(tokens)
        return "Meal", "Composite Dishes", title_case(dish), (
            f"Meal > Composite Dishes > {title_case(dish)} > {leaf_title}"
        )

    if retail_type == "combo_pack":
        fmt = pack_format or "combo"
        component_label = " + ".join(title_case(component) for component in components[:4])
        leaf = f"Snack > Combo Packs > {title_case(fmt)}"
        if component_label:
            leaf += f" > {component_label}"
        return "Snack", "Combo Packs", title_case(fmt), leaf

    # Plant-based milk fast-path. Generic "beverage" wording only reaches this
    # block after parse_row has found plant-milk evidence and rewritten form to
    # "milk"; otherwise coconut water etc. must stay generic beverage/water.
    if primary_food in PLANT_MILK_BASES and form == "milk":
        if has_positive_dairy_context(tokens) and "blend" in tokens:
            leaf = f"Beverage > Dairy Milk > Blended Milks > Dairy+{title_case(primary_food)}"
            return "Beverage", "Blended Milks", f"Dairy+{title_case(primary_food)}", leaf
        category = f"{title_case(primary_food)} Milk"
        flavor_label = milk_flavor_label(flavor, claims)
        return "Beverage", "Plant-based Milk", category, (
            f"Beverage > Plant-based Milk > {category} > {flavor_label}"
        )

    if form == "milk":
        # Dairy milk — surface chocolate/strawberry/etc flavor in the leaf
        flavor_label = milk_flavor_label(flavor or primary_food, claims)
        if flavor_label.lower() in {"plain","milk"}:
            return "Beverage", "Dairy Milk", "Milk", "Beverage > Dairy Milk > Milk"
        return "Beverage", "Dairy Milk", "Milk", f"Beverage > Dairy Milk > {flavor_label} Milk"

    if form == "smoothie":
        leaf_detail = blend_label(flavor_blend) or title_case(flavor or primary_food or "Plain")
        if inclusions:
            leaf_detail += " w/ " + ", ".join(title_case(item) for item in inclusions)
        return "Beverage", "Fruit-based Drinks", "Smoothie", (
            f"Beverage > Fruit-based Drinks > Smoothie > {leaf_detail}"
        )

    if form == "juice":
        detail = title_case(primary_food or flavor or "Juice")
        return "Beverage", "Fruit-based Drinks", "Juice", (
            f"Beverage > Fruit-based Drinks > Juice > {detail}"
        )

    if form in BEVERAGE_FORMS:
        category = title_case(form)
        detail = blend_label(flavor_blend) or title_case(flavor or primary_food or category)
        return "Beverage", "Beverages", category, f"Beverage > Beverages > {category} > {detail}"

    if form in {"powder", "protein powder"} and ("protein" in tokens or "whey" in tokens):
        protein = f"{title_case(primary_food)} Protein".strip()
        return "Pantry", "Protein Powders", protein, f"Pantry > Protein Powders > {protein}"

    meta = lexicon.category_meta.get(primary_food)
    if form != "milk" and primary_food in PLANT_MILK_BASES:
        meta = CategoryMeta("Snack", "Nuts & Seeds")
    elif form != "milk" and primary_food in {"rice", "oat", "oats"}:
        meta = CategoryMeta("Pantry", "Grain")
    supercategory = meta.supercategory if meta else "Other"
    category_group = meta.category_group if meta else "Other"
    category = title_case(primary_food or form or "Unclassified")
    leaf_bits = [supercategory, category_group, category]
    if form and form != primary_food:
        leaf_bits.append(title_case(form))
    if flavor and flavor not in {primary_food, form}:
        leaf_bits.append(title_case(flavor))
    if prep_state and prep_state not in {primary_food, form, flavor}:
        leaf_bits.append(title_case(prep_state))
    return supercategory, category_group, category, " > ".join(bit for bit in leaf_bits if bit)


def summarize_title(tokens: list[str]) -> str:
    skip = {
        "the",
        "original",
        "flavored",
        "flavor",
        "style",
        "with",
        "and",
    }
    kept = [tok for tok in tokens if tok not in skip]
    return title_case(" ".join(kept[:6])) or "Dish"


def milk_flavor_label(flavor: str, claims: dict[str, list[str]]) -> str:
    sweetener = claims.get("sweetener", [])
    if flavor in {"", "plain", "original", "unflavored"}:
        if "unsweetened" in sweetener:
            return "Plain Unsweetened"
        return title_case(flavor or "Plain")
    label = title_case(flavor)
    if "unsweetened" in sweetener and "unsweetened" not in flavor:
        label += " Unsweetened"
    return label


def blend_label(values_: list[str]) -> str:
    if not values_:
        return ""
    return "-".join(title_case(value) for value in values_)


def dedupe_leaf(leaf: str) -> str:
    """Collapse exact adjacent duplicates in a ' > ' separated leaf path."""
    if not leaf or ' > ' not in leaf:
        return leaf
    parts = [p.strip() for p in leaf.split(' > ') if p.strip()]
    out: list[str] = []
    for p in parts:
        pl = p.lower()
        if out and out[-1].lower() == pl:
            continue
        out.append(p)
    return ' > '.join(out)


def confidence_score(result: dict[str, object]) -> float:
    checks = [
        bool(result.get("retail_type")),
        bool(result.get("category")),
        bool(result.get("retail_leaf")),
        bool(result.get("form") or result.get("dish_type") or result.get("pack_format")),
        not bool(result.get("needs_review")),
    ]
    return round(sum(checks) / len(checks), 2)


def axis_review_issues(
    result: dict[str, object],
    form_candidates: list[str],
    category_candidates: list[str],
    ambiguous_terms: list[str],
    unaccounted_tokens_: list[str],
) -> list[str]:
    issues: list[str] = []
    retail_type = str(result.get("retail_type", ""))
    form = str(result.get("form", ""))
    primary_food = str(result.get("primary_food", ""))
    category_group = str(result.get("category_group", ""))

    if retail_type == "single" and not form:
        issues.append("axis_missing_form")
    if retail_type == "single" and not primary_food and category_group not in {"", "Other"}:
        issues.append("axis_missing_primary_food")
    if form in GENERIC_FORMS and len(set(form_candidates) - {form}) >= 1:
        issues.append("generic_form_with_specific_candidate")
    if form in BEVERAGE_CONTEXT_FORMS and set(form_candidates) & SOLID_FORMS:
        issues.append("beverage_context_form_over_solid_candidate")
    if len(unaccounted_tokens_) >= 4:
        issues.append("unaccounted_title_tokens")
    if len(ambiguous_terms) >= 4:
        issues.append("many_axis_ambiguous_terms")
    if not category_candidates and retail_type == "single":
        issues.append("no_category_candidates")
    return dedupe_ordered(issues)


def parse_row(row: dict[str, str], lexicon: AxisLexicon) -> dict[str, object]:
    raw_title = row.get("product_description") or row.get("title") or ""
    cleaned = clean_duplicate_tail(raw_title)
    normalized = lexicon.normalize(cleaned)
    tokens = tokens_for(normalized)
    matches = lexicon.all_matches(tokens)
    strong_dishes = dish_strength_matches(lexicon, matches)
    matches["__dish_strength__"] = strong_dishes

    form = select_form(tokens, matches)
    prep_state = select_prep_state(tokens, matches)
    storage = select_storage(tokens, matches, row.get("branded_food_category", ""))
    cut = select_first_axis(matches, "CUT")
    plant_base = select_plant_milk_base(row, tokens)
    force_plant_milk = (
        any(match.value in {"beverage", "drink"} for match in matches.get("FORM", []))
        and plant_milk_evidence(row, tokens, plant_base)
    )
    if force_plant_milk:
        form = "milk"
        primary_food = plant_base
    else:
        primary_food = primary_food_from_categories(tokens, matches, form)
    flavor, flavor_blend = flavor_values(tokens, matches, primary_food, form)
    claims = detect_claims(tokens, matches)
    components = component_phrases(tokens, matches)
    retail_type = detect_type(tokens, matches, row.get("branded_food_category", ""), components, form)
    pack_format = detect_pack_format(tokens, matches, components) if retail_type == "combo_pack" else ""
    inclusions = detect_inclusions(tokens, matches, retail_type)
    dish_type = strong_dishes[0].value if retail_type == "composite_dish" and strong_dishes else ""

    supercategory, category_group, category, retail_leaf_raw = resolve_taxonomy(
        tokens=tokens,
        lexicon=lexicon,
        retail_type=retail_type,
        primary_food=primary_food,
        form=form,
        dish_type=dish_type,
        pack_format=pack_format,
        components=components,
        flavor=flavor,
        flavor_blend=flavor_blend,
        inclusions=inclusions,
        claims=claims,
        prep_state=prep_state,
    )

    retail_leaf = dedupe_leaf(retail_leaf_raw)

    needs_review = []
    if retail_type == "single" and not form and not (primary_food and prep_state):
        needs_review.append("missing_form")
    if retail_type == "single" and not (primary_food or category):
        needs_review.append("missing_category")
    if retail_type == "combo_pack" and len(components) < 2:
        needs_review.append("combo_components_lt_2")
    if retail_type == "composite_dish" and not dish_type:
        needs_review.append("missing_dish_type")

    debug = {
        axis: [match.value for match in axis_matches[:6]]
        for axis, axis_matches in matches.items()
        if axis != "__dish_strength__" and axis_matches
    }

    result: dict[str, object] = {
        "gtin_upc": row.get("gtin_upc", ""),
        "fdc_id": row.get("fdc_id", ""),
        "product_description": raw_title,
        "retail_type": retail_type,
        "supercategory": supercategory,
        "category_group": category_group,
        "category": category,
        "primary_food": primary_food,
        "form": form,
        "cut": cut,
        "prep_state": prep_state,
        "storage": storage,
        "flavor": flavor,
        "flavor_blend": flavor_blend,
        "inclusions": inclusions,
        "claims": claims,
        "dish_type": dish_type,
        "pack_format": pack_format,
        "components": components if retail_type != "single" else [],
        "retail_leaf": retail_leaf,
        "needs_review": needs_review,
        "debug_matches": debug,
    }
    result["confidence"] = confidence_score(result)

    category_candidates = candidate_values_for_axis(matches, "CATEGORY")
    form_candidates = candidate_values_for_axis(matches, "FORM")
    flavor_candidates = candidate_values_for_axis(matches, "FLAVOR_UNIVERSAL")
    selected_flavors = [flavor] + flavor_blend
    selected_flavor_tokens = [
        token
        for selected_flavor in selected_flavors
        for token in selected_flavor.split()
    ]
    unaccounted = significant_unaccounted_tokens(tokens, matches)
    ambiguous_terms = ambiguous_axis_terms(matches)
    result["category_candidates"] = category_candidates
    result["form_candidates"] = form_candidates
    result["flavor_candidates"] = flavor_candidates
    result["unselected_category_candidates"] = unselected_values(category_candidates, [primary_food])
    result["unselected_form_candidates"] = unselected_values(form_candidates, [form])
    result["unselected_flavor_candidates"] = unselected_values(
        flavor_candidates,
        selected_flavors + selected_flavor_tokens,
    )
    result["ambiguous_axis_terms"] = ambiguous_terms
    result["unaccounted_tokens"] = unaccounted
    result["axis_coverage_score"] = axis_coverage_score(tokens, unaccounted)
    result["axis_review_issues"] = axis_review_issues(
        result,
        form_candidates=form_candidates,
        category_candidates=category_candidates,
        ambiguous_terms=ambiguous_terms,
        unaccounted_tokens_=unaccounted,
    )
    return result


def serialize(value: object) -> str:
    if isinstance(value, (list, dict)):
        return json.dumps(value, sort_keys=True, separators=(",", ":"))
    return "" if value is None else str(value)


def write_parsed_csv(
    input_path: str,
    output_path: str,
    lexicon: AxisLexicon,
    limit: int | None = None,
) -> int:
    count = 0
    with open(input_path, newline="") as src, open(output_path, "w", newline="") as dst:
        reader = csv.DictReader(src)
        writer = csv.DictWriter(dst, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        for row in reader:
            parsed = parse_row(row, lexicon)
            writer.writerow({field: serialize(parsed.get(field, "")) for field in OUTPUT_FIELDS})
            count += 1
            if limit and count >= limit:
                break
    return count


def parse_examples(lexicon: AxisLexicon) -> list[dict[str, object]]:
    examples = [
        "HINT OF PUMPKIN SPICE ALMONDMILK",
        "LEMON GINGER COLD-PRESSED ALMOND JUICE",
        "ALMOND PROTEIN POWDER, UNFLAVORED",
        "APPLE NOODLE KUGEL",
        "APPLE SLICES WITH PEANUT BUTTER",
        "HUMMUS WITH PITA CHIPS",
        "ACAI BLUEBERRY WATERMELON SMOOTHIE WITH CHIA SEEDS",
        "FULLY COOKED BACON",
        "ORIGINAL DAIRY + ALMOND BLEND MILK",
    ]
    return [parse_row({"product_description": title}, lexicon) for title in examples]


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Parse branded retail titles into axis vectors.")
    parser.add_argument("--input", default=os.path.join(repo_root(), "product_esha_fixy.v6.csv"))
    parser.add_argument("--output", default=os.path.join(repo_root(), "parsed_titles.csv"))
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--title", help="Parse one title and print JSON.")
    parser.add_argument("--examples", action="store_true", help="Print built-in regression examples as JSONL.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    lexicon = AxisLexicon(repo_root())
    if args.title:
        print(json.dumps(parse_row({"product_description": args.title}, lexicon), indent=2, sort_keys=True))
        return 0
    if args.examples:
        for parsed in parse_examples(lexicon):
            print(json.dumps(parsed, sort_keys=True))
        return 0
    count = write_parsed_csv(args.input, args.output, lexicon, args.limit)
    print(f"Wrote {count:,} parsed rows to {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
