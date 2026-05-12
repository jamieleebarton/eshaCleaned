#!/usr/bin/env python3
"""Macro sanity gate. Run calculator on 50 random recipes from the resolved
pool. Per-serving macros must stay in physically plausible bounds.

Bounds (per serving, not per recipe):
  50 ≤ kcal     ≤ 1500
  1  ≤ protein  ≤ 100
  0  ≤ fat      ≤ 100
  0  ≤ sodium   ≤ 5000
"""
from __future__ import annotations
import json, random, sqlite3, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "recipe_pricing"))
import calculate_recipe_cost_v7 as calc

OUT = ROOT / "planner" / "data" / "macro_sanity_failures.json"
SAMPLE_SIZE = 50


def main():
    print("loading…", file=sys.stderr)
    unified = calc.load_unified()
    cls = calc.load_classifications()
    bfl, overridden = calc.load_buy_form_lookup()
    excluded_upcs = calc.load_excluded_upcs()
    fndds_macros = calc.load_fndds_macros()
    product_claims = calc.load_product_claims()
    con = sqlite3.connect(str(calc.PRICED_DB))

    rng = random.Random(42)
    candidates = [r for r in cls.keys() if r in unified]
    sample = rng.sample(candidates, SAMPLE_SIZE)

    failures = []
    passes  = 0
    for rid in sample:
        r = calc.calculate(rid, unified, cls, bfl, con, [], excluded_upcs,
                            fndds_macros, product_claims, overridden)
        servings = 4
        try:
            servings = max(1, len(r.lines) // 3) if not r.lines else 4
        except: servings = 4
        kcal_s    = r.total_kcal      / servings
        prot_s    = r.total_protein_g / servings
        fat_s     = r.total_fat_g     / servings
        sod_s     = r.total_sodium_mg / servings
        violations = []
        if not (50 <= kcal_s <= 1500):
            violations.append(f"kcal/serving={kcal_s:.0f}")
        if not (1 <= prot_s <= 100):
            violations.append(f"protein/serving={prot_s:.1f}")
        if not (0 <= fat_s <= 100):
            violations.append(f"fat/serving={fat_s:.1f}")
        if not (0 <= sod_s <= 5000):
            violations.append(f"sodium/serving={sod_s:.0f}")
        if violations:
            failures.append({
                "recipe_id": rid,
                "title": r.recipe_title[:60],
                "kcal": round(r.total_kcal, 0),
                "protein": round(r.total_protein_g, 1),
                "violations": violations,
                "skus": [(ln.canonical_buy_form, ln.sku_name)
                         for ln in r.lines if ln.sku_name],
            })
        else:
            passes += 1

    print(f"\n=== MACRO SANITY: {passes}/{SAMPLE_SIZE} pass, {len(failures)} fail ===")
    for f in failures[:15]:
        print(f"  ✗ rid={f['recipe_id']:<8} {f['title']}")
        print(f"      {f['violations']}")
        for bf, sku in f["skus"][:6]:
            print(f"        {bf:<28} → {sku[:55]}")

    OUT.write_text(json.dumps(failures, indent=2))
    print(f"\n  → failures dumped to {OUT}")
    return 0 if passes >= 40 else 1


if __name__ == "__main__":
    sys.exit(main())
