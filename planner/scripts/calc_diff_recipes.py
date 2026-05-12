#!/usr/bin/env python3
"""Side-by-side per-recipe calc comparison.

For each sampled recipe:

  HESTIA (cached, FNDDS-derived in recipes2.csv):
    total_estimated_cost
    calories_total_kcal, protein_total_g, fat_total_g, carbs_total_g
    total_mass_g
    food_groups.vegetables_g / fruit_g / dairy_g / grains_g / protein_g

  OURS (live, SKU-priced, calculate_recipe_cost_v7):
    line_total_cents → dollars
    total_kcal, total_protein_g, total_fat_g, total_carb_g
    total_mass = sum of line.grams (only 'calculate' lines)
    food_groups: heuristic from picked-SKU canonical_path

We also emit per-line SKU picks so the user can see what Hestia would have
expected vs what we picked.

Output:
  planner/data/calc_diff_recipes.json  — full data
  planner/data/calc_diff_recipes.md    — human-readable side-by-side
"""
from __future__ import annotations
import csv, json, random, sqlite3, sys
from pathlib import Path
csv.field_size_limit(2**30)

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "recipe_pricing"))
import calculate_recipe_cost_v7 as calc

OUT_JSON = ROOT / "planner" / "data" / "calc_diff_recipes.json"
OUT_MD   = ROOT / "planner" / "data" / "calc_diff_recipes.md"
RECIPES2 = Path("/Users/jamiebarton/Desktop/Hestia/api/data/recipes2.csv")
SAMPLE = 100


def load_hestia_values() -> dict[int, dict]:
    """rid → recipes2.csv per-recipe values."""
    out = {}
    keys = [
        "recipeName","total_estimated_cost",
        "calories_total_kcal","protein_total_g","fat_total_g","carbs_total_g",
        "total_mass_g","totalMass","fiber","sodium","sodium_total_mg",
        "food_groups.vegetables_g","food_groups.fruit_g",
        "food_groups.dairy_g","food_groups.grains_g","food_groups.protein_g",
        "servings.max",
    ]
    with RECIPES2.open(encoding="utf-8", errors="replace") as f:
        for row in csv.DictReader(f):
            try: rid = int(row.get("recipeNum") or 0)
            except: continue
            if rid == 0: continue
            d = {"rid": rid}
            for k in keys:
                v = row.get(k, "")
                d[k] = v
            out[rid] = d
    return out


def fnum(v) -> float:
    try: return float(v) if v not in ("", None) else 0.0
    except: return 0.0


def main():
    print("loading Hestia recipes2.csv values…", file=sys.stderr)
    hestia = load_hestia_values()
    print(f"  {len(hestia):,} recipes with Hestia values", file=sys.stderr)

    print("loading our calculator data…", file=sys.stderr)
    unified = calc.load_unified()
    cls = calc.load_classifications()
    bfl, overridden = calc.load_buy_form_lookup()
    excluded = calc.load_excluded_upcs()
    fndds_macros = calc.load_fndds_macros()
    sr28_macros = calc.load_sr28_macros() if hasattr(calc, "load_sr28_macros") else {}
    product_claims = calc.load_product_claims()
    con = sqlite3.connect(str(calc.PRICED_DB))

    rng = random.Random(11)
    rids_in_both = [r for r in cls.keys() if r in unified and int(r) in hestia]
    sample = rng.sample(rids_in_both, min(SAMPLE, len(rids_in_both)))

    rows = []
    for rid_str in sample:
        rid = int(rid_str)
        h = hestia[rid]
        try:
            r = calc.calculate(rid_str, unified, cls, bfl, con, [], excluded,
                                fndds_macros, product_claims, overridden,
                                sr28_macros=sr28_macros)
        except TypeError:
            r = calc.calculate(rid_str, unified, cls, bfl, con, [], excluded,
                                fndds_macros, product_claims, overridden)
        except Exception as e:
            continue
        servings = max(1, int(fnum(h.get("servings.max")) or 4))
        # Sum mass from our 'calculate' lines
        ours_mass = sum(ln.grams for ln in r.lines if ln.decision == "calculate")
        # Per-line picks
        line_picks = []
        for ln in r.lines:
            line_picks.append({
                "ingredient": ln.raw_display[:80],
                "buy_form": ln.canonical_buy_form,
                "decision": ln.decision,
                "grams": round(ln.grams, 1),
                "sku": ln.sku_name[:65] if ln.sku_name else "",
                "line_cost": round(ln.line_cost_cents/100.0, 2),
                "line_kcal": round(ln.line_kcal, 0),
                "line_protein": round(ln.line_protein_g, 1),
            })

        h_cost  = fnum(h.get("total_estimated_cost"))
        h_kcal  = fnum(h.get("calories_total_kcal"))
        h_prot  = fnum(h.get("protein_total_g"))
        h_fat   = fnum(h.get("fat_total_g"))
        h_carb  = fnum(h.get("carbs_total_g"))
        h_mass  = fnum(h.get("total_mass_g")) or fnum(h.get("totalMass"))
        h_sodium = fnum(h.get("sodium_total_mg")) or fnum(h.get("sodium"))

        o_cost = round(r.line_total_cents/100.0, 2)
        o_kcal = round(r.total_kcal, 0)
        o_prot = round(r.total_protein_g, 1)
        o_fat  = round(r.total_fat_g, 1)
        o_carb = round(r.total_carb_g, 1)
        o_mass = round(ours_mass, 1)
        o_sodium = round(r.total_sodium_mg, 0)

        rows.append({
            "rid": rid,
            "title": r.recipe_title or h.get("recipeName",""),
            "servings": servings,
            "hestia": {"cost": h_cost, "kcal": h_kcal, "protein": h_prot,
                        "fat": h_fat, "carb": h_carb, "mass": h_mass, "sodium": h_sodium},
            "ours":   {"cost": o_cost, "kcal": o_kcal, "protein": o_prot,
                        "fat": o_fat, "carb": o_carb, "mass": o_mass, "sodium": o_sodium},
            "diff": {
                "cost":     round(o_cost - h_cost, 2),
                "kcal":     round(o_kcal - h_kcal, 0),
                "protein":  round(o_prot - h_prot, 1),
                "mass":     round(o_mass - h_mass, 1),
                "sodium":   round(o_sodium - h_sodium, 0),
            },
            "lines": line_picks,
        })

    OUT_JSON.write_text(json.dumps(rows, indent=2))

    # Build markdown
    rows.sort(key=lambda r: -abs(r["diff"]["cost"]))
    md = ["# Per-recipe calc A/B — Hestia (recipes2.csv FNDDS) vs Ours (SKU-priced)\n"]
    md.append(f"Sample: {len(rows)} recipes; sorted by abs(cost diff) descending.\n")
    md.append("## Aggregate stats\n")
    avg_cost_h = sum(r["hestia"]["cost"] for r in rows)/len(rows)
    avg_cost_o = sum(r["ours"]["cost"] for r in rows)/len(rows)
    avg_kcal_h = sum(r["hestia"]["kcal"] for r in rows)/len(rows)
    avg_kcal_o = sum(r["ours"]["kcal"] for r in rows)/len(rows)
    avg_mass_h = sum(r["hestia"]["mass"] for r in rows)/len(rows)
    avg_mass_o = sum(r["ours"]["mass"] for r in rows)/len(rows)
    md.append(f"| Metric | Hestia avg | Ours avg | Δ |")
    md.append(f"|---|---:|---:|---:|")
    md.append(f"| total cost ($) | {avg_cost_h:.2f} | {avg_cost_o:.2f} | {avg_cost_o-avg_cost_h:+.2f} |")
    md.append(f"| kcal/recipe | {avg_kcal_h:.0f} | {avg_kcal_o:.0f} | {avg_kcal_o-avg_kcal_h:+.0f} |")
    md.append(f"| mass/recipe (g) | {avg_mass_h:.0f} | {avg_mass_o:.0f} | {avg_mass_o-avg_mass_h:+.0f} |")

    md.append("\n## Top 10 cost divergences\n")
    md.append("| rid | title | hestia $ | ours $ | Δ$ | hestia kcal | ours kcal | mass diff |")
    md.append("|---|---|---:|---:|---:|---:|---:|---:|")
    for r in rows[:10]:
        md.append(f"| {r['rid']} | {r['title'][:38]} | {r['hestia']['cost']:.2f} | "
                   f"{r['ours']['cost']:.2f} | {r['diff']['cost']:+.2f} | "
                   f"{r['hestia']['kcal']:.0f} | {r['ours']['kcal']:.0f} | "
                   f"{r['diff']['mass']:+.0f}g |")

    md.append("\n## Top 5 — full ingredient-by-ingredient comparison\n")
    for r in rows[:5]:
        md.append(f"\n### {r['rid']} — {r['title']}")
        md.append(f"- Hestia: ${r['hestia']['cost']:.2f}  /  {r['hestia']['kcal']:.0f} kcal  /  {r['hestia']['protein']:.0f}g prot  /  {r['hestia']['mass']:.0f}g mass")
        md.append(f"- Ours:   ${r['ours']['cost']:.2f}  /  {r['ours']['kcal']:.0f} kcal  /  {r['ours']['protein']:.0f}g prot  /  {r['ours']['mass']:.0f}g mass")
        md.append(f"\n| line | grams | SKU | $line | kcal |")
        md.append(f"|---|---:|---|---:|---:|")
        for ln in r["lines"]:
            md.append(f"| {ln['ingredient'][:50]} | {ln['grams']} | {ln['sku'][:55]} | "
                       f"{ln['line_cost']:.2f} | {ln['line_kcal']} |")

    md.append("\n## Top 10 mass-divergence (recipes where total_mass disagrees most)\n")
    rows.sort(key=lambda r: -abs(r["diff"]["mass"]))
    md.append("| rid | title | hestia mass | ours mass | Δ |")
    md.append("|---|---|---:|---:|---:|")
    for r in rows[:10]:
        md.append(f"| {r['rid']} | {r['title'][:42]} | {r['hestia']['mass']:.0f} | "
                   f"{r['ours']['mass']:.0f} | {r['diff']['mass']:+.0f}g |")

    OUT_MD.write_text("\n".join(md))
    print(f"\n→ {OUT_JSON}", file=sys.stderr)
    print(f"→ {OUT_MD}", file=sys.stderr)
    print(f"\n=== HEADLINE ===")
    print(f"  avg cost — Hestia: ${avg_cost_h:.2f}  Ours: ${avg_cost_o:.2f}  (Δ {avg_cost_o-avg_cost_h:+.2f})")
    print(f"  avg kcal — Hestia: {avg_kcal_h:.0f}  Ours: {avg_kcal_o:.0f}  (Δ {avg_kcal_o-avg_kcal_h:+.0f})")
    print(f"  avg mass — Hestia: {avg_mass_h:.0f}g  Ours: {avg_mass_o:.0f}g  (Δ {avg_mass_o-avg_mass_h:+.0f}g)")


if __name__ == "__main__":
    main()
