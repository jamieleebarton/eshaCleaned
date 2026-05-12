"""Review queue generator: per-row quality score so you can scroll and spot-check.

For each row in v4, computes a composite quality score using:
  - Token overlap between product description and ESHA description
    (weighted by entropy: low-entropy tokens count more)
  - Primary food token agreement (+3 if same, -5 if different domain food, 0 if either missing)
  - Family agreement bonus (+1 if both have a known primary food)

Outputs:
  graph/review/review_queue.csv      — every row, sorted ASCENDING by quality
                                       (worst rows first → easy to scroll & inspect)
  graph/review/low_quality.csv       — quality_score < 1.0 (the priority review list)
  graph/review/regressions.csv       — rows where v4 quality < an earlier version
                                       (only meaningful if you have a prior CSV to diff)

Usage:
  .venv/bin/python graph/queries/review_queue.py
  # Then open graph/review/review_queue.csv — top rows are most suspicious.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
V_LATEST = ROOT / "implementation" / "output" / "product_to_best_esha_full_map.v4.csv"
V_PRIOR  = ROOT / "implementation" / "output" / "product_to_best_esha_full_map.csv"   # fresh matcher (no graph healing)
TOKEN_ENTROPY_CSV = ROOT / "data" / "token_entropy.csv"
OUT_DIR = ROOT / "graph" / "review"
OUT_QUEUE = OUT_DIR / "review_queue.csv"
OUT_LOW = OUT_DIR / "low_quality.csv"
OUT_REGRESSIONS = OUT_DIR / "regressions.csv"

sys.path.insert(0, str(ROOT / "implementation"))
from match_esha_to_products import (  # noqa: E402
    FRUITS, VEGETABLES, MEATS, POULTRY, SEAFOOD, LEGUMES, NUTS_SEEDS,
    GRAINS, DESSERT_HEADS, tokens_for,
)

DOMAIN_ORDER: list[tuple[str, set[str]]] = [
    ("DESSERT", DESSERT_HEADS),
    ("SEAFOOD", SEAFOOD),
    ("POULTRY", POULTRY),
    ("MEAT", MEATS),
    ("LEGUME", LEGUMES),
    ("NUT_SEED", NUTS_SEEDS),
    ("VEGETABLE", VEGETABLES),
    ("FRUIT", FRUITS),
    ("GRAIN", GRAINS),
]


def primary_food(tokens: list[str]) -> tuple[str | None, str | None]:
    if not tokens:
        return None, None
    for domain, members in DOMAIN_ORDER:
        for tok in tokens:
            if tok in members:
                return tok, domain
    return None, None


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"loading {V_LATEST.name}", flush=True)
    df = pd.read_csv(V_LATEST, dtype=str, keep_default_na=False, low_memory=False)
    print(f"  rows: {len(df):,}", flush=True)

    if TOKEN_ENTROPY_CSV.exists():
        ent = pd.read_csv(TOKEN_ENTROPY_CSV)
        max_e = max(float(ent["entropy"].max() or 1.0), 1e-6)
        token_weight = {row.token: 1.0 - (float(row.entropy or 0.0) / max_e) for row in ent.itertuples()}
    else:
        token_weight = {}

    print("computing quality score per row", flush=True)
    df["_p_tokens"] = df["product_description"].apply(tokens_for)
    df["_e_tokens"] = df["best_esha_description"].apply(tokens_for)
    df[["_p_primary", "_p_domain"]] = df["_p_tokens"].apply(lambda t: pd.Series(primary_food(t)))
    df[["_e_primary", "_e_domain"]] = df["_e_tokens"].apply(lambda t: pd.Series(primary_food(t)))

    def score_row(r) -> float:
        ptoks, etoks = set(r["_p_tokens"]), set(r["_e_tokens"])
        if not r["best_esha_code"]:
            return -10.0  # unassigned = worst
        if not ptoks or not etoks:
            return 0.0
        shared = ptoks & etoks
        if not shared:
            return -2.0
        s = sum(token_weight.get(t, 0.5) for t in shared)
        pp, ep = r["_p_primary"], r["_e_primary"]
        pd_, ed_ = r["_p_domain"], r["_e_domain"]
        if pp and ep:
            if pp == ep:
                s += 3.0
            elif pd_ == ed_:
                s -= 3.0   # same domain, different food (apricot vs apple)
            else:
                s -= 5.0   # different domain entirely (chocolate vs apple)
        return round(float(s), 4)

    print("  scoring (this takes ~30s)...", flush=True)
    df["quality_score"] = df.apply(score_row, axis=1)
    df["primary_food_agree"] = (df["_p_primary"] == df["_e_primary"]) & df["_p_primary"].notna() & df["_e_primary"].notna()
    df["primary_food_disagree"] = (df["_p_primary"] != df["_e_primary"]) & df["_p_primary"].notna() & df["_e_primary"].notna()

    out_cols = [
        "gtin_upc", "product_description", "branded_food_category", "brand_name",
        "best_esha_code", "best_esha_description", "best_esha_family",
        "score", "assignment_source",
        "quality_score", "primary_food_agree", "primary_food_disagree",
        "_p_primary", "_e_primary",
    ]
    df_out = df[out_cols].copy().rename(columns={"_p_primary": "product_primary_food", "_e_primary": "esha_primary_food"})

    df_out_sorted = df_out.sort_values("quality_score", ascending=True)
    df_out_sorted.to_csv(OUT_QUEUE, index=False)
    print(f"  wrote {OUT_QUEUE.relative_to(ROOT)} ({len(df_out_sorted):,} rows, sorted worst-first)", flush=True)

    low = df_out_sorted[df_out_sorted["quality_score"] < 1.0]
    low.to_csv(OUT_LOW, index=False)
    print(f"  wrote {OUT_LOW.relative_to(ROOT)} ({len(low):,} rows below quality 1.0)", flush=True)

    print("  bucketed quality distribution:", flush=True)
    buckets = pd.cut(
        df_out["quality_score"],
        bins=[-100, -5, -2, 0, 1, 3, 6, 100],
        labels=["unassigned (-10)", "wrong primary (-5)", "no overlap (-2)", "weak (0-1)", "ok (1-3)", "good (3-6)", "great (6+)"],
    )
    print(buckets.value_counts().sort_index().to_string(), flush=True)

    if V_PRIOR.exists():
        print(f"\nloading {V_PRIOR.name} for regression check", flush=True)
        prior = pd.read_csv(V_PRIOR, dtype=str, keep_default_na=False, low_memory=False)
        prior["_p_tokens"] = prior["product_description"].apply(tokens_for)
        prior["_e_tokens"] = prior["best_esha_description"].apply(tokens_for)
        prior[["_p_primary", "_p_domain"]] = prior["_p_tokens"].apply(lambda t: pd.Series(primary_food(t)))
        prior[["_e_primary", "_e_domain"]] = prior["_e_tokens"].apply(lambda t: pd.Series(primary_food(t)))
        prior["quality_score"] = prior.apply(score_row, axis=1)

        diff = df[["gtin_upc", "product_description", "best_esha_code", "best_esha_description", "quality_score"]].rename(
            columns={
                "best_esha_code": "v4_code",
                "best_esha_description": "v4_description",
                "quality_score": "v4_quality",
            }
        ).merge(
            prior[["gtin_upc", "best_esha_code", "best_esha_description", "quality_score"]].rename(
                columns={
                    "best_esha_code": "v_prior_code",
                    "best_esha_description": "v_prior_description",
                    "quality_score": "v_prior_quality",
                }
            ),
            on="gtin_upc", how="inner",
        )
        diff["delta"] = diff["v4_quality"] - diff["v_prior_quality"]
        regressions = diff[diff["delta"] < -1.0].sort_values("delta", ascending=True).head(2000)
        regressions.to_csv(OUT_REGRESSIONS, index=False)
        print(f"  regressions (v4 quality < prior quality by >1.0): {len(diff[diff['delta'] < -1.0]):,}", flush=True)
        print(f"  wrote top 2000 regressions -> {OUT_REGRESSIONS.relative_to(ROOT)}", flush=True)
        print(f"  improvements (v4 > prior by >1.0): {len(diff[diff['delta'] > 1.0]):,}", flush=True)
        print(f"  no change: {len(diff[abs(diff['delta']) <= 1.0]):,}", flush=True)


if __name__ == "__main__":
    main()
