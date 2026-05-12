"""Review queue v2 — split by what you can actually act on.

Three files instead of one giant confusing CSV. All sorted worst-first.

  graph/review/unassigned.csv          — products with no ESHA at all
                                         (need: better matcher rules or manual)
  graph/review/review_queue.csv        — assigned rows ranked by quality
                                         WITH old vs new ESHA so you can see
                                         what each pass changed
  graph/review/low_quality.csv         — review_queue filtered to quality < 1.0

The review_queue includes:
  - product info
  - CURRENT ESHA (v4) + family + quality_score
  - ORIGINAL ESHA (fresh matcher, no graph healing) + quality_score
  - delta (positive = healing improved it, negative = healing made it worse)
  - signals: product primary food vs ESHA primary food
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
V_LATEST = ROOT / "implementation" / "output" / "product_to_best_esha_full_map.v4.csv"
V_PRIOR  = ROOT / "implementation" / "output" / "product_to_best_esha_full_map.csv"
TOKEN_ENTROPY_CSV = ROOT / "data" / "token_entropy.csv"
OUT_DIR = ROOT / "graph" / "review"
OUT_QUEUE = OUT_DIR / "review_queue.csv"
OUT_LOW = OUT_DIR / "low_quality.csv"
OUT_UNASSIGNED = OUT_DIR / "unassigned.csv"

sys.path.insert(0, str(ROOT / "implementation"))
from match_esha_to_products import (  # noqa: E402
    FRUITS, VEGETABLES, MEATS, POULTRY, SEAFOOD, LEGUMES, NUTS_SEEDS,
    GRAINS, DESSERT_HEADS, tokens_for,
)

# Exclude generic meal/snack tokens — they aren't food types, they're packaging.
EXCLUDE_FROM_PRIMARY = {"snack", "dessert", "meal", "dish", "bar", "mix"}
DESSERT_FOODS = DESSERT_HEADS - EXCLUDE_FROM_PRIMARY

DOMAIN_ORDER: list[tuple[str, set[str]]] = [
    ("DESSERT", DESSERT_FOODS),
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
    v4 = pd.read_csv(V_LATEST, dtype=str, keep_default_na=False, low_memory=False)
    print(f"  rows: {len(v4):,}", flush=True)

    print(f"loading {V_PRIOR.name} (fresh matcher, no healing) for before/after diff", flush=True)
    prior = pd.read_csv(V_PRIOR, dtype=str, keep_default_na=False, low_memory=False)
    prior = prior[["gtin_upc", "best_esha_code", "best_esha_description", "best_esha_family", "score", "assignment_source"]].rename(
        columns={
            "best_esha_code": "original_esha_code",
            "best_esha_description": "original_esha_description",
            "best_esha_family": "original_esha_family",
            "score": "original_score",
            "assignment_source": "original_assignment_source",
        }
    )

    df = v4.merge(prior, on="gtin_upc", how="left")

    if TOKEN_ENTROPY_CSV.exists():
        ent = pd.read_csv(TOKEN_ENTROPY_CSV)
        max_e = max(float(ent["entropy"].max() or 1.0), 1e-6)
        token_weight = {row.token: 1.0 - (float(row.entropy or 0.0) / max_e) for row in ent.itertuples()}
    else:
        token_weight = {}

    print("computing per-row quality scores", flush=True)
    df["_p_tokens"] = df["product_description"].apply(tokens_for)
    df["_e_tokens"] = df["best_esha_description"].apply(tokens_for)
    df["_orig_tokens"] = df["original_esha_description"].apply(tokens_for)
    df[["_p_primary", "_p_domain"]] = df["_p_tokens"].apply(lambda t: pd.Series(primary_food(t)))
    df[["_e_primary", "_e_domain"]] = df["_e_tokens"].apply(lambda t: pd.Series(primary_food(t)))
    df[["_orig_primary", "_orig_domain"]] = df["_orig_tokens"].apply(lambda t: pd.Series(primary_food(t)))

    def quality(p_toks: list[str], e_toks: list[str], pp: str | None, ep: str | None, pd_: str | None, ed_: str | None, esha_code: str) -> float:
        if not esha_code:
            return -10.0
        ptoks, etoks = set(p_toks), set(e_toks)
        if not ptoks or not etoks:
            return 0.0
        shared = ptoks & etoks
        if not shared:
            return -2.0
        s = sum(token_weight.get(t, 0.5) for t in shared)
        if pp and ep:
            if pp == ep:
                s += 3.0
            elif pd_ == ed_:
                s -= 3.0
            else:
                s -= 5.0
        return round(float(s), 4)

    df["quality_score"] = df.apply(
        lambda r: quality(r["_p_tokens"], r["_e_tokens"], r["_p_primary"], r["_e_primary"], r["_p_domain"], r["_e_domain"], r["best_esha_code"]),
        axis=1,
    )
    df["original_quality"] = df.apply(
        lambda r: quality(r["_p_tokens"], r["_orig_tokens"], r["_p_primary"], r["_orig_primary"], r["_p_domain"], r["_orig_domain"], r["original_esha_code"]),
        axis=1,
    )
    df["quality_delta"] = df["quality_score"] - df["original_quality"]

    # Split: unassigned vs assigned
    has_esha = df["best_esha_code"].astype(str).str.strip() != ""
    unassigned = df[~has_esha].copy()
    assigned = df[has_esha].copy()

    # ---- unassigned.csv ----
    un_cols = ["gtin_upc", "product_description", "branded_food_category", "brand_name", "brand_owner",
               "original_esha_code", "original_esha_description", "original_assignment_source",
               "_p_primary"]
    unassigned_out = unassigned[un_cols].rename(columns={"_p_primary": "product_primary_food"})
    unassigned_out.to_csv(OUT_UNASSIGNED, index=False)
    print(f"  wrote {OUT_UNASSIGNED.relative_to(ROOT)}: {len(unassigned_out):,} unassigned products", flush=True)

    # ---- review_queue.csv ----
    queue_cols = [
        "gtin_upc", "product_description", "branded_food_category", "brand_name",
        # current (v4)
        "best_esha_code", "best_esha_description", "best_esha_family", "assignment_source",
        # quality
        "quality_score",
        # original (fresh matcher)
        "original_esha_code", "original_esha_description", "original_esha_family", "original_assignment_source",
        "original_quality",
        # delta + signals
        "quality_delta",
        "_p_primary", "_e_primary",
    ]
    queue_out = assigned[queue_cols].rename(columns={"_p_primary": "product_primary_food", "_e_primary": "esha_primary_food"})
    queue_sorted = queue_out.sort_values("quality_score", ascending=True)
    queue_sorted.to_csv(OUT_QUEUE, index=False)
    print(f"  wrote {OUT_QUEUE.relative_to(ROOT)}: {len(queue_sorted):,} assigned rows (worst-first)", flush=True)

    low = queue_sorted[queue_sorted["quality_score"] < 1.0]
    low.to_csv(OUT_LOW, index=False)
    print(f"  wrote {OUT_LOW.relative_to(ROOT)}: {len(low):,} rows below quality 1.0", flush=True)

    print("\nquality distribution (assigned rows only):", flush=True)
    bins = [-100, -5, -2, 0, 1, 3, 6, 100]
    labels = ["very_bad (<-5)", "wrong_primary (-5 to -2)", "no_overlap (-2 to 0)", "weak (0-1)", "ok (1-3)", "good (3-6)", "great (6+)"]
    buckets = pd.cut(assigned["quality_score"], bins=bins, labels=labels)
    print(buckets.value_counts().sort_index().to_string(), flush=True)

    print("\nbiggest improvements (top 10):", flush=True)
    top_imp = assigned.sort_values("quality_delta", ascending=False).head(10)
    for _, r in top_imp.iterrows():
        print(f"  +{r['quality_delta']:.2f}  {str(r['product_description'])[:45]:<45}  was {str(r['original_esha_description'])[:30]:<30}  now {str(r['best_esha_description'])[:30]}", flush=True)

    print("\nbiggest regressions (top 10):", flush=True)
    top_reg = assigned.sort_values("quality_delta", ascending=True).head(10)
    for _, r in top_reg.iterrows():
        print(f"  {r['quality_delta']:.2f}   {str(r['product_description'])[:45]:<45}  was {str(r['original_esha_description'])[:30]:<30}  now {str(r['best_esha_description'])[:30]}", flush=True)


if __name__ == "__main__":
    main()
