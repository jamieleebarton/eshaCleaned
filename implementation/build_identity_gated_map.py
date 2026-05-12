from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

import match_esha_to_products as matcher
from identity_contract import (
    DAIRY_TERMS,
    FRUIT_TERMS,
    MEAT_TERMS,
    POULTRY_TERMS,
    SEAFOOD_TERMS,
    VEGETABLE_TERMS,
    FoodIdentity,
    compatibility_reason,
    esha_identity,
    product_identity,
    tokenize,
)


ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "implementation" / "output"

DEFAULT_VM = OUT_DIR / "product_to_best_esha_full_map.vM.csv"
DEFAULT_CLUSTER = OUT_DIR / "product_to_best_esha_full_map.vCluster.csv"
DEFAULT_MEMBERS = OUT_DIR / "ingredient_only_cluster_members.csv"
DEFAULT_ESHA = ROOT / "esha_cleaned.csv"

OUT_MAP = OUT_DIR / "product_to_best_esha_full_map.vIdentity.csv"
OUT_DIFF = OUT_DIR / "product_to_best_esha_full_map.vIdentity.diff.csv"
OUT_SUMMARY = OUT_DIR / "product_to_best_esha_full_map.vIdentity.summary.json"


BASE_COLUMNS = [
    "gtin_upc",
    "fdc_id",
    "product_description",
    "branded_food_category",
    "brand_owner",
    "brand_name",
    "best_esha_code",
    "best_esha_description",
    "best_esha_head",
    "best_esha_family",
    "score",
    "n_candidates",
    "assignment_source",
    "score_num",
]


@dataclass(frozen=True)
class EshaCandidate:
    code: str
    description: str
    head: str
    family: str
    fact: FoodIdentity


def product_key(row: dict[str, str], row_number: int = 0) -> str:
    fdc_id = str(row.get("fdc_id") or "").strip()
    if fdc_id:
        return f"fdc:{fdc_id}"
    gtin = str(row.get("gtin_upc") or "").strip()
    if gtin:
        return f"gtin:{gtin}"
    return f"row:{row_number}"


def load_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8", errors="replace") as f:
        return list(csv.DictReader(f))


def load_map_by_key(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    rows = load_rows(path)
    return {product_key(row, i): row for i, row in enumerate(rows, start=1)}


def load_ingredient_signatures(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    with path.open(newline="", encoding="utf-8", errors="replace") as f:
        for i, row in enumerate(csv.DictReader(f), start=1):
            out[product_key(row, i)] = str(row.get("ingredient_signature") or "")
    return out


def detect_family(description: str) -> str:
    tokens = set(tokenize(description))
    try:
        return matcher.detect_family(tokens, str(description).lower())
    except Exception:
        return ""


def load_esha_catalog(path: Path) -> tuple[dict[str, EshaCandidate], dict[str, set[str]]]:
    by_code: dict[str, EshaCandidate] = {}
    index: dict[str, set[str]] = defaultdict(set)
    with path.open(newline="", encoding="utf-8", errors="replace") as f:
        for row in csv.DictReader(f):
            code = str(row.get("EshaCode") or "").strip()
            desc = str(row.get("Description") or "").strip()
            if not code or not desc:
                continue
            fact = esha_identity(desc)
            cand = EshaCandidate(
                code=code,
                description=desc,
                head=desc.split(",", 1)[0].strip(),
                family=detect_family(desc),
                fact=fact,
            )
            by_code[code] = cand
            for term in fact.primary_terms:
                index[f"primary:{term}"].add(code)
            for term in fact.identity_terms:
                index[f"identity:{term}"].add(code)
            for term in fact.component_terms:
                index[f"component:{term}"].add(code)
            if fact.form:
                index[f"form:{fact.form}"].add(code)
    return by_code, index


def compatible(product: FoodIdentity, candidate: EshaCandidate) -> tuple[bool, str]:
    reason = compatibility_reason(product, candidate.fact)
    return reason == "", reason


def category_bonus(category: str, candidate: EshaCandidate) -> float:
    c = category.lower()
    h = candidate.fact.form
    if "salad dressing" in c and h == "salad_dressing":
        return 14.0
    if "tea" in c and h == "tea":
        return 16.0
    if "coffee" in c and h == "coffee":
        return 16.0
    if "powdered drinks" in c and h == "drink":
        return 16.0
    if "fruit & vegetable juice" in c and h in {"juice", "juice_drink", "drink"}:
        return 16.0
    if "pasta by shape" in c and h == "dry_pasta":
        return 14.0
    if "bacon" in c and h == "turkey_bacon":
        return 16.0
    if "soup" in c and h == "soup":
        return 14.0
    if ("sausages" in c or "hotdogs" in c or "brats" in c) and h == "sausage":
        return 14.0
    if "canned seafood" in c and h == "fish":
        return 14.0
    if "breakfast sandwich" in c and h == "sandwich":
        return 14.0
    if "chicken" in c and h in {"chicken", "chicken_strips", "tenders", "nuggets"}:
        return 12.0
    if "frozen appetizers" in c and h in {"chicken", "chicken_strips", "tenders", "nuggets"}:
        return 10.0
    if "cooked & prepared" in c and h in {"chicken", "chicken_strips"}:
        return 10.0
    if "unprepared" in c and h in {"raw_meat", "meat"}:
        return 12.0
    if "pre-packaged fruit" in c and h == "produce":
        return 12.0
    if "wholesome snacks" in c and h == "dried_fruit":
        return 10.0
    if "popcorn, peanuts" in c and h in {"nuts", "popcorn", "pretzels"}:
        return 8.0
    return 0.0


def candidate_score(
    product: FoodIdentity,
    candidate: EshaCandidate,
    *,
    category: str,
    incumbent_bonus: float = 0.0,
) -> tuple[float, str] | None:
    ok, reject = compatible(product, candidate)
    if not ok:
        return None

    product_terms = set(product.tokens)
    candidate_terms = set(candidate.fact.tokens)
    primary_hits = set(product.primary_terms) & set(candidate.fact.primary_terms)
    identity_hits = set(product.identity_terms) & set(candidate.fact.identity_terms)
    component_hits = set(product.component_terms) & set(candidate.fact.component_terms)
    title_hits = set(product.title_tokens) & candidate_terms
    ingredient_hits = set(product.ingredient_tokens) & candidate_terms
    state_hits = set(product.state_terms) & set(candidate.fact.state_terms)

    if product.primary_terms and not primary_hits and product.form not in {"sandwich", "salad_dressing", "fruit_snacks", "juice", "juice_drink", "drink"}:
        return None

    score = 0.0
    score += 34.0 * len(primary_hits)
    score += 8.0 * len(identity_hits)
    score += 5.0 * len(component_hits)
    score += 2.0 * len(title_hits)
    score += 2.5 * len(ingredient_hits)
    score += 8.0 * len(state_hits)
    if product.form and candidate.fact.form == product.form:
        score += 28.0
    score += category_bonus(category, candidate)
    score += incumbent_bonus

    if product.form == "sandwich":
        wanted = product.identity_terms & {"biscuit", "chicken", "sausage", "egg", "cheese", "beef", "pork", "ham"}
        missing = wanted - candidate.fact.identity_terms
        score -= 10.0 * len(missing)
        if "biscuit" in wanted and "biscuit" in candidate.fact.identity_terms:
            score += 8.0
    if product.form == "raw_meat":
        cut_terms = product_terms & {"loin", "tenderloin", "shoulder", "chop", "rib", "ribs", "steak"}
        score += 5.0 * len(cut_terms & candidate_terms)
        if "raw" in candidate.fact.state_terms:
            score += 8.0
    if product.form == "canned_seafood":
        medium = product_terms & {"oil", "water", "smoked", "mustard", "tomato"}
        score += 4.0 * len(medium & candidate_terms)
    if product.form == "dried_fruit":
        if "freeze" in product.state_terms and "freeze" in candidate.fact.state_terms:
            score += 10.0
        if "sweetened" in product_terms and "sweetened" in candidate_terms:
            score += 4.0
    if product.form == "chicken_strips":
        if "chicken" in candidate.fact.identity_terms or "chicken" in candidate.fact.primary_terms:
            score += 18.0
        if candidate.fact.form in {"chicken_strips", "chicken", "tenders", "nuggets"}:
            score += 18.0
        if "strip" in candidate_terms or "strips" in candidate_terms:
            score += 12.0
        if "grilled" in product_terms and "grilled" in candidate_terms:
            score += 6.0
        if "crispy" in product_terms and "crispy" in candidate_terms:
            score += 6.0

    product_category = category.lower()
    if not (product.state_terms & {"frozen", "canned", "cooked", "steamed"}):
        unexpected_states = candidate.fact.state_terms & {"frozen", "canned", "cooked", "steamed"}
        score -= 10.0 * len(unexpected_states)
    if product.form == "produce" and "pre-packaged fruit" in product_category:
        if "fresh" in candidate.fact.state_terms or "fresh" in candidate_terms:
            score += 12.0
        if "frozen" in candidate.fact.state_terms or "canned" in candidate.fact.state_terms:
            score -= 18.0

    extra_domains = (
        set(candidate.fact.primary_terms)
        & (FRUIT_TERMS | VEGETABLE_TERMS | MEAT_TERMS | POULTRY_TERMS | SEAFOOD_TERMS | DAIRY_TERMS)
        - set(product.primary_terms)
        - set(product.identity_terms)
    )
    score -= 3.0 * len(extra_domains)
    if "fs" in candidate_terms:
        score -= 1.0

    reason = (
        f"form={product.form}->{candidate.fact.form};"
        f"primary_hits={','.join(sorted(primary_hits))};"
        f"identity_hits={len(identity_hits)};"
        f"component_hits={len(component_hits)};"
        f"state_hits={','.join(sorted(state_hits))};"
        f"title_hits={len(title_hits)};"
        f"ingredient_hits={len(ingredient_hits)};"
        f"incumbent_bonus={incumbent_bonus:.1f}"
    )
    return score, reason


def candidate_pool(product: FoodIdentity, index: dict[str, set[str]]) -> set[str]:
    noisy_search_terms = {
        "butter",
        "cream",
        "dressing",
        "food",
        "honey",
        "milk",
        "oil",
        "salt",
        "sauce",
        "snack",
        "sugar",
        "water",
    }

    def codes_for_term(term: str) -> set[str]:
        return set(index.get(f"primary:{term}", set())) | set(index.get(f"identity:{term}", set()))

    def ranked_term_sets(terms: set[str]) -> list[set[str]]:
        sets = [codes_for_term(term) for term in terms if term and codes_for_term(term)]
        return sorted(sets, key=len)

    def intersect_first(term_sets: list[set[str]], limit: int = 3) -> set[str]:
        if not term_sets:
            return set()
        out = set(term_sets[0])
        for s in term_sets[1:limit]:
            out &= s
            if not out:
                break
        return out

    codes: set[str] = set()
    primary_terms = set(product.primary_terms) - noisy_search_terms
    identity_terms = set(product.identity_terms) - noisy_search_terms

    # Strict forms should be retrieved by form plus the real identity noun, not
    # by every broad code that mentions one ingredient.
    if product.form in {"dried_fruit", "produce", "canned_seafood", "raw_meat", "mashed_potatoes", "chicken_strips"}:
        term_sets = ranked_term_sets(primary_terms or identity_terms)
        term_codes = intersect_first(term_sets, limit=2) or (set().union(*term_sets[:2]) if term_sets else set())
        form_codes = set(index.get(f"form:{product.form}", set()))
        if product.form == "canned_seafood":
            form_codes = set(index.get("form:fish", set()))
        if product.form == "chicken_strips":
            form_codes = (
                set(index.get("form:chicken_strips", set()))
                | set(index.get("form:chicken", set()))
                | set(index.get("form:tenders", set()))
                | set(index.get("form:nuggets", set()))
            )
        if term_codes and form_codes:
            codes = term_codes & form_codes
        else:
            codes = term_codes or form_codes
    elif product.form == "prepared_meal":
        term_sets = ranked_term_sets(primary_terms or identity_terms)
        codes = intersect_first(term_sets, limit=3) or intersect_first(term_sets, limit=2)
        if not codes and term_sets:
            codes = set(term_sets[0])
    else:
        term_sets = ranked_term_sets(primary_terms or identity_terms)
        if len(term_sets) >= 2:
            codes = intersect_first(term_sets, limit=2) or (set(term_sets[0]) | set(term_sets[1]))
        elif term_sets:
            codes = set(term_sets[0])
        if product.form:
            form_codes = set(index.get(f"form:{product.form}", set()))
            codes = (codes & form_codes) if codes and form_codes else (codes or form_codes)

    if product.form == "sandwich":
        sandwich_codes = set(index.get("form:sandwich", set()))
        term_sets = ranked_term_sets(product.identity_terms & {"biscuit", "chicken", "sausage", "egg", "cheese", "beef", "pork", "ham"})
        term_codes = intersect_first(term_sets, limit=2) or (set().union(*term_sets[:2]) if term_sets else set())
        codes = (sandwich_codes & term_codes) if term_codes else sandwich_codes
    if product.form == "salad_dressing":
        dressing_codes = set(index.get("form:salad_dressing", set()))
        flavor_sets = ranked_term_sets(product.identity_terms & {"mustard", "honey", "ranch", "dijon", "italian", "french"})
        flavor_codes = intersect_first(flavor_sets, limit=2) or (set().union(*flavor_sets[:2]) if flavor_sets else set())
        codes = (dressing_codes & flavor_codes) if flavor_codes else dressing_codes
    return codes


def choose_candidate(
    product: FoodIdentity,
    *,
    category: str,
    by_code: dict[str, EshaCandidate],
    index: dict[str, set[str]],
    preferred_codes: dict[str, float],
) -> tuple[EshaCandidate | None, float, str, int, str]:
    pool = candidate_pool(product, index) | set(preferred_codes)
    if len(pool) > 2500 and product.primary_terms:
        primary = set(product.primary_terms)
        exact_form = product.form
        pool = {
            code
            for code in pool
            if code in preferred_codes
            or ((cand := by_code.get(str(code))) is not None and (cand.fact.primary_terms & primary or (exact_form and cand.fact.form == exact_form)))
        }
    if len(pool) > 5000:
        return None, 0.0, f"candidate_pool_too_broad:{len(pool)}", len(pool), f"candidate_pool_too_broad:{len(pool)}"
    best: tuple[float, EshaCandidate, str] | None = None
    evaluated = 0
    rejects: Counter[str] = Counter()

    for code in pool:
        cand = by_code.get(str(code))
        if not cand:
            continue
        evaluated += 1
        ok, reject = compatible(product, cand)
        if not ok:
            rejects[reject] += 1
            continue
        scored = candidate_score(
            product,
            cand,
            category=category,
            incumbent_bonus=preferred_codes.get(code, 0.0),
        )
        if scored is None:
            rejects["score_none"] += 1
            continue
        score, reason = scored
        if best is None or (score, cand.code) > (best[0], best[1].code):
            best = (score, cand, reason)

    if not best:
        reject_summary = " | ".join(f"{k}:{v}" for k, v in rejects.most_common(6))
        return None, 0.0, reject_summary, evaluated, reject_summary
    reject_summary = " | ".join(f"{k}:{v}" for k, v in rejects.most_common(6))
    return best[1], best[0], best[2], evaluated, reject_summary


def assign_candidate(row: dict[str, str], cand: EshaCandidate, score: float, n_candidates: int, source: str) -> None:
    row["best_esha_code"] = cand.code
    row["best_esha_description"] = cand.description
    row["best_esha_head"] = cand.head
    row["best_esha_family"] = cand.family
    row["score"] = f"{score:.4f}"
    row["score_num"] = f"{score:.4f}"
    row["n_candidates"] = str(n_candidates)
    row["assignment_source"] = source


def blank_assignment(row: dict[str, str], source: str) -> None:
    row["best_esha_code"] = ""
    row["best_esha_description"] = ""
    row["best_esha_head"] = ""
    row["best_esha_family"] = ""
    row["score"] = "0"
    row["score_num"] = "0"
    row["n_candidates"] = "0"
    row["assignment_source"] = source


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--vm", type=Path, default=DEFAULT_VM)
    parser.add_argument("--cluster", type=Path, default=DEFAULT_CLUSTER)
    parser.add_argument("--members", type=Path, default=DEFAULT_MEMBERS)
    parser.add_argument("--esha", type=Path, default=DEFAULT_ESHA)
    parser.add_argument("--out", type=Path, default=OUT_MAP)
    parser.add_argument("--diff", type=Path, default=OUT_DIFF)
    parser.add_argument("--summary", type=Path, default=OUT_SUMMARY)
    parser.add_argument("--min-recovery-score", type=float, default=42.0)
    args = parser.parse_args()

    print("loading maps and ingredient signatures", flush=True)
    vm_rows = load_rows(args.vm)
    cluster_by_key = load_map_by_key(args.cluster)
    ingredients = load_ingredient_signatures(args.members)

    print("loading ESHA identity catalog", flush=True)
    by_code, index = load_esha_catalog(args.esha)
    print(f"  ESHA candidates: {len(by_code):,}; index keys: {len(index):,}", flush=True)

    out_rows: list[dict[str, str]] = []
    diff_rows: list[dict[str, str]] = []
    action_counts: Counter[str] = Counter()
    reject_counts: Counter[str] = Counter()
    recovered_sources: Counter[str] = Counter()

    for i, row in enumerate(vm_rows, start=1):
        if i % 50000 == 0:
            print(f"  processed {i:,} rows", flush=True)
        key = product_key(row, i)
        original = dict(row)
        cluster_row = cluster_by_key.get(key, {})
        ingredient_signature = ingredients.get(key, "")
        product = product_identity(
            product_description=row.get("product_description", ""),
            category=row.get("branded_food_category", ""),
            ingredient_signature=ingredient_signature,
        )

        current_code = str(row.get("best_esha_code") or "").strip()
        cluster_code = str(cluster_row.get("best_esha_code") or "").strip()
        current = by_code.get(current_code)
        cluster = by_code.get(cluster_code)
        current_reason = compatibility_reason(product, current.fact) if current else ("unassigned" if not current_code else "unknown_code")
        cluster_reason = compatibility_reason(product, cluster.fact) if cluster else ("unassigned" if not cluster_code else "unknown_code")

        preferred: dict[str, float] = {}
        if current and not current_reason:
            preferred[current.code] = 12.0
        if cluster and not cluster_reason:
            preferred[cluster.code] = max(preferred.get(cluster.code, 0.0), 9.0)

        needs_choice = bool(current_reason)
        if current and not current_reason and cluster and not cluster_reason and cluster.code != current.code:
            # Re-score when the cluster offers a compatible alternative; this
            # lets a better exact identity beat a weak incumbent.
            needs_choice = True
        if not current:
            needs_choice = True

        chosen: EshaCandidate | None = current if current and not current_reason else None
        score = float(row.get("score_num") or row.get("score") or 0 or 0)
        reason = "kept_current_identity_compatible"
        n_candidates = int(float(row.get("n_candidates") or 0))
        rejects = ""
        action = "kept_current"

        if needs_choice:
            chosen, score, reason, n_candidates, rejects = choose_candidate(
                product,
                category=row.get("branded_food_category", ""),
                by_code=by_code,
                index=index,
                preferred_codes=preferred,
            )
            if chosen and score >= args.min_recovery_score:
                source = "identity_contract_recovered" if not current else "identity_contract_remapped"
                assign_candidate(row, chosen, score, n_candidates, source)
                action = source
                recovered_sources[source] += 1
            else:
                blank_assignment(row, "identity_contract_no_safe_match")
                action = "blanked_no_safe_match" if current else "stayed_unassigned_no_safe_match"
                if current_reason:
                    reject_counts[current_reason] += 1
        else:
            if current:
                assign_candidate(row, current, score, n_candidates, row.get("assignment_source", ""))

        if (
            original.get("best_esha_code") != row.get("best_esha_code")
            or original.get("assignment_source") != row.get("assignment_source")
        ):
            diff_rows.append(
                {
                    "product_key": key,
                    "gtin_upc": original.get("gtin_upc", ""),
                    "fdc_id": original.get("fdc_id", ""),
                    "product_description": original.get("product_description", ""),
                    "branded_food_category": original.get("branded_food_category", ""),
                    "brand_owner": original.get("brand_owner", ""),
                    "brand_name": original.get("brand_name", ""),
                    "ingredient_signature": ingredient_signature,
                    "product_form": product.form,
                    "product_primary_terms": " ".join(sorted(product.primary_terms)),
                    "old_best_esha_code": original.get("best_esha_code", ""),
                    "old_best_esha_description": original.get("best_esha_description", ""),
                    "old_best_esha_head": original.get("best_esha_head", ""),
                    "old_assignment_source": original.get("assignment_source", ""),
                    "old_reject_reason": current_reason,
                    "cluster_best_esha_code": cluster_code,
                    "cluster_best_esha_description": cluster_row.get("best_esha_description", ""),
                    "cluster_best_esha_head": cluster_row.get("best_esha_head", ""),
                    "cluster_reject_reason": cluster_reason,
                    "new_best_esha_code": row.get("best_esha_code", ""),
                    "new_best_esha_description": row.get("best_esha_description", ""),
                    "new_best_esha_head": row.get("best_esha_head", ""),
                    "new_assignment_source": row.get("assignment_source", ""),
                    "new_score": row.get("score", ""),
                    "n_candidates_evaluated": str(n_candidates),
                    "action": action,
                    "choice_reason": reason,
                    "top_rejects": rejects,
                }
            )

        action_counts[action] += 1
        out_rows.append({col: row.get(col, "") for col in BASE_COLUMNS})

    print("writing outputs", flush=True)
    with args.out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=BASE_COLUMNS)
        writer.writeheader()
        writer.writerows(out_rows)

    diff_fields = [
        "product_key",
        "gtin_upc",
        "fdc_id",
        "product_description",
        "branded_food_category",
        "brand_owner",
        "brand_name",
        "ingredient_signature",
        "product_form",
        "product_primary_terms",
        "old_best_esha_code",
        "old_best_esha_description",
        "old_best_esha_head",
        "old_assignment_source",
        "old_reject_reason",
        "cluster_best_esha_code",
        "cluster_best_esha_description",
        "cluster_best_esha_head",
        "cluster_reject_reason",
        "new_best_esha_code",
        "new_best_esha_description",
        "new_best_esha_head",
        "new_assignment_source",
        "new_score",
        "n_candidates_evaluated",
        "action",
        "choice_reason",
        "top_rejects",
    ]
    with args.diff.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=diff_fields)
        writer.writeheader()
        writer.writerows(diff_rows)

    assigned_before = sum(1 for r in vm_rows if str(r.get("best_esha_code") or "").strip())
    assigned_after = sum(1 for r in out_rows if str(r.get("best_esha_code") or "").strip())
    summary = {
        "source": str(args.vm),
        "cluster_source": str(args.cluster),
        "output": str(args.out),
        "diff": str(args.diff),
        "rows": len(out_rows),
        "assigned_before": assigned_before,
        "assigned_after": assigned_after,
        "coverage_delta": assigned_after - assigned_before,
        "action_counts": dict(action_counts),
        "recovered_sources": dict(recovered_sources),
        "top_old_reject_reasons": dict(reject_counts.most_common(40)),
        "changed_rows": len(diff_rows),
    }
    args.summary.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
