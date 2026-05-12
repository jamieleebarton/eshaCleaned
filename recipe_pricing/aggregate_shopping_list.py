#!/usr/bin/env python3
"""Aggregate shopping list across multiple recipes.

Per-recipe calc treats each recipe in isolation — same butter ingredient gets
priced as a separate package per recipe. Reality: 5 recipes that all use butter
need ONE shopping list line with summed grams, then enough packages to cover
that total.

This is what Hestia does at the API layer; we hadn't built it yet.

Algorithm:
  1. For each (recipe_id, servings) in the plan, expand to per-line ingredient
     grams (scaled by servings).
  2. Resolve each recipe-line concept_key → priced concept_key via
     concept_resolution.json.
  3. Group by priced concept_key, sum grams across all recipes.
  4. For each aggregated concept, pick package combination that covers the
     total grams with minimum total cost (greedy: cheapest cpg first, scale up
     to nearest package size).

Usage:
  python3 aggregate_shopping_list.py --plan PLAN.json [--out OUT.json]

  PLAN.json: {"recipes": [{"recipe_id": 277685, "servings": 4}, ...]}
"""
from __future__ import annotations
import argparse, csv, json, math, sys
from collections import defaultdict
from pathlib import Path
csv.field_size_limit(2**30)

ROOT = Path(__file__).resolve().parents[1]
PLANNER_DATA = ROOT / "planner" / "data"
RECIPE_GRAMS  = PLANNER_DATA / "recipe_concept_grams.json"
CONCEPT_INDEX = PLANNER_DATA / "concept_index.json"
CONCEPT_RES   = PLANNER_DATA / "concept_resolution.json"
RECIPES2      = Path("/Users/jamiebarton/Desktop/Hestia/api/data/recipes2.csv")


def load_indexes():
    rcg = json.loads(RECIPE_GRAMS.read_text())["concept_grams"]
    ci  = json.loads(CONCEPT_INDEX.read_text())
    res = json.loads(CONCEPT_RES.read_text())
    # Recipe servings (default 4 if not in recipes2)
    servings = {}
    if RECIPES2.exists():
        with RECIPES2.open(encoding="utf-8", errors="replace") as f:
            for row in csv.DictReader(f):
                try: rid = int(row.get("recipeNum") or 0)
                except: continue
                try: sv = int(float(row.get("servings.max") or 4))
                except: sv = 4
                if rid: servings[rid] = max(1, sv)
    return rcg, ci, res, servings


def aggregate(plan_recipes: list[dict], rcg, ci, res, servings) -> tuple[dict, list[str]]:
    """Aggregate grams per priced concept_key across all plan recipes.

    Returns (concept_key → total_grams, list of unmatched recipe-line concepts).
    """
    by_concept: dict[str, float] = defaultdict(float)
    unmatched: list[str] = []
    for entry in plan_recipes:
        rid = str(entry["recipe_id"])
        servings_used = entry["servings"]
        servings_total = servings.get(int(rid), 4)
        scale = servings_used / max(1, servings_total)
        rg = rcg.get(rid, {})
        for rk, grams in rg.items():
            r = res.get(rk, {})
            pk = r.get("priced_key")
            if not pk:
                unmatched.append(rk); continue
            by_concept[pk] += grams * scale
    return dict(by_concept), unmatched


def pick_packages(grams_needed: float, packages: list[dict]) -> tuple[list[dict], float, float, float]:
    """Pick package combination to cover grams_needed.

    packages: [{cents, grams, name, upc, ...}] sorted by recipe-leaf rank then cpg ASC.
    Strategy: greedy — repeatedly pick the cheapest package whose grams ≥
    remaining need; if no single package big enough, take the largest available
    and continue.

    Returns (picks_list, total_cents, total_grams_bought, surplus_grams).
    """
    if not packages or grams_needed <= 0: return [], 0, 0, 0
    picks: dict = {}  # upc → count
    remaining = grams_needed
    # Sort: prefer fitting cheapest single-pack first
    by_cpg = sorted(packages, key=lambda p: p["cents"]/p["grams"])
    while remaining > 0:
        # First try a single package big enough
        fitting = [p for p in by_cpg if p["grams"] >= remaining]
        if fitting:
            best = fitting[0]  # cheapest cpg that covers remaining
            key = best["upc"]
            picks[key] = picks.get(key, 0) + 1
            remaining = 0
        else:
            # No single package fits; take the largest available, continue
            biggest = max(by_cpg, key=lambda p: p["grams"])
            picks[biggest["upc"]] = picks.get(biggest["upc"], 0) + 1
            remaining -= biggest["grams"]
            if biggest["grams"] <= 0: break  # safety

    # Materialize picks
    upc_to_pkg = {p["upc"]: p for p in packages}
    out = []
    total_cents = 0; total_grams = 0
    for upc, count in picks.items():
        pkg = upc_to_pkg[upc]
        out.append({**pkg, "count": count})
        total_cents += pkg["cents"] * count
        total_grams += pkg["grams"] * count
    surplus = total_grams - grams_needed
    return out, total_cents, total_grams, surplus


def build_shopping_list(plan_recipes: list[dict],
                          pantry_grams_by_concept: dict[str, float] | None = None) -> dict:
    """Build whole-cart shopping list. If pantry_grams_by_concept is given,
    subtract pantry stock from each concept's needed grams before computing
    package picks — i.e., we only pay for what we actually need to BUY this
    week, not what we already have on hand from prior weeks."""
    rcg, ci, res, servings = load_indexes()
    print(f"loaded: {len(rcg):,} recipe grams, {len(ci):,} priced concepts, "
          f"{len(res):,} resolutions", file=sys.stderr)

    by_concept, unmatched = aggregate(plan_recipes, rcg, ci, res, servings)
    print(f"\naggregated {len(by_concept):,} concepts across "
          f"{len(plan_recipes)} recipes ({len(unmatched)} unmatched lines)",
          file=sys.stderr)

    pantry_used_total = 0.0
    if pantry_grams_by_concept:
        # Subtract pantry stock from each concept's need
        recipe_keys = set(by_concept.keys())
        pantry_keys = set(pantry_grams_by_concept.keys())
        overlap = recipe_keys & pantry_keys
        for ck in list(by_concept.keys()):
            in_pantry = pantry_grams_by_concept.get(ck, 0.0)
            if in_pantry > 0:
                used = min(in_pantry, by_concept[ck])
                by_concept[ck] -= used
                pantry_used_total += used
                if by_concept[ck] <= 0:
                    del by_concept[ck]
        print(f"  pantry stock: {len(pantry_keys)} concepts, overlap with recipes: "
              f"{len(overlap)}, used {pantry_used_total:.0f}g",
              file=sys.stderr)

    rows = []
    grand_cents = 0; grand_grams_needed = 0; grand_grams_bought = 0
    for ck, grams_needed in sorted(by_concept.items(), key=lambda x: -x[1]):
        c = ci.get(ck)
        if not c or not c.get("packages"): continue
        picks, total_cents, total_grams, surplus = pick_packages(
            grams_needed, c["packages"])
        rows.append({
            "concept": ck, "canonical_path": c["canonical_path"],
            "modifier": c["modifier"], "htc_form": c["htc_form"],
            "grams_needed": round(grams_needed, 1),
            "grams_bought": round(total_grams, 1),
            "surplus_grams": round(surplus, 1),
            "total_cents": int(total_cents),
            "n_packages": sum(p["count"] for p in picks),
            "picks": [{"name": p["name"][:80], "count": p["count"],
                        "cents": p["cents"], "grams": p["grams"], "upc": p["upc"]}
                       for p in picks],
        })
        grand_cents += total_cents
        grand_grams_needed += grams_needed
        grand_grams_bought += total_grams

    return {
        "n_concepts": len(rows),
        "n_recipes_in_plan": len(plan_recipes),
        "total_cents": int(grand_cents),
        "total_dollars": round(grand_cents/100, 2),
        "grams_needed": round(grand_grams_needed, 1),
        "grams_bought": round(grand_grams_bought, 1),
        "pantry_grams_used": round(pantry_used_total, 1),
        "surplus_pct": round(100 * (grand_grams_bought - grand_grams_needed) /
                              max(1, grand_grams_bought), 1),
        "n_unmatched_lines": len(unmatched),
        "rows": rows,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", required=True, help="JSON: {'recipes':[{'recipe_id':N,'servings':S},...]}")
    ap.add_argument("--out",  default="/tmp/aggregate_shopping.json")
    args = ap.parse_args()

    plan = json.loads(Path(args.plan).read_text())
    out = build_shopping_list(plan["recipes"])
    Path(args.out).write_text(json.dumps(out, indent=2))

    print(f"\n=== SHOPPING LIST ===")
    print(f"  {out['n_concepts']:,} unique concepts across {out['n_recipes_in_plan']} recipes")
    print(f"  total: ${out['total_dollars']:.2f}  ({out['grams_needed']:.0f}g needed, "
          f"{out['grams_bought']:.0f}g bought, {out['surplus_pct']:.1f}% surplus)")
    print(f"  unmatched lines: {out['n_unmatched_lines']}")
    print(f"\nTop 15 line items by grams:")
    for r in out["rows"][:15]:
        leaf = r["canonical_path"].split(" > ")[-1]
        n_pkg = r["n_packages"]
        print(f"  {leaf[:30]:<30} {r['grams_needed']:>7.0f}g  ${r['total_cents']/100:>6.2f}  "
              f"({n_pkg} pkg)  {r['picks'][0]['name'][:55]}")


if __name__ == "__main__":
    main()
