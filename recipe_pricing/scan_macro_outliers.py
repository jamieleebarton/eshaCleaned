#!/usr/bin/env python3
"""Scan a sample of recipes through calculate_recipe_cost_v7. Flag any with
macros so high they suggest a bridge error in the SKU pick (e.g., bacon-kit
for cinnamon, or rotisserie-chicken for raw chicken with 50x macros).

Outputs:
  recipe_pricing/macro_outliers.csv  — recipe-level outliers + suspect line
  recipe_pricing/macro_outlier_skus.csv — SKUs that frequently get picked for
                                          incompatible buy_forms
"""
from __future__ import annotations
import csv, json, random, sqlite3, sys, time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "recipe_pricing"))
import calculate_recipe_cost_v7 as calc

OUT = ROOT / "recipe_pricing" / "macro_outliers.csv"
OUT_SKUS = ROOT / "recipe_pricing" / "macro_outlier_skus.csv"

# Bounds that flag a recipe as suspect (per recipe, not per serving)
KCAL_PER_LINE_HARD = 4000      # any single line > 4000 kcal is sus
PROTEIN_PER_LINE_HARD = 300
SODIUM_PER_LINE_HARD = 50000   # 50g sodium in one line

SAMPLE_SIZE = 5000


def main():
    print("loading indexes...", file=sys.stderr)
    unified = calc.load_unified()
    cls = calc.load_classifications()
    bfl, overridden = calc.load_buy_form_lookup()
    excluded_upcs = calc.load_excluded_upcs()
    fndds_macros = calc.load_fndds_macros()
    product_claims = calc.load_product_claims()
    con = sqlite3.connect(str(calc.PRICED_DB))

    # Pick recipes that have classifier output AND unified ingredient data
    recipe_ids = [r for r in cls.keys() if r in unified]
    rng = random.Random(42)
    sample = rng.sample(recipe_ids, min(SAMPLE_SIZE, len(recipe_ids)))
    print(f"scanning {len(sample):,} recipes...", file=sys.stderr)

    outliers = []
    bad_sku_for_buyform: Counter = Counter()
    t0 = time.time()
    for i, rid in enumerate(sample, 1):
        try:
            r = calc.calculate(rid, unified, cls, bfl, con, [],
                                excluded_upcs, fndds_macros, product_claims, overridden)
        except Exception:
            continue
        for ln in r.lines:
            if ln.line_kcal      > KCAL_PER_LINE_HARD or \
               ln.line_protein_g > PROTEIN_PER_LINE_HARD or \
               ln.line_sodium_mg > SODIUM_PER_LINE_HARD:
                outliers.append({
                    "recipe_id": rid,
                    "title": r.recipe_title[:60],
                    "line_index": ln.line_index,
                    "buy_form": ln.canonical_buy_form,
                    "canonical_path": ln.canonical_path,
                    "grams": round(ln.grams, 1),
                    "sku_name": ln.sku_name,
                    "sku_upc": ln.sku_upc,
                    "kcal": round(ln.line_kcal, 0),
                    "protein_g": round(ln.line_protein_g, 1),
                    "sodium_mg": round(ln.line_sodium_mg, 0),
                })
                bad_sku_for_buyform[(ln.canonical_buy_form, ln.sku_name)] += 1
        if i % 500 == 0:
            print(f"  {i}/{len(sample)}  ({time.time()-t0:.0f}s)", file=sys.stderr)

    print(f"\nfound {len(outliers):,} outlier lines in {len(sample):,} recipes "
          f"({len(set(o['recipe_id'] for o in outliers)):,} affected recipes)",
          file=sys.stderr)

    with OUT.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["recipe_id","title","line_index","buy_form",
            "canonical_path","grams","sku_name","sku_upc","kcal","protein_g","sodium_mg"])
        w.writeheader()
        outliers.sort(key=lambda r: -r["kcal"])
        w.writerows(outliers)

    # Top offending (buy_form, sku) combos
    with OUT_SKUS.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["buy_form","sku_name","occurrences"])
        for (bf, sku), n in bad_sku_for_buyform.most_common(100):
            w.writerow([bf, sku, n])

    print(f"\n=== Top 20 outlier (buy_form → SKU) pairs ===", file=sys.stderr)
    for (bf, sku), n in bad_sku_for_buyform.most_common(20):
        print(f"  {n:>4}  {bf[:30]:<30} → {sku[:60]}", file=sys.stderr)

    print(f"\n→ {OUT}", file=sys.stderr)
    print(f"→ {OUT_SKUS}", file=sys.stderr)


if __name__ == "__main__":
    main()
