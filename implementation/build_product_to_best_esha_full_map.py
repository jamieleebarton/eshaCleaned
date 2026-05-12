from __future__ import annotations

import argparse
import csv
import json
import math
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import match_esha_to_products as matcher


ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "implementation" / "output"
PRODUCTS_DB = ROOT / "data" / "master_products.db"
ESHA_CSV = ROOT / "esha_cleaned.csv"
AGGREGATION_CSV = OUT_DIR / "esha_code_category_aggregation.csv"
CANONICAL_SURFACE_CSV = OUT_DIR / "canonical_surface_normalized_with_product_proxies_CLEANED.csv"
LEGACY_BEST_MAP_CSV = OUT_DIR / "product_to_best_esha_map.csv"
FIX_QUEUE_CSV = OUT_DIR / "esha_single_category_fix_queue.csv"
OUT_CSV = OUT_DIR / "product_to_best_esha_full_map.csv"
OUT_SUMMARY = OUT_DIR / "product_to_best_esha_full_map_summary.json"

FIELDNAMES = [
    "gtin_upc",
    "fdc_id",
    "product_description",
    "branded_food_category",
    "brand_owner",
    "brand_name",
    "best_esha_code",
    "best_esha_description",
    "best_esha_family",
    "score",
    "n_candidates",
    "assignment_source",
]

WEAK_FALLBACK_TOKENS = {
    "baby",
    "canned",
    "chunk",
    "chunks",
    "chopped",
    "cinnamon",
    "cultured",
    "diced",
    "fat",
    "flavor",
    "flavored",
    "fresh",
    "frozen",
    "halves",
    "jumbo",
    "large",
    "low",
    "medium",
    "mini",
    "natural",
    "naturally",
    "nonfat",
    "organic",
    "original",
    "piece",
    "pieces",
    "quality",
    "reduced",
    "sliced",
    "small",
    "stem",
    "stems",
    "sweetened",
    "unsweetened",
    "whole",
}

GENERIC_FAMILY_TOKENS = {
    "beverage",
    "broth",
    "cheese",
    "cream",
    "dessert",
    "dip",
    "dish",
    "drink",
    "food",
    "fruit",
    "grain",
    "juice",
    "meat",
    "milk",
    "mix",
    "oil",
    "pasta",
    "salad",
    "sauce",
    "seafood",
    "snack",
    "soup",
    "spread",
    "sweetener",
    "vegetable",
    "water",
}

SECONDARY_IDENTITY_TOKENS = {
    "cinnamon",
    "cultured",
    "fat",
    "free",
    "jumbo",
    "large",
    "low",
    "lowfat",
    "medium",
    "mini",
    "natural",
    "naturally",
    "nonfat",
    "original",
    "small",
    "skim",
    "sweetened",
    "unsweetened",
    "whole",
}

EXPLICIT_STATE_TOKENS = {
    "canned",
    "cooked",
    "condensed",
    "dried",
    "dry",
    "drained",
    "evaporated",
    "frozen",
    "powder",
    "roasted",
    "smoked",
}

COMPOUND_TOKEN_EXPANSIONS = {
    "almondmilk": {"almond", "milk"},
    "applesauce": {"apple", "sauce", "applesauce"},
    "cashewmilk": {"cashew", "milk"},
    "coconutmilk": {"coconut", "milk"},
    "goatcheese": {"goat", "cheese"},
    "hempmilk": {"hemp", "milk"},
    "oatmilk": {"oat", "milk"},
    "ricemilk": {"rice", "milk"},
    "spark": {"sparkling"},
    "sparkling": {"spark"},
    "soymilk": {"soy", "milk"},
}


def normalize_gtin(value: str) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def query_tokens(query: str) -> set[str]:
    clean = (
        (query or "")
        .replace("(", " ")
        .replace(")", " ")
        .replace("AND", " ")
        .replace("OR", " ")
        .replace("|", " ")
    )
    return {tok for tok in matcher.tokens_for(clean) if tok and tok not in matcher.STOPWORDS}


def expand_compound_tokens(tokens: Iterable[str]) -> frozenset[str]:
    expanded: set[str] = set(tokens)
    for token in list(expanded):
        expanded.update(COMPOUND_TOKEN_EXPANSIONS.get(token, ()))
    return frozenset(expanded)


def meaningful_tokens(tokens: Iterable[str], *, drop_family_tokens: bool = True) -> frozenset[str]:
    meaningful = set(expand_compound_tokens(tokens))
    meaningful = {tok for tok in meaningful if tok and tok not in matcher.STOPWORDS and tok not in WEAK_FALLBACK_TOKENS}
    if drop_family_tokens:
        meaningful = {tok for tok in meaningful if tok not in GENERIC_FAMILY_TOKENS}
    return frozenset(meaningful)


def candidate_identity_terms(profile: matcher.EshaProfile, core_tokens: frozenset[str]) -> frozenset[str]:
    identity = set(meaningful_tokens(profile.hard_terms))
    if not identity:
        identity = set(meaningful_tokens(core_tokens))
    return frozenset(identity)


@dataclass(frozen=True)
class Candidate:
    code: str
    description: str
    family: str
    tokens: frozenset[str]
    hard_terms: frozenset[str]
    identity_terms: frozenset[str]
    meaningful_terms: frozenset[str]
    categories: frozenset[str]
    category_support: int
    needs_fix: bool


def load_profiles() -> dict[str, matcher.EshaProfile]:
    profiles: dict[str, matcher.EshaProfile] = {}
    with ESHA_CSV.open(newline="", encoding="utf-8-sig", errors="replace") as handle:
        for row in csv.DictReader(handle):
            if "EshaCode" not in row and "Code" in row:
                row = {**row, "EshaCode": row.get("Code", "")}
            profile = matcher.profile_for(row)
            if not profile.code or profile.skip_reason:
                continue
            profiles[profile.code] = profile
    return profiles


def load_category_rows() -> dict[str, dict[str, int]]:
    by_code: dict[str, dict[str, int]] = defaultdict(dict)
    if not AGGREGATION_CSV.exists():
        return by_code
    with AGGREGATION_CSV.open(newline="", encoding="utf-8", errors="replace") as handle:
        reader = csv.DictReader((line.replace("\x00", "") for line in handle))
        for row in reader:
            if (row.get("signal") or "").strip() != "in_scope_category":
                continue
            code = (row.get("esha_code") or "").strip()
            category = (row.get("category") or "").strip().lower()
            if not code or not category:
                continue
            count = int((row.get("category_count") or "0").strip() or "0")
            by_code[code][category] = max(count, by_code[code].get(category, 0))
    return by_code


def load_bad_category_codes() -> set[str]:
    bad: set[str] = set()
    if not FIX_QUEUE_CSV.exists():
        return bad
    with FIX_QUEUE_CSV.open(newline="", encoding="utf-8", errors="replace") as handle:
        reader = csv.DictReader((line.replace("\x00", "") for line in handle))
        for row in reader:
            if (row.get("needs_fix") or "").strip() == "1":
                code = (row.get("esha_code") or "").strip()
                if code:
                    bad.add(code)
    return bad


def load_canonical_surface_tokens() -> dict[str, frozenset[str]]:
    by_code: dict[str, set[str]] = defaultdict(set)
    if not CANONICAL_SURFACE_CSV.exists():
        return {}
    with CANONICAL_SURFACE_CSV.open(newline="", encoding="utf-8", errors="replace") as handle:
        reader = csv.DictReader((line.replace("\x00", "") for line in handle))
        for row in reader:
            code = (row.get("esha_code") or "").strip()
            if not code:
                continue
            for field in ("canonical_surface", "canonical_normalized", "product_query"):
                by_code[code].update(matcher.tokens_for(row.get(field, "")))
    return {code: frozenset(tokens) for code, tokens in by_code.items() if tokens}


def build_candidates() -> tuple[dict[str, Candidate], dict[str, list[str]], dict[str, list[str]], dict[str, float]]:
    profiles = load_profiles()
    categories_by_code = load_category_rows()
    bad_category_codes = load_bad_category_codes()
    canonical_surface_tokens = load_canonical_surface_tokens()

    docfreq: Counter[str] = Counter()
    token_docs: dict[str, set[str]] = defaultdict(set)
    candidates: dict[str, Candidate] = {}
    category_to_codes: dict[str, list[str]] = defaultdict(list)
    family_to_codes: dict[str, list[str]] = defaultdict(list)

    for code, profile in profiles.items():
        category_tokens = set()
        categories = frozenset(categories_by_code.get(code, {}).keys())
        for category in categories:
            category_tokens.update(matcher.tokens_for(category))
        canonical_tokens = canonical_surface_tokens.get(code, frozenset())
        core_tokens = expand_compound_tokens(set(profile.tokens) | set(profile.hard_terms) | set(profile.fts_terms) | set(canonical_tokens))
        tokens = frozenset(set(core_tokens) | category_tokens)
        if not tokens:
            continue
        support = sum(categories_by_code.get(code, {}).values())
        candidate = Candidate(
            code=code,
            description=profile.description,
            family=profile.family,
            tokens=tokens,
            hard_terms=frozenset(profile.hard_terms),
            identity_terms=candidate_identity_terms(profile, frozenset(set(core_tokens) | set(canonical_tokens))),
            meaningful_terms=meaningful_tokens(core_tokens),
            categories=categories,
            category_support=support,
            needs_fix=code in bad_category_codes,
        )
        candidates[code] = candidate
        family_to_codes[profile.family].append(code)
        for category in categories:
            category_to_codes[category].append(code)
        for token in tokens:
            token_docs[token].add(code)

    for token, codes in token_docs.items():
        docfreq[token] = len(codes)
    n_docs = max(len(candidates), 1)
    idf = {token: math.log((1 + n_docs) / (1 + df)) + 1.0 for token, df in docfreq.items()}

    # Pass F: apply token-entropy weighting if data/token_entropy.csv is present.
    # High-entropy tokens (e.g. "apple" appearing across 24 ESHA categories) get
    # their effective IDF reduced; low-entropy informative tokens keep ~full IDF.
    # The CSV is produced by graph/queries/dump_token_entropy.py.
    token_entropy_csv = ROOT / "data" / "token_entropy.csv"
    if token_entropy_csv.exists():
        entropy_map: dict[str, float] = {}
        with token_entropy_csv.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                tok = (row.get("token") or "").strip()
                if not tok:
                    continue
                try:
                    entropy_map[tok] = float(row.get("entropy") or 0.0)
                except ValueError:
                    pass
        max_ent = max(entropy_map.values(), default=1.0) or 1.0
        weighted = 0
        for tok in list(idf.keys()):
            ent = entropy_map.get(tok)
            if ent is None:
                continue
            weight = max(0.1, 1.0 - ent / max_ent)
            idf[tok] = idf[tok] * weight
            weighted += 1
        print(f"[entropy-weight] applied to {weighted}/{len(idf)} tokens (max_entropy={max_ent:.3f})")
    return candidates, category_to_codes, family_to_codes, idf


def load_legacy_best_map() -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    if not LEGACY_BEST_MAP_CSV.exists():
        return out
    with LEGACY_BEST_MAP_CSV.open(newline="", encoding="utf-8", errors="replace") as handle:
        reader = csv.DictReader((line.replace("\x00", "") for line in handle))
        for row in reader:
            gtin = normalize_gtin(row.get("gtin_upc", ""))
            if gtin and gtin not in out:
                out[gtin] = row
    return out


def hinted_product_family(description: str, category: str) -> str:
    norm_category = (category or "").strip().lower()
    if norm_category in {
        "water",
        "powdered drinks",
        "non alcoholic beverages  ready to drink",
        "fruit & vegetable juice, nectars & fruit drinks",
        "energy, protein & muscle recovery drinks",
        "soda",
        "beer",
        "wine",
        "cocktail mixes",
        "sparkling water, seltzer water, tonic water & carbonated water",
        "carbonated soft drinks",
        "iced tea, lemonade, fruit drinks & punch",
        "coffee",
        "tea",
    }:
        return "beverage"
    if norm_category in {"milk additives"}:
        return "cream"
    if norm_category in {"cheese"}:
        return "cheese"
    if norm_category in {"granulated, brown & powdered sugar"}:
        return "sweetener"
    if norm_category in {
        "pasta by shape & type",
        "pasta dinners",
        "frozen dinners & entrees",
        "frozen appetizers & hors d'oeuvres",
        "stuffing",
        "frozen pizza",
        "soups, broths & bouillon",
        "rice & grain dishes",
    }:
        return "prepared_food"
    if norm_category in {"crackers & biscotti", "cookies & biscuits", "breads & buns", "cereal"}:
        return "grain"
    if norm_category in {
        "confectionery products",
        "candy",
        "chocolate",
        "cookies & biscotti",
        "cakes, cupcakes, snack cakes",
        "wholesome snacks",
        "cake, cookie & cupcake mixes",
        "pies, pastries, donuts",
        "frozen desserts & toppings",
        "ice cream & frozen yogurt",
        "chewing gum & mints",
        "snack, energy & granola bars",
        "snack mix, trail mix",
    }:
        return "dessert_snack"
    if norm_category in {"pretzels & salty snacks", "cereal bars & granola bars", "popcorn"}:
        return "grain"
    product_norm = matcher.normalize_text(description or "")
    product_tokens = [tok for tok in matcher.tokens_for(description or "") if tok and tok not in matcher.STOPWORDS]
    return matcher.detect_family(product_tokens, product_norm)


def product_rows() -> Iterable[tuple[str, str, str, str, str, str]]:
    sql = """
        SELECT gtin_upc, fdc_id, description, brand_owner, brand_name, branded_food_category
        FROM products
        ORDER BY gtin_upc
    """
    con = sqlite3.connect(PRODUCTS_DB)
    try:
        yield from con.execute(sql)
    finally:
        con.close()


def score_candidate(
    *,
    candidate: Candidate,
    product_norm: str,
    token_set: frozenset[str],
    meaningful_product_tokens: frozenset[str],
    product_family: str,
    category_norm: str,
    idf: dict[str, float],
) -> tuple[float, int, int] | None:
    required_identity_terms = candidate.identity_terms - SECONDARY_IDENTITY_TOKENS
    if not required_identity_terms:
        required_identity_terms = candidate.identity_terms
    shared_identity = meaningful_product_tokens & required_identity_terms
    shared_meaningful = meaningful_product_tokens & candidate.meaningful_terms
    if required_identity_terms:
        if not shared_identity:
            return None
    elif not shared_meaningful:
        return None

    # Pass K.3 — subtype gate. Skip candidates whose subtype is structurally
    # incompatible with the product's. E.g. roasted ⊥ butter for nut_seed.
    if not matcher.subtype_compatible(token_set, candidate.tokens, product_family):
        return None

    hard_hits = sum(1 for term in candidate.hard_terms if matcher.product_has_term(product_norm, set(token_set), term))
    overlap_score = sum(idf.get(tok, 1.0) for tok in shared_meaningful)
    score = overlap_score
    score += 2.0 * len(shared_identity)
    score += 1.5 * hard_hits
    if candidate.family == product_family:
        score += 0.75
    else:
        score -= 2.0
    if category_norm and category_norm in candidate.categories:
        score += 0.5
    if candidate.needs_fix:
        score -= 0.5
    mismatched_states = (candidate.meaningful_terms & EXPLICIT_STATE_TOKENS) - token_set
    if mismatched_states:
        score -= 1.25 * len(mismatched_states)
    score += math.log1p(candidate.category_support) * 0.02

    # Pass K.2 — over-specific attractor penalty. ESHA codes whose descriptions
    # carry many distinctive tokens NOT in the product (e.g. "Cereal, granola,
    # Ginger Zing, with cashews" matched by a plain GRANOLA product) get
    # penalized proportional to how many extra distinctive tokens they have.
    extra_tokens = (candidate.meaningful_terms - meaningful_product_tokens) - matcher.GENERIC_FILLER_TOKENS
    if extra_tokens:
        overspec_penalty = 0.35 * sum(idf.get(tok, 1.0) for tok in extra_tokens)
        # Cap penalty so it never drops the score below a positive shared base
        overspec_penalty = min(overspec_penalty, 0.6 * max(overlap_score, 0.0))
        score -= overspec_penalty

    return score, hard_hits, len(shared_meaningful)


def choose_best_candidate(
    description: str,
    category: str,
    candidates: dict[str, Candidate],
    category_to_codes: dict[str, list[str]],
    family_to_codes: dict[str, list[str]],
    idf: dict[str, float],
    pc_candidate_pool: dict[str, set[str]] | None = None,
) -> tuple[Candidate | None, float, int, str]:
    product_norm = matcher.normalize_text(description or "")
    product_tokens = [tok for tok in matcher.tokens_for(description or "") if tok and tok not in matcher.STOPWORDS]
    token_set = expand_compound_tokens(product_tokens)
    meaningful_product_tokens = meaningful_tokens(token_set)
    product_family = hinted_product_family(description, category)
    category_norm = (category or "").strip().lower()

    # Pass M — PC-anchored candidate pool. The product's branded_food_category
    # constrains which ESHA codes are even considered. ESHAs have canonical PCs
    # (learned from trusted rows or derived from description); a product in
    # PC=X can only match codes whose canonical PC is X (or in the same
    # compatibility group). This is the structural fix — no token overlap
    # can route a CHEWING GUM product to a FRESH APPLE ESHA, because fresh
    # apples are NOT in the chewing-gum candidate pool.
    pool: list[str] = []
    source: str
    if pc_candidate_pool:
        from pc_anchored_assignment import expand_pc_pool as _expand_pc
        pc_raw = (category or "").strip()
        candidate_codes = _expand_pc(pc_raw, pc_candidate_pool, minimum_codes=20)
        pool = [c for c in candidate_codes if c in candidates]
        if pool:
            source = "pc_anchored"

    if not pool:
        # Fallback to legacy logic for sparse PCs / new PCs
        category_pool = category_to_codes.get(category_norm, [])
        family_pool = family_to_codes.get(product_family, [])
        if category_pool and family_pool:
            pool = [code for code in category_pool if candidates[code].family == product_family] or list(category_pool)
            source = "fallback_category_family"
        elif category_pool:
            pool = list(category_pool)
            source = "fallback_category"
        elif family_pool:
            pool = list(family_pool)
            source = "fallback_family"
        else:
            pool = list(candidates.keys())
            source = "fallback_global"

    best: Candidate | None = None
    best_score = float("-inf")
    best_hard_hits = -1
    best_shared = -1
    for code in pool:
        candidate = candidates[code]
        scored = score_candidate(
            candidate=candidate,
            product_norm=product_norm,
            token_set=token_set,
            meaningful_product_tokens=meaningful_product_tokens,
            product_family=product_family,
            category_norm=category_norm,
            idf=idf,
        )
        if scored is None:
            continue
        score, hard_hits, shared_count = scored
        if best is None or (
            score,
            hard_hits,
            shared_count,
            -len(candidate.tokens),
            -int(candidate.code) if candidate.code.isdigit() else -10**9,
        ) > (
            best_score,
            best_hard_hits,
            best_shared,
            -len(best.tokens),
            -int(best.code) if best.code.isdigit() else -10**9,
        ):
            best = candidate
            best_score = score
            best_hard_hits = hard_hits
            best_shared = shared_count
    return best, best_score, len(pool), source


def build_full_map() -> dict[str, int | str]:
    candidates, category_to_codes, family_to_codes, idf = build_candidates()
    legacy = load_legacy_best_map()

    # Pass M — load PC-anchored candidate pool. If the cache is missing, the
    # matcher falls back to the legacy category/family pool logic. When
    # available, every product is restricted to ESHA codes whose canonical PC
    # matches its branded_food_category — the structural fix that prevents
    # cross-category attractor pollution (e.g., gum products landing on fresh
    # apple codes).
    pc_candidate_pool: dict[str, set[str]] = {}
    pc_cache = ROOT / "graph" / "cache" / "esha_canonical_pcs.json"
    if pc_cache.exists():
        import sys as _sys
        _sys.path.insert(0, str(ROOT / "implementation"))
        from pc_anchored_assignment import load_canonical_pcs as _load_pcs
        canonical = _load_pcs(pc_cache)
        for code, pcs in canonical.items():
            for pc, _share in pcs:
                pc_candidate_pool.setdefault(pc, set()).add(code)
        print(f"[pass-M] PC-anchored pool loaded: {len(pc_candidate_pool):,} PCs, {sum(len(s) for s in pc_candidate_pool.values()):,} (PC,code) edges")
    else:
        print("[pass-M] WARNING: esha_canonical_pcs.json not found — running with legacy pool logic")

    assigned_legacy = 0
    assigned_fallback = 0
    unassigned = 0
    source_counts: Counter[str] = Counter()
    rows_written = 0

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    tmp = OUT_CSV.with_suffix(".csv.tmp")
    with tmp.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        for gtin, fdc_id, description, brand_owner, brand_name, category in product_rows():
            norm_gtin = normalize_gtin(gtin)
            legacy_row = legacy.get(norm_gtin)
            if legacy_row and legacy_row.get("best_esha_code"):
                legacy_code = legacy_row.get("best_esha_code", "")
                legacy_candidate = candidates.get(legacy_code)
                if legacy_candidate is not None:
                    product_norm = matcher.normalize_text(description or "")
                    token_set = expand_compound_tokens(
                        tok for tok in matcher.tokens_for(description or "") if tok and tok not in matcher.STOPWORDS
                    )
                    meaningful_product_tokens = meaningful_tokens(token_set)
                    product_family = hinted_product_family(description, category)
                    category_norm = (category or "").strip().lower()
                    legacy_scored = score_candidate(
                        candidate=legacy_candidate,
                        product_norm=product_norm,
                        token_set=token_set,
                        meaningful_product_tokens=meaningful_product_tokens,
                        product_family=product_family,
                        category_norm=category_norm,
                        idf=idf,
                    )
                    if legacy_scored is not None:
                        source = "legacy_best_map"
                        writer.writerow(
                            {
                                "gtin_upc": gtin,
                                "fdc_id": fdc_id,
                                "product_description": description,
                                "branded_food_category": category,
                                "brand_owner": brand_owner,
                                "brand_name": brand_name,
                                "best_esha_code": legacy_row.get("best_esha_code", ""),
                                "best_esha_description": legacy_row.get("best_esha_description", ""),
                                "best_esha_family": legacy_candidate.family,
                                "score": legacy_row.get("score", ""),
                                "n_candidates": legacy_row.get("n_candidates", ""),
                                "assignment_source": source,
                            }
                        )
                        assigned_legacy += 1
                        source_counts[source] += 1
                        rows_written += 1
                        continue

            best, score, n_candidates, source = choose_best_candidate(
                pc_candidate_pool=pc_candidate_pool,
                description=description,
                category=category,
                candidates=candidates,
                category_to_codes=category_to_codes,
                family_to_codes=family_to_codes,
                idf=idf,
            )
            if best is None:
                writer.writerow(
                    {
                        "gtin_upc": gtin,
                        "fdc_id": fdc_id,
                        "product_description": description,
                        "branded_food_category": category,
                        "brand_owner": brand_owner,
                        "brand_name": brand_name,
                        "best_esha_code": "",
                        "best_esha_description": "",
                        "best_esha_family": "",
                        "score": "",
                        "n_candidates": str(n_candidates),
                        "assignment_source": source + "_no_match",
                    }
                )
                unassigned += 1
                source_counts[source + "_no_match"] += 1
                rows_written += 1
                continue
            writer.writerow(
                {
                    "gtin_upc": gtin,
                    "fdc_id": fdc_id,
                    "product_description": description,
                    "branded_food_category": category,
                    "brand_owner": brand_owner,
                    "brand_name": brand_name,
                    "best_esha_code": best.code,
                    "best_esha_description": best.description,
                    "best_esha_family": best.family,
                    "score": f"{score:.4f}",
                    "n_candidates": str(n_candidates),
                    "assignment_source": source,
                }
            )
            assigned_fallback += 1
            source_counts[source] += 1
            rows_written += 1

    tmp.replace(OUT_CSV)
    summary = {
        "products": rows_written,
        "assigned_from_legacy": assigned_legacy,
        "assigned_from_fallback": assigned_fallback,
        "unassigned": unassigned,
        "output_csv": str(OUT_CSV),
        "source_counts": dict(source_counts),
    }
    OUT_SUMMARY.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.parse_args()
    print(json.dumps(build_full_map(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
