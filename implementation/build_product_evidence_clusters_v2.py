from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import pandas as pd

import build_ingredient_fingerprint_clusters as ingredient_clusters
import cluster_spine_common as common
import self_heal_common as self_heal


OUT_CLUSTERS = common.PRODUCT_CLUSTERS_CSV
OUT_MEMBERS = common.PRODUCT_CLUSTER_MEMBERS_CSV
OUT_JSON = common.OUT_DIR / "product_evidence_clusters_v2_summary.json"
DEFAULT_MAP = common.OUT_DIR / "product_to_best_esha_full_map.csv"


def _first_mode(values: pd.Series) -> str:
    vals = [str(v) for v in values if str(v)]
    if not vals:
        return ""
    return Counter(vals).most_common(1)[0][0]


def _short_representative(values: pd.Series) -> str:
    vals = [str(v) for v in values if str(v)]
    if not vals:
        return ""
    counts = Counter(vals)
    top_count = counts.most_common(1)[0][1]
    tied = [v for v, n in counts.items() if n == top_count]
    return sorted(tied, key=lambda s: (len(s), s))[0]


def build_members(current_map_path: Path) -> pd.DataFrame:
    print("loading products", flush=True)
    products = ingredient_clusters.load_products()
    if current_map_path.exists():
        current = ingredient_clusters.load_current_map(current_map_path)
        cols = [
            c
            for c in (
                "gtin_upc", "fdc_id", "best_esha_code", "best_esha_description",
                "best_esha_head", "best_esha_family", "score", "n_candidates",
                "assignment_source",
            )
            if c in current.columns
        ]
        products = products.merge(current[cols].drop_duplicates("fdc_id", keep="first"), on=["gtin_upc", "fdc_id"], how="left")

    rows: list[dict[str, object]] = []
    for i, row in products.iterrows():
        if (i + 1) % 50000 == 0:
            print(f"  product evidence rows: {i + 1:,}/{len(products):,}", flush=True)
        desc = str(row.get("product_description") or "")
        category = str(row.get("branded_food_category") or "")
        title = set(ingredient_clusters.title_tokens(desc))
        ingredients = set(ingredient_clusters.tokenize_ingredients(str(row.get("ingredients") or "")))
        lane = self_heal.category_lane_for(desc, category, title)
        form = self_heal.product_form_for(desc, category, lane, title)
        role = self_heal.role_for(desc, lane, form, title)
        product_family = ingredient_clusters.product_family_for(desc, category, tuple(title))
        primary = ingredient_clusters.primary_food(tuple(title))
        state = ingredient_clusters.state_lane(desc, category, tuple(title))
        state_group = common.state_bucket(state)
        title_identity = common.title_identity_terms(title, lane, form, primary)
        ingredient_profile = ingredient_clusters.ingredient_profile_key(tuple(sorted(ingredients)), product_family, primary)
        ingredient_core = common.ingredient_core_terms(ingredients, title_identity, primary)
        subtypes = common.subtype_keys(set(title_identity) | set(ingredient_core) | title, f"{desc} {row.get('ingredients', '')}")
        target_heads = self_heal.target_heads_for(lane, form, role, title)
        ingredient_basis = " ".join(ingredient_core[:40])
        if not ingredient_basis:
            ingredient_basis = ingredient_profile[:240]
        cluster_basis = (
            lane,
            form,
            role,
            primary,
            state_group,
            " ".join(title_identity[:40]),
            ingredient_basis,
            "|".join(sorted(subtypes)),
        )
        cluster_id = common.cluster_id_for(cluster_basis)
        rows.append(
            {
                "cluster_id": cluster_id,
                "gtin_upc": row.get("gtin_upc", ""),
                "fdc_id": row.get("fdc_id", ""),
                "product_description": desc,
                "branded_food_category": category,
                "brand_owner": row.get("brand_owner", ""),
                "brand_name": row.get("brand_name", ""),
                "category_lane": lane,
                "product_form": form,
                "product_role": role,
                "product_family_hint": product_family,
                "primary_food": primary,
                "state_lane": state,
                "state_bucket": state_group,
                "title_identity_terms": " ".join(title_identity),
                "ingredient_core_terms": " ".join(ingredient_core),
                "ingredient_profile_signature": ingredient_profile,
                "ingredient_signature": ingredient_clusters.ingredient_key(tuple(sorted(ingredients))),
                "subtype_keys": " ".join(sorted(subtypes)),
                "target_heads": "|".join(target_heads),
                "title_tokens": " ".join(sorted(title)),
                "ingredient_tokens": " ".join(sorted(ingredients)),
                "current_esha_code": row.get("best_esha_code", ""),
                "current_esha_description": row.get("best_esha_description", ""),
                "current_esha_head": row.get("best_esha_head", ""),
                "current_esha_family": row.get("best_esha_family", ""),
                "current_assignment_source": row.get("assignment_source", ""),
            }
        )
    return pd.DataFrame(rows)


def build_clusters(members: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for cluster_id, group in members.groupby("cluster_id", sort=False):
        title_counter: Counter[str] = Counter()
        ingredient_counter: Counter[str] = Counter()
        for value in group["title_identity_terms"].astype(str):
            title_counter.update(value.split())
        for value in group["ingredient_core_terms"].astype(str):
            ingredient_counter.update(value.split())
        rows.append(
            {
                "cluster_id": cluster_id,
                "n_products": int(len(group)),
                "category_lane": _first_mode(group["category_lane"]),
                "product_form": _first_mode(group["product_form"]),
                "product_role": _first_mode(group["product_role"]),
                "product_family_hint": _first_mode(group["product_family_hint"]),
                "primary_food": _first_mode(group["primary_food"]),
                "state_bucket": _first_mode(group["state_bucket"]),
                "state_lane_top": common.top_counts(group["state_lane"], 8),
                "title_identity_terms": " ".join(sorted(title_counter)),
                "ingredient_core_terms": " ".join(sorted(ingredient_counter)),
                "subtype_keys": " ".join(sorted({t for v in group["subtype_keys"].astype(str) for t in v.split()})),
                "target_heads": _first_mode(group["target_heads"]),
                "dominant_title_tokens": " ".join(t for t, _ in title_counter.most_common(40)),
                "dominant_ingredient_terms": " ".join(t for t, _ in ingredient_counter.most_common(40)),
                "dominant_category": _first_mode(group["branded_food_category"]),
                "top_categories": common.top_counts(group["branded_food_category"], 15),
                "top_brands": common.top_counts(group["brand_name"], 12),
                "top_current_codes": common.top_counts(group["current_esha_code"], 12),
                "dominant_current_code": _first_mode(group["current_esha_code"]),
                "dominant_current_head": _first_mode(group["current_esha_head"]),
                "dominant_product_description": _short_representative(group["product_description"]),
                "sample_fdc_ids": " ".join(group["fdc_id"].astype(str).head(20)),
                "sample_gtins": " ".join(group["gtin_upc"].astype(str).head(20)),
            }
        )
    out = pd.DataFrame(rows)
    return out.sort_values(["n_products", "cluster_id"], ascending=[False, True])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--current-map", type=Path, default=DEFAULT_MAP)
    parser.add_argument("--clusters", type=Path, default=OUT_CLUSTERS)
    parser.add_argument("--members", type=Path, default=OUT_MEMBERS)
    args = parser.parse_args()

    members = build_members(args.current_map)
    print("building cluster summaries", flush=True)
    clusters = build_clusters(members)
    members.to_csv(args.members, index=False)
    clusters.to_csv(args.clusters, index=False)
    summary = {
        "members": str(args.members),
        "clusters": str(args.clusters),
        "products": int(len(members)),
        "clusters_total": int(len(clusters)),
        "clusters_multi_product": int((clusters["n_products"].astype(int) > 1).sum()),
        "products_in_multi_product_clusters": int(clusters.loc[clusters["n_products"].astype(int) > 1, "n_products"].astype(int).sum()),
        "top_lanes": clusters.groupby("category_lane")["n_products"].sum().sort_values(ascending=False).head(30).to_dict(),
        "top_forms": clusters.groupby("product_form")["n_products"].sum().sort_values(ascending=False).head(30).to_dict(),
    }
    OUT_JSON.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
