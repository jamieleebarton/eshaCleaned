#!/usr/bin/env python3
"""R9a — Per-recipe end-to-end audit.

For each picked recipe, walks every ingredient line from text to spend,
emitting a trace row per line with:

  recipe_id, recipe_name, line_idx, ingredient_text, ingredient_item,
  qty, unit, grams, grams_source,
  htc_code, fdc_id, sr_description,
  canonical_path, concept_key,
  resolution_tier, priced_concept_key,
  picked_sku, pkg_grams, pkg_cents, n_packs, total_spend_$,
  flag_gram, flag_bridge, flag_pick, flags_combined

Plus a per-recipe summary: total_grams, total_spend, n_lines, n_flagged.

Outputs:
  recipe_pricing/per_recipe_audit_lines.csv
  recipe_pricing/per_recipe_audit_summary.csv
"""
from __future__ import annotations
import csv, json, math, sys, sqlite3
from collections import defaultdict
from pathlib import Path

csv.field_size_limit(2**30)
ROOT = Path(__file__).resolve().parents[1]
PICKED = Path("/tmp/multi_week_ours_12w_round8.json")
RECIPES = ROOT / "recipe_mapper" / "v1" / "output" / "recipes_unified.csv"
RCG = ROOT / "planner" / "data" / "recipe_concept_grams.json"
CR = ROOT / "planner" / "data" / "concept_resolution.json"
CI = ROOT / "planner" / "data" / "concept_index.json"
HTC_TO_FDC = ROOT / "recipe_pricing" / "htc_to_fdc.csv"
SR28_FOOD = ROOT / "data" / "sr28_csv" / "food.csv"
OUT_LINES = ROOT / "recipe_pricing" / "per_recipe_audit_lines.csv"
OUT_SUMMARY = ROOT / "recipe_pricing" / "per_recipe_audit_summary.csv"


def total_spend(grams_needed: float, sku_g: float, sku_c: int):
    if not sku_g or sku_g <= 0: return (0, 10**12)
    if grams_needed <= 0: return (1, sku_c)
    n = max(1, math.ceil(grams_needed / sku_g))
    return (n, n * sku_c)


def cheapest_pick(packages: list[dict], grams_needed: float):
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
    picked = set()
    for w in pj.get("weeks", []):
        for x in w.get("recipe_ids") or []:
            picked.add(str(x))
    print(f"  {len(picked)} picked recipe IDs", file=sys.stderr)

    rcg = json.loads(RCG.read_text())["concept_grams"]
    cr = json.loads(CR.read_text())
    ci = json.loads(CI.read_text())

    htc_to_fdc: dict[str, tuple[str, str]] = {}
    with HTC_TO_FDC.open() as f:
        for row in csv.DictReader(f):
            htc_to_fdc[row["htc_code"]] = (row["fdc_id"], row["sr_description"])

    fdc_desc: dict[str, str] = {}
    with SR28_FOOD.open() as f:
        for row in csv.DictReader(f):
            fdc_desc[row["fdc_id"]] = row["description"]

    # Walk recipes_unified, collect lines for picked recipes
    print("collecting picked recipe lines…", file=sys.stderr)
    lines_by_rid: dict[str, list[dict]] = defaultdict(list)
    titles: dict[str, str] = {}
    with RECIPES.open() as f:
        for row in csv.DictReader(f):
            rid = row.get("recipe_id","")
            if rid not in picked: continue
            titles[rid] = row.get("recipe_title","")
            lines_by_rid[rid].append(row)

    # Per-line trace — use recipe_concept_grams as canonical concept_key source
    out_lines = []
    summary = []
    for rid in sorted(picked, key=lambda x: int(x) if x.isdigit() else 0):
        cg = rcg.get(rid, {})
        if not cg: continue
        title = titles.get(rid, "")
        # Build a map of htc_code → list of recipe lines (some recipes have
        # the same htc on multiple lines; we'll display the first match)
        lines_by_htc: dict[str, list[dict]] = defaultdict(list)
        for ln in lines_by_rid.get(rid, []):
            h = (ln.get("htc_code") or "").strip().lstrip("~")
            if h: lines_by_htc[h].append(ln)
        n_lines = 0; total_g = 0.0; total_cost = 0.0; n_flag = 0

        for i, (ck, g) in enumerate(cg.items()):
            cp, htc = ck.split("|", 1) if "|" in ck else (ck, "")
            # Find a matching line for display info (qty, unit, display text)
            matched_lines = lines_by_htc.get(htc, [])
            ln = matched_lines[0] if matched_lines else {}
            try: qty = float(ln.get("qty") or 0)
            except: qty = 0
            ing = (ln.get("ingredient_item") or "").strip()
            disp = ln.get("display","") or ""
            grams_source = ln.get("grams_source","")

            # Bridge: htc → fdc → SR28 desc
            bridge = htc_to_fdc.get(htc)
            fdc = bridge[0] if bridge else ""
            sr_desc = fdc_desc.get(fdc, "") if fdc else ""

            # Concept resolution + planner pick (using rcg's authoritative ck)
            res = cr.get(ck, {})
            tier = res.get("tier", "NO_MATCH")
            priced_key = res.get("priced_key") or ""
            pick_sku = ""; pick_g = 0; pick_c = 0; n_packs = 0; spend = 0
            n_pool = 0
            if priced_key and priced_key in ci:
                concept = ci[priced_key]
                packages = concept.get("packages", []) or []
                n_pool = concept.get("n_skus_total", 0)
                pick = cheapest_pick(packages, g)
                if pick:
                    pick_sku = pick.get("name","")[:60]
                    pick_g = pick.get("grams", 0)
                    pick_c = pick.get("cents", 0)
                    n_packs = pick.get("_n_packs", 0)
                    spend = pick.get("_total_spend", 0)

            # Flags per step
            flag_gram = ""
            if g <= 0 and qty > 0:
                flag_gram = "no_gram"
            elif g > 5000:
                flag_gram = "big_gram"
            flag_bridge = "" if fdc else "no_fdc"
            flag_pick = ""
            if not pick_sku:
                flag_pick = "no_sku"
            elif n_packs >= 5:
                flag_pick = f"buy_{n_packs}_packs"

            flags = "|".join(f for f in (flag_gram, flag_bridge, flag_pick) if f)
            if flags: n_flag += 1

            n_lines += 1
            total_g += g
            total_cost += spend / 100.0

            out_lines.append({
                "recipe_id": rid,
                "recipe_name": title[:60],
                "line_idx": i,
                "ingredient_text": disp[:70],
                "ingredient_item": ing[:30],
                "qty": qty,
                "unit": (ln.get("unit") or "").strip(),
                "grams": round(g, 1),
                "grams_source": grams_source,
                "htc_code": htc,
                "fdc_id": fdc,
                "sr_description": sr_desc[:40],
                "canonical_path": cp[:40],
                "resolution_tier": tier,
                "priced_concept_key": priced_key[:55],
                "n_pool": n_pool,
                "picked_sku": pick_sku,
                "pkg_grams": round(pick_g, 1),
                "pkg_cents": pick_c,
                "n_packs": n_packs,
                "total_spend_$": round(spend / 100.0, 2),
                "flags": flags,
            })

        summary.append({
            "recipe_id": rid, "name": title[:60], "n_lines": n_lines,
            "total_grams": round(total_g, 0),
            "total_spend_$": round(total_cost, 2),
            "n_flagged_lines": n_flag,
        })

    OUT_LINES.parent.mkdir(parents=True, exist_ok=True)
    if out_lines:
        with OUT_LINES.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(out_lines[0].keys()))
            w.writeheader()
            for r in out_lines: w.writerow(r)
    summary.sort(key=lambda r: -r["n_flagged_lines"])
    if summary:
        with OUT_SUMMARY.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(summary[0].keys()))
            w.writeheader()
            for r in summary: w.writerow(r)

    print(f"\n{len(out_lines):,} line traces across {len(summary):,} recipes",
          file=sys.stderr)
    n_flag_total = sum(1 for r in out_lines if r["flags"])
    print(f"  flagged lines: {n_flag_total:,}  ({n_flag_total*100/max(1,len(out_lines)):.1f}%)",
          file=sys.stderr)
    print(f"\n→ {OUT_LINES}", file=sys.stderr)
    print(f"→ {OUT_SUMMARY}", file=sys.stderr)
    print(f"\nTop 10 most-flagged recipes:", file=sys.stderr)
    for r in summary[:10]:
        print(f"  rid={r['recipe_id']:>6}  flagged={r['n_flagged_lines']:>2}/{r['n_lines']}  "
              f"  ${r['total_spend_$']:>6.2f}  {r['name']}", file=sys.stderr)


if __name__ == "__main__":
    main()
