#!/usr/bin/env python3
"""Audit concept_resolution.json against the wrong-class pick patterns
surfaced in the 2026-05-11 recipe-price audit.

Walks every recipe concept_key whose resolved priced_key targets a SKU
matching a banned name fragment for that concept family. Emits a CSV
report so the regression is visible without re-running the planner.

Usage:
  python3 recipe_pricing/audit_concept_resolution_misroutes.py
"""
from __future__ import annotations
import csv
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CR = ROOT / "planner" / "data" / "concept_resolution.json"
CI = ROOT / "planner" / "data" / "concept_index.json"
RCG = ROOT / "planner" / "data" / "recipe_concept_grams.json"
OUT = ROOT / "recipe_pricing" / "concept_resolution_misroute_audit.csv"

# Each banned pair: (concept_path_fragment, banned_sku_or_path_fragment).
# Substring matching, case-insensitive. If ANY package in the resolved
# priced concept's pool matches the banned fragment, the resolution is a
# misroute candidate.
BANNED_PAIRS = [
    ("Produce > Vegetables > Avocado",          "Grape Leaves"),
    ("Produce > Vegetables > Baby Carrots",     "Peas"),
    ("Dairy > Cheese > Cheddar",                "Snack Stick"),
    ("Dairy > Cheese > Cheddar",                "String Cheese"),
    ("Pantry > Oil > Vegetable Oil",            "Vegetable Oil Stick"),
    ("Pantry > Oil > Vegetable Oil",            "Margarine"),
    ("Pantry > Sweeteners > Sugar > Brown",     "Agave"),
    ("Pantry > Spices & Seasonings > Oregano",  "Bay Leaves"),
    ("Pantry > Spices & Seasonings > Cumin",    "Bay Leaves"),
    ("Dairy > Cream",                           "Finishing Sugar"),
    ("Meat & Seafood > Bacon",                  "Veggie"),
    ("Meat & Seafood > Bacon",                  "MorningStar"),
    ("Meat & Seafood > Bacon",                  "Meatless"),
    ("Produce > Fruit > Limes",                 "Citrus Splash"),
    ("Frozen > Vegetables > Pierogies",         "Mashed Potatoes"),
    ("Pantry > Sauces & Salsas > Hot Pepper",   "Hollandaise"),
]


def main() -> int:
    cr = json.loads(CR.read_text())
    ci = json.loads(CI.read_text())
    rcg = json.loads(RCG.read_text())

    recipe_freq: Counter = Counter()
    for rid, d in rcg["concept_grams"].items():
        for ck in d:
            recipe_freq[ck] += 1

    violations: list[dict] = []
    by_pair: Counter = Counter()

    for rk, res in cr.items():
        pk = res.get("priced_key")
        if not pk:
            continue
        cp_recipe = rk.split("|", 1)[0]
        priced = ci.get(pk)
        if not priced:
            continue
        cp_priced = priced.get("canonical_path", "")
        package_names = [p.get("name", "") for p in priced.get("packages", [])]
        joined_sku_blob = " || ".join(package_names).lower()

        for concept_frag, sku_frag in BANNED_PAIRS:
            cf = concept_frag.lower()
            sf = sku_frag.lower()
            if cf not in cp_recipe.lower():
                continue
            # banned fragment may appear in either the priced path itself
            # or in one of the package SKU names
            if sf in cp_priced.lower() or sf in joined_sku_blob:
                violations.append({
                    "recipe_concept_key": rk,
                    "priced_concept_key": pk,
                    "tier": res.get("tier", ""),
                    "recipe_path": cp_recipe,
                    "priced_path": cp_priced,
                    "n_recipes_using": recipe_freq.get(rk, 0),
                    "n_packages_in_pool": len(package_names),
                    "banned_concept_fragment": concept_frag,
                    "banned_sku_fragment": sku_frag,
                    "sample_sku": next(
                        (n for n in package_names if sf in n.lower()), ""
                    )[:120],
                })
                by_pair[(concept_frag, sku_frag)] += 1
                break

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="") as f:
        cols = [
            "recipe_concept_key", "priced_concept_key", "tier",
            "recipe_path", "priced_path", "n_recipes_using",
            "n_packages_in_pool", "banned_concept_fragment",
            "banned_sku_fragment", "sample_sku",
        ]
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for row in violations:
            w.writerow(row)

    print(f"violations: {len(violations)}")
    for pair, n in by_pair.most_common():
        print(f"  {n:4}  '{pair[0]}'  →  '{pair[1]}'")
    print(f"→ {OUT}")
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
