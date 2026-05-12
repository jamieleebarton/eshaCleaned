#!/usr/bin/env python3
"""Build an adjudicated priced-product evidence layer.

This is intentionally non-mutating. It reads the live priced-products DB plus
the 42-column consensus audit corpus and writes a CSV that the calculator can
consume instead of trusting stale title-derived bridge fields.
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

HERE = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[2]
PRICED_DB = ROOT / "recipe_pricing" / "data" / "priced_products_v2.db"
AUDIT = ROOT / "retail_mapper" / "v2" / "consensus_full_corpus_audit.v2.csv"
CONSENSUS_HTC = HERE / "output" / "consensus_htc_tagged.csv"
OUT_CSV = HERE / "output" / "priced_product_evidence_v1.csv"
OUT_SUMMARY = HERE / "output" / "priced_product_evidence_v1_summary.json"

try:
    from build_priced_consensus_bridge_v2 import (
        NON_FOOD_RE,
        RULE_B_PIDS,
        candidate_is_absent_claim,
        candidate_occurs_as_component,
        category_identity_hints,
        category_target_prefixes,
        normalize_display,
        path_starts,
        phrase_key,
        split_path,
        title_pid_keys,
        token_set,
        tokens,
    )
except ImportError:  # pragma: no cover - allows module import from tests
    from recipe_mapper.v1.build_priced_consensus_bridge_v2 import (  # type: ignore
        NON_FOOD_RE,
        RULE_B_PIDS,
        candidate_is_absent_claim,
        candidate_occurs_as_component,
        category_identity_hints,
        category_target_prefixes,
        normalize_display,
        path_starts,
        phrase_key,
        split_path,
        title_pid_keys,
        token_set,
        tokens,
    )


PATH_SEP = " > "

MAJOR_NON_FOOD_CATEGORY_RE = re.compile(
    r"\b("
    r"home improvement|plumbing|water filtration|water softeners?|water softener salt|"
    r"health and medicine|vitamins? and supplements?|dietary supplements?|"
    r"personal care|beauty|oral care|pet supplies?|pets?|cat treats?|dog treats?|"
    r"lawn and garden|household essentials|cleaning supplies"
    r")\b",
    re.I,
)

COMPONENT_CONTEXT_RE = re.compile(
    r"\b(made with|with|contains|containing|flavored|flavour(?:ed)?|"
    r"infused|filled with|covered|coated)\b",
    re.I,
)

TITLE_FLAVOR_CONTEXT_RE = re.compile(
    r"\b(flavor(?:ed)?|flavour(?:ed)?|with|made with|contains|infused|"
    r"variety pack|assorted|combo)\b",
    re.I,
)

WEAK_IDENTITY_SINGLETONS = {
    "almond", "almonds", "apple", "apples", "banana", "bananas",
    "butter", "caramel", "chocolate", "cinnamon", "coconut", "garlic",
    "honey", "lemon", "lime", "mango", "mint", "orange", "pecan",
    "pecans", "peach", "peanut", "strawberry", "vanilla",
}

GENERIC_COMPOSITE_PIDS = {
    "Sauce", "Soup", "Salsa", "Dip", "Sandwich", "Salad", "Pizza",
    "Composite Dish", "Single Entree", "Family Entree", "Pasta Dish",
}

PLAIN_FRUIT_PIDS = {
    "Apples", "Apricots", "Bananas", "Blackberries", "Blueberries",
    "Banana Slices", "Cherries", "Cranberries", "Grapes", "Mango",
    "Mangoes", "Oranges", "Peaches", "Pineapple", "Raspberries",
    "Strawberries",
}

PLAIN_NUT_SEED_PIDS = {
    "Almonds", "Cashews", "Hazelnuts", "Macadamia Nuts", "Peanuts",
    "Pecans", "Pine Nuts", "Pistachios", "Walnuts", "Pumpkin Seeds",
    "Sesame Seeds", "Sunflower Seeds",
}

FRUIT_PID_TOKENS = {
    "apple", "apricot", "banana", "blackberry", "blueberry", "cherry",
    "cranberry", "grape", "mango", "orange", "peach", "pineapple",
    "raspberry", "strawberry",
}

NUT_SEED_PID_TOKENS = {
    "almond", "cashew", "hazelnut", "macadamia", "peanut", "pecan",
    "pistachio", "walnut", "seed",
}

SWEET_COATED_COMPONENT_RE = re.compile(
    r"\b(chocolate|milk chocolate|dark chocolate|white chocolate|candy|"
    r"caramel|yogurt[-\s]*covered|covered|coated|peanut butter chips?)\b",
    re.I,
)

MIX_OR_TOPPER_RE = re.compile(
    r"\b(salad toppers?|trail mix|snack mix|party mix|cranberries|raisins)\b",
    re.I,
)


def norm_tokens(text: str) -> set[str]:
    return set(tokens(text or "", drop_stop=True, singular=True))


def pipe_values(text: str) -> list[str]:
    if not text:
        return []
    parts = re.split(r"\s*(?:\||>|;|,)\s*", text)
    return [p.strip() for p in parts if p.strip()]


def title_contains_phrase(title: str, phrase: str) -> bool:
    key = phrase_key(phrase)
    if not key:
        return False
    return re.search(rf"\b{re.escape(key)}\b", normalize_display(title)) is not None


def retailer_category_text(product: Mapping[str, object]) -> str:
    return " ".join(str(product.get(k) or "") for k in ("category_path_walmart", "category_path"))


def extended_category_target_prefixes(title: str, category: str) -> list[str]:
    prefixes = list(category_target_prefixes(title, category))
    blob = f"{title} {category}".lower()
    if re.search(r"\btoaster\s+(?:pastr(?:y|ies)|treats?)\b|pop-?tarts?", blob):
        prefixes.append("Bakery > Toaster Pastries")
    if re.search(r"\bsundae\s+cones?\b|\bice\s*cream\s+cones?\b", blob):
        prefixes.extend(["Frozen > Ice Cream", "Frozen > Desserts"])
    if re.search(r"\bfrozen\s+dessert\b", blob):
        prefixes.extend(["Frozen > Desserts", "Frozen > Ice Cream"])
    if re.search(r"\bcandy\b|chocolate candy|share pack", blob):
        prefixes.extend(["Snack > Candy", "Snack > Chocolate Candy"])
    return list(dict.fromkeys(prefixes))


def extended_category_identity_hints(title: str, category: str) -> list[str]:
    blob = f"{title} {category}".lower()
    hints = list(category_identity_hints(title, category))
    if re.search(r"\btomato\s+juice\b", blob):
        hints.insert(0, "Tomato Juice")
    if re.search(r"\b(?:lemon|vanilla|almond|coconut|coffee)?\s*extract\b", blob):
        hints.append("Extract")
    if re.search(r"\bcandy\s+bars?\b", blob):
        hints.insert(0, "Candy Bar")
    elif re.search(r"\bcandy\b", blob):
        hints.append("Candy")
    if re.search(r"\bprotein[-\s]*packed\s+drink\s+shakes?\b|\bprotein\s+shake\b", blob):
        hints.insert(0, "Protein Shake")
    return list(dict.fromkeys(hints))


@dataclass(frozen=True)
class EvidenceConcept:
    pid: str
    canonical: str
    modifier: str = ""
    count: int = 0
    sample_title: str = ""
    modal_category: str = ""
    modal_bfc: str = ""
    htc_prefixes: frozenset[str] = field(default_factory=frozenset)
    variants: frozenset[str] = field(default_factory=frozenset)
    flavors: frozenset[str] = field(default_factory=frozenset)
    forms: frozenset[str] = field(default_factory=frozenset)
    processing: frozenset[str] = field(default_factory=frozenset)
    claims: frozenset[str] = field(default_factory=frozenset)
    components: frozenset[str] = field(default_factory=frozenset)
    reference_tokens: frozenset[str] = field(default_factory=frozenset)
    avg_confidence: float = 0.0
    max_match_score: float = 0.0
    review_flag_count: int = 0
    override_count: int = 0
    source_conflict_count: int = 0


@dataclass
class EvidenceIndex:
    concepts: list[EvidenceConcept]
    by_pid_key: dict[str, list[EvidenceConcept]]
    by_direct_pid_key: dict[str, list[EvidenceConcept]]
    pid_keys: set[str]
    pid_keys_by_last: dict[str, list[str]]


@dataclass
class EvidenceScore:
    concept: EvidenceConcept
    source: str
    identity_score: float = 0.0
    category_score: float = 0.0
    facet_score: float = 0.0
    component_score: float = 0.0
    reference_score: float = 0.0
    provenance_score: float = 0.0
    htc_score: float = 0.0
    hard_vetoes: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)

    @property
    def total(self) -> float:
        return (
            self.identity_score
            + self.category_score
            + self.facet_score
            + self.component_score
            + self.reference_score
            + self.provenance_score
            + self.htc_score
        )


@dataclass
class EvidenceDecision:
    rowid: str
    taxonomy_status: str
    nutrition_status: str
    proposed_pid: str = ""
    proposed_canonical: str = ""
    proposed_modifier: str = ""
    total_score: float = 0.0
    identity_score: float = 0.0
    category_score: float = 0.0
    facet_score: float = 0.0
    component_score: float = 0.0
    reference_score: float = 0.0
    provenance_score: float = 0.0
    htc_score: float = 0.0
    hard_vetoes: str = ""
    runner_up: str = ""
    evidence: str = ""
    existing_pid: str = ""
    existing_canonical: str = ""
    existing_modifier: str = ""
    existing_bridge_status: str = ""


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


def concept_index(concepts: Iterable[EvidenceConcept]) -> EvidenceIndex:
    concept_list = list(concepts)
    by_pid_key: dict[str, list[EvidenceConcept]] = defaultdict(list)
    by_direct_pid_key: dict[str, list[EvidenceConcept]] = defaultdict(list)
    for concept in concept_list:
        key = phrase_key(concept.pid)
        if key:
            by_pid_key[key].append(concept)
            by_direct_pid_key[key].append(concept)
        if concept.pid in RULE_B_PIDS:
            mod_key = phrase_key((concept.modifier or "").split(PATH_SEP)[0])
            if mod_key and mod_key != key:
                by_pid_key[mod_key].append(concept)
    pid_keys = set(by_pid_key)
    by_last: dict[str, list[str]] = defaultdict(list)
    for key in pid_keys:
        parts = key.split()
        if parts:
            by_last[parts[-1]].append(key)
    for keys in by_last.values():
        keys.sort(key=lambda k: (-len(k.split()), k))
    return EvidenceIndex(
        concepts=concept_list,
        by_pid_key=dict(by_pid_key),
        by_direct_pid_key=dict(by_direct_pid_key),
        pid_keys=pid_keys,
        pid_keys_by_last=dict(by_last),
    )


def load_evidence_index(audit_path: Path = AUDIT, htc_path: Path = CONSENSUS_HTC) -> EvidenceIndex:
    htc_by_fdc = load_htc_by_fdc(htc_path)
    grouped: dict[tuple[str, str, str], dict[str, object]] = {}
    with audit_path.open(encoding="utf-8", errors="replace", newline="") as handle:
        for row in csv.DictReader(handle):
            pid = (row.get("product_identity_fixed") or "").strip()
            canonical = (row.get("canonical_path") or "").strip()
            if not pid or not canonical:
                continue
            raw_modifier = (row.get("modifier") or "").split(PATH_SEP)[0].strip()
            modifier = raw_modifier if pid in RULE_B_PIDS else ""
            key = (pid, canonical, modifier)
            entry = grouped.setdefault(key, {
                "count": 0,
                "sample_title": "",
                "category": Counter(),
                "bfc": Counter(),
                "htc": Counter(),
                "variant": Counter(),
                "flavor": Counter(),
                "form": Counter(),
                "processing": Counter(),
                "claims": Counter(),
                "components": Counter(),
                "reference_tokens": Counter(),
                "confidence_sum": 0.0,
                "confidence_n": 0,
                "max_match_score": 0.0,
                "review_flag_count": 0,
                "override_count": 0,
                "source_conflict_count": 0,
            })
            entry["count"] = int(entry["count"]) + 1
            if not entry["sample_title"]:
                entry["sample_title"] = (row.get("title") or "").strip()
            category = (row.get("category_path_fixed") or row.get("category_path_original") or "").strip()
            bfc = (row.get("branded_food_category_corrected") or row.get("branded_food_category") or "").strip()
            if category:
                entry["category"][category] += 1
            if bfc:
                entry["bfc"][bfc] += 1
            htc = htc_by_fdc.get((row.get("fdc_id") or "").strip(), "")
            if len(htc) >= 2:
                entry["htc"][htc[:2]] += 1
            for field, bucket in (
                ("variant", "variant"),
                ("flavor", "flavor"),
                ("form_texture_cut", "form"),
                ("processing_storage", "processing"),
                ("claims", "claims"),
                ("components", "components"),
            ):
                for value in pipe_values(row.get(field) or ""):
                    entry[bucket][value] += 1
            ref_blob = " ".join(
                row.get(col) or ""
                for col in ("fndds_desc", "sr28_desc", "esha_desc", "matched_key")
            )
            for tok in norm_tokens(ref_blob):
                entry["reference_tokens"][tok] += 1
            try:
                conf = float(row.get("confidence") or 0)
            except ValueError:
                conf = 0.0
            if conf:
                entry["confidence_sum"] = float(entry["confidence_sum"]) + conf
                entry["confidence_n"] = int(entry["confidence_n"]) + 1
            try:
                match_score = float(row.get("match_score") or 0)
            except ValueError:
                match_score = 0.0
            entry["max_match_score"] = max(float(entry["max_match_score"]), match_score)
            if (row.get("review_flags") or "").strip():
                entry["review_flag_count"] = int(entry["review_flag_count"]) + 1
            if (row.get("override_source") or "").strip():
                entry["override_count"] = int(entry["override_count"]) + 1
            if (row.get("source_conflict_action") or row.get("source_conflict_note") or "").strip():
                entry["source_conflict_count"] = int(entry["source_conflict_count"]) + 1

    concepts: list[EvidenceConcept] = []
    for (pid, canonical, modifier), entry in grouped.items():
        conf_n = int(entry["confidence_n"])
        avg_conf = float(entry["confidence_sum"]) / conf_n if conf_n else 0.0
        concepts.append(EvidenceConcept(
            pid=pid,
            canonical=canonical,
            modifier=modifier,
            count=int(entry["count"]),
            sample_title=str(entry["sample_title"]),
            modal_category=entry["category"].most_common(1)[0][0] if entry["category"] else "",
            modal_bfc=entry["bfc"].most_common(1)[0][0] if entry["bfc"] else "",
            htc_prefixes=frozenset(k for k, _ in entry["htc"].most_common(8)),
            variants=frozenset(k for k, _ in entry["variant"].most_common(20)),
            flavors=frozenset(k for k, _ in entry["flavor"].most_common(20)),
            forms=frozenset(k for k, _ in entry["form"].most_common(20)),
            processing=frozenset(k for k, _ in entry["processing"].most_common(20)),
            claims=frozenset(k for k, _ in entry["claims"].most_common(20)),
            components=frozenset(k for k, _ in entry["components"].most_common(20)),
            reference_tokens=frozenset(k for k, _ in entry["reference_tokens"].most_common(80)),
            avg_confidence=avg_conf,
            max_match_score=float(entry["max_match_score"]),
            review_flag_count=int(entry["review_flag_count"]),
            override_count=int(entry["override_count"]),
            source_conflict_count=int(entry["source_conflict_count"]),
        ))
    return concept_index(concepts)


def add_candidates_from_pool(
    out: dict[tuple[str, str, str], tuple[EvidenceConcept, str]],
    pool: list[EvidenceConcept],
    source: str,
    *,
    prefixes: list[str],
    cap: int = 100,
) -> None:
    if prefixes:
        matching = [concept for concept in pool if path_starts(concept.canonical, prefixes)]
        if matching:
            pool = matching
    if len(pool) > cap:
        pool = sorted(pool, key=lambda c: -c.count)[:cap]
    for concept in pool:
        out[(concept.pid, concept.canonical, concept.modifier)] = (concept, source)


def candidate_concepts(product: Mapping[str, object], index: EvidenceIndex) -> list[tuple[EvidenceConcept, str]]:
    title = str(product.get("name") or product.get("title") or "")
    category = retailer_category_text(product)
    prefixes = extended_category_target_prefixes(title, category)
    out: dict[tuple[str, str, str], tuple[EvidenceConcept, str]] = {}

    for pid_key, source in title_pid_keys(title, index).items():  # type: ignore[arg-type]
        add_candidates_from_pool(out, index.by_pid_key.get(pid_key, []), source, prefixes=prefixes)

    for hint in extended_category_identity_hints(title, category):
        add_candidates_from_pool(
            out,
            index.by_direct_pid_key.get(phrase_key(hint), []),
            "category_identity_hint",
            prefixes=prefixes,
            cap=160,
        )

    existing_pid = str(product.get("consensus_pid") or "").strip()
    if existing_pid:
        pool = index.by_direct_pid_key.get(phrase_key(existing_pid), [])
        add_candidates_from_pool(out, pool, "existing_bridge", prefixes=prefixes, cap=80)

    return list(out.values())


def facet_token_hits(title_tokens: set[str], values: Iterable[str]) -> set[str]:
    hits: set[str] = set()
    for value in values:
        value_tokens = norm_tokens(value)
        if value_tokens and value_tokens.issubset(title_tokens):
            hits.add(value)
    return hits


def score_candidate(product: Mapping[str, object], concept: EvidenceConcept, source: str) -> EvidenceScore:
    title = str(product.get("name") or product.get("title") or "")
    category = retailer_category_text(product)
    title_norm = normalize_display(title)
    title_tokens = token_set(title)
    pid_key = phrase_key(concept.pid)
    pid_parts = pid_key.split()
    pid_tokens = set(pid_parts)
    prefixes = extended_category_target_prefixes(title, category)
    score = EvidenceScore(concept=concept, source=source)

    if source.startswith("title_contiguous"):
        span_len = int(source.rsplit(":", 1)[1])
        score.identity_score += min(35, 16 + 5 * span_len)
        score.evidence.append(f"identity:{source}")
    elif source.startswith("title_token_subset"):
        span_len = int(source.rsplit(":", 1)[1])
        score.identity_score += min(30, 14 + 4 * span_len)
        score.evidence.append(f"identity:{source}")
    elif source == "title_single_token":
        score.identity_score += 16
        score.evidence.append("identity:title_single_token")
    elif source == "category_identity_hint":
        score.identity_score += 30
        score.evidence.append("identity:category_hint")
    elif source == "existing_bridge":
        bridge_status = str(product.get("bridge_status") or "")
        score.identity_score += 20 if bridge_status in {"bridged", "manual"} else 8
        score.evidence.append(f"identity:existing_{bridge_status or 'unknown'}")

    if pid_tokens and pid_tokens.issubset(title_tokens):
        score.identity_score += 6
        score.evidence.append("identity:pid_tokens_in_title")
        if len(pid_tokens) > 1:
            score.identity_score += min(8, 3 * len(pid_tokens))
            score.evidence.append("identity:multi_token_specificity")

    if candidate_occurs_as_component(title_norm, concept.pid):
        score.component_score -= 25
        score.hard_vetoes.append("component_only_identity")
        score.evidence.append("component:component_phrase")

    if candidate_is_absent_claim(title_norm, concept.pid):
        score.component_score -= 30
        score.hard_vetoes.append("absent_claim_identity")
        score.evidence.append("component:absent_claim")

    if (
        len(pid_parts) == 1
        and pid_parts[0] in WEAK_IDENTITY_SINGLETONS
        and TITLE_FLAVOR_CONTEXT_RE.search(title_norm)
        and source != "category_identity_hint"
    ):
        score.component_score -= 12
        score.evidence.append("component:single_token_flavor_context")

    if (
        pid_key in {"cookie", "cookies", "cooky"}
        and re.search(r"\bcook(?:ie|y)\s+(?:n|and)\s+creme\b|\bcandy\b|\b(?:shake|drink|smoothie|protein)\b", title_norm)
        and not path_starts(concept.canonical, ["Bakery > Cookies", "Snack > Cookies"])
    ):
        score.component_score -= 40
        score.evidence.append("component:cookie_flavor_or_candy_context")

    is_fruit_identity = concept.pid in PLAIN_FRUIT_PIDS or bool(pid_tokens & FRUIT_PID_TOKENS)
    is_nut_seed_identity = concept.pid in PLAIN_NUT_SEED_PIDS or bool(pid_tokens & NUT_SEED_PID_TOKENS)

    if is_fruit_identity and SWEET_COATED_COMPONENT_RE.search(title_norm):
        score.component_score -= 35
        score.hard_vetoes.append("sweet_coated_component_identity")
        score.evidence.append("component:sweet_coated_fruit_context")

    if is_nut_seed_identity and (
        SWEET_COATED_COMPONENT_RE.search(title_norm) or MIX_OR_TOPPER_RE.search(title_norm)
    ):
        score.component_score -= 35
        score.hard_vetoes.append("mix_or_sweet_component_identity")
        score.evidence.append("component:nut_seed_mix_or_sweet_context")

    if prefixes:
        if path_starts(concept.canonical, prefixes):
            score.category_score += 20
            score.evidence.append("category:target_prefix_agrees")
        else:
            score.category_score -= 25
            score.hard_vetoes.append("major_category_conflict")
            score.evidence.append(f"category:target_prefix_conflict={'|'.join(prefixes)}")
    else:
        cat_tokens = norm_tokens(category)
        modal_tokens = norm_tokens(f"{concept.modal_category} {concept.modal_bfc}")
        overlap = len(cat_tokens & modal_tokens)
        if overlap:
            score.category_score += min(10, 3 + overlap)
            score.evidence.append(f"category:modal_overlap={overlap}")

    facet_hits: list[str] = []
    for label, values, points in (
        ("variant", concept.variants, 4),
        ("form", concept.forms, 4),
        ("processing", concept.processing, 4),
        ("claims", concept.claims, 2),
    ):
        hits = facet_token_hits(title_tokens, values)
        if hits:
            score.facet_score += min(8, len(hits) * points)
            facet_hits.append(f"{label}={','.join(sorted(hits)[:3])}")
    flavor_hits = facet_token_hits(title_tokens, concept.flavors)
    if flavor_hits:
        score.facet_score += min(5, len(flavor_hits) * 2)
        facet_hits.append(f"flavor={','.join(sorted(flavor_hits)[:3])}")
    if concept.modifier and facet_token_hits(title_tokens, [concept.modifier]):
        score.facet_score += 5
        facet_hits.append(f"modifier={concept.modifier}")
    if facet_hits:
        score.evidence.append("facet:" + "|".join(facet_hits))

    component_hits = facet_token_hits(title_tokens, concept.components)
    if component_hits and concept.pid in GENERIC_COMPOSITE_PIDS:
        score.component_score += min(8, len(component_hits) * 2)
        score.evidence.append(f"component:support={','.join(sorted(component_hits)[:3])}")

    ref_overlap = len(pid_tokens & concept.reference_tokens)
    title_ref_overlap = len(title_tokens & concept.reference_tokens)
    if ref_overlap:
        score.reference_score += min(8, 3 + ref_overlap)
        score.evidence.append(f"reference:pid_overlap={ref_overlap}")
    if title_ref_overlap:
        score.reference_score += min(5, title_ref_overlap)
    if concept.max_match_score >= 80:
        score.reference_score += 2
        score.evidence.append("reference:high_match_score")

    if concept.avg_confidence:
        score.provenance_score += min(6, concept.avg_confidence * 6)
    if concept.override_count:
        score.provenance_score += 2
        score.evidence.append("provenance:override")
    if concept.review_flag_count:
        score.provenance_score -= min(4, concept.review_flag_count / max(concept.count, 1) * 20)
        score.evidence.append("provenance:review_flags")
    if concept.source_conflict_count:
        score.provenance_score -= min(5, concept.source_conflict_count / max(concept.count, 1) * 25)
        score.evidence.append("provenance:source_conflict")

    priced_htc = str(product.get("htc_code") or "")
    priced_prefix = priced_htc[:2] if len(priced_htc) >= 2 else ""
    priced_group = priced_htc[:1] if priced_htc else ""
    if priced_prefix and concept.htc_prefixes:
        if priced_prefix in concept.htc_prefixes:
            score.htc_score += 5
            score.evidence.append("htc:group_family_agrees")
        elif (
            priced_group
            and priced_group not in {"0", "N"}
            and not any(h.startswith(priced_group) for h in concept.htc_prefixes)
        ):
            score.htc_score -= 15
            if score.category_score < 20:
                score.hard_vetoes.append("htc_group_conflict")
            score.evidence.append(f"htc:group_conflict={priced_prefix}")
        else:
            score.htc_score -= 5
            score.evidence.append(f"htc:family_conflict={priced_prefix}")

    return score


def same_pid_runner_compatible(best: EvidenceScore, runner: EvidenceScore, prefixes: list[str]) -> bool:
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


def decide_product(product: Mapping[str, object], index: EvidenceIndex) -> EvidenceDecision:
    rowid = str(product.get("rowid") or "")
    title = str(product.get("name") or "")
    category = retailer_category_text(product)
    existing_pid = str(product.get("consensus_pid") or "")
    existing_canonical = str(product.get("consensus_canonical") or "")
    existing_modifier = str(product.get("consensus_modifier") or "")
    existing_status = str(product.get("bridge_status") or "")

    if NON_FOOD_RE.search(f"{title} {category}") or MAJOR_NON_FOOD_CATEGORY_RE.search(category):
        return EvidenceDecision(
            rowid=rowid,
            taxonomy_status="reject_non_food",
            nutrition_status="not_eligible",
            hard_vetoes="non_food",
            evidence="non_food_title_or_category",
            existing_pid=existing_pid,
            existing_canonical=existing_canonical,
            existing_modifier=existing_modifier,
            existing_bridge_status=existing_status,
        )

    scored = [score_candidate(product, c, source) for c, source in candidate_concepts(product, index)]
    scored.sort(key=lambda s: (
        -s.total,
        -s.identity_score,
        -s.category_score,
        -len(phrase_key(s.concept.pid).split()),
        -s.concept.count,
        s.concept.pid,
        s.concept.canonical,
    ))

    if not scored:
        return EvidenceDecision(
            rowid=rowid,
            taxonomy_status="quarantine_no_candidate",
            nutrition_status="not_eligible",
            evidence="no_consensus_candidate",
            existing_pid=existing_pid,
            existing_canonical=existing_canonical,
            existing_modifier=existing_modifier,
            existing_bridge_status=existing_status,
        )

    if existing_pid:
        top_total = scored[0].total
        existing_matches = [
            s for s in scored
            if phrase_key(s.concept.pid) == phrase_key(existing_pid)
            and not s.hard_vetoes
            and top_total - s.total <= 8
        ]
        if existing_matches:
            existing_matches.sort(key=lambda s: (-s.identity_score, -s.category_score, -s.total, -len(split_path(s.concept.canonical))))
            preferred = existing_matches[0]
            scored = [preferred] + [s for s in scored if s is not preferred]

    best = scored[0]
    runner = scored[1] if len(scored) > 1 else None
    margin = best.total - runner.total if runner else 999.0
    if runner and same_pid_runner_compatible(best, runner, extended_category_target_prefixes(title, category)):
        margin = 999.0
    vetoes = sorted(set(best.hard_vetoes))
    taxonomy_status = "approved_taxonomy"

    if vetoes:
        taxonomy_status = "quarantine_veto"
    elif best.identity_score < 25:
        if not (best.category_score >= 20 and best.htc_score > -15 and best.identity_score >= 14 and best.total >= 45):
            taxonomy_status = "quarantine_identity"
    elif best.total < 70:
        if not (best.category_score >= 20 and best.identity_score >= 25 and best.total >= 50):
            taxonomy_status = "quarantine_low_score"
    elif margin < 8:
        taxonomy_status = "quarantine_close_runner"

    # Keep manual/UPC bridged rows if the evidence did not actively veto them.
    if (
        taxonomy_status.startswith("quarantine")
        and existing_status in {"manual", "bridged"}
        and phrase_key(existing_pid) == phrase_key(best.concept.pid)
        and not vetoes
        and best.total >= 55
    ):
        taxonomy_status = "approved_existing"

    nutrition_status = "nutrition_anchor_eligible"
    if not taxonomy_status.startswith("approved"):
        nutrition_status = "not_eligible"
    elif best.reference_score < 8 or best.concept.source_conflict_count:
        nutrition_status = "taxonomy_only"

    runner_text = ""
    if runner:
        runner_text = (
            f"{runner.concept.pid} @ {runner.concept.canonical}"
            f" mod={runner.concept.modifier} ({runner.total:.1f})"
        )

    return EvidenceDecision(
        rowid=rowid,
        taxonomy_status=taxonomy_status,
        nutrition_status=nutrition_status,
        proposed_pid=best.concept.pid,
        proposed_canonical=best.concept.canonical,
        proposed_modifier=best.concept.modifier,
        total_score=best.total,
        identity_score=best.identity_score,
        category_score=best.category_score,
        facet_score=best.facet_score,
        component_score=best.component_score,
        reference_score=best.reference_score,
        provenance_score=best.provenance_score,
        htc_score=best.htc_score,
        hard_vetoes="|".join(vetoes),
        runner_up=runner_text,
        evidence="; ".join(best.evidence + ([f"runner_margin={margin:.1f}"] if runner else [])),
        existing_pid=existing_pid,
        existing_canonical=existing_canonical,
        existing_modifier=existing_modifier,
        existing_bridge_status=existing_status,
    )


def parse_rowids(value: str) -> set[int] | None:
    if not value:
        return None
    out = {int(part.strip()) for part in value.split(",") if part.strip()}
    return out or None


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


def write_csv(rows: list[dict[str, object]], decisions: list[EvidenceDecision], out_csv: Path) -> None:
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "rowid", "source", "upc", "name", "category_path", "category_path_walmart",
        "existing_bridge_status", "existing_pid", "existing_canonical", "existing_modifier",
        "taxonomy_status", "nutrition_status",
        "proposed_pid", "proposed_canonical", "proposed_modifier",
        "total_score", "identity_score", "category_score", "facet_score",
        "component_score", "reference_score", "provenance_score", "htc_score",
        "hard_vetoes", "runner_up", "evidence",
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
                "existing_modifier": decision.existing_modifier,
                "taxonomy_status": decision.taxonomy_status,
                "nutrition_status": decision.nutrition_status,
                "proposed_pid": decision.proposed_pid,
                "proposed_canonical": decision.proposed_canonical,
                "proposed_modifier": decision.proposed_modifier,
                "total_score": f"{decision.total_score:.1f}",
                "identity_score": f"{decision.identity_score:.1f}",
                "category_score": f"{decision.category_score:.1f}",
                "facet_score": f"{decision.facet_score:.1f}",
                "component_score": f"{decision.component_score:.1f}",
                "reference_score": f"{decision.reference_score:.1f}",
                "provenance_score": f"{decision.provenance_score:.1f}",
                "htc_score": f"{decision.htc_score:.1f}",
                "hard_vetoes": decision.hard_vetoes,
                "runner_up": decision.runner_up,
                "evidence": decision.evidence,
            })


def write_summary(rows: list[dict[str, object]], decisions: list[EvidenceDecision], out_summary: Path, elapsed_s: float) -> None:
    status_counts = Counter(d.taxonomy_status for d in decisions)
    nutrition_counts = Counter(d.nutrition_status for d in decisions)
    existing_counts = Counter(str(row.get("bridge_status") or "") for row in rows)
    changed = sum(
        1 for row, decision in zip(rows, decisions)
        if decision.taxonomy_status.startswith("approved")
        and str(row.get("consensus_pid") or "") != decision.proposed_pid
    )
    summary = {
        "rows_scored": len(rows),
        "elapsed_s": round(elapsed_s, 1),
        "taxonomy_status_counts": dict(status_counts.most_common()),
        "nutrition_status_counts": dict(nutrition_counts.most_common()),
        "existing_bridge_status_counts": dict(existing_counts.most_common()),
        "approved_existing_pid_changes": changed,
    }
    out_summary.parent.mkdir(parents=True, exist_ok=True)
    out_summary.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--priced-db", type=Path, default=PRICED_DB)
    parser.add_argument("--audit", type=Path, default=AUDIT)
    parser.add_argument("--consensus-htc", type=Path, default=CONSENSUS_HTC)
    parser.add_argument("--out", type=Path, default=OUT_CSV)
    parser.add_argument("--summary-out", type=Path, default=OUT_SUMMARY)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--rowids", default="")
    args = parser.parse_args()

    t0 = time.time()
    print("loading 42-column consensus evidence index...")
    index = load_evidence_index(args.audit, args.consensus_htc)
    print(f"  {len(index.concepts):,} concepts across {len(index.pid_keys):,} indexed identity keys")

    rows = load_priced_rows(args.priced_db, limit=args.limit, rowids=parse_rowids(args.rowids))
    print(f"loaded {len(rows):,} priced rows")

    decisions: list[EvidenceDecision] = []
    cache: dict[tuple[object, ...], EvidenceDecision] = {}
    for i, row in enumerate(rows, 1):
        cache_key = (
            row.get("name"),
            row.get("category_path"),
            row.get("category_path_walmart"),
            row.get("htc_code"),
            row.get("consensus_pid"),
            row.get("consensus_canonical"),
            row.get("consensus_modifier"),
            row.get("bridge_status"),
        )
        decision = cache.get(cache_key)
        if decision is None:
            decision = decide_product(row, index)
            cache[cache_key] = decision
        decisions.append(decision)
        if i % 25000 == 0:
            print(f"  scored {i:,} rows", flush=True)

    elapsed_s = time.time() - t0
    write_csv(rows, decisions, args.out)
    write_summary(rows, decisions, args.summary_out, elapsed_s)
    print(f"wrote {args.out}")
    print(f"wrote {args.summary_out}")
    print(json.dumps({
        "rows_scored": len(rows),
        "taxonomy_status_counts": dict(Counter(d.taxonomy_status for d in decisions).most_common()),
        "elapsed_s": round(elapsed_s, 1),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
