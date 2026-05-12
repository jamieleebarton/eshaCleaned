#!/usr/bin/env python3
"""Batch-run the v7 calculator on every recipe in the classifier output.
Emit per-recipe totals: line_cost_cents, cart_total_cents, kcal, protein_g,
fat_g, carb_g, fiber_g, sodium_mg, total_grams.

Output: recipe_pricing/recipe_totals.json   (recipe_id → dict of totals)

This feeds Hestia's tensor cache rebuild — replaces stale costs/macros from
recipes2.csv + food_packages_final.db with our calc output.
"""
from __future__ import annotations

import csv
import json
import sqlite3
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import calculate_recipe_cost_v7 as calc

ROOT = Path(__file__).resolve().parents[1]
OUT_JSON = ROOT / "recipe_pricing" / "recipe_totals.json"
OUT_PROGRESS = ROOT / "recipe_pricing" / "recipe_totals.partial.json"

csv.field_size_limit(sys.maxsize)


def main() -> int:
    print("loading shared indexes...", file=sys.stderr)
    unified = calc.load_unified()
    classifications, titles = calc.load_classifications()
    bfl, overridden = calc.load_buy_form_lookup()
    excluded_upcs = calc.load_excluded_upcs()
    fndds_macros = calc.load_fndds_macros()
    product_claims = calc.load_product_claims()

    print(f"  {len(unified):,} recipes in unified, {len(classifications):,} classified",
          file=sys.stderr)

    con = sqlite3.connect(str(calc.PRICED_DB))

    rids = list(classifications.keys())
    print(f"running calc on {len(rids):,} recipes...", file=sys.stderr)

    out: dict[str, dict] = {}
    n_calc = 0
    n_no_calc = 0
    t0 = time.time()
    for i, rid in enumerate(rids, 1):
        try:
            r = calc.calculate(
                str(rid), unified, classifications, titles,
                con, bfl, overridden, excluded_upcs, fndds_macros, product_claims,
                user_facets=[],
            )
        except Exception as e:
            n_no_calc += 1
            continue
        out[str(rid)] = {
            "title": r.recipe_title,
            "line_cost_cents": round(r.line_total_cents, 2),
            "cart_total_cents": r.cart_total_cents,
            "kcal": round(r.total_kcal, 1),
            "protein_g": round(r.total_protein_g, 2),
            "fat_g": round(r.total_fat_g, 2),
            "carb_g": round(r.total_carb_g, 2),
            "fiber_g": round(r.total_fiber_g, 2),
            "sodium_mg": round(r.total_sodium_mg, 1),
            "n_lines": len(r.lines),
            "coverage": dict(r.coverage),
        }
        n_calc += 1
        if i % 5000 == 0:
            elapsed = time.time() - t0
            rate = i / elapsed
            remaining = (len(rids) - i) / rate
            print(f"  {i:>7,}/{len(rids):,}  {elapsed/60:.1f}m elapsed  "
                  f"({rate:.0f}/s, ~{remaining/60:.1f}m left)", file=sys.stderr)
            # Periodic save in case of crash
            with OUT_PROGRESS.open("w") as f:
                json.dump(out, f)

    print(f"\nfinal: {n_calc:,} calculated, {n_no_calc:,} errors", file=sys.stderr)
    with OUT_JSON.open("w") as f:
        json.dump(out, f)
    print(f"→ {OUT_JSON}", file=sys.stderr)
    OUT_PROGRESS.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
