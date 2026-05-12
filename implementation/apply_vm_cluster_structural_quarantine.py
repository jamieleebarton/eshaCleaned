from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

import build_evidence_first_cluster_proposals as evidence
from identity_contract import compatibility_reason, esha_identity, product_identity
import self_heal_common as self_heal


ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "implementation" / "output"

DEFAULT_VM = OUT_DIR / "product_to_best_esha_full_map.vM.csv"
DEFAULT_CLUSTER_MAP = OUT_DIR / "product_to_best_esha_full_map.vCluster.csv"
DEFAULT_MEMBERS = OUT_DIR / "ingredient_only_cluster_members.csv"
DEFAULT_AUDIT = OUT_DIR / "vm_ingredient_cluster_audit.csv"
OUT_MAP = OUT_DIR / "product_to_best_esha_full_map.vM_cluster_quarantine.csv"
OUT_DIFF = OUT_DIR / "vm_cluster_structural_quarantine_diff.csv"
OUT_SUMMARY = OUT_DIR / "vm_cluster_structural_quarantine_summary.json"


def product_key_frame(df: pd.DataFrame) -> pd.Series:
    fdc = df.get("fdc_id", pd.Series([""] * len(df))).fillna("").astype(str).str.strip()
    gtin = df.get("gtin_upc", pd.Series([""] * len(df))).fillna("").astype(str).str.strip()
    return fdc.where(fdc != "", gtin)


def hard_structural_reason(reason: str) -> bool:
    return reason.startswith(
        (
            "head_without_product_form_support:",
            "category_head_mismatch:",
            "narrow_head_without_title_support:",
            "dried_fruit_",
            "fruit_state_mismatch:",
            "popcorn_product_to_plain_butter",
            "dry_pasta_head_on_prepared_product",
            "bean_subtype_mismatch:",
            "vanilla_bean_flavor_to_bean_code",
            "bean_head_without_bean_evidence",
            "meal_extra_components_absent:",
            "milk_state_mismatch:",
            "dressing_identity_mismatch:",
            "seafood_identity_mismatch:",
            "seafood_identity_absent:",
            "meat_species_mismatch:",
            "single_fruit_head_on_processed_product:",
            "single_fruit_head_without_produce_context",
            "identity_contract:",
        )
    )


def row_structural_reject_reason(
    row: pd.Series,
    *,
    by_code: dict[str, evidence.EshaCandidate],
    ingredient_signature: str,
) -> str:
    code = str(row.get("best_esha_code", "")).strip()
    if not code or code not in by_code:
        return ""
    product_description = str(row.get("product_description", "") or "")
    category = str(row.get("branded_food_category", "") or "")
    identity_reason = compatibility_reason(
        product_identity(
            product_description=product_description,
            category=category,
            ingredient_signature=ingredient_signature,
        ),
        esha_identity(by_code[code].description),
    )
    if identity_reason:
        return f"identity_contract:{identity_reason}"
    title_terms = set(evidence.tokenize_text(product_description))
    ingredient_terms = evidence.split_terms(ingredient_signature)
    lane = self_heal.category_lane_for(product_description, category, title_terms)
    form = self_heal.product_form_for(product_description, category, lane, title_terms)
    reason = evidence.candidate_reject_reason(
        by_code[code],
        dominant_category=category,
        representative_description=product_description,
        ingredient_terms=ingredient_terms,
        title_terms=title_terms,
        lane_terms=set(str(lane).replace("_", " ").split()),
        form_terms=set(str(form).replace("_", " ").split()),
    )
    return reason if reason and hard_structural_reason(reason) else ""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--vm", type=Path, default=DEFAULT_VM)
    parser.add_argument("--cluster-map", type=Path, default=DEFAULT_CLUSTER_MAP)
    parser.add_argument("--members", type=Path, default=DEFAULT_MEMBERS)
    parser.add_argument("--audit", type=Path, default=DEFAULT_AUDIT)
    parser.add_argument("--out", type=Path, default=OUT_MAP)
    parser.add_argument("--diff", type=Path, default=OUT_DIFF)
    parser.add_argument("--summary", type=Path, default=OUT_SUMMARY)
    args = parser.parse_args()

    vm = pd.read_csv(args.vm, dtype=str, keep_default_na=False, low_memory=False)
    vm["product_key"] = product_key_frame(vm)
    members = pd.read_csv(
        args.members,
        dtype=str,
        keep_default_na=False,
        usecols=["gtin_upc", "fdc_id", "ingredient_cluster_id", "ingredient_signature"],
        low_memory=False,
    )
    members["product_key"] = product_key_frame(members)
    audit = pd.read_csv(args.audit, dtype=str, keep_default_na=False, low_memory=False)
    cluster_map = pd.DataFrame()
    if args.cluster_map.exists():
        cluster_map = pd.read_csv(args.cluster_map, dtype=str, keep_default_na=False, low_memory=False)
        cluster_map["product_key"] = product_key_frame(cluster_map)
        cluster_map = cluster_map.drop_duplicates("product_key", keep="first").set_index("product_key")

    print("loading ESHA code facts for row structural validation", flush=True)
    _, by_code, _, _ = evidence.load_esha_catalog(evidence.ESHA_CSV, evidence.CANONICAL_CSV)
    ingredient_by_product = (
        members.drop_duplicates("product_key", keep="first").set_index("product_key")["ingredient_signature"].to_dict()
    )

    structural = audit[
        audit["audit_flags"].astype(str).str.contains("current_top_code_structural_reject", regex=False)
        & (audit["current_top_code"].astype(str).str.strip() != "")
    ].copy()
    bad_pairs = structural[[
        "ingredient_cluster_id",
        "ingredient_signature",
        "dominant_category",
        "current_top_code",
        "current_top_description",
        "current_reject_reason",
        "audit_flags",
    ]].drop_duplicates()
    bad_pairs = bad_pairs.rename(columns={"ingredient_signature": "audit_ingredient_signature"})

    member_bad = members.merge(bad_pairs, on="ingredient_cluster_id", how="inner")
    targets = member_bad[["product_key", "current_top_code", "ingredient_cluster_id", "audit_ingredient_signature", "dominant_category", "current_top_description", "current_reject_reason", "audit_flags"]]
    targets = targets.rename(columns={"audit_ingredient_signature": "ingredient_signature"})
    targets = targets.drop_duplicates(["product_key", "current_top_code"])
    target_index = targets.set_index("product_key")

    out = vm.copy()
    cluster_matched = (
        out["product_key"].isin(target_index.index)
        & (out["best_esha_code"].astype(str).str.strip() != "")
        & out.apply(lambda r: str(r["best_esha_code"]) == str(target_index.loc[r["product_key"], "current_top_code"]) if r["product_key"] in target_index.index else False, axis=1)
    )
    row_reasons: list[str] = []
    row_bad: list[bool] = []
    replacement_reason: list[str] = []
    for i, r in out.iterrows():
        key = str(r["product_key"])
        reason = row_structural_reject_reason(
            r,
            by_code=by_code,
            ingredient_signature=str(ingredient_by_product.get(key, "")),
        )
        row_reasons.append(reason)
        row_bad.append(bool(reason))
        if reason:
            replacement_reason.append(reason)
        elif bool(cluster_matched.iloc[i]) and key in target_index.index:
            replacement_reason.append(str(target_index.loc[key, "current_reject_reason"]))
        else:
            replacement_reason.append("")

    row_bad_series = pd.Series(row_bad, index=out.index)
    matched = cluster_matched | row_bad_series

    replacement_rows: dict[int, pd.Series] = {}
    replacement_reject_reasons: dict[int, str] = {}
    if not cluster_map.empty:
        for idx in out.index[matched]:
            key = str(out.at[idx, "product_key"])
            if key not in cluster_map.index:
                continue
            candidate = cluster_map.loc[key]
            if not str(candidate.get("best_esha_code", "")).strip():
                continue
            candidate_reason = row_structural_reject_reason(
                candidate,
                by_code=by_code,
                ingredient_signature=str(ingredient_by_product.get(key, "")),
            )
            if candidate_reason:
                replacement_reject_reasons[idx] = candidate_reason
                continue
            replacement_rows[idx] = candidate

    before_cols = [
        "product_key",
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
        "assignment_source",
    ]
    before_cols = [c for c in before_cols if c in out.columns]
    diff = out.loc[matched, before_cols].copy()
    diff = diff.rename(
        columns={
            "best_esha_code": "old_best_esha_code",
            "best_esha_description": "old_best_esha_description",
            "best_esha_head": "old_best_esha_head",
            "best_esha_family": "old_best_esha_family",
            "score": "old_score",
            "assignment_source": "old_assignment_source",
        }
    )
    meta = targets.drop_duplicates("product_key").set_index("product_key")
    for col in [
        "ingredient_cluster_id",
        "ingredient_signature",
        "dominant_category",
        "current_top_description",
        "current_reject_reason",
        "audit_flags",
    ]:
        diff[col] = diff["product_key"].map(meta[col]) if not meta.empty and col in meta.columns else ""
    diff["row_structural_reject_reason"] = diff["product_key"].map(
        pd.Series(row_reasons, index=out["product_key"]).to_dict()
    )
    diff["effective_structural_reject_reason"] = diff["product_key"].map(
        pd.Series(replacement_reason, index=out["product_key"]).to_dict()
    )
    diff["replacement_reject_reason"] = ""
    diff["new_assignment_action"] = "quarantined"
    diff["new_best_esha_code"] = ""
    diff["new_best_esha_description"] = ""
    diff["new_best_esha_head"] = ""

    output_cols = [c for c in out.columns if c != "product_key"]
    remapped_count = 0
    for idx, candidate in replacement_rows.items():
        for col in [
            "best_esha_code",
            "best_esha_description",
            "best_esha_head",
            "best_esha_family",
            "score",
            "score_num",
            "n_candidates",
        ]:
            if col in out.columns and col in candidate.index:
                out.at[idx, col] = candidate[col]
        out.at[idx, "assignment_source"] = "kg_row_structural_remap_vcluster"
        remapped_count += 1
        key = out.at[idx, "product_key"]
        diff.loc[diff["product_key"] == key, "new_assignment_action"] = "remapped_from_vCluster"
        diff.loc[diff["product_key"] == key, "new_best_esha_code"] = candidate.get("best_esha_code", "")
        diff.loc[diff["product_key"] == key, "new_best_esha_description"] = candidate.get("best_esha_description", "")
        diff.loc[diff["product_key"] == key, "new_best_esha_head"] = candidate.get("best_esha_head", "")

    if replacement_reject_reasons:
        reject_reason_by_key = {out.at[idx, "product_key"]: reason for idx, reason in replacement_reject_reasons.items()}
        diff["replacement_reject_reason"] = diff["product_key"].map(reject_reason_by_key).fillna(diff["replacement_reject_reason"])

    remapped_index = set(replacement_rows)
    to_blank = matched & ~out.index.isin(remapped_index)
    for col in ["best_esha_code", "best_esha_description", "best_esha_head", "best_esha_family"]:
        if col in out.columns:
            out.loc[to_blank, col] = ""
    if "score" in out.columns:
        out.loc[to_blank, "score"] = "0"
    if "score_num" in out.columns:
        out.loc[to_blank, "score_num"] = "0"
    if "n_candidates" in out.columns:
        out.loc[to_blank, "n_candidates"] = "0"
    out.loc[to_blank, "assignment_source"] = "cluster_structural_quarantine"

    out[output_cols].to_csv(args.out, index=False)
    diff.to_csv(args.diff, index=False)

    assigned_before = int((vm["best_esha_code"].astype(str).str.strip() != "").sum())
    assigned_after = int((out["best_esha_code"].astype(str).str.strip() != "").sum())
    summary = {
        "source": str(args.vm),
        "output": str(args.out),
        "diff": str(args.diff),
        "structural_reject_clusters": int(len(structural)),
        "candidate_member_rows_in_rejected_clusters": int(len(member_bad)),
        "rows_quarantined": int(matched.sum()),
        "cluster_structural_rows": int(cluster_matched.sum()),
        "row_structural_rows": int(row_bad_series.sum()),
        "rows_remapped_from_vcluster": int(remapped_count),
        "rows_blank_quarantined": int(matched.sum() - remapped_count),
        "assigned_before": assigned_before,
        "assigned_after": assigned_after,
        "coverage_delta": assigned_after - assigned_before,
        "top_quarantine_reasons": diff["effective_structural_reject_reason"].value_counts().head(30).to_dict() if not diff.empty else {},
        "top_replacement_reject_reasons": diff["replacement_reject_reason"].value_counts().head(30).to_dict() if not diff.empty else {},
        "top_old_codes": diff["old_best_esha_description"].value_counts().head(30).to_dict() if not diff.empty else {},
    }
    args.summary.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
