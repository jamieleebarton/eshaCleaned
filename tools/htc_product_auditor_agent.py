#!/usr/bin/env python3
"""HTC product auditor: propose and verify the correct HTC for branded/store rows.

This is the product-level auditor the full-code repair script was not.

Flow per product row:
  1. Gather every local signal we have: UPC, title/name, brand, search term,
     Walmart/category aisle, current HTC, raw HTC, tree identity/path/modifier,
     taxonomy authority/status, price/package metadata.
  2. Search the branded FDC consensus corpus for candidate HTC buckets using an
     inverted index over title/product identity/canonical path/retail leaf/BFC.
  3. Score candidates with independent signal families: product-title overlap,
     search-term overlap, category/aisle overlap, path/identity overlap, string
     similarity, current-code agreement, and source-authority penalties.
  4. Verify the proposed HTC with a second deterministic audit pass. Rows only
     become update candidates when the proposal has enough support and margin;
     otherwise they go to a machine evidence-expansion queue. No human-review
     state is emitted by this auditor.

Dry-run/output only. No production mutation happens here.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from itertools import combinations
from pathlib import Path
from typing import Any, Iterable

csv.field_size_limit(sys.maxsize)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONSENSUS = ROOT / "recipe_mapper" / "v1" / "output" / "consensus_htc_tagged.csv"
DEFAULT_PRODUCTS = ROOT / "recipe_mapper" / "v1" / "output" / "htc_coded_store_products_v1.csv"
DEFAULT_OUT_DIR = ROOT / "output" / "htc_product_auditor_agent"

STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "ct", "count", "fl", "for", "from", "gal",
    "gallon", "gram", "grams", "great", "in", "lb", "lbs", "liter", "ml", "no", "of", "or", "ounce",
    "ounces", "oz", "pack", "pk", "pkg", "pouch", "regular", "resealable", "size", "the", "to", "value",
    "with", "w", "walmart", "com", "homepage", "home", "page", "food", "foods", "brand", "brands",
}
WEAK_TOKENS = {
    "all", "best", "blend", "classic", "fresh", "gold", "golden", "good", "natural", "original",
    "premium", "pure", "real", "style", "traditional", "new", "old", "simple", "simply", "quality",
}
CRITICAL_IDENTITY_TOKENS = {
    "juice", "milk", "water", "cereal", "chicken", "beef", "pork", "turkey", "fish", "tuna", "salmon",
    "cheese", "yogurt", "bread", "bagel", "pasta", "noodle", "rice", "bean", "beans", "sauce", "salsa",
    "soup", "broth", "stock", "oil", "butter", "honey", "sugar", "flour", "cracker", "chips", "cookie",
    "coffee", "tea", "egg", "eggs", "apple", "orange", "cranberry", "grape",
}
EXCLUSIVE_FLAVOR_TOKENS = {
    "apple", "apricot", "banana", "berry", "blackberry", "blueberry", "cherry", "cranberry",
    "grape", "grapefruit", "guava", "kiwi", "lemon", "lime", "mango", "orange", "peach",
    "pear", "pineapple", "pomegranate", "raspberry", "strawberry", "tangerine", "tropical",
    "watermelon",
}
GENERIC_PATH_TOKENS = {
    "beverage", "food", "foods", "juice", "plain", "regular", "unspecified", "other",
}
CLAIM_OR_VARIETY_LEAF_TOKENS = {
    "100", "blend", "cocktail", "gala", "gravenstein", "honey", "honeycrisp", "lady",
    "nectar", "organic", "pink", "pure", "spiced", "unfiltered",
}
SIZE_RE = re.compile(r"\b\d+(?:\.\d+)?\b")
TOKEN_RE = re.compile(r"[a-z0-9]+(?:'[a-z0-9]+)?")


@dataclass
class HtcReference:
    htc_code: str
    row_count: int
    canonical_path: str
    retail_leaf_path: str
    product_identity: str
    branded_food_category: str
    title_samples: list[str]
    terms: list[str]
    path_terms: list[str]
    category_terms: list[str]
    similarity_terms: list[str]


@dataclass
class CandidateScore:
    htc_code: str
    score: float
    title_overlap: float
    search_overlap: float
    path_overlap: float
    aisle_overlap: float
    string_similarity: float
    current_match_bonus: float
    authority_penalty: float
    canonical_path: str
    retail_leaf_path: str
    product_identity: str
    row_count: int
    evidence_terms: list[str]
    missing_required_identity_terms: list[str]
    title_samples: list[str]


@dataclass
class AuditDecision:
    row_number: int
    upc: str
    name: str
    brand: str
    current_htc_code: str
    raw_htc_code: str
    proposed_htc_code: str
    proposed_canonical_path: str
    verifier_verdict: str
    confidence: str
    score: float
    margin: float
    reason: str
    signal_summary: dict[str, Any]
    top_candidates: list[dict[str, Any]]


def clean_htc(value: Any) -> str:
    return str(value or "").strip().lstrip("~")


def normalize_text(value: Any) -> str:
    text = str(value or "").lower()
    text = text.replace("&", " and ").replace("/", " ").replace(">", " ")
    text = SIZE_RE.sub(" ", text)
    return text


def tokens(value: Any, *, keep_weak: bool = False) -> set[str]:
    out: set[str] = set()
    for tok in TOKEN_RE.findall(normalize_text(value)):
        if len(tok) < 2:
            continue
        if tok in STOPWORDS:
            continue
        if not keep_weak and tok in WEAK_TOKENS:
            continue
        out.add(tok)
        if tok.endswith("ies") and len(tok) > 4:
            out.add(tok[:-3] + "y")
        elif tok.endswith("s") and len(tok) > 3:
            out.add(tok[:-1])
    return out


def weighted_tokens(row: dict[str, str]) -> dict[str, set[str]]:
    return {
        "title": tokens(" ".join([row.get("name", ""), row.get("tree_product_identity", "")])),
        "search": tokens(row.get("search_term", "")),
        "path": tokens(" ".join([row.get("tree_canonical_path", ""), row.get("tree_modifier", ""), row.get("category_path", "")])),
        "aisle": tokens(row.get("category_path_walmart", "")),
        "brand": tokens(row.get("brand", ""), keep_weak=True),
    }


def product_text(row: dict[str, str]) -> str:
    return " ".join(
        str(row.get(k) or "")
        for k in ["name", "search_term", "tree_product_identity", "tree_canonical_path", "tree_modifier", "category_path", "category_path_walmart"]
    )


def required_identity_terms(row: dict[str, str]) -> set[str]:
    strong = set()
    strong.update(tokens(row.get("search_term", "")))
    strong.update(tokens(row.get("tree_product_identity", "")))
    if not strong:
        strong.update(tokens(row.get("name", "")))
    return {tok for tok in strong if tok in CRITICAL_IDENTITY_TOKENS}


def title_identity_terms(row: dict[str, str]) -> set[str]:
    return tokens(" ".join([row.get("name", ""), row.get("tree_product_identity", "")]))


def read_csv_rows(path: Path, *, limit: int = 0) -> list[dict[str, str]]:
    rows = []
    with path.open(newline="", encoding="utf-8", errors="replace") as handle:
        for row in csv.DictReader(handle):
            rows.append(row)
            if limit and len(rows) >= limit:
                break
    return rows


def build_references(consensus_path: Path) -> tuple[dict[str, HtcReference], dict[str, set[str]], dict[str, int]]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    with consensus_path.open(newline="", encoding="utf-8", errors="replace") as handle:
        for row in csv.DictReader(handle):
            code = clean_htc(row.get("htc_code"))
            if code:
                grouped[code].append(row)

    refs: dict[str, HtcReference] = {}
    inv: dict[str, set[str]] = defaultdict(set)
    df: Counter[str] = Counter()
    temp_terms: dict[str, set[str]] = {}
    for code, rows in grouped.items():
        cp_counts = Counter(str(r.get("canonical_path") or "").strip() for r in rows if r.get("canonical_path"))
        leaf_counts = Counter(str(r.get("retail_leaf_path") or "").strip() for r in rows if r.get("retail_leaf_path"))
        identity_counts = Counter(str(r.get("product_identity_fixed") or "").strip() for r in rows if r.get("product_identity_fixed"))
        bfc_counts = Counter(str(r.get("branded_food_category") or "").strip() for r in rows if r.get("branded_food_category"))
        title_counts = Counter(str(r.get("title") or "").strip() for r in rows if r.get("title"))
        cp = cp_counts.most_common(1)[0][0] if cp_counts else ""
        leaf = leaf_counts.most_common(1)[0][0] if leaf_counts else cp
        identity = identity_counts.most_common(1)[0][0] if identity_counts else leaf.rsplit(">", 1)[-1].strip()
        bfc = bfc_counts.most_common(1)[0][0] if bfc_counts else ""
        term_set = set()
        path_terms = tokens(" ".join([cp, leaf, identity]))
        category_terms = tokens(bfc)
        term_set.update(path_terms)
        term_set.update(category_terms)
        for title, _ in title_counts.most_common(20):
            term_set.update(tokens(title))
        temp_terms[code] = term_set
        for tok in term_set:
            df[tok] += 1
        refs[code] = HtcReference(
            htc_code=code,
            row_count=len(rows),
            canonical_path=cp,
            retail_leaf_path=leaf,
            product_identity=identity,
            branded_food_category=bfc,
            title_samples=[title for title, _ in title_counts.most_common(5)],
            terms=sorted(term_set),
            path_terms=sorted(path_terms),
            category_terms=sorted(category_terms),
            similarity_terms=sorted(tokens(" ".join([
                identity,
                cp,
                leaf,
                " ".join(title for title, _ in title_counts.most_common(2)),
            ]))),
        )

    # Keep common terms available, but cap extremely broad ones out of candidate generation.
    max_df = max(150, int(len(refs) * 0.10))
    for code, term_set in temp_terms.items():
        for tok in term_set:
            if df[tok] <= max_df:
                inv[tok].add(code)
    for code, ref in refs.items():
        critical_path_terms = sorted(set(ref.path_terms) & CRITICAL_IDENTITY_TOKENS)
        for a, b in combinations(critical_path_terms, 2):
            inv[f"identity_pair:{a}|{b}"].add(code)
    return refs, inv, dict(df)


def candidate_codes(signal_tokens: dict[str, set[str]], inv: dict[str, set[str]], current_code: str, raw_code: str) -> set[str]:
    codes: set[str] = set()
    for family in ["title", "search", "path", "aisle"]:
        for tok in signal_tokens[family]:
            codes.update(inv.get(tok, set()))
    if current_code:
        codes.add(current_code)
    if raw_code:
        codes.add(raw_code)
    for key in identity_pair_keys(signal_tokens):
        codes.update(inv.get(key, set()))
    return codes


def identity_pair_keys(signal_tokens: dict[str, set[str]]) -> list[str]:
    product_terms = set().union(signal_tokens["title"], signal_tokens["search"], signal_tokens["path"], signal_tokens["aisle"])
    critical_terms = sorted(product_terms & CRITICAL_IDENTITY_TOKENS)
    return [f"identity_pair:{a}|{b}" for a, b in combinations(critical_terms, 2)]


def overlap_score(left: Iterable[str], right: Iterable[str]) -> tuple[float, list[str]]:
    lset = set(left)
    rset = set(right)
    if not lset or not rset:
        return 0.0, []
    hits = sorted(lset & rset)
    denom = math.sqrt(len(lset) * len(rset))
    return len(hits) / denom if denom else 0.0, hits


def token_similarity(left_text: str, right_text: str) -> float:
    left = tokens(left_text)
    right = tokens(right_text)
    if not left or not right:
        return 0.0
    hits = left & right
    return len(hits) / len(left | right)


def score_candidate(row: dict[str, str], ref: HtcReference, signal_tokens: dict[str, set[str]], df: dict[str, int]) -> CandidateScore:
    title_score, title_hits = overlap_score(signal_tokens["title"], ref.terms)
    search_score, search_hits = overlap_score(signal_tokens["search"], ref.terms)
    path_score, path_hits = overlap_score(signal_tokens["path"], ref.path_terms)
    aisle_score, aisle_hits = overlap_score(signal_tokens["aisle"], set(ref.path_terms) | set(ref.category_terms))
    product_terms = set().union(signal_tokens["title"], signal_tokens["search"], signal_tokens["path"], signal_tokens["aisle"])
    ref_similarity_terms = set(ref.similarity_terms)
    sim = len(product_terms & ref_similarity_terms) / len(product_terms | ref_similarity_terms) if product_terms and ref_similarity_terms else 0.0
    current = clean_htc(row.get("htc_code"))
    raw = clean_htc(row.get("raw_htc_code"))
    current_bonus = 0.0
    if ref.htc_code == current:
        current_bonus += 0.12
    if ref.htc_code == raw and raw != current:
        current_bonus += 0.04
    authority = str(row.get("tree_authority") or "") + " " + str(row.get("taxonomy_status") or "") + " " + str(row.get("htc_source") or "")
    penalty = 0.0
    if "evidence_reject" in authority or "raw_product_only" in authority or "priced_db_raw" in authority:
        if ref.htc_code == current:
            penalty += 0.16
    if str(row.get("non_food_path") or "") in {"1", "true", "True"} and ref.htc_code == current:
        penalty += 0.25
    evidence_terms = sorted(set(title_hits + search_hits + path_hits + aisle_hits), key=lambda t: (df.get(t, 999999), t))[:20]
    required_terms = required_identity_terms(row)
    candidate_terms = set(ref.path_terms) | set(ref.category_terms)
    missing_required = sorted(required_terms - candidate_terms)
    product_terms = set().union(signal_tokens["title"], signal_tokens["search"], signal_tokens["path"], signal_tokens["aisle"])
    title_terms = title_identity_terms(row)
    candidate_path_terms = set(ref.path_terms)
    for flavor in sorted((candidate_path_terms & EXCLUSIVE_FLAVOR_TOKENS) - product_terms):
        missing_required.append(f"incompatible_flavor:{flavor}")
    for flavor in sorted((candidate_path_terms & EXCLUSIVE_FLAVOR_TOKENS) - title_terms):
        missing_required.append(f"title_absent_flavor:{flavor}")
    extra_sparse_path_terms = sorted(candidate_path_terms - product_terms - GENERIC_PATH_TOKENS)
    if ref.row_count < 10 and extra_sparse_path_terms:
        missing_required.append("sparse_candidate_adds_absent_path_terms:" + ",".join(extra_sparse_path_terms[:5]))
    leaf_tail = str(ref.retail_leaf_path or "").rsplit(">", 1)[-1].lower()
    leaf_tail_tokens = set(TOKEN_RE.findall(leaf_tail))
    sparse_variant_terms = sorted(leaf_tail_tokens & CLAIM_OR_VARIETY_LEAF_TOKENS)
    if ref.row_count < 25 and sparse_variant_terms:
        missing_required.append("sparse_candidate_claim_or_variant_leaf:" + ",".join(sparse_variant_terms[:5]))
    if "juice" in required_terms:
        if "vinegar" in candidate_terms:
            missing_required.append("incompatible:vinegar")
        if not ({"juice", "beverage"} & candidate_terms):
            missing_required.append("path_missing:juice_or_beverage")
        for subtype in ("cider", "soda", "sparkling", "concentrate", "punch", "drink", "slush", "smoothie"):
            if subtype in candidate_path_terms and subtype not in product_terms:
                missing_required.append(f"incompatible:{subtype}")
    identity_penalty = 0.9 * len(missing_required)
    score = (
        4.0 * title_score
        + 2.5 * search_score
        + 2.0 * path_score
        + 1.5 * aisle_score
        + 1.4 * sim
        + math.log10(max(ref.row_count, 1)) * 0.08
        + current_bonus
        - penalty
        - identity_penalty
    )
    return CandidateScore(
        htc_code=ref.htc_code,
        score=round(score, 6),
        title_overlap=round(title_score, 6),
        search_overlap=round(search_score, 6),
        path_overlap=round(path_score, 6),
        aisle_overlap=round(aisle_score, 6),
        string_similarity=round(sim, 6),
        current_match_bonus=round(current_bonus, 6),
        authority_penalty=round(penalty, 6),
        canonical_path=ref.canonical_path,
        retail_leaf_path=ref.retail_leaf_path,
        product_identity=ref.product_identity,
        row_count=ref.row_count,
        evidence_terms=evidence_terms,
        missing_required_identity_terms=missing_required,
        title_samples=ref.title_samples[:3],
    )


def rank_candidates(row: dict[str, str], refs: dict[str, HtcReference], inv: dict[str, set[str]], df: dict[str, int], *, max_codes: int = 400) -> list[CandidateScore]:
    sig = weighted_tokens(row)
    current = clean_htc(row.get("htc_code"))
    raw = clean_htc(row.get("raw_htc_code"))
    codes = candidate_codes(sig, inv, current, raw)
    # Bound pathological broad-token rows without dropping current/raw.
    term_support: Counter[str] = Counter()
    weights = {"title": 9, "search": 7, "path": 5, "aisle": 3}
    for family, weight in weights.items():
        for tok in sig[family]:
            inverse_frequency = max(1, 100000 // max(df.get(tok, 100000), 1))
            for code in inv.get(tok, ()):
                term_support[code] += weight * inverse_frequency
    protected_codes: set[str] = set()
    for key in identity_pair_keys(sig):
        protected_codes.update(inv.get(key, set()))
    if term_support:
        keep = {code for code, _ in term_support.most_common(max_codes)}
        keep.update(protected_codes)
        if current:
            keep.add(current)
        if raw:
            keep.add(raw)
        codes = keep
    scored = [score_candidate(row, refs[code], sig, df) for code in codes if code in refs]
    return sorted(scored, key=lambda c: c.score, reverse=True)


def verify_decision(row: dict[str, str], candidates: list[CandidateScore]) -> tuple[str, str, float, str]:
    if not candidates:
        return "needs_more_evidence", "low", 0.0, "no_candidate_htc_found"
    top = candidates[0]
    second = candidates[1] if len(candidates) > 1 else None
    margin = top.score - (second.score if second else 0.0)
    current = clean_htc(row.get("htc_code"))
    raw = clean_htc(row.get("raw_htc_code"))
    evidence_term_count = len(top.evidence_terms)
    identity_terms_missing = bool(top.missing_required_identity_terms)
    strong_title = top.title_overlap >= 0.18 or top.search_overlap >= 0.25
    path_support = top.path_overlap >= 0.15 or top.aisle_overlap >= 0.12
    strong_score = top.score >= 2.25 and margin >= 0.20
    medium_score = top.score >= 1.65 and margin >= 0.12
    authority = " ".join(str(row.get(k) or "") for k in ["tree_authority", "taxonomy_status", "htc_source"])
    weak_current_authority = any(s in authority for s in ["evidence_reject", "raw_product_only", "priced_db_raw"])

    if identity_terms_missing:
        return "needs_more_evidence", "low", margin, "candidate_missing_required_identity_terms"
    if top.htc_code != current and top.row_count < 3:
        return "needs_more_evidence", "low", margin, "candidate_reference_support_too_sparse"
    if top.htc_code == current and (strong_score or (medium_score and evidence_term_count >= 2)):
        return "verified_current", "high" if strong_score else "medium", margin, "current_htc_supported_by_independent_signals"
    if top.htc_code != current and strong_score and strong_title and evidence_term_count >= 2:
        if weak_current_authority or raw == current or current:
            return "verified_update", "high", margin, "proposed_htc_beats_current_with_title_search_path_evidence"
    if top.htc_code != current and medium_score and strong_title and path_support and evidence_term_count >= 2:
        return "evidence_expansion_update_candidate", "medium", margin, "proposed_htc_supported_but_needs_more_machine_evidence"
    if top.htc_code == current:
        return "weak_current", "low", margin, "current_htc_is_top_candidate_but_support_is_weak"
    return "needs_more_evidence", "low", margin, "candidate_margin_or_signal_support_insufficient"


def audit_row(row: dict[str, str], row_number: int, refs: dict[str, HtcReference], inv: dict[str, set[str]], df: dict[str, int]) -> AuditDecision:
    candidates = rank_candidates(row, refs, inv, df)
    top = candidates[0] if candidates else None
    verdict, confidence, margin, reason = verify_decision(row, candidates)
    sig = weighted_tokens(row)
    return AuditDecision(
        row_number=row_number,
        upc=str(row.get("upc") or ""),
        name=str(row.get("name") or ""),
        brand=str(row.get("brand") or ""),
        current_htc_code=clean_htc(row.get("htc_code")),
        raw_htc_code=clean_htc(row.get("raw_htc_code")),
        proposed_htc_code=top.htc_code if top else "",
        proposed_canonical_path=top.canonical_path if top else "",
        verifier_verdict=verdict,
        confidence=confidence,
        score=top.score if top else 0.0,
        margin=round(margin, 6),
        reason=reason,
        signal_summary={
            "title_tokens": sorted(sig["title"]),
            "search_tokens": sorted(sig["search"]),
            "path_tokens": sorted(sig["path"]),
            "aisle_tokens": sorted(sig["aisle"]),
            "tree_authority": row.get("tree_authority"),
            "taxonomy_status": row.get("taxonomy_status"),
            "htc_source": row.get("htc_source"),
            "category_path": row.get("category_path"),
            "category_path_walmart": row.get("category_path_walmart"),
            "tree_product_identity": row.get("tree_product_identity"),
            "tree_canonical_path": row.get("tree_canonical_path"),
            "tree_modifier": row.get("tree_modifier"),
        },
        top_candidates=[asdict(c) for c in candidates[:5]],
    )


def write_outputs(decisions: list[AuditDecision], out_dir: Path) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    jsonl = out_dir / "audit_decisions.jsonl"
    with jsonl.open("w", encoding="utf-8") as handle:
        for d in decisions:
            handle.write(json.dumps(asdict(d), sort_keys=True) + "\n")
    csv_path = out_dir / "audit_decisions.csv"
    fieldnames = [
        "row_number", "upc", "name", "brand", "current_htc_code", "raw_htc_code", "proposed_htc_code",
        "proposed_canonical_path", "verifier_verdict", "confidence", "score", "margin", "reason",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for d in decisions:
            row = asdict(d)
            writer.writerow({k: row.get(k, "") for k in fieldnames})
    counts = Counter(d.verifier_verdict for d in decisions)
    updates = [d for d in decisions if d.verifier_verdict == "verified_update"]
    evidence_expansion_updates = [
        d for d in decisions if d.verifier_verdict == "evidence_expansion_update_candidate"
    ]
    summary = {
        "schema_version": 1,
        "agent": "htc_product_auditor_agent",
        "row_count": len(decisions),
        "verdict_counts": dict(sorted(counts.items())),
        "verified_update_count": len(updates),
        "evidence_expansion_update_candidate_count": len(evidence_expansion_updates),
        "production_writes": False,
        "jsonl": str(jsonl),
        "csv": str(csv_path),
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--consensus", type=Path, default=DEFAULT_CONSENSUS)
    parser.add_argument("--products", type=Path, default=DEFAULT_PRODUCTS)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--upc", action="append", default=[])
    parser.add_argument("--rowid", action="append", default=[])
    return parser


def selected_rows(path: Path, *, limit: int, upcs: set[str], rowids: set[str]) -> list[tuple[int, dict[str, str]]]:
    out: list[tuple[int, dict[str, str]]] = []
    with path.open(newline="", encoding="utf-8", errors="replace") as handle:
        for row_number, row in enumerate(csv.DictReader(handle), start=2):
            if upcs and str(row.get("upc") or "") not in upcs:
                continue
            if rowids and str(row.get("rowid") or "") not in rowids:
                continue
            out.append((row_number, row))
            if limit and len(out) >= limit and not upcs and not rowids:
                break
    return out


def main() -> int:
    args = build_parser().parse_args()
    refs, inv, df = build_references(args.consensus)
    rows = selected_rows(args.products, limit=args.limit, upcs=set(args.upc), rowids=set(args.rowid))
    decisions = [audit_row(row, row_number, refs, inv, df) for row_number, row in rows]
    summary = write_outputs(decisions, args.out_dir)
    summary["reference_htc_count"] = len(refs)
    summary["selected_count"] = len(rows)
    (args.out_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
