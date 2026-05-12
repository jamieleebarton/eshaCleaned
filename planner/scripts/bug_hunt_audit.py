#!/usr/bin/env python3
"""Wide bug-hunting audit. Run cost calc on N recipes, score each by
suspicion, then dump top cases per category for line-by-line review.

Categories:
  WE_TOO_LOW       ours_whole < 25% of Hestia AND Hestia > 5
  WE_TOO_HIGH      ours_whole > 2× Hestia AND Hestia > 5
  HESTIA_ZERO      Hestia cached cost = 0 AND ours_whole > 5
  MANY_PACKAGES    n_packages > 20
  HIGH_SURPLUS     surplus_g > 10 × grams_needed_total
  MISSING_LINES    ≥3 ingredient lines have grams=0 or no SKU
  ZERO_COST        ours_whole = 0
"""
from __future__ import annotations
import csv, json, random, sqlite3, sys
from collections import defaultdict
from pathlib import Path
csv.field_size_limit(2**30)

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "recipe_pricing"))
import calculate_recipe_cost_v7 as calc

OUT_MD = ROOT / "planner" / "data" / "bug_hunt.md"
OUT_JSON = ROOT / "planner" / "data" / "bug_hunt.json"
RECIPES2 = Path("/Users/jamiebarton/Desktop/Hestia/api/data/recipes2.csv")
SAMPLE = 200


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
                }
    return out


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

    rng = random.Random(42)
    rids = [r for r in cls.keys() if r in unified and int(r) in hestia]
    sample = rng.sample(rids, min(SAMPLE, len(rids)))

    audited = []
    for rid_str in sample:
        rid = int(rid_str)
        h = hestia[rid]
        try:
            r = calc.calculate(rid_str, unified, cls, bfl, con, [], excluded,
                                fndds_macros, product_claims, overridden,
                                sr28_macros=sr28_macros)
        except Exception:
            continue
        # Whole-cart cost (per-UPC dedup)
        upc_grams = defaultdict(float)
        upc_pkg = {}
        for ln in r.lines:
            if ln.decision != "calculate" or not ln.sku_upc or ln.grams <= 0: continue
            upc_grams[ln.sku_upc] += ln.grams
            upc_pkg.setdefault(ln.sku_upc, ln)
        whole_cents = 0; n_pkg = 0; total_grams_need = 0; surplus = 0
        for upc, gn in upc_grams.items():
            ln = upc_pkg[upc]
            n = max(1, int(-(-gn // max(1, ln.sku_grams))))
            whole_cents += ln.sku_cents * n
            n_pkg += n
            total_grams_need += gn
            surplus += (ln.sku_grams * n) - gn

        # Missing-line check
        n_missing = sum(
            1 for ln in r.lines
            if ln.decision == "calculate" and (ln.grams <= 0 or not ln.sku_upc)
        )
        n_total_lines = sum(1 for ln in r.lines if ln.decision == "calculate")

        ours = round(whole_cents / 100, 2)
        h_cost = h["cost"]

        flags = []
        if h_cost > 5 and ours < h_cost * 0.25:
            flags.append("WE_TOO_LOW")
        if h_cost > 5 and ours > h_cost * 2.0 and ours > 30:
            flags.append("WE_TOO_HIGH")
        if h_cost == 0 and ours > 5:
            flags.append("HESTIA_ZERO")
        if n_pkg > 20:
            flags.append("MANY_PACKAGES")
        if total_grams_need > 0 and surplus > 10 * total_grams_need:
            flags.append("HIGH_SURPLUS")
        if n_missing >= 3 or (n_total_lines > 0 and n_missing / n_total_lines > 0.5):
            flags.append("MISSING_LINES")
        if ours == 0 and n_total_lines > 0:
            flags.append("ZERO_COST")

        # Build per-line picks
        line_picks = []
        for ln in r.lines:
            line_picks.append({
                "ingredient": ln.raw_display[:75],
                "decision": ln.decision,
                "grams": round(ln.grams, 1),
                "sku": (ln.sku_name or "(none)")[:55],
                "pkg_grams": round(ln.sku_grams, 0) if ln.sku_grams else 0,
                "pkg_cents": ln.sku_cents,
            })

        audited.append({
            "rid": rid,
            "title": r.recipe_title or h["name"],
            "hestia": h_cost,
            "ours_whole": ours,
            "n_pkg": n_pkg,
            "surplus_g": int(surplus),
            "grams_need": int(total_grams_need),
            "n_missing": n_missing,
            "n_lines": n_total_lines,
            "flags": flags,
            "lines": line_picks,
        })

    # Aggregate by category
    by_flag = defaultdict(list)
    for a in audited:
        for f in a["flags"]:
            by_flag[f].append(a)
    for f in by_flag: by_flag[f].sort(key=lambda x: -abs(x["ours_whole"] - x["hestia"]))

    md = ["# Wide bug-hunting audit\n"]
    md.append(f"Sample: {len(audited)} recipes. Each may carry multiple flags.\n")

    md.append("## Flag counts\n")
    for f in ("WE_TOO_LOW","WE_TOO_HIGH","HESTIA_ZERO","MANY_PACKAGES",
               "HIGH_SURPLUS","MISSING_LINES","ZERO_COST"):
        md.append(f"- **{f}**: {len(by_flag.get(f, []))}")
    md.append("")

    for category in ("WE_TOO_LOW", "WE_TOO_HIGH", "MANY_PACKAGES",
                      "HIGH_SURPLUS", "MISSING_LINES", "HESTIA_ZERO"):
        cases = by_flag.get(category, [])[:5]
        if not cases: continue
        md.append(f"\n## {category} — top {len(cases)}\n")
        for a in cases:
            md.append(f"\n### {a['rid']} — {a['title'][:55]}")
            md.append(f"- Hestia: ${a['hestia']:.2f} | Ours: ${a['ours_whole']:.2f} "
                       f"| n_pkg: {a['n_pkg']} | surplus: {a['surplus_g']}g "
                       f"| missing: {a['n_missing']}/{a['n_lines']}")
            md.append(f"- Flags: {', '.join(a['flags'])}\n")
            md.append("| ingredient | decision | grams | SKU | pkg_g | $/pkg |")
            md.append("|---|---|---:|---|---:|---:|")
            for ln in a["lines"]:
                md.append(f"| {ln['ingredient']} | {ln['decision']} | {ln['grams']} | "
                           f"{ln['sku']} | {ln['pkg_grams']} | "
                           f"${ln['pkg_cents']/100:.2f} |")

    OUT_MD.write_text("\n".join(md))
    OUT_JSON.write_text(json.dumps(audited, indent=2))
    print(f"\n→ {OUT_MD}")
    print(f"→ {OUT_JSON}")
    print(f"\n=== Flag totals ===")
    for f in ("WE_TOO_LOW","WE_TOO_HIGH","HESTIA_ZERO","MANY_PACKAGES",
               "HIGH_SURPLUS","MISSING_LINES","ZERO_COST"):
        print(f"  {f}: {len(by_flag.get(f, []))}")


if __name__ == "__main__":
    main()
