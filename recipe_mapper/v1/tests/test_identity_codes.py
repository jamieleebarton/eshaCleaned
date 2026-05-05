#!/usr/bin/env python3
"""Probe the identity-code matcher output."""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

DEFAULT = Path(__file__).resolve().parents[1] / "output" / "recipe_ingredient_identity_codes.csv"

PROBES = [
    "milk", "whole milk", "skim milk", "heavy cream",
    "sugar", "granulated sugar", "brown sugar",
    "all-purpose flour", "bread flour",
    "olive oil", "vegetable oil",
    "butter", "unsalted butter",
    "salt", "kosher salt",
    "garlic", "garlic cloves",
    "onion", "yellow onion",
    "chicken breast", "boneless skinless chicken breasts",
    "ground beef",
    "blueberries", "fresh blueberries",
    "saffron threads",
    "vanilla yogurt",
    "soy sauce", "lemon juice",
    "egg", "large eggs",
    "parsley", "fresh parsley",
    "black pepper", "ground cinnamon",
    "honey", "maple syrup",
    "tomato", "diced tomatoes",
    "white rice", "brown rice",
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", type=Path, default=DEFAULT)
    args = ap.parse_args()
    df = pd.read_csv(args.csv).fillna("")
    df["item_lc"] = df["item"].astype(str).str.lower()
    print(f"loaded {len(df):,} rows from {args.csv.name}")
    print()
    for q in PROBES:
        hit = df[df["item_lc"] == q.lower()]
        if hit.empty:
            print(f"--- '{q}'  [NOT IN CORPUS]")
            continue
        r = hit.iloc[0]
        print(f"--- '{q}'   recipes={int(r['recipe_count'])}")
        print(f"     code: {r['identity_code']}  rule={r['rule']}  "
              f"sim={r['similarity']:.3f} (base={r['base_similarity']:.3f})")
        print(f"     path: {r['canonical_path']}  >  {r['product_identity_fixed']}")
        if r["modifier"]:
            print(f"     modifier: {r['modifier']}")
        print(f"     fndds={r['modal_fndds_code']} '{r['modal_fndds_desc']}'  "
              f"sr28={r['modal_sr28_code']} '{r['modal_sr28_desc']}'  "
              f"portions={r['has_portions']}")
        for c in str(r["top_k"]).split(" || ")[:5]:
            print("       ", c)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
