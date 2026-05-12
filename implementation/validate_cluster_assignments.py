from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

import build_ingredient_fingerprint_clusters as ingredient_clusters
import cluster_spine_common as common
import self_heal_policy as policy


OUT_CSV = common.CLUSTER_VALIDATION_CSV
OUT_JSON = common.OUT_DIR / "cluster_assignment_validation_summary.json"


def violation_reason(row: pd.Series) -> str:
    code = str(row.get("best_esha_code") or "").strip()
    if not code:
        return ""
    desc = str(row.get("product_description") or "")
    category = str(row.get("branded_food_category") or "")
    esha_desc = str(row.get("best_esha_description") or "")
    head = str(row.get("best_esha_head") or common.esha_head(esha_desc))
    head_norm = common.norm_head(head)
    title = set(ingredient_clusters.title_tokens(desc))
    text = common.norm_text(f"{desc} {category}")

    ok, reason = policy.category_allows_head(
        category=category,
        product_description=desc,
        title_tokens=title,
        candidate_head=head,
    )
    if not ok:
        return reason

    if ("pasta by shape" in category.lower() or category.lower() == "all noodles") and head_norm not in {"pasta", "noodles", "macaroni"}:
        return f"dry_pasta_category_to_wrong_head:{head}"
    if "canned & bottled beans" in category.lower() and head_norm not in {
        "beans", "baked beans", "refried beans", "pork and beans", "beans rice", "beans and rice", "snap beans", "soybeans"
    }:
        return f"canned_beans_category_to_wrong_head:{head}"
    if "vanilla bean" in text and head_norm in {"beans", "baked beans", "refried beans"}:
        return "vanilla_bean_flavor_to_beans"
    if "popcorn" in title and head_norm == "butter" and "popcorn" not in common.norm_text(esha_desc):
        return "popcorn_to_plain_butter"
    if "popcorn" in title and head_norm == "nut butter":
        return "popcorn_to_nut_butter"
    if ("mashed" in title or "mash" in title) and (title & {"potato", "potatoes"}):
        meal_terms = {"chicken", "turkey", "beef", "pork", "steak", "meatloaf", "bowl", "meal", "dinner", "entree"}
        if not (title & meal_terms) and head_norm != "mashed potatoes":
            return f"plain_mashed_potatoes_to_wrong_head:{head}"
        if head_norm in {"meal", "dish"}:
            evidence = title | set(ingredient_clusters.tokenize_ingredients(str(row.get("ingredients") or "")))
            missing = common.self_heal.missing_meal_components(esha_desc, evidence)
            if missing:
                return "mashed_potatoes_meal_extra_components:" + ",".join(sorted(missing))
    if "yogurt" in category.lower() and head_norm in {"beans", "bacon", "butter", "pasta", "pasta dish"}:
        return f"yogurt_category_to_wrong_head:{head}"
    return ""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--map", type=Path, default=common.CLUSTER_PROJECTION_CSV)
    parser.add_argument("--output", type=Path, default=OUT_CSV)
    args = parser.parse_args()

    print(f"loading {args.map}", flush=True)
    df = pd.read_csv(args.map, dtype=str, keep_default_na=False, low_memory=False)
    reasons = []
    for i, row in df.iterrows():
        if (i + 1) % 50000 == 0:
            print(f"  validated rows: {i + 1:,}/{len(df):,}", flush=True)
        reasons.append(violation_reason(row))
    df["hard_violation_reason"] = reasons
    violations = df[df["hard_violation_reason"].astype(str).str.strip() != ""].copy()
    columns = [
        "gtin_upc", "fdc_id", "product_description", "branded_food_category",
        "brand_owner", "brand_name", "best_esha_code", "best_esha_description",
        "best_esha_head", "best_esha_family", "assignment_source", "cluster_id",
        "cluster_assignment_status", "hard_violation_reason",
    ]
    violations[[c for c in columns if c in violations.columns]].to_csv(args.output, index=False)
    summary = {
        "map": str(args.map),
        "output": str(args.output),
        "rows": int(len(df)),
        "assigned_rows": int((df["best_esha_code"].astype(str).str.strip() != "").sum()),
        "hard_violation_rows": int(len(violations)),
        "hard_violation_reasons": violations["hard_violation_reason"].value_counts().head(50).to_dict(),
    }
    OUT_JSON.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
