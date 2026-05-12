from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

import build_ingredient_fingerprint_clusters as ingredient_clusters
import cluster_spine_common as common
import self_heal_policy as policy


DEFAULT_INPUT_MAP = common.OUT_DIR / "product_to_best_esha_full_map.csv"
OUT_CSV = common.CLUSTER_PROJECTION_CSV
OUT_JSON = common.OUT_DIR / "product_to_best_esha_full_map.vCluster_summary.json"


def projection_guard_reason(row: pd.Series) -> str:
    code = str(row.get("best_esha_code") or "").strip()
    if not code:
        return ""
    product_description = str(row.get("product_description") or "")
    category = str(row.get("branded_food_category") or "")
    esha_description = str(row.get("best_esha_description") or "")
    head = str(row.get("best_esha_head") or common.esha_head(esha_description))
    head_norm = common.norm_head(head)
    title_tokens = set(ingredient_clusters.title_tokens(product_description))
    product_text = common.norm_text(f"{product_description} {category}")
    esha_text = common.norm_text(esha_description)

    ok, reason = policy.category_allows_head(
        category=category,
        product_description=product_description,
        title_tokens=title_tokens,
        candidate_head=head,
    )
    if not ok:
        return reason
    narrow = policy.narrow_head_requires_title_support(head, title_tokens, product_description)
    if narrow:
        return narrow

    category_l = category.lower()
    if ("pasta by shape" in category_l or category_l == "all noodles") and head_norm not in {"pasta", "noodles", "macaroni"}:
        return f"dry_pasta_category_to_wrong_head:{head}"
    if "canned & bottled beans" in category_l and head_norm in {"beans rice", "beans and rice"} and "rice" not in title_tokens:
        return "canned_beans_to_beans_rice_without_rice"
    if "vanilla bean" in product_text and head_norm in {"beans", "baked beans", "refried beans", "beans rice", "beans and rice"}:
        return "vanilla_bean_flavor_to_beans"
    if "popcorn" in title_tokens and head_norm == "butter" and "popcorn" not in esha_text:
        return "popcorn_to_plain_butter"
    if "popcorn" in title_tokens and head_norm == "nut butter":
        return "popcorn_to_nut_butter"
    if ("mashed" in title_tokens or "mash" in title_tokens) and (title_tokens & {"potato", "potatoes"}):
        meal_terms = {"chicken", "turkey", "beef", "pork", "steak", "meatloaf", "patty", "loaf", "bowl", "meal", "dinner", "entree"}
        if not (title_tokens & meal_terms) and head_norm != "mashed potatoes":
            return f"plain_mashed_potatoes_to_wrong_head:{head}"
        if head_norm in {"meal", "dish"}:
            missing = common.self_heal.missing_meal_components(esha_description, title_tokens)
            if missing:
                return "mashed_potatoes_meal_extra_components:" + ",".join(sorted(missing))
    return ""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-map", type=Path, default=DEFAULT_INPUT_MAP)
    parser.add_argument("--members", type=Path, default=common.PRODUCT_CLUSTER_MEMBERS_CSV)
    parser.add_argument("--assignments", type=Path, default=common.CLUSTER_ASSIGNMENTS_CSV)
    parser.add_argument("--output", type=Path, default=OUT_CSV)
    args = parser.parse_args()

    print("loading map, members, assignments", flush=True)
    current = pd.read_csv(args.input_map, dtype=str, keep_default_na=False, low_memory=False)
    members = common.load_cluster_members(args.members)[["fdc_id", "gtin_upc", "cluster_id"]]
    assignments = pd.read_csv(args.assignments, dtype=str, keep_default_na=False, low_memory=False)
    keep_cols = [
        "cluster_id", "assignment_status", "assignment_confidence", "assignment_reason",
        "assigned_esha_code", "assigned_esha_description", "assigned_esha_head",
        "assigned_esha_family", "assignment_score", "candidate_pool_size",
    ]
    assignments = assignments[[c for c in keep_cols if c in assignments.columns]].drop_duplicates("cluster_id", keep="first")
    out = current.merge(members.drop_duplicates("fdc_id", keep="first"), on=["fdc_id", "gtin_upc"], how="left")
    out = out.merge(assignments, on="cluster_id", how="left")
    if "best_esha_head" not in out.columns:
        out.insert(out.columns.get_loc("best_esha_description") + 1, "best_esha_head", "")
    out["cluster_assignment_status"] = out["assignment_status"].fillna("unassigned")
    out["cluster_assignment_reason"] = out["assignment_reason"].fillna("no_cluster_assignment")

    assigned = out["assignment_status"].eq("assigned")
    out.loc[assigned, "best_esha_code"] = out.loc[assigned, "assigned_esha_code"]
    out.loc[assigned, "best_esha_description"] = out.loc[assigned, "assigned_esha_description"]
    out.loc[assigned, "best_esha_head"] = out.loc[assigned, "assigned_esha_head"]
    out.loc[assigned, "best_esha_family"] = out.loc[assigned, "assigned_esha_family"]
    out.loc[assigned, "score"] = out.loc[assigned, "assignment_score"]
    out.loc[assigned, "n_candidates"] = out.loc[assigned, "candidate_pool_size"]
    out.loc[assigned, "assignment_source"] = "cluster_spine_v1"

    guard_reasons: dict[int, str] = {}
    for idx, row in out.loc[assigned].iterrows():
        reason = projection_guard_reason(row)
        if reason:
            guard_reasons[idx] = reason
    if guard_reasons:
        out["projection_guard_reason"] = ""
        for idx, reason in guard_reasons.items():
            out.at[idx, "projection_guard_reason"] = reason
        blocked = out["projection_guard_reason"].astype(str).str.strip() != ""
        for col in ("best_esha_code", "best_esha_description", "best_esha_head", "best_esha_family", "score"):
            if col in out.columns:
                out.loc[blocked, col] = ""
        if "n_candidates" in out.columns:
            out.loc[blocked, "n_candidates"] = "0"
        out.loc[blocked, "assignment_source"] = "cluster_spine_projection_rejected"
        out.loc[blocked, "cluster_assignment_status"] = "projection_rejected"
        out.loc[blocked, "cluster_assignment_reason"] = "row_projection_guard:" + out.loc[blocked, "projection_guard_reason"]
        print(f"  projection guard rejected rows: {int(blocked.sum()):,}", flush=True)
    elif "projection_guard_reason" not in out.columns:
        out["projection_guard_reason"] = ""

    unassigned = ~assigned
    for col in ("best_esha_code", "best_esha_description", "best_esha_head", "best_esha_family", "score"):
        if col in out.columns:
            out.loc[unassigned, col] = ""
    if "n_candidates" in out.columns:
        out.loc[unassigned, "n_candidates"] = "0"
    out.loc[unassigned, "assignment_source"] = "cluster_spine_unassigned"

    drop_internal = [
        "assignment_status", "assignment_confidence", "assignment_reason",
        "assigned_esha_code", "assigned_esha_description", "assigned_esha_head",
        "assigned_esha_family", "assignment_score", "candidate_pool_size",
    ]
    out = out.drop(columns=[c for c in drop_internal if c in out.columns])
    out.to_csv(args.output, index=False)
    summary = {
        "input_map": str(args.input_map),
        "output": str(args.output),
        "rows": int(len(out)),
        "assigned_rows": int((out["best_esha_code"].astype(str).str.strip() != "").sum()),
        "unassigned_rows": int((out["best_esha_code"].astype(str).str.strip() == "").sum()),
        "assignment_sources": out["assignment_source"].value_counts().head(40).to_dict(),
        "cluster_status_counts": out["cluster_assignment_status"].value_counts().head(20).to_dict(),
    }
    OUT_JSON.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
