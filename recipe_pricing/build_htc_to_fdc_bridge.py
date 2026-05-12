#!/usr/bin/env python3
"""Build htc_code → fdc_id bridge for deterministic SR28 portion lookup.

Joins:
  recipes_unified.csv     →  ingredient_item.lower() ↔ htc_code (per-line)
  ingredient_to_sr28.csv  →  ingredient_item.lower() → fdc_id

For each htc_code, picks the dominant fdc_id (recipe-weighted majority).
Surfaces htc_codes where the dominant pick covers <80% of recipes for
manual review.

Output: recipe_pricing/htc_to_fdc.csv
Columns: htc_code, fdc_id, sr_description, n_recipes, dominant_pct,
         alt_fdc_ids, ambiguity_flag

Read-only.

Usage:
  python3 recipe_pricing/build_htc_to_fdc_bridge.py [--dry-run]
"""
from __future__ import annotations
import argparse, csv, sys
from collections import Counter, defaultdict
from pathlib import Path

csv.field_size_limit(2**30)
ROOT = Path(__file__).resolve().parents[1]
RECIPES = ROOT / "recipe_mapper" / "v1" / "output" / "recipes_unified.csv"
ING_TO_SR28 = ROOT / "recipe_mapper" / "v1" / "output" / "ingredient_to_sr28.csv"
OUT = ROOT / "recipe_pricing" / "htc_to_fdc.csv"
SR28_FOOD = ROOT / "data" / "sr28_csv" / "food.csv"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    # 1. Load ingredient → fdc_id from existing bridge, then apply overrides
    print("loading ingredient_to_sr28…", file=sys.stderr)
    ing_to_fdc: dict[str, tuple[str, str]] = {}  # item → (fdc_id, sr_description)
    with ING_TO_SR28.open() as f:
        r = csv.DictReader(f)
        for row in r:
            it = (row.get("item") or "").lower().strip()
            fdc = (row.get("fdc_id") or "").strip()
            desc = (row.get("sr_description") or "").strip()
            if it and fdc:
                ing_to_fdc[it] = (fdc, desc)
    print(f"  {len(ing_to_fdc):,} item → fdc mappings", file=sys.stderr)

    # 2. Apply manual overrides for known-bad bridge entries (broths, stocks, etc.)
    OVERRIDES = ROOT / "recipe_pricing" / "ingredient_fdc_overrides.csv"
    n_override = 0
    if OVERRIDES.exists():
        with OVERRIDES.open() as f:
            r = csv.DictReader(f)
            for row in r:
                it = (row.get("item") or "").lower().strip()
                fdc = (row.get("fdc_id") or "").strip()
                desc = (row.get("sr_description") or "").strip()
                if it and fdc:
                    ing_to_fdc[it] = (fdc, desc)
                    n_override += 1
        print(f"  applied {n_override} manual overrides from ingredient_fdc_overrides.csv",
              file=sys.stderr)

    # 2. Walk recipes_unified.csv: per-line collect (htc_code, ingredient_item)
    print("walking recipes_unified…", file=sys.stderr)
    htc_to_items: dict[str, Counter] = defaultdict(Counter)  # htc_code → {item: line_count}
    n_lines = 0
    with RECIPES.open() as f:
        r = csv.DictReader(f)
        for row in r:
            n_lines += 1
            if n_lines % 500_000 == 0:
                print(f"  {n_lines:,} lines", file=sys.stderr)
            htc = (row.get("htc_code") or "").strip()
            ing = (row.get("ingredient_item") or "").lower().strip()
            if not htc or not ing: continue
            htc_to_items[htc][ing] += 1

    # 3. For each htc, count fdc_id distribution via the bridge
    print(f"\nresolving fdc_id per htc_code (have {len(htc_to_items):,} htcs)…", file=sys.stderr)
    rows_out = []
    n_dominant_low = 0
    for htc, items in htc_to_items.items():
        fdc_counts: Counter = Counter()
        items_via = 0
        for it, n in items.items():
            ent = ing_to_fdc.get(it)
            if not ent: continue
            fdc, desc = ent
            fdc_counts[(fdc, desc)] += n
            items_via += n
        if not fdc_counts: continue
        total_lines = sum(items.values())
        (best_fdc, best_desc), best_n = fdc_counts.most_common(1)[0]
        dominant_pct = best_n / total_lines * 100
        alt = [f"{f}:{n}" for (f, _), n in fdc_counts.most_common()[1:4]]
        ambiguity_flag = dominant_pct < 80
        if ambiguity_flag: n_dominant_low += 1
        rows_out.append({
            "htc_code": htc,
            "fdc_id": best_fdc,
            "sr_description": best_desc,
            "n_recipes": total_lines,
            "dominant_pct": round(dominant_pct, 1),
            "alt_fdc_ids": "|".join(alt),
            "ambiguity_flag": int(ambiguity_flag),
        })

    rows_out.sort(key=lambda r: -r["n_recipes"])
    print(f"\n  htcs with fdc_id: {len(rows_out):,}", file=sys.stderr)
    print(f"  ambiguous (<80% dominant): {n_dominant_low:,}", file=sys.stderr)

    if args.dry_run:
        print(f"\nTop 15 highest-volume htc → fdc mappings:", file=sys.stderr)
        for r in rows_out[:15]:
            print(f"  htc={r['htc_code']}  fdc={r['fdc_id']}  ({r['dominant_pct']:.0f}%)  "
                  f"n={r['n_recipes']:>6}  '{r['sr_description'][:50]}'", file=sys.stderr)
        print(f"\nSample ambiguous (low dominant_pct):", file=sys.stderr)
        amb = [r for r in rows_out if r['ambiguity_flag']][:10]
        for r in amb:
            print(f"  htc={r['htc_code']}  fdc={r['fdc_id']}  ({r['dominant_pct']:.0f}%)  "
                  f"n={r['n_recipes']}  alt={r['alt_fdc_ids']}  '{r['sr_description'][:50]}'", file=sys.stderr)
        print(f"\n(dry-run; not written)", file=sys.stderr)
        return

    OUT.parent.mkdir(parents=True, exist_ok=True)
    if rows_out:
        with OUT.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows_out[0].keys()))
            w.writeheader()
            for r in rows_out: w.writerow(r)
    print(f"\n→ {OUT}", file=sys.stderr)


if __name__ == "__main__":
    main()
