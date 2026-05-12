from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

from build_identity_gated_map import (
    BASE_COLUMNS,
    EshaCandidate,
    assign_candidate,
    blank_assignment,
    candidate_score,
    detect_family,
    load_esha_catalog,
    load_ingredient_signatures,
    load_rows,
    product_key,
)
from identity_contract import compatibility_reason, esha_identity, product_identity


ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "implementation" / "output"

DEFAULT_BASE = OUT_DIR / "product_to_best_esha_full_map.vIdentity.csv"
DEFAULT_RFT = OUT_DIR / "rft_v2" / "rft_v2_product_to_esha.csv"
DEFAULT_MEMBERS = OUT_DIR / "ingredient_only_cluster_members.csv"
DEFAULT_ESHA = ROOT / "esha_cleaned.csv"

OUT_MAP = OUT_DIR / "product_to_best_esha_full_map.vKG_RFT.csv"
OUT_DIFF = OUT_DIR / "product_to_best_esha_full_map.vKG_RFT.diff.csv"
OUT_SUMMARY = OUT_DIR / "product_to_best_esha_full_map.vKG_RFT.summary.json"

SAFE_RFT_VERDICTS = {"EXACT", "STRONG"}
SAFE_RFT_STATUS = {"auto_assigned"}

RFT_COLUMNS = [
    "rft_esha_code",
    "rft_esha_description",
    "rft_head",
    "rft_score",
    "rft_status",
    "rft_verdict",
    "rft_leaf_id",
    "rft_leaf_canonical",
    "rft_sr28_code",
    "rft_fndds_code",
    "rft_retail_attrs",
    "rft_brand_stripped",
    "rft_missing_from_leaf",
    "rft_leaf_extra_facets",
    "rft_agreement",
    "kg_rft_decision",
    "kg_current_reject_reason",
    "kg_rft_reject_reason",
    "kg_choice_reason",
]


def load_rft_by_key(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    rows = load_rows(path)
    return {product_key(row, i): row for i, row in enumerate(rows, start=1)}


def rft_is_safe(rft_row: dict[str, str]) -> bool:
    return (
        str(rft_row.get("rft_status") or "").strip() in SAFE_RFT_STATUS
        and str(rft_row.get("rft_verdict") or "").strip().upper() in SAFE_RFT_VERDICTS
        and bool(str(rft_row.get("rft_esha_code") or "").strip())
    )


def build_rft_candidate(rft_row: dict[str, str]) -> EshaCandidate | None:
    code = str(rft_row.get("rft_esha_code") or "").strip()
    desc = str(rft_row.get("rft_esha_description") or "").strip()
    if not code or not desc:
        return None
    return EshaCandidate(
        code=code,
        description=desc,
        head=desc.split(",", 1)[0].strip(),
        family=detect_family(desc),
        fact=esha_identity(desc),
    )


def score_for(product, candidate: EshaCandidate, *, category: str) -> tuple[float, str]:
    scored = candidate_score(product, candidate, category=category, incumbent_bonus=0.0)
    if scored is None:
        return 0.0, "candidate_score_none"
    return scored


def numeric(value: object, default: float = 0.0) -> float:
    try:
        return float(str(value or "").strip())
    except ValueError:
        return default


def enrich(row: dict[str, str], rft_row: dict[str, str], decision: str, current_reject: str, rft_reject: str, reason: str) -> dict[str, str]:
    out = dict(row)
    for col in RFT_COLUMNS:
        if col.startswith("kg_"):
            continue
        out[col] = str(rft_row.get(col, "") or "")
    out["rft_agreement"] = str(rft_row.get("agreement", rft_row.get("rft_agreement", "")) or "")
    out["kg_rft_decision"] = decision
    out["kg_current_reject_reason"] = current_reject
    out["kg_rft_reject_reason"] = rft_reject
    out["kg_choice_reason"] = reason
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", type=Path, default=DEFAULT_BASE)
    parser.add_argument("--rft", type=Path, default=DEFAULT_RFT)
    parser.add_argument("--members", type=Path, default=DEFAULT_MEMBERS)
    parser.add_argument("--esha", type=Path, default=DEFAULT_ESHA)
    parser.add_argument("--out", type=Path, default=OUT_MAP)
    parser.add_argument("--diff", type=Path, default=OUT_DIFF)
    parser.add_argument("--summary", type=Path, default=OUT_SUMMARY)
    parser.add_argument("--min-exact-score", type=float, default=12.0)
    parser.add_argument("--min-strong-score", type=float, default=18.0)
    args = parser.parse_args()

    print("loading base, RFT routes, ingredients, and ESHA catalog", flush=True)
    base_rows = load_rows(args.base)
    rft_by_key = load_rft_by_key(args.rft)
    ingredients = load_ingredient_signatures(args.members)
    by_code, _ = load_esha_catalog(args.esha)
    print(f"  base rows: {len(base_rows):,}", flush=True)
    print(f"  RFT rows: {len(rft_by_key):,}", flush=True)
    print(f"  ESHA candidates: {len(by_code):,}", flush=True)

    out_rows: list[dict[str, str]] = []
    diff_rows: list[dict[str, str]] = []
    decision_counts: Counter[str] = Counter()
    rft_reject_counts: Counter[str] = Counter()
    current_reject_counts: Counter[str] = Counter()

    for i, row in enumerate(base_rows, start=1):
        if i % 50000 == 0:
            print(f"  processed {i:,} rows", flush=True)

        key = product_key(row, i)
        original = dict(row)
        rft_row = rft_by_key.get(key, {})
        ingredient_signature = ingredients.get(key, "")
        product = product_identity(
            product_description=row.get("product_description", ""),
            category=row.get("branded_food_category", ""),
            ingredient_signature=ingredient_signature,
        )

        current_code = str(row.get("best_esha_code") or "").strip()
        current = by_code.get(current_code)
        current_reject = compatibility_reason(product, current.fact) if current else ("unassigned" if not current_code else "unknown_code")
        if current_reject:
            current_reject_counts[current_reject] += 1

        rft_candidate = build_rft_candidate(rft_row)
        rft_reject = ""
        rft_score = 0.0
        rft_reason = ""
        if rft_candidate:
            rft_reject = compatibility_reason(product, rft_candidate.fact)
            if rft_reject:
                rft_reject_counts[rft_reject] += 1
            else:
                rft_score, rft_reason = score_for(product, rft_candidate, category=row.get("branded_food_category", ""))

        decision = "kept_current_no_rft"
        choice_reason = "no_safe_rft_route"
        safe_rft = rft_is_safe(rft_row) and rft_candidate is not None and not rft_reject
        rft_verdict = str(rft_row.get("rft_verdict") or "").strip().upper()
        min_score = args.min_exact_score if rft_verdict == "EXACT" else args.min_strong_score

        if safe_rft and rft_score >= min_score:
            if current and current.code == rft_candidate.code and not current_reject:
                decision = "rft_confirmed_current"
                choice_reason = f"safe_rft_agrees;score={rft_score:.4f};{rft_reason}"
            elif current_reject or not current:
                assign_candidate(row, rft_candidate, max(rft_score, numeric(rft_row.get("rft_score")) * 100.0), 1, f"kg_rft_{rft_verdict.lower()}")
                decision = "rft_promoted_over_bad_or_blank_current"
                choice_reason = f"current_reject={current_reject};rft_score={rft_score:.4f};{rft_reason}"
            elif rft_verdict == "EXACT":
                assign_candidate(row, rft_candidate, max(rft_score, numeric(rft_row.get("rft_score")) * 100.0), 1, "kg_rft_exact")
                decision = "rft_exact_promoted_over_compatible_current"
                choice_reason = f"exact_rft_over_current;current_code={current.code};rft_score={rft_score:.4f};{rft_reason}"
            elif rft_verdict == "STRONG" and numeric(rft_row.get("rft_score")) >= 0.80:
                assign_candidate(row, rft_candidate, max(rft_score, numeric(rft_row.get("rft_score")) * 100.0), 1, "kg_rft_strong")
                decision = "rft_strong_promoted_over_compatible_current"
                choice_reason = f"strong_rft_over_current;current_code={current.code};rft_score={rft_score:.4f};{rft_reason}"
            else:
                decision = "kept_current_rft_safe_but_not_stronger"
                choice_reason = f"safe_rft_not_promoted;current_code={current.code};rft_score={rft_score:.4f};{rft_reason}"
        elif current_reject and current:
            blank_assignment(row, "kg_rft_identity_quarantine")
            decision = "blanked_current_no_safe_rft"
            choice_reason = f"current_reject={current_reject};rft_reject={rft_reject or 'not_safe'}"
        elif current and not current_reject:
            decision = "kept_current_identity_compatible"
            choice_reason = f"rft_not_promoted;status={rft_row.get('rft_status','')};verdict={rft_row.get('rft_verdict','')};rft_reject={rft_reject}"
        else:
            decision = "stayed_unassigned_no_safe_rft"
            choice_reason = f"rft_not_promoted;status={rft_row.get('rft_status','')};verdict={rft_row.get('rft_verdict','')};rft_reject={rft_reject}"

        decision_counts[decision] += 1
        enriched = enrich(row, rft_row, decision, current_reject, rft_reject, choice_reason)
        out_rows.append({col: enriched.get(col, "") for col in BASE_COLUMNS + RFT_COLUMNS})

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
                    "old_best_esha_code": original.get("best_esha_code", ""),
                    "old_best_esha_description": original.get("best_esha_description", ""),
                    "old_assignment_source": original.get("assignment_source", ""),
                    "new_best_esha_code": row.get("best_esha_code", ""),
                    "new_best_esha_description": row.get("best_esha_description", ""),
                    "new_assignment_source": row.get("assignment_source", ""),
                    "rft_esha_code": rft_row.get("rft_esha_code", ""),
                    "rft_esha_description": rft_row.get("rft_esha_description", ""),
                    "rft_status": rft_row.get("rft_status", ""),
                    "rft_verdict": rft_row.get("rft_verdict", ""),
                    "rft_leaf_id": rft_row.get("rft_leaf_id", ""),
                    "rft_leaf_canonical": rft_row.get("rft_leaf_canonical", ""),
                    "rft_missing_from_leaf": rft_row.get("rft_missing_from_leaf", ""),
                    "rft_leaf_extra_facets": rft_row.get("rft_leaf_extra_facets", ""),
                    "kg_rft_decision": decision,
                    "kg_current_reject_reason": current_reject,
                    "kg_rft_reject_reason": rft_reject,
                    "kg_choice_reason": choice_reason,
                }
            )

    print("writing outputs", flush=True)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=BASE_COLUMNS + RFT_COLUMNS)
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
        "old_best_esha_code",
        "old_best_esha_description",
        "old_assignment_source",
        "new_best_esha_code",
        "new_best_esha_description",
        "new_assignment_source",
        "rft_esha_code",
        "rft_esha_description",
        "rft_status",
        "rft_verdict",
        "rft_leaf_id",
        "rft_leaf_canonical",
        "rft_missing_from_leaf",
        "rft_leaf_extra_facets",
        "kg_rft_decision",
        "kg_current_reject_reason",
        "kg_rft_reject_reason",
        "kg_choice_reason",
    ]
    with args.diff.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=diff_fields)
        writer.writeheader()
        writer.writerows(diff_rows)

    assigned_before = sum(1 for r in base_rows if str(r.get("best_esha_code") or "").strip())
    assigned_after = sum(1 for r in out_rows if str(r.get("best_esha_code") or "").strip())
    summary = {
        "base": str(args.base),
        "rft": str(args.rft),
        "out": str(args.out),
        "diff": str(args.diff),
        "rows": len(out_rows),
        "assigned_before": assigned_before,
        "assigned_after": assigned_after,
        "coverage_delta": assigned_after - assigned_before,
        "changed_rows": len(diff_rows),
        "decision_counts": dict(decision_counts),
        "top_current_reject_reasons": dict(current_reject_counts.most_common(40)),
        "top_rft_reject_reasons": dict(rft_reject_counts.most_common(40)),
        "safe_rft_verdicts": sorted(SAFE_RFT_VERDICTS),
        "safe_rft_status": sorted(SAFE_RFT_STATUS),
    }
    args.summary.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
