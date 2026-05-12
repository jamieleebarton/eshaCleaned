from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

import pandas as pd

import build_ingredient_fingerprint_clusters as ingredient_clusters


ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "implementation" / "output"
DEFAULT_MAP = OUT_DIR / "product_to_best_esha_full_map.vM.csv"
DEFAULT_COMPARE_MAP = OUT_DIR / "product_to_best_esha_full_map.vCluster.csv"

OUT_MEMBERS = OUT_DIR / "ingredient_only_cluster_members.csv"
OUT_CLUSTERS = OUT_DIR / "ingredient_only_clusters.csv"
OUT_SUMMARY = OUT_DIR / "ingredient_only_cluster_summary.json"


def cluster_id_for(signature: str) -> str:
    return hashlib.sha1(signature.encode("utf-8")).hexdigest()[:18]


def top_counts(values: pd.Series, limit: int = 12) -> str:
    counts = Counter(str(v) for v in values if str(v))
    return " | ".join(f"{k}:{v}" for k, v in counts.most_common(limit))


def top_share(values: pd.Series) -> float:
    vals = [str(v) for v in values if str(v)]
    if not vals:
        return 0.0
    return Counter(vals).most_common(1)[0][1] / len(vals)


def top_value(values: pd.Series) -> str:
    vals = [str(v) for v in values if str(v)]
    if not vals:
        return ""
    return Counter(vals).most_common(1)[0][0]


def sample_values(values: pd.Series, limit: int = 10) -> str:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
        if len(out) >= limit:
            break
    return " || ".join(out)


def load_map(path: Path, prefix: str) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=["gtin_upc", "fdc_id"])
    df = ingredient_clusters.load_current_map(path)
    keep = [
        "gtin_upc",
        "fdc_id",
        "best_esha_code",
        "best_esha_description",
        "best_esha_head",
        "assignment_source",
    ]
    keep = [c for c in keep if c in df.columns]
    df = df[keep].copy()
    return df.rename(
        columns={
            "best_esha_code": f"{prefix}_esha_code",
            "best_esha_description": f"{prefix}_esha_description",
            "best_esha_head": f"{prefix}_esha_head",
            "assignment_source": f"{prefix}_assignment_source",
        }
    )


def build_members(map_path: Path, compare_map_path: Path | None) -> pd.DataFrame:
    products = ingredient_clusters.load_products()
    products["ingredient_tokens"] = products["ingredients"].map(ingredient_clusters.tokenize_ingredients)
    products["ingredient_signature"] = products["ingredient_tokens"].map(ingredient_clusters.ingredient_key)
    products["ingredient_token_count"] = products["ingredient_tokens"].map(lambda x: len(set(x)))
    products = products[products["ingredient_signature"].astype(str).str.strip() != ""].copy()
    products["ingredient_cluster_id"] = products["ingredient_signature"].map(cluster_id_for)
    products["ingredient_tokens"] = products["ingredient_tokens"].map(lambda x: " ".join(x))

    current = load_map(map_path, "map")
    products = products.merge(current.drop_duplicates("fdc_id", keep="first"), on=["gtin_upc", "fdc_id"], how="left")
    if compare_map_path:
        compare = load_map(compare_map_path, "compare")
        products = products.merge(compare.drop_duplicates("fdc_id", keep="first"), on=["gtin_upc", "fdc_id"], how="left")

    for col in products.columns:
        if products[col].dtype == object:
            products[col] = products[col].fillna("")
    return products


def build_clusters(members: pd.DataFrame) -> pd.DataFrame:
    group_col = "ingredient_cluster_id"
    counts = members.groupby(group_col, sort=False).size().rename("n_products").reset_index()
    first = members.drop_duplicates(group_col, keep="first")[
        [group_col, "ingredient_signature", "ingredient_token_count"]
    ].copy()
    out = counts.merge(first, on=group_col, how="left")

    # Expensive evidence summaries are only useful for clusters with neighbors.
    multi_ids = set(out.loc[out["n_products"].astype(int) > 1, group_col])
    summary_rows: list[dict[str, object]] = []
    for cluster_id, group in members[members[group_col].isin(multi_ids)].groupby(group_col, sort=False):
        summary_rows.append(
            {
                group_col: cluster_id,
                "top_categories": top_counts(group["branded_food_category"], 20),
                "category_count": int(group["branded_food_category"].astype(str).replace("", pd.NA).dropna().nunique()),
                "category_top_share": round(top_share(group["branded_food_category"]), 4),
                "top_brands": top_counts(group["brand_name"], 20),
                "brand_count": int(group["brand_name"].astype(str).replace("", pd.NA).dropna().nunique()),
                "top_map_codes": top_counts(group.get("map_esha_code", pd.Series(dtype=str)), 20),
                "map_code_count": int(group.get("map_esha_code", pd.Series(dtype=str)).astype(str).replace("", pd.NA).dropna().nunique()),
                "map_code_top_share": round(top_share(group.get("map_esha_code", pd.Series(dtype=str))), 4),
                "top_map_heads": top_counts(group.get("map_esha_head", pd.Series(dtype=str)), 20),
                "map_head_count": int(group.get("map_esha_head", pd.Series(dtype=str)).astype(str).replace("", pd.NA).dropna().nunique()),
                "map_head_top_share": round(top_share(group.get("map_esha_head", pd.Series(dtype=str))), 4),
                "top_compare_codes": top_counts(group.get("compare_esha_code", pd.Series(dtype=str)), 20),
                "compare_code_count": int(group.get("compare_esha_code", pd.Series(dtype=str)).astype(str).replace("", pd.NA).dropna().nunique()),
                "sample_products": sample_values(group["product_description"], 12),
            }
        )
    summaries = pd.DataFrame(summary_rows)
    if not summaries.empty:
        out = out.merge(summaries, on=group_col, how="left")
    for col in (
        "top_categories", "top_brands", "top_map_codes", "top_map_heads",
        "top_compare_codes", "sample_products",
    ):
        if col not in out.columns:
            out[col] = ""
        out[col] = out[col].fillna("")
    for col in ("category_count", "brand_count", "map_code_count", "map_head_count", "compare_code_count"):
        if col not in out.columns:
            out[col] = 0
        out[col] = out[col].fillna(0).astype(int)
    for col in ("category_top_share", "map_code_top_share", "map_head_top_share"):
        if col not in out.columns:
            out[col] = 0.0
        out[col] = out[col].fillna(0.0).astype(float)
    return out.sort_values(["n_products", group_col], ascending=[False, True])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--map", type=Path, default=DEFAULT_MAP)
    parser.add_argument("--compare-map", type=Path, default=DEFAULT_COMPARE_MAP)
    parser.add_argument("--members", type=Path, default=OUT_MEMBERS)
    parser.add_argument("--clusters", type=Path, default=OUT_CLUSTERS)
    args = parser.parse_args()

    print("building ingredient-only members", flush=True)
    members = build_members(args.map, args.compare_map if args.compare_map.exists() else None)
    print("building ingredient-only clusters", flush=True)
    clusters = build_clusters(members)
    members.to_csv(args.members, index=False)
    clusters.to_csv(args.clusters, index=False)

    multi = clusters[clusters["n_products"].astype(int) > 1]
    large = clusters[clusters["n_products"].astype(int) >= 5]
    summary = {
        "map": str(args.map),
        "compare_map": str(args.compare_map) if args.compare_map.exists() else "",
        "members": str(args.members),
        "clusters": str(args.clusters),
        "products_with_ingredients": int(len(members)),
        "clusters_total": int(len(clusters)),
        "clusters_multi_product": int(len(multi)),
        "products_in_multi_product_clusters": int(multi["n_products"].astype(int).sum()),
        "clusters_ge_5_products": int(len(large)),
        "products_in_clusters_ge_5": int(large["n_products"].astype(int).sum()),
        "large_clusters_one_category_share_ge_90": int((large["category_top_share"].astype(float) >= 0.9).sum()),
        "large_clusters_one_map_code_share_ge_90": int((large["map_code_top_share"].astype(float) >= 0.9).sum()),
        "top_clusters": clusters.head(25)[
            ["n_products", "ingredient_signature", "top_categories", "top_map_codes", "sample_products"]
        ].to_dict(orient="records"),
    }
    OUT_SUMMARY.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
