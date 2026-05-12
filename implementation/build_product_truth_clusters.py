from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

import self_heal_common as sh


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--product-facts", type=Path, default=sh.SELF_HEAL_DIR / "product_facts.csv")
    parser.add_argument("--output", type=Path, default=sh.SELF_HEAL_DIR / "product_clusters.csv")
    args = parser.parse_args()

    sh.SELF_HEAL_DIR.mkdir(parents=True, exist_ok=True)
    facts = pd.read_csv(args.product_facts, dtype=str, keep_default_na=False, low_memory=False)
    rows = []
    for cluster_key, group in facts.groupby("cluster_key", sort=False):
        first = group.iloc[0]
        rows.append(
            {
                "cluster_key": cluster_key,
                "n_products": int(len(group)),
                # cluster_key already includes the structural facts; first row is
                # enough and avoids computing pandas mode() hundreds of thousands
                # of times.
                "category_lane": first.get("category_lane", ""),
                "product_form": first.get("product_form", ""),
                "product_role": first.get("product_role", ""),
                "target_heads": first.get("target_heads", ""),
                "top_categories": sh.top_values(group["branded_food_category"], 5),
                "top_identities": sh.top_values(group["identity_terms"], 5),
                "top_current_codes": sh.top_values(group.get("best_esha_code", pd.Series(dtype=str)), 5),
                "examples": " || ".join(group["product_description"].astype(str).head(5)),
            }
        )
    clusters = pd.DataFrame(rows).sort_values("n_products", ascending=False)
    clusters.to_csv(args.output, index=False)
    summary = {
        "product_facts": str(args.product_facts),
        "output": str(args.output),
        "clusters": int(len(clusters)),
        "products": int(len(facts)),
        "top_forms": clusters.groupby("product_form")["n_products"].sum().sort_values(ascending=False).head(50).to_dict(),
        "top_lanes": clusters.groupby("category_lane")["n_products"].sum().sort_values(ascending=False).head(50).to_dict(),
    }
    sh.summarize_json(args.output.with_suffix(".summary.json"), summary)
    print(f"wrote {args.output} ({len(clusters):,})", flush=True)


if __name__ == "__main__":
    main()
