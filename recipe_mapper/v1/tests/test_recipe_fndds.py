#!/usr/bin/env python3
"""Real-eye test: for each known ingredient, print top-5 FNDDS candidates.

You read the output and decide if 'milk' actually returns milk, etc.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

DEFAULT = Path(__file__).resolve().parents[1] / "output" / "recipe_ingredient_fndds.csv"

PROBES = [
    "milk",
    "whole milk",
    "skim milk",
    "heavy cream",
    "sugar",
    "granulated sugar",
    "brown sugar",
    "all-purpose flour",
    "bread flour",
    "olive oil",
    "vegetable oil",
    "butter",
    "unsalted butter",
    "salt",
    "kosher salt",
    "garlic",
    "garlic cloves",
    "onion",
    "yellow onion",
    "chicken breast",
    "boneless skinless chicken breasts",
    "ground beef",
    "blueberries",
    "fresh blueberries",
    "saffron threads",
    "vanilla yogurt",
    "soy sauce",
    "lemon juice",
    "egg",
    "large eggs",
    "parsley",
    "fresh parsley",
    "black pepper",
    "ground cinnamon",
    "honey",
    "maple syrup",
    "tomato",
    "diced tomatoes",
    "white rice",
    "brown rice",
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", type=Path, default=DEFAULT)
    args = ap.parse_args()
    df = pd.read_csv(args.csv)
    df["item_lc"] = df["item"].astype(str).str.lower()
    print(f"loaded {len(df):,} ingredient rows from {args.csv.name}")
    print()
    for q in PROBES:
        hit = df[df["item_lc"] == q.lower()]
        if hit.empty:
            print(f"--- '{q}'  [NOT IN CORPUS]")
            continue
        r = hit.iloc[0]
        print(f"--- '{q}'   recipes={int(r['recipe_count'])}  "
              f"top1={r['fndds_code']} '{r['fndds_description']}'  "
              f"sim={r['similarity']:.3f}  has_weight={r['has_weight']}")
        for cand in str(r["top_k"]).split(" || "):
            print("    ", cand)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
