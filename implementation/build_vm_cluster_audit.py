from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

import build_evidence_first_cluster_proposals as evidence
import self_heal_common as self_heal


ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "implementation" / "output"

DEFAULT_MEMBERS = OUT_DIR / "ingredient_only_cluster_members.csv"
DEFAULT_CLUSTERS = OUT_DIR / "ingredient_only_clusters.csv"
OUT_AUDIT = OUT_DIR / "vm_ingredient_cluster_audit.csv"
OUT_CONFLICTS = OUT_DIR / "vm_ingredient_cluster_conflicts.csv"
OUT_SUMMARY = OUT_DIR / "vm_ingredient_cluster_audit_summary.json"


def build_audit(
    members: pd.DataFrame,
    clusters: pd.DataFrame,
    by_code: dict[str, evidence.EshaCandidate],
    *,
    min_size: int,
    min_category_share: float,
) -> pd.DataFrame:
    eligible = clusters[clusters["n_products"].astype(int) >= min_size].copy()
    if min_category_share > 0 and "category_top_share" in eligible.columns:
        eligible = eligible[eligible["category_top_share"].astype(float) >= min_category_share]
    eligible_ids = set(eligible["ingredient_cluster_id"].astype(str))
    work = members[members["ingredient_cluster_id"].astype(str).isin(eligible_ids)].copy()

    rows: list[dict[str, object]] = []
    for processed, (cluster_id, group) in enumerate(work.groupby("ingredient_cluster_id", sort=False), start=1):
        if processed % 5000 == 0:
            print(f"  audited {processed:,} clusters", flush=True)

        n = len(group)
        ingredient_signature = str(group["ingredient_signature"].iloc[0])
        ingredient_terms = evidence.split_terms(ingredient_signature)
        dominant_category, _, category_share = evidence.top_value_and_share(group["branded_food_category"])
        dominant_brand, _, brand_share = evidence.top_value_and_share(group["brand_name"])
        dominant_desc = str(group["product_description"].iloc[0])

        title_counter = {}
        for text in group["product_description"].head(100):
            for tok in evidence.tokenize_text(text):
                title_counter[tok] = title_counter.get(tok, 0) + 1
        title_terms = {t for t, _ in sorted(title_counter.items(), key=lambda kv: (-kv[1], kv[0]))[:40]}
        lane = self_heal.category_lane_for(dominant_desc, dominant_category, title_terms)
        form = self_heal.product_form_for(dominant_desc, dominant_category, lane, title_terms)
        lane_terms = set(str(lane).replace("_", " ").split())
        form_terms = set(str(form).replace("_", " ").split())

        current_code, current_code_count, current_code_share = evidence.top_value_and_share(
            group.get("map_esha_code", pd.Series(dtype=str))
        )
        current_head, _, current_head_share = evidence.top_value_and_share(
            group.get("map_esha_head", pd.Series(dtype=str))
        )
        current_desc = ""
        if current_code:
            descs = group.loc[group["map_esha_code"].astype(str) == current_code, "map_esha_description"]
            current_desc = str(descs.iloc[0]) if len(descs) else ""

        current_reject = ""
        if current_code and current_code in by_code:
            current_reject = evidence.candidate_reject_reason(
                by_code[current_code],
                dominant_category=dominant_category,
                representative_description=dominant_desc,
                ingredient_terms=ingredient_terms,
                title_terms=title_terms,
                lane_terms=lane_terms,
                form_terms=form_terms,
            )

        current_code_count = int(group.get("map_esha_code", pd.Series(dtype=str)).astype(str).replace("", pd.NA).dropna().nunique())
        current_head_count = int(group.get("map_esha_head", pd.Series(dtype=str)).astype(str).replace("", pd.NA).dropna().nunique())
        category_count = int(group["branded_food_category"].astype(str).replace("", pd.NA).dropna().nunique())

        flags: list[str] = []
        if current_reject:
            flags.append("current_top_code_structural_reject")
        if n >= 5 and category_share >= 0.8 and current_code_count >= 4:
            flags.append("same_ingredient_category_maps_to_many_codes")
        if n >= 5 and category_share >= 0.8 and current_code and current_code_share < 0.25:
            flags.append("no_dominant_vM_code")
        if n >= 5 and category_count >= 4 and category_share < 0.8:
            flags.append("same_ingredients_cross_many_categories")
        if not current_code:
            flags.append("cluster_top_unassigned")

        rows.append(
            {
                "ingredient_cluster_id": cluster_id,
                "n_products": n,
                "ingredient_signature": ingredient_signature,
                "dominant_category": dominant_category,
                "category_top_share": round(category_share, 4),
                "category_count": category_count,
                "top_categories": evidence.top_counts(group["branded_food_category"], 16),
                "dominant_brand": dominant_brand,
                "brand_top_share": round(brand_share, 4),
                "brand_count": int(group["brand_name"].astype(str).replace("", pd.NA).dropna().nunique()),
                "top_brands": evidence.top_counts(group["brand_name"], 16),
                "dominant_lane": lane,
                "dominant_form": form,
                "title_terms": evidence.terms_summary(title_terms, 50),
                "current_top_code": current_code,
                "current_top_description": current_desc,
                "current_top_head": current_head,
                "current_code_top_share": round(current_code_share, 4),
                "current_head_top_share": round(current_head_share, 4),
                "current_code_count": current_code_count,
                "current_head_count": current_head_count,
                "current_reject_reason": current_reject,
                "audit_flags": "|".join(flags),
                "top_current_codes": evidence.top_counts(group.get("map_esha_code", pd.Series(dtype=str)), 16),
                "top_current_heads": evidence.top_counts(group.get("map_esha_head", pd.Series(dtype=str)), 16),
                "sample_products": evidence.sample_values(group["product_description"], 12),
            }
        )
    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--members", type=Path, default=DEFAULT_MEMBERS)
    parser.add_argument("--clusters", type=Path, default=DEFAULT_CLUSTERS)
    parser.add_argument("--out", type=Path, default=OUT_AUDIT)
    parser.add_argument("--conflicts", type=Path, default=OUT_CONFLICTS)
    parser.add_argument("--summary", type=Path, default=OUT_SUMMARY)
    parser.add_argument("--min-size", type=int, default=5)
    parser.add_argument("--min-category-share", type=float, default=0.8)
    args = parser.parse_args()

    print("loading ESHA code facts for current-code validation", flush=True)
    _, by_code, _, _ = evidence.load_esha_catalog(evidence.ESHA_CSV, evidence.CANONICAL_CSV)

    print("loading clusters and members", flush=True)
    clusters = pd.read_csv(args.clusters, dtype=str, keep_default_na=False, low_memory=False)
    eligible = clusters[clusters["n_products"].astype(int) >= args.min_size].copy()
    if args.min_category_share > 0 and "category_top_share" in eligible.columns:
        eligible = eligible[eligible["category_top_share"].astype(float) >= args.min_category_share]
    eligible_ids = set(eligible["ingredient_cluster_id"].astype(str))
    print(
        f"  eligible clusters >= {args.min_size} and category_share >= {args.min_category_share}: {len(eligible_ids):,}",
        flush=True,
    )
    members = pd.read_csv(args.members, dtype=str, keep_default_na=False, low_memory=False)
    audit = build_audit(
        members,
        clusters,
        by_code,
        min_size=args.min_size,
        min_category_share=args.min_category_share,
    )
    conflicts = audit[audit["audit_flags"].astype(str).str.strip() != ""].copy()
    audit = audit.sort_values(["n_products", "category_top_share"], ascending=[False, False])
    conflicts = conflicts.sort_values(["n_products", "category_top_share"], ascending=[False, False])
    audit.to_csv(args.out, index=False)
    conflicts.to_csv(args.conflicts, index=False)

    summary = {
        "members": str(args.members),
        "clusters": str(args.clusters),
        "audit": str(args.out),
        "conflicts": str(args.conflicts),
        "min_size": args.min_size,
        "min_category_share": args.min_category_share,
        "clusters_audited": int(len(audit)),
        "products_in_audited_clusters": int(audit["n_products"].astype(int).sum()) if not audit.empty else 0,
        "conflict_clusters": int(len(conflicts)),
        "products_in_conflict_clusters": int(conflicts["n_products"].astype(int).sum()) if not conflicts.empty else 0,
        "flag_counts": dict(
            sorted(
                (
                    flag,
                    int(audit["audit_flags"].astype(str).str.contains(flag, regex=False).sum()),
                )
                for flag in [
                    "current_top_code_structural_reject",
                    "same_ingredient_category_maps_to_many_codes",
                    "no_dominant_vM_code",
                    "same_ingredients_cross_many_categories",
                    "cluster_top_unassigned",
                ]
            )
        ),
        "top_conflicts": conflicts.head(30)[
            [
                "n_products",
                "ingredient_signature",
                "dominant_category",
                "category_top_share",
                "current_top_code",
                "current_top_description",
                "current_code_top_share",
                "current_code_count",
                "current_reject_reason",
                "audit_flags",
                "sample_products",
            ]
        ].to_dict(orient="records") if not conflicts.empty else [],
    }
    args.summary.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
