#!/usr/bin/env python3
"""Clean retail_leaf_v2_enriched_v2 with an axis-first arbitration layer.

This script does not try to invent another fuzzy score. It treats the current
v2 leaf, parser output, provenance candidates, family routers, and exact-group
modal evidence as candidates, then asks whether each candidate is allowed by
identity and taxonomy gates.

Default output is a thin audit map. Use --full-output if the original wide row
should be copied with clean_* columns appended.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


REPO = Path("/Users/jamiebarton/Desktop/esha_audit_bundle")
RM = REPO / "retail_mapper"
V2 = RM / "v2"
DEFAULT_INPUT = V2 / "retail_leaf_v2_enriched_v2.csv"
DEFAULT_OUTPUT = V2 / "retail_leaf_v2_enriched_v2.cleaned.csv"
DEFAULT_SUMMARY = V2 / "retail_leaf_v2_enriched_v2.cleaned_summary.json"
DEFAULT_TAXONOMY = REPO / "implementation" / "output" / "taxonomy_paths_cleaned.csv"

PARSER_DIR = RM / "parsers"
if str(PARSER_DIR) not in sys.path:
    sys.path.insert(0, str(PARSER_DIR))

from title_parser import AxisLexicon, parse_row, repo_root  # noqa: E402


csv.field_size_limit(sys.maxsize)

TOKEN_RE = re.compile(r"[a-z0-9]+")
NON_WORD_RE = re.compile(r"[^a-z0-9]+")

VALID_ROOTS = {
    "Bakery",
    "Beverage",
    "Dairy",
    "Frozen",
    "Meal",
    "Meat & Seafood",
    "Other",
    "Pantry",
    "Produce",
    "Snack",
}

ROOT_REWRITES = {
    "Cereal": "Pantry > Breakfast Cereal",
    "Spoons": "Other > Edible Servingware > Spoon",
}

SEGMENT_REWRITES = {
    "Mixe": "Mixes",
    "Mixe ": "Mixes",
    "Sauce ": "Sauce",
}

WEAK_TOKENS = {
    "added",
    "baby",
    "best",
    "brand",
    "canned",
    "classic",
    "count",
    "ct",
    "each",
    "fat",
    "fl",
    "free",
    "fresh",
    "grade",
    "great",
    "light",
    "made",
    "natural",
    "naturally",
    "net",
    "new",
    "original",
    "oz",
    "pack",
    "pieces",
    "plain",
    "premium",
    "quality",
    "real",
    "reduced",
    "size",
    "stems",
    "style",
    "sweetened",
    "unsweetened",
    "whole",
}

GENERIC_PATH_TOKENS = {
    "and",
    "bakery",
    "based",
    "beverage",
    "beverages",
    "category",
    "canned",
    "dairy",
    "food",
    "foods",
    "frozen",
    "fruit",
    "generic",
    "meal",
    "meat",
    "nut",
    "other",
    "pantry",
    "plant",
    "produce",
    "product",
    "reference",
    "seafood",
    "seed",
    "snack",
    "spreads",
    "spread",
    "unclassified",
    "vegetable",
}

SOLID_FORMS = {
    "bagel",
    "bar",
    "bars",
    "biscuit",
    "biscuits",
    "bread",
    "brownie",
    "cake",
    "cakes",
    "candy",
    "cereal",
    "cookie",
    "cookies",
    "cracker",
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
    "waffle",
    "waffles",
}

MILK_BLOCKING_FORMS = SOLID_FORMS | {
    "mix",
    "powder",
    "protein powder",
    "chocolate",
    "chip",
    "chips",
}

FRUITS = {
    "apple",
    "apricot",
    "blackberry",
    "blueberry",
    "cherry",
    "cranberry",
    "date",
    "fig",
    "grape",
    "grapefruit",
    "mango",
    "orange",
    "peach",
    "pear",
    "pineapple",
    "raspberry",
    "strawberry",
}

PEPPERS = {
    "habanero",
    "jalapeno",
    "pepper",
    "peppers",
    "chile",
    "chili",
}

PRODUCE_LEAVES = {
    "arugula",
    "broccoli",
    "cabbage",
    "carrot",
    "celery",
    "greens",
    "kale",
    "lettuce",
    "mushroom",
    "okra",
    "spinach",
}

COMPOUND_REWRITES = {
    "almondmilk": "almond milk",
    "oatmilk": "oat milk",
    "soymilk": "soy milk",
    "cashewmilk": "cashew milk",
    "coconutmilk": "coconut milk",
    "ricemilk": "rice milk",
    "hempmilk": "hemp milk",
    "peamilk": "pea milk",
    "beefjerky": "beef jerky",
    "turkeyjerky": "turkey jerky",
    "porkjerky": "pork jerky",
    "saladkit": "salad kit",
}

SPELLING_REWRITES = {
    "graperfruit": "grapefruit",
    "grouton": "crouton",
    "groutons": "croutons",
}

COLOR_TOKENS = {
    "amber",
    "black",
    "blue",
    "brown",
    "clear",
    "gold",
    "golden",
    "green",
    "orange",
    "pink",
    "purple",
    "red",
    "ruby",
    "white",
    "yellow",
}

TAXONOMY_IDENTITY_STOP_TOKENS = (
    WEAK_TOKENS
    | GENERIC_PATH_TOKENS
    | COLOR_TOKENS
    | {
        "boiled",
        "blend",
        "drink",
        "flavor",
        "flavored",
        "juice",
        "kettle",
        "large",
        "larger",
        "mix",
        "pre",
        "pulp",
        "slice",
        "sliced",
        "style",
        "york",
    }
)

BREAD_TERMINAL_STOP_TOKENS = {
    "bakery",
    "boiled",
    "generic",
    "kettle",
    "large",
    "larger",
    "new",
    "pre",
    "slice",
    "sliced",
    "style",
    "york",
}

BREAD_VARIETY_PHRASES = [
    "apple cinnamon",
    "cranberry apple",
    "cinnamon raisin",
    "raisin cinnamon",
    "asiago parmesan",
    "whole wheat",
    "everything",
    "blueberry",
    "cranberry",
    "cinnamon",
    "sesame",
    "asiago",
    "parmesan",
    "onion",
    "garlic",
    "plain",
    "poppy",
    "egg",
]

BREAD_PRODUCT_LEAVES = {
    "bolillo": "Pantry > Bread > Bolillos",
    "bolillos": "Pantry > Bread > Bolillos",
    "concha": "Pantry > Bread > Conchas",
    "conchas": "Pantry > Bread > Conchas",
    "crumpet": "Pantry > Bread > Crumpets",
    "crumpets": "Pantry > Bread > Crumpets",
    "matzo": "Pantry > Bread > Matzo",
    "matzos": "Pantry > Bread > Matzo",
    "matzoh": "Pantry > Bread > Matzo",
    "matzohs": "Pantry > Bread > Matzo",
}


@dataclass
class Candidate:
    leaf: str
    source: str
    weight: float
    reasons: list[str] = field(default_factory=list)


@dataclass
class CandidateScore:
    candidate: Candidate
    score: float
    accepted: bool
    reasons: list[str] = field(default_factory=list)
    identity_overlap: list[str] = field(default_factory=list)
    taxonomy_valid: bool = True


@dataclass
class Decision:
    clean_retail_leaf: str
    clean_status: str
    clean_reason: str
    clean_score: float
    clean_sources: str
    identity_overlap: str
    taxonomy_valid: bool
    parser: dict[str, object]
    candidates: list[CandidateScore] = field(default_factory=list)
    group_applied: str = ""


def ascii_fold(value: str) -> str:
    return unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode("ascii")


def normalize_text(value: str) -> str:
    value = ascii_fold(value).lower()
    value = value.replace("&", " and ").replace("+", " and ")
    for src, dst in COMPOUND_REWRITES.items():
        value = re.sub(rf"\b{re.escape(src)}\b", dst, value)
    for src, dst in SPELLING_REWRITES.items():
        value = re.sub(rf"\b{re.escape(src)}\b", dst, value)
    value = NON_WORD_RE.sub(" ", value)
    return re.sub(r"\s+", " ", value).strip()


def tokens_for(value: str) -> list[str]:
    return [tok for tok in TOKEN_RE.findall(normalize_text(value)) if len(tok) >= 2]


def token_set(value: str) -> set[str]:
    return {singularize(tok) for tok in tokens_for(value)}


def singularize(token: str) -> str:
    if token in {"berries", "cherries"}:
        return token[:-3] + "y"
    if token in {"tomatoes", "potatoes"}:
        return token[:-2]
    if token.endswith("ies") and len(token) > 4:
        return token[:-3] + "y"
    if token.endswith("s") and len(token) > 3 and not token.endswith(("ss", "us")):
        return token[:-1]
    return token


def title_case(value: str) -> str:
    special = {"bbq": "BBQ", "rtd": "RTD"}
    return " ".join(special.get(part, part.capitalize()) for part in value.split())


def has_phrase(tokens: list[str], phrase: str) -> bool:
    wanted = phrase.split()
    if not wanted:
        return False
    return any(tokens[idx : idx + len(wanted)] == wanted for idx in range(len(tokens) - len(wanted) + 1))


def first_present(tokens: Iterable[str], options: Iterable[str]) -> str:
    token_set_ = set(tokens)
    for option in options:
        if option in token_set_:
            return option
    return ""


def parse_json_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(v) for v in value if v]
    if not value:
        return []
    try:
        parsed = json.loads(str(value))
    except json.JSONDecodeError:
        return []
    if isinstance(parsed, list):
        return [str(v) for v in parsed if v]
    return []


def is_truthy(value: str) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def safe_float(value: str, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def confectionery_context(row: dict[str, str], parsed: dict[str, object] | None = None) -> bool:
    title_token_list = tokens_for(row.get("title") or row.get("product_description") or "")
    title_tokens = set(title_token_list)
    bfc = normalize_text(row.get("branded_food_category") or "")
    form = str((parsed or {}).get("form") or "")
    return bool(
        {"candy", "candies", "gummy", "gummi", "gum", "mints", "chew", "chews"} & title_tokens
        or {"gummies", "slices"} & title_tokens
        or has_phrase(title_token_list, "jelly bean")
        or has_phrase(title_token_list, "jelly beans")
        or "candy" in bfc
        or "confectionery" in bfc
        or "chewing gum" in bfc
        or form in {"candy", "candies", "gummy", "gummi", "gum", "mints", "chew", "chews"}
    )


def canonicalize_leaf(leaf: str) -> str:
    leaf = (leaf or "").strip()
    if not leaf:
        return ""
    if leaf.startswith(("ESHA:", "FNDDS:", "FUNNEL:")):
        return ""
    for root, replacement in ROOT_REWRITES.items():
        if leaf == root:
            leaf = replacement
            break
        if leaf.startswith(root + " > "):
            tail = leaf[len(root) + 3 :]
            leaf = replacement + (" > " + tail if tail else "")
            break
    parts = [SEGMENT_REWRITES.get(part.strip(), part.strip()) for part in leaf.split(" > ") if part.strip()]
    if not parts:
        return ""
    fixed: list[str] = []
    for part in parts:
        if fixed and fixed[-1].lower() == part.lower():
            continue
        fixed.append(part)
    parts = fixed

    lowered = {part.lower() for part in parts}
    if "unsweetened" in lowered and "sweetened" in lowered:
        parts = [part for part in parts if part.lower() != "sweetened"]
    if "plain unsweetened" in lowered and "sweetened" in lowered:
        parts = [part for part in parts if part.lower() != "sweetened"]

    return " > ".join(parts)


def load_taxonomy_paths(path: Path = DEFAULT_TAXONOMY) -> set[str]:
    paths: set[str] = set()
    for source_path in (path, Path(str(path) + ".v2bak"), Path(str(path) + ".bak")):
        if not source_path.exists():
            continue
        with source_path.open(newline="", errors="replace") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                leaf = canonicalize_leaf(row.get("retail_leaf") or "")
                if not leaf and row.get("category_path"):
                    category_path = row.get("category_path") or ""
                    head = row.get("head") or ""
                    leaf = canonicalize_leaf(
                        category_path if not head else f"{category_path} > {head}"
                    )
                if leaf and root_of(leaf) in VALID_ROOTS:
                    paths.add(leaf)
    return paths


def root_of(leaf: str) -> str:
    return leaf.split(" > ", 1)[0] if leaf else ""


def leaf_anchor_tokens(leaf: str) -> set[str]:
    out: set[str] = set()
    for token in token_set(leaf):
        if token in WEAK_TOKENS or token in GENERIC_PATH_TOKENS:
            continue
        out.add(token)
    return out


def least_common_parent(leaves: Iterable[str]) -> str:
    split = [[part.strip() for part in leaf.split(" > ") if part.strip()] for leaf in leaves if leaf]
    if not split:
        return ""
    parent: list[str] = []
    for idx in range(min(len(parts) for parts in split)):
        values = {parts[idx].lower() for parts in split}
        if len(values) != 1:
            break
        parent.append(split[0][idx])
    return " > ".join(parent)


def group_key(row: dict[str, str]) -> tuple[str, str, str]:
    return (
        normalize_text(row.get("title") or row.get("product_description") or ""),
        normalize_text(row.get("branded_food_category") or ""),
        normalize_text(row.get("current_esha") or row.get("current_esha_desc") or ""),
    )


def leaf_summary(leaf: str, limit: int = 6) -> str:
    anchors = sorted(leaf_anchor_tokens(leaf))
    return ",".join(anchors[:limit])


class RetailLeafCleaner:
    def __init__(
        self,
        group_choices: dict[tuple[str, str, str], tuple[str, str]] | None = None,
        enable_group_smoothing: bool = True,
    ) -> None:
        self.lexicon = AxisLexicon(repo_root())
        self.group_choices = group_choices or {}
        self.enable_group_smoothing = enable_group_smoothing
        self.taxonomy_paths = load_taxonomy_paths()
        self.taxonomy_token_index = self.build_taxonomy_token_index(self.taxonomy_paths)

    def build_taxonomy_token_index(self, paths: set[str]) -> dict[tuple[str, str], list[str]]:
        index: dict[tuple[str, str], list[str]] = defaultdict(list)
        for leaf in sorted(paths):
            parts = [part.strip() for part in leaf.split(" > ") if part.strip()]
            if len(parts) < 3:
                continue
            for depth in range(1, len(parts)):
                prefix = " > ".join(parts[:depth])
                tail = " > ".join(parts[depth:])
                for token in leaf_anchor_tokens(tail):
                    index[(prefix, token)].append(leaf)
        return dict(index)

    def parse_product(self, row: dict[str, str]) -> dict[str, object]:
        parser_row = {
            "gtin_upc": row.get("gtin_upc", ""),
            "fdc_id": row.get("fdc_id", ""),
            "product_description": row.get("title", ""),
            "branded_food_category": row.get("branded_food_category", ""),
            "fixy_category": row.get("branded_food_category", ""),
            "v6_fndds_description": row.get("current_esha_desc", ""),
            "best_esha_description": row.get("current_esha_desc", ""),
        }
        return parse_row(parser_row, self.lexicon)

    def clean_row(self, row: dict[str, str], apply_group: bool = True) -> Decision:
        parsed = self.parse_product(row)
        candidates = self.collect_candidates(row, parsed)
        scored = [self.score_candidate(row, parsed, candidate) for candidate in candidates]
        accepted = [score for score in scored if score.accepted]
        accepted.sort(key=lambda score: (-score.score, -len(score.candidate.leaf), score.candidate.leaf))

        if accepted:
            best = accepted[0]
            status = self.status_for(best)
            reason = ";".join(best.reasons[:5])
        else:
            fallback = self.safe_fallback(row, parsed)
            if fallback.leaf in VALID_ROOTS:
                fallback = Candidate("", fallback.source, fallback.weight, fallback.reasons + ["root_only_not_leaf"])
            best = self.score_candidate(row, parsed, fallback)
            best.accepted = bool(fallback.leaf and fallback.leaf not in VALID_ROOTS)
            status = "review" if not fallback.leaf else "accepted_parent_only"
            reason = "no_candidate_passed_identity_gate"

        group_applied = ""
        if apply_group and self.enable_group_smoothing and best.candidate.leaf:
            replacement, replacement_status = self.group_choices.get(group_key(row), ("", ""))
            if replacement and replacement != best.candidate.leaf:
                replacement_score = self.score_candidate(
                    row,
                    parsed,
                    Candidate(replacement, "exact_group_smoothing", best.score + 0.5, ["exact_group_smoothing"]),
                )
                if replacement_score.accepted:
                    best = replacement_score
                    status = replacement_status or status
                    reason = (reason + ";exact_group_smoothing").strip(";")
                    group_applied = replacement

        return Decision(
            clean_retail_leaf=best.candidate.leaf,
            clean_status=status,
            clean_reason=reason or ";".join(best.reasons[:5]),
            clean_score=round(best.score, 3),
            clean_sources=best.candidate.source,
            identity_overlap="|".join(best.identity_overlap),
            taxonomy_valid=best.taxonomy_valid,
            parser=parsed,
            candidates=scored,
            group_applied=group_applied,
        )

    def collect_candidates(self, row: dict[str, str], parsed: dict[str, object]) -> list[Candidate]:
        candidates: list[Candidate] = []
        seen: dict[str, Candidate] = {}

        def add(leaf: str, source: str, weight: float, reason: str = "") -> None:
            leaf = canonicalize_leaf(leaf)
            if not leaf:
                return
            if leaf in seen:
                seen[leaf].weight += weight
                seen[leaf].source += f"|{source}"
                if reason:
                    seen[leaf].reasons.append(reason)
                return
            candidate = Candidate(leaf=leaf, source=source, weight=weight, reasons=[reason] if reason else [])
            seen[leaf] = candidate
            candidates.append(candidate)

        parser_leaf = str(parsed.get("retail_leaf") or "")
        parser_weight = 3.6
        if parsed.get("needs_review"):
            parser_weight = 2.4
        if parser_leaf and "Other > Unclassified" not in parser_leaf:
            add(parser_leaf, "axis_parser", parser_weight, "axis_parser_leaf")

        for router_leaf, reason in self.family_router(row, parsed):
            add(router_leaf, "family_router", 7.0, reason)

        for taxonomy_leaf, weight, reason in self.taxonomy_identity_candidates(row, parsed):
            add(taxonomy_leaf, "taxonomy_identity", weight, reason)

        current = row.get("retail_leaf") or ""
        current_weight = 1.2 + 2.5 * safe_float(row.get("confidence"))
        if is_truthy(row.get("gap_flag", "")):
            current_weight -= 2.0
        if row.get("sources_agreed") == "0":
            current_weight -= 0.6
        add(current, "current_v2", current_weight, "current_v2_leaf")

        provenance = self.provenance(row)
        for key, value in provenance.items():
            if not isinstance(value, dict):
                continue
            for field in ("leaf", "resolved_leaf", "anchor_leaf", "forced", "hint", "fallback_leaf"):
                leaf = value.get(field)
                if not leaf:
                    continue
                source_weight = self.provenance_weight(key, field, row)
                add(str(leaf), f"provenance:{key}.{field}", source_weight, f"provenance_{key}")

        return candidates

    def taxonomy_identity_candidates(self, row: dict[str, str], parsed: dict[str, object]) -> list[tuple[str, float, str]]:
        prefixes = self.taxonomy_context_prefixes(row, parsed)
        token_sources = self.taxonomy_identity_token_sources(row, parsed)
        if not prefixes or not token_sources:
            return []

        out: list[tuple[str, float, str]] = []
        seen: set[str] = set()
        for prefix in prefixes:
            if prefix.count(" > ") < 2:
                continue
            for token, sources in token_sources.items():
                for leaf in self.taxonomy_token_index.get((prefix, token), []):
                    if leaf in seen:
                        continue
                    tail = leaf[len(prefix) + 3 :] if leaf.startswith(prefix + " > ") else ""
                    if tail.count(" > ") > 0:
                        continue
                    tail_anchors = {
                        anchor
                        for anchor in leaf_anchor_tokens(tail)
                        if anchor not in TAXONOMY_IDENTITY_STOP_TOKENS
                    }
                    if not tail_anchors:
                        continue
                    # A taxonomy leaf tail is allowed to fill in missing
                    # specificity, but it cannot smuggle in another identity
                    # just because one loose token matched. This blocks cases
                    # like Bagels > Onion New York for an asiago bagel.
                    if tail_anchors - set(token_sources):
                        continue
                    seen.add(leaf)
                    source_label = "title" if "title" in sources else sorted(sources)[0]
                    weight = 5.4 if "title" in sources else 4.4
                    if prefix.count(" > ") >= 2:
                        weight += 0.6
                    out.append((leaf, weight, f"taxonomy_identity_{source_label}"))
        return out

    def taxonomy_context_prefixes(self, row: dict[str, str], parsed: dict[str, object]) -> list[str]:
        prefixes: list[str] = []

        def add(prefix: str) -> None:
            prefix = canonicalize_leaf(prefix)
            if prefix and prefix not in prefixes:
                prefixes.append(prefix)

        parser_leaf = canonicalize_leaf(str(parsed.get("retail_leaf") or ""))
        parser_parts = [part.strip() for part in parser_leaf.split(" > ") if part.strip()]
        for depth in range(len(parser_parts) - 1, 0, -1):
            add(" > ".join(parser_parts[:depth]))

        parsed_bits = [
            str(parsed.get("supercategory") or ""),
            str(parsed.get("category_group") or ""),
            str(parsed.get("category") or ""),
        ]
        if all(parsed_bits):
            add(" > ".join(parsed_bits))
        if parsed_bits[0] and parsed_bits[1]:
            add(" > ".join(parsed_bits[:2]))

        form = str(parsed.get("form") or "")
        bfc = normalize_text(row.get("branded_food_category") or "")
        if form == "juice" or "juice" in bfc:
            add("Beverage > Fruit-based Drinks > Juice")
        if form == "smoothie" or "smoothie" in bfc:
            add("Beverage > Fruit-based Drinks > Smoothie")
        if form in {"soda", "seltzer", "kombucha", "tea", "coffee", "water"}:
            add(f"Beverage > {title_case(form)}")
        return prefixes

    def taxonomy_identity_token_sources(self, row: dict[str, str], parsed: dict[str, object]) -> dict[str, set[str]]:
        sources: dict[str, set[str]] = defaultdict(set)

        def add_tokens(value: str, source: str) -> None:
            for token in token_set(value):
                if token in TAXONOMY_IDENTITY_STOP_TOKENS:
                    continue
                sources[token].add(source)

        add_tokens(row.get("title") or row.get("product_description") or "", "title")
        add_tokens(row.get("distinctive_tokens") or "", "distinctive")
        add_tokens(row.get("distinctive_bigrams") or "", "distinctive")
        add_tokens(str(parsed.get("primary_food") or ""), "parser")
        add_tokens(str(parsed.get("flavor") or ""), "parser")
        add_tokens(row.get("current_esha_desc") or "", "esha")
        return dict(sources)

    def provenance(self, row: dict[str, str]) -> dict[str, object]:
        raw = row.get("provenance") or ""
        if not raw:
            return {}
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    def provenance_weight(self, key: str, field: str, row: dict[str, str]) -> float:
        if key == "b1_parser":
            return 2.8
        if key in {"b_axis_plant_milk", "plant_milk_safety_net"}:
            return 3.0
        if key == "b_neg1_esha_anchor":
            return 1.8
        if key == "b0_bfc":
            return 1.0 if field == "hint" else 1.2
        if key == "b8_ingredient_fndds":
            return 1.2
        if key == "b6_embed_knn":
            return 0.4 if row.get("sources_agreed") == "0" else 0.8
        if key == "b7_funnel":
            return 0.5
        return 0.8

    def family_router(self, row: dict[str, str], parsed: dict[str, object]) -> list[tuple[str, str]]:
        title = row.get("title") or ""
        bfc = row.get("branded_food_category") or ""
        desc = row.get("current_esha_desc") or ""
        text = normalize_text(" ".join([title, bfc, desc]))
        bfc_norm = normalize_text(bfc)
        title_tokens = tokens_for(title)
        token_set_ = set(title_tokens)
        out: list[tuple[str, str]] = []
        form = str(parsed.get("form") or "")
        primary = str(parsed.get("primary_food") or "")
        category_group = str(parsed.get("category_group") or "")
        parser_leaf = str(parsed.get("retail_leaf") or "")

        # Chemical/additive cases: never let an embedding promote these to
        # ordinary baked foods.
        if has_phrase(title_tokens, "calcium hydroxide"):
            out.append(("Pantry > Baking > Additive > Calcium Hydroxide", "chemical_additive_router"))
        if "yeast" in token_set_ and (("baking" in token_set_) or ("rapidrise" in token_set_) or ("instant" in token_set_)):
            out.append(("Pantry > Baking > Yeast", "baking_yeast_router"))
        if "cocoa" in token_set_ and ("baking" in token_set_ or "powdered" in token_set_ or "powder" in token_set_):
            out.append(("Pantry > Baking > Cocoa", "baking_cocoa_router"))
        if "protein" in token_set_ and "powder" in token_set_:
            flavor = self.first_flavor(title_tokens, default=primary or "plain")
            protein = self.protein_powder_base(title_tokens, primary)
            out.append((f"Pantry > Protein Powders > {protein} > {title_case(flavor)}", "protein_powder_router"))
        if (token_set_ & {"bar", "bars"}) and ("protein" in token_set_ or "energy" in token_set_ or "snack" in bfc_norm):
            flavor = self.first_flavor(title_tokens, default=primary or "plain")
            if "protein" in token_set_:
                out.append((f"Snack > Bar > Protein > {title_case(flavor)}", "bar_router"))
            elif "granola" in token_set_:
                out.append((f"Snack > Bar > Granola > {title_case(flavor)}", "bar_router"))
            else:
                out.append((f"Snack > Bar > {title_case(flavor)}", "bar_router"))

        if confectionery_context(row, parsed):
            if has_phrase(title_tokens, "jelly beans") or has_phrase(title_tokens, "jelly bean"):
                out.append(("Snack > Candy > Jelly Beans", "candy_form_router"))
            elif "jelly" in token_set_ and ("slice" in token_set_ or "slices" in token_set_):
                out.append(("Snack > Candy > Jelly Slices", "candy_form_router"))
            elif "gummy" in token_set_ or "gummi" in token_set_ or "gummies" in token_set_:
                out.append(("Snack > Candy > Gummy", "candy_form_router"))
            elif "gum" in token_set_:
                out.append(("Snack > Candy > Gum", "candy_form_router"))
            elif has_phrase(title_tokens, "hard candy") or "candy" in token_set_:
                flavor = self.first_flavor(title_tokens, default="")
                leaf = "Snack > Candy > Hard Candy" if "hard" in token_set_ else "Snack > Candy"
                if flavor and flavor not in {"plain", "original"}:
                    leaf += f" > {title_case(flavor)}"
                out.append((leaf, "candy_form_router"))

        bread_leaf = self.bread_variety_leaf(row, parsed, title_tokens)
        if bread_leaf:
            out.append((bread_leaf, "bread_variety_router"))

        if (
            "mix" in token_set_
            and ("baking" in bfc_norm or "cake" in bfc_norm or "cookie" in bfc_norm or "cupcake" in bfc_norm or "baking" in token_set_)
            and "protein" not in token_set_
        ):
            product = first_present(title_tokens, ["cake", "cupcake", "cookie", "brownie", "pancake", "biscuit", "muffin"])
            product_label = title_case(product or primary or "Baking")
            out.append((f"Pantry > Baking > Mix > {product_label}", "baking_mix_generic_router"))

        # Edible servingware is a real retail class, but not a cereal class.
        if "spoon" in token_set_ or "spoons" in token_set_:
            if "edible" in token_set_ or "cocoa" in token_set_ or "honey" in token_set_:
                out.append(("Other > Edible Servingware > Spoon", "edible_spoon_router"))

        # Jerky is meat identity even when the BFC says snack.
        if "jerky" in token_set_:
            plant_based = has_phrase(title_tokens, "plant based") or "vegan" in token_set_ or "banana" in token_set_
            protein = first_present(title_tokens, ["beef", "turkey", "pork", "chicken", "salmon", "bacon"])
            if plant_based and not protein:
                out.append(("Snack > Jerky > Plant-based", "plant_based_jerky_router"))
            elif plant_based and protein == "bacon":
                out.append(("Snack > Jerky > Plant-based", "plant_based_jerky_router"))
            elif protein:
                if protein == "bacon":
                    protein = "pork"
                out.append((f"Meat & Seafood > Jerky > {title_case(protein)}", "jerky_identity_router"))
            else:
                out.append(("Meat & Seafood > Jerky", "jerky_identity_router"))

        # Jams/jellies/preserves: form determines the shelf, pepper/fruit
        # determines the identity tail.
        spread_shelf = "jam" in bfc_norm or "jelly" in bfc_norm or "spread" in bfc_norm or "preserve" in bfc_norm
        solid_product = bool(
            token_set_
            & {
                "bar",
                "bars",
                "bean",
                "beans",
                "candy",
                "candies",
                "chew",
                "chews",
                "cereal",
                "cookie",
                "cookies",
                "drops",
                "gummi",
                "gummy",
                "gum",
                "mints",
                "oats",
                "pandas",
                "protein",
                "slice",
                "slices",
            }
        )
        spread_title_product = (
            not solid_product
            and (form in {"jam", "jelly", "preserves", "spread"} or {"jam", "jelly", "preserves", "spread"} & token_set_)
        )
        if (spread_shelf or spread_title_product) and (form in {"jam", "jelly", "preserves", "spread"} or {"jam", "jelly", "preserves", "spread"} & token_set_):
            spread_form = "Jelly" if "jelly" in token_set_ else "Jam"
            if "preserves" in token_set_ or "preserve" in token_set_:
                spread_form = "Preserves"
            leaf_parts = ["Pantry", "Spreads", spread_form]
            if token_set_ & PEPPERS:
                leaf_parts.append("Pepper")
                pepper = first_present(title_tokens, ["habanero", "jalapeno", "chile", "chili"])
                if pepper:
                    leaf_parts.append(title_case(pepper))
            else:
                fruit = first_present(title_tokens, sorted(FRUITS))
                if fruit:
                    leaf_parts.append(title_case(fruit))
            out.append((" > ".join(leaf_parts), "spread_form_router"))

        # Milk routing: milk is the class only when the product form is milk
        # or the shelf category explicitly says milk/cream. Buttermilk in
        # biscuit mix remains a baking product.
        if bfc_norm in {"plant based milk", "plant based milk alternatives"}:
            plant = first_present(title_tokens, ["almond", "oat", "soy", "coconut", "cashew", "rice", "pea", "hemp"])
            if plant:
                flavor_label = self.milk_flavor_from_tokens(title_tokens)
                out.append(
                    (
                        f"Beverage > Plant-based Milk > {title_case(plant)} Milk > {flavor_label}",
                        "plant_milk_bfc_router",
                    )
                )

        if ("milkshake" in token_set_ or has_phrase(title_tokens, "milk shake")) and "powder" not in token_set_:
            flavor = self.first_flavor(title_tokens, default="plain")
            out.append((f"Beverage > Shake > Milkshake > {title_case(flavor)}", "milkshake_router"))
        elif "shake" in token_set_ and ("protein" in token_set_ or "nutrition" in token_set_):
            flavor = self.first_flavor(title_tokens, default="plain")
            out.append((f"Beverage > Functional > Protein Shake > {title_case(flavor)}", "protein_shake_router"))

        milk_context = (
            "milk" in token_set_
            or "buttermilk" in token_set_
            or "creamer" in token_set_
            or has_phrase(title_tokens, "half and half")
            or "milk" in normalize_text(bfc).split()
            or normalize_text(bfc) in {"cream", "milk additives"}
        )
        milk_component_context = (
            "with" in token_set_
            and "milk" in token_set_
            and form in {"coffee", "drink", "beverage", "latte", "shake", "smoothie"}
            and bfc_norm not in {"milk", "plant based milk", "plant based milk alternatives"}
        )
        chocolate_confection_context = (
            "chocolate" in token_set_
            and (token_set_ & {"candy", "candies", "bar", "bars", "peanut", "peanuts", "apple", "caramel"})
            and bfc_norm not in {"milk", "plant based milk", "plant based milk alternatives"}
        )
        buttermilk_baking_context = (
            "buttermilk" in token_set_
            and (token_set_ & {"biscuit", "biscuits", "dough", "mix", "pancake", "pancakes", "waffle", "waffles"})
        )
        if milk_context and form not in MILK_BLOCKING_FORMS and not milk_component_context and not chocolate_confection_context and not buttermilk_baking_context:
            if category_group == "Plant-based Milk" and parser_leaf:
                out.append((parser_leaf, "plant_milk_axis_router"))
            elif has_phrase(title_tokens, "half and half") or has_phrase(title_tokens, "half half"):
                out.append(("Dairy > Cream > Half and Half", "cream_half_and_half_router"))
            elif "creamer" in token_set_:
                out.append(("Dairy > Creamer > Coffee Creamer", "creamer_router"))
            elif "buttermilk" in token_set_:
                out.append(("Dairy > Buttermilk", "buttermilk_beverage_router"))
            elif "milk" in token_set_:
                if "evaporated" in token_set_ and "filled" in token_set_:
                    out.append(("Beverage > Dairy Milk > Evaporated Filled Milk", "milk_subtype_router"))
                elif "evaporated" in token_set_:
                    out.append(("Beverage > Dairy Milk > Evaporated Milk", "milk_subtype_router"))
                elif "condensed" in token_set_:
                    out.append(("Beverage > Dairy Milk > Condensed Milk", "milk_subtype_router"))
                elif "goat" in token_set_ or "goats" in token_set_:
                    out.append(("Beverage > Dairy Milk > Goat Milk", "milk_subtype_router"))
                elif "chocolate" in token_set_:
                    out.append(("Beverage > Dairy Milk > Chocolate Milk", "milk_subtype_router"))
                elif "strawberry" in token_set_:
                    out.append(("Beverage > Dairy Milk > Strawberry Milk", "milk_subtype_router"))
                elif "fat" in token_set_ and "free" in token_set_:
                    out.append(("Beverage > Dairy Milk > Fat Free Milk", "milk_subtype_router"))
                elif "reduced" in token_set_ and "fat" in token_set_:
                    out.append(("Beverage > Dairy Milk > Reduced Fat Milk", "milk_subtype_router"))
                elif "whole" in token_set_:
                    out.append(("Beverage > Dairy Milk > Whole Milk", "milk_subtype_router"))

        # Baking products: buttermilk is usually a flavor/modifier here.
        if "buttermilk" in token_set_ and form in {"mix", "biscuit", "biscuits", "pancake", "pancakes", "bread", "dough"}:
            if "mix" in token_set_:
                product = "Biscuit" if ("biscuit" in token_set_ or "biscuits" in token_set_) else title_case(primary or "Baking")
                out.append((f"Pantry > Baking > Mix > {product} > Buttermilk", "baking_mix_router"))
            else:
                product = "Biscuit" if ("biscuit" in token_set_ or "biscuits" in token_set_) else title_case(form)
                out.append((f"Pantry > Bread > {product} > Buttermilk", "baking_buttermilk_router"))

        # Canned produce and produce leaf specificity.
        if primary in PRODUCE_LEAVES:
            base = f"Produce > Vegetable > {title_case(primary)}"
            if normalize_text(bfc) == "canned vegetables" or "canned" in token_set_:
                base = f"Pantry > Canned > Vegetable > {title_case(primary)}"
            elif "baby" in token_set_ and primary in {"kale", "spinach", "arugula", "lettuce"}:
                base += " > Baby"
            elif "organic" in token_set_:
                base += " > Organic"
            out.append((base, "produce_identity_router"))
        for produce_token in sorted(PRODUCE_LEAVES):
            if produce_token in token_set_ and produce_token != primary:
                base = f"Produce > Vegetable > {title_case(produce_token)}"
                if normalize_text(bfc) == "canned vegetables" or "canned" in token_set_:
                    base = f"Pantry > Canned > Vegetable > {title_case(produce_token)}"
                out.append((base, "produce_identity_router"))
                break

        if has_phrase(title_tokens, "salad kit") or has_phrase(title_tokens, "salad kits"):
            out.append(("Produce > Salad Kit", "salad_kit_router"))
        elif has_phrase(title_tokens, "mixed greens") or has_phrase(title_tokens, "greens blend") or has_phrase(title_tokens, "power greens") or has_phrase(title_tokens, "spring mix"):
            out.append(("Produce > Greens Blend", "greens_blend_router"))

        # Meals/composites: for these, ingredient identity is subordinate to
        # dish structure. Parser output is the safest place to start.
        composite_bfc = any(
            phrase in bfc_norm
            for phrase in [
                "frozen dinners",
                "frozen entrees",
                "other deli",
                "prepared subs",
                "sandwiches",
                "pasta dinners",
                "frozen breakfast",
            ]
        )
        if parsed.get("retail_type") == "composite_dish" and parser_leaf:
            out.append((parser_leaf, "composite_axis_router"))
        elif composite_bfc and ({"meal", "dinner", "entree", "served", "bowl", "kit"} & token_set_):
            detail = self.title_summary(title_tokens)
            out.append((f"Meal > Composite Dishes > Entree > {detail}", "meal_bfc_router"))

        return out

    def milk_flavor_from_tokens(self, tokens: list[str]) -> str:
        if set(tokens) & {"almond", "oat", "soy", "coconut", "cashew", "rice", "pea", "hemp"} and "chocolate" in tokens:
            if has_phrase(tokens, "mexican hot chocolate"):
                flavor = "mexican hot chocolate"
            elif has_phrase(tokens, "dark chocolate"):
                flavor = "dark chocolate"
            else:
                flavor = "chocolate"
            claims: list[str] = []
            if "unsweetened" in tokens or "unsweet" in tokens:
                claims.append("Unsweetened")
            label = title_case(flavor)
            if "Unsweetened" in claims and "unsweetened" not in flavor:
                label += " Unsweetened"
            return label
        flavor = self.first_flavor(tokens, default="")
        claims: list[str] = []
        if "unsweetened" in tokens or "unsweet" in tokens:
            claims.append("Unsweetened")
        if not flavor or flavor in {"original", "plain", "unflavored"}:
            return "Plain Unsweetened" if "Unsweetened" in claims else title_case(flavor or "Plain")
        label = title_case(flavor)
        if "Unsweetened" in claims and "unsweetened" not in flavor:
            label += " Unsweetened"
        return label

    def first_flavor(self, tokens: list[str], default: str = "") -> str:
        if "pb" in tokens:
            return "peanut butter"
        for phrase in ["mexican hot chocolate", "dark chocolate", "milk chocolate", "white chocolate", "salted caramel", "peanut butter"]:
            if has_phrase(tokens, phrase):
                return phrase
        for token in [
            "chocolate",
            "vanilla",
            "strawberry",
            "banana",
            "caramel",
            "coffee",
            "mocha",
            "cinnamon",
            "original",
            "plain",
            "unflavored",
        ]:
            if token in tokens:
                return token
        return default

    def bread_variety_leaf(self, row: dict[str, str], parsed: dict[str, object], title_tokens: list[str]) -> str:
        bfc_norm = normalize_text(row.get("branded_food_category") or "")
        desc_tokens = tokens_for(row.get("current_esha_desc") or "")
        parsed_group = str(parsed.get("category_group") or "")
        parsed_category = str(parsed.get("category") or "")
        parsed_form = str(parsed.get("form") or "")
        all_tokens = title_tokens + desc_tokens
        token_set_ = {singularize(token) for token in all_tokens}

        bread_context = (
            parsed_group == "Bread"
            or "bread" in bfc_norm.split()
            or "breads" in bfc_norm.split()
            or "buns" in bfc_norm.split()
            or "bun" in bfc_norm.split()
            or "bagel" in token_set_
        )
        if not bread_context:
            return ""

        crouton_leaf = self.crouton_leaf(title_tokens)
        if crouton_leaf:
            return crouton_leaf

        for token in title_tokens:
            leaf = BREAD_PRODUCT_LEAVES.get(token) or BREAD_PRODUCT_LEAVES.get(singularize(token))
            if leaf:
                return leaf

        is_bagel = (
            "bagel" in token_set_
            or parsed_category in {"Bagel", "Bagels"}
            or parsed_form in {"bagel", "bagels"}
        )
        if not is_bagel:
            return ""

        segment = "Bagels" if "bagels" in title_tokens or parsed_category == "Bagels" or parsed_form == "bagels" else "Bagel"
        variety = self.bread_variety(all_tokens)
        leaf = f"Pantry > Bread > {segment}"
        if variety:
            leaf += f" > {title_case(variety)}"
        return leaf

    def crouton_leaf(self, tokens: list[str]) -> str:
        token_set_ = {singularize(token) for token in tokens}
        if "crouton" not in token_set_:
            return ""
        if "seasoned" in token_set_ or "season" in token_set_:
            return "Pantry > Croutons > Seasoned"
        if "garlic" in token_set_:
            return "Pantry > Croutons > Garlic"
        if "caesar" in token_set_:
            return "Pantry > Croutons > Caesar"
        return "Pantry > Croutons"

    def bread_variety(self, tokens: list[str]) -> str:
        normalized_tokens = [singularize(token) for token in tokens if token not in BREAD_TERMINAL_STOP_TOKENS]
        for phrase in BREAD_VARIETY_PHRASES:
            if has_phrase(normalized_tokens, phrase):
                return phrase
        token_set_ = set(normalized_tokens)
        for token in ["asiago", "parmesan", "blueberry", "cranberry", "apple", "cinnamon", "sesame", "onion", "garlic", "plain"]:
            if token in token_set_:
                return token
        return ""

    def title_summary(self, tokens: list[str], limit: int = 6) -> str:
        skip = {"and", "the", "with", "served", "over", "flavored", "flavor", "count", "oz"}
        kept = [tok for tok in tokens if tok not in skip and not tok.isdigit()]
        return title_case(" ".join(kept[:limit])) or "Entree"

    def protein_powder_base(self, tokens: list[str], primary: str) -> str:
        if "whey" in tokens:
            return "Whey Protein"
        if "casein" in tokens:
            return "Casein Protein"
        if "collagen" in tokens:
            return "Collagen Protein"
        if has_phrase(tokens, "plant based") or "plant" in tokens:
            return "Plant Protein"
        if primary in {"almond", "pea", "soy"}:
            return f"{title_case(primary)} Protein"
        return "Protein"

    def score_candidate(self, row: dict[str, str], parsed: dict[str, object], candidate: Candidate) -> CandidateScore:
        leaf = canonicalize_leaf(candidate.leaf)
        candidate = Candidate(leaf, candidate.source, candidate.weight, list(candidate.reasons))
        reasons = list(candidate.reasons)
        taxonomy_valid = self.taxonomy_valid(leaf)
        if not taxonomy_valid:
            return CandidateScore(candidate, -999.0, False, reasons + ["taxonomy_invalid"], [], False)

        if self.has_path_contradiction(leaf):
            return CandidateScore(candidate, -999.0, False, reasons + ["path_contradiction"], [], False)

        if leaf in VALID_ROOTS:
            return CandidateScore(candidate, -700.0, False, reasons + ["root_only_not_leaf"], [], taxonomy_valid)

        if self.has_weak_bread_terminal(leaf):
            return CandidateScore(candidate, -450.0, False, reasons + ["bread_terminal_not_identity"], [], taxonomy_valid)

        product_tokens = self.product_identity_tokens(row, parsed)
        title_tokens = token_set(row.get("title") or "")
        bfc_tokens = token_set(row.get("branded_food_category") or "")
        esha_tokens = token_set(row.get("current_esha_desc") or "")
        anchors = leaf_anchor_tokens(leaf)
        overlap = sorted(anchors & product_tokens)
        secondary_overlap = sorted(anchors & (bfc_tokens | esha_tokens))

        provenance = self.provenance(row)
        audit_missing_title = bool(
            isinstance(provenance.get("guards"), dict)
            and provenance.get("guards", {}).get("b_neg1_audit_token_missing_in_title")
        )

        if anchors:
            if not overlap and not secondary_overlap:
                return CandidateScore(candidate, -500.0, False, reasons + ["identity_no_overlap"], [], taxonomy_valid)
            if (
                audit_missing_title
                and not (anchors & title_tokens)
                and candidate.source == "provenance:b_neg1_esha_anchor.anchor_leaf"
            ):
                return CandidateScore(candidate, -400.0, False, reasons + ["audit_anchor_missing_from_title"], [], taxonomy_valid)

        parsed_super = str(parsed.get("supercategory") or "")
        leaf_root = root_of(leaf)
        title_token_list = tokens_for(row.get("title") or "")
        bfc_norm = normalize_text(row.get("branded_food_category") or "")
        is_confectionery = confectionery_context(row, parsed)
        if is_confectionery:
            if leaf_root != "Snack":
                return CandidateScore(candidate, -450.0, False, reasons + ["confectionery_requires_snack_root"], [], taxonomy_valid)
            if leaf_root in {"Produce", "Meal"}:
                return CandidateScore(candidate, -450.0, False, reasons + ["confectionery_flavor_not_product_identity"], [], taxonomy_valid)
            if leaf_root == "Pantry" and "Spreads" in leaf:
                return CandidateScore(candidate, -450.0, False, reasons + ["confectionery_jelly_not_spread"], [], taxonomy_valid)
            if "Combo Packs" in leaf and not (
                {"combo", "kit", "pack", "packs", "variety"} & set(title_token_list)
                or has_phrase(title_token_list, "snack pack")
            ):
                return CandidateScore(candidate, -450.0, False, reasons + ["confectionery_not_combo_pack"], [], taxonomy_valid)
        root_mismatch = parsed_super and parsed_super != "Other" and leaf_root != parsed_super
        if root_mismatch and not (anchors & (title_tokens | bfc_tokens)) and candidate.source in {"current_v2"}:
            return CandidateScore(candidate, -300.0, False, reasons + ["root_mismatch_without_title_anchor"], overlap, taxonomy_valid)

        score = candidate.weight
        score += 0.6 * len(overlap)
        score += 0.2 * len(secondary_overlap)
        if leaf_root == parsed_super:
            score += 0.8
        if "plant_milk_bfc_router" in candidate.reasons:
            score += 3.0
        elif bfc_norm in {"plant based milk", "plant based milk alternatives"} and leaf_root != "Beverage":
            score -= 2.0
            reasons.append("plant_milk_bfc_root_penalty")
        router_bonus = {
            "bar_router": 6.0,
            "candy_form_router": 6.0,
            "spread_form_router": 5.0,
            "milk_subtype_router": 3.0,
            "produce_identity_router": 2.5,
            "bread_variety_router": 5.0,
            "bread_product_router": 5.0,
            "baking_mix_router": 1.0,
            "baking_mix_generic_router": 1.0,
        }
        for reason_key, bonus in router_bonus.items():
            if reason_key in candidate.reasons:
                score += bonus
        if "salt" in anchors and has_phrase(title_token_list, "no salt") and "salt" not in bfc_norm:
            score -= 5.0
            reasons.append("salt_claim_identity_penalty")
        if "spreads" in leaf.lower() and {"bar", "bars", "protein"} & set(title_token_list) and "bar" in bfc_norm:
            score -= 5.0
            reasons.append("spread_bar_identity_penalty")
        if parsed.get("retail_type") == "composite_dish" and leaf_root == "Meal":
            score += 1.0
        if candidate.source.startswith("taxonomy_identity"):
            score += 1.6
            reasons.append("taxonomy_identity_candidate")
        if candidate.source.startswith("family_router"):
            score += 1.0
        if candidate.source.startswith("axis_parser") and not parsed.get("needs_review"):
            score += 0.8
        if is_truthy(row.get("gap_flag", "")) and candidate.source == "current_v2":
            score -= 2.0
            reasons.append("current_gap_penalty")
        if row.get("sources_agreed") == "0" and candidate.source == "current_v2":
            score -= 0.4
            reasons.append("current_no_agreement_penalty")

        if anchors - (product_tokens | bfc_tokens | esha_tokens):
            score -= 0.25 * len(anchors - (product_tokens | bfc_tokens | esha_tokens))

        accepted = score >= 1.2
        if accepted:
            reasons.append("identity_gate_passed")
        return CandidateScore(candidate, score, accepted, reasons, overlap or secondary_overlap, taxonomy_valid)

    def taxonomy_valid(self, leaf: str) -> bool:
        if not leaf:
            return False
        if leaf.startswith(("ESHA:", "FNDDS:", "FUNNEL:")):
            return False
        if "FUNNEL:" in leaf:
            return False
        return root_of(leaf) in VALID_ROOTS

    def has_path_contradiction(self, leaf: str) -> bool:
        tokens = token_set(leaf)
        return "unsweetened" in tokens and "sweetened" in tokens

    def has_weak_bread_terminal(self, leaf: str) -> bool:
        parts = [part.strip() for part in leaf.split(" > ") if part.strip()]
        if len(parts) < 4 or parts[:2] != ["Pantry", "Bread"]:
            return False
        terminal_tokens = token_set(parts[-1])
        return bool(terminal_tokens) and terminal_tokens <= BREAD_TERMINAL_STOP_TOKENS

    def product_identity_tokens(self, row: dict[str, str], parsed: dict[str, object]) -> set[str]:
        values_: list[str] = [
            row.get("title") or "",
            row.get("distinctive_tokens") or "",
            row.get("distinctive_bigrams") or "",
            row.get("product_form_guess") or "",
            str(parsed.get("primary_food") or ""),
            str(parsed.get("form") or ""),
            str(parsed.get("category") or ""),
            str(parsed.get("category_group") or ""),
        ]
        product_tokens: set[str] = set()
        for value in values_:
            product_tokens |= token_set(value)
        return {tok for tok in product_tokens if tok not in WEAK_TOKENS and tok not in GENERIC_PATH_TOKENS}

    def safe_fallback(self, row: dict[str, str], parsed: dict[str, object]) -> Candidate:
        if confectionery_context(row, parsed):
            return Candidate("Snack > Candy", "safe_confectionery_parent", 1.6, ["safe_confectionery_parent"])

        parser_leaf = canonicalize_leaf(str(parsed.get("retail_leaf") or ""))
        if parser_leaf and self.taxonomy_valid(parser_leaf) and "Other > Unclassified" not in parser_leaf:
            parent = least_common_parent([parser_leaf])
            return Candidate(parent, "safe_parser_parent", 1.5, ["safe_parser_parent"])

        bfc = normalize_text(row.get("branded_food_category") or "")
        if "milk" in bfc:
            return Candidate("Beverage > Dairy Milk", "safe_bfc_parent", 1.2, ["safe_bfc_parent"])
        if "jam" in bfc or "jelly" in bfc or "spread" in bfc:
            return Candidate("Pantry > Spreads", "safe_bfc_parent", 1.2, ["safe_bfc_parent"])
        return Candidate("", "unmapped", 0.0, ["no_safe_fallback"])

    def status_for(self, best: CandidateScore) -> str:
        if best.candidate.source.startswith("family_router"):
            return "accepted_router"
        if best.candidate.source.startswith("exact_group_smoothing"):
            return "accepted_group"
        if best.candidate.leaf.count(" > ") <= 1:
            return "accepted_parent_only"
        if best.candidate.source.startswith("safe_"):
            return "accepted_parent_only"
        return "accepted"


THIN_FIELDS = [
    "fdc_id",
    "gtin_upc",
    "title",
    "branded_food_category",
    "current_esha",
    "current_esha_desc",
    "original_retail_leaf",
    "retail_leaf",
    "clean_retail_leaf",
    "clean_status",
    "clean_reason",
    "clean_sources",
    "identity_overlap",
    "parser_retail_type",
    "parser_supercategory",
    "parser_category_group",
    "parser_category",
    "parser_primary_food",
    "parser_form",
    "parser_flavor",
    "ner_spans",
    "head_phrase",
    "compound_prefix",
    "pp_components",
    "comma_tail",
    "confidence",
    "top_score",
    "second_score",
    "sources_agreed",
    "gap_flag",
    "ing_top5",
    "ing_categories",
    "distinctive_tokens",
    "distinctive_bigrams",
    "product_form_guess",
    "modifier_guesses",
    "ingredient_guesses",
    "form_word_in_title",
    "form_word_in_esha",
    "form_word_in_bfc",
]


def decision_columns(decision: Decision) -> dict[str, str]:
    parser = decision.parser
    return {
        "clean_retail_leaf": decision.clean_retail_leaf,
        "clean_status": decision.clean_status,
        "clean_reason": decision.clean_reason,
        "clean_sources": decision.clean_sources,
        "identity_overlap": decision.identity_overlap,
        "parser_retail_type": str(parser.get("retail_type", "")),
        "parser_supercategory": str(parser.get("supercategory", "")),
        "parser_category_group": str(parser.get("category_group", "")),
        "parser_category": str(parser.get("category", "")),
        "parser_primary_food": str(parser.get("primary_food", "")),
        "parser_form": str(parser.get("form", "")),
        "parser_flavor": str(parser.get("flavor", "")),
    }


def build_group_choices(
    input_path: Path,
    limit: int | None,
    cleaner: RetailLeafCleaner,
) -> dict[tuple[str, str, str], tuple[str, str]]:
    counters: dict[tuple[str, str, str], Counter[str]] = defaultdict(Counter)
    totals: Counter[tuple[str, str, str]] = Counter()
    with input_path.open(newline="", errors="replace") as handle:
        reader = csv.DictReader(handle)
        for idx, row in enumerate(reader, start=1):
            decision = cleaner.clean_row(row, apply_group=False)
            if decision.clean_retail_leaf and decision.clean_status != "review":
                counters[group_key(row)][decision.clean_retail_leaf] += 1
                totals[group_key(row)] += 1
            if limit and idx >= limit:
                break

    choices: dict[tuple[str, str, str], tuple[str, str]] = {}
    for key, counter in counters.items():
        total = totals[key]
        if total < 2:
            continue
        leaf, count = counter.most_common(1)[0]
        if count >= 2 and count / total >= 0.6:
            choices[key] = (leaf, "accepted_group")
            continue
        common_parent = least_common_parent(counter)
        if common_parent and common_parent.count(" > ") >= 1:
            choices[key] = (common_parent, "accepted_parent_only")
    return choices


def run(
    input_path: Path,
    output_path: Path,
    summary_path: Path | None,
    limit: int | None,
    full_output: bool,
    no_group_smoothing: bool,
) -> dict[str, object]:
    first_pass_cleaner = RetailLeafCleaner(enable_group_smoothing=False)
    group_choices: dict[tuple[str, str, str], tuple[str, str]] = {}
    if not no_group_smoothing:
        group_choices = build_group_choices(input_path, limit, first_pass_cleaner)

    cleaner = RetailLeafCleaner(group_choices=group_choices, enable_group_smoothing=not no_group_smoothing)

    summary: dict[str, object] = {
        "input": str(input_path),
        "output": str(output_path),
        "rows": 0,
        "status_counts": Counter(),
        "changed_rows": 0,
        "group_choice_count": len(group_choices),
        "top_reasons": Counter(),
        "top_clean_roots": Counter(),
        "invalid_taxonomy_rows": 0,
    }

    with input_path.open(newline="", errors="replace") as src, output_path.open("w", newline="") as dst:
        reader = csv.DictReader(src)
        if full_output:
            out_fields = list(reader.fieldnames or []) + [field for field in THIN_FIELDS if field not in (reader.fieldnames or [])]
        else:
            out_fields = THIN_FIELDS
        writer = csv.DictWriter(dst, fieldnames=out_fields, extrasaction="ignore")
        writer.writeheader()

        for idx, row in enumerate(reader, start=1):
            decision = cleaner.clean_row(row, apply_group=True)
            extra = decision_columns(decision)
            out = dict(row) if full_output else {field: row.get(field, "") for field in THIN_FIELDS}
            out["original_retail_leaf"] = row.get("original_retail_leaf") or row.get("retail_leaf", "")
            out.update(extra)
            out["retail_leaf"] = decision.clean_retail_leaf
            writer.writerow(out)

            summary["rows"] = idx
            summary["status_counts"][decision.clean_status] += 1
            if decision.clean_retail_leaf != canonicalize_leaf(row.get("retail_leaf") or ""):
                summary["changed_rows"] += 1
            if not decision.taxonomy_valid:
                summary["invalid_taxonomy_rows"] += 1
            if decision.clean_retail_leaf:
                summary["top_clean_roots"][root_of(decision.clean_retail_leaf)] += 1
            for reason in decision.clean_reason.split(";"):
                if reason:
                    summary["top_reasons"][reason] += 1

            if limit and idx >= limit:
                break

    serializable = {
        **summary,
        "status_counts": dict(summary["status_counts"]),
        "top_reasons": dict(summary["top_reasons"].most_common(30)),
        "top_clean_roots": dict(summary["top_clean_roots"].most_common()),
    }
    if summary_path:
        with summary_path.open("w") as handle:
            json.dump(serializable, handle, indent=2, sort_keys=True)
            handle.write("\n")
    return serializable


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Clean retail_leaf_v2_enriched_v2 retail leaves.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--full-output", action="store_true", help="Copy original wide columns before clean_* columns.")
    parser.add_argument("--no-group-smoothing", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    summary = run(
        input_path=args.input,
        output_path=args.output,
        summary_path=args.summary,
        limit=args.limit,
        full_output=args.full_output,
        no_group_smoothing=args.no_group_smoothing,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
