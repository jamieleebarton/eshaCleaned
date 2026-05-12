#!/usr/bin/env python3
"""Corpus-learned HTC ingredient-to-product bridge.

This module is the deterministic core for the v1 learned bridge. It does not
contain per-ingredient contracts. It learns an ingredient's shopping contract
from the consensus corpus, HTC tags, reference descriptions, sibling/nearby
negative concepts, and priced-product evidence.
"""
from __future__ import annotations

import csv
import json
import math
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Mapping

csv.field_size_limit(sys.maxsize)

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

DEFAULT_AUDIT = ROOT / "retail_mapper" / "v2" / "consensus_full_corpus_audit.v2.csv"
DEFAULT_AUDIT_FALLBACK = ROOT / "retail_mapper" / "v2" / "consensus_full_corpus_audit.csv"
DEFAULT_CONSENSUS_HTC = HERE / "output" / "consensus_htc_tagged.csv"
DEFAULT_INGREDIENT_HTC = HERE / "output" / "recipe_ingredient_htc_tagged.csv"
DEFAULT_INGREDIENT_SR28 = HERE / "output" / "ingredient_to_sr28.csv"
DEFAULT_PRICED_DB = ROOT / "recipe_pricing" / "data" / "priced_products_v2.db"
DEFAULT_PRODUCT_EVIDENCE = HERE / "output" / "priced_product_evidence_v1.csv"

PATH_SEP = " > "

TOKEN_RE = re.compile(r"[a-z0-9]+")
NON_FOOD_RE = re.compile(
    r"\b("
    r"water\s+softener|softener\s+salt|plumbing|filtration|mouthwash|"
    r"toothpaste|deodorant|shampoo|conditioner|soap|lotion|detergent|"
    r"cleaner|cleaning|bleach|carpet|flea|pet\s+food|dog\s+food|cat\s+food|"
    r"vitamin|supplement|toy|candle|fragrance|decorat|torch|lamp|"
    r"patio|garden|backyard|citronella|outdoor\s+fuel|torch\s+fuel|"
    r"apparel|clothing|pantyhose"
    r")\b",
    re.I,
)
COMPONENT_CONTEXT_RE = re.compile(
    r"\b(made\s+with|with|contains|containing|flavored|flavour(?:ed)?|"
    r"infused|filled\s+with|covered|coated|variety\s+pack|assorted)\b",
    re.I,
)
MULTIPACK_RE = re.compile(r"\b(?:\d+\s*(?:pack|pk)|pack\s+of\s+\d+)\b", re.I)

STOP_TOKENS = {
    "a", "an", "and", "are", "as", "at", "by", "for", "from", "in",
    "into", "of", "on", "or", "the", "to", "with", "without",
    "brand", "value", "great", "kroger", "walmart", "freshness",
}

GENERIC_IDENTITY_TOKENS = {
    "food", "foods", "item", "items", "product", "products", "plain",
    "generic", "other", "misc", "mix", "blend", "seasoning", "spice",
    "spices", "pantry", "produce", "frozen", "dairy", "snack", "meal",
    "beverage", "beverages", "vegetable", "vegetables", "fruit", "fruits",
    "raw", "fresh", "whole", "ground", "powder", "powdered", "dried",
    "dry", "chopped", "diced", "minced", "sliced", "cut", "canned",
    "organic", "natural", "small", "large", "medium", "extra", "lean",
    "low", "fat", "free", "no", "added", "reduced", "unsalted", "salted",
}

FORBIDDEN_LEARN_SKIP = GENERIC_IDENTITY_TOKENS | {
    "black", "white", "red", "green", "yellow", "blue", "brown",
    "original", "classic", "style", "sweet", "hot", "medium", "mild",
}

WEAK_SURFACE_TERMS = {
    "all", "purpose", "bleached", "enriched", "white", "wheat",
    "seed", "leaf", "leave", "oil", "juice", "flour", "powder",
    "piece", "breast", "thigh", "tomatoe",
}

FORM_TOKENS = {
    "fresh", "frozen", "ground", "powder", "powdered", "whole", "dried",
    "dry", "chopped", "diced", "minced", "sliced", "crushed", "grated",
    "shredded", "canned", "jarred", "raw", "roasted", "toasted",
}

FORM_SYNONYMS = {
    "ground": {"ground", "powder", "powdered"},
    "powder": {"ground", "powder", "powdered"},
    "powdered": {"ground", "powder", "powdered"},
    "fresh": {"fresh", "raw"},
    "dried": {"dried", "dry"},
    "dry": {"dried", "dry"},
}

STRICT_PRODUCT_FORM_TERMS = {
    "powder", "powdered", "dried", "dry", "dehydrated", "substitute", "mix",
    "crispy", "coated", "covered", "flavored", "drink", "ready", "pouch",
    "microwavable", "microwaveable", "second", "heat", "serve", "kit",
    "spray", "croissant", "knot", "knots", "bread", "toast", "creme",
    "rub", "seasoning", "candy", "gum", "dressing", "dressings", "dip",
    "dips", "sauce", "bran", "cereal", "granola", "bar", "bars",
}

FLAVOR_CONFLICT_TERMS = {
    "almond", "avocado", "bacon", "bbq", "caramel", "carmel", "cheddar",
    "cheese", "chili", "chipotle", "chocolate", "cinnamon", "blueberry", "cocoa",
    "coca", "coconut", "garlic", "goat", "gruyere", "honey", "jalapeno",
    "habanero", "lemon", "lime", "mango", "mint", "orange", "peach",
    "pepper", "pineapple", "raspberry", "salt", "salted", "sea",
    "sriracha", "strawberry", "vanilla",
}

RULE_B_PIDS = {
    "Spice Blend", "Seasoning", "Single Entree", "Family Entree",
    "Pasta Sauce", "BBQ Sauce", "Hot Sauce", "Marinade", "Pizza",
    "Sandwich", "Salad", "Composite Dish", "Pasta Dish", "Sauce",
    "Soup", "Salsa", "Dip", "Extract",
}

FRESH_LEAF_TERMS = {
    "basil", "bay", "chervil", "chive", "cilantro", "coriander", "dill",
    "herb", "leaf", "leave", "marjoram", "mint", "oregano", "parsley",
    "rosemary", "sage", "sprig", "tarragon", "thyme",
}

COMPOSITE_PRIMARY_IDENTITY_TERMS = {
    "beverage", "burrito", "cereal", "drink", "entree", "kit", "meal",
    "pizza", "salad", "sandwich", "sauce", "soup", "wrap",
}

PRODUCE_PLU_RE = re.compile(r"^0{6,}\d{4,5}$")


def singular_word(value: str) -> str:
    exceptions = {
        "chile": "chili",
        "chiles": "chili",
        "chilies": "chili",
        "cookies": "cookie",
        "brownies": "brownie",
        "smoothies": "smoothie",
    }
    if value in exceptions:
        return exceptions[value]
    if value.endswith("ies") and len(value) > 4:
        return value[:-3] + "y"
    if value.endswith("es") and len(value) > 3 and value[-3] in "sxz":
        return value[:-2]
    if value.endswith("s") and len(value) > 2 and not value.endswith("ss"):
        return value[:-1]
    return value


def tokens(value: str, *, drop_stop: bool = True, singular: bool = True) -> list[str]:
    out: list[str] = []
    for token in TOKEN_RE.findall((value or "").lower()):
        if len(token) <= 1:
            continue
        if drop_stop and token in STOP_TOKENS:
            continue
        out.append(singular_word(token) if singular else token)
    return out


def token_set(value: str, *, drop_stop: bool = True) -> set[str]:
    return set(tokens(value, drop_stop=drop_stop, singular=True))


def normalize_phrase(value: str) -> str:
    return " ".join(tokens(value, drop_stop=True, singular=True))


def pipe_values(value: str) -> list[str]:
    if not value:
        return []
    return [p.strip() for p in re.split(r"\s*(?:\||>|;|,)\s*", value) if p.strip()]


def path_parts(path: str) -> list[str]:
    if not path:
        return []
    normalized = path.replace("/", PATH_SEP)
    return [p.strip() for p in normalized.split(PATH_SEP) if p.strip() and p.strip().lower() != "home page"]


def path_starts(path: str, prefixes: Iterable[str]) -> bool:
    parts_path = PATH_SEP.join(path_parts(path))
    for prefix in prefixes:
        parts_prefix = PATH_SEP.join(path_parts(prefix))
        if not parts_prefix:
            continue
        if parts_path == parts_prefix or parts_path.startswith(parts_prefix + PATH_SEP):
            return True
    return False


def parent_path(path: str) -> str:
    parts = path_parts(path)
    if len(parts) <= 1:
        return PATH_SEP.join(parts)
    return PATH_SEP.join(parts[:-1])


def phrase_present(blob: str, phrase: str) -> bool:
    norm_blob = " " + normalize_phrase(blob) + " "
    norm_phrase = normalize_phrase(phrase)
    return bool(norm_phrase and f" {norm_phrase} " in norm_blob)


def absent_claim_present(title: str, term: str) -> bool:
    norm_title = normalize_phrase(title)
    norm_term = normalize_phrase(term)
    if not norm_term:
        return False
    patterns = (
        rf"\b{re.escape(norm_term)}\s+free\b",
        rf"\bfree\s+from\s+{re.escape(norm_term)}\b",
        rf"\bwithout\s+{re.escape(norm_term)}\b",
        rf"\bno\s+{re.escape(norm_term)}\b",
        rf"\beverything\s+but\s+(?:the\s+)?{re.escape(norm_term)}\b",
        rf"\bbut\s+(?:the\s+)?{re.escape(norm_term)}\b",
    )
    if any(re.search(pattern, norm_title) for pattern in patterns):
        return True
    allergen_terms = {
        "dairy", "egg", "eggs", "gluten", "milk", "nut", "nuts",
        "peanut", "peanuts", "soy", "tree", "wheat",
    }
    if norm_term in allergen_terms:
        list_terms = r"(?:dairy|egg|eggs|gluten|milk|nut|nuts|peanut|peanuts|soy|tree|wheat|and|or)"
        if re.search(rf"\bno(?:\s+{list_terms}){{0,10}}\s+{re.escape(norm_term)}\b", norm_title):
            return True
    return False


def split_modifier(value: str) -> str:
    return pipe_values(value)[0] if value else ""


def htc_prefix(code: str) -> str:
    code = (code or "").strip()
    return code[:2] if len(code) >= 2 else ""


def htc_group(code: str) -> str:
    code = (code or "").strip()
    return code[:1] if code else ""


def fresh_leaf_profile(profile: IngredientProfile) -> bool:
    blob_terms = token_set(f"{profile.item} {profile.sr28_desc}")
    has_leaf_signal = bool(blob_terms & FRESH_LEAF_TERMS)
    has_dry_signal = bool(re.search(r"\b(dried|dry|ground|powder|powdered|seed)\b", normalize_phrase(profile.item)))
    return has_leaf_signal and not has_dry_signal


def terminal_status_for_offer(contract_status: str, offer_status: str) -> str:
    if offer_status == "accepted_offer":
        return "safe_priced"
    if offer_status == "tap_water":
        return "safe_tap_water"
    if contract_status == "needs_llm_contract_review":
        return "needs_llm_contract_review"
    if contract_status == "no_concept":
        return "gap_no_concept"
    if offer_status == "needs_product_api_query":
        return "needs_product_api_query"
    return "blocked_by_verified_gate"


@dataclass
class ConceptEvidence:
    pid: str
    canonical: str
    modifier: str = ""
    count: int = 0
    sample_title: str = ""
    htc_prefix_counts: Counter[str] = field(default_factory=Counter)
    identity_tokens: Counter[str] = field(default_factory=Counter)
    title_tokens: Counter[str] = field(default_factory=Counter)
    path_tokens: Counter[str] = field(default_factory=Counter)
    reference_tokens: Counter[str] = field(default_factory=Counter)
    facet_tokens: Counter[str] = field(default_factory=Counter)
    category_tokens: Counter[str] = field(default_factory=Counter)
    confidence_sum: float = 0.0
    confidence_n: int = 0
    review_flag_count: int = 0
    source_conflict_count: int = 0

    @property
    def key(self) -> tuple[str, str, str]:
        return self.pid, self.canonical, self.modifier

    @property
    def htc_prefixes(self) -> set[str]:
        return {prefix for prefix, _ in self.htc_prefix_counts.most_common(8)}

    @property
    def avg_confidence(self) -> float:
        return self.confidence_sum / self.confidence_n if self.confidence_n else 0.0

    def concept_terms(self) -> set[str]:
        terms = set(self.identity_tokens)
        terms.update(t for t, _ in self.reference_tokens.most_common(30))
        return {t for t in terms if t not in GENERIC_IDENTITY_TOKENS}

    def all_search_terms(self) -> set[str]:
        return set(self.identity_tokens) | set(self.title_tokens) | set(self.path_tokens) | set(self.reference_tokens)


@dataclass(frozen=True)
class IngredientProfile:
    item: str
    recipe_count: int = 0
    grams_total: float = 0.0
    htc_code: str = ""
    sr28_fdc_id: str = ""
    sr28_desc: str = ""

    @property
    def htc_prefix(self) -> str:
        return htc_prefix(self.htc_code)

    @property
    def htc_group(self) -> str:
        return htc_group(self.htc_code)

    @property
    def form_terms(self) -> set[str]:
        found = token_set(self.item) & FORM_TOKENS
        expanded = set(found)
        for term in found:
            expanded.update(FORM_SYNONYMS.get(term, set()))
        return expanded

    @property
    def identity_terms(self) -> set[str]:
        item_terms = token_set(self.item)
        sr_terms = token_set(self.sr28_desc)
        combined = item_terms | sr_terms
        blocked = GENERIC_IDENTITY_TOKENS | self.form_terms | {"spice", "spices", "raw"}
        terms = {t for t in combined if t not in blocked}
        if not terms:
            terms = {t for t in item_terms if t not in GENERIC_IDENTITY_TOKENS}
        return terms


@dataclass
class CandidateScore:
    concept: ConceptEvidence
    score: float = 0.0
    identity_score: float = 0.0
    reference_score: float = 0.0
    htc_score: float = 0.0
    path_score: float = 0.0
    provenance_score: float = 0.0
    source: str = ""
    hard_vetoes: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)

    def total(self) -> float:
        return (
            self.score
            + self.identity_score
            + self.reference_score
            + self.htc_score
            + self.path_score
            + self.provenance_score
        )


@dataclass(frozen=True)
class LearnedContract:
    ingredient_item: str
    recipe_count: int
    status: str
    concept_pid: str = ""
    canonical: str = ""
    modifier: str = ""
    htc_code: str = ""
    allowed_htc_prefixes: tuple[str, ...] = ()
    required_terms: tuple[str, ...] = ()
    forbidden_terms: tuple[str, ...] = ()
    allowed_paths: tuple[str, ...] = ()
    allowed_forms: tuple[str, ...] = ()
    proxy_policy: str = "none"
    confidence: float = 0.0
    evidence: tuple[str, ...] = ()
    review_reason: str = ""

    @property
    def concept_key(self) -> tuple[str, str, str]:
        return self.concept_pid, self.canonical, self.modifier

    def to_dict(self) -> dict[str, object]:
        return {
            "ingredient_item": self.ingredient_item,
            "recipe_count": self.recipe_count,
            "status": self.status,
            "shopping_concept": self.concept_pid or self.ingredient_item,
            "canonical_path": self.canonical,
            "modifier": self.modifier,
            "htc_code": self.htc_code,
            "allowed_htc_prefixes": list(self.allowed_htc_prefixes),
            "required_terms": list(self.required_terms),
            "forbidden_terms": list(self.forbidden_terms),
            "allowed_paths": list(self.allowed_paths),
            "allowed_forms": list(self.allowed_forms),
            "proxy_policy": self.proxy_policy,
            "confidence": round(self.confidence, 3),
            "review_reason": self.review_reason,
            "evidence": list(self.evidence),
        }


@dataclass(frozen=True)
class ProductRecord:
    rowid: str
    source: str = ""
    upc: str = ""
    name: str = ""
    brand: str = ""
    grams: float = 0.0
    cents: int = 0
    category_path: str = ""
    category_path_walmart: str = ""
    htc_code: str = ""
    proposed_pid: str = ""
    proposed_canonical: str = ""
    proposed_modifier: str = ""
    taxonomy_status: str = ""
    hard_vetoes: str = ""
    evidence_score: float = 0.0

    @property
    def cpg(self) -> float:
        return self.cents / self.grams if self.grams > 0 else math.inf

    @property
    def concept_key(self) -> tuple[str, str, str]:
        return self.proposed_pid, self.proposed_canonical, _concept_modifier(self.proposed_pid, self.proposed_modifier)

    @property
    def primary_identity_label(self) -> str:
        if self.proposed_pid:
            return self.proposed_pid
        parts = path_parts(self.proposed_canonical)
        return parts[-1] if parts else ""

    @property
    def primary_identity_terms(self) -> set[str]:
        parts = path_parts(self.proposed_canonical)
        leaf = parts[-1] if parts else ""
        return _identity_terms_from_blob(" ".join([self.proposed_pid, leaf]))

    @property
    def htc_prefix(self) -> str:
        return htc_prefix(self.htc_code)

    @property
    def htc_group(self) -> str:
        return htc_group(self.htc_code)

    def searchable_blob(self) -> str:
        return " ".join([
            self.name,
            self.brand,
            self.category_path,
            self.category_path_walmart,
            self.proposed_pid,
            self.proposed_canonical,
            self.proposed_modifier,
        ])


@dataclass(frozen=True)
class ProductMatch:
    status: str
    product: ProductRecord | None = None
    score: float = 0.0
    reason: str = ""
    rejected: tuple[str, ...] = ()


@dataclass
class EvidenceIndex:
    concepts: list[ConceptEvidence]
    by_term: dict[str, list[ConceptEvidence]]
    by_exact_key: dict[str, list[ConceptEvidence]]
    by_htc_prefix: dict[str, list[ConceptEvidence]]


@dataclass
class ProductIndex:
    products: list[ProductRecord]
    by_term: dict[str, list[ProductRecord]]
    by_concept_key: dict[tuple[str, str, str], list[ProductRecord]]


def concept_index(concepts: Iterable[ConceptEvidence]) -> EvidenceIndex:
    concept_list = list(concepts)
    by_term: dict[str, list[ConceptEvidence]] = defaultdict(list)
    by_exact_key: dict[str, list[ConceptEvidence]] = defaultdict(list)
    by_htc_prefix_map: dict[str, list[ConceptEvidence]] = defaultdict(list)
    for concept in concept_list:
        exact_blobs = [
            concept.pid,
            concept.modifier,
            path_parts(concept.canonical)[-1] if path_parts(concept.canonical) else "",
        ]
        for blob in exact_blobs:
            key = normalize_phrase(blob)
            if key:
                by_exact_key[key].append(concept)
        for term in concept.all_search_terms():
            if term and term not in STOP_TOKENS:
                by_term[term].append(concept)
        for prefix in concept.htc_prefixes:
            by_htc_prefix_map[prefix].append(concept)
    for bucket in by_term.values():
        bucket.sort(key=lambda c: -c.count)
    for bucket in by_exact_key.values():
        bucket.sort(key=lambda c: -c.count)
    for bucket in by_htc_prefix_map.values():
        bucket.sort(key=lambda c: -c.count)
    return EvidenceIndex(
        concepts=concept_list,
        by_term=dict(by_term),
        by_exact_key=dict(by_exact_key),
        by_htc_prefix=dict(by_htc_prefix_map),
    )


def product_index(products: Iterable[ProductRecord]) -> ProductIndex:
    product_list = list(products)
    by_term: dict[str, list[ProductRecord]] = defaultdict(list)
    by_key: dict[tuple[str, str, str], list[ProductRecord]] = defaultdict(list)
    for product in product_list:
        by_key[product.concept_key].append(product)
        for term in token_set(product.searchable_blob()):
            by_term[term].append(product)
    for bucket in by_key.values():
        bucket.sort(key=lambda p: (-p.evidence_score, p.cpg, p.cents))
    for bucket in by_term.values():
        bucket.sort(key=lambda p: (-p.evidence_score, p.cpg, p.cents))
    return ProductIndex(product_list, dict(by_term), dict(by_key))


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


def load_sr28_by_item(path: Path) -> dict[str, tuple[str, str]]:
    out: dict[str, tuple[str, str]] = {}
    if not path.exists():
        return out
    with path.open(encoding="utf-8", errors="replace", newline="") as handle:
        for row in csv.DictReader(handle):
            item = normalize_phrase(row.get("item") or "")
            if item:
                out[item] = ((row.get("fdc_id") or "").strip(), (row.get("sr_description") or "").strip())
    return out


def load_ingredient_profiles(
    ingredient_htc_path: Path = DEFAULT_INGREDIENT_HTC,
    sr28_path: Path = DEFAULT_INGREDIENT_SR28,
    *,
    top_n: int = 2500,
) -> list[IngredientProfile]:
    sr28 = load_sr28_by_item(sr28_path)
    profiles: list[IngredientProfile] = []
    with ingredient_htc_path.open(encoding="utf-8", errors="replace", newline="") as handle:
        for row in csv.DictReader(handle):
            item = (row.get("item") or "").strip()
            if not item:
                continue
            key = normalize_phrase(item)
            fdc_id, sr_desc = sr28.get(key, ("", ""))
            try:
                recipe_count = int(float(row.get("recipe_count") or 0))
            except ValueError:
                recipe_count = 0
            try:
                grams_total = float(row.get("grams_total") or 0)
            except ValueError:
                grams_total = 0.0
            profiles.append(IngredientProfile(
                item=item,
                recipe_count=recipe_count,
                grams_total=grams_total,
                htc_code=(row.get("htc_code") or "").strip(),
                sr28_fdc_id=fdc_id,
                sr28_desc=sr_desc,
            ))
    profiles.sort(key=lambda p: (-p.recipe_count, p.item))
    return profiles[:top_n] if top_n > 0 else profiles


def _add_counter_terms(counter: Counter[str], value: str, *, weight: int = 1) -> None:
    for token in token_set(value):
        if token not in STOP_TOKENS:
            counter[token] += weight


def _concept_modifier(pid: str, raw_modifier: str) -> str:
    modifier = split_modifier(raw_modifier).strip()
    if not modifier:
        return ""
    if pid in RULE_B_PIDS:
        return modifier
    return ""


def _identity_terms_from_blob(value: str) -> set[str]:
    raw = token_set(value)
    filtered = raw - GENERIC_IDENTITY_TOKENS - FORM_TOKENS
    return filtered or raw


def _identity_label(value: str) -> str:
    value = (value or "").strip()
    return value if value else "unknown"


def _choose_product_tree_fields(
    *,
    title: str,
    existing_pid: str,
    existing_canonical: str,
    existing_modifier: str,
    existing_bridge_status: str,
    proposed_pid: str,
    proposed_canonical: str,
    proposed_modifier: str,
) -> tuple[str, str, str]:
    if not existing_pid:
        return proposed_pid, proposed_canonical, proposed_modifier
    if not proposed_pid:
        return existing_pid, existing_canonical, existing_modifier
    if normalize_phrase(existing_pid) == normalize_phrase(proposed_pid):
        return existing_pid, existing_canonical, existing_modifier or proposed_modifier

    proposed_in_title = phrase_present(title, proposed_pid)
    existing_in_title = phrase_present(title, existing_pid)
    existing_terms = _identity_terms_from_blob(existing_pid)
    proposed_terms = _identity_terms_from_blob(proposed_pid)
    if (
        existing_in_title
        and proposed_in_title
        and proposed_terms
        and proposed_terms < existing_terms
    ):
        return existing_pid, existing_canonical, existing_modifier
    if (
        existing_in_title
        and proposed_in_title
        and existing_terms & COMPOSITE_PRIMARY_IDENTITY_TERMS
        and not proposed_terms & COMPOSITE_PRIMARY_IDENTITY_TERMS
    ):
        return existing_pid, existing_canonical, existing_modifier
    proposed_is_generic_facet_parent = (
        proposed_pid in RULE_B_PIDS
        and bool(proposed_modifier)
        and not proposed_in_title
        and existing_in_title
    )
    if proposed_is_generic_facet_parent:
        return existing_pid, existing_canonical, existing_modifier
    if existing_bridge_status == "bridged":
        return existing_pid, existing_canonical, existing_modifier
    if (
        existing_bridge_status == "title_match"
        and existing_in_title
        and proposed_in_title
        and normalize_phrase(proposed_pid)
        and normalize_phrase(proposed_pid) in normalize_phrase(existing_pid)
        and normalize_phrase(proposed_pid) != normalize_phrase(existing_pid)
    ):
        return existing_pid, existing_canonical, existing_modifier
    if existing_bridge_status == "title_match" and proposed_in_title:
        return proposed_pid, proposed_canonical, proposed_modifier
    return existing_pid, existing_canonical, existing_modifier


def _fresh_herb_product_tree_fields(
    *,
    title: str,
    category_path: str,
    category_path_walmart: str,
) -> tuple[str, str, str] | None:
    title_terms = token_set(title)
    category_terms = token_set(f"{category_path} {category_path_walmart}")
    if not category_terms & {"produce", "herb", "herbs"}:
        return None
    non_herb_context = {
        "baking", "candy", "personal", "care", "dressing", "dressings",
        "dip", "dips", "sauce", "salad", "yogurt",
    }
    if (category_terms | title_terms) & non_herb_context:
        return None
    herb_terms = sorted(
        title_terms & (FRESH_LEAF_TERMS - {"herb", "leaf", "leave", "sprig"})
    )
    if not herb_terms:
        return None
    label = " ".join(term.capitalize() for term in herb_terms[:1])
    return label, f"Produce > Fresh Herbs > {label}", ""


def load_evidence_index(
    audit_path: Path = DEFAULT_AUDIT,
    consensus_htc_path: Path = DEFAULT_CONSENSUS_HTC,
) -> EvidenceIndex:
    if not audit_path.exists() and DEFAULT_AUDIT_FALLBACK.exists():
        audit_path = DEFAULT_AUDIT_FALLBACK
    htc_by_fdc = load_htc_by_fdc(consensus_htc_path)
    grouped: dict[tuple[str, str, str], ConceptEvidence] = {}
    with audit_path.open(encoding="utf-8", errors="replace", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            pid = (row.get("product_identity_fixed") or row.get("product_identity_original") or "").strip()
            canonical = (row.get("canonical_path") or "").strip()
            if not pid or not canonical:
                continue
            modifier = _concept_modifier(pid, row.get("modifier") or "")
            key = (pid, canonical, modifier)
            concept = grouped.get(key)
            if concept is None:
                concept = ConceptEvidence(pid=pid, canonical=canonical, modifier=modifier)
                grouped[key] = concept
            concept.count += 1
            if not concept.sample_title:
                concept.sample_title = (row.get("title") or "").strip()
            fdc = (row.get("fdc_id") or "").strip()
            prefix = htc_prefix(htc_by_fdc.get(fdc, ""))
            if prefix:
                concept.htc_prefix_counts[prefix] += 1
            for field_name in (
                "product_identity_original",
                "product_identity_fixed",
                "canonical_label",
                "modifier",
                "retail_leaf_path",
            ):
                _add_counter_terms(concept.identity_tokens, row.get(field_name) or "")
            _add_counter_terms(concept.identity_tokens, canonical)
            _add_counter_terms(concept.path_tokens, canonical)
            _add_counter_terms(concept.title_tokens, row.get("title") or "")
            _add_counter_terms(concept.category_tokens, row.get("category_path_fixed") or row.get("category_path_original") or "")
            _add_counter_terms(concept.category_tokens, row.get("branded_food_category_corrected") or row.get("branded_food_category") or "")
            for field_name in ("fndds_desc", "sr28_desc", "esha_desc", "matched_key"):
                _add_counter_terms(concept.reference_tokens, row.get(field_name) or "")
            for field_name in ("variant", "flavor", "form_texture_cut", "processing_storage", "claims", "components"):
                for value in pipe_values(row.get(field_name) or ""):
                    _add_counter_terms(concept.facet_tokens, value)
            try:
                confidence = float(row.get("confidence") or 0)
            except ValueError:
                confidence = 0.0
            if confidence:
                concept.confidence_sum += confidence
                concept.confidence_n += 1
            if (row.get("review_flags") or "").strip():
                concept.review_flag_count += 1
            if (row.get("source_conflict_action") or row.get("source_conflict_note") or "").strip():
                concept.source_conflict_count += 1
    return concept_index(grouped.values())


def score_candidate(profile: IngredientProfile, concept: ConceptEvidence, source: str = "") -> CandidateScore:
    score = CandidateScore(concept=concept, source=source or "lexical")
    item_key = normalize_phrase(profile.item)
    item_no_forms = " ".join(t for t in item_key.split() if t not in profile.form_terms)
    pid_key = normalize_phrase(concept.pid)
    modifier_key = normalize_phrase(concept.modifier)
    leaf_key = normalize_phrase(path_parts(concept.canonical)[-1] if path_parts(concept.canonical) else "")
    identity_terms = profile.identity_terms
    concept_terms = concept.concept_terms()

    if item_key and item_key in {pid_key, modifier_key, leaf_key}:
        score.identity_score += 70
        score.evidence.append("identity:exact_surface")
    elif item_no_forms and item_no_forms in {pid_key, modifier_key, leaf_key}:
        score.identity_score += 65
        score.evidence.append("identity:exact_without_form")

    for key_name, key_terms in (
        ("pid", set(pid_key.split())),
        ("modifier", set(modifier_key.split())),
        ("leaf", set(leaf_key.split())),
    ):
        key_terms = {t for t in key_terms if t not in GENERIC_IDENTITY_TOKENS}
        if key_terms and key_terms.issubset(identity_terms):
            score.identity_score += 35 + min(20, 5 * len(key_terms))
            score.evidence.append(f"identity:{key_name}_subset")

    overlap = identity_terms & concept_terms
    if overlap:
        score.identity_score += min(30, 10 * len(overlap))
        score.evidence.append("identity:term_overlap=" + ",".join(sorted(overlap)))

    sr_terms = token_set(profile.sr28_desc) - GENERIC_IDENTITY_TOKENS
    ref_overlap = sr_terms & set(concept.reference_tokens)
    if ref_overlap:
        score.reference_score += min(20, 5 + 5 * len(ref_overlap))
        score.evidence.append("reference:sr28_overlap=" + ",".join(sorted(ref_overlap)[:5]))

    if profile.htc_prefix and concept.htc_prefixes:
        if profile.htc_prefix in concept.htc_prefixes:
            score.htc_score += 25
            score.evidence.append("htc:prefix_agrees")
        elif profile.htc_group and any(p.startswith(profile.htc_group) for p in concept.htc_prefixes):
            score.htc_score += 8
            score.evidence.append("htc:group_agrees")
        elif profile.htc_group and profile.htc_group not in {"0", "N"}:
            score.htc_score -= 40
            score.hard_vetoes.append("htc_group_conflict")
            score.evidence.append("htc:group_conflict")

    if fresh_leaf_profile(profile):
        if path_starts(concept.canonical, ("Produce", "Produce > Fresh Herbs", "Produce > Vegetables")):
            score.path_score += 85
            score.evidence.append("path:fresh_leaf_prefers_produce")
        elif path_starts(concept.canonical, ("Pantry > Spices & Seasonings",)):
            score.path_score -= 40
            score.evidence.append("path:fresh_leaf_penalizes_dried_spice")
        elif path_starts(concept.canonical, ("Snack", "Snack > Candy", "Beverage", "Personal Care")):
            score.path_score -= 120
            score.evidence.append("path:fresh_leaf_rejects_non_herb_context")

    if concept.avg_confidence:
        score.provenance_score += min(8, concept.avg_confidence * 8)
    if concept.source_conflict_count:
        score.provenance_score -= min(12, 30 * concept.source_conflict_count / max(concept.count, 1))
        score.evidence.append("provenance:source_conflict")
    if concept.review_flag_count:
        score.provenance_score -= min(8, 20 * concept.review_flag_count / max(concept.count, 1))
        score.evidence.append("provenance:review_flags")
    return score


def candidate_pool(profile: IngredientProfile, index: EvidenceIndex, *, cap: int = 800) -> dict[tuple[str, str, str], tuple[ConceptEvidence, str]]:
    out: dict[tuple[str, str, str], tuple[ConceptEvidence, str]] = {}
    keys = {normalize_phrase(profile.item)}
    without_forms = " ".join(t for t in normalize_phrase(profile.item).split() if t not in profile.form_terms)
    if without_forms:
        keys.add(without_forms)
    for key in keys:
        for concept in index.by_exact_key.get(key, [])[:cap]:
            out[concept.key] = (concept, "exact_key")
    for term in sorted(profile.identity_terms):
        for concept in index.by_term.get(term, [])[:cap]:
            out.setdefault(concept.key, (concept, f"identity_term:{term}"))
    if len(out) < 30 and profile.htc_prefix:
        for concept in index.by_htc_prefix.get(profile.htc_prefix, [])[:cap]:
            out.setdefault(concept.key, (concept, "htc_prefix_backfill"))
    return out


def generate_candidates(profile: IngredientProfile, index: EvidenceIndex, *, limit: int = 20) -> list[CandidateScore]:
    scored = [
        score_candidate(profile, concept, source)
        for concept, source in candidate_pool(profile, index).values()
    ]
    scored = [s for s in scored if s.total() > 0 or not s.hard_vetoes]
    scored.sort(key=lambda s: (-s.total(), -s.identity_score, -s.htc_score, -s.concept.count, s.concept.pid))
    return scored[:limit]


def _required_terms(profile: IngredientProfile, concept: ConceptEvidence) -> tuple[str, ...]:
    positive_terms = concept.concept_terms()
    exact_concept_terms: set[str] = set()
    for blob in (concept.modifier, concept.pid, path_parts(concept.canonical)[-1] if path_parts(concept.canonical) else ""):
        exact_concept_terms.update(token_set(blob))
    item_terms = {
        t for t in token_set(profile.item)
        if t not in GENERIC_IDENTITY_TOKENS and t not in profile.form_terms
    }
    identity_form_terms = {
        t for t in (token_set(profile.item) & profile.form_terms)
        if t in exact_concept_terms
    }
    terms = {
        t for t in item_terms & positive_terms
        if t not in GENERIC_IDENTITY_TOKENS and t not in profile.form_terms
    }
    terms.update(identity_form_terms)
    if not terms:
        terms = {
            t for t in profile.identity_terms & positive_terms
            if t not in GENERIC_IDENTITY_TOKENS and t not in profile.form_terms
        }
        terms.update(identity_form_terms)
    if not terms:
        for blob in (concept.modifier, concept.pid, path_parts(concept.canonical)[-1] if path_parts(concept.canonical) else ""):
            terms.update(
                t for t in token_set(blob)
                if t in profile.identity_terms and t not in GENERIC_IDENTITY_TOKENS
            )
    return tuple(sorted(terms))


def _allowed_paths(concept: ConceptEvidence) -> tuple[str, ...]:
    canonical = PATH_SEP.join(path_parts(concept.canonical))
    parent = parent_path(canonical)
    out = [canonical]
    if parent and parent != canonical:
        out.append(parent)
    return tuple(dict.fromkeys(out))


def _allowed_forms(profile: IngredientProfile, concept: ConceptEvidence) -> tuple[str, ...]:
    forms = set(profile.form_terms)
    concept_form_terms = set(concept.facet_tokens) & FORM_TOKENS
    forms.update(concept_form_terms & profile.form_terms)
    return tuple(sorted(forms))


def fresh_leaf_fallback_contract(profile: IngredientProfile, reason: str) -> LearnedContract:
    label_terms = [
        term for term in normalize_phrase(profile.item).split()
        if term not in GENERIC_IDENTITY_TOKENS and term not in FORM_TOKENS
    ]
    label = " ".join(word.capitalize() for word in (label_terms or normalize_phrase(profile.item).split()))
    required = tuple(sorted(label_terms))
    if not required:
        required = tuple(sorted(
            term for term in profile.identity_terms
            if term not in GENERIC_IDENTITY_TOKENS and term not in FORM_TOKENS
        ))
    canonical = f"Produce > Fresh Herbs > {label}"
    return LearnedContract(
        ingredient_item=profile.item,
        recipe_count=profile.recipe_count,
        status="ready",
        concept_pid=label,
        canonical=canonical,
        modifier="",
        htc_code=profile.htc_code,
        allowed_htc_prefixes=(profile.htc_prefix,) if profile.htc_prefix else (),
        required_terms=required,
        forbidden_terms=("candy", "gum", "mouthwash", "toothpaste"),
        allowed_paths=(canonical, "Produce > Fresh Herbs", "Produce"),
        allowed_forms=tuple(sorted(profile.form_terms)),
        proxy_policy="none",
        confidence=0.78,
        evidence=(f"fresh_leaf_fallback:{reason}",),
    )


def _near_negative_concepts(
    required_terms: Iterable[str],
    best: ConceptEvidence,
    index: EvidenceIndex,
    *,
    cap_per_term: int = 500,
) -> list[ConceptEvidence]:
    out: dict[tuple[str, str, str], ConceptEvidence] = {}
    required = set(required_terms)
    for term in required:
        for concept in index.by_term.get(term, [])[:cap_per_term]:
            if concept.key == best.key:
                continue
            all_terms = concept.all_search_terms()
            if not required.issubset(all_terms):
                continue
            same_pid = normalize_phrase(concept.pid) == normalize_phrase(best.pid)
            same_modifier = normalize_phrase(concept.modifier) == normalize_phrase(best.modifier)
            if same_pid and same_modifier and path_starts(concept.canonical, _allowed_paths(best)) and (
                not best.htc_prefixes or not concept.htc_prefixes or best.htc_prefixes & concept.htc_prefixes
            ):
                continue
            out[concept.key] = concept
    return list(out.values())


def _learn_forbidden_terms(required_terms: tuple[str, ...], best: ConceptEvidence, index: EvidenceIndex) -> tuple[str, ...]:
    if not required_terms:
        return ()
    positives = Counter(best.identity_tokens)
    positives.update(best.reference_tokens)
    positives.update(best.path_tokens)
    negatives: Counter[str] = Counter()
    for concept in _near_negative_concepts(required_terms, best, index):
        risk_weight = 1
        if best.htc_prefixes and concept.htc_prefixes and not (best.htc_prefixes & concept.htc_prefixes):
            risk_weight += 1
        if not path_starts(concept.canonical, _allowed_paths(best)):
            risk_weight += 1
        for counter in (concept.identity_tokens, concept.title_tokens, concept.path_tokens, concept.category_tokens):
            for term, count in counter.items():
                negatives[term] += min(count, 5) * risk_weight
    out: list[str] = []
    required = set(required_terms)
    positive_concept_terms = best.concept_terms()
    for term, count in negatives.most_common(40):
        if term in required or term in STOP_TOKENS or term in FORBIDDEN_LEARN_SKIP:
            continue
        if term in positive_concept_terms and positives.get(term, 0):
            continue
        if positives.get(term, 0) and positives[term] >= count:
            continue
        out.append(term)
        if len(out) >= 20:
            break
    return tuple(sorted(out))


def learn_contract(profile: IngredientProfile, candidates: list[CandidateScore], index: EvidenceIndex) -> LearnedContract:
    if normalize_phrase(profile.item) in {"water", "fresh water", "tap water", "plain water", "ice", "ice cube"}:
        return LearnedContract(
            ingredient_item=profile.item,
            recipe_count=profile.recipe_count,
            status="tap_water",
            htc_code=profile.htc_code,
            confidence=1.0,
            evidence=("terminal:tap_water",),
        )
    if not candidates:
        if fresh_leaf_profile(profile):
            return fresh_leaf_fallback_contract(profile, "no_consensus_candidate")
        return LearnedContract(
            ingredient_item=profile.item,
            recipe_count=profile.recipe_count,
            status="no_concept",
            htc_code=profile.htc_code,
            review_reason="no_consensus_candidate",
        )
    best = candidates[0]
    runner = candidates[1] if len(candidates) > 1 else None
    margin = best.total() - runner.total() if runner else 999.0
    if fresh_leaf_profile(profile) and not path_starts(best.concept.canonical, ("Produce",)):
        return fresh_leaf_fallback_contract(profile, "non_herb_consensus_winner")
    if best.total() < 45:
        return LearnedContract(
            ingredient_item=profile.item,
            recipe_count=profile.recipe_count,
            status="needs_llm_contract_review",
            htc_code=profile.htc_code,
            concept_pid=best.concept.pid,
            canonical=best.concept.canonical,
            modifier=best.concept.modifier,
            confidence=max(0.0, best.total() / 100.0),
            review_reason="low_candidate_score",
            evidence=tuple(best.evidence),
        )
    if runner and margin < 8 and best.identity_score < 70:
        return LearnedContract(
            ingredient_item=profile.item,
            recipe_count=profile.recipe_count,
            status="needs_llm_contract_review",
            htc_code=profile.htc_code,
            concept_pid=best.concept.pid,
            canonical=best.concept.canonical,
            modifier=best.concept.modifier,
            confidence=max(0.0, min(0.75, best.total() / 120.0)),
            review_reason=f"ambiguous_runner_margin={margin:.1f}",
            evidence=tuple(best.evidence + [f"runner={runner.concept.pid}@{runner.concept.canonical}"]),
        )
    surface_terms = {
        t for t in token_set(profile.item)
        if t not in GENERIC_IDENTITY_TOKENS and t not in profile.form_terms
    }
    concept_terms = best.concept.concept_terms()
    strong_surface_terms = surface_terms - WEAK_SURFACE_TERMS
    if surface_terms and (
        not (surface_terms & concept_terms)
        or (strong_surface_terms and not (strong_surface_terms & concept_terms))
    ):
        return LearnedContract(
            ingredient_item=profile.item,
            recipe_count=profile.recipe_count,
            status="needs_llm_contract_review",
            htc_code=profile.htc_code,
            concept_pid=best.concept.pid,
            canonical=best.concept.canonical,
            modifier=best.concept.modifier,
            confidence=max(0.0, min(0.65, best.total() / 140.0)),
            review_reason="surface_reference_conflict",
            evidence=tuple(best.evidence + [
                "surface_terms=" + ",".join(sorted(surface_terms)),
                "concept_terms=" + ",".join(sorted(concept_terms)[:12]),
            ]),
        )
    required = _required_terms(profile, best.concept)
    if not required:
        return LearnedContract(
            ingredient_item=profile.item,
            recipe_count=profile.recipe_count,
            status="needs_llm_contract_review",
            htc_code=profile.htc_code,
            concept_pid=best.concept.pid,
            canonical=best.concept.canonical,
            modifier=best.concept.modifier,
            confidence=max(0.0, min(0.7, best.total() / 120.0)),
            review_reason="no_required_identity_terms",
            evidence=tuple(best.evidence),
        )
    allowed_prefixes = tuple(sorted(best.concept.htc_prefixes))
    forbidden = _learn_forbidden_terms(required, best.concept, index)
    confidence = min(0.99, max(0.4, (best.total() + min(margin, 30)) / 140.0))
    return LearnedContract(
        ingredient_item=profile.item,
        recipe_count=profile.recipe_count,
        status="ready",
        concept_pid=best.concept.pid,
        canonical=best.concept.canonical,
        modifier=best.concept.modifier,
        htc_code=profile.htc_code,
        allowed_htc_prefixes=allowed_prefixes,
        required_terms=required,
        forbidden_terms=forbidden,
        allowed_paths=_allowed_paths(best.concept),
        allowed_forms=_allowed_forms(profile, best.concept),
        proxy_policy="none",
        confidence=confidence,
        evidence=tuple(best.evidence + [f"candidate_score={best.total():.1f}", f"runner_margin={margin:.1f}"]),
    )


def load_product_evidence(path: Path) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    if not path.exists():
        return out
    with path.open(encoding="utf-8", errors="replace", newline="") as handle:
        for row in csv.DictReader(handle):
            rowid = (row.get("rowid") or "").strip()
            if rowid:
                out[rowid] = row
    return out


def load_product_records(
    db_path: Path = DEFAULT_PRICED_DB,
    evidence_path: Path = DEFAULT_PRODUCT_EVIDENCE,
    *,
    include_quarantine_without_veto: bool = True,
    limit: int = 0,
) -> list[ProductRecord]:
    if not db_path.exists():
        return []
    evidence = load_product_evidence(evidence_path)
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    sql = """
        SELECT rowid, source, upc, name, brand, grams, cents,
               category_path, category_path_walmart, marketplace, available,
               htc_code, consensus_pid, consensus_canonical, consensus_modifier
        FROM priced_products
        WHERE marketplace = 0 AND available = 1 AND grams > 0 AND cents > 0
        ORDER BY rowid
    """
    if limit > 0:
        sql += " LIMIT ?"
        rows = con.execute(sql, (limit,))
    else:
        rows = con.execute(sql)
    out: list[ProductRecord] = []
    for row in rows:
        rowid = str(row["rowid"])
        ev = evidence.get(rowid, {})
        taxonomy_status = ev.get("taxonomy_status") or ""
        hard_vetoes = ev.get("hard_vetoes") or ""
        existing_pid = ev.get("existing_pid") or row["consensus_pid"] or ""
        existing_canonical = ev.get("existing_canonical") or row["consensus_canonical"] or ""
        existing_modifier = ev.get("existing_modifier") or row["consensus_modifier"] or ""
        tree_pid, tree_canonical, tree_modifier = _choose_product_tree_fields(
            title=row["name"] or "",
            existing_pid=existing_pid,
            existing_canonical=existing_canonical,
            existing_modifier=existing_modifier,
            existing_bridge_status=ev.get("existing_bridge_status") or "",
            proposed_pid=ev.get("proposed_pid") or "",
            proposed_canonical=ev.get("proposed_canonical") or "",
            proposed_modifier=ev.get("proposed_modifier") or "",
        )
        fresh_herb_override = _fresh_herb_product_tree_fields(
            title=row["name"] or "",
            category_path=row["category_path"] or "",
            category_path_walmart=row["category_path_walmart"] or "",
        )
        if fresh_herb_override:
            tree_pid, tree_canonical, tree_modifier = fresh_herb_override
        chose_existing_identity = (
            bool(existing_pid or existing_canonical)
            and normalize_phrase(tree_pid) == normalize_phrase(existing_pid)
            and normalize_phrase(tree_canonical) == normalize_phrase(existing_canonical)
        )
        if taxonomy_status and not taxonomy_status.startswith("approved"):
            if hard_vetoes and not chose_existing_identity:
                continue
            if not include_quarantine_without_veto and not chose_existing_identity:
                continue
        try:
            evidence_score = float(ev.get("total_score") or 0)
        except ValueError:
            evidence_score = 0.0
        out.append(ProductRecord(
            rowid=rowid,
            source=row["source"] or "",
            upc=row["upc"] or f"rowid:{rowid}",
            name=row["name"] or "",
            brand=row["brand"] or "",
            grams=float(row["grams"] or 0),
            cents=int(row["cents"] or 0),
            category_path=row["category_path"] or "",
            category_path_walmart=row["category_path_walmart"] or "",
            htc_code=row["htc_code"] or "",
            proposed_pid=tree_pid,
            proposed_canonical=tree_canonical,
            proposed_modifier=tree_modifier.split(PATH_SEP)[0].strip(),
            taxonomy_status=taxonomy_status or "raw_priced_product",
            hard_vetoes=hard_vetoes,
            evidence_score=evidence_score,
        ))
    return out


def product_candidates(contract: LearnedContract, index: ProductIndex, *, cap: int = 2500) -> list[ProductRecord]:
    exact: dict[str, ProductRecord] = {}
    out: dict[str, ProductRecord] = {}
    for product in index.by_concept_key.get(contract.concept_key, []):
        exact[product.rowid] = product
        out[product.rowid] = product
    required = list(contract.required_terms)
    if required:
        pools = [index.by_term.get(term, [])[:cap] for term in required]
        if pools:
            rowid_sets = [set(p.rowid for p in pool) for pool in pools]
            common = set.intersection(*rowid_sets) if rowid_sets else set()
            if common:
                for pool in pools:
                    for product in pool:
                        if product.rowid in common:
                            out[product.rowid] = product
            else:
                for pool in pools:
                    for product in pool:
                        out.setdefault(product.rowid, product)
    exact_rows = sorted(exact.values(), key=lambda p: (-p.evidence_score, p.cpg, p.cents))
    remaining = [product for rowid, product in out.items() if rowid not in exact]
    remaining.sort(key=lambda p: (-p.evidence_score, p.cpg, p.cents))
    if len(exact_rows) >= cap:
        return exact_rows[:cap]
    return exact_rows + remaining[: max(0, cap - len(exact_rows))]


def _contract_primary_identity_terms(contract: LearnedContract) -> set[str]:
    parts = path_parts(contract.canonical)
    leaf = parts[-1] if parts else ""
    identity_blobs = [contract.concept_pid, leaf]
    if contract.concept_pid in RULE_B_PIDS and contract.modifier:
        identity_blobs.append(contract.modifier)
    terms = _identity_terms_from_blob(" ".join(identity_blobs))
    form_terms = set(contract.allowed_forms)
    if form_terms:
        reduced = terms - form_terms
        terms = reduced or terms
    return terms


def primary_identity_reject_reason(contract: LearnedContract, product: ProductRecord) -> str:
    """Reject products whose tree identity only mentions the ingredient as a facet.

    The consensus tree separates a SKU's primary shopping identity from its
    modifier/flavor/form fields. Recipe pricing should match on that primary
    identity first; title tokens and facets can only rank already-compatible
    products.
    """
    if not (product.proposed_pid or product.proposed_canonical):
        return ""

    contract_terms = _contract_primary_identity_terms(contract)
    product_terms = product.primary_identity_terms
    if not contract_terms or not product_terms:
        return ""

    contract_pid_key = normalize_phrase(contract.concept_pid)
    product_pid_key = normalize_phrase(product.proposed_pid)
    if contract_pid_key and product_pid_key and contract_pid_key == product_pid_key:
        return ""

    contract_leaf = normalize_phrase(path_parts(contract.canonical)[-1] if path_parts(contract.canonical) else "")
    product_leaf = normalize_phrase(path_parts(product.proposed_canonical)[-1] if path_parts(product.proposed_canonical) else "")
    if contract_leaf and product_leaf and contract_leaf == product_leaf:
        return ""

    allowed_extra = FORM_TOKENS | set(contract.allowed_forms) | set(contract.required_terms)
    if contract_terms <= product_terms:
        extra_terms = product_terms - contract_terms - allowed_extra
        if not extra_terms:
            return ""
    elif product_terms <= contract_terms:
        return ""

    return f"primary_identity_conflict:{_identity_label(product.primary_identity_label)}"


def product_form_reject_reason(contract: LearnedContract, product: ProductRecord) -> str:
    allowed = set(contract.allowed_forms) | token_set(contract.ingredient_item)
    allowed.update(*(FORM_SYNONYMS.get(term, {term}) for term in list(allowed)))
    form_blob = " ".join([product.name, product.proposed_modifier])
    if "pack" not in allowed and MULTIPACK_RE.search(product.name):
        return "form_conflict:multipack"
    for term in sorted(STRICT_PRODUCT_FORM_TERMS):
        equivalents = FORM_SYNONYMS.get(term, {term})
        if allowed & equivalents:
            continue
        if phrase_present(form_blob, term):
            return f"form_conflict:{term}"
    return ""


def product_flavor_reject_reason(contract: LearnedContract, product: ProductRecord) -> str:
    allowed = token_set(contract.ingredient_item) | set(contract.required_terms)
    flavor_blob = " ".join([product.name, product.proposed_modifier])
    flavor_terms = token_set(flavor_blob) & FLAVOR_CONFLICT_TERMS
    for term in sorted(flavor_terms - allowed):
        return f"flavor_conflict:{term}"
    return ""


def plain_staple_reject_reason(contract: LearnedContract, product: ProductRecord) -> str:
    item_terms = token_set(contract.ingredient_item)
    title_terms = token_set(product.name)
    modifier_terms = token_set(product.proposed_modifier)
    category_terms = token_set(" ".join([product.category_path, product.category_path_walmart]))
    product_terms = title_terms | modifier_terms | category_terms | token_set(product.proposed_canonical)

    if "salt" in item_terms:
        if product_terms & {"himalayan", "pink", "grinder", "refill"}:
            return "staple_conflict:non_plain_salt"

    if "milk" in item_terms and "buttermilk" not in item_terms:
        if "buttermilk" in product_terms:
            return "staple_conflict:buttermilk"

    if "banana" in item_terms and not (item_terms & {"frozen", "sliced", "puree", "baby"}):
        if product_terms & {"frozen", "sliced", "chip", "chips", "puree"}:
            return "staple_conflict:not_fresh_banana"
        if "baby" in category_terms:
            return "staple_conflict:baby_food"

    if item_terms & {"onion"} and not (item_terms & {"dried", "dry", "powder", "powdered"}):
        if category_terms & {"pantry", "spice", "spices", "seasoning", "seasonings"}:
            return "staple_conflict:not_fresh_onion"
        if title_terms & {"bottle", "powder", "dried", "dehydrated"}:
            return "staple_conflict:not_fresh_onion"

    if {"vegetable", "oil"} <= item_terms:
        if product_terms & {"avocado", "olive", "coconut", "peanut", "sesame"}:
            return "staple_conflict:non_vegetable_oil"

    if fresh_leaf_contract(contract):
        if product_terms & {"dressing", "dressings", "dip", "dips", "sauce", "salad", "yogurt"}:
            return "staple_conflict:not_fresh_herb"

    return ""


def fresh_leaf_contract(contract: LearnedContract) -> bool:
    item_terms = token_set(contract.ingredient_item)
    return bool(item_terms & FRESH_LEAF_TERMS) and path_starts(contract.canonical, ("Produce",))


def required_term_satisfied(contract: LearnedContract, product: ProductRecord, term: str) -> bool:
    title_blob = product.name
    if phrase_present(title_blob, term):
        return True
    if term == "pepper" and "chili" in contract.required_terms and phrase_present(title_blob, "chili"):
        return True
    return False


def plain_staple_preference_score(contract: LearnedContract, product: ProductRecord) -> float:
    item_terms = token_set(contract.ingredient_item)
    title_terms = token_set(product.name)
    modifier_terms = token_set(product.proposed_modifier)
    category_terms = token_set(" ".join([product.category_path, product.category_path_walmart]))
    canonical = product.proposed_canonical
    score = 0.0

    if "salt" in item_terms:
        if title_terms & {"plain", "iodized"} or modifier_terms & {"plain", "iodized"}:
            score += 45
        if title_terms & {"himalayan", "pink", "grinder", "refill"} or modifier_terms & {"himalayan", "pink"}:
            score -= 80
        if (title_terms | modifier_terms) & {"sea"} and "sea" not in item_terms:
            score -= 70
        if modifier_terms & {"flaky"} and not (title_terms & {"plain", "iodized"}):
            score -= 35

    if "banana" in item_terms:
        if path_starts(canonical, ("Produce > Fruit > Bananas",)):
            score += 75
        if PRODUCE_PLU_RE.match(product.upc or ""):
            score += 35
        if "fresh" in title_terms:
            score += 20
        if path_starts(canonical, ("Frozen", "Frozen > Frozen Fruit")) and not (item_terms & {"frozen", "sliced"}):
            score -= 45

    if "yogurt" in item_terms:
        if "plain" in title_terms or "plain" in modifier_terms:
            score += 60
        flavor_noise = title_terms & {"strawberry", "banana", "mango", "berry", "blueberry", "raspberry", "peach", "vanilla"}
        if flavor_noise and "plain" in item_terms:
            score -= 90

    if "rice" in item_terms and not (item_terms & {"ready", "instant", "microwavable", "microwaveable"}):
        if title_terms & {"ready", "pouch", "microwavable", "microwaveable", "second"}:
            score -= 70
        if title_terms & {"rice"} and not (title_terms & {"ready", "pouch", "microwavable", "microwaveable", "second"}):
            score += 25

    if "milk" in item_terms and "lactose" in title_terms and "lactose" not in item_terms:
        score -= 25

    if "ghee" in item_terms:
        if title_terms & {"plain", "original", "clarified"} or modifier_terms & {"plain", "clarified"}:
            score += 35
        if (title_terms | modifier_terms) & {"himalayan", "pink", "salt"} and "salt" not in item_terms:
            score -= 75

    if item_terms & FRESH_LEAF_TERMS:
        if "produce" in category_terms:
            score += 70
        if category_terms & {"baking", "spice", "spices", "seasoning", "seasonings", "pantry"}:
            score -= 70
        if PRODUCE_PLU_RE.match(product.upc or ""):
            score += 25

    return score


def contract_reject_reason(contract: LearnedContract, product: ProductRecord) -> str:
    if contract.status != "ready":
        return contract.status
    blob = product.searchable_blob()
    title_blob = product.name
    identity_blob = " ".join([
        product.name,
        product.brand,
        product.proposed_pid,
        product.proposed_canonical,
        product.proposed_modifier,
    ])
    category_blob = " ".join([product.category_path, product.category_path_walmart, product.proposed_canonical])
    if NON_FOOD_RE.search(blob):
        return "reject_non_food"
    identity_reason = primary_identity_reject_reason(contract, product)
    if identity_reason:
        return identity_reason
    identity_ok = True
    for term in contract.required_terms:
        if not required_term_satisfied(contract, product, term):
            return f"missing_required:{term}"
        if absent_claim_present(title_blob, term):
            return f"absent_claim:{term}"
    form_reason = product_form_reject_reason(contract, product)
    if form_reason:
        return form_reason
    flavor_reason = product_flavor_reject_reason(contract, product)
    if flavor_reason:
        return flavor_reason
    staple_reason = plain_staple_reject_reason(contract, product)
    if staple_reason:
        return staple_reason
    for term in contract.forbidden_terms:
        if phrase_present(identity_blob, term):
            return f"forbidden_term:{term}"
    if contract.allowed_paths:
        path_ok = path_starts(product.proposed_canonical, contract.allowed_paths)
        if not path_ok:
            # Retail categories use slashes and include Home Page/Food; token
            # overlap keeps this from rejecting good rows that lack evidence
            # canonical but have a matching retailer category path.
            category_terms = token_set(category_blob)
            if fresh_leaf_contract(contract):
                path_ok = bool(category_terms & {"produce", "herb", "herbs"})
            else:
                allowed_leaf_terms = set()
                for path in contract.allowed_paths:
                    if path_parts(path):
                        allowed_leaf_terms.update(token_set(path_parts(path)[-1]))
                path_ok = bool(allowed_leaf_terms & category_terms)
        if not path_ok:
            return "path_conflict"
    if contract.allowed_htc_prefixes and product.htc_prefix:
        if product.htc_prefix not in contract.allowed_htc_prefixes:
            allowed_groups = {prefix[:1] for prefix in contract.allowed_htc_prefixes if prefix}
            if product.htc_group and product.htc_group not in allowed_groups and not identity_ok:
                return f"htc_conflict:{product.htc_prefix}"
    if (
        COMPONENT_CONTEXT_RE.search(normalize_phrase(product.name))
        and product.concept_key != contract.concept_key
        and not path_starts(product.proposed_canonical, contract.allowed_paths)
    ):
        return "component_or_flavor_context"
    return ""


def product_accept_score(contract: LearnedContract, product: ProductRecord) -> float:
    score = product.evidence_score
    if product.concept_key == contract.concept_key:
        score += 25
    if path_starts(product.proposed_canonical, contract.allowed_paths):
        score += 12
    if product.htc_prefix and product.htc_prefix in contract.allowed_htc_prefixes:
        score += 8
    score += 4 * sum(1 for term in contract.required_terms if phrase_present(product.name, term))
    score += plain_staple_preference_score(contract, product)
    return score


def pick_product_for_contract(contract: LearnedContract, index: ProductIndex, *, cap: int = 2500) -> ProductMatch:
    if contract.status == "tap_water":
        return ProductMatch(status="tap_water", reason="tap_water")
    if contract.status != "ready":
        return ProductMatch(status="no_contract", reason=contract.status)

    def scan(search_cap: int) -> tuple[list[tuple[float, ProductRecord]], Counter[str]]:
        rejected: Counter[str] = Counter()
        accepted: list[tuple[float, ProductRecord]] = []
        for product in product_candidates(contract, index, cap=search_cap):
            reason = contract_reject_reason(contract, product)
            if reason:
                rejected[reason] += 1
                continue
            accepted.append((product_accept_score(contract, product), product))
        return accepted, rejected

    accepted, rejected = scan(cap)
    if not accepted and cap < 10000:
        accepted, rejected = scan(10000)
    if not accepted:
        reason = "no_candidate_products"
        if rejected:
            reason = ";".join(f"{k}={v}" for k, v in rejected.most_common(5))
        return ProductMatch(
            status="needs_product_api_query",
            reason=reason,
            rejected=tuple(f"{k}={v}" for k, v in rejected.most_common(10)),
        )
    accepted.sort(key=lambda entry: (-entry[0], entry[1].cpg, entry[1].cents, entry[1].product_key if hasattr(entry[1], "product_key") else entry[1].rowid))
    score, product = accepted[0]
    return ProductMatch(status="accepted_offer", product=product, score=score, reason="accepted")


def candidate_row(profile: IngredientProfile, candidate: CandidateScore, rank: int, margin: float) -> dict[str, object]:
    return {
        "ingredient_item": profile.item,
        "recipe_count": profile.recipe_count,
        "ingredient_htc_code": profile.htc_code,
        "ingredient_identity_terms": "|".join(sorted(profile.identity_terms)),
        "candidate_rank": rank,
        "candidate_pid": candidate.concept.pid,
        "candidate_canonical": candidate.concept.canonical,
        "candidate_modifier": candidate.concept.modifier,
        "candidate_count": candidate.concept.count,
        "candidate_htc_prefixes": "|".join(sorted(candidate.concept.htc_prefixes)),
        "score": f"{candidate.total():.1f}",
        "margin_to_next": f"{margin:.1f}",
        "identity_score": f"{candidate.identity_score:.1f}",
        "reference_score": f"{candidate.reference_score:.1f}",
        "htc_score": f"{candidate.htc_score:.1f}",
        "path_score": f"{candidate.path_score:.1f}",
        "provenance_score": f"{candidate.provenance_score:.1f}",
        "source": candidate.source,
        "hard_vetoes": "|".join(candidate.hard_vetoes),
        "evidence": "; ".join(candidate.evidence),
    }


def bridge_row(contract: LearnedContract, match: ProductMatch) -> dict[str, object]:
    product = match.product
    offer_status = match.status
    terminal = terminal_status_for_offer(contract.status, offer_status)
    return {
        "ingredient_item": contract.ingredient_item,
        "recipe_count": contract.recipe_count,
        "contract_status": contract.status,
        "offer_status": offer_status,
        "terminal_status": terminal,
        "concept_pid": contract.concept_pid,
        "canonical_path": contract.canonical,
        "modifier": contract.modifier,
        "required_terms": "|".join(contract.required_terms),
        "forbidden_terms": "|".join(contract.forbidden_terms),
        "allowed_paths": "|".join(contract.allowed_paths),
        "allowed_htc_prefixes": "|".join(contract.allowed_htc_prefixes),
        "contract_confidence": f"{contract.confidence:.3f}",
        "review_reason": contract.review_reason,
        "product_rowid": product.rowid if product else "",
        "source": product.source if product else "",
        "upc": product.upc if product else "",
        "name": product.name if product else "",
        "grams": f"{product.grams:.1f}" if product else "",
        "cents": product.cents if product else "",
        "cpg": f"{product.cpg:.6f}" if product else "",
        "product_identity": product.proposed_pid if product else "",
        "product_canonical_path": product.proposed_canonical if product else "",
        "product_modifier": product.proposed_modifier if product else "",
        "product_score": f"{match.score:.1f}" if product else "",
        "product_taxonomy_status": product.taxonomy_status if product else "",
        "product_evidence_score": f"{product.evidence_score:.1f}" if product else "",
        "reject_reason": match.reason,
        "rejected_summary": "|".join(match.rejected),
    }


def summary_from_rows(rows: Iterable[dict[str, object]], *, total_recipe_lines: int | None = None) -> dict[str, object]:
    row_list = list(rows)
    status_counts: Counter[str] = Counter()
    line_counts: Counter[str] = Counter()
    safe_lines = 0
    scored_lines = 0
    for row in row_list:
        status = str(row.get("terminal_status") or "")
        try:
            recipe_count = int(float(row.get("recipe_count") or 0))
        except ValueError:
            recipe_count = 0
        status_counts[status] += 1
        line_counts[status] += recipe_count
        scored_lines += recipe_count
        if status in {"safe_priced", "safe_tap_water"}:
            safe_lines += recipe_count
    total = total_recipe_lines if total_recipe_lines is not None else scored_lines
    return {
        "ingredients_scored": len(row_list),
        "recipe_lines_scored": scored_lines,
        "safe_recipe_lines": safe_lines,
        "safe_line_pct_of_scored": round((safe_lines / scored_lines * 100), 2) if scored_lines else 0.0,
        "safe_line_lower_bound_pct_of_full_corpus": round((safe_lines / total * 100), 2) if total else 0.0,
        "terminal_status_counts": dict(status_counts.most_common()),
        "terminal_line_counts": dict(line_counts.most_common()),
    }


def write_jsonl(path: Path, rows: Iterable[Mapping[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
