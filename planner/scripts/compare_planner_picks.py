#!/usr/bin/env python3
"""Compare what OUR planner picked vs what HESTIA picked for the SAME recipes.

For each recipe, prices it under BOTH systems:
  - OURS:   recipe_concept_grams.json (concept_keys) → priced_products_v2.db
  - HESTIA: recipes2.csv fndds_grams_dict → food_packages_esha_shadow.db

Then surfaces the recipes with the biggest cost divergence so we can see
which ingredient lines drive the gap.

Usage:
  python3 compare_planner_picks.py --rids 49508,189779
  python3 compare_planner_picks.py --plan-ours OUR.json --plan-hes HES.json
                                     --top 20 --out report.md
"""
from __future__ import annotations
import argparse, ast, csv, json, math, sqlite3, sys
from pathlib import Path
csv.field_size_limit(2**30)

ROOT = Path(__file__).resolve().parents[2]
OURS_DB = ROOT / "recipe_pricing" / "data" / "priced_products_v2.db"
HESTIA_DB = Path("/Users/jamiebarton/Desktop/Hestia/api/data/food_packages_esha_shadow.db")
RECIPES2 = Path("/Users/jamiebarton/Desktop/Hestia/api/data/recipes2.csv")
RCG_PATH = ROOT / "planner" / "data" / "recipe_concept_grams.json"
CI_PATH = ROOT / "planner" / "data" / "concept_index.json"
RES_PATH = ROOT / "planner" / "data" / "concept_resolution.json"


def load_hestia_recipe_lines(rids: set[str]) -> dict[str, dict]:
    """rid → {'name': str, 'fndds_grams': {fndds_code: grams}}"""
    out = {}
    with RECIPES2.open(encoding="utf-8", errors="replace") as f:
        for row in csv.DictReader(f):
            rid = row.get("recipeNum", "")
            if rid not in rids: continue
            fndds_blob = row.get("fndds_grams_dict") or "{}"
            try:
                fndds_grams = ast.literal_eval(fndds_blob) if isinstance(fndds_blob, str) else fndds_blob
            except Exception:
                fndds_grams = {}
            if not isinstance(fndds_grams, dict): fndds_grams = {}
            out[rid] = {
                "name": row.get("recipeName", ""),
                "fndds_grams": {str(k): float(v) for k, v in fndds_grams.items() if v},
            }
    return out


def cheapest_total(packages: list[tuple], grams_needed: float):
    """packages = [(cents, grams, name)]"""
    if not packages or grams_needed <= 0: return None
    def spend(p):
        c, g, _ = p
        if g <= 0: return 10**12
        return math.ceil(grams_needed / g) * c
    return min(packages, key=spend)


def hestia_pick(hes: sqlite3.Connection, fndds: str, grams_needed: float):
    cur = hes.cursor()
    cur.execute("""SELECT package_weight_grams,
        COALESCE(walmart_price_cents, kroger_price_cents) AS cents,
        food_description
        FROM packages WHERE fndds_code = ?
        AND COALESCE(walmart_price_cents, kroger_price_cents) IS NOT NULL""", (fndds,))
    rows = cur.fetchall()
    pkgs = [(c, g, n) for g, c, n in rows if g and c]
    if not pkgs: return None
    pick = cheapest_total(pkgs, grams_needed)
    if not pick: return None
    cents, g, name = pick
    name = name or ""
    n_packs = math.ceil(grams_needed / g) if g > 0 else 1
    return {"name": name[:55], "pkg_grams": round(g, 0),
            "cents": cents, "n_packs": n_packs, "spend": cents * n_packs,
            "pool": len(pkgs)}


def our_pick(rcg_concept_grams: dict, ci: dict, res: dict):
    """For an OUR-side recipe (concept_key → grams), compute total spend
    by picking cheapest_total at each concept_key (with resolution fallback).
    Returns {concept_key: {grams_needed, sku, pkg_g, cents, n_packs, spend}}."""
    out = {}
    for ck, grams_needed in rcg_concept_grams.items():
        # Resolve concept_key
        priced_key = ck
        if ck not in ci:
            r = res.get(ck, {})
            priced_key = r.get("priced_key")
        if not priced_key or priced_key not in ci:
            out[ck] = {"grams_needed": grams_needed, "sku": "(no concept match)",
                       "pkg_g": 0, "cents": 0, "n_packs": 0, "spend": 0,
                       "pool": 0}
            continue
        concept = ci[priced_key]
        pkgs = [(p["cents"], p["grams"], p["name"]) for p in concept["packages"]]
        pick = cheapest_total(pkgs, grams_needed)
        if not pick:
            out[ck] = {"grams_needed": grams_needed, "sku": "(no pkg)",
                       "pkg_g": 0, "cents": 0, "n_packs": 0, "spend": 0,
                       "pool": concept.get("n_skus_total", 0)}
            continue
        cents, g, name = pick
        n_packs = math.ceil(grams_needed / g) if g > 0 else 1
        out[ck] = {"grams_needed": grams_needed, "sku": name[:55],
                   "pkg_g": round(g, 0), "cents": cents, "n_packs": n_packs,
                   "spend": cents * n_packs,
                   "pool": concept.get("n_skus_total", 0),
                   "priced_key": priced_key}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rids", help="comma-separated recipe IDs")
    ap.add_argument("--plan-ours", help="our planner JSON output")
    ap.add_argument("--plan-hes", help="Hestia summary JSON")
    ap.add_argument("--top", type=int, default=15)
    ap.add_argument("--out", default="planner/data/planner_pick_compare.md")
    args = ap.parse_args()

    if args.rids:
        rids = set(args.rids.split(","))
    elif args.plan_ours or args.plan_hes:
        rids = set()
        if args.plan_ours:
            ours = json.load(open(args.plan_ours))
            for w in ours["weeks"]:
                rids.update(str(r) for r in w["recipe_ids"])
        if args.plan_hes:
            hes = json.load(open(args.plan_hes))
            for cell in hes.get("configs", {}).values():
                rids.update(str(r) for r in cell.get("union_recipe_ids", hes.get("union_recipe_ids", [])))
            if not rids:
                rids.update(str(r) for r in hes.get("union_recipe_ids", []))
    else:
        ap.error("--rids or --plan-* required")

    print(f"comparing {len(rids)} recipes…", file=sys.stderr)
    print("loading hestia recipe data…", file=sys.stderr)
    hestia_lines = load_hestia_recipe_lines(rids)
    print(f"  {len(hestia_lines)} matched in recipes2.csv", file=sys.stderr)

    print("loading concept_index / resolution…", file=sys.stderr)
    ci = json.loads(CI_PATH.read_text())
    res = json.loads(RES_PATH.read_text())
    print("loading recipe_concept_grams…", file=sys.stderr)
    rcg = json.loads(RCG_PATH.read_text())
    rcg_concepts = rcg.get("concept_grams", {})

    hes_db = sqlite3.connect(str(HESTIA_DB))

    recipes = []
    for rid in rids:
        # OUR side: from recipe_concept_grams.json
        our_concepts = rcg_concepts.get(rid, {})
        our_picks = our_pick(our_concepts, ci, res)
        ours_total = sum(p["spend"] for p in our_picks.values())

        # HESTIA side
        h = hestia_lines.get(rid, {"name": f"r{rid}", "fndds_grams": {}})
        hes_total = 0
        hes_picks = {}
        for fndds, grams in h["fndds_grams"].items():
            pick = hestia_pick(hes_db, fndds, grams)
            if pick:
                hes_picks[fndds] = {**pick, "grams_needed": grams}
                hes_total += pick["spend"]
            else:
                hes_picks[fndds] = {"grams_needed": grams, "name": "(no fndds match)",
                                     "pkg_grams": 0, "cents": 0, "n_packs": 0,
                                     "spend": 0, "pool": 0}

        recipes.append({
            "rid": rid, "name": h["name"][:50],
            "ours": ours_total, "hestia": hes_total,
            "diff": ours_total - hes_total,
            "n_our_lines": len(our_picks), "n_hes_lines": len(hes_picks),
            "our_picks": our_picks, "hes_picks": hes_picks,
        })

    recipes.sort(key=lambda r: -abs(r["diff"]))
    sum_o = sum(r["ours"] for r in recipes)
    sum_h = sum(r["hestia"] for r in recipes)

    md = ["# Recipe pricing: OURS vs HESTIA (per-line)\n"]
    md.append(f"\n**{len(recipes)} recipes:** ours ${sum_o/100:.2f}, "
              f"hestia ${sum_h/100:.2f}, Δ ${(sum_o-sum_h)/100:+.2f}\n")

    md.append("## Per-recipe totals (sorted by |Δ|)\n")
    md.append("| rid | recipe | ours $ | hestia $ | Δ $ | our lines | hes lines |")
    md.append("|---|---|---:|---:|---:|---:|---:|")
    for r in recipes:
        md.append(f"| {r['rid']} | {r['name']} | ${r['ours']/100:.2f} | "
                   f"${r['hestia']/100:.2f} | ${r['diff']/100:+.2f} | "
                   f"{r['n_our_lines']} | {r['n_hes_lines']} |")

    md.append(f"\n## Top {args.top} divergences — line by line\n")
    for r in recipes[:args.top]:
        md.append(f"\n### {r['rid']} — {r['name']}")
        md.append(f"- ours ${r['ours']/100:.2f} | hestia ${r['hestia']/100:.2f} | "
                  f"Δ ${r['diff']/100:+.2f}\n")
        md.append("\n**OUR picks (concept_key → spend):**")
        md.append("| concept | g need | sku | pkg_g | $/pkg | n× | spend | pool |")
        md.append("|---|---:|---|---:|---:|---:|---:|---:|")
        for ck, p in sorted(r["our_picks"].items(), key=lambda x: -x[1]["spend"]):
            md.append(f"| {ck[:50]} | {p['grams_needed']:.0f} | {p['sku']} | "
                       f"{p['pkg_g']} | ${p['cents']/100:.2f} | {p['n_packs']} | "
                       f"${p['spend']/100:.2f} | {p['pool']} |")
        md.append("\n**HESTIA picks (fndds_code → spend):**")
        md.append("| fndds | g need | sku | pkg_g | $/pkg | n× | spend | pool |")
        md.append("|---|---:|---|---:|---:|---:|---:|---:|")
        for fndds, p in sorted(r["hes_picks"].items(), key=lambda x: -x[1]["spend"]):
            md.append(f"| {fndds} | {p['grams_needed']:.0f} | "
                       f"{p.get('name','')[:55]} | {p.get('pkg_grams',0)} | "
                       f"${p.get('cents',0)/100:.2f} | {p.get('n_packs',0)} | "
                       f"${p.get('spend',0)/100:.2f} | {p.get('pool',0)} |")

    out_md = ROOT / args.out if not args.out.startswith("/") else Path(args.out)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text("\n".join(md))
    print(f"\n→ {out_md}", file=sys.stderr)
    print(f"\nAggregate: ours ${sum_o/100:.2f}, hestia ${sum_h/100:.2f}, "
          f"Δ ${(sum_o-sum_h)/100:+.2f}", file=sys.stderr)


if __name__ == "__main__":
    main()
