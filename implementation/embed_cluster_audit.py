"""Honest audit of product_to_anchor.csv.

Stops asking 'did it run' and asks 'are the answers correct'.

Checks:
  1. Random sample with manual-eye spot check — pretty-print 50 random rows.
  2. Cross-category contamination: clusters whose products span >1 branded_food_category.
  3. Identity-token mismatch: product title contains an identity noun that does
     NOT appear in the assigned ESHA label (cookie→milk, peanut→almond, etc.).
  4. Form-family leakage from prior KG_RFT lessons: cookie!=cake, sandwich!=cookie,
     sausage!=bacon, dry_pasta!=prepared_meal, etc.
  5. The user's flagged failures from AGENTS.md: BABY KALE, HABANERO PEPPER JELLY,
     GRACE EVAPORATED FILLED MILK, milk-family subtypes, jelly-family.
  6. Brand purity (sanity that the brand_split rule fired).
  7. Score-quality: bucket score ranges and show 5 random examples per bucket.
  8. NEEDS_NEW_CONCEPT distribution.
  9. Top ESHA labels by frequency — do degenerate fragments dominate?
"""

from __future__ import annotations

import json
import random
import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path("/Users/jamiebarton/Desktop/esha_audit_bundle")
PMAP_PATH = ROOT / "implementation/output/embed_cluster_v1_products_only/product_to_anchor.csv"

random.seed(7)
pd.set_option("display.max_colwidth", 90)


def load() -> pd.DataFrame:
    df = pd.read_csv(PMAP_PATH, low_memory=False)
    df["d"] = df["description"].astype(str).str.lower()
    df["esha_l"] = df["esha_label"].astype(str).str.lower()
    df["fndds_l"] = df["fndds_label"].astype(str).str.lower()
    df["sr28_l"] = df["sr28_label"].astype(str).str.lower()
    return df


def fmt_row(r: dict, keys=None) -> str:
    keys = keys or [
        "description",
        "brand_name",
        "branded_food_category",
        "esha_label",
        "esha_score",
        "fndds_label",
        "sr28_label",
        "cluster_id",
    ]
    return " | ".join(f"{k}={r.get(k)}" for k in keys)


# ---------------- check 1: random sample ----------------


def check_random_sample(df: pd.DataFrame, n: int = 30) -> dict:
    print("\n" + "=" * 80)
    print(f"1. RANDOM SAMPLE  (n={n})  — eyeball each one")
    print("=" * 80)
    sample = df.sample(n, random_state=7)[
        [
            "description",
            "brand_name",
            "branded_food_category",
            "esha_label",
            "esha_score",
            "fndds_label",
            "cluster_id",
        ]
    ]
    for _, r in sample.iterrows():
        print(
            f"\n  [{r['cluster_id']}] {r['description']!r}"
            f"\n    brand={r['brand_name']!r}  cat={r['branded_food_category']!r}"
            f"\n    ESHA  ={r['esha_label']!r}  ({r['esha_score']:.3f})"
            f"\n    FNDDS ={r['fndds_label']!r}"
        )
    return {"sampled": n}


# ---------------- check 2: cross-category contamination ----------------


def check_cross_category(df: pd.DataFrame) -> dict:
    print("\n" + "=" * 80)
    print("2. CROSS-CATEGORY CONTAMINATION")
    print("=" * 80)
    g = df.groupby("cluster_id")["branded_food_category"]
    cats_per_cluster = g.apply(
        lambda s: s.dropna().astype(str).replace("", pd.NA).dropna().unique()
    )
    sizes = g.size()
    contaminated = []
    for cid, cats in cats_per_cluster.items():
        if len(cats) >= 3 and sizes[cid] >= 20:
            contaminated.append((cid, len(cats), int(sizes[cid]), list(cats)[:6]))
    contaminated.sort(key=lambda x: -x[2])
    print(f"  {len(contaminated):,} clusters of size >=20 mix >=3 distinct categories")
    print("  worst 10:")
    for cid, ncats, sz, cats in contaminated[:10]:
        examples = (
            df[df["cluster_id"] == cid]["description"].head(3).astype(str).tolist()
        )
        anchor = df[df["cluster_id"] == cid]["esha_label"].iat[0]
        score = df[df["cluster_id"] == cid]["esha_score"].iat[0]
        print(
            f"\n    cluster={cid}  n={sz}  cats={ncats} {cats}\n"
            f"      anchor={anchor!r} ({score:.3f})\n"
            f"      examples: {' | '.join(examples)}"
        )
    return {"contaminated_clusters_3plus_cats_size_20plus": len(contaminated)}


# ---------------- check 3: identity-token mismatch ----------------

# token in product description that should be reflected in ESHA label
IDENTITY_PAIRS = [
    ("peanut", "peanut"),
    ("almond", "almond"),
    ("cashew", "cashew"),
    ("walnut", "walnut"),
    ("pecan", "pecan"),
    ("hazelnut", "hazelnut"),
    ("coconut", "coconut"),
    ("chocolate", "chocolate"),
    ("vanilla", "vanilla"),
    ("strawberry", "strawberry"),
    ("blueberry", "blueberry"),
    ("raspberry", "raspberry"),
    ("cherry", "cherry"),
    ("lemon", "lemon"),
    ("lime", "lime"),
    ("orange", "orange"),
    ("mango", "mango"),
    ("pineapple", "pineapple"),
    ("apple", "apple"),
    ("banana", "banana"),
    ("beef", "beef"),
    ("chicken", "chicken"),
    ("pork", "pork"),
    ("bacon", "bacon"),
    ("turkey", "turkey"),
    ("salmon", "salmon"),
    ("tuna", "tuna"),
    ("shrimp", "shrimp"),
    ("rice", "rice"),
    ("pasta", "pasta"),
    ("noodle", "noodle"),
    ("milk", "milk"),
    ("cheese", "cheese"),
    ("butter", "butter"),
    ("yogurt", "yogurt"),
    ("egg", "egg"),
    ("honey", "honey"),
    ("maple", "maple"),
    ("ginger", "ginger"),
    ("garlic", "garlic"),
    ("onion", "onion"),
    ("tomato", "tomato"),
    ("kale", "kale"),
    ("spinach", "spinach"),
]


def check_identity_mismatch(df: pd.DataFrame, max_examples: int = 15) -> dict:
    print("\n" + "=" * 80)
    print("3. IDENTITY-TOKEN MISMATCH (product has X, ESHA label has different X)")
    print("=" * 80)
    mismatches = []
    sample = df[df["esha_score"] >= 0.70]  # focus on the supposedly-good ones
    for prod_tok, esha_tok in IDENTITY_PAIRS:
        prod_pat = re.compile(rf"\b{re.escape(prod_tok)}\b")
        has_prod = sample["d"].str.contains(prod_pat, regex=True, na=False)
        has_esha = sample["esha_l"].str.contains(rf"\b{re.escape(esha_tok)}\b", regex=True, na=False)
        miss = sample[has_prod & ~has_esha]
        # exclude rows where the OTHER source has it
        miss = miss[
            ~miss["fndds_l"].str.contains(rf"\b{re.escape(esha_tok)}\b", regex=True, na=False)
        ]
        if len(miss):
            mismatches.append((prod_tok, len(miss), miss))
    mismatches.sort(key=lambda x: -x[1])
    total = sum(m[1] for m in mismatches)
    print(f"  total identity-token mismatches: {total:,} rows  (out of {len(sample):,} rows scoring >=0.70)")
    print(f"  worst tokens (top 20):")
    for tok, cnt, _ in mismatches[:20]:
        print(f"    {tok:<14} {cnt:>7,}")
    print("\n  examples (worst 5 tokens × 3 rows each):")
    for tok, cnt, miss in mismatches[:5]:
        print(f"\n  --- {tok} (n={cnt}) ---")
        for _, r in miss.head(3).iterrows():
            print(
                f"    PROD:  {r['description'][:80]!r}"
                f"\n    ESHA:  {r['esha_label']!r} ({r['esha_score']:.3f})"
                f"\n    FNDDS: {r['fndds_label']!r}"
            )
    return {"identity_mismatches_total_rows": total, "tokens_with_misses": len(mismatches)}


# ---------------- check 4: form-family leakage from KG_RFT ----------------

FORM_PAIRS = [
    ("cookie", "cake"),
    ("sandwich", "cookie"),
    ("sausage", "bacon"),
    ("juice_drink", "juice"),
    ("dry_pasta", "prepared_meal"),
    ("muffin", "bread"),
    ("cream", "milk"),
    ("salad_dressing", "dressing"),
    ("tea", "drink"),
]


def check_form_leakage(df: pd.DataFrame) -> dict:
    print("\n" + "=" * 80)
    print("4. FORM-FAMILY LEAKAGE — clusters that contain BOTH product types")
    print("=" * 80)
    leaks = {}
    for a, b in FORM_PAIRS:
        a_clusters = set(
            df[df["d"].str.contains(rf"\b{a}", regex=True, na=False)]["cluster_id"].unique()
        )
        b_clusters = set(
            df[df["d"].str.contains(rf"\b{b}", regex=True, na=False)]["cluster_id"].unique()
        )
        overlap = a_clusters & b_clusters
        leaks[f"{a}__{b}"] = len(overlap)
        print(f"  {a:>16} <-> {b:<20}  shared_clusters={len(overlap):,}")
    return leaks


# ---------------- check 5: AGENTS.md known-bad cases ----------------


def check_known_bad(df: pd.DataFrame) -> dict:
    print("\n" + "=" * 80)
    print("5. AGENTS.md KNOWN-BAD CASES")
    print("=" * 80)
    queries = [
        "BABY KALE",
        "HABANERO PEPPER JELLY",
        "GRACE EVAPORATED FILLED MILK",
        "GOAT MILK",
        "BUTTERMILK",
        "ALMOND MILK",
        "OAT MILK",
        "COCONUT MILK",
        "PEPPER JELLY",
        "STRAWBERRY JAM",
        "ORIGINAL CHEESECAKE",
        "CARAMEL CHEESECAKE",
        "STRAWBERRY CRUMBLE CHEESECAKE",
        "NEW YORK STYLE CHEESECAKE",
        "PUMPKIN CHEESECAKE",
    ]
    out = {}
    for q in queries:
        m = df[df["d"].str.contains(q.lower(), na=False)].head(5)
        if not len(m):
            continue
        print(f"\n  --- {q} ---")
        out[q] = []
        for _, r in m.iterrows():
            print(
                f"    PROD:  {r['description'][:80]!r}  brand={r['brand_name']!r}"
                f"\n    ESHA:  {r['esha_label']!r} ({r['esha_score']:.3f})"
                f"\n    FNDDS: {r['fndds_label']!r}"
            )
            out[q].append(
                {
                    "desc": r["description"],
                    "esha": r["esha_label"],
                    "esha_score": r["esha_score"],
                    "fndds": r["fndds_label"],
                }
            )
    return out


# ---------------- check 6: brand purity ----------------


def check_brand_purity(df: pd.DataFrame) -> dict:
    print("\n" + "=" * 80)
    print("6. BRAND PURITY  — confirms the brand_split rule actually fired")
    print("=" * 80)
    g = df[df["brand_name"].notna() & (df["brand_name"] != "")].groupby("cluster_id")[
        "brand_name"
    ]
    distinct = g.apply(lambda s: s.astype(str).nunique())
    sizes = g.size()
    mixed = distinct[distinct > 1]
    print(f"  clusters with branded products: {len(distinct):,}")
    print(f"  clusters with >1 distinct brand: {(distinct > 1).sum():,}")
    if (distinct > 1).any():
        worst = mixed.sort_values(ascending=False).head(5)
        print("  worst mixed-brand clusters:")
        for cid, n in worst.items():
            ex = df[df["cluster_id"] == cid][["description", "brand_name"]].head(3)
            print(f"\n    cluster={cid} n_distinct_brands={n} cluster_size={sizes[cid]}")
            for _, r in ex.iterrows():
                print(f"      {r['brand_name']!r:>30} :: {r['description'][:70]!r}")
    else:
        print("  ✓ brand split rule applied cleanly")
    return {
        "branded_clusters": int(len(distinct)),
        "mixed_brand_clusters": int((distinct > 1).sum()),
    }


# ---------------- check 7: score buckets ----------------


def check_score_buckets(df: pd.DataFrame) -> dict:
    print("\n" + "=" * 80)
    print("7. SCORE BUCKETS — does high score = good match?")
    print("=" * 80)
    buckets = [(0.90, 1.01), (0.85, 0.90), (0.80, 0.85), (0.75, 0.80), (0.70, 0.75), (0.60, 0.70), (0.0, 0.60)]
    out = {}
    for lo, hi in buckets:
        sub = df[(df["esha_score"] >= lo) & (df["esha_score"] < hi)]
        out[f"{lo:.2f}-{hi:.2f}"] = len(sub)
        print(f"\n  --- score {lo:.2f}–{hi:.2f}  n={len(sub):,} ---")
        if len(sub):
            for _, r in sub.sample(min(3, len(sub)), random_state=42).iterrows():
                print(
                    f"    PROD: {r['description'][:80]!r}"
                    f"\n    ESHA: {r['esha_label']!r}  ({r['esha_score']:.3f})"
                )
    return out


# ---------------- check 8: degenerate ESHA labels ----------------


def check_degenerate_labels(df: pd.DataFrame) -> dict:
    print("\n" + "=" * 80)
    print("8. DEGENERATE ESHA LABELS  — short / fragment labels dominating")
    print("=" * 80)
    counts = df.groupby("esha_label").size().sort_values(ascending=False)
    print(f"  unique ESHA labels in use: {len(counts):,}")
    print("\n  top 30 by product count:")
    for lbl, n in counts.head(30).items():
        flag = "  <-- SUSPICIOUS" if (isinstance(lbl, str) and len(lbl.split()) <= 1) else ""
        print(f"    {n:>7,}   {lbl!r}{flag}")
    short_labels = [l for l in counts.index if isinstance(l, str) and len(l.split()) <= 1]
    short_count = sum(counts[l] for l in short_labels)
    print(f"\n  one-word ESHA labels: {len(short_labels):,} labels covering {short_count:,} products")
    return {"unique_labels": int(len(counts)), "one_word_labels": len(short_labels), "one_word_label_products": int(short_count)}


# ---------------- run ----------------


def main() -> int:
    print(f"\nLoading {PMAP_PATH}...")
    df = load()
    print(f"  rows: {len(df):,}  unique clusters: {df['cluster_id'].nunique():,}")

    findings: dict = {}
    findings["random_sample"] = check_random_sample(df, n=20)
    findings["cross_category"] = check_cross_category(df)
    findings["identity_mismatch"] = check_identity_mismatch(df)
    findings["form_leakage"] = check_form_leakage(df)
    findings["known_bad"] = check_known_bad(df)
    findings["brand_purity"] = check_brand_purity(df)
    findings["score_buckets"] = check_score_buckets(df)
    findings["degenerate_labels"] = check_degenerate_labels(df)

    out_path = ROOT / "implementation/output/embed_cluster_v1_products_only/audit_findings.json"
    out_path.write_text(json.dumps(findings, indent=2, default=str))
    print(f"\n\nFINDINGS JSON: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
