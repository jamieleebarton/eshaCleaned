from __future__ import annotations

import hashlib
import re
from collections import Counter
from pathlib import Path
from typing import Iterable

import pandas as pd

import build_ingredient_fingerprint_clusters as ingredient_clusters
import match_esha_to_products as matcher
import self_heal_common as self_heal
import self_heal_policy as policy


ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "implementation" / "output"

ESHA_SPINE_CSV = OUT_DIR / "esha_spine.csv"
PRODUCT_CLUSTERS_CSV = OUT_DIR / "product_evidence_clusters_v2.csv"
PRODUCT_CLUSTER_MEMBERS_CSV = OUT_DIR / "product_evidence_cluster_members_v2.csv"
CLUSTER_ASSIGNMENTS_CSV = OUT_DIR / "cluster_to_esha_assignments.csv"
CLUSTER_PROJECTION_CSV = OUT_DIR / "product_to_best_esha_full_map.vCluster.csv"
CLUSTER_VALIDATION_CSV = OUT_DIR / "cluster_assignment_validation.csv"
CLUSTER_GRAPH_NODES_CSV = OUT_DIR / "cluster_graph_nodes.csv"
CLUSTER_GRAPH_EDGES_CSV = OUT_DIR / "cluster_graph_edges.csv"
CLUSTER_GRAPH_HTML = OUT_DIR / "cluster_taxonomy_conflict_map.html"


FOOD_DOMAINS = (
    matcher.SEAFOOD
    | matcher.POULTRY
    | matcher.MEATS
    | matcher.LEGUMES
    | matcher.NUTS_SEEDS
    | matcher.VEGETABLES
    | matcher.FRUITS
    | matcher.GRAINS
    | {
        "milk", "cream", "creamer", "cheese", "yogurt", "butter", "egg",
        "coffee", "tea", "juice", "water", "soda", "soup", "chili",
        "sauce", "dressing", "dip", "salsa", "hummus", "pasta", "noodle",
        "noodles", "macaroni", "spaghetti", "rice", "flour", "sugar",
        "syrup", "honey", "popcorn", "pretzel", "pretzels", "chip", "chips",
        "cookie", "cookies", "cake", "muffin", "doughnut", "donut", "bagel",
        "bread", "bar", "cereal", "granola", "oatmeal", "pizza", "bacon",
        "sausage", "sandwich", "wrap", "burrito", "taco", "tamale",
        "potato", "potatoes",
    }
)

FORM_IDENTITY_TERMS = {
    "mashed", "refried", "baked", "fried", "frozen", "canned", "dry",
    "dried", "roasted", "raw", "sliced", "whole", "cut", "french",
    "instant", "powder", "powdered", "creamy", "crunchy", "light",
    "plain", "original", "sweetened", "unsweetened", "salted", "unsalted",
}

INGREDIENT_CORE_DROP = (
    ingredient_clusters.INGREDIENT_STOPWORDS
    | {
        "water", "salt", "sugar", "oil", "oils", "natural", "flavor",
        "flavors", "spice", "spices", "extract", "extracts", "citric",
        "acid", "ascorbic", "calcium", "chloride", "xanthan", "gum",
        "guar", "lecithin", "starch", "modified", "dextrose", "maltodextrin",
        "color", "colored", "contains", "less", "percent",
    }
)


def norm_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").lower()).strip()


def norm_head(value: object) -> str:
    return policy.norm_head(value)


def split_terms(value: object) -> tuple[str, ...]:
    return tuple(t for t in str(value or "").split() if t)


def esha_head(description: str) -> str:
    return str(description or "").split(",", 1)[0].strip()


def cluster_id_for(parts: Iterable[object]) -> str:
    payload = "\t".join(str(p or "") for p in parts).encode("utf-8")
    return hashlib.sha1(payload).hexdigest()[:18]


def top_counts(values: Iterable[str], limit: int = 12) -> str:
    counts = Counter(v for v in values if v)
    return " | ".join(f"{k}:{v}" for k, v in counts.most_common(limit))


def terms_join(values: Iterable[str], limit: int = 80) -> str:
    return " ".join(sorted({v for v in values if v})[:limit])


def bean_subtypes(tokens: set[str], text: str) -> set[str]:
    return self_heal.bean_subtypes_from_text(text, tokens)


def subtype_keys(tokens: set[str], text: str) -> set[str]:
    out: set[str] = set()
    out |= {f"bean:{s}" for s in bean_subtypes(tokens, text)}
    if ("mashed" in tokens or "mash" in tokens) and (tokens & {"potato", "potatoes"}):
        out.add("potato:mashed")
    if "hash" in tokens and (tokens & {"brown", "browns", "potato", "potatoes"}):
        out.add("potato:hash_brown")
    if "popcorn" in tokens or "popcorn" in text:
        out.add("snack:popcorn")
    if tokens & {"pasta", "noodle", "noodles", "spaghetti", "macaroni", "penne", "rigatoni", "fettuccine"}:
        out.add("grain:pasta")
    if "vanilla bean" in text:
        out.add("flavor:vanilla_bean")
    if "butter bean" in text or "butter beans" in text or "lima bean" in text or "lima beans" in text:
        out.add("bean:butter")
    return out


def title_identity_terms(title_tokens: Iterable[str], lane: str, form: str, primary: str) -> tuple[str, ...]:
    tokens = set(title_tokens)
    keep = set(tokens & FOOD_DOMAINS)
    keep |= set(tokens & FORM_IDENTITY_TERMS)
    if primary:
        keep.add(primary)
    if form:
        keep.update(t for t in form.split("_") if t)
    if lane:
        keep.update(t for t in lane.split("_") if t and t not in {"and", "other"})
    keep -= ingredient_clusters.TITLE_NOISE
    keep -= {"food", "foods", "product", "products", "style", "type", "original", "classic"}
    return tuple(sorted(t for t in keep if len(t) > 1))


def ingredient_core_terms(ingredient_tokens: Iterable[str], title_terms: Iterable[str], primary: str) -> tuple[str, ...]:
    ing = set(ingredient_tokens)
    title = set(title_terms)
    keep: set[str] = set()
    for token in ing:
        if token in INGREDIENT_CORE_DROP:
            continue
        if token in FOOD_DOMAINS or token in title or token in FORM_IDENTITY_TERMS:
            keep.add(token)
    if primary:
        keep.add(primary)
    return tuple(sorted(t for t in keep if len(t) > 1))


def state_bucket(state_lane: str) -> str:
    states = set(str(state_lane or "").split("+"))
    if "frozen" in states:
        return "frozen"
    if "canned" in states:
        return "canned"
    if "dry" in states or "dried" in states or "powder" in states:
        return "dry"
    if "fresh" in states or "raw" in states:
        return "fresh"
    return "generic"


def candidate_text_terms(description: str) -> set[str]:
    return set(ingredient_clusters.title_tokens(description)) | set(matcher.tokens_for(description))


def load_spine(path: Path = ESHA_SPINE_CSV) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, keep_default_na=False, low_memory=False)


def load_clusters(path: Path = PRODUCT_CLUSTERS_CSV) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, keep_default_na=False, low_memory=False)


def load_cluster_members(path: Path = PRODUCT_CLUSTER_MEMBERS_CSV) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, keep_default_na=False, low_memory=False)


def cluster_tokens(row: pd.Series) -> set[str]:
    out: set[str] = set()
    for col in (
        "title_identity_terms",
        "ingredient_core_terms",
        "dominant_title_tokens",
        "primary_food",
        "state_bucket",
        "product_form",
        "category_lane",
        "subtype_keys",
    ):
        out |= set(split_terms(row.get(col, "")))
    return {t for t in out if t and t != "generic"}


def hard_reject_cluster_candidate(cluster: pd.Series, candidate: pd.Series) -> str:
    head = str(candidate.get("esha_head") or "")
    head_norm = norm_head(head)
    title_terms = set(split_terms(cluster.get("dominant_title_tokens", ""))) | set(split_terms(cluster.get("title_identity_terms", "")))
    category = str(cluster.get("dominant_category") or "")
    desc = str(cluster.get("dominant_product_description") or "")
    ok, reason = policy.category_allows_head(
        category=category,
        product_description=desc,
        title_tokens=title_terms,
        candidate_head=head,
    )
    if not ok:
        return reason
    narrow_reason = policy.narrow_head_requires_title_support(head, title_terms, desc)
    if narrow_reason:
        return narrow_reason

    form = str(cluster.get("product_form") or "")
    c_tokens = cluster_tokens(cluster)
    cand_terms = set(split_terms(candidate.get("meaningful_terms", ""))) | set(split_terms(candidate.get("identity_terms", "")))
    cand_text = norm_text(candidate.get("esha_description", ""))
    product_text = norm_text(desc)

    if form in {"pasta", "noodles"} and head_norm not in {"pasta", "noodles", "macaroni"}:
        return f"dry_pasta_to_non_pasta_head:{head}"
    if form == "mashed_potatoes" and head_norm != "mashed potatoes":
        return f"mashed_potatoes_to_non_mashed_head:{head}"
    if form == "popcorn" and head_norm not in {"popcorn", "butter"}:
        return f"popcorn_to_non_popcorn_head:{head}"
    if form == "popcorn" and head_norm == "butter" and "popcorn" not in cand_text:
        return "popcorn_to_plain_butter"
    if form == "green_beans":
        if head_norm not in {"beans", "vegetables", "snap beans"}:
            return f"green_beans_to_wrong_head:{head}"
        if not ({"green", "snap", "string"} & cand_terms or "green bean" in cand_text or "snap bean" in cand_text):
            return "green_beans_to_wrong_bean_subtype"
    if form in {"beans", "baked_beans", "refried_beans"} and head_norm not in {
        "beans", "baked beans", "refried beans", "pork and beans", "beans rice", "beans and rice"
    }:
        return f"bean_cluster_to_non_bean_head:{head}"

    product_subtypes = bean_subtypes(c_tokens, product_text)
    candidate_subtypes = bean_subtypes(cand_terms, cand_text)
    if product_subtypes and candidate_subtypes and not (product_subtypes & candidate_subtypes):
        return "bean_subtype_mismatch:" + ",".join(sorted(product_subtypes)) + "!=" + ",".join(sorted(candidate_subtypes))
    if "flavor:vanilla_bean" in set(split_terms(cluster.get("subtype_keys", ""))) and head_norm in {"beans", "baked beans"}:
        return "vanilla_bean_flavor_to_bean_code"

    if head_norm in {"meal", "dish"}:
        missing = self_heal.missing_meal_components(str(candidate.get("esha_description") or ""), c_tokens)
        if missing:
            return "meal_extra_components_absent:" + ",".join(sorted(missing))
    return ""


def score_cluster_candidate(cluster: pd.Series, candidate: pd.Series, idf: dict[str, float] | None = None) -> tuple[float, str] | None:
    reject = hard_reject_cluster_candidate(cluster, candidate)
    if reject:
        return None
    idf = idf or {}
    evidence = cluster_tokens(cluster)
    identity = set(split_terms(candidate.get("identity_terms", "")))
    meaningful = set(split_terms(candidate.get("meaningful_terms", "")))
    candidate_subtypes = set(split_terms(candidate.get("subtype_keys", "")))
    cluster_subtypes = set(split_terms(cluster.get("subtype_keys", "")))
    head = str(candidate.get("esha_head") or "")
    target_heads = str(cluster.get("target_heads") or "").split("|")

    identity_hits = evidence & identity
    meaningful_hits = evidence & meaningful
    subtype_hits = cluster_subtypes & candidate_subtypes
    extra_identity = identity - evidence - {"dry", "prepared", "cooked", "fs", "serving"}
    score = 0.0
    score += 24.0 if policy.head_matches_targets(target_heads, head) else 0.0
    score += 6.0 * len(identity_hits)
    score += 3.0 * len(meaningful_hits)
    score += 8.0 * len(subtype_hits)
    score += sum(idf.get(t, 1.0) for t in meaningful_hits)
    try:
        support = int(float(candidate.get("category_support") or 0))
    except ValueError:
        support = 0
    score += min(4.0, support ** 0.5 / 10.0)
    score -= 2.0 * len(extra_identity)
    if str(candidate.get("needs_fix") or "") == "1":
        score -= 4.0
    if not identity_hits and not meaningful_hits:
        return None
    if len(extra_identity) >= 5:
        return None
    reason = (
        f"head={head};identity_hits={len(identity_hits)};"
        f"meaningful_hits={len(meaningful_hits)};subtype_hits={len(subtype_hits)};"
        f"extra_identity={len(extra_identity)}"
    )
    return score, reason
