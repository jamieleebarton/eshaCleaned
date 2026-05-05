#!/usr/bin/env python3
"""Sanity tests on the recipe-ingredient taxonomy output.

Not a unit test — a smoke verifier. Prints pass/fail per assertion.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

DEFAULT = Path(__file__).resolve().parents[1] / "output" / "recipe_ingredient_taxonomy_smoke.csv"


def expect(label: str, ok: bool, detail: str = "") -> bool:
    mark = "PASS" if ok else "FAIL"
    print(f"  [{mark}] {label}{('  -- ' + detail) if detail else ''}")
    return ok


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", type=Path, default=DEFAULT)
    args = ap.parse_args()

    df = pd.read_csv(args.csv)
    print(f"loaded {len(df):,} rows from {args.csv}")
    print()

    # ---- coverage / shape ----
    print("== Shape ==")
    fails = 0
    fails += not expect("has rows", len(df) > 0)
    fails += not expect("required cols present",
                        all(c in df.columns for c in
                            ["item", "esha_code", "esha_description", "similarity"]))
    fails += not expect("no null esha assignments",
                        df["esha_code"].notna().all())

    print()
    print("== Similarity distribution ==")
    s = df["similarity"]
    print(f"  count={len(s)}  mean={s.mean():.3f}  median={s.median():.3f}  "
          f"p10={s.quantile(0.10):.3f}  p90={s.quantile(0.90):.3f}")
    fails += not expect("median similarity ≥ 0.50", s.median() >= 0.50,
                        f"median={s.median():.3f}")
    fails += not expect("at least 60% of items have sim ≥ 0.50",
                        (s >= 0.50).mean() >= 0.60,
                        f"share={ (s >= 0.50).mean():.2%}")

    print()
    print("== Spot checks (known ingredient -> reasonable ESHA description) ==")
    probes = {
        "blueberries":     ["blueberr"],
        "granulated sugar":["sugar"],
        "saffron threads": ["saffron"],
        "vanilla yogurt":  ["yogurt"],
        "boneless skinless chicken breasts": ["chicken"],
        "olive oil":       ["olive"],
        "all-purpose flour":["flour"],
        "garlic":          ["garlic"],
        "soy sauce":       ["soy"],
        "lemon juice":     ["lemon"],
    }
    for item, must_contain_any in probes.items():
        hit = df[df["item"] == item]
        if hit.empty:
            print(f"  [SKIP] '{item}' not in sample")
            continue
        desc = str(hit.iloc[0]["esha_description"]).lower()
        sim = float(hit.iloc[0]["similarity"])
        ok = any(tok in desc for tok in must_contain_any)
        fails += not expect(f"'{item}' -> '{desc[:60]}' (sim={sim:.2f})",
                            ok, f"need one of {must_contain_any}")

    print()
    print("== Cluster summary ==")
    if "cluster_id" in df.columns and df["cluster_id"].astype(str).str.len().gt(0).any():
        sizes = df.groupby("cluster_id").size()
        print(f"  n_clusters={len(sizes)}  median_size={int(sizes.median())}  "
              f"max_size={int(sizes.max())}  singleton_clusters={int((sizes==1).sum())}")
        # show 5 random clusters with their dominant home + 4 sample members
        sample = sizes.sample(min(5, len(sizes)), random_state=7).index.tolist()
        for cid in sample:
            sub = df[df["cluster_id"] == cid]
            dom = sub.iloc[0].get("cluster_dominant_esha_description", "")
            members = " | ".join(sub["item"].head(4).tolist())
            print(f"  cluster {cid} (n={len(sub)}) dom='{dom}' :: {members}")

    print()
    print(f"== Result: {fails} failures ==")
    return 0 if fails == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
