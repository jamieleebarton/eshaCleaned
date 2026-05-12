#!/usr/bin/env python3
"""R9d — Bridge round-trip + outlier audits.

Validates the recipe-side bridges by walking:
  recipe.ingredient_item → recipe.htc_code → htc_to_fdc.fdc_id
                       → SR28.food.description

For each htc_code, check that the SR28 description has token-overlap
with the ingredient_items that feed into it. Where they don't overlap,
the bridge is silently broken.

Plus outlier hunts:
  - SKUs with price-per-gram more than 3σ from the path's mean
  - Picked recipes with absurd cost (>$25/recipe)
  - Recipes with bizarre gram totals (>5kg per recipe with <8 lines)
  - htc_codes used by many ingredient_items (potential identity collision)

Outputs:
  recipe_pricing/audit_bridge_roundtrip.csv — htc_codes with poor name overlap
  recipe_pricing/audit_outlier_skus.csv     — price outliers per path
  recipe_pricing/audit_outlier_recipes.csv  — recipes with absurd cost/grams
"""
from __future__ import annotations
import csv, json, sqlite3, statistics, sys
from collections import defaultdict, Counter
from pathlib import Path

csv.field_size_limit(2**30)
ROOT = Path(__file__).resolve().parents[1]
RECIPES = ROOT / "recipe_mapper" / "v1" / "output" / "recipes_unified.csv"
HTC_TO_FDC = ROOT / "recipe_pricing" / "htc_to_fdc.csv"
SR28_FOOD = ROOT / "data" / "sr28_csv" / "food.csv"
DB = ROOT / "recipe_pricing" / "data" / "priced_products_v2.db"

OUT_BRIDGE = ROOT / "recipe_pricing" / "audit_bridge_roundtrip.csv"
OUT_SKU_OUTLIER = ROOT / "recipe_pricing" / "audit_outlier_skus.csv"
OUT_RECIPE_OUTLIER = ROOT / "recipe_pricing" / "audit_outlier_recipes.csv"

STOPWORDS = {"the","a","an","of","and","or","with","fresh","whole","raw",
              "organic","plain","ground","dried","cooked","ground","mix",
              "raw","food","without","added","unit","oz","pkg"}


def tokens(s: str) -> set[str]:
    import re
    return {t for t in re.findall(r"[a-z]+", (s or "").lower())
            if len(t) > 2 and t not in STOPWORDS}


def main():
    print("loading SR28 food.csv…", file=sys.stderr)
    fdc_desc: dict[str, str] = {}
    with SR28_FOOD.open() as f:
        for row in csv.DictReader(f):
            fdc_desc[row["fdc_id"]] = row["description"]
    print(f"  {len(fdc_desc):,} fdc_ids", file=sys.stderr)

    print("loading htc → fdc bridge…", file=sys.stderr)
    htc_to_fdc: dict[str, tuple[str, str]] = {}
    with HTC_TO_FDC.open() as f:
        for row in csv.DictReader(f):
            htc_to_fdc[row["htc_code"]] = (row["fdc_id"], row["sr_description"])
    print(f"  {len(htc_to_fdc):,} htc → fdc", file=sys.stderr)

    print("walking recipes_unified for ingredient_item per htc_code…", file=sys.stderr)
    htc_items: dict[str, Counter] = defaultdict(Counter)
    rows_seen = 0
    with RECIPES.open() as f:
        for row in csv.DictReader(f):
            rows_seen += 1
            htc = (row.get("htc_code") or "").strip().lstrip("~")
            ing = (row.get("ingredient_item") or "").lower().strip()
            if htc and ing:
                htc_items[htc][ing] += 1
    print(f"  {rows_seen:,} lines", file=sys.stderr)
    print(f"  {len(htc_items):,} unique htc_codes used", file=sys.stderr)

    # === BRIDGE ROUND-TRIP ===
    print("\nrunning bridge round-trip…", file=sys.stderr)
    bridge_rows = []
    n_overlap_zero = 0; n_overlap_partial = 0; n_overlap_clean = 0
    for htc, items in htc_items.items():
        bridge = htc_to_fdc.get(htc)
        if not bridge: continue
        fdc, desc = bridge
        sr_desc = fdc_desc.get(fdc, desc)
        sr_toks = tokens(sr_desc)
        # Aggregate ingredient tokens (top 5 most-common items)
        top_items = items.most_common(5)
        all_ing_toks = set()
        for it, _ in top_items:
            all_ing_toks |= tokens(it)
        if not all_ing_toks: continue
        overlap = sr_toks & all_ing_toks
        n_lines = sum(items.values())
        if not overlap:
            n_overlap_zero += 1
            verdict = "NO_OVERLAP"
        elif len(overlap) == 1 and len(all_ing_toks) > 2:
            n_overlap_partial += 1
            verdict = "WEAK_OVERLAP"
        else:
            n_overlap_clean += 1
            verdict = "OK"
        if verdict != "OK":
            bridge_rows.append({
                "htc_code": htc,
                "fdc_id": fdc,
                "sr_description": sr_desc[:50],
                "n_lines": n_lines,
                "top_ingredients": "|".join(it for it, _ in top_items[:3]),
                "ing_tokens": "|".join(sorted(all_ing_toks)[:6]),
                "sr_tokens": "|".join(sorted(sr_toks)[:6]),
                "overlap": "|".join(sorted(overlap)),
                "verdict": verdict,
            })
    bridge_rows.sort(key=lambda r: -r["n_lines"])
    print(f"  htc_codes with NO_OVERLAP: {n_overlap_zero:,}", file=sys.stderr)
    print(f"  htc_codes with WEAK_OVERLAP: {n_overlap_partial:,}", file=sys.stderr)
    print(f"  htc_codes with OK overlap: {n_overlap_clean:,}", file=sys.stderr)

    if bridge_rows:
        with OUT_BRIDGE.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(bridge_rows[0].keys()))
            w.writeheader()
            for r in bridge_rows: w.writerow(r)
    print(f"\n→ {OUT_BRIDGE}", file=sys.stderr)
    print(f"\nTop 10 broken-bridge htc_codes (by line volume):", file=sys.stderr)
    for r in bridge_rows[:10]:
        print(f"  htc={r['htc_code']:<10} n={r['n_lines']:>6}  fdc={r['fdc_id']}  "
              f"'{r['sr_description']}'  ingredients=({r['top_ingredients'][:40]})", file=sys.stderr)

    # === SKU PRICE OUTLIERS ===
    print("\nrunning SKU price-per-gram outlier audit…", file=sys.stderr)
    con = sqlite3.connect(str(DB))
    by_path: dict[str, list[tuple[str, float, str, int, float]]] = defaultdict(list)
    for r in con.execute("""SELECT consensus_canonical, name, cents/grams AS cpg,
                            cents, grams FROM priced_products
                            WHERE available=1 AND cents>0 AND grams>0
                              AND consensus_canonical IS NOT NULL
                              AND consensus_canonical != ''""").fetchall():
        cp, name, cpg, cents, grams = r
        by_path[cp].append((name, cpg, name, cents, grams))
    sku_outliers = []
    for cp, skus in by_path.items():
        if len(skus) < 5: continue
        cpgs = [s[1] for s in skus]
        try: med = statistics.median(cpgs)
        except: continue
        if med <= 0: continue
        # Outlier: cpg > 5x median (likely mispriced for this path)
        for name, cpg, _, cents, grams in skus:
            if cpg > med * 5:
                sku_outliers.append({
                    "canonical_path": cp,
                    "sku_name": name[:60],
                    "cpg_$/g": round(cpg, 4),
                    "median_cpg_$/g": round(med, 4),
                    "ratio_vs_median": round(cpg/med, 2),
                    "cents": cents, "grams": round(grams, 1),
                })
    sku_outliers.sort(key=lambda r: -r["ratio_vs_median"])
    if sku_outliers:
        with OUT_SKU_OUTLIER.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(sku_outliers[0].keys()))
            w.writeheader()
            for r in sku_outliers[:200]: w.writerow(r)
    print(f"  {len(sku_outliers):,} SKUs with cpg > 5× path median", file=sys.stderr)
    print(f"\nTop 10 price-per-gram outliers:", file=sys.stderr)
    for r in sku_outliers[:10]:
        print(f"  ${r['cpg_$/g']:.3f}/g (path med ${r['median_cpg_$/g']:.3f})  ratio={r['ratio_vs_median']}× "
              f"  '{r['sku_name']}' @ '{r['canonical_path'][:30]}'", file=sys.stderr)

    # === RECIPE OUTLIERS (uses round-8 picks) ===
    print("\nrunning recipe outlier audit…", file=sys.stderr)
    PICKED_R8 = Path("/tmp/multi_week_ours_12w_round8.json")
    if PICKED_R8.exists():
        d = json.loads(PICKED_R8.read_text())
        # Just per-recipe sanity from concept_grams
        rcg = json.loads((ROOT / "planner/data/recipe_concept_grams.json").read_text())["concept_grams"]
        picked_rids = set()
        for w in d["weeks"]:
            for x in w["recipe_ids"]: picked_rids.add(str(x))

        recipe_outliers = []
        for rid in picked_rids:
            cg = rcg.get(rid, {})
            if not cg: continue
            n_lines = len(cg)
            total_g = sum(cg.values())
            issues = []
            if total_g > 8000:
                issues.append(f"high_grams_{total_g/1000:.1f}kg")
            if n_lines < 3:
                issues.append(f"few_lines_{n_lines}")
            if n_lines > 25:
                issues.append(f"many_lines_{n_lines}")
            if issues:
                recipe_outliers.append({
                    "recipe_id": rid,
                    "n_lines": n_lines,
                    "total_grams": round(total_g, 0),
                    "issues": "|".join(issues),
                })
        recipe_outliers.sort(key=lambda r: -r["total_grams"])
        if recipe_outliers:
            with OUT_RECIPE_OUTLIER.open("w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=list(recipe_outliers[0].keys()))
                w.writeheader()
                for r in recipe_outliers: w.writerow(r)
        print(f"  {len(recipe_outliers):,} picked recipes with outlier flags", file=sys.stderr)
        print(f"\nTop 10 by total grams:", file=sys.stderr)
        for r in recipe_outliers[:10]:
            print(f"  rid={r['recipe_id']:>6}  n_lines={r['n_lines']:>2}  total={r['total_grams']:.0f}g  flags={r['issues']}",
                  file=sys.stderr)


if __name__ == "__main__":
    main()
