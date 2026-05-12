"""Diagnostics on cluster_alignment.csv + product_to_anchor.csv outputs."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path("/Users/jamiebarton/Desktop/esha_audit_bundle")


def run(mode: str) -> dict:
    od = ROOT / "implementation" / "output" / f"embed_cluster_v1_{mode}"
    align = pd.read_csv(od / "cluster_alignment.csv")
    pmap = pd.read_csv(od / "product_to_anchor.csv", low_memory=False)

    out: dict = {"mode": mode}

    # 1. score distribution at various thresholds
    s = align["esha_score"].dropna()
    out["score_pct_at_thresholds"] = {
        "ge_0.60": int((s >= 0.60).sum()),
        "ge_0.70": int((s >= 0.70).sum()),
        "ge_0.75": int((s >= 0.75).sum()),
        "ge_0.80": int((s >= 0.80).sum()),
        "ge_0.85": int((s >= 0.85).sum()),
        "ge_0.90": int((s >= 0.90).sum()),
        "total_clusters": int(len(s)),
    }
    p_s = pmap["esha_score"].dropna()
    out["product_pct_at_thresholds"] = {
        "ge_0.60": int((p_s >= 0.60).sum()),
        "ge_0.70": int((p_s >= 0.70).sum()),
        "ge_0.75": int((p_s >= 0.75).sum()),
        "ge_0.80": int((p_s >= 0.80).sum()),
        "ge_0.85": int((p_s >= 0.85).sum()),
        "ge_0.90": int((p_s >= 0.90).sum()),
        "total_products": int(len(p_s)),
    }

    # 2. top 20 biggest clusters
    top = align.sort_values("n_products", ascending=False).head(20)
    out["top20_largest_clusters"] = top[
        [
            "cluster_id",
            "n_products",
            "top_brand",
            "top_category",
            "esha_label",
            "esha_score",
            "fndds_label",
            "sr28_label",
            "examples",
        ]
    ].to_dict(orient="records")

    # 3. ESHA-label diversity — are too many clusters mapped to the same code?
    code_counts = align.groupby("esha_label").size().sort_values(ascending=False)
    out["top20_most_used_esha_labels"] = code_counts.head(20).to_dict()
    out["unique_esha_labels"] = int(code_counts.shape[0])

    # 4. cookie/cake mixing check (form-mismatch leakage)
    def has_token(s: str, tokens: list[str]) -> bool:
        s = str(s).lower()
        return any(t in s for t in tokens)

    pmap_l = pmap.copy()
    pmap_l["d"] = pmap_l["description"].astype(str).str.lower()
    cookie_clusters = set(
        pmap_l[pmap_l["d"].str.contains(r"\bcookie", regex=True, na=False)][
            "cluster_id"
        ].unique()
    )
    cake_clusters = set(
        pmap_l[pmap_l["d"].str.contains(r"\bcake", regex=True, na=False)][
            "cluster_id"
        ].unique()
    )
    out["cookie_and_cake_overlap_clusters"] = len(cookie_clusters & cake_clusters)
    out["cookie_clusters"] = len(cookie_clusters)
    out["cake_clusters"] = len(cake_clusters)

    # 5. cheesecake variants (the user's example)
    cc = pmap_l[pmap_l["d"].str.contains("cheesecake", na=False)]
    cc_clusters = (
        cc.groupby("cluster_id")
        .agg(
            n=("description", "count"),
            ex=(
                "description",
                lambda s: " || ".join(s.dropna().astype(str).head(3).tolist()),
            ),
            esha=("esha_label", "first"),
            score=("esha_score", "first"),
        )
        .sort_values("n", ascending=False)
        .head(20)
    )
    out["top_cheesecake_clusters"] = cc_clusters.reset_index().to_dict(
        orient="records"
    )

    # 6. brand purity — confirm brand split worked
    brand_purity = (
        pmap_l[pmap_l["brand_name"].notna() & (pmap_l["brand_name"] != "")]
        .groupby("cluster_id")["brand_name"]
        .nunique()
    )
    out["brand_purity"] = {
        "clusters_with_brand": int(len(brand_purity)),
        "clusters_with_single_brand": int((brand_purity == 1).sum()),
        "clusters_with_mixed_brand": int((brand_purity > 1).sum()),
    }

    # 7. milk-family & jelly examples (the AGENTS.md known-bad pairs)
    bad_examples = []
    for query in [
        "GRACE EVAPORATED FILLED MILK",
        "HABANERO PEPPER JELLY",
        "BABY KALE",
        "ORIGINAL CHEESECAKE",
        "CARAMEL CHEESECAKE",
        "STRAWBERRY CRUMBLE CHEESECAKE",
        "NEW YORK STYLE CHEESECAKE",
    ]:
        rows = pmap_l[pmap_l["d"].str.contains(query.lower(), na=False)].head(3)
        if len(rows):
            bad_examples.append(
                {
                    "query": query,
                    "rows": rows[
                        [
                            "description",
                            "brand_name",
                            "cluster_id",
                            "esha_label",
                            "esha_score",
                        ]
                    ].to_dict(orient="records"),
                }
            )
    out["spot_checks"] = bad_examples

    return out


if __name__ == "__main__":
    import sys

    mode = sys.argv[1] if len(sys.argv) > 1 else "products_only"
    res = run(mode)
    print(json.dumps(res, indent=2, default=str))
