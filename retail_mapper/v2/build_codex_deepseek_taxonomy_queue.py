#!/usr/bin/env python3
"""Build Codex DeepSeek review packets for retail taxonomy outliers.

This is an adjudication queue, not an auto-fix. It packages the rows most
likely to be wrong after `build_codex_full_corpus_audit.py`:

  - BFC department/top2 mismatches against the corpus-derived home map
  - rows emitted by Codex path-outlier audits
  - known lexical hijacks where title words often steal the route
  - residual "ice cream" title rows left under Bakery for explicit review

Output:
  - codex_deepseek_taxonomy_review_queue.jsonl
  - codex_deepseek_taxonomy_review_queue.csv
  - codex_deepseek_taxonomy_review_queue_report.json

Default mode is intentionally high-precision. Broad BFC top2/top3 and path
outlier signals are useful for ranking/context, but they are not proof that a
row is wrong.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[2]
V2 = REPO / "retail_mapper" / "v2"
AUDIT = V2 / "codex_full_corpus_audit.csv"
EXPECTED_HOMES = V2 / "codex_bfc_expected_homes.csv"
DEPT_EXAMPLES = V2 / "codex_bfc_department_misplaced_examples.csv"
PATH_OUTLIERS = V2 / "codex_bfc_path_outliers.csv"
PATH_OUTLIER_EXAMPLES = V2 / "codex_bfc_path_outlier_examples.csv"
ICE_CREAM_RESIDUALS = V2 / "codex_ice_cream_bakery_residuals.csv"
PRODUCT_DB = REPO / "data" / "master_products.db"

OUT_JSONL = V2 / "codex_deepseek_taxonomy_review_queue.jsonl"
OUT_CSV = V2 / "codex_deepseek_taxonomy_review_queue.csv"
OUT_REPORT = V2 / "codex_deepseek_taxonomy_review_queue_report.json"

csv.field_size_limit(sys.maxsize)

HIJACK_RE = re.compile(
    r"\b("
    r"bagels?|bars?|beans?|buns?|burritos?|cakes?|churros?|cones?|cookies?|"
    r"crackers?|cream(?:er)?|croutons?|mix(?:es)?|pastr(?:y|ies)|pies?|"
    r"rolls?|sandwich(?:es)?|tortillas?"
    r")\b",
    re.I,
)

HIGH_RISK_BFCS = {
    "alcohol",
    "breads & buns",
    "cakes, cupcakes, snack cakes",
    "cookies & biscuits",
    "biscuits/cookies",
    "croissants, sweet rolls, muffins & other pastries",
    "frozen appetizers & hors d'oeuvres",
    "ice cream & frozen yogurt",
    "mexican dinner mixes",
    "prepared subs & sandwiches",
    "pre-packaged fruit & vegetables",
    "vegetable and lentil mixes",
}

MUST_INCLUDE_REASONS = {
    "ice_cream_title_under_bakery_residual",
}

REVIEW_FIELDS = [
    "fdc_id",
    "priority_score",
    "reason_codes",
    "title",
    "branded_food_category",
    "current_canonical_path",
    "current_retail_leaf_path",
    "expected_department",
    "expected_top2",
    "expected_top3",
    "fndds_desc",
    "sr28_desc",
    "esha_desc",
    "matched_key",
]


def path_prefix(path: str, depth: int) -> str:
    parts = [p.strip() for p in (path or "").split(" > ") if p.strip()]
    return " > ".join(parts[:depth])


def as_float(value: str, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def load_expected_homes(path: Path = EXPECTED_HOMES) -> dict[str, dict[str, str]]:
    homes: dict[str, dict[str, str]] = {}
    if not path.exists():
        return homes
    with path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            bfc = (row.get("branded_food_category") or "").strip()
            if bfc:
                homes[bfc] = row
    return homes


def load_dept_example_ids(path: Path = DEPT_EXAMPLES) -> set[str]:
    ids: set[str] = set()
    if not path.exists():
        return ids
    with path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            fdc = (row.get("fdc_id") or "").strip()
            if fdc:
                ids.add(fdc)
    return ids


def load_path_outlier_signals(
    outliers_path: Path = PATH_OUTLIERS,
    examples_path: Path = PATH_OUTLIER_EXAMPLES,
) -> dict[str, dict[str, Any]]:
    bucket_signals: dict[tuple[str, str, str], dict[str, str]] = {}
    if outliers_path.exists():
        with outliers_path.open(newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                bfc = (row.get("branded_food_category") or "").strip()
                cp = (row.get("current_canonical_path") or "").strip()
                leaf = (row.get("current_retail_leaf_path") or "").strip()
                if bfc and cp and leaf:
                    bucket_signals[(bfc, cp, leaf)] = row

    signals_by_fdc: dict[str, dict[str, Any]] = {}
    if not examples_path.exists():
        return signals_by_fdc

    with examples_path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            fdc = (row.get("fdc_id") or "").strip()
            if not fdc:
                continue
            key = (
                (row.get("branded_food_category") or "").strip(),
                (row.get("canonical_path") or "").strip(),
                (row.get("retail_leaf_path") or "").strip(),
            )
            bucket = bucket_signals.get(key, {})
            signals_by_fdc[fdc] = {
                "issue_types": row.get("issue_types", ""),
                "severity_score": as_float(row.get("severity_score", "")),
                "bfc_dominant_prefixes": bucket.get("bfc_dominant_prefixes", ""),
                "path_pct_in_bfc": bucket.get("path_pct_in_bfc", ""),
                "suggested_dominant_path_for_leaf": bucket.get("suggested_dominant_path_for_leaf", ""),
                "suggested_dominant_path_pct_for_leaf": bucket.get("suggested_dominant_path_pct_for_leaf", ""),
            }
    return signals_by_fdc


def load_ice_cream_residual_ids(path: Path = ICE_CREAM_RESIDUALS) -> set[str]:
    ids: set[str] = set()
    if not path.exists():
        return ids
    with path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            fdc = (row.get("fdc_id") or "").strip()
            if fdc:
                ids.add(fdc)
    return ids


def load_product_context(fdcs: set[str], db_path: Path = PRODUCT_DB) -> dict[str, dict[str, str]]:
    if not fdcs or not db_path.exists():
        return {}
    out: dict[str, dict[str, str]] = {}
    fdcs_list = list(fdcs)
    conn = sqlite3.connect(db_path)
    try:
        for batch_start in range(0, len(fdcs_list), 500):
            batch = fdcs_list[batch_start:batch_start + 500]
            placeholders = ",".join("?" for _ in batch)
            sql = (
                "SELECT fdc_id, brand_name, brand_owner, ingredients_clean, ingredients, "
                "package_weight, serving_size, serving_size_unit "
                f"FROM products WHERE fdc_id IN ({placeholders})"
            )
            for row in conn.execute(sql, batch):
                (
                    fdc_id,
                    brand_name,
                    brand_owner,
                    ingredients_clean,
                    ingredients,
                    package_weight,
                    serving_size,
                    serving_size_unit,
                ) = row
                fdc = str(fdc_id)
                out[fdc] = {
                    "brand_name": brand_name or "",
                    "brand_owner": brand_owner or "",
                    "ingredients": (ingredients_clean or ingredients or "")[:1200],
                    "package_weight": package_weight or "",
                    "serving_size": "" if serving_size is None else str(serving_size),
                    "serving_size_unit": serving_size_unit or "",
                }
    finally:
        conn.close()
    return out


def row_reason_and_score(
    row: dict[str, str],
    *,
    homes: dict[str, dict[str, str]],
    dept_example_ids: set[str],
    path_outlier_signals: dict[str, dict[str, Any]],
    ice_cream_residual_ids: set[str],
) -> tuple[list[str], float, dict[str, Any]]:
    fdc = (row.get("fdc_id") or "").strip()
    title = row.get("title") or ""
    bfc = (row.get("branded_food_category") or "").strip()
    bfc_lower = bfc.lower()
    cp = row.get("canonical_path") or ""
    dept = path_prefix(cp, 1)
    top2 = path_prefix(cp, 2)
    top3 = path_prefix(cp, 3)
    home = homes.get(bfc, {})

    reasons: list[str] = []
    score = 0.0
    signal: dict[str, Any] = {}

    expected_dept = home.get("dominant_department", "")
    dept_pct = as_float(home.get("dominant_department_pct", ""))
    dept_status = home.get("department_status", "")
    if expected_dept and dept != expected_dept and dept_status in {"strong", "medium"}:
        reasons.append("bfc_department_mismatch")
        score += 900 * dept_pct

    expected_top2 = home.get("dominant_top2", "")
    top2_pct = as_float(home.get("dominant_top2_pct", ""))
    top2_status = home.get("top2_status", "")
    if expected_top2 and top2 != expected_top2 and top2_status == "strong":
        reasons.append("bfc_top2_mismatch")
        score += 350 * top2_pct

    expected_top3 = home.get("dominant_top3", "")
    top3_pct = as_float(home.get("dominant_top3_pct", ""))
    top3_status = home.get("top3_status", "")
    if expected_top3 and top3 != expected_top3 and top3_status == "strong":
        reasons.append("bfc_top3_mismatch")
        score += 100 * top3_pct

    if fdc in dept_example_ids:
        reasons.append("department_misplaced_audit_example")
        score += 300

    outlier_signal = path_outlier_signals.get(fdc)
    if outlier_signal:
        reasons.append("path_outlier_audit_example")
        score += min(500.0, outlier_signal.get("severity_score", 0.0) / 25.0)
        signal.update(outlier_signal)

    if fdc in ice_cream_residual_ids:
        reasons.append("ice_cream_title_under_bakery_residual")
        score += 2500

    if HIJACK_RE.search(title):
        if reasons or bfc_lower in HIGH_RISK_BFCS:
            reasons.append("known_lexical_hijack_word")
            score += 75

    if bfc_lower in HIGH_RISK_BFCS and reasons:
        score += 50

    if not reasons:
        return [], 0.0, signal

    signal.update({
        "expected_department": expected_dept,
        "expected_top2": expected_top2,
        "expected_top3": expected_top3,
        "department_distribution": home.get("department_distribution", ""),
        "top2_distribution": home.get("top2_distribution", ""),
    })
    return sorted(set(reasons)), round(score, 3), signal


def is_high_precision_case(case: dict[str, Any], *, path_severity_threshold: float) -> bool:
    reasons = set(case.get("reason_codes") or [])
    signal = case.get("_signal") or {}
    bfc = (case.get("branded_food_category") or "").lower()
    severity = as_float(str(signal.get("severity_score", "")))

    if "ice_cream_title_under_bakery_residual" in reasons:
        return True

    # Department mismatch is the strongest corpus-derived signal. Require a
    # second independent signal so broad/heterogeneous BFCs don't flood review.
    if "bfc_department_mismatch" in reasons:
        if "department_misplaced_audit_example" in reasons:
            return True
        if "path_outlier_audit_example" in reasons and severity >= path_severity_threshold:
            return True
        if "known_lexical_hijack_word" in reasons and bfc in HIGH_RISK_BFCS:
            return True

    return False


def build_review_case(
    row: dict[str, str],
    *,
    reasons: list[str],
    score: float,
    signal: dict[str, Any],
    product_context: dict[str, str],
) -> dict[str, Any]:
    fdc = (row.get("fdc_id") or "").strip()
    return {
        "case_id": fdc,
        "fdc_id": fdc,
        "priority_score": score,
        "reason_codes": reasons,
        "title": row.get("title", ""),
        "branded_food_category": row.get("branded_food_category", ""),
        "brand_name": product_context.get("brand_name", ""),
        "brand_owner": product_context.get("brand_owner", ""),
        "ingredients": product_context.get("ingredients", ""),
        "package_weight": product_context.get("package_weight", ""),
        "serving_size": product_context.get("serving_size", ""),
        "serving_size_unit": product_context.get("serving_size_unit", ""),
        "current_taxonomy": {
            "category_path_fixed": row.get("category_path_fixed", ""),
            "product_identity_fixed": row.get("product_identity_fixed", ""),
            "canonical_path": row.get("canonical_path", ""),
            "modifier": row.get("modifier", ""),
            "retail_leaf_path": row.get("retail_leaf_path", ""),
        },
        "reference_matches": {
            "fndds_code": row.get("fndds_code", ""),
            "fndds_desc": row.get("fndds_desc", ""),
            "sr28_code": row.get("sr28_code", ""),
            "sr28_desc": row.get("sr28_desc", ""),
            "esha_code": row.get("esha_code", ""),
            "esha_desc": row.get("esha_desc", ""),
            "match_source": row.get("match_source", ""),
            "match_score": row.get("match_score", ""),
            "matched_key": row.get("matched_key", ""),
        },
        "bfc_context": {
            "expected_department": signal.get("expected_department", ""),
            "expected_top2": signal.get("expected_top2", ""),
            "expected_top3": signal.get("expected_top3", ""),
            "department_distribution": signal.get("department_distribution", ""),
            "top2_distribution": signal.get("top2_distribution", ""),
            "bfc_dominant_prefixes": signal.get("bfc_dominant_prefixes", ""),
        },
        "outlier_context": {
            "issue_types": signal.get("issue_types", ""),
            "severity_score": signal.get("severity_score", ""),
            "path_pct_in_bfc": signal.get("path_pct_in_bfc", ""),
            "suggested_dominant_path_for_leaf": signal.get("suggested_dominant_path_for_leaf", ""),
            "suggested_dominant_path_pct_for_leaf": signal.get("suggested_dominant_path_pct_for_leaf", ""),
        },
        "_signal": signal,
    }


def select_cases(
    candidates: list[dict[str, Any]],
    *,
    max_cases: int,
    per_bfc_limit: int,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    bfc_counts: Counter[str] = Counter()
    seen: set[str] = set()

    must_include = [
        case for case in candidates
        if MUST_INCLUDE_REASONS.intersection(case.get("reason_codes", []))
    ]
    for case in sorted(must_include, key=lambda c: (-c["priority_score"], c["fdc_id"])):
        fdc = case["fdc_id"]
        if fdc in seen:
            continue
        selected.append(case)
        seen.add(fdc)
        bfc_counts[case["branded_food_category"]] += 1
        if max_cases and len(selected) >= max_cases:
            return selected

    for case in sorted(candidates, key=lambda c: (-c["priority_score"], c["fdc_id"])):
        fdc = case["fdc_id"]
        bfc = case["branded_food_category"]
        if fdc in seen:
            continue
        if per_bfc_limit and bfc_counts[bfc] >= per_bfc_limit:
            continue
        selected.append(case)
        seen.add(fdc)
        bfc_counts[bfc] += 1
        if max_cases and len(selected) >= max_cases:
            break
    return selected


def write_outputs(cases: list[dict[str, Any]], report: dict[str, Any]) -> None:
    with OUT_JSONL.open("w", encoding="utf-8") as fh:
        for case in cases:
            out_case = dict(case)
            out_case.pop("_signal", None)
            fh.write(json.dumps(out_case, ensure_ascii=False, sort_keys=True) + "\n")

    with OUT_CSV.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=REVIEW_FIELDS)
        writer.writeheader()
        for case in cases:
            refs = case["reference_matches"]
            bfc_ctx = case["bfc_context"]
            writer.writerow({
                "fdc_id": case["fdc_id"],
                "priority_score": case["priority_score"],
                "reason_codes": "|".join(case["reason_codes"]),
                "title": case["title"],
                "branded_food_category": case["branded_food_category"],
                "current_canonical_path": case["current_taxonomy"]["canonical_path"],
                "current_retail_leaf_path": case["current_taxonomy"]["retail_leaf_path"],
                "expected_department": bfc_ctx.get("expected_department", ""),
                "expected_top2": bfc_ctx.get("expected_top2", ""),
                "expected_top3": bfc_ctx.get("expected_top3", ""),
                "fndds_desc": refs.get("fndds_desc", ""),
                "sr28_desc": refs.get("sr28_desc", ""),
                "esha_desc": refs.get("esha_desc", ""),
                "matched_key": refs.get("matched_key", ""),
            })

    OUT_REPORT.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-cases", type=int, default=2000)
    parser.add_argument("--per-bfc-limit", type=int, default=35)
    parser.add_argument("--mode", choices=["high-precision", "broad"], default="high-precision")
    parser.add_argument("--path-severity-threshold", type=float, default=1000.0)
    parser.add_argument("--no-ingredients", action="store_true")
    args = parser.parse_args()

    if not AUDIT.exists():
        raise SystemExit(f"missing {AUDIT}; run build_codex_full_corpus_audit.py first")

    homes = load_expected_homes()
    dept_example_ids = load_dept_example_ids()
    path_outlier_signals = load_path_outlier_signals()
    ice_cream_residual_ids = load_ice_cream_residual_ids()

    raw_candidates: list[tuple[dict[str, str], list[str], float, dict[str, Any]]] = []
    reason_counts: Counter[str] = Counter()
    bfc_candidate_counts: Counter[str] = Counter()

    with AUDIT.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            reasons, score, signal = row_reason_and_score(
                row,
                homes=homes,
                dept_example_ids=dept_example_ids,
                path_outlier_signals=path_outlier_signals,
                ice_cream_residual_ids=ice_cream_residual_ids,
            )
            if not reasons:
                continue
            raw_candidates.append((row, reasons, score, signal))
            reason_counts.update(reasons)
            bfc_candidate_counts[row.get("branded_food_category", "")] += 1

    fdcs = {row.get("fdc_id", "") for row, _reasons, _score, _signal in raw_candidates}
    product_context = {} if args.no_ingredients else load_product_context(fdcs)

    broad_cases = [
        build_review_case(
            row,
            reasons=reasons,
            score=score,
            signal=signal,
            product_context=product_context.get(row.get("fdc_id", ""), {}),
        )
        for row, reasons, score, signal in raw_candidates
    ]

    if args.mode == "high-precision":
        cases = [
            case for case in broad_cases
            if is_high_precision_case(case, path_severity_threshold=args.path_severity_threshold)
        ]
    else:
        cases = broad_cases

    selected = select_cases(cases, max_cases=args.max_cases, per_bfc_limit=args.per_bfc_limit)
    selected_reason_counts: Counter[str] = Counter()
    selected_bfc_counts: Counter[str] = Counter()
    for case in selected:
        selected_reason_counts.update(case["reason_codes"])
        selected_bfc_counts[case["branded_food_category"]] += 1

    report = {
        "audit_csv": str(AUDIT),
        "mode": args.mode,
        "broad_suspicion_rows": len(raw_candidates),
        "candidate_rows": len(cases),
        "selected_rows": len(selected),
        "max_cases": args.max_cases,
        "per_bfc_limit": args.per_bfc_limit,
        "path_severity_threshold": args.path_severity_threshold,
        "reason_counts": dict(reason_counts.most_common()),
        "selected_reason_counts": dict(selected_reason_counts.most_common()),
        "top_candidate_bfcs": dict(bfc_candidate_counts.most_common(30)),
        "top_selected_bfcs": dict(selected_bfc_counts.most_common(30)),
        "outputs": {
            "jsonl": str(OUT_JSONL),
            "csv": str(OUT_CSV),
            "report": str(OUT_REPORT),
        },
    }
    write_outputs(selected, report)

    print(json.dumps({
        "mode": args.mode,
        "broad_suspicion_rows": len(raw_candidates),
        "candidate_rows": len(cases),
        "selected_rows": len(selected),
        "outputs": report["outputs"],
    }, indent=2))


if __name__ == "__main__":
    main()
