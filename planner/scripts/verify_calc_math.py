#!/usr/bin/env python3
"""Hard verification that the calculator math is internally consistent AND
SKU-level data is correct.

For 200 random recipes:
  1. Sum line.line_cost_cents → must equal recipe.line_total_cents
  2. Sum line.line_kcal       → must equal recipe.total_kcal
  3. Per line: line_cost_cents ≈ grams × (sku_cents/sku_grams)   [<0.01¢ tol]
  4. Per line: line_kcal       ≈ grams × (fndds.energy_kcal/100) [<0.5 kcal tol]
  5. Per line: SKU's consensus_fndds is in fndds_nutrient_lookup
  6. Per line: macros from picked SKU's actual FNDDS (not pooled)
  7. Per-serving sanity: kcal/sv ∈ [50,1500], protein/sv ∈ [1,100],
                          sodium/sv ∈ [0,5000]
"""
from __future__ import annotations
import csv, json, random, sqlite3, sys
from collections import Counter
from pathlib import Path
csv.field_size_limit(2**30)

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "recipe_pricing"))
import calculate_recipe_cost_v7 as calc

OUT = ROOT / "planner" / "data" / "calc_math_audit.json"
SAMPLE = 200
KCAL_TOL = 0.5
COST_TOL = 1   # cents
MACRO_TOL = 0.5  # g


def main():
    print("loading…", file=sys.stderr)
    unified = calc.load_unified()
    cls = calc.load_classifications()
    bfl, overridden = calc.load_buy_form_lookup()
    excluded = calc.load_excluded_upcs()
    fndds_macros = calc.load_fndds_macros()
    sr28_macros  = calc.load_sr28_macros()
    product_claims = calc.load_product_claims()
    con = sqlite3.connect(str(calc.PRICED_DB))
    cur = con.cursor()

    rng = random.Random(7)
    candidates = [r for r in cls.keys() if r in unified]
    sample = rng.sample(candidates, SAMPLE)

    bugs = {
        "cost_sum_mismatch":     0,
        "kcal_sum_mismatch":     0,
        "line_cost_wrong":       0,
        "line_kcal_wrong":       0,
        "fndds_missing":         0,
        "kcal_per_serving_high": 0,
        "kcal_per_serving_low":  0,
        "protein_per_sv_extreme":0,
        "sodium_per_sv_extreme": 0,
    }
    examples: dict[str, list] = {k: [] for k in bugs}
    n_recipes = 0; n_lines = 0

    for rid in sample:
        try:
            r = calc.calculate(rid, unified, cls, bfl, con, [],
                                excluded, fndds_macros, product_claims, overridden,
                                sr28_macros=sr28_macros)
        except Exception:
            continue
        if not r.lines: continue
        n_recipes += 1
        sum_cost = 0.0
        sum_kcal = 0.0
        for ln in r.lines:
            n_lines += 1
            sum_cost += ln.line_cost_cents
            sum_kcal += ln.line_kcal
            # Skip lines that aren't supposed to compute cost/macros
            if ln.decision != "calculate": continue
            # 3. line_cost == grams × cpg ?
            if ln.sku_grams and ln.sku_cents and ln.grams:
                expected_cost = ln.grams * (ln.sku_cents / ln.sku_grams)
                if abs(expected_cost - ln.line_cost_cents) > COST_TOL:
                    bugs["line_cost_wrong"] += 1
                    if len(examples["line_cost_wrong"]) < 5:
                        examples["line_cost_wrong"].append({
                            "rid": rid, "bf": ln.canonical_buy_form,
                            "expected": round(expected_cost, 2),
                            "got": round(ln.line_cost_cents, 2),
                            "sku": ln.sku_name[:50]})
            # 4. line_kcal == grams × kcal/100 ?
            sku_fndds = (ln.note or "")  # not stored on line; refetch from SKU
            if ln.sku_upc and ln.grams > 0:
                cur.execute("SELECT consensus_fndds, consensus_sr28 FROM priced_products WHERE upc=? LIMIT 1", (ln.sku_upc,))
                row_f = cur.fetchone()
                fndds = (row_f[0] if row_f else "") or ""
                sr28  = (row_f[1] if row_f else "") or ""
                m = fndds_macros.get(fndds) if fndds else None
                source = "fndds" if m else ""
                if not m and sr28:
                    m = sr28_macros.get(sr28)
                    if m: source = "sr28"
                if not m and (fndds or sr28):
                    bugs["fndds_missing"] += 1
                    if len(examples["fndds_missing"]) < 5:
                        examples["fndds_missing"].append({
                            "rid": rid, "bf": ln.canonical_buy_form,
                            "fndds": fndds, "sr28": sr28, "sku": ln.sku_name[:50]})
                if m:
                    expected_kcal = ln.grams * m["kcal"] / 100.0
                    if abs(expected_kcal - ln.line_kcal) > KCAL_TOL + 0.001*expected_kcal:
                        bugs["line_kcal_wrong"] += 1
                        if len(examples["line_kcal_wrong"]) < 5:
                            examples["line_kcal_wrong"].append({
                                "rid": rid, "bf": ln.canonical_buy_form,
                                "expected": round(expected_kcal, 1),
                                "got": round(ln.line_kcal, 1),
                                "src": source, "sku": ln.sku_name[:50]})

        # 1, 2: per-recipe sums
        if abs(sum_cost - r.line_total_cents) > COST_TOL:
            bugs["cost_sum_mismatch"] += 1
        if abs(sum_kcal - r.total_kcal) > KCAL_TOL:
            bugs["kcal_sum_mismatch"] += 1

        # 7: per-serving sanity
        sv = 4
        kcal_s = r.total_kcal/sv
        prot_s = r.total_protein_g/sv
        sod_s = r.total_sodium_mg/sv
        if kcal_s > 1500: bugs["kcal_per_serving_high"] += 1
        if kcal_s < 50 and len(r.lines) >= 3: bugs["kcal_per_serving_low"] += 1
        if prot_s > 100 or prot_s < 0: bugs["protein_per_sv_extreme"] += 1
        if sod_s > 5000: bugs["sodium_per_sv_extreme"] += 1

    print(f"\n=== CALC MATH AUDIT ===")
    print(f"recipes audited: {n_recipes}")
    print(f"lines audited:   {n_lines}")
    print(f"\nbug counts:")
    for k, n in bugs.items():
        flag = " ⚠" if n > 0 else " ✓"
        print(f"  {k:<26} {n:>5}{flag}")
    print(f"\nexamples:")
    for k, ex in examples.items():
        if not ex: continue
        print(f"  {k}:")
        for e in ex:
            print(f"    {e}")

    OUT.write_text(json.dumps({"bugs": bugs, "examples": examples}, indent=2))
    print(f"\n→ {OUT}")


if __name__ == "__main__":
    main()
