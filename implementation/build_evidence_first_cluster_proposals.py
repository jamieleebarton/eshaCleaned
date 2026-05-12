from __future__ import annotations

import argparse
import csv
import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd

import build_ingredient_fingerprint_clusters as ingredient_clusters
import match_esha_to_products as matcher
import self_heal_common as self_heal
import self_heal_policy as policy


ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "implementation" / "output"
ESHA_CSV = ROOT / "esha_cleaned.csv"
CANONICAL_CSV = OUT_DIR / "canonical_surface_normalized_with_product_proxies_CLEANED.csv"

DEFAULT_MEMBERS = OUT_DIR / "ingredient_only_cluster_members.csv"
DEFAULT_CLUSTERS = OUT_DIR / "ingredient_only_clusters.csv"
OUT_PROPOSALS = OUT_DIR / "evidence_first_cluster_proposals.csv"
OUT_CONFLICTS = OUT_DIR / "evidence_first_cluster_conflicts.csv"
OUT_SUMMARY = OUT_DIR / "evidence_first_cluster_summary.json"


TOKEN_RE = re.compile(r"[a-z][a-z0-9']+")

NOISE_TERMS = (
    matcher.STOPWORDS
    | ingredient_clusters.INGREDIENT_STOPWORDS
    | ingredient_clusters.TITLE_NOISE
    | {
        "food",
        "foods",
        "product",
        "products",
        "brand",
        "quality",
        "premium",
        "select",
        "original",
        "classic",
        "natural",
        "organic",
        "fresh",
        "freshly",
        "style",
        "flavor",
        "flavored",
        "flavors",
        "pack",
        "count",
    }
)

FUNCTION_TERMS = {
    "applesauce",
    "sauce",
    "glaze",
    "vinegar",
    "juice",
    "drink",
    "cider",
    "smoothie",
    "water",
    "soda",
    "tea",
    "coffee",
    "stuffing",
    "dressing",
    "dip",
    "salsa",
    "hummus",
    "soup",
    "meal",
    "dinner",
    "entree",
    "bowl",
    "bar",
    "bars",
    "candy",
    "cookie",
    "cookies",
    "cake",
    "muffin",
    "muffins",
    "pie",
    "pudding",
    "custard",
    "creamer",
    "cream",
    "yogurt",
    "protein",
    "powder",
    "mix",
    "filling",
    "spread",
    "butter",
    "cheese",
}

FORM_SUPPORT: dict[str, set[str]] = {
    "bagel": {"bagel", "bagels"},
    "bar": {"bar", "bars"},
    "baking chips": {"chip", "chips", "morsel", "morsels"},
    "baking mix": {"baking", "mix", "pancake", "pancakes", "waffle", "waffles", "cake", "cookie", "muffin", "bread"},
    "baking powder": {"baking", "powder"},
    "baking soda": {"baking", "soda"},
    "burrito": {"burrito", "burritos"},
    "cake": {"cake", "cakes", "cupcake", "cupcakes"},
    "candy": {"candy", "candies", "chocolate", "gum", "gummi", "jellybean"},
    "cereal": {"cereal", "granola", "oatmeal"},
    "chips": {"chip", "chips", "crisp", "crisps"},
    "cookie": {"cookie", "cookies", "cooky"},
    "cookies": {"cookie", "cookies", "cooky"},
    "cracker": {"cracker", "crackers", "biscuit", "biscotti"},
    "doughnut": {"donut", "donuts", "doughnut", "doughnuts"},
    "dressing": {"dressing", "dressings", "vinaigrette", "mayonnaise", "mayo"},
    "fruit snacks": {"fruit", "snack", "snacks"},
    "hummus": {"hummus"},
    "juice": {"juice", "nectar"},
    "juice drink": {"juice", "drink", "beverage", "nectar"},
    "macaroni": {"macaroni", "pasta", "noodle", "noodles"},
    "mashed potatoes": {"mashed", "mash", "potato", "potatoes"},
    "muffin": {"muffin", "muffins"},
    "pasta": {"pasta", "noodle", "noodles", "spaghetti", "macaroni", "penne", "rigatoni", "fettuccine", "lasagna"},
    "pasta dish": {"pasta", "noodle", "noodles", "spaghetti", "macaroni", "lasagna", "ravioli"},
    "pizza": {"pizza"},
    "popcorn": {"popcorn"},
    "pretzels": {"pretzel", "pretzels"},
    "pudding": {"pudding", "puddings"},
    "salad dressing": {"dressing", "dressings", "vinaigrette", "mayonnaise", "mayo"},
    "sandwich": {"sandwich", "sandwiches", "sub", "hoagie"},
    "salsa": {"salsa"},
    "soup": {"soup", "chowder", "bisque"},
    "taco": {"taco", "tacos"},
    "waffles": {"waffle", "waffles"},
    "wrap": {"wrap", "wraps"},
}

DRY_PASTA_CATEGORIES = {"Pasta by Shape & Type", "All Noodles"}

FRESH_SINGLE_FRUIT_HEADS = {
    "apple",
    "apricot",
    "banana",
    "blackberry",
    "blueberry",
    "cherry",
    "grape",
    "grapefruit",
    "kiwi",
    "mango",
    "melon",
    "orange",
    "peach",
    "pear",
    "pineapple",
    "plum",
    "raspberry",
    "strawberry",
    "watermelon",
}

FRUIT_TERMS = {
    "apple",
    "apricot",
    "banana",
    "blackberry",
    "blueberry",
    "cherry",
    "cranberry",
    "grape",
    "grapefruit",
    "kiwi",
    "mango",
    "melon",
    "orange",
    "peach",
    "pear",
    "pineapple",
    "plum",
    "raspberry",
    "strawberry",
    "watermelon",
}

SEAFOOD_TERMS = {
    "anchovy",
    "anchovies",
    "clam",
    "clams",
    "crab",
    "fish",
    "herring",
    "mackerel",
    "oyster",
    "oysters",
    "salmon",
    "sardine",
    "sardines",
    "seafood",
    "shrimp",
    "tilapia",
    "trout",
    "tuna",
}

MEAT_SPECIES_TERMS = {
    "beef",
    "chicken",
    "duck",
    "goat",
    "ham",
    "lamb",
    "pork",
    "turkey",
    "veal",
}

DRESSING_IDENTITY_TERMS = {
    "balsamic",
    "caesar",
    "dijon",
    "french",
    "honey",
    "italian",
    "mustard",
    "ranch",
    "russian",
    "thousand",
    "vinaigrette",
}

COMPONENT_TERMS = (
    matcher.SEAFOOD
    | matcher.POULTRY
    | matcher.MEATS
    | matcher.LEGUMES
    | matcher.NUTS_SEEDS
    | matcher.VEGETABLES
    | matcher.FRUITS
    | matcher.GRAINS
    | {
        "bacon",
        "bagel",
        "bar",
        "bean",
        "beans",
        "beef",
        "butter",
        "candy",
        "cheese",
        "chicken",
        "chip",
        "chips",
        "cookie",
        "cream",
        "egg",
        "flour",
        "hummus",
        "juice",
        "milk",
        "muffin",
        "noodle",
        "noodles",
        "pasta",
        "pizza",
        "popcorn",
        "pork",
        "potato",
        "potatoes",
        "pretzel",
        "pretzels",
        "rice",
        "salsa",
        "sauce",
        "soup",
        "turkey",
        "yogurt",
    }
)


@dataclass(frozen=True)
class EshaCandidate:
    code: str
    description: str
    head: str
    head_norm: str
    desc_terms: frozenset[str]
    terms: frozenset[str]
    canonical_terms: frozenset[str]


def norm_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").lower()).strip()


def norm_token(token: str) -> str:
    token = matcher.singular(token.lower().strip("'"))
    return matcher.TOKEN_SYNONYMS.get(token, token)


def tokenize_text(value: object) -> tuple[str, ...]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in TOKEN_RE.findall(norm_text(value)):
        tok = norm_token(raw)
        if len(tok) < 2 or tok in NOISE_TERMS:
            continue
        for expanded in (tok, *matcher.COMPOUND_TOKEN_EXPANSIONS.get(tok, ())):
            if expanded and expanded not in NOISE_TERMS and expanded not in seen:
                seen.add(expanded)
                out.append(expanded)
    return tuple(out)


def split_terms(value: object) -> set[str]:
    return {t for t in str(value or "").split() if t}


def top_counts(values: Iterable[str], limit: int = 12) -> str:
    counts = Counter(str(v).strip() for v in values if str(v).strip())
    return " | ".join(f"{k}:{v}" for k, v in counts.most_common(limit))


def top_value_and_share(values: Iterable[str]) -> tuple[str, int, float]:
    vals = [str(v).strip() for v in values if str(v).strip()]
    if not vals:
        return "", 0, 0.0
    value, count = Counter(vals).most_common(1)[0]
    return value, count, count / len(vals)


def sample_values(values: Iterable[str], limit: int = 8) -> str:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
        if len(out) >= limit:
            break
    return " || ".join(out)


def terms_summary(terms: Iterable[str], limit: int = 30) -> str:
    return " ".join(sorted({t for t in terms if t})[:limit])


def esha_head(description: str) -> str:
    return str(description or "").split(",", 1)[0].strip()


def load_canonical_terms(path: Path) -> dict[str, set[str]]:
    out: dict[str, set[str]] = defaultdict(set)
    if not path.exists():
        return out
    wanted = {
        "esha_code",
        "canonical_surface",
        "canonical_normalized",
        "canonical_shopping_item",
        "product_query",
        "esha_description",
    }
    with path.open(newline="", encoding="utf-8", errors="replace") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            code = str(row.get("esha_code") or "").strip()
            if not code or not code.isdigit():
                continue
            for col in wanted:
                out[code].update(tokenize_text(row.get(col, "")))
    return out


def load_esha_catalog(path: Path, canonical_path: Path) -> tuple[list[EshaCandidate], dict[str, EshaCandidate], dict[str, set[int]], dict[str, float]]:
    canonical_terms = load_canonical_terms(canonical_path)
    candidates: list[EshaCandidate] = []
    by_code: dict[str, EshaCandidate] = {}
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    for _, row in df.iterrows():
        code = str(row.get("EshaCode") or "").strip()
        desc = str(row.get("Description") or "").strip()
        if not code or not desc:
            continue
        head = esha_head(desc)
        terms = set(tokenize_text(desc)) | set(tokenize_text(head))
        c_terms = set(canonical_terms.get(code, set()))
        cand = EshaCandidate(
            code=code,
            description=desc,
            head=head,
            head_norm=policy.norm_head(head),
            desc_terms=frozenset(terms),
            terms=frozenset(terms | c_terms),
            canonical_terms=frozenset(c_terms),
        )
        by_code[code] = cand
        candidates.append(cand)

    postings: dict[str, set[int]] = defaultdict(set)
    for i, cand in enumerate(candidates):
        for term in cand.terms:
            postings[term].add(i)

    n = max(len(candidates), 1)
    idf = {term: 1.0 + math.log((n + 1) / (len(ids) + 1)) for term, ids in postings.items()}
    return candidates, by_code, postings, idf


def head_has_form_support(head_norm: str, evidence_terms: set[str], evidence_text: str) -> str:
    needed = FORM_SUPPORT.get(head_norm)
    if needed and not (evidence_terms & needed) and not any(t in evidence_text for t in needed):
        return f"head_without_product_form_support:{head_norm}"
    return ""


def fruit_state_conflict(
    candidate: EshaCandidate,
    ingredient_terms: set[str],
    title_terms: set[str],
    category_text: str,
    evidence_text: str,
) -> str:
    if candidate.head_norm not in FRESH_SINGLE_FRUIT_HEADS:
        return ""

    cand_text = norm_text(candidate.description)
    product_terms = ingredient_terms | title_terms
    function_hits = product_terms & FUNCTION_TERMS

    # Dried/frozen/canned fruit can map to a fruit head only if the ESHA text has
    # the same state. This keeps dried mango away from raw/fresh mango and away
    # from flavor-only codes.
    if "dried" in product_terms or "dry" in product_terms:
        if "dried" not in cand_text and "dry" not in cand_text:
            return "fruit_state_mismatch:dried_product_to_non_dried_fruit"
    if "frozen" in product_terms and "frozen" not in cand_text:
        return "fruit_state_mismatch:frozen_product_to_non_frozen_fruit"
    if "canned" in product_terms and "canned" not in cand_text:
        return "fruit_state_mismatch:canned_product_to_non_canned_fruit"

    processed_ok = any(t in cand_text for t in ("sauce", "applesauce", "juice", "cider", "nectar", "dried", "frozen", "canned", "pie"))
    produce_context = any(
        term in category_text
        for term in (
            "pre-packaged fruit",
            "frozen fruit",
            "canned fruit",
            "fruit prepared",
            "wholesome snacks",
            "fruit & vegetable",
        )
    )
    if function_hits and not processed_ok:
        return "single_fruit_head_on_processed_product:" + ",".join(sorted(function_hits)[:6])
    if not produce_context and not processed_ok and function_hits:
        return "single_fruit_head_without_produce_context"
    return ""


def bean_conflict(candidate: EshaCandidate, evidence_terms: set[str], evidence_text: str) -> str:
    if candidate.head_norm not in {"beans", "baked beans", "refried beans", "beans rice", "beans and rice"}:
        return ""
    if "vanilla bean" in evidence_text:
        return "vanilla_bean_flavor_to_bean_code"
    if "bean" not in evidence_terms and "beans" not in evidence_terms and "bean" not in evidence_text:
        return "bean_head_without_bean_evidence"

    product_subtypes = self_heal.bean_subtypes_from_text(evidence_text, evidence_terms)
    candidate_subtypes = self_heal.bean_subtypes_from_text(norm_text(candidate.description), set(candidate.desc_terms))
    if product_subtypes and candidate_subtypes and not (product_subtypes & candidate_subtypes):
        return "bean_subtype_mismatch:" + ",".join(sorted(product_subtypes)) + "!=" + ",".join(sorted(candidate_subtypes))
    return ""


def component_conflict(candidate: EshaCandidate, evidence_terms: set[str]) -> str:
    candidate_components = set(candidate.desc_terms) & COMPONENT_TERMS
    if not candidate_components:
        return ""

    # Heads like Mango or Beans are themselves the component. Do not require
    # every descriptor token, only extra components that change the food.
    head_terms = set(tokenize_text(candidate.head))
    extra_components = candidate_components - head_terms
    harmless = {"food", "prepared", "raw", "fresh", "cooked", "dry", "dried", "frozen", "canned"}
    extra_components -= harmless

    # Enforce a small set of components that caused real observed failures.
    required = extra_components & {
        "potato",
        "potatoes",
        "chicken",
        "beef",
        "pork",
        "turkey",
        "bacon",
        "rice",
        "noodle",
        "noodles",
        "pasta",
        "cheese",
        "milk",
        "cream",
        "bean",
        "beans",
    }
    missing = sorted(t for t in required if t not in evidence_terms)
    if missing:
        return "candidate_extra_components_absent:" + ",".join(missing[:8])
    return ""


def category_component_conflict(
    candidate: EshaCandidate,
    *,
    dominant_category: str,
    ingredient_terms: set[str],
    title_terms: set[str],
) -> str:
    category = norm_text(dominant_category)
    head = candidate.head_norm
    cand_terms = set(candidate.terms)
    cand_desc_terms = set(candidate.desc_terms)
    evidence_terms = ingredient_terms | title_terms
    head_terms = set(tokenize_text(candidate.head))

    product_meat_species = evidence_terms & MEAT_SPECIES_TERMS
    candidate_meat_species = (cand_desc_terms | head_terms) & MEAT_SPECIES_TERMS
    if product_meat_species and candidate_meat_species and not (product_meat_species & candidate_meat_species):
        return "meat_species_mismatch:" + ",".join(sorted(product_meat_species)) + "!=" + ",".join(sorted(candidate_meat_species))

    if "pepperoni" in category or "salami" in category or "cold cuts" in category:
        if "raw" in cand_desc_terms or cand_desc_terms & {"steak", "tenderloin", "loin", "bones"}:
            return f"category_head_mismatch:cold_cuts_raw_meat:{candidate.head}"

    if "vegetable & cooking oils" in category:
        if head != "oil":
            return f"category_head_mismatch:vegetable_oils:{candidate.head}"

    if category == "milk" or "milk/milk substitutes" in category:
        if head != "milk":
            return f"category_head_mismatch:milk:{candidate.head}"
        if "evaporated" in cand_terms and "evaporated" not in evidence_terms:
            return "milk_state_mismatch:evaporated_without_product_evidence"
        if "condensed" in cand_terms and "condensed" not in evidence_terms:
            return "milk_state_mismatch:condensed_without_product_evidence"

    if category == "cheese" and not (("cream" in evidence_terms or "creme" in evidence_terms) and "cheese" not in evidence_terms):
        if "cheese" not in head:
            return f"category_head_mismatch:cheese:{candidate.head}"

    if "pasta by shape" in category or category == "all noodles":
        if head not in {"pasta", "noodles", "macaroni"}:
            return f"category_head_mismatch:dry_pasta:{candidate.head}"

    if category == "tomatoes":
        if "tomato" not in cand_desc_terms and "tomatoes" not in cand_desc_terms:
            return f"category_head_mismatch:tomatoes:{candidate.head}"
        if head in {"chile pepper", "pepper", "peppers"}:
            return "tomato_category_to_pepper_code"

    if "ketchup" in category or "mustard" in category or "bbq" in category or "cheese sauce" in category:
        if evidence_terms & {"tomato", "ketchup", "catsup"}:
            if not (cand_desc_terms & {"tomato", "ketchup", "catsup", "sauce"} or head in {"catsup", "ketchup", "sauce", "tomato sauce"}):
                return f"category_head_mismatch:ketchup_sauce:{candidate.head}"

    if "salad dressing" in category or "mayonnaise" in category:
        product_dressing_terms = evidence_terms & DRESSING_IDENTITY_TERMS
        candidate_dressing_terms = cand_desc_terms & DRESSING_IDENTITY_TERMS
        if product_dressing_terms and candidate_dressing_terms and not (product_dressing_terms & candidate_dressing_terms):
            return "dressing_identity_mismatch:" + ",".join(sorted(product_dressing_terms)) + "!=" + ",".join(sorted(candidate_dressing_terms))
        if "mustard" in product_dressing_terms and "mustard" not in cand_desc_terms:
            return "dressing_identity_mismatch:mustard_absent"
        if "ranch" in product_dressing_terms and "ranch" not in cand_desc_terms:
            return "dressing_identity_mismatch:ranch_absent"

    if "canned seafood" in category or "fish & seafood" in category or "frozen fish" in category:
        if head not in {"fish", "seafood", "shellfish", "tuna", "salmon", "sardines", "mackerel", "shrimp", "crab", "clam", "clams", "oyster", "oysters"}:
            return f"category_head_mismatch:seafood:{candidate.head}"
        product_seafood_terms = evidence_terms & SEAFOOD_TERMS
        candidate_seafood_terms = cand_desc_terms & SEAFOOD_TERMS
        if product_seafood_terms and candidate_seafood_terms and not (product_seafood_terms & candidate_seafood_terms):
            return "seafood_identity_mismatch:" + ",".join(sorted(product_seafood_terms)) + "!=" + ",".join(sorted(candidate_seafood_terms))
        if product_seafood_terms and not candidate_seafood_terms:
            return "seafood_identity_absent:" + ",".join(sorted(product_seafood_terms))

    if "canned vegetables" in category:
        vegetable_terms = evidence_terms & (matcher.VEGETABLES | matcher.LEGUMES | {"bean", "beans", "pea", "peas", "tomato", "tomatoes"})
        if vegetable_terms and not (cand_desc_terms & vegetable_terms):
            return "canned_vegetable_component_mismatch:" + ",".join(sorted(vegetable_terms)[:8])

    if "dried" in evidence_terms or "dry" in evidence_terms or "dehydrated" in evidence_terms or "freeze" in evidence_terms:
        fruit_terms = evidence_terms & FRUIT_TERMS
        if fruit_terms:
            if head in {"bar", "cake", "candy", "cereal", "chips", "cookie", "cracker", "ice cream", "juice", "juice drink", "muffin", "pretzels", "seeds", "snack", "spice", "herb"}:
                return f"dried_fruit_cluster_to_non_fruit_head:{candidate.head}"
            if "dried" not in cand_desc_terms and "dry" not in cand_desc_terms and "dried" not in norm_text(candidate.description):
                return "dried_fruit_cluster_to_non_dried_candidate"
            if not (cand_desc_terms & fruit_terms):
                return "dried_fruit_component_mismatch:" + ",".join(sorted(fruit_terms)[:8])

    return ""


def candidate_reject_reason(
    candidate: EshaCandidate,
    *,
    dominant_category: str,
    representative_description: str,
    ingredient_terms: set[str],
    title_terms: set[str],
    lane_terms: set[str],
    form_terms: set[str],
) -> str:
    evidence_terms = ingredient_terms | title_terms | lane_terms | form_terms
    evidence_text = " ".join(sorted(evidence_terms)) + " " + norm_text(representative_description)
    category_text = norm_text(dominant_category)

    ok, reason = policy.category_allows_head(
        category=dominant_category,
        product_description=representative_description,
        title_tokens=title_terms,
        candidate_head=candidate.head,
    )
    if not ok:
        return reason

    narrow = policy.narrow_head_requires_title_support(candidate.head, title_terms, representative_description)
    if narrow:
        return narrow

    form_reason = head_has_form_support(candidate.head_norm, evidence_terms, evidence_text)
    if form_reason:
        return form_reason

    if candidate.head_norm in {"meal", "dish"}:
        missing = self_heal.missing_meal_components(candidate.description, evidence_terms)
        if missing:
            return "meal_extra_components_absent:" + ",".join(sorted(missing)[:8])

    if candidate.head_norm == "butter" and ("popcorn" in evidence_terms or "popcorn" in category_text):
        if "popcorn" not in norm_text(candidate.description):
            return "popcorn_product_to_plain_butter"

    if candidate.head_norm in {"pasta", "noodles", "macaroni"}:
        if dominant_category not in DRY_PASTA_CATEGORIES and evidence_terms & {"meal", "dinner", "entree", "sauce", "cheese", "chicken", "beef"}:
            if "dish" not in norm_text(candidate.description) and "meal" not in norm_text(candidate.description):
                return "dry_pasta_head_on_prepared_product"

    fruit_reason = fruit_state_conflict(candidate, ingredient_terms, title_terms, category_text, evidence_text)
    if fruit_reason:
        return fruit_reason

    bean_reason = bean_conflict(candidate, evidence_terms, evidence_text)
    if bean_reason:
        return bean_reason

    component_reason = component_conflict(candidate, evidence_terms)
    if component_reason:
        return component_reason

    category_component_reason = category_component_conflict(
        candidate,
        dominant_category=dominant_category,
        ingredient_terms=ingredient_terms,
        title_terms=title_terms,
    )
    if category_component_reason:
        return category_component_reason

    return ""


def score_candidate(
    candidate: EshaCandidate,
    *,
    ingredient_terms: set[str],
    title_terms: set[str],
    lane_terms: set[str],
    form_terms: set[str],
    current_support: float,
    idf: dict[str, float],
) -> tuple[float, str] | None:
    candidate_terms = set(candidate.terms)
    ingredient_overlap = ingredient_terms & candidate_terms
    title_overlap = title_terms & candidate_terms
    form_overlap = form_terms & candidate_terms
    lane_overlap = lane_terms & candidate_terms

    if not ingredient_overlap and not title_overlap and current_support <= 0:
        return None

    score = 0.0
    score += sum(idf.get(t, 1.0) for t in ingredient_overlap) * 3.0
    score += sum(idf.get(t, 1.0) for t in title_overlap) * 1.3
    score += len(form_overlap) * 2.5
    score += len(lane_overlap) * 0.7
    score += current_support * 8.0

    if candidate.canonical_terms and (set(candidate.canonical_terms) & (ingredient_terms | title_terms)):
        score += 2.0

    reason = (
        f"ingredient_hits={len(ingredient_overlap)};"
        f"title_hits={len(title_overlap)};"
        f"form_hits={len(form_overlap)};"
        f"lane_hits={len(lane_overlap)};"
        f"current_support={current_support:.3f}"
    )
    return score, reason


def candidate_indices_for_terms(
    terms: set[str],
    postings: dict[str, set[int]],
    *,
    max_posting_size: int,
) -> set[int]:
    out: set[int] = set()
    for term in terms:
        ids = postings.get(term)
        if not ids or len(ids) > max_posting_size:
            continue
        out.update(ids)
    return out


def build_cluster_proposals(
    members: pd.DataFrame,
    clusters: pd.DataFrame,
    candidates: list[EshaCandidate],
    by_code: dict[str, EshaCandidate],
    postings: dict[str, set[int]],
    idf: dict[str, float],
    *,
    min_size: int,
    min_category_share: float,
    max_posting_size: int,
    max_clusters: int | None = None,
) -> pd.DataFrame:
    code_to_idx = {cand.code: i for i, cand in enumerate(candidates)}
    eligible = clusters[clusters["n_products"].astype(int) >= min_size].copy()
    if min_category_share > 0 and "category_top_share" in eligible.columns:
        eligible = eligible[eligible["category_top_share"].astype(float) >= min_category_share]
    eligible_ids = set(eligible["ingredient_cluster_id"].astype(str))
    work = members[members["ingredient_cluster_id"].astype(str).isin(eligible_ids)].copy()
    rows: list[dict[str, object]] = []
    processed = 0
    for cluster_id, group in work.groupby("ingredient_cluster_id", sort=False):
        processed += 1
        if max_clusters and processed > max_clusters:
            break
        if processed % 5000 == 0:
            print(f"  processed {processed:,} clusters", flush=True)

        n = len(group)
        ingredient_signature = str(group["ingredient_signature"].iloc[0])
        ingredient_terms = split_terms(ingredient_signature)
        dominant_category, dominant_category_count, category_share = top_value_and_share(group["branded_food_category"])
        dominant_brand, dominant_brand_count, brand_share = top_value_and_share(group["brand_name"])
        dominant_desc = str(group["product_description"].iloc[0])

        title_counter: Counter[str] = Counter()
        for text in group["product_description"].head(100):
            title_counter.update(tokenize_text(text))
        title_terms = {t for t, c in title_counter.most_common(40) if c >= 1 and t not in NOISE_TERMS}

        lane = self_heal.category_lane_for(dominant_desc, dominant_category, title_terms)
        form = self_heal.product_form_for(dominant_desc, dominant_category, lane, title_terms)
        lane_share = 1.0
        form_share = 1.0
        lane_terms = set(str(lane).replace("_", " ").split())
        form_terms = set(str(form).replace("_", " ").split())

        current_code, current_code_count, current_code_share = top_value_and_share(group.get("map_esha_code", pd.Series(dtype=str)))
        current_head, _, current_head_share = top_value_and_share(group.get("map_esha_head", pd.Series(dtype=str)))
        current_desc = ""
        if current_code:
            descs = group.loc[group["map_esha_code"].astype(str) == current_code, "map_esha_description"]
            current_desc = str(descs.iloc[0]) if len(descs) else ""
        current_support_by_code = Counter(str(v) for v in group.get("map_esha_code", pd.Series(dtype=str)) if str(v).strip())

        evidence_terms = ingredient_terms | title_terms | lane_terms | form_terms
        candidate_ids = candidate_indices_for_terms(evidence_terms, postings, max_posting_size=max_posting_size)
        for code in current_support_by_code:
            idx = code_to_idx.get(code)
            if idx is not None:
                candidate_ids.add(idx)

        scored: list[tuple[float, EshaCandidate, str]] = []
        rejects: Counter[str] = Counter()
        for idx in candidate_ids:
            cand = candidates[idx]
            reject = candidate_reject_reason(
                cand,
                dominant_category=dominant_category,
                representative_description=dominant_desc,
                ingredient_terms=ingredient_terms,
                title_terms=title_terms,
                lane_terms=lane_terms,
                form_terms=form_terms,
            )
            if reject:
                rejects[reject] += 1
                continue
            current_support = current_support_by_code.get(cand.code, 0) / n
            score = score_candidate(
                cand,
                ingredient_terms=ingredient_terms,
                title_terms=title_terms,
                lane_terms=lane_terms,
                form_terms=form_terms,
                current_support=current_support,
                idf=idf,
            )
            if score:
                scored.append((score[0], cand, score[1]))

        scored.sort(key=lambda item: (item[0], item[1].code), reverse=True)
        top = scored[0] if scored else None
        runner = scored[1] if len(scored) > 1 else None
        margin = (top[0] - runner[0]) if top and runner else (top[0] if top else 0.0)

        current_reject = ""
        if current_code and current_code in by_code:
            current_reject = candidate_reject_reason(
                by_code[current_code],
                dominant_category=dominant_category,
                representative_description=dominant_desc,
                ingredient_terms=ingredient_terms,
                title_terms=title_terms,
                lane_terms=lane_terms,
                form_terms=form_terms,
            )

        proposal_status = "no_compatible_candidate"
        proposed_code = proposed_desc = proposed_head = proposal_reason = ""
        proposal_score = 0.0
        if top:
            proposal_score, cand, proposal_reason = top
            proposed_code = cand.code
            proposed_desc = cand.description
            proposed_head = cand.head
            if current_code and current_reject == "" and current_code_share >= 0.25:
                current = by_code.get(current_code)
                proposal_status = "current_code_supported"
                proposed_code = current_code
                proposed_desc = current.description if current else current_desc
                proposed_head = current.head if current else current_head
                proposal_reason = f"kept_vM_incumbent;current_code_share={current_code_share:.3f}"
                proposal_score = max(proposal_score, current_code_share * 100.0)
            elif current_code and proposed_code == current_code and current_reject == "":
                proposal_status = "current_code_supported"
            elif current_reject:
                proposal_status = "current_code_rejected_proposed_replacement"
            elif current_code and current_reject == "" and map_code_count >= 4:
                proposal_status = "cluster_needs_subsplit_review"
                proposed_code = ""
                proposed_desc = ""
                proposed_head = ""
                proposal_reason = (
                    f"ingredient_cluster_too_broad_for_auto_replacement;"
                    f"current_code_share={current_code_share:.3f};"
                    f"current_code_count={map_code_count}"
                )
            elif category_share >= 0.8 and margin >= 2.0:
                proposal_status = "evidence_first_candidate"
            else:
                proposal_status = "ambiguous_candidate"
        elif current_reject:
            proposal_status = "current_code_rejected_no_replacement"

        map_code_count = int(group.get("map_esha_code", pd.Series(dtype=str)).astype(str).replace("", pd.NA).dropna().nunique())
        map_head_count = int(group.get("map_esha_head", pd.Series(dtype=str)).astype(str).replace("", pd.NA).dropna().nunique())

        rows.append(
            {
                "ingredient_cluster_id": cluster_id,
                "n_products": n,
                "ingredient_signature": ingredient_signature,
                "ingredient_terms": terms_summary(ingredient_terms, 50),
                "dominant_category": dominant_category,
                "category_top_share": round(category_share, 4),
                "category_count": int(group["branded_food_category"].astype(str).replace("", pd.NA).dropna().nunique()),
                "top_categories": top_counts(group["branded_food_category"], 12),
                "dominant_brand": dominant_brand,
                "brand_top_share": round(brand_share, 4),
                "brand_count": int(group["brand_name"].astype(str).replace("", pd.NA).dropna().nunique()),
                "top_brands": top_counts(group["brand_name"], 12),
                "dominant_lane": lane,
                "lane_top_share": round(lane_share, 4),
                "dominant_form": form,
                "form_top_share": round(form_share, 4),
                "title_terms": terms_summary(title_terms, 50),
                "current_top_code": current_code,
                "current_top_description": current_desc,
                "current_top_head": current_head,
                "current_code_top_share": round(current_code_share, 4),
                "current_head_top_share": round(current_head_share, 4),
                "current_code_count": map_code_count,
                "current_head_count": map_head_count,
                "current_reject_reason": current_reject,
                "proposal_status": proposal_status,
                "proposed_esha_code": proposed_code,
                "proposed_esha_description": proposed_desc,
                "proposed_esha_head": proposed_head,
                "proposal_score": round(proposal_score, 4),
                "proposal_margin": round(margin, 4),
                "proposal_reason": proposal_reason,
                "top_candidates": " | ".join(
                    f"{cand.code}:{cand.description}({score:.2f};{reason})"
                    for score, cand, reason in scored[:8]
                ),
                "top_reject_reasons": " | ".join(f"{k}:{v}" for k, v in rejects.most_common(8)),
                "sample_products": sample_values(group["product_description"], 10),
            }
        )
    return pd.DataFrame(rows)


def conflict_subset(proposals: pd.DataFrame) -> pd.DataFrame:
    if proposals.empty:
        return proposals
    current_rejected = proposals["current_reject_reason"].astype(str).str.strip() != ""
    map_scatter = (
        (proposals["n_products"].astype(int) >= 5)
        & (proposals["category_top_share"].astype(float) >= 0.8)
        & (proposals["current_code_count"].astype(int) >= 4)
    )
    changed = (
        proposals["proposed_esha_code"].astype(str).str.strip().ne("")
        & proposals["current_top_code"].astype(str).str.strip().ne("")
        & (proposals["proposed_esha_code"].astype(str) != proposals["current_top_code"].astype(str))
        & (proposals["proposal_status"].isin(["current_code_rejected_proposed_replacement", "evidence_first_candidate"]))
    )
    no_candidate = proposals["proposal_status"].eq("current_code_rejected_no_replacement")
    return proposals[current_rejected | map_scatter | changed | no_candidate].copy()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--members", type=Path, default=DEFAULT_MEMBERS)
    parser.add_argument("--clusters", type=Path, default=DEFAULT_CLUSTERS)
    parser.add_argument("--esha", type=Path, default=ESHA_CSV)
    parser.add_argument("--canonical", type=Path, default=CANONICAL_CSV)
    parser.add_argument("--out", type=Path, default=OUT_PROPOSALS)
    parser.add_argument("--conflicts", type=Path, default=OUT_CONFLICTS)
    parser.add_argument("--summary", type=Path, default=OUT_SUMMARY)
    parser.add_argument("--min-size", type=int, default=5)
    parser.add_argument(
        "--min-category-share",
        type=float,
        default=0.8,
        help="Start with coherent ingredient clusters; set 0 for the full cluster set.",
    )
    parser.add_argument("--max-posting-size", type=int, default=2500)
    parser.add_argument("--max-clusters", type=int, default=0)
    args = parser.parse_args()

    print("loading ESHA candidate catalog", flush=True)
    candidates, by_code, postings, idf = load_esha_catalog(args.esha, args.canonical)
    print(f"  ESHA candidates: {len(candidates):,}; indexed terms: {len(postings):,}", flush=True)

    print("loading ingredient-only clusters", flush=True)
    clusters = pd.read_csv(args.clusters, dtype=str, keep_default_na=False, low_memory=False)
    eligible = clusters[clusters["n_products"].astype(int) >= args.min_size].copy()
    if args.min_category_share > 0 and "category_top_share" in eligible.columns:
        eligible = eligible[eligible["category_top_share"].astype(float) >= args.min_category_share]
    eligible_ids = set(eligible["ingredient_cluster_id"].astype(str))
    print(
        f"  eligible clusters >= {args.min_size} and category_share >= {args.min_category_share}: {len(eligible_ids):,}",
        flush=True,
    )

    print("loading ingredient-only members", flush=True)
    members = pd.read_csv(args.members, dtype=str, keep_default_na=False, low_memory=False)
    members = members[members["ingredient_cluster_id"].astype(str).isin(eligible_ids)].copy()
    proposals = build_cluster_proposals(
        members,
        clusters,
        candidates,
        by_code,
        postings,
        idf,
        min_size=args.min_size,
        min_category_share=args.min_category_share,
        max_posting_size=args.max_posting_size,
        max_clusters=args.max_clusters or None,
    )
    proposals = proposals.sort_values(
        ["proposal_status", "n_products", "category_top_share", "proposal_score"],
        ascending=[True, False, False, False],
    )
    conflicts = conflict_subset(proposals).sort_values(
        ["n_products", "category_top_share", "current_code_count"],
        ascending=[False, False, False],
    )

    proposals.to_csv(args.out, index=False)
    conflicts.to_csv(args.conflicts, index=False)

    summary = {
        "members": str(args.members),
        "clusters": str(args.clusters),
        "output": str(args.out),
        "conflicts": str(args.conflicts),
        "min_size": args.min_size,
        "min_category_share": args.min_category_share,
        "clusters_evaluated": int(len(proposals)),
        "products_in_evaluated_clusters": int(proposals["n_products"].astype(int).sum()) if not proposals.empty else 0,
        "conflict_clusters": int(len(conflicts)),
        "status_counts": proposals["proposal_status"].value_counts().to_dict() if not proposals.empty else {},
        "current_rejected_clusters": int((proposals["current_reject_reason"].astype(str).str.strip() != "").sum()) if not proposals.empty else 0,
        "current_code_scatter_clusters": int(((proposals["n_products"].astype(int) >= 5) & (proposals["category_top_share"].astype(float) >= 0.8) & (proposals["current_code_count"].astype(int) >= 4)).sum()) if not proposals.empty else 0,
        "top_conflicts": conflicts.head(25)[
            [
                "n_products",
                "ingredient_signature",
                "dominant_category",
                "category_top_share",
                "current_top_code",
                "current_top_description",
                "current_reject_reason",
                "proposed_esha_code",
                "proposed_esha_description",
                "proposal_status",
                "sample_products",
            ]
        ].to_dict(orient="records") if not conflicts.empty else [],
    }
    args.summary.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
