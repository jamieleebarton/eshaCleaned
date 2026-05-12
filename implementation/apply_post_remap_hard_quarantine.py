from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

import build_ingredient_fingerprint_clusters as ingredient_clusters


ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "implementation" / "output"
DEFAULT_INPUT = OUT_DIR / "product_to_best_esha_full_map.vM2.csv"
DEFAULT_OUTPUT = OUT_DIR / "product_to_best_esha_full_map.vM3.csv"
OUT_QUARANTINE = OUT_DIR / "post_remap_hard_quarantine.csv"
OUT_SUMMARY = OUT_DIR / "post_remap_hard_quarantine_summary.json"


def classify_hard_quarantine(
    features: pd.DataFrame,
    anchors: dict[str, ingredient_clusters.EshaAnchor],
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    assigned = features[features["best_esha_code"].astype(str).str.strip() != ""]
    for _, product in assigned.iterrows():
        code = str(product.get("best_esha_code") or "").split(".")[0]
        anchor = anchors.get(code)
        if anchor is None:
            continue
        ok, reason = ingredient_clusters.candidate_gate(product, anchor)
        evidence = set(product["_title_tokens"]) | set(product["_ingredient_tokens"])
        structural_reason = ingredient_clusters.form_mismatch_reason(product, anchor, evidence)
        display_reason = structural_reason or reason
        if ok:
            continue
        hard = ingredient_clusters.hard_quarantine(product, anchor, reason)
        if not hard:
            continue
        if ingredient_clusters.is_infant_food_anchor(anchor.description.lower(), set(anchor.tokens)) and not ingredient_clusters.is_infant_product(
            str(product.get("product_description") or ""),
            str(product.get("branded_food_category") or ""),
            evidence,
        ):
            display_reason = "infant_anchor_without_infant_product"
        rows.append(
            {
                "gtin_upc": product["gtin_upc"],
                "fdc_id": product["fdc_id"],
                "product_description": product["product_description"],
                "branded_food_category": product["branded_food_category"],
                "brand_owner": product["brand_owner"],
                "brand_name": product["brand_name"],
                "current_esha_code": code,
                "current_esha_description": product.get("best_esha_description", ""),
                "current_esha_family": product.get("best_esha_family", ""),
                "current_esha_head": str(product.get("best_esha_description", "")).split(",", 1)[0].strip(),
                "assignment_source": product.get("assignment_source", ""),
                "score": product.get("score", ""),
                "product_family": product["_product_family"],
                "primary_food": product["_primary"],
                "state_lane": product["_state_lane"],
                "ingredient_key": product["_ingredient_key"],
                "quarantine_reason": display_reason,
            }
        )
    return pd.DataFrame(rows)


def apply_quarantine(current: pd.DataFrame, quarantine: pd.DataFrame) -> pd.DataFrame:
    out = current.copy()
    if quarantine.empty:
        return out

    q_ids = set(quarantine["fdc_id"].astype(str))
    matched = out["fdc_id"].astype(str).isin(q_ids) & (out["best_esha_code"].astype(str).str.strip() != "")
    for col in ("best_esha_code", "best_esha_description", "best_esha_head", "best_esha_family", "score"):
        if col in out.columns:
            out.loc[matched, col] = ""
    if "n_candidates" in out.columns:
        out.loc[matched, "n_candidates"] = "0"
    out.loc[matched, "assignment_source"] = "ingredient_candidate_gate_quarantine"
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-map", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-map", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"loading map: {args.input_map}", flush=True)
    current = ingredient_clusters.load_current_map(args.input_map)
    print(f"  rows: {len(current):,}", flush=True)

    print("loading products/features", flush=True)
    products = ingredient_clusters.load_products()
    features = ingredient_clusters.build_product_features(products, current)

    print("loading ESHA anchors", flush=True)
    anchors = ingredient_clusters.load_esha_anchors()

    print("classifying hard post-remap conflicts", flush=True)
    quarantine = classify_hard_quarantine(features, anchors)
    quarantine.to_csv(OUT_QUARANTINE, index=False)
    print(f"  wrote {OUT_QUARANTINE.relative_to(ROOT)} ({len(quarantine):,})", flush=True)

    out = apply_quarantine(current, quarantine)
    out.to_csv(args.output_map, index=False)

    assigned_before = int((current["best_esha_code"].astype(str).str.strip() != "").sum())
    assigned_after = int((out["best_esha_code"].astype(str).str.strip() != "").sum())
    summary = {
        "input_map": str(args.input_map),
        "output_map": str(args.output_map),
        "rows": int(len(current)),
        "assigned_before": assigned_before,
        "assigned_after": assigned_after,
        "newly_quarantined": int(assigned_before - assigned_after),
        "quarantine_rows": int(len(quarantine)),
        "quarantine_reasons": quarantine["quarantine_reason"].value_counts().head(50).to_dict() if not quarantine.empty else {},
        "quarantine_sources": quarantine["assignment_source"].value_counts().head(30).to_dict() if not quarantine.empty else {},
    }
    OUT_SUMMARY.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"  wrote {args.output_map.relative_to(ROOT) if args.output_map.is_absolute() else args.output_map}", flush=True)
    print(json.dumps(summary, indent=2, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
