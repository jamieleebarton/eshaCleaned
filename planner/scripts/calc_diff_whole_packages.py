#!/usr/bin/env python3
"""Re-do per-recipe Hestia vs ours, but compute OUR cost as the SHOPPING-CART
cost: sum of cheapest whole package that covers each ingredient's grams need.

You can't buy 88% of a pasta box — you buy the whole box.

OURS now:
  for each ingredient line in recipe (decision='calculate'):
    pick the cheapest package whose grams >= line.grams,
    OR if no single package fits, take enough packages to cover.
  recipe_cost = sum of those whole-package prices, deduped by upc

Note: a single recipe with 15 unique ingredients = 15 packages = real shopping
trip cost. (No multi-recipe pantry pooling — that's done elsewhere.)
"""
from __future__ import annotations
import csv, json, random, sqlite3, sys
from pathlib import Path
csv.field_size_limit(2**30)

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "recipe_pricing"))
import calculate_recipe_cost_v7 as calc

OUT = ROOT / "planner" / "data" / "calc_diff_whole_packages.md"
RECIPES2 = Path("/Users/jamiebarton/Desktop/Hestia/api/data/recipes2.csv")
SAMPLE = 100


def fnum(v):
    try: return float(v) if v not in ("", None) else 0.0
    except: return 0.0


def load_hestia_values() -> dict[int, dict]:
    out = {}
    with RECIPES2.open(encoding="utf-8", errors="replace") as f:
        for row in csv.DictReader(f):
            try: rid = int(row.get("recipeNum") or 0)
            except: continue
            if rid: out[rid] = {
                "name": row.get("recipeName",""),
                "cost": fnum(row.get("total_estimated_cost")),
                "kcal": fnum(row.get("calories_total_kcal")),
                "mass": fnum(row.get("total_mass_g")) or fnum(row.get("totalMass")),
            }
    return out


def whole_package_cost(grams_needed: float, packages: list, surplus_track: dict) -> tuple[float, list, float]:
    """Pick whole package(s) that cover grams_needed.
    Returns (total_cents, list_of_picked_pkgs, surplus_grams)."""
    if not packages or grams_needed <= 0: return 0, [], 0
    # packages: [{cents, grams, name, upc, ...}] already sorted by cpg ASC
    by_cpg = sorted(packages, key=lambda p: p["cents"]/p["grams"])
    fitting = [p for p in by_cpg if p["grams"] >= grams_needed]
    if fitting:
        pkg = fitting[0]
        return pkg["cents"], [pkg], pkg["grams"] - grams_needed
    # No single package big enough — take cheapest, then more if needed
    remaining = grams_needed
    picked = []
    total_cents = 0
    biggest = max(packages, key=lambda p: p["grams"])
    while remaining > 0:
        picked.append(biggest)
        total_cents += biggest["cents"]
        remaining -= biggest["grams"]
        if biggest["grams"] <= 0: break
    return total_cents, picked, -remaining  # negative remaining = surplus


def main():
    hestia = load_hestia_values()
    print(f"loaded {len(hestia):,} Hestia values", file=sys.stderr)

    unified = calc.load_unified()
    cls = calc.load_classifications()
    bfl, overridden = calc.load_buy_form_lookup()
    excluded = calc.load_excluded_upcs()
    fndds_macros = calc.load_fndds_macros()
    sr28_macros = calc.load_sr28_macros() if hasattr(calc,'load_sr28_macros') else {}
    product_claims = calc.load_product_claims()
    con = sqlite3.connect(str(calc.PRICED_DB))
    cur = con.cursor()

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
        except Exception:
            continue

        # Build per-ingredient whole-package cost
        # Group lines by their picked SKU upc → sum grams need per upc, then
        # buy enough packages.
        from collections import defaultdict
        upc_grams: dict[str, float] = defaultdict(float)
        upc_pkg: dict[str, dict] = {}
        unmet = []
        for ln in r.lines:
            if ln.decision != "calculate" or not ln.sku_upc or ln.grams <= 0:
                continue
            upc_grams[ln.sku_upc] += ln.grams
            if ln.sku_upc not in upc_pkg:
                upc_pkg[ln.sku_upc] = {
                    "name": ln.sku_name, "cents": ln.sku_cents,
                    "grams": ln.sku_grams, "upc": ln.sku_upc,
                }

        line_attrib_cents = sum(ln.line_cost_cents for ln in r.lines if ln.decision == "calculate")
        whole_cents = 0
        n_packages = 0
        surplus_g = 0
        picks = []
        for upc, grams_need in upc_grams.items():
            pkg = upc_pkg[upc]
            n_pack = max(1, int(-(-grams_need // max(1, pkg["grams"]))))  # ceil
            cost_cents = pkg["cents"] * n_pack
            grams_bought = pkg["grams"] * n_pack
            whole_cents += cost_cents
            n_packages += n_pack
            surplus_g += (grams_bought - grams_need)
            picks.append({"name": pkg["name"][:55], "cents": pkg["cents"],
                          "grams_pkg": pkg["grams"], "n_packages": n_pack,
                          "grams_need": round(grams_need, 1)})

        rows.append({
            "rid": rid, "title": r.recipe_title or h["name"],
            "hestia_cost": h["cost"], "hestia_kcal": h["kcal"], "hestia_mass": h["mass"],
            "ours_line_attrib": round(line_attrib_cents/100, 2),
            "ours_whole_cart":  round(whole_cents/100, 2),
            "n_packages": n_packages,
            "surplus_g": round(surplus_g, 0),
            "picks": picks,
        })

    rows.sort(key=lambda r: -abs(r["ours_whole_cart"] - r["hestia_cost"]))

    # Headlines
    avg_h = sum(r["hestia_cost"] for r in rows)/len(rows)
    avg_o_line = sum(r["ours_line_attrib"] for r in rows)/len(rows)
    avg_o_whole = sum(r["ours_whole_cart"] for r in rows)/len(rows)

    print(f"\n=== HEADLINE ({len(rows)} recipes) ===")
    print(f"  Hestia cached cost:        ${avg_h:.2f}")
    print(f"  Ours LINE-ATTRIB cost:     ${avg_o_line:.2f}  (the fake number)")
    print(f"  Ours WHOLE-CART cost:      ${avg_o_whole:.2f}  (real shopping cost)")
    print(f"  whole-cart vs Hestia diff: ${avg_o_whole - avg_h:+.2f}")

    md = ["# Per-recipe Hestia vs Ours — REAL shopping cost (whole packages)\n"]
    md.append(f"\nSample {len(rows)} recipes; ours uses sum of cheapest whole package per unique SKU.\n")
    md.append(f"\n## Aggregate\n")
    md.append(f"| Metric | Hestia | Ours (line-attrib) | Ours (whole cart) |")
    md.append(f"|---|---:|---:|---:|")
    md.append(f"| avg cost ($) | {avg_h:.2f} | {avg_o_line:.2f} | **{avg_o_whole:.2f}** |")
    md.append(f"| Δ vs Hestia | — | {avg_o_line - avg_h:+.2f} | **{avg_o_whole - avg_h:+.2f}** |\n")

    md.append("## Top 15 cost divergences (whole-cart vs Hestia)\n")
    md.append("| rid | title | hestia $ | ours line $ | ours WHOLE $ | n_pkg | surplus g |")
    md.append("|---|---|---:|---:|---:|---:|---:|")
    for r in rows[:15]:
        md.append(f"| {r['rid']} | {r['title'][:38]} | {r['hestia_cost']:.2f} | "
                   f"{r['ours_line_attrib']:.2f} | **{r['ours_whole_cart']:.2f}** | "
                   f"{r['n_packages']} | {r['surplus_g']:.0f} |")

    md.append("\n## Brisket walkthrough (rid 189779)\n")
    brisket = next((r for r in rows if r["rid"] == 189779), None)
    if brisket:
        md.append(f"- Hestia cached: ${brisket['hestia_cost']:.2f}")
        md.append(f"- Ours line-attributable: ${brisket['ours_line_attrib']:.2f}")
        md.append(f"- Ours WHOLE CART: ${brisket['ours_whole_cart']:.2f} ({brisket['n_packages']} packages)\n")
        md.append("| picked | size | $ | n × pack | grams needed |")
        md.append("|---|---:|---:|---:|---:|")
        for p in brisket["picks"]:
            md.append(f"| {p['name']} | {p['grams_pkg']:.0f}g | ${p['cents']/100:.2f} | "
                       f"{p['n_packages']} | {p['grams_need']:.0f}g |")

    md.append("\n## Snappy Turtles walkthrough (rid 49508)\n")
    sn = next((r for r in rows if r["rid"] == 49508), None)
    if sn:
        md.append(f"- Hestia cached: ${sn['hestia_cost']:.2f}")
        md.append(f"- Ours line-attributable: ${sn['ours_line_attrib']:.2f}")
        md.append(f"- Ours WHOLE CART: ${sn['ours_whole_cart']:.2f} ({sn['n_packages']} packages)")
        md.append("\n| picked | size | $ | n × pack | grams needed |")
        md.append("|---|---:|---:|---:|---:|")
        for p in sn["picks"]:
            md.append(f"| {p['name']} | {p['grams_pkg']:.0f}g | ${p['cents']/100:.2f} | "
                       f"{p['n_packages']} | {p['grams_need']:.0f}g |")

    OUT.write_text("\n".join(md))
    print(f"\n→ {OUT}")


if __name__ == "__main__":
    main()
