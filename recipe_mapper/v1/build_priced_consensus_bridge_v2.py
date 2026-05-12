#!/usr/bin/env python3
"""Dry-run priced-product -> consensus bridge.

This script is intentionally non-mutating. It scores each priced Walmart/Kroger
row against the consensus retail tree and writes a preview CSV that can be
audited before any database update is considered.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Mapping

csv.field_size_limit(sys.maxsize)

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
PRICED_DB = ROOT / "recipe_pricing" / "data" / "priced_products_v2.db"
CONSENSUS_AUDIT = ROOT / "retail_mapper" / "v2" / "consensus_full_corpus_audit.v2.csv"
CONSENSUS_HTC = HERE / "output" / "consensus_htc_tagged.csv"
OUT_CSV = HERE / "output" / "priced_consensus_bridge_v2_preview.csv"
OUT_SUMMARY = HERE / "output" / "priced_consensus_bridge_v2_summary.json"

PATH_SEP = " > "
WORD_RE = re.compile(r"[a-z0-9]+")

STOP = {
    "the", "of", "and", "with", "a", "an", "to", "in", "for", "from",
    "by", "on", "or", "at", "as", "made", "contains", "contain",
    "size", "pack", "oz", "fl", "ml", "g", "kg", "lb", "lbs", "ct",
    "count", "each", "ea", "bottle", "jar", "bag", "box", "can",
    "case", "family", "value", "new", "free",
}

PACKAGING_NOISE = {
    "great", "value", "kroger", "simple", "truth", "marketside", "organic",
    "fresh", "premium", "select", "brand", "walmart", "private", "selection",
    "big", "deal", "kosher", "natural", "original", "classic", "home",
    "style", "homestyle", "creamy", "real", "pure", "clear",
}

GENERIC_SINGLETON_PID_KEYS = {
    "food", "product", "item", "mix", "drink", "beverage", "snack", "bar",
    "sauce", "spread", "blend", "meal", "dish", "kit", "flavor", "organic",
}

FLAVOR_OR_COMPONENT_TOKENS = {
    "almond", "almonds", "apple", "apples", "banana", "bananas", "basil",
    "butter", "caramel", "cherry", "cilantro", "cinnamon", "coconut",
    "garlic", "honey", "lemon", "lime", "mango", "maple", "mint",
    "orange", "pecan", "pecans", "peach", "peanut", "raspberry",
    "strawberry", "vanilla",
}

RULE_B_PIDS = {
    "Spice Blend", "Seasoning", "Single Entree", "Family Entree",
    "Pasta Sauce", "BBQ Sauce", "Hot Sauce", "Marinade", "Pizza",
    "Sandwich", "Salad", "Composite Dish", "Pasta Dish", "Sauce",
    "Soup", "Salsa", "Dip",
}

COMPOSITE_RULE_B_PIDS = {
    "Single Entree", "Family Entree", "Pizza", "Sandwich", "Salad",
    "Composite Dish", "Pasta Dish", "Sauce", "Soup", "Salsa", "Dip",
    "Marinade", "Hot Sauce", "BBQ Sauce", "Pasta Sauce",
}

SPICE_RULE_B_PIDS = {"Spice Blend", "Seasoning"}

UNSAFE_MODIFIER_KEYS = {
    "plain", "original", "classic", "regular", "organic", "natural",
    "gluten free", "plant based", "non dairy", "vegan", "vegetarian",
    "low fat", "fat free", "reduced fat", "sugar free", "no sugar added",
    "low sodium", "reduced sodium", "salt free", "no salt added",
    "kosher", "halal", "premium", "select",
}

NON_FOOD_RE = re.compile(
    r"\b("
    r"water\s*softener|softener\s*(?:salt|pellets?)|rust\s*remover|ice\s*melt|"
    r"pool\s*salt|dishwasher\s*salt|epsom\s*salt|bath\s*salt|magnesium\s*soak|"
    r"mouthwash|toothpaste|deodorant|shampoo|conditioner|soap|lotion|"
    r"essential\s*oil|aromatherapy|diffuser|petroleum\s*jelly|dry\s*skin|"
    r"listerine|colgate|crest|scope|oral\s*care|dental|"
    r"detergent|laundry|cleaner|cleaning|bleach|"
    r"cat\s*(?:food|treats?|toppers?)|dog\s*(?:food|treats?)|pet\s*food|bird\s*(?:food|feed|seed)|fish\s*food|"
    r"ferry\s*-?\s*morse|annual\s+vegetable\s+seeds?|full\s+sun|seed\s+packet|"
    r"dietary\s*supplements?|herbal\s*supplements?|vitamins?|"
    r"candle|fragrance|perfume|cologne|toy|decoration|decorative|"
    r"confetti|cascaron|easter|christmas|halloween"
    r")\b",
    re.I,
)


@dataclass(frozen=True)
class ConsensusConcept:
    pid: str
    canonical: str
    modifier: str = ""
    category_path: str = ""
    htc_groups: frozenset[str] = field(default_factory=frozenset)
    count: int = 1
    sample_title: str = ""
    modal_bfc: str = ""

    @property
    def department(self) -> str:
        return split_path(self.canonical)[0] if self.canonical else ""


@dataclass
class CandidateScore:
    concept: ConsensusConcept
    score: float
    positive: list[str] = field(default_factory=list)
    negative: list[str] = field(default_factory=list)


@dataclass
class BridgeDecision:
    status: str
    proposed_pid: str = ""
    proposed_canonical: str = ""
    proposed_modifier: str = ""
    score: float = 0.0
    runner_up: str = ""
    evidence: str = ""
    existing_pid: str = ""
    existing_canonical: str = ""
    existing_bridge_status: str = ""


@dataclass
class ConceptIndex:
    concepts: list[ConsensusConcept]
    by_pid_key: dict[str, list[ConsensusConcept]]
    by_direct_pid_key: dict[str, list[ConsensusConcept]]
    pid_keys: set[str]
    pid_keys_by_last: dict[str, list[str]]


def split_path(path: str) -> list[str]:
    return [part.strip() for part in re.split(r"\s*>\s*", path or "") if part.strip()]


def phrase_key(text: str) -> str:
    return " ".join(tokens(text, drop_stop=True, singular=True))


def raw_key(text: str) -> str:
    return " ".join(tokens(text, drop_stop=False, singular=True))


def singular(word: str) -> str:
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 3 and word.endswith("es") and word[-3] in "sxz":
        return word[:-2]
    if len(word) > 3 and word.endswith("s") and not word.endswith(("ss", "us", "is")):
        return word[:-1]
    return word


def tokens(text: str, *, drop_stop: bool = True, singular: bool = False) -> list[str]:
    words = WORD_RE.findall((text or "").lower().replace("&", " and "))
    out: list[str] = []
    for word in words:
        if drop_stop and word in STOP:
            continue
        if singular:
            word = globals()["singular"](word)
        if len(word) >= 2:
            out.append(word)
    return out


def token_set(text: str) -> set[str]:
    return set(tokens(text, drop_stop=True, singular=True))


def path_starts(path: str, prefixes: Iterable[str]) -> bool:
    return any(path == prefix or path.startswith(prefix + PATH_SEP) for prefix in prefixes)


def normalize_display(text: str) -> str:
    return " ".join(tokens(text, drop_stop=False, singular=True))


def category_target_prefixes(title: str, category_text: str) -> list[str]:
    blob = f"{title} {category_text}".lower()
    title_l = (title or "").lower()
    category_l = (category_text or "").lower()
    salt_claim = re.search(r"\b(?:no|without|reduced|low)\s+salt\b|\bsalt[-\s]*free\b|\bsalt\s+added\b", title_l)
    prefixes: list[str] = []
    salad_toppings_cat = re.search(r"salad\s+dressings?|dressings?\s*&?\s*toppings?", blob)
    if salad_toppings_cat and re.search(r"\b(?:topping|topper|bacon\s+bits?|bacon\s+pieces?|croutons?)\b", title_l):
        prefixes.extend(["Pantry > Salad Dressings > Salad Topping", "Pantry > Bacon Toppings", "Pantry > Bacon Bits"])
    elif salad_toppings_cat:
        prefixes.extend(["Pantry > Salad Dressings"])
    if re.search(r"\bice\s*cream\b|ice\s*cream\s*&\s*novelties", blob):
        prefixes.extend(["Frozen > Ice Cream", "Frozen > Gelato", "Frozen > Frozen Yogurt"])
    if re.search(r"\bfrozen\s+yogurt\b", blob):
        prefixes.append("Frozen > Frozen Yogurt")
    if re.search(r"\bhalf\s*(?:and|&)\s*half\b", blob):
        prefixes.extend(["Dairy > Cream > Half and Half", "Beverage > Coffee Creamer"])
    if re.search(r"\bcoffee\s*creamer\b|\bcreamer\b", blob):
        prefixes.extend(["Beverage > Coffee Creamer", "Dairy > Cream > Coffee Creamer"])
    extract_context = re.search(r"\bextracts?\b", blob)
    if extract_context:
        prefixes.extend(["Pantry > Baking Extracts", "Pantry > Baking Additives & Extracts"])
    if re.search(r"\b(?:ground|whole|powdered?|crushed|dried)\s+(?:cloves?|cinnamon|nutmeg|ginger|oregano|thyme|basil|rosemary|sage|cumin|paprika|turmeric|pepper)\b", title_l):
        prefixes.append("Pantry > Spices & Seasonings")
    spice_context = re.search(r"\b(?:spices?|seasonings?|marinades?|tenderizers?)\b", blob)
    salt_context = (
        re.search(r"\bsalts?\b", blob)
        and not salt_claim
        and re.search(r"\b(?:salts?|spices?|seasonings?)\b", category_l)
    )
    if (spice_context or salt_context) and not extract_context:
        prefixes.append("Pantry > Spices & Seasonings")
    if re.search(r"\bjuice\b", blob):
        prefixes.append("Beverage > Juice")
        if re.search(r"\b(?:lemon|lime)\b", blob):
            prefixes.append("Pantry > Sauces & Salsas")
    if re.search(r"\bfried\s+apples?\b|\bapples?\s+with\s+cinnamon\b", blob):
        prefixes.extend(["Pantry > Canned Fruit", "Produce > Fruit"])
    if re.search(r"\bfruit\b", blob) and re.search(r"\b(apples?|bananas?|blueberries|strawberries)\b", blob):
        prefixes.extend(["Produce > Fruit", "Frozen > Frozen Fruit", "Pantry > Canned Fruit"])
    if re.search(r"\bonions?\b", blob) and (
        "produce" in category_l
        or "fresh vegetables" in category_l
        or not re.search(r"\b(?:soup|dip|mix|recipe|seasoning|sauce|dressing)\b", title_l)
    ):
        prefixes.extend(["Produce > Vegetables > Onions", "Produce > Vegetables"])
    if re.search(r"\byogurt\b", blob) and not re.search(r"\b(?:dressing|covered|coated|melts?|drops?)\b", title_l):
        prefixes.extend(["Dairy > Yogurt", "Frozen > Frozen Yogurt"])
    if re.search(r"\bhot\s+cereals?\b", title_l):
        prefixes.append("Pantry > Hot Cereal")
    if re.search(r"\bcereals?\b", title_l) or (
        re.search(r"cereal\s*&\s*granola", category_l)
        and not re.search(r"\b(?:pancake|waffle|baking|cake|muffin)\s+mix\b", title_l)
    ):
        prefixes.append("Pantry > Cereal")
    if re.search(r"\bbagels?\b", title_l):
        prefixes.append("Bakery > Bagels")
    if re.search(r"\bbuns?\b", title_l):
        prefixes.append("Bakery > Buns")
    cookie_flavor_context = re.search(r"\bcookies?\s*['’]?\s*(?:n|and)\s*cre(?:a)?me\b|\b(?:candy|shake|drink|smoothie|protein)\b", title_l)
    if re.search(r"\b(?:cookies?|cookie\s+mix|sandwich\s+cookies?)\b", title_l) and not cookie_flavor_context:
        prefixes.extend(["Bakery > Cookies", "Snack > Cookies"])
    if re.search(r"\b(?:cracker|crackers)\b", title_l):
        prefixes.append("Snack > Crackers")
    if re.search(r"\b(?:baking|cake|pancake|waffle|muffin|quick\s+bread|corn\s+bread|cookie)\s+mix\b", title_l):
        prefixes.append("Pantry > Baking Mixes")
    if re.search(r"\bbreads?\b", title_l) or (
        re.search(r"bakery\s*&\s*bread", category_l)
        and not re.search(r"\bbuns?\b", title_l)
        and not re.search(r"\bbagels?\b", title_l)
        and not re.search(r"\b(?:baking|cake|pancake|waffle|muffin|quick\s+bread|corn\s+bread|cookie)\s+mix\b", title_l)
    ):
        prefixes.append("Bakery > Bread")
    if re.search(r"\bbaking\s+(?:soda|powder)\b", title_l):
        prefixes.extend(["Pantry > Baking Additives & Extracts", "Pantry > Baking Extracts"])
    if re.search(r"dairy.*cheese|cheese.*dairy", category_l):
        prefixes.append("Dairy > Cheese")
    if (
        re.search(r"\bbutter\b", title_l)
        and re.search(r"butter\s*&\s*margarine|butter\s+sticks?|unsalted\s+butter|salted\s+butter|butter,\s*oils", category_l)
        and not re.search(r"\b(?:nut|peanut|almond|cashew|pecan|cookie)\s+butter\b|\bbutter\s+pecan\b|\bbuttercream\b", blob)
    ):
        prefixes.append("Dairy > Butter")
    if re.search(r"cooking\s+oils?|oils?\s*&\s*vinegar", category_l):
        prefixes.extend(["Pantry > Oil", "Pantry > Vinegar"])
    if (
        re.search(r"\bsoda\b|soda\s+pop|carbonated", blob)
        and not re.search(r"\bbaking\s+soda\b", title_l)
        and ("beverage" in category_l or "soda" in category_l or "carbonated" in category_l)
    ):
        prefixes.append("Beverage > Carbonated")
    return list(dict.fromkeys(prefixes))


def category_identity_hints(title: str, category_text: str) -> list[str]:
    blob = f"{title} {category_text}".lower()
    title_l = (title or "").lower()
    category_l = (category_text or "").lower()
    salt_claim = re.search(r"\b(?:no|without|reduced|low)\s+salt\b|\bsalt[-\s]*free\b|\bsalt\s+added\b", title_l)
    hints: list[str] = []
    if re.search(r"salad\s+dressings?|dressings?\s*&?\s*toppings?", blob) and (
        re.search(r"\b(?:dressing|vinaigrette)\b", title_l)
        or not re.search(r"\b(?:topping|topper|bacon\s+bits?|bacon\s+pieces?|croutons?)\b", title_l)
    ):
        hints.append("Salad Dressing")
    if re.search(r"\branch\b", blob) and "dressing" in blob:
        hints.append("Ranch Dressing")
    if re.search(r"\bice\s*cream\b|ice\s*cream\s*&\s*novelties", blob):
        hints.append("Ice Cream")
    if re.search(r"\bfrozen\s+yogurt\b", blob):
        hints.append("Frozen Yogurt")
    if re.search(r"\bhalf\s*(?:and|&)\s*half\b", blob):
        hints.append("Half and Half")
    if re.search(r"\bcoffee\s*creamer\b|\bcreamer\b", blob):
        hints.append("Coffee Creamer")
    if re.search(r"\blemon\b", blob) and re.search(r"\bjuice\b", blob):
        hints.append("Lemon Juice")
    if re.search(r"\bground\s+cloves?\b", title_l) or (
        re.search(r"\bcloves?\b", blob) and re.search(r"\b(?:spices?|seasonings?)\b", blob)
    ):
        hints.append("Cloves")
    if re.search(r"\bbaking\s+powder\b", blob):
        hints.append("Baking Powder")
    if re.search(r"\bbaking\s+soda\b", blob):
        hints.append("Baking Soda")
    if re.search(r"\bplain\b", blob) and re.search(r"\byogurt\b", blob) and not re.search(r"\b(?:dressing|covered|coated|melts?)\b", title_l):
        hints.append("Yogurt")
    if re.search(r"\byellow\s+onions?\b", blob) and (
        "produce" in category_l
        or not re.search(r"\b(?:soup|dip|mix|recipe|seasoning|sauce|dressing)\b", title_l)
    ):
        hints.append("Yellow Onions")
    elif re.search(r"\bonions?\b", blob) and (
        "produce" in category_l
        or not re.search(r"\b(?:soup|dip|mix|recipe|seasoning|sauce|dressing)\b", title_l)
    ):
        hints.append("Onions")
    if re.search(r"\bfried\s+apples?\b|\bapples?\s+with\s+cinnamon\b", blob):
        hints.append("Apples")
    if (
        re.search(r"\bsalt\b", blob)
        and not salt_claim
        and (
            re.search(r"\b(?:spices?|seasonings?)\b", blob)
            or re.search(r"\b(?:salts?|spices?|seasonings?)\b", category_l)
        )
    ):
        hints.append("Salt")
    if (
        re.search(r"\bbutter\b", title_l)
        and re.search(r"butter\s*&\s*margarine|butter\s+sticks?|unsalted\s+butter|salted\s+butter|butter,\s*oils", category_l)
        and not re.search(r"\b(?:nut|peanut|almond|cashew|pecan|cookie)\s+butter\b|\bbutter\s+pecan\b|\bbuttercream\b", blob)
    ):
        hints.append("Butter")
    return list(dict.fromkeys(hints))


def concept_index(concepts: Iterable[ConsensusConcept]) -> ConceptIndex:
    concept_list = list(concepts)
    by_pid_key: dict[str, list[ConsensusConcept]] = defaultdict(list)
    by_direct_pid_key: dict[str, list[ConsensusConcept]] = defaultdict(list)
    for concept in concept_list:
        key = phrase_key(concept.pid)
        if key:
            by_pid_key[key].append(concept)
            by_direct_pid_key[key].append(concept)
        # Rule-B concepts such as Spice Blend, Sauce, Dressing, etc. often put
        # the shopper-facing leaf in modifier. Index the first modifier segment
        # too, so "Ground Cloves" can resolve to Spice Blend + modifier=Cloves.
        modifier_key = phrase_key((concept.modifier or "").split(PATH_SEP)[0])
        if (
            concept.pid in RULE_B_PIDS
            and modifier_key
            and modifier_key != key
            and modifier_key not in UNSAFE_MODIFIER_KEYS
        ):
            by_pid_key[modifier_key].append(concept)
    pid_keys = set(by_pid_key)
    pid_keys_by_last: dict[str, list[str]] = defaultdict(list)
    for key in pid_keys:
        parts = key.split()
        if parts:
            pid_keys_by_last[parts[-1]].append(key)
    for keys in pid_keys_by_last.values():
        keys.sort(key=lambda k: (-len(k.split()), k))
    return ConceptIndex(
        concepts=concept_list,
        by_pid_key=dict(by_pid_key),
        by_direct_pid_key=dict(by_direct_pid_key),
        pid_keys=pid_keys,
        pid_keys_by_last=dict(pid_keys_by_last),
    )


def load_htc_by_fdc(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    with path.open(encoding="utf-8", errors="replace", newline="") as handle:
        for row in csv.DictReader(handle):
            fdc = (row.get("fdc_id") or "").strip()
            code = (row.get("htc_code") or "").strip()
            if fdc and code:
                out[fdc] = code
    return out


def load_consensus_index(audit_path: Path = CONSENSUS_AUDIT, htc_path: Path = CONSENSUS_HTC) -> ConceptIndex:
    htc_by_fdc = load_htc_by_fdc(htc_path)
    grouped: dict[tuple[str, str, str], dict[str, object]] = {}
    with audit_path.open(encoding="utf-8", errors="replace", newline="") as handle:
        for row in csv.DictReader(handle):
            pid = (row.get("product_identity_fixed") or "").strip()
            canonical = (row.get("canonical_path") or "").strip()
            if not pid or not canonical:
                continue
            raw_modifier = (row.get("modifier") or "").split(" > ")[0].strip()
            modifier = raw_modifier if pid in RULE_B_PIDS else ""
            key = (pid, canonical, modifier)
            entry = grouped.setdefault(key, {
                "count": 0,
                "category": Counter(),
                "bfc": Counter(),
                "htc": Counter(),
                "sample_title": "",
            })
            entry["count"] = int(entry["count"]) + 1
            category = (row.get("category_path_fixed") or row.get("category_path_original") or "").strip()
            bfc = (row.get("branded_food_category_corrected") or row.get("branded_food_category") or "").strip()
            fdc = (row.get("fdc_id") or "").strip()
            htc = htc_by_fdc.get(fdc, "")
            if category:
                entry["category"][category] += 1
            if bfc:
                entry["bfc"][bfc] += 1
            if htc:
                entry["htc"][htc[:2]] += 1
            if not entry["sample_title"]:
                entry["sample_title"] = (row.get("title") or "").strip()

    concepts: list[ConsensusConcept] = []
    for (pid, canonical, modifier), entry in grouped.items():
        htc_groups = frozenset(k for k, _ in entry["htc"].most_common(5))
        concepts.append(ConsensusConcept(
            pid=pid,
            canonical=canonical,
            modifier=modifier,
            category_path=entry["category"].most_common(1)[0][0] if entry["category"] else "",
            htc_groups=htc_groups,
            count=int(entry["count"]),
            sample_title=str(entry["sample_title"]),
            modal_bfc=entry["bfc"].most_common(1)[0][0] if entry["bfc"] else "",
        ))
    return concept_index(concepts)


def title_pid_keys(title: str, index: ConceptIndex) -> dict[str, str]:
    """Return pid_key -> evidence source from title text."""
    title_tokens = tokens(title, drop_stop=True, singular=True)
    title_set = set(title_tokens)
    found: dict[str, str] = {}

    # Fast path: exact contiguous title n-grams. This avoids walking giant
    # "last token" buckets for generic leaves like Food, Mix, Bar, etc.
    for start_i in range(len(title_tokens)):
        for span_len in range(1, min(5, len(title_tokens) - start_i) + 1):
            span = " ".join(title_tokens[start_i:start_i + span_len])
            if span in index.pid_keys:
                found[span] = f"title_contiguous:{span_len}"

    # Subset fallback only for bounded buckets. It recovers "Lemon 100% Juice"
    # -> Lemon Juice without turning common tokens into an O(corpus) walk.
    for end_tok in title_set:
        bucket = index.pid_keys_by_last.get(end_tok, [])
        if len(bucket) > 250:
            continue
        for pid_key in bucket:
            parts = pid_key.split()
            if len(parts) > 1 and set(parts).issubset(title_set):
                found.setdefault(pid_key, f"title_token_subset:{len(parts)}")

    # Single-token identities are useful but risky. Keep them as candidates so
    # the scorer can reject them when they are only flavor/component evidence.
    for tok in title_set:
        if tok in index.pid_keys and tok not in GENERIC_SINGLETON_PID_KEYS:
            found.setdefault(tok, "title_single_token")
    return found


def candidate_concepts(product: Mapping[str, object], index: ConceptIndex) -> list[tuple[ConsensusConcept, str]]:
    title = str(product.get("name") or product.get("title") or "")
    category = " ".join(str(product.get(k) or "") for k in ("category_path_walmart", "category_path"))
    prefixes = category_target_prefixes(title, category)
    candidates: dict[tuple[str, str, str], tuple[ConsensusConcept, str]] = {}

    def add_from_pool(pool: list[ConsensusConcept], source: str, *, cap: int = 80) -> None:
        if prefixes:
            matching = [concept for concept in pool if path_starts(concept.canonical, prefixes)]
            if matching:
                pool = matching
        if len(pool) > cap:
            pool = sorted(pool, key=lambda c: -c.count)[:cap]
        for concept in pool:
            candidates[(concept.pid, concept.canonical, concept.modifier)] = (concept, source)

    for pid_key, source in title_pid_keys(title, index).items():
        add_from_pool(index.by_pid_key.get(pid_key, []), source)

    for hint in category_identity_hints(title, category):
        pid_key = phrase_key(hint)
        add_from_pool(index.by_direct_pid_key.get(pid_key, []), "category_identity_hint", cap=120)

    existing_pid = str(product.get("consensus_pid") or "").strip()
    if existing_pid:
        pid_key = phrase_key(existing_pid)
        pool = [
            concept for concept in index.by_direct_pid_key.get(pid_key, [])
            if not product.get("consensus_canonical") or concept.canonical == product.get("consensus_canonical")
        ]
        for concept in pool[:20]:
            candidates.setdefault((concept.pid, concept.canonical, concept.modifier), (concept, "existing_bridge"))
    return list(candidates.values())


def candidate_occurs_as_component(title: str, pid: str) -> bool:
    pid_key = raw_key(pid)
    raw = normalize_display(title)
    if not pid_key or not raw:
        return False
    patterns = [
        rf"\bmade with\b.{{0,80}}\b{re.escape(pid_key)}\b",
        rf"\bwith\b.{{0,80}}\b{re.escape(pid_key)}\b",
        rf"\bcontains\b.{{0,80}}\b{re.escape(pid_key)}\b",
        rf"\bin\b.{{0,80}}\b{re.escape(pid_key)}\b",
    ]
    return any(re.search(pattern, raw) for pattern in patterns)


def candidate_is_absent_claim(title: str, pid: str) -> bool:
    pid_key = raw_key(pid)
    raw = normalize_display(title)
    if not pid_key or not raw:
        return False
    patterns = [
        rf"\bfree from\b.{{0,50}}\b{re.escape(pid_key)}\b",
        rf"\bwithout\b.{{0,50}}\b{re.escape(pid_key)}\b",
        rf"\bno\b.{{0,20}}\b{re.escape(pid_key)}\b",
    ]
    if any(re.search(pattern, raw) for pattern in patterns):
        return True
    if re.search(r"\bfree from\b.{0,50}\begg\b|\bwithout\b.{0,50}\begg\b|\bno\b.{0,20}\begg\b", raw):
        return "egg" in set(raw_key(pid).split())
    return False


def modifier_supported_by_title(title: str, modifier: str) -> bool:
    modifier_head = (modifier or "").split(PATH_SEP)[0].strip()
    key = phrase_key(modifier_head)
    if not key or key == "plain":
        return False
    return set(key.split()).issubset(token_set(title))


def safe_output_modifier(title: str, concept: ConsensusConcept) -> str:
    if concept.pid in RULE_B_PIDS and modifier_supported_by_title(title, concept.modifier):
        return concept.modifier
    return ""


def score_candidate(product: Mapping[str, object], concept: ConsensusConcept, source: str) -> CandidateScore:
    title = str(product.get("name") or product.get("title") or "")
    category = " ".join(str(product.get(k) or "") for k in ("category_path_walmart", "category_path"))
    title_norm = normalize_display(title)
    pid_key = phrase_key(concept.pid)
    pid_parts = pid_key.split()
    pid_tokens = set(pid_parts)
    title_tokens = token_set(title)
    prefixes = category_target_prefixes(title, category)

    score = 0.0
    positive: list[str] = []
    negative: list[str] = []

    if source.startswith("title_contiguous"):
        span_len = int(source.rsplit(":", 1)[1])
        points = 20 + 15 * min(span_len, 4)
        score += points
        positive.append(f"{source}+{points}")
    elif source.startswith("title_token_subset"):
        span_len = int(source.rsplit(":", 1)[1])
        points = 24 + 10 * min(span_len, 4)
        score += points
        positive.append(f"{source}+{points}")
    elif source == "title_single_token":
        score += 20
        positive.append("title_single_token+20")
    elif source == "category_identity_hint":
        score += 80
        positive.append("category_identity_hint+80")
    elif source == "existing_bridge":
        bridge_status = str(product.get("bridge_status") or "")
        points = 35 if bridge_status == "bridged" else 10
        score += points
        positive.append(f"existing_{bridge_status or 'unknown'}+{points}")

    if pid_tokens and pid_tokens.issubset(title_tokens):
        score += 12
        positive.append("all_pid_tokens_in_title+12")

    if prefixes:
        if path_starts(concept.canonical, prefixes):
            score += 60
            positive.append("category_path_agrees+60")
        else:
            score -= 85
            negative.append(f"category_path_conflict:{'|'.join(prefixes)}-85")

    priced_htc = str(product.get("htc_code") or "")
    if priced_htc and concept.htc_groups:
        if priced_htc[:2] in concept.htc_groups:
            score += 8
            positive.append("htc_prefix_agrees+8")
        else:
            score -= 12
            negative.append("htc_prefix_conflict-12")

    if candidate_occurs_as_component(title_norm, concept.pid):
        score -= 75
        negative.append("component_phrase_context-75")

    if candidate_is_absent_claim(title_norm, concept.pid):
        score -= 90
        negative.append("absent_claim_context-90")

    if concept.pid in RULE_B_PIDS and modifier_supported_by_title(title_norm, concept.modifier):
        score += 28
        positive.append("rule_b_modifier_in_title+28")
        if not pid_tokens.issubset(title_tokens):
            spice_exception = (
                concept.pid in SPICE_RULE_B_PIDS
                and path_starts(concept.canonical, ["Pantry > Spices & Seasonings"])
                and prefixes
                and path_starts(concept.canonical, prefixes)
            )
            if concept.pid in COMPOSITE_RULE_B_PIDS or not spice_exception:
                score -= 65
                negative.append("rule_b_modifier_without_identity-65")
            elif spice_exception:
                score -= 45
                negative.append("spice_rule_b_modifier_without_identity-45")

    if (
        concept.pid in SPICE_RULE_B_PIDS
        and re.search(r"\b(?:cast\s+iron|griddle|skillet|cookware)\b", title_norm)
    ):
        score -= 85
        negative.append("non_food_seasoning_context-85")

    if len(pid_parts) == 1 and pid_parts[0] in FLAVOR_OR_COMPONENT_TOKENS:
        if prefixes and not path_starts(concept.canonical, prefixes):
            score -= 55
            negative.append("single_flavor_token_with_category_conflict-55")
        elif re.search(r"\b(flavor(?:ed)?|with|made with)\b", title_norm):
            score -= 35
            negative.append("single_flavor_or_component_token-35")

    if pid_key in {"cookie", "cookies", "cooky"} and re.search(r"\bcook(?:ie|y)\s+(?:n|and)\s+creme\b|\bcandy\b|\b(?:shake|drink|smoothie|protein)\b", title_norm):
        score -= 60
        negative.append("cookie_flavor_or_candy_context-60")

    # A food identity should not be inferred from a brand-only token.
    if pid_tokens and pid_tokens.issubset(PACKAGING_NOISE):
        score -= 50
        negative.append("packaging_noise_identity-50")

    return CandidateScore(concept=concept, score=score, positive=positive, negative=negative)


def same_pid_runner_is_compatible(
    best: CandidateScore,
    runner: CandidateScore,
    prefixes: list[str],
) -> bool:
    if phrase_key(best.concept.pid) != phrase_key(runner.concept.pid):
        return False
    if best.concept.modifier and runner.concept.modifier and best.concept.modifier != runner.concept.modifier:
        return False
    if prefixes:
        return (
            path_starts(best.concept.canonical, prefixes)
            or path_starts(runner.concept.canonical, prefixes)
        )
    best_parts = split_path(best.concept.canonical)
    runner_parts = split_path(runner.concept.canonical)
    return bool(best_parts and runner_parts and best_parts[0] == runner_parts[0])


def decide_product_bridge(product: Mapping[str, object], index: ConceptIndex) -> BridgeDecision:
    title = str(product.get("name") or product.get("title") or "")
    category = " ".join(str(product.get(k) or "") for k in ("category_path_walmart", "category_path"))
    existing_pid = str(product.get("consensus_pid") or "")
    existing_canonical = str(product.get("consensus_canonical") or "")
    existing_status = str(product.get("bridge_status") or "")

    if NON_FOOD_RE.search(f"{title} {category}"):
        return BridgeDecision(
            status="reject_non_food",
            score=0.0,
            evidence="non_food_title_or_category",
            existing_pid=existing_pid,
            existing_canonical=existing_canonical,
            existing_bridge_status=existing_status,
        )

    scored = [
        score_candidate(product, concept, source)
        for concept, source in candidate_concepts(product, index)
    ]
    scored.sort(key=lambda c: (
        -c.score,
        -len(phrase_key(c.concept.pid).split()),
        -len(split_path(c.concept.canonical)),
        -c.concept.count,
        c.concept.pid,
        c.concept.canonical,
    ))
    if not scored:
        return BridgeDecision(
            status="quarantine_low_confidence",
            evidence="no_consensus_candidates",
            existing_pid=existing_pid,
            existing_canonical=existing_canonical,
            existing_bridge_status=existing_status,
        )

    best = scored[0]
    runner = scored[1] if len(scored) > 1 else None
    runner_text = ""
    if runner:
        runner_text = f"{runner.concept.pid} @ {runner.concept.canonical} ({runner.score:.1f})"

    evidence = "; ".join(best.positive + best.negative)
    status = "accepted" if best.score >= 55 else "quarantine_low_confidence"

    if existing_status == "bridged":
        if existing_pid and phrase_key(existing_pid) == phrase_key(best.concept.pid):
            status = "keep_existing_bridged"
        elif best.score < 85:
            status = "quarantine_conflict"

    if (
        runner
        and (runner.concept.pid, runner.concept.canonical) != (best.concept.pid, best.concept.canonical)
        and best.score - runner.score < 8
        and status == "accepted"
        and not same_pid_runner_is_compatible(best, runner, category_target_prefixes(title, category))
    ):
        status = "quarantine_conflict"
        evidence = f"{evidence}; close_runner_up_delta={best.score - runner.score:.1f}"

    return BridgeDecision(
        status=status,
        proposed_pid=best.concept.pid,
        proposed_canonical=best.concept.canonical,
        proposed_modifier=safe_output_modifier(title, best.concept),
        score=best.score,
        runner_up=runner_text,
        evidence=evidence,
        existing_pid=existing_pid,
        existing_canonical=existing_canonical,
        existing_bridge_status=existing_status,
    )


def load_priced_rows(db_path: Path, *, limit: int = 0, rowids: set[int] | None = None) -> list[dict[str, object]]:
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    sql = """
        SELECT rowid, source, upc, name, brand, grams, cents, cpg,
               category_path, category_path_walmart, marketplace, available,
               non_food_path, htc_code, htc_group,
               consensus_pid, consensus_canonical, consensus_modifier,
               consensus_fndds, consensus_sr28, bridge_status
        FROM priced_products
        WHERE marketplace = 0 AND available = 1 AND grams > 0 AND cents > 0
    """
    params: list[object] = []
    if rowids:
        marks = ",".join("?" for _ in rowids)
        sql += f" AND rowid IN ({marks})"
        params.extend(sorted(rowids))
    sql += " ORDER BY rowid"
    if limit > 0:
        sql += " LIMIT ?"
        params.append(limit)
    return [dict(row) for row in con.execute(sql, params)]


def write_preview(rows: list[dict[str, object]], decisions: list[BridgeDecision], out_csv: Path) -> None:
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "rowid", "source", "upc", "name", "category_path", "category_path_walmart",
        "existing_bridge_status", "existing_pid", "existing_canonical",
        "decision_status", "proposed_pid", "proposed_canonical", "proposed_modifier",
        "score", "runner_up", "evidence",
    ]
    with out_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row, decision in zip(rows, decisions):
            writer.writerow({
                "rowid": row.get("rowid", ""),
                "source": row.get("source", ""),
                "upc": row.get("upc", ""),
                "name": row.get("name", ""),
                "category_path": row.get("category_path", ""),
                "category_path_walmart": row.get("category_path_walmart", ""),
                "existing_bridge_status": decision.existing_bridge_status,
                "existing_pid": decision.existing_pid,
                "existing_canonical": decision.existing_canonical,
                "decision_status": decision.status,
                "proposed_pid": decision.proposed_pid,
                "proposed_canonical": decision.proposed_canonical,
                "proposed_modifier": decision.proposed_modifier,
                "score": f"{decision.score:.1f}",
                "runner_up": decision.runner_up,
                "evidence": decision.evidence,
            })


def write_summary(rows: list[dict[str, object]], decisions: list[BridgeDecision], out_summary: Path, elapsed_s: float) -> None:
    status_counts = Counter(d.status for d in decisions)
    existing_counts = Counter(str(row.get("bridge_status") or "") for row in rows)
    changed_existing = sum(
        1 for row, d in zip(rows, decisions)
        if d.status == "accepted"
        and str(row.get("consensus_pid") or "") != d.proposed_pid
    )
    summary = {
        "rows_scored": len(rows),
        "elapsed_s": round(elapsed_s, 1),
        "status_counts": dict(status_counts.most_common()),
        "existing_bridge_status_counts": dict(existing_counts.most_common()),
        "accepted_existing_pid_changes": changed_existing,
    }
    out_summary.parent.mkdir(parents=True, exist_ok=True)
    out_summary.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")


def parse_rowids(value: str) -> set[int] | None:
    if not value:
        return None
    out = {int(part.strip()) for part in value.split(",") if part.strip()}
    return out or None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--priced-db", type=Path, default=PRICED_DB)
    parser.add_argument("--audit", type=Path, default=CONSENSUS_AUDIT)
    parser.add_argument("--consensus-htc", type=Path, default=CONSENSUS_HTC)
    parser.add_argument("--out", type=Path, default=OUT_CSV)
    parser.add_argument("--summary-out", type=Path, default=OUT_SUMMARY)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--rowids", default="", help="comma-separated priced_products rowids")
    args = parser.parse_args()

    t0 = time.time()
    print("loading consensus concept index...")
    index = load_consensus_index(args.audit, args.consensus_htc)
    print(f"  {len(index.concepts):,} concepts across {len(index.pid_keys):,} identities")

    rowids = parse_rowids(args.rowids)
    print("loading priced products...")
    priced_rows = load_priced_rows(args.priced_db, limit=args.limit, rowids=rowids)
    print(f"  {len(priced_rows):,} priced rows")

    decisions: list[BridgeDecision] = []
    decision_cache: dict[tuple[object, ...], BridgeDecision] = {}
    for i, row in enumerate(priced_rows, 1):
        cache_key = (
            row.get("name"),
            row.get("category_path"),
            row.get("category_path_walmart"),
            row.get("htc_code"),
            row.get("consensus_pid"),
            row.get("consensus_canonical"),
            row.get("bridge_status"),
        )
        decision = decision_cache.get(cache_key)
        if decision is None:
            decision = decide_product_bridge(row, index)
            decision_cache[cache_key] = decision
        decisions.append(decision)
        if i % 25000 == 0:
            print(f"  scored {i:,} rows", flush=True)

    elapsed = time.time() - t0
    write_preview(priced_rows, decisions, args.out)
    write_summary(priced_rows, decisions, args.summary_out, elapsed)

    print(f"wrote {args.out}")
    print(f"wrote {args.summary_out}")
    print(json.dumps({
        "rows_scored": len(priced_rows),
        "status_counts": dict(Counter(d.status for d in decisions).most_common()),
        "elapsed_s": round(elapsed, 1),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
