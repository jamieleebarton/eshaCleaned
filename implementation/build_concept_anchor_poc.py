#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "implementation" / "output"

PARSED_UNIFIED_CSV = OUT_DIR / "rft_poc" / "parsed_unified.csv"
PRODUCT_CLUSTERS_CSV = OUT_DIR / "product_evidence_clusters_v2.csv"
PRODUCT_MEMBERS_CSV = OUT_DIR / "product_evidence_cluster_members_v2.csv"
BASE_MAP_CSV = OUT_DIR / "product_to_best_esha_full_map.csv"

OUT_CONCEPTS_CSV = OUT_DIR / "concept_anchor_poc_concepts.csv"
OUT_PRODUCT_CLUSTERS_CSV = OUT_DIR / "concept_anchor_poc_product_clusters.csv"
OUT_PRODUCTS_CSV = OUT_DIR / "concept_anchor_poc_products.csv"
OUT_FULL_MAP_CSV = OUT_DIR / "product_to_best_esha_full_map.vConceptAnchor.csv"
OUT_ANCHORS_CSV = OUT_DIR / "concept_anchor_poc_anchor_spine.csv"
OUT_GAPS_CSV = OUT_DIR / "concept_anchor_poc_esha_gaps.csv"
OUT_MD = OUT_DIR / "concept_anchor_poc.md"
OUT_SUMMARY_JSON = OUT_DIR / "concept_anchor_poc_summary.json"


TOKEN_RE = re.compile(r"[a-z][a-z0-9']*")

TOKEN_NORMALIZATION = {
    "oysters": "oyster",
    "scallops": "scallop",
    "shrimps": "shrimp",
    "prawns": "shrimp",
    "prawn": "shrimp",
    "crabs": "crab",
    "sardines": "sardine",
    "anchovies": "anchovy",
    "mussels": "mussel",
    "clams": "clam",
    "mollusks": "mollusk",
    "molluscs": "mollusk",
    "crustaceans": "crustacean",
    "fishes": "fish",
    "fillets": "fillet",
    "steaks": "steak",
    "clusters": "cluster",
    "legs": "leg",
    "rolls": "roll",
    "pouches": "pouch",
    "packets": "pouch",
    "cans": "can",
    "mushrooms": "mushroom",
    "dungeoness": "dungeness",
    "dungeness": "dungeness",
    "yellowfin": "yellowfin",
    "bluefin": "bluefin",
    "skipjack": "skipjack",
    "albacore": "albacore",
}

SEAFOOD_MARKERS = {
    "fish",
    "seafood",
    "shellfish",
    "mollusk",
    "crustacean",
    "oyster",
    "scallop",
    "shrimp",
    "crab",
    "lobster",
    "salmon",
    "tuna",
    "sardine",
    "anchovy",
    "mackerel",
    "pollock",
    "cod",
    "tilapia",
    "trout",
    "mahi",
    "catfish",
    "clam",
    "mussel",
    "herring",
    "flounder",
    "haddock",
    "snapper",
    "swai",
    "whiting",
}

SEAFOOD_IDENTITIES = (
    "scallop",
    "oyster",
    "shrimp",
    "crab",
    "lobster",
    "salmon",
    "tuna",
    "sardine",
    "anchovy",
    "mackerel",
    "pollock",
    "cod",
    "tilapia",
    "trout",
    "mahi",
    "catfish",
    "clam",
    "mussel",
    "herring",
    "flounder",
    "haddock",
    "snapper",
    "swai",
    "whiting",
    "fish",
    "seafood",
)

SEAFOOD_CATEGORY_MARKERS = (
    "fish",
    "seafood",
    "shellfish",
    "canned tuna",
    "sushi",
)

SEAFOOD_LANES = {
    "fish_seafood",
    "canned_seafood",
    "canned_tuna",
    "sushi",
}
TARGET_CONCEPT_LANES = {"seafood", "mushroom"}

NON_SEAFOOD_OYSTER_HEADS = {
    "mushroom",
    "cracker",
    "sauce",
    "soup",
    "beef",
    "ostrich",
    "emu",
    "vegetable",
    "salsify",
}

STRONG_SUBTYPES = {
    "crab": {"snow", "blue", "dungeness", "king", "queen"},
    "salmon": {"pink", "sockeye", "atlantic", "coho", "chinook", "chum"},
    "tuna": {"skipjack", "albacore", "yellowfin", "bluefin", "white", "light"},
    "oyster": {"pacific", "eastern"},
}

SUBTYPE_TERMS = {
    "crab": {
        "snow",
        "blue",
        "dungeness",
        "king",
        "queen",
        "soft",
        "hard",
        "imitation",
        "surimi",
        "alaska",
        "alaskan",
        "maryland",
    },
    "salmon": {
        "pink",
        "sockeye",
        "atlantic",
        "coho",
        "chinook",
        "chum",
        "red",
        "alaska",
        "alaskan",
        "nova",
    },
    "tuna": {
        "skipjack",
        "albacore",
        "yellowfin",
        "bluefin",
        "white",
        "light",
        "ahi",
    },
    "scallop": {"sea", "bay", "mixed", "imitation", "surimi"},
    "oyster": {"pacific", "eastern", "smoked"},
    "shrimp": {"popcorn", "breaded", "imitation", "surimi", "deveined", "tiny"},
    "lobster": {"northern", "spiny", "brazil", "green"},
}

STATE_TERMS = {
    "canned",
    "raw",
    "fresh",
    "frozen",
    "cooked",
    "steamed",
    "baked",
    "broiled",
    "fried",
    "smoked",
    "dried",
    "dry",
    "breaded",
    "coated",
    "battered",
    "grilled",
    "roasted",
    "unsalted",
}
MATERIAL_STATE_TERMS = {"dried", "canned", "smoked", "fried", "breaded", "cooked"}

FORM_TERMS = {
    "fillet",
    "steak",
    "cluster",
    "leg",
    "meat",
    "pouch",
    "roll",
    "sushi",
    "whole",
    "sliced",
    "slice",
    "cake",
    "patty",
    "salad",
    "sauce",
    "soup",
    "popcorn",
    "nugget",
    "bite",
    "bites",
}

BAD_PROXY_FORMS = {"dish", "sushi_roll", "soup", "sauce", "cracker", "base", "seasoning"}
BAD_PROXY_FORMS |= {
    "meal",
    "rice",
    "noodle",
    "pasta",
    "casserole",
    "sandwich",
    "taco",
    "toast",
    "quiche",
    "salad",
    "roll",
}
PREPARED_PRODUCT_FORMS = {"seasoned", "marinated", "stuffed", "skewer", "medley"}


@dataclass(frozen=True)
class Concept:
    lane: str
    identity: str
    subtypes: tuple[str, ...]
    states: tuple[str, ...]
    forms: tuple[str, ...]

    @property
    def path(self) -> str:
        return "/".join(
            (
                self.lane or "unknown",
                self.identity or "unknown",
                "+".join(self.subtypes) if self.subtypes else "generic",
                "+".join(self.states) if self.states else "generic",
                "+".join(self.forms) if self.forms else "generic",
            )
        )

    @property
    def concept_id(self) -> str:
        return hashlib.sha1(self.path.encode("utf-8")).hexdigest()[:14]


@dataclass(frozen=True)
class Anchor:
    source: str
    code: str
    description: str
    category: str
    concept: Concept


@dataclass(frozen=True)
class AnchorMatch:
    anchor: Anchor
    score: float
    quality: str
    reason: str


def normalized_token(raw: str) -> str:
    token = raw.lower().strip("'")
    token = TOKEN_NORMALIZATION.get(token, token)
    if len(token) > 3 and token.endswith("s") and token not in {"bass"}:
        singular = token[:-1]
        token = TOKEN_NORMALIZATION.get(singular, singular)
    return token


def tokens_for(text: object) -> set[str]:
    text_s = str(text or "").lower().replace("&", " and ")
    tokens = {normalized_token(t) for t in TOKEN_RE.findall(text_s)}
    if "yellow fin" in text_s:
        tokens.add("yellowfin")
    if "blue fin" in text_s:
        tokens.add("bluefin")
    if "mahi mahi" in text_s or "mahi-mahi" in text_s:
        tokens.add("mahi")
    if "snow crab" in text_s:
        tokens.update({"snow", "crab"})
    if "king crab" in text_s or "alaska king" in text_s or "alaskan king" in text_s:
        tokens.update({"king", "crab"})
    if "oyster mushroom" in text_s:
        tokens.update({"oyster", "mushroom"})
    if "popcorn shrimp" in text_s:
        tokens.update({"popcorn", "shrimp"})
    if "sushi roll" in text_s:
        tokens.update({"sushi", "roll"})
    return {t for t in tokens if len(t) >= 2}


def compact(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(sorted({v for v in values if v and v != "generic"}))


def category_says_seafood(category: str) -> bool:
    cat_l = str(category or "").lower()
    return any(marker in cat_l for marker in SEAFOOD_CATEGORY_MARKERS)


def detect_lane(tokens: set[str], text: str, category: str, source: str = "") -> str:
    category_l = str(category or "").lower()
    text_l = str(text or "").lower()

    if "mushroom" in tokens:
        return "mushroom"
    if "vegetable oyster" in text_l:
        return "vegetable"

    if source in {"sr28", "fndds"} and category_says_seafood(category):
        return "seafood"
    if category_says_seafood(category):
        return "seafood"
    if tokens & SEAFOOD_MARKERS:
        if tokens & NON_SEAFOOD_OYSTER_HEADS and not category_says_seafood(category):
            return ""
        if "oyster" in tokens and not (tokens - {"oyster"} & SEAFOOD_MARKERS):
            return ""
        return "seafood"
    if "finfish and shellfish" in category_l:
        return "seafood"
    return ""


def detect_identity(tokens: set[str], lane: str) -> str:
    if lane == "mushroom":
        return "mushroom"
    if lane != "seafood":
        return ""
    for identity in SEAFOOD_IDENTITIES:
        if identity in tokens:
            return identity
    if "mollusk" in tokens:
        return "mollusk"
    if "crustacean" in tokens:
        return "crustacean"
    return "seafood"


def detect_subtypes(identity: str, tokens: set[str]) -> tuple[str, ...]:
    if identity == "mushroom":
        out = []
        for subtype in ("oyster", "shiitake", "porcini", "button", "portobello", "crimini", "king", "golden"):
            if subtype in tokens:
                out.append(subtype)
        if "king" in tokens and "oyster" in tokens:
            out.append("king_oyster")
        return compact(out)

    terms = SUBTYPE_TERMS.get(identity, set())
    out = set(tokens & terms)
    if identity == "crab" and "alaskan" in out:
        out.add("alaska")
    if identity == "salmon" and "red" in out:
        out.add("sockeye")
    if identity == "tuna" and "ahi" in out:
        out.add("yellowfin")
    if "surimi" in out:
        out.add("imitation")
    return compact(out)


def detect_states(tokens: set[str], text: str, category: str) -> tuple[str, ...]:
    text_l = str(text or "").lower()
    category_l = str(category or "").lower()
    out: set[str] = set()
    for term in STATE_TERMS:
        if term in tokens:
            out.add(term)
    if "can" in tokens or "canned" in category_l:
        out.add("canned")
    if "fresh" in tokens or "raw" in tokens or "uncooked" in tokens:
        out.add("raw")
    if "batter" in tokens or "battered" in tokens:
        out.add("breaded")
    if "breaded" in tokens or "coated" in tokens:
        out.add("breaded")
    if "water pack" in text_l or "in water" in text_l:
        out.add("water_pack")
    if "oil pack" in text_l or "in oil" in text_l:
        out.add("oil_pack")
    if "dried" in out or "dry" in out:
        out.discard("dry")
        out.add("dried")
    if "fried" in out or "steamed" in out or "baked" in out or "broiled" in out or "grilled" in out:
        out.add("cooked")
    produce_category = (
        "pre-packaged fruit & vegetables" in category_l
        or "pre-packaged fruit and vegetables" in category_l
        or "fresh fruit" in category_l
        or "fresh vegetables" in category_l
    )
    if produce_category and not (out & (MATERIAL_STATE_TERMS | {"frozen"})):
        out.update({"fresh", "raw"})
    return compact(out)


def detect_forms(tokens: set[str], text: str) -> tuple[str, ...]:
    text_l = str(text or "").lower()
    out: set[str] = set()
    for term in FORM_TERMS:
        if term in tokens:
            out.add(term)
    if "sushi" in tokens and "roll" in tokens:
        out.add("sushi_roll")
        out.discard("sushi")
        out.discard("roll")
    if "crabmeat" in text_l:
        out.add("meat")
    if "crab cake" in text_l:
        out.add("cake")
    if "fish stick" in text_l or "fish sticks" in text_l:
        out.add("stick")
    if tokens & {"seasoned", "seasoning", "spiced", "spice", "spices", "smoky", "marinated", "shawarma"}:
        out.add("seasoned")
    if tokens & {"stuffed", "skewer", "skewers", "medley"}:
        out |= tokens & {"stuffed", "skewer", "medley"}
    composite_markers = {
        "dish",
        "meal",
        "casserole",
        "rice",
        "noodle",
        "pasta",
        "sandwich",
        "taco",
        "toast",
        "quiche",
        "base",
        "seasoning",
    }
    out |= tokens & composite_markers
    if "fillet" in out:
        out.discard("filet")
    if "slice" in out:
        out.add("sliced")
        out.discard("slice")
    if "bites" in out:
        out.add("bite")
        out.discard("bites")
    return compact(out)


def extract_concept(text: object, category: object = "", source: str = "") -> Concept | None:
    text_s = str(text or "")
    category_s = str(category or "")
    text_tokens = tokens_for(text_s)
    category_tokens = tokens_for(category_s)
    lane = detect_lane(text_tokens | category_tokens, text_s, category_s, source)
    if not lane:
        return None
    identity = detect_identity(text_tokens, lane)
    if not identity and lane == "seafood" and category_s:
        identity = "seafood"
    if not identity:
        return None
    return Concept(
        lane=lane,
        identity=identity,
        subtypes=detect_subtypes(identity, text_tokens),
        states=detect_states(text_tokens | category_tokens, text_s, category_s),
        forms=detect_forms(text_tokens, text_s),
    )


def dominant_state_hint(state_lane_top: object) -> str:
    first = str(state_lane_top or "").split(" | ", 1)[0].strip()
    if not first:
        return ""
    state = first.split(":", 1)[0].strip()
    return state.replace("+", " ")


def concept_for_product_cluster(row: dict[str, str]) -> Concept | None:
    text = " ".join(
        str(row.get(col, ""))
        for col in (
            "dominant_product_description",
            "title_identity_terms",
            "ingredient_core_terms",
            "dominant_title_tokens",
            "dominant_ingredient_terms",
        )
    )
    state_hint = dominant_state_hint(row.get("state_lane_top", ""))
    if state_hint:
        text = f"{text} {state_hint}"
    category = " ".join(str(row.get(col, "")) for col in ("dominant_category", "top_categories", "category_lane"))
    return extract_concept(text, category)


def is_seafood_product_cluster(row: dict[str, str]) -> bool:
    lane = str(row.get("category_lane") or "").strip()
    if lane in SEAFOOD_LANES:
        return True
    haystack = f"{row.get('dominant_category', '')} {row.get('top_categories', '')}".lower()
    return any(marker in haystack for marker in SEAFOOD_CATEGORY_MARKERS)


def is_plain_mushroom_product_cluster(row: dict[str, str]) -> bool:
    haystack = " ".join(
        str(row.get(col, ""))
        for col in (
            "dominant_product_description",
            "dominant_category",
            "top_categories",
            "category_lane",
            "product_form",
            "title_identity_terms",
            "dominant_title_tokens",
        )
    ).lower()
    if "mushroom" not in haystack:
        return False
    excluded_forms = {
        "soup",
        "sauce_condiment",
        "gravy_mix",
        "chili_stew",
        "prepared_meal",
        "seasoning",
        "cracker",
        "pizza",
        "sandwich",
    }
    if str(row.get("category_lane") or "") in excluded_forms:
        return False
    excluded_text = {"soup", "sauce", "gravy", "stew", "pizza", "cracker", "broth", "spaghetti", "pasta"}
    if tokens_for(row.get("dominant_product_description", "")) & excluded_text:
        return False
    allowed_lanes = {
        "vegetable",
        "produce_fruit",
        "baking_additives",
        "vegetable_lentil_mixes",
        "pickles_olives_peppers_relishes",
        "other_deli",
    }
    if str(row.get("category_lane") or "") in allowed_lanes:
        return True
    category = str(row.get("dominant_category") or "").lower()
    return any(
        marker in category
        for marker in (
            "vegetable",
            "fruit & vegetables",
            "baking additives",
            "pickles",
            "deli",
        )
    )


def is_target_product_cluster(row: dict[str, str]) -> bool:
    return is_seafood_product_cluster(row) or is_plain_mushroom_product_cluster(row)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def load_member_current_descriptions(path: Path) -> dict[str, Counter[str]]:
    by_cluster: dict[str, Counter[str]] = defaultdict(Counter)
    if not path.exists():
        return by_cluster
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            cluster_id = str(row.get("cluster_id") or "")
            current_desc = str(row.get("current_esha_description") or "").strip()
            if cluster_id and current_desc:
                by_cluster[cluster_id][current_desc] += 1
    return by_cluster


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def load_anchor_spine(path: Path) -> list[Anchor]:
    anchors: list[Anchor] = []
    for row in read_csv(path):
        source = (row.get("source") or "").strip()
        if source not in {"esha", "fndds", "sr28"}:
            continue
        desc = row.get("full_desc") or ""
        category = row.get("category") or ""
        concept = extract_concept(desc, category, source=source)
        if not concept or concept.lane not in TARGET_CONCEPT_LANES:
            continue
        anchors.append(
            Anchor(
                source=source,
                code=str(row.get("code") or "").strip(),
                description=desc,
                category=category,
                concept=concept,
            )
        )
    return anchors


def subtype_conflict(product: Concept, anchor: Concept) -> str:
    strong = STRONG_SUBTYPES.get(product.identity, set())
    if not strong:
        return ""
    product_strong = set(product.subtypes) & strong
    anchor_strong = set(anchor.subtypes) & strong
    if product_strong and anchor_strong and not (product_strong & anchor_strong):
        return "strong_subtype_mismatch"
    return ""


def state_conflict(product: Concept, anchor: Concept) -> str:
    p_states = set(product.states)
    a_states = set(anchor.states)
    if "raw" in p_states and ({"cooked", "fried", "smoked", "dried", "canned"} & a_states):
        return "raw_product_to_cooked_anchor"
    if "dried" in p_states and not ("dried" in a_states):
        return "dried_product_to_non_dried_anchor"
    if "canned" in p_states and "canned" not in a_states and ({"raw", "fresh"} & a_states):
        return "canned_product_to_raw_anchor"
    if "canned" in p_states and "dried" in a_states:
        return "canned_product_to_dried_anchor"
    if "breaded" in p_states and not ({"breaded", "fried"} & a_states):
        return "breaded_product_to_unbreaded_anchor"
    return ""


def score_anchor(product: Concept, anchor: Anchor) -> AnchorMatch | None:
    candidate = anchor.concept
    if product.lane != candidate.lane or product.identity != candidate.identity:
        return None

    conflict = subtype_conflict(product, candidate) or state_conflict(product, candidate)
    if conflict:
        return None

    score = 50.0
    reasons = ["identity"]

    product_subtypes = set(product.subtypes)
    anchor_subtypes = set(candidate.subtypes)
    if product_subtypes:
        overlap = product_subtypes & anchor_subtypes
        if overlap:
            score += 20.0 + min(8.0, len(overlap) * 2.0)
            reasons.append("subtype:" + "+".join(sorted(overlap)))
        elif not (anchor_subtypes & STRONG_SUBTYPES.get(product.identity, set())):
            score -= 5.0
            reasons.append("generic_subtype_proxy")
        else:
            score -= 15.0
            reasons.append("subtype_proxy")
    else:
        anchor_strong = anchor_subtypes & STRONG_SUBTYPES.get(product.identity, set())
        if anchor_strong:
            score -= 8.0
            reasons.append("specific_subtype_proxy:" + "+".join(sorted(anchor_strong)))

    product_states = set(product.states)
    anchor_states = set(candidate.states)
    state_overlap = product_states & anchor_states
    frozen_raw_proxy = (
        product_states == {"frozen"}
        and "raw" in anchor_states
        and not (anchor_states & {"cooked", "fried", "breaded", "smoked", "canned"})
    )
    if state_overlap:
        score += 14.0 + min(6.0, len(state_overlap) * 2.0)
        reasons.append("state:" + "+".join(sorted(state_overlap)))
    elif frozen_raw_proxy:
        score += 8.0
        reasons.append("state:frozen_raw_proxy")
    elif product_states:
        score -= 8.0
        reasons.append("state_proxy")
    elif anchor_states & MATERIAL_STATE_TERMS:
        score -= 16.0
        reasons.append("stateful_anchor_without_product_state")
    if "fried" in anchor_states and not (product_states & {"fried", "breaded"}):
        score -= 8.0
        reasons.append("fried_anchor_without_fried_product")

    product_forms = set(product.forms)
    anchor_forms = set(candidate.forms)
    form_overlap = product_forms & anchor_forms
    if form_overlap:
        score += 8.0 + min(6.0, len(form_overlap) * 2.0)
        reasons.append("form:" + "+".join(sorted(form_overlap)))
    elif product_forms and anchor_forms:
        score -= 5.0
        reasons.append("form_proxy")
    if product_forms & PREPARED_PRODUCT_FORMS and not (anchor_forms & product_forms):
        score -= 12.0
        reasons.append("prepared_form_proxy")

    bad_extra_forms = (anchor_forms & BAD_PROXY_FORMS) - product_forms
    if bad_extra_forms:
        score -= 18.0
        reasons.append("bad_proxy_form:" + "+".join(sorted(bad_extra_forms)))

    if anchor.source == "esha":
        score += 2.0
    elif anchor.source == "sr28":
        score += 1.0

    if score >= 84:
        quality = "exact"
    elif score >= 68:
        quality = "close_proxy"
    elif score >= 54:
        quality = "broad_proxy"
    else:
        quality = "weak"
    return AnchorMatch(anchor=anchor, score=score, quality=quality, reason=";".join(reasons))


def best_anchor(product: Concept, anchors: list[Anchor], source: str) -> AnchorMatch | None:
    matches = [m for anchor in anchors if anchor.source == source for m in [score_anchor(product, anchor)] if m]
    if not matches:
        return None
    matches.sort(key=lambda m: (m.score, -len(m.anchor.description)), reverse=True)
    return matches[0]


def anchor_value(match: AnchorMatch | None, attr: str) -> str:
    if not match:
        return ""
    if attr == "code":
        return match.anchor.code
    if attr == "description":
        return match.anchor.description
    if attr == "quality":
        return match.quality
    if attr == "score":
        return f"{match.score:.1f}"
    if attr == "reason":
        return match.reason
    if attr == "path":
        return match.anchor.concept.path
    return ""


def current_conflict_reason(product: Concept, current_description: str) -> str:
    if not current_description:
        return "current_unassigned"
    current = extract_concept(current_description, "")
    if not current:
        return "current_unparseable"
    if current.lane != product.lane:
        return f"current_lane_mismatch:{current.lane}"
    if current.identity != product.identity:
        return f"current_identity_mismatch:{current.identity}"
    if subtype_conflict(product, current):
        return "current_strong_subtype_mismatch"
    if state_conflict(product, current):
        return "current_state_mismatch"
    bad_extra_forms = (set(current.forms) & BAD_PROXY_FORMS) - set(product.forms)
    if bad_extra_forms:
        return "current_bad_proxy_form:" + "+".join(sorted(bad_extra_forms))
    return ""


def summarize_counts(values: Iterable[str], limit: int = 8) -> str:
    return " | ".join(f"{k}:{v}" for k, v in Counter(v for v in values if v).most_common(limit))


def choose_nutrition_anchor(matches: dict[str, AnchorMatch | None]) -> str:
    usable = [m for m in matches.values() if m and m.quality in {"exact", "close_proxy", "broad_proxy"}]
    if not usable:
        return ""
    usable.sort(
        key=lambda m: (
            {"exact": 3, "close_proxy": 2, "broad_proxy": 1, "weak": 0}[m.quality],
            m.score,
            {"sr28": 3, "fndds": 2, "esha": 1}.get(m.anchor.source, 0),
        ),
        reverse=True,
    )
    best = usable[0]
    return f"{best.anchor.source}:{best.anchor.code}"


def concept_status(row: dict[str, object]) -> str:
    esha_quality = str(row.get("esha_quality") or "")
    gap = str(row.get("gap_reason") or "")
    nutrition_anchor = str(row.get("nutrition_anchor") or "")
    if esha_quality in {"exact", "close_proxy"} and not gap:
        return "safe_esha"
    if nutrition_anchor:
        return "nutrition_proxy_review"
    return "gap_unmapped"


def esha_head(description: object) -> str:
    return str(description or "").split(",", 1)[0].strip().title()


def gap_reason(matches: dict[str, AnchorMatch | None]) -> str:
    esha = matches.get("esha")
    sr28 = matches.get("sr28")
    fndds = matches.get("fndds")
    if esha and esha.quality in {"exact", "close_proxy"}:
        return ""
    if (sr28 and sr28.quality in {"exact", "close_proxy"}) or (fndds and fndds.quality in {"exact", "close_proxy"}):
        return "esha_tree_gap_or_weak_esha_proxy"
    if esha and esha.quality == "broad_proxy":
        return "esha_broad_proxy_review"
    return "no_good_anchor"


def build_product_rows(
    product_members_path: Path,
    cluster_lookup: dict[str, dict[str, object]],
    concept_lookup: dict[str, dict[str, object]],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    if not product_members_path.exists():
        return rows
    with product_members_path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        for member in reader:
            cluster_id = str(member.get("cluster_id") or "")
            cluster = cluster_lookup.get(cluster_id)
            if not cluster:
                continue
            concept = concept_lookup.get(str(cluster.get("concept_path") or ""))
            if not concept:
                continue
            status = concept_status(concept)
            rows.append(
                {
                    "gtin_upc": member.get("gtin_upc", ""),
                    "fdc_id": member.get("fdc_id", ""),
                    "product_description": member.get("product_description", ""),
                    "branded_food_category": member.get("branded_food_category", ""),
                    "brand_owner": member.get("brand_owner", ""),
                    "brand_name": member.get("brand_name", ""),
                    "cluster_id": cluster_id,
                    "concept_id": concept.get("concept_id", ""),
                    "concept_path": concept.get("concept_path", ""),
                    "concept_status": status,
                    "current_esha_code": member.get("current_esha_code", ""),
                    "current_esha_description": member.get("current_esha_description", ""),
                    "current_assignment_source": member.get("current_assignment_source", ""),
                    "recommended_esha_code": concept.get("esha_code", "") if status == "safe_esha" else "",
                    "recommended_esha_description": concept.get("esha_description", "") if status == "safe_esha" else "",
                    "esha_code": concept.get("esha_code", ""),
                    "esha_description": concept.get("esha_description", ""),
                    "esha_quality": concept.get("esha_quality", ""),
                    "esha_score": concept.get("esha_score", ""),
                    "fndds_code": concept.get("fndds_code", ""),
                    "fndds_description": concept.get("fndds_description", ""),
                    "fndds_quality": concept.get("fndds_quality", ""),
                    "sr28_code": concept.get("sr28_code", ""),
                    "sr28_description": concept.get("sr28_description", ""),
                    "sr28_quality": concept.get("sr28_quality", ""),
                    "nutrition_anchor": concept.get("nutrition_anchor", ""),
                    "gap_reason": concept.get("gap_reason", ""),
                }
            )
    return rows


def build_full_overlay(
    base_map_path: Path,
    product_rows: list[dict[str, object]],
    output_path: Path,
) -> dict[str, object]:
    by_fdc = {str(row.get("fdc_id") or ""): row for row in product_rows if str(row.get("fdc_id") or "")}
    if not base_map_path.exists() or not by_fdc:
        return {"rows": 0, "overlay_rows": 0}

    with base_map_path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        base_rows = list(reader)
        fieldnames = list(reader.fieldnames or [])

    added_fields = [
        "concept_id",
        "concept_path",
        "concept_status",
        "concept_esha_code",
        "concept_esha_description",
        "concept_esha_quality",
        "concept_fndds_code",
        "concept_fndds_description",
        "concept_fndds_quality",
        "concept_sr28_code",
        "concept_sr28_description",
        "concept_sr28_quality",
        "concept_nutrition_anchor",
        "concept_gap_reason",
    ]
    for field in added_fields:
        if field not in fieldnames:
            fieldnames.append(field)

    status_counts: Counter[str] = Counter()
    overlay_rows = 0
    safe_rows = 0
    blanked_rows = 0
    for row in base_rows:
        assignment = by_fdc.get(str(row.get("fdc_id") or ""))
        if not assignment:
            for field in added_fields:
                row.setdefault(field, "")
            continue
        overlay_rows += 1
        status = str(assignment.get("concept_status") or "")
        status_counts[status] += 1
        row["concept_id"] = str(assignment.get("concept_id") or "")
        row["concept_path"] = str(assignment.get("concept_path") or "")
        row["concept_status"] = status
        row["concept_esha_code"] = str(assignment.get("esha_code") or "")
        row["concept_esha_description"] = str(assignment.get("esha_description") or "")
        row["concept_esha_quality"] = str(assignment.get("esha_quality") or "")
        row["concept_fndds_code"] = str(assignment.get("fndds_code") or "")
        row["concept_fndds_description"] = str(assignment.get("fndds_description") or "")
        row["concept_fndds_quality"] = str(assignment.get("fndds_quality") or "")
        row["concept_sr28_code"] = str(assignment.get("sr28_code") or "")
        row["concept_sr28_description"] = str(assignment.get("sr28_description") or "")
        row["concept_sr28_quality"] = str(assignment.get("sr28_quality") or "")
        row["concept_nutrition_anchor"] = str(assignment.get("nutrition_anchor") or "")
        row["concept_gap_reason"] = str(assignment.get("gap_reason") or "")

        if status == "safe_esha":
            safe_rows += 1
            row["best_esha_code"] = str(assignment.get("recommended_esha_code") or "")
            row["best_esha_description"] = str(assignment.get("recommended_esha_description") or "")
            if "best_esha_head" in row:
                row["best_esha_head"] = esha_head(row["best_esha_description"])
            if "best_esha_family" in row:
                row["best_esha_family"] = str(assignment.get("concept_path") or "").split("/", 2)[0]
            if "score" in row:
                row["score"] = str(assignment.get("esha_score") or "")
            if "n_candidates" in row:
                row["n_candidates"] = "1"
            row["assignment_source"] = "concept_anchor_safe"
        else:
            blanked_rows += 1
            for field in ("best_esha_code", "best_esha_description", "best_esha_head", "best_esha_family", "score"):
                if field in row:
                    row[field] = ""
            if "n_candidates" in row:
                row["n_candidates"] = "0"
            row["assignment_source"] = "concept_anchor_" + status

    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(base_rows)

    return {
        "rows": len(base_rows),
        "output": str(output_path),
        "overlay_rows": overlay_rows,
        "safe_esha_rows": safe_rows,
        "blanked_review_or_gap_rows": blanked_rows,
        "concept_status_counts": dict(status_counts),
    }


def build_poc(args: argparse.Namespace) -> dict[str, object]:
    anchors = load_anchor_spine(args.parsed_unified)
    target_anchors = [a for a in anchors if a.concept.lane in TARGET_CONCEPT_LANES]
    member_current = load_member_current_descriptions(args.product_members)

    cluster_rows: list[dict[str, object]] = []
    concept_groups: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in read_csv(args.product_clusters):
        if not is_target_product_cluster(row):
            continue
        concept = concept_for_product_cluster(row)
        if not concept or concept.lane not in TARGET_CONCEPT_LANES:
            continue
        try:
            n_products = int(float(row.get("n_products") or 0))
        except ValueError:
            n_products = 0
        if n_products < args.min_cluster_size:
            continue
        current_counter = member_current.get(str(row.get("cluster_id") or ""), Counter())
        dominant_current_description = current_counter.most_common(1)[0][0] if current_counter else ""
        current_reason = current_conflict_reason(concept, dominant_current_description)
        out_row: dict[str, object] = {
            "cluster_id": row.get("cluster_id", ""),
            "concept_id": concept.concept_id,
            "concept_path": concept.path,
            "n_products": n_products,
            "dominant_category": row.get("dominant_category", ""),
            "top_categories": row.get("top_categories", ""),
            "dominant_product_description": row.get("dominant_product_description", ""),
            "top_current_codes": row.get("top_current_codes", ""),
            "dominant_current_code": row.get("dominant_current_code", ""),
            "dominant_current_head": row.get("dominant_current_head", ""),
            "dominant_current_description": dominant_current_description,
            "top_current_descriptions": " | ".join(f"{desc}:{count}" for desc, count in current_counter.most_common(5)),
            "current_conflict_hint": current_reason,
            "title_identity_terms": row.get("title_identity_terms", ""),
            "ingredient_core_terms": row.get("ingredient_core_terms", ""),
            "dominant_title_tokens": row.get("dominant_title_tokens", ""),
            "dominant_ingredient_terms": row.get("dominant_ingredient_terms", ""),
            "sample_fdc_ids": row.get("sample_fdc_ids", ""),
            "sample_gtins": row.get("sample_gtins", ""),
        }
        cluster_rows.append(out_row)
        concept_groups[concept.path].append(out_row)

    concept_rows: list[dict[str, object]] = []
    for path, group in concept_groups.items():
        first = group[0]
        concept_parts = path.split("/")
        concept = Concept(
            lane=concept_parts[0],
            identity=concept_parts[1],
            subtypes=tuple(() if concept_parts[2] == "generic" else concept_parts[2].split("+")),
            states=tuple(() if concept_parts[3] == "generic" else concept_parts[3].split("+")),
            forms=tuple(() if concept_parts[4] == "generic" else concept_parts[4].split("+")),
        )
        matches = {source: best_anchor(concept, target_anchors, source) for source in ("esha", "fndds", "sr28")}
        concept_rows.append(
            {
                "concept_id": concept.concept_id,
                "concept_path": concept.path,
                "lane": concept.lane,
                "identity": concept.identity,
                "subtypes": " ".join(concept.subtypes),
                "states": " ".join(concept.states),
                "forms": " ".join(concept.forms),
                "n_product_clusters": len(group),
                "n_products": sum(int(r["n_products"]) for r in group),
                "top_categories": summarize_counts((str(r["dominant_category"]) for r in group), 6),
                "sample_products": " || ".join(str(r["dominant_product_description"]) for r in group[:8]),
                "current_conflict_hints": summarize_counts((str(r["current_conflict_hint"]) for r in group), 6),
                "top_current_codes": " || ".join(str(r["top_current_codes"]) for r in group[:4]),
                "esha_code": anchor_value(matches["esha"], "code"),
                "esha_description": anchor_value(matches["esha"], "description"),
                "esha_quality": anchor_value(matches["esha"], "quality"),
                "esha_score": anchor_value(matches["esha"], "score"),
                "esha_reason": anchor_value(matches["esha"], "reason"),
                "fndds_code": anchor_value(matches["fndds"], "code"),
                "fndds_description": anchor_value(matches["fndds"], "description"),
                "fndds_quality": anchor_value(matches["fndds"], "quality"),
                "fndds_score": anchor_value(matches["fndds"], "score"),
                "sr28_code": anchor_value(matches["sr28"], "code"),
                "sr28_description": anchor_value(matches["sr28"], "description"),
                "sr28_quality": anchor_value(matches["sr28"], "quality"),
                "sr28_score": anchor_value(matches["sr28"], "score"),
                "nutrition_anchor": choose_nutrition_anchor(matches),
                "gap_reason": gap_reason(matches),
            }
        )

    concept_rows.sort(key=lambda r: (int(r["n_products"]), str(r["concept_path"])), reverse=True)
    cluster_rows.sort(key=lambda r: (str(r["concept_path"]), -int(r["n_products"])))
    concept_lookup = {str(row["concept_path"]): row for row in concept_rows}
    cluster_lookup = {str(row["cluster_id"]): row for row in cluster_rows}
    product_rows = build_product_rows(args.product_members, cluster_lookup, concept_lookup)
    overlay_summary = build_full_overlay(args.base_map, product_rows, args.output_full_map)

    anchor_rows = [
        {
            "source": a.source,
            "code": a.code,
            "description": a.description,
            "category": a.category,
            "concept_path": a.concept.path,
            "lane": a.concept.lane,
            "identity": a.concept.identity,
            "subtypes": " ".join(a.concept.subtypes),
            "states": " ".join(a.concept.states),
            "forms": " ".join(a.concept.forms),
        }
        for a in anchors
    ]
    anchor_rows.sort(key=lambda r: (str(r["lane"]), str(r["identity"]), str(r["source"]), str(r["code"])))

    write_csv(
        args.output_concepts,
        concept_rows,
        [
            "concept_id",
            "concept_path",
            "lane",
            "identity",
            "subtypes",
            "states",
            "forms",
            "n_product_clusters",
            "n_products",
            "top_categories",
            "sample_products",
            "current_conflict_hints",
            "top_current_codes",
            "esha_code",
            "esha_description",
            "esha_quality",
            "esha_score",
            "esha_reason",
            "fndds_code",
            "fndds_description",
            "fndds_quality",
            "fndds_score",
            "sr28_code",
            "sr28_description",
            "sr28_quality",
            "sr28_score",
            "nutrition_anchor",
            "gap_reason",
        ],
    )
    write_csv(
        args.output_product_clusters,
        cluster_rows,
        [
            "cluster_id",
            "concept_id",
            "concept_path",
            "n_products",
            "dominant_category",
            "top_categories",
            "dominant_product_description",
            "top_current_codes",
            "dominant_current_code",
            "dominant_current_head",
            "dominant_current_description",
            "top_current_descriptions",
            "current_conflict_hint",
            "title_identity_terms",
            "ingredient_core_terms",
            "dominant_title_tokens",
            "dominant_ingredient_terms",
            "sample_fdc_ids",
            "sample_gtins",
        ],
    )
    write_csv(
        args.output_products,
        product_rows,
        [
            "gtin_upc",
            "fdc_id",
            "product_description",
            "branded_food_category",
            "brand_owner",
            "brand_name",
            "cluster_id",
            "concept_id",
            "concept_path",
            "concept_status",
            "current_esha_code",
            "current_esha_description",
            "current_assignment_source",
            "recommended_esha_code",
            "recommended_esha_description",
            "esha_code",
            "esha_description",
            "esha_quality",
            "esha_score",
            "fndds_code",
            "fndds_description",
            "fndds_quality",
            "sr28_code",
            "sr28_description",
            "sr28_quality",
            "nutrition_anchor",
            "gap_reason",
        ],
    )
    write_csv(
        args.output_anchors,
        anchor_rows,
        ["source", "code", "description", "category", "concept_path", "lane", "identity", "subtypes", "states", "forms"],
    )
    gap_rows = [
        {"concept_status": concept_status(row), **row}
        for row in concept_rows
        if concept_status(row) != "safe_esha"
    ]
    write_csv(
        args.output_gaps,
        gap_rows,
        [
            "concept_status",
            "concept_id",
            "concept_path",
            "lane",
            "identity",
            "subtypes",
            "states",
            "forms",
            "n_product_clusters",
            "n_products",
            "top_categories",
            "sample_products",
            "current_conflict_hints",
            "top_current_codes",
            "esha_code",
            "esha_description",
            "esha_quality",
            "esha_score",
            "esha_reason",
            "fndds_code",
            "fndds_description",
            "fndds_quality",
            "fndds_score",
            "sr28_code",
            "sr28_description",
            "sr28_quality",
            "sr28_score",
            "nutrition_anchor",
            "gap_reason",
        ],
    )

    summary = {
        "anchors": len(anchor_rows),
        "target_lanes": sorted(TARGET_CONCEPT_LANES),
        "target_anchors": len(target_anchors),
        "product_clusters": len(cluster_rows),
        "concepts": len(concept_rows),
        "products_in_concepts": sum(int(r["n_products"]) for r in concept_rows),
        "product_rows": len(product_rows),
        "product_status_counts": Counter(str(r["concept_status"]) for r in product_rows).most_common(),
        "gap_concepts": len(gap_rows),
        "gap_products": sum(int(r["n_products"]) for r in gap_rows),
        "gap_reasons": Counter(str(r["gap_reason"]) or "esha_exact_or_close" for r in concept_rows).most_common(),
        "overlay": overlay_summary,
        "outputs": {
            "concepts": str(args.output_concepts),
            "product_clusters": str(args.output_product_clusters),
            "products": str(args.output_products),
            "full_map": str(args.output_full_map),
            "anchors": str(args.output_anchors),
            "gaps": str(args.output_gaps),
            "markdown": str(args.output_md),
        },
    }
    args.output_summary.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_markdown(args.output_md, concept_rows, cluster_rows, anchors, summary)
    return summary


def write_markdown(
    path: Path,
    concept_rows: list[dict[str, object]],
    cluster_rows: list[dict[str, object]],
    anchors: list[Anchor],
    summary: dict[str, object],
) -> None:
    by_path = {str(r["concept_path"]): r for r in concept_rows}
    focused_paths = [
        "seafood/oyster/pacific+smoked/canned/generic",
        "seafood/oyster/pacific/generic/generic",
        "seafood/crab/snow/generic/cluster",
        "seafood/scallop/generic/frozen/generic",
        "seafood/salmon/pink/canned/generic",
        "seafood/tuna/light/generic/generic",
        "seafood/shrimp/breaded+popcorn/breaded+cooked/popcorn",
    ]
    lines: list[str] = []
    lines.append("# Concept anchor POC\n\n")
    lines.append("This is a non-production proof of concept. Products are first mapped to a canonical concept path, then ESHA/FNDDS/SR28 anchors are attached to that concept.\n\n")
    lines.append("Signal order in this POC: category/lane gate -> ingredient/title identity -> subtype/state/form -> source anchor matching.\n\n")
    lines.append("## Summary\n\n")
    lines.append(f"- Product clusters included: {summary['product_clusters']:,}\n")
    lines.append(f"- Product rows projected: {summary['product_rows']:,}\n")
    lines.append(f"- Canonical concepts formed: {summary['concepts']:,}\n")
    lines.append(f"- Products represented: {summary['products_in_concepts']:,}\n")
    lines.append(f"- Non-safe concepts: {summary['gap_concepts']:,} over {summary['gap_products']:,} products\n")
    lines.append(f"- Target lanes: {', '.join(summary['target_lanes'])}\n")
    lines.append(f"- Source anchors indexed: {summary['target_anchors']:,}\n\n")
    lines.append("## Focused Concepts\n\n")
    for wanted in focused_paths:
        row = by_path.get(wanted)
        if not row:
            continue
        lines.extend(markdown_concept_block(row))

    lines.append("## Top Concepts By Product Count\n\n")
    for row in concept_rows[:25]:
        lines.extend(markdown_concept_block(row, compact_block=True))

    lines.append("## Top ESHA Gaps And Reviews\n\n")
    non_safe = [row for row in concept_rows if concept_status(row) != "safe_esha"]
    non_safe.sort(key=lambda r: int(r["n_products"]), reverse=True)
    for row in non_safe[:25]:
        lines.extend(markdown_concept_block(row, compact_block=True))

    lines.append("## Oyster Word Sanity Check\n\n")
    sanity = [
        ("FRESH PACIFIC OYSTERS", "Fish & Seafood"),
        ("PACIFIC SEAFOOD, SEAROCK, FRESH PACIFIC OYSTERS", "Canned Seafood"),
        ("OYSTER MUSHROOMS", "Baking Additives & Extracts"),
        ("DRIED MUSHROOMS OYSTER", "Baking Additives & Extracts"),
        ("RICHIN BRAND, WHOLE OYSTER MUSHROOMS", "Canned Vegetables"),
    ]
    for desc, category in sanity:
        concept = extract_concept(desc, category)
        path_s = concept.path if concept else "unparsed"
        lines.append(f"- `{desc}` / `{category}` -> `{path_s}`\n")
    lines.append("\n")

    lines.append("## Files\n\n")
    lines.append(f"- Concepts: `{OUT_CONCEPTS_CSV}`\n")
    lines.append(f"- Product clusters: `{OUT_PRODUCT_CLUSTERS_CSV}`\n")
    lines.append(f"- Product rows: `{OUT_PRODUCTS_CSV}`\n")
    lines.append(f"- Full-corpus overlay: `{OUT_FULL_MAP_CSV}`\n")
    lines.append(f"- Anchor spine: `{OUT_ANCHORS_CSV}`\n")
    lines.append(f"- ESHA gaps/reviews: `{OUT_GAPS_CSV}`\n")
    lines.append(f"- Summary: `{OUT_SUMMARY_JSON}`\n")

    path.write_text("".join(lines), encoding="utf-8")


def markdown_concept_block(row: dict[str, object], compact_block: bool = False) -> list[str]:
    lines = [
        f"### `{row['concept_path']}` (n={row['n_products']})\n",
        f"- products: {row['sample_products']}\n",
        f"- ESHA: [{row['esha_code']}] {row['esha_description']} ({row['esha_quality']}, score={row['esha_score']})\n",
        f"- FNDDS: [{row['fndds_code']}] {row['fndds_description']} ({row['fndds_quality']}, score={row['fndds_score']})\n",
        f"- SR28: [{row['sr28_code']}] {row['sr28_description']} ({row['sr28_quality']}, score={row['sr28_score']})\n",
        f"- nutrition anchor: `{row['nutrition_anchor'] or 'none'}`; gap: `{row['gap_reason'] or 'none'}`\n",
    ]
    if not compact_block:
        lines.append(f"- current hints: {row['top_current_codes']}\n")
        lines.append(f"- conflict hints: {row['current_conflict_hints'] or 'none'}\n")
    lines.append("\n")
    return lines


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a product concept -> ESHA/FNDDS/SR28 anchor proof of concept.")
    parser.add_argument("--parsed-unified", type=Path, default=PARSED_UNIFIED_CSV)
    parser.add_argument("--product-clusters", type=Path, default=PRODUCT_CLUSTERS_CSV)
    parser.add_argument("--product-members", type=Path, default=PRODUCT_MEMBERS_CSV)
    parser.add_argument("--base-map", type=Path, default=BASE_MAP_CSV)
    parser.add_argument("--min-cluster-size", type=int, default=1)
    parser.add_argument("--output-concepts", type=Path, default=OUT_CONCEPTS_CSV)
    parser.add_argument("--output-product-clusters", type=Path, default=OUT_PRODUCT_CLUSTERS_CSV)
    parser.add_argument("--output-products", type=Path, default=OUT_PRODUCTS_CSV)
    parser.add_argument("--output-full-map", type=Path, default=OUT_FULL_MAP_CSV)
    parser.add_argument("--output-anchors", type=Path, default=OUT_ANCHORS_CSV)
    parser.add_argument("--output-gaps", type=Path, default=OUT_GAPS_CSV)
    parser.add_argument("--output-md", type=Path, default=OUT_MD)
    parser.add_argument("--output-summary", type=Path, default=OUT_SUMMARY_JSON)
    return parser.parse_args()


def main() -> None:
    summary = build_poc(parse_args())
    print(json.dumps(summary, indent=2, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
