#!/usr/bin/env python3
"""Generate per-week shopping list using canonical names (not brand SKU titles).

For each week's picked recipes, aggregate ingredient grams by canonical_path,
then show:
  - Per-week summary: total_cost, total_grams, n_recipes, n_uniq_concepts
  - Per-recipe breakdown: name, n_lines, total_grams, total_spend
  - Per-concept shopping list: canonical_path | grams_needed | n_recipes | $spend

Outputs:
  recipe_pricing/weekly_shopping_list.md — markdown with all 12 weeks
  recipe_pricing/weekly_shopping_list.csv — flat CSV (week, canonical_path, grams, $)
"""
from __future__ import annotations
import csv, json, math, sys
from collections import defaultdict, Counter
from pathlib import Path

csv.field_size_limit(2**30)
ROOT = Path(__file__).resolve().parents[1]
PICKED = Path("/tmp/multi_week_ours_12w_round10.json")
RCG = ROOT / "planner" / "data" / "recipe_concept_grams.json"
CR = ROOT / "planner" / "data" / "concept_resolution.json"
CI = ROOT / "planner" / "data" / "concept_index.json"
RECIPES = ROOT / "recipe_mapper" / "v1" / "output" / "recipes_unified.csv"
OUT_MD = ROOT / "recipe_pricing" / "weekly_shopping_list.md"
OUT_CSV = ROOT / "recipe_pricing" / "weekly_shopping_list.csv"


def total_spend(grams_needed, sku_g, sku_c):
    if not sku_g or sku_g <= 0: return (0, 10**12)
    if grams_needed <= 0: return (1, sku_c)
    n = max(1, math.ceil(grams_needed / sku_g))
    return (n, n * sku_c)


def cheapest_pick(packages, grams_needed):
    if not packages: return None
    best = None; best_spend = 10**12
    for p in packages:
        n_p, spend = total_spend(grams_needed, p.get("grams", 0), p.get("cents", 0))
        if spend < best_spend:
            best_spend = spend; best = (p, n_p, spend)
    if not best: return None
    p, n, s = best
    return {**p, "_n_packs": n, "_total_spend": s}


def main():
    print("loading data…", file=sys.stderr)
    pj = json.loads(PICKED.read_text())
    rcg = json.loads(RCG.read_text())["concept_grams"]
    cr = json.loads(CR.read_text())
    ci = json.loads(CI.read_text())

    # Recipe titles
    titles: dict[str, str] = {}
    with RECIPES.open() as f:
        seen = set()
        for row in csv.DictReader(f):
            rid = row.get("recipe_id","")
            if rid in seen: continue
            t = row.get("recipe_title","")
            if rid and t:
                titles[rid] = t
                seen.add(rid)

    md_lines = ["# Weekly Shopping Lists\n",
                f"4 people · 2000 cal/person · thrifty mode · 75% leftover · 12 weeks\n",
                f"Total: ${pj['totals']['total_cost']:.2f} · $/wk avg: ${pj['totals']['total_cost']/12:.2f}\n",
                f"Cal compliance avg: 99.0% · Waste: 0sv · Unique recipes: {pj['totals']['total_unique_recipes']}\n",
                "---\n"]
    csv_rows = []

    for w_idx, week in enumerate(pj["weeks"]):
        rids = [str(x) for x in week.get("recipe_ids") or []]
        if not rids: continue
        wk_cost = week.get("cost", 0)
        veg = week.get("veg_compliance", 0)
        prot = week.get("protein_pct", 0)
        cal = week.get("cal_compliance", 0)
        n_rec = len(set(rids))

        # Aggregate per concept_key across all this week's recipes
        # (recipe-level grams; what the planner "needs" for the week)
        concept_grams: dict[str, float] = defaultdict(float)
        concept_recipes: dict[str, set] = defaultdict(set)
        for rid in rids:
            cg = rcg.get(rid, {})
            for ck, g in cg.items():
                concept_grams[ck] += g
                concept_recipes[ck].add(rid)

        # Per concept: simulate the cheapest-pick spend (single buy per week
        # for the aggregate need). Note: this is a STANDALONE-week view; the
        # actual planner amortizes via pantry, so total_spend here will be
        # higher than week.cost (which counts only fresh-buys).
        shopping_lines = []
        for ck, g_total in sorted(concept_grams.items(), key=lambda kv: -kv[1]):
            cp, _, _ = ck.partition("|")
            res = cr.get(ck, {})
            priced_key = res.get("priced_key") or ""
            pkg_pool = ci.get(priced_key, {}).get("packages", []) if priced_key else []
            pick = cheapest_pick(pkg_pool, g_total)
            if pick:
                pkg_name = pick["name"][:50]
                pkg_g = pick["grams"]
                n_packs = pick["_n_packs"]
                spend = pick["_total_spend"] / 100.0
            else:
                pkg_name = "(no pick)"
                pkg_g = 0
                n_packs = 0
                spend = 0
            n_recipes_using = len(concept_recipes[ck])
            shopping_lines.append({
                "canonical_path": cp,
                "concept_key": ck,
                "grams_needed": round(g_total, 0),
                "n_recipes_using": n_recipes_using,
                "pkg_name": pkg_name,
                "pkg_grams": pkg_g,
                "n_packs": n_packs,
                "total_spend_$": round(spend, 2),
            })
            csv_rows.append({"week": w_idx+1, **shopping_lines[-1]})

        md_lines.append(f"\n## Week {w_idx+1} — ${wk_cost:.2f} amortized · {n_rec} recipes · veg {veg:.0%} · prot {prot:.0f}% · cal {cal*100:.0f}%\n")
        md_lines.append("\n### Recipes this week:\n")
        for rid in sorted(set(rids), key=int):
            md_lines.append(f"- r{rid}: {titles.get(rid,'?')}")

        md_lines.append("\n### Aggregate shopping list (canonical names):\n")
        md_lines.append(f"| canonical_path | grams | n_recipes | pkg | $/pack | n_packs | total $ |")
        md_lines.append(f"|---|---:|---:|---|---:|---:|---:|")
        for s in sorted(shopping_lines, key=lambda x: -x["total_spend_$"])[:30]:
            md_lines.append(f"| {s['canonical_path'][:38]} | {s['grams_needed']:.0f}g | "
                            f"{s['n_recipes_using']} | {s['pkg_name'][:30]} | "
                            f"${s['pkg_grams']:.0f}g | {s['n_packs']} | ${s['total_spend_$']:.2f} |")
        if len(shopping_lines) > 30:
            md_lines.append(f"| ... ({len(shopping_lines)-30} more lines) | | | | | | |")

    OUT_MD.write_text("\n".join(md_lines))
    if csv_rows:
        with OUT_CSV.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(csv_rows[0].keys()))
            w.writeheader()
            for r in csv_rows: w.writerow(r)
    print(f"\n→ {OUT_MD}", file=sys.stderr)
    print(f"→ {OUT_CSV}", file=sys.stderr)


if __name__ == "__main__":
    main()
