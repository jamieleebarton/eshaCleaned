#!/usr/bin/env python3
"""Side-by-side recipe pricing diagnostic — OURS (concept-keyed) vs
BROAD-PATH (Hestia-equivalent: pool by canonical_path leaf, ignore HTC granularity).

The user's question: Hestia treats recipes as needing "milk" → broad pool.
We treat them as needing (canonical_path | htc_form) → narrow pool. This
script shows per-line where the narrow pool forces a worse pick.

For each ingredient line in each recipe:
  - OUR pick: cheapest-total at (canonical_path | htc_form) — exact concept
  - BROAD pick: cheapest-total at canonical_path (any htc_form) — what Hestia does
  - Δ = ours - broad

Usage:
  python3 compare_recipe_picks.py --plan PLAN.json --week 8 --top 10
  python3 compare_recipe_picks.py --rids 49508,189779 --out report.md
"""
from __future__ import annotations
import argparse, csv, json, math, sqlite3, sys
from collections import defaultdict
from pathlib import Path
csv.field_size_limit(2**30)

ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / "recipe_pricing" / "data" / "priced_products_v2.db"
UNIFIED = ROOT / "recipe_mapper" / "v1" / "output" / "recipes_unified.csv"
TAXONOMY_V2 = ROOT / "recipe_mapper" / "v1" / "output" / "recipe_ingredient_taxonomy_v2.csv"


def load_title_to_path() -> dict[str, str]:
    """ingredient_item (lowered) → canonical_path."""
    out: dict[str, str] = {}
    with TAXONOMY_V2.open() as f:
        for row in csv.DictReader(f):
            t = (row.get("title") or "").strip().lower()
            cp = (row.get("canonical_path") or "").strip()
            if t and cp: out[t] = cp
    return out


def load_recipe_lines(rids: set[str], title_to_path: dict[str, str]) -> dict[str, list[dict]]:
    by_recipe: dict[str, list[dict]] = defaultdict(list)
    titles: dict[str, str] = {}
    with UNIFIED.open() as f:
        for row in csv.DictReader(f):
            rid = row.get("recipe_id", "")
            if rid not in rids: continue
            try: grams = float(row.get("grams_resolved") or 0)
            except: grams = 0.0
            if grams <= 0: continue
            item = (row.get("ingredient_item") or "").strip().lower()
            cp = title_to_path.get(item, "")
            htc = (row.get("htc_code") or "").strip().lstrip("~")
            t = (row.get("recipe_title") or "").strip()
            if t and rid not in titles: titles[rid] = t
            by_recipe[rid].append({
                "display": row.get("display", ""),
                "ingredient_item": item,
                "canonical_path": cp,
                "htc_form": htc,
                "grams": grams,
            })
    return by_recipe, titles


def cheapest_total(packages: list[tuple], grams_needed: float):
    if not packages or grams_needed <= 0: return None
    def spend(p):
        c, g = p[0], p[1]
        if g <= 0: return 10**12
        return math.ceil(grams_needed / g) * c
    return min(packages, key=spend)


def query_pool(con, where: str, params: tuple) -> list[tuple]:
    cur = con.cursor()
    cur.execute(f"""SELECT cents, grams, name, upc FROM priced_products
        WHERE {where} AND available=1 AND grams>0 AND cents>0
        AND htc_form_code NOT IN ('','00000000')""", params)
    return cur.fetchall()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rids", help="Comma-separated recipe IDs")
    ap.add_argument("--plan", help="Plan JSON (multi_week output)")
    ap.add_argument("--week", type=int, help="Week index 1-based")
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--out", default="planner/data/recipe_pick_compare.md")
    ap.add_argument("--json", help="Optional JSON output path")
    args = ap.parse_args()

    if args.rids:
        rids = set(args.rids.split(","))
    elif args.plan:
        plan = json.load(open(args.plan))
        if args.week:
            wk = plan["weeks"][args.week - 1]
            rids = {str(r) for r in wk.get("recipe_ids", [])}
        else:
            rids = set()
            for wk in plan.get("weeks", []):
                rids.update(str(r) for r in wk.get("recipe_ids", []))
    else:
        ap.error("--rids or --plan required")

    print(f"loading {len(rids)} recipes…", file=sys.stderr)
    title_to_path = load_title_to_path()
    print(f"  {len(title_to_path):,} title→path mappings", file=sys.stderr)
    by_recipe, titles = load_recipe_lines(rids, title_to_path)
    print(f"  matched {len(by_recipe)} recipes", file=sys.stderr)

    con = sqlite3.connect(str(DB))

    recipes = []
    for rid in rids:
        lines = by_recipe.get(rid, [])
        if not lines: continue
        title = titles.get(rid, f"recipe {rid}")

        ours_total = 0; broad_total = 0
        rows = []
        for ln in lines:
            cp = ln["canonical_path"]; hf = ln["htc_form"]
            grams = ln["grams"]
            # OUR pool — exact concept (cp + htc_form)
            our_pool = query_pool(con,
                "consensus_canonical = ? AND REPLACE(htc_form_code,'~','') = ?",
                (cp, hf)) if cp and hf else []
            our_pick = cheapest_total(our_pool, grams)
            our_pool_n = len(set((p[3] for p in our_pool)))
            if our_pick:
                oc, og, on, ou = our_pick
                on_packs = math.ceil(grams / og) if og > 0 else 1
                our_spend = oc * on_packs
                our_str = f"{on[:55]} ({og:.0f}g × {on_packs}, pool={our_pool_n})"
            else:
                our_spend = 0; our_str = "(no concept match)"

            # BROAD pool — canonical_path only (ignore htc_form granularity)
            broad_pool = query_pool(con,
                "consensus_canonical = ?", (cp,)) if cp else []
            broad_pick = cheapest_total(broad_pool, grams)
            broad_pool_n = len(set((p[3] for p in broad_pool)))
            if broad_pick:
                bc, bg, bn, bu = broad_pick
                bn_packs = math.ceil(grams / bg) if bg > 0 else 1
                broad_spend = bc * bn_packs
                broad_str = f"{bn[:55]} ({bg:.0f}g × {bn_packs}, pool={broad_pool_n})"
            else:
                broad_spend = 0; broad_str = "(no path match)"

            ours_total += our_spend
            broad_total += broad_spend
            rows.append({
                "display": ln["display"][:55],
                "grams": round(grams, 1),
                "cp": cp[:35], "htc": hf,
                "our_spend": our_spend, "our_str": our_str,
                "broad_spend": broad_spend, "broad_str": broad_str,
                "diff": our_spend - broad_spend,
            })

        recipes.append({
            "rid": rid, "title": title,
            "ours_total": ours_total, "broad_total": broad_total,
            "diff": ours_total - broad_total,
            "n_lines": len(lines), "rows": rows,
        })

    recipes.sort(key=lambda r: -abs(r["diff"]))
    top = recipes[:args.top]

    sum_o = sum(r["ours_total"] for r in recipes)
    sum_b = sum(r["broad_total"] for r in recipes)

    md = ["# Recipe Pick Comparison — OURS (concept-keyed) vs BROAD (path-only)\n"]
    md.append(f"**Across {len(recipes)} recipes:** ours ${sum_o/100:.2f}, "
              f"broad-path ${sum_b/100:.2f}, Δ ${(sum_o-sum_b)/100:+.2f}\n")
    md.append("> **Δ > 0** = our concept-keying makes us pay more than path-pooling would.\n")

    md.append("\n## Per-recipe totals (sorted by |Δ|)\n")
    md.append("| rid | recipe | ours $ | broad $ | Δ $ | lines |")
    md.append("|---|---|---:|---:|---:|---:|")
    for r in recipes:
        md.append(f"| {r['rid']} | {r['title'][:55]} | "
                   f"${r['ours_total']/100:.2f} | ${r['broad_total']/100:.2f} | "
                   f"${r['diff']/100:+.2f} | {r['n_lines']} |")

    md.append(f"\n## Top {len(top)} — line-by-line breakdown\n")
    for r in top:
        md.append(f"\n### {r['rid']} — {r['title']}")
        md.append(f"- ours ${r['ours_total']/100:.2f} | broad ${r['broad_total']/100:.2f}"
                  f" | Δ ${r['diff']/100:+.2f}\n")
        md.append("| ingredient | g | OUR pick | $ | BROAD pick | $ | Δ |")
        md.append("|---|---:|---|---:|---|---:|---:|")
        for ln in r["rows"]:
            md.append(f"| {ln['display']} | {ln['grams']:.0f} | {ln['our_str']} | "
                       f"${ln['our_spend']/100:.2f} | {ln['broad_str']} | "
                       f"${ln['broad_spend']/100:.2f} | ${ln['diff']/100:+.2f} |")

    out_md = ROOT / args.out if not args.out.startswith("/") else Path(args.out)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text("\n".join(md))
    print(f"\n→ {out_md}", file=sys.stderr)
    print(f"\nAggregate: ours ${sum_o/100:.2f}, broad ${sum_b/100:.2f}, "
          f"Δ ${(sum_o-sum_b)/100:+.2f}", file=sys.stderr)

    if args.json:
        Path(args.json).write_text(json.dumps(recipes, indent=2))
        print(f"→ {args.json}", file=sys.stderr)


if __name__ == "__main__":
    main()
