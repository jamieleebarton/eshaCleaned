#!/usr/bin/env python3
"""Per-recipe SKU audit — line-by-line, what did we pick and is it sane?

For each of N recipes (default = top divergences from prior calc_diff run):

  - recipe title, ours-line $, ours-whole-cart $, Hestia cached $
  - per-ingredient table:
      ingredient line | grams needed | OUR SKU | pkg grams | $ | n_pkgs |
      surplus_g | per-gram | flag

Flag heuristics (no human review yet — these are AUTOMATIC):

  WRONG_PATH    — picked SKU's canonical_path doesn't match recipe's
                  (e.g. recipe = oregano, sku = toddler food)
  OVERSIZED     — pkg_grams > 10× grams_needed AND surplus_g > 500
                  (e.g. 32 fl oz extract for 4g need)
  PREMIUM       — picked SKU's $/g > 2× cheapest-in-its-canonical_path
                  (e.g. Private Selection vs Great Value)
  TINY_NEED     — grams_needed < 5g (spice-bottle problem regardless)
  OK            — none of the above

Output:
  planner/data/recipe_sku_audit.md
"""
from __future__ import annotations
import csv, json, sqlite3, sys
from pathlib import Path
from collections import defaultdict
csv.field_size_limit(2**30)

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "recipe_pricing"))
import calculate_recipe_cost_v7 as calc

OUT = ROOT / "planner" / "data" / "recipe_sku_audit.md"
RECIPES2 = Path("/Users/jamiebarton/Desktop/Hestia/api/data/recipes2.csv")

# Recipes to audit — mix of high-divergence + a few "expected normal"
TARGETS = [
    49508,    # Snappy Turtles cookies — $51 ours, $83 Hestia
    189779,   # Smoked brisket — $90 ours, $227 Hestia
    195954,   # Caramel Pecan Brownies — $56 ours, $0 Hestia
    260663,   # Blueberry Cobbler — $118 ours, $76 Hestia
    342529,   # Banana Nut Bread — $54 ours, $0 Hestia
    260962,   # Brown Sugar Honey Butter — $61 ours, $18 Hestia
    3344,     # Penne Piperade — $38 ours, $94 Hestia
    193084,   # Turkey Gravy — $94 ours, $48 Hestia (49 packages — wtf)
    149279,   # Almond sugar cookies — $46 ours
    168229,   # Roast Sirloin — $98 ours, $155 Hestia
]


def fnum(v):
    try: return float(v) if v not in ("", None) else 0.0
    except: return 0.0


def load_hestia_costs() -> dict[int, dict]:
    out = {}
    with RECIPES2.open(encoding="utf-8", errors="replace") as f:
        for row in csv.DictReader(f):
            try: rid = int(row.get("recipeNum") or 0)
            except: continue
            if rid:
                out[rid] = {
                    "name": row.get("recipeName",""),
                    "cost": fnum(row.get("total_estimated_cost")),
                    "kcal": fnum(row.get("calories_total_kcal")),
                }
    return out


def load_min_cpg_per_path(con) -> dict[str, float]:
    """For each canonical_path, lowest cents-per-gram among available SKUs.
    Used to flag PREMIUM picks."""
    cur = con.cursor()
    cur.execute("""SELECT consensus_canonical, MIN(CAST(cents AS REAL)/grams)
        FROM priced_products WHERE available=1 AND grams>0 AND cents>0
        GROUP BY consensus_canonical""")
    return {cp: float(m or 1.0) for cp, m in cur.fetchall() if cp}


def get_sku_canonical_path(con, upc: str) -> str:
    cur = con.cursor()
    cur.execute("SELECT consensus_canonical FROM priced_products WHERE upc=? LIMIT 1", (upc,))
    row = cur.fetchone()
    return row[0] if row else ""


def flag_line(grams_need: float, sku_grams: float, n_pkgs: int,
              surplus_g: float, recipe_path: str, sku_path: str,
              sku_cpg: float, min_cpg_at_recipe_path: float) -> str:
    flags = []
    # WRONG_PATH — top-2 segments must match (Bakery > Bread vs Pantry > Mix)
    rp_top = " > ".join((recipe_path or "").split(" > ")[:2]).lower()
    sp_top = " > ".join((sku_path   or "").split(" > ")[:2]).lower()
    if rp_top and sp_top and rp_top != sp_top:
        flags.append("WRONG_PATH")
    # OVERSIZED — bought 10× more than need
    if grams_need > 0 and sku_grams >= grams_need * 10 and surplus_g > 500:
        flags.append("OVERSIZED")
    # PREMIUM — picked SKU is >2× the cheapest in its path
    if min_cpg_at_recipe_path > 0 and sku_cpg > min_cpg_at_recipe_path * 2:
        flags.append("PREMIUM")
    # TINY_NEED — sub-5g (spice problem regardless of pick)
    if 0 < grams_need < 5:
        flags.append("TINY_NEED")
    return ",".join(flags) or "OK"


def main():
    print("loading…", file=sys.stderr)
    hestia = load_hestia_costs()
    unified = calc.load_unified()
    cls = calc.load_classifications()
    bfl, overridden = calc.load_buy_form_lookup()
    excluded = calc.load_excluded_upcs()
    fndds_macros = calc.load_fndds_macros()
    sr28_macros = calc.load_sr28_macros() if hasattr(calc, "load_sr28_macros") else {}
    product_claims = calc.load_product_claims()
    con = sqlite3.connect(str(calc.PRICED_DB))
    min_cpg = load_min_cpg_per_path(con)

    # Pull recipe paths from unified for flag reference
    recipe_path_for_line: dict[tuple[str, str], str] = {}
    with (ROOT / "recipe_mapper" / "v1" / "output" / "recipes_unified.csv").open() as f:
        for row in csv.DictReader(f):
            rid = row.get("recipe_id","")
            disp = row.get("display","")[:80]
            recipe_path_for_line[(rid, disp)] = row.get("canonical_path","") or ""

    md = ["# Per-recipe SKU audit — what did we pick, was it right?\n"]
    md.append("Flags: WRONG_PATH (sku path mismatch) | OVERSIZED (>10× need + >500g surplus) "
              "| PREMIUM (>2× cheapest in path) | TINY_NEED (<5g need) | OK\n")
    md.append("`grams_blob` = original USDA-derived grams; `grams_resolved` = parsed qty (the one we use).\n")

    summary_rows = []
    for rid in TARGETS:
        rid_str = str(rid)
        if rid_str not in unified or rid_str not in cls:
            md.append(f"\n## {rid} — NOT IN CORPUS\n")
            continue
        h = hestia.get(rid, {"name": "?", "cost": 0.0})
        try:
            r = calc.calculate(rid_str, unified, cls, bfl, con, [], excluded,
                                fndds_macros, product_claims, overridden,
                                sr28_macros=sr28_macros)
        except TypeError:
            r = calc.calculate(rid_str, unified, cls, bfl, con, [], excluded,
                                fndds_macros, product_claims, overridden)
        except Exception as e:
            md.append(f"\n## {rid} — calc error: {e}\n"); continue

        # Whole-package per-SKU cost
        upc_grams = defaultdict(float)
        upc_first_line = {}
        for ln in r.lines:
            if ln.decision != "calculate" or not ln.sku_upc or ln.grams <= 0: continue
            upc_grams[ln.sku_upc] += ln.grams
            if ln.sku_upc not in upc_first_line: upc_first_line[ln.sku_upc] = ln

        whole_cents = 0; n_packages = 0
        per_sku_rows = []
        flag_counts = defaultdict(int)
        for upc, grams_need in upc_grams.items():
            ln = upc_first_line[upc]
            n_pack = max(1, int(-(-grams_need // max(1, ln.sku_grams))))
            cost = ln.sku_cents * n_pack
            grams_bought = ln.sku_grams * n_pack
            surplus = grams_bought - grams_need
            sku_path = get_sku_canonical_path(con, upc)
            recipe_path = recipe_path_for_line.get((rid_str, ln.raw_display[:80]), "")
            sku_cpg = ln.sku_cents / max(1, ln.sku_grams)
            min_at_rp = min_cpg.get(recipe_path, 0)
            flag = flag_line(grams_need, ln.sku_grams, n_pack, surplus,
                              recipe_path, sku_path, sku_cpg, min_at_rp)
            for f in flag.split(","): flag_counts[f] += 1
            whole_cents += cost; n_packages += n_pack
            per_sku_rows.append({
                "ingredient": ln.raw_display[:60],
                "grams_need": grams_need,
                "sku": ln.sku_name[:55],
                "sku_path": sku_path[:30],
                "pkg_grams": ln.sku_grams,
                "pkg_cents": ln.sku_cents,
                "n_pack": n_pack,
                "cost": cost,
                "surplus_g": surplus,
                "flag": flag,
            })
        per_sku_rows.sort(key=lambda x: -x["cost"])

        ours_line = sum(ln.line_cost_cents for ln in r.lines if ln.decision == "calculate") / 100
        md.append(f"\n## {rid} — {r.recipe_title or h['name']}\n")
        md.append(f"- **Hestia cached:** ${h['cost']:.2f}")
        md.append(f"- **Ours line-attrib:** ${ours_line:.2f}  (food-value math, fake)")
        md.append(f"- **Ours WHOLE CART:** ${whole_cents/100:.2f}  ({n_packages} packages)\n")
        flag_str = ", ".join(f"{k}={v}" for k, v in flag_counts.items() if k != "OK" and v > 0) or "all OK"
        md.append(f"- Flags: {flag_str}\n")

        md.append("| ingredient | need g | SKU | path | pkg g | $/pkg | n× | $ | surplus g | flag |")
        md.append("|---|---:|---|---|---:|---:|---:|---:|---:|---|")
        for s in per_sku_rows:
            md.append(f"| {s['ingredient']} | {s['grams_need']:.0f} | {s['sku']} | "
                       f"{s['sku_path']} | {s['pkg_grams']:.0f} | ${s['pkg_cents']/100:.2f} | "
                       f"{s['n_pack']} | ${s['cost']/100:.2f} | {s['surplus_g']:.0f} | "
                       f"**{s['flag']}** |")
        summary_rows.append({
            "rid": rid, "title": r.recipe_title[:35],
            "hestia": h["cost"], "ours_line": ours_line, "ours_whole": whole_cents/100,
            "n_pkg": n_packages, "flags": dict(flag_counts),
        })

    md.append("\n\n## Summary\n")
    md.append("| rid | title | Hestia | Ours line | Ours whole | n_pkg | wrong_path | oversized | premium | tiny |")
    md.append("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for s in summary_rows:
        f = s["flags"]
        md.append(f"| {s['rid']} | {s['title']} | ${s['hestia']:.2f} | ${s['ours_line']:.2f} | "
                   f"${s['ours_whole']:.2f} | {s['n_pkg']} | {f.get('WRONG_PATH',0)} | "
                   f"{f.get('OVERSIZED',0)} | {f.get('PREMIUM',0)} | {f.get('TINY_NEED',0)} |")

    # Aggregate flag totals
    total_flags = defaultdict(int)
    for s in summary_rows:
        for k, v in s["flags"].items(): total_flags[k] += v
    md.append("\n### Aggregate flag totals\n")
    for k in ("OK","WRONG_PATH","OVERSIZED","PREMIUM","TINY_NEED"):
        md.append(f"- {k}: {total_flags.get(k, 0)}")

    OUT.write_text("\n".join(md))
    print(f"\n→ {OUT}")
    print(f"\nflag totals: {dict(total_flags)}")


if __name__ == "__main__":
    main()
