#!/usr/bin/env python3
"""Find SKUs where the htc_form_code says one food but the modifier (or path
leaf) says a different food — i.e., the HTC was assigned wrong.

Method: at each htc_form_code, look at the distribution of modifier values.
If most SKUs share a common food family (e.g. "Plain", "Whole Wheat" at
wheat-flour HTC) but a few outliers belong to a different family
("Black Bean", "Garbanzo Bean") AND those outliers have a price >2× the
pool median — flag them.

Outputs CSV ranked by severity (price multiple × SKU count). Manual review
before A2 applies fixes.
"""
from __future__ import annotations
import csv, sqlite3, statistics, sys
from collections import defaultdict
from pathlib import Path

ROOT = Path("/Users/jamiebarton/Desktop/esha_audit_bundle")
DB   = ROOT / "recipe_pricing" / "data" / "priced_products_v2.db"
OUT  = ROOT / "recipe_pricing" / "htc_mismatch_audit.csv"

# Tokens that suggest a DIFFERENT food family than the dominant one.
# When these appear in a modifier (or product name) at an HTC where most
# SKUs have a different identity, flag.
FOOD_FAMILY_TOKENS = {
    "wheat":   ["wheat", "all purpose", "white flour", "whole wheat", "bread", "00"],
    "rice":    ["rice", "rice flour"],
    "corn":    ["corn", "masa", "polenta", "cornmeal"],
    "almond":  ["almond"],
    "coconut": ["coconut"],
    "oat":     ["oat"],
    "chickpea": ["chickpea", "garbanzo", "besan"],
    "blackbean": ["black bean"],
    "buckwheat": ["buckwheat"],
    "spelt":   ["spelt"],
    "tapioca": ["tapioca", "cassava"],
    "potato":  ["potato"],
    "milk":    ["milk", "dairy"],
    "soy":     ["soy"],
    "lentil":  ["lentil"],
}


def family_from_tokens(text: str) -> set[str]:
    t = (text or "").lower()
    found = set()
    for fam, toks in FOOD_FAMILY_TOKENS.items():
        for tok in toks:
            if tok in t:
                found.add(fam); break
    return found


def main():
    con = sqlite3.connect(str(DB))
    cur = con.cursor()
    cur.execute("""SELECT DISTINCT upc, name, REPLACE(htc_form_code,'~','') AS hf,
        consensus_canonical, consensus_modifier, grams, cents
        FROM priced_products
        WHERE htc_form_code IS NOT NULL
          AND htc_form_code NOT IN ('','00000000')
          AND consensus_canonical IS NOT NULL
          AND available = 1 AND grams > 0 AND cents > 0""")
    rows = cur.fetchall()
    print(f"scanning {len(rows):,} distinct food SKUs…", file=sys.stderr)

    # Group by htc_form to find dominant family in each pool
    by_hf: dict[str, list] = defaultdict(list)
    for r in rows:
        upc, name, hf, cp, mod, g, c = r
        by_hf[hf].append({"upc": upc, "name": name, "cp": cp,
                          "mod": mod or "", "grams": g, "cents": c,
                          "cpg": c/g if g else 0})

    bugs = []
    for hf, pool in by_hf.items():
        if len(pool) < 5: continue  # too small to detect outliers
        # What's the dominant family across modifier+name+path?
        family_counts: dict[str, int] = defaultdict(int)
        for s in pool:
            fams = family_from_tokens(s["mod"]) | family_from_tokens(s["name"]) | family_from_tokens(s["cp"])
            if not fams:
                family_counts["__nofamily__"] += 1
            else:
                for f in fams: family_counts[f] += 1
        # Skip if no clear dominant family
        sorted_fams = sorted(family_counts.items(), key=lambda x: -x[1])
        if not sorted_fams or sorted_fams[0][0] == "__nofamily__":
            continue
        dominant = sorted_fams[0][0]
        dominant_count = sorted_fams[0][1]
        if dominant_count < 0.6 * len(pool):  # require 60%+ pool agrees
            continue
        # Compute median price for SKUs in dominant family
        dom_skus = [s for s in pool if dominant in family_from_tokens(s["mod"]+" "+s["name"]+" "+s["cp"])]
        if len(dom_skus) < 3: continue
        median_cpg = statistics.median(s["cpg"] for s in dom_skus)
        # Find outliers — SKUs at this HTC NOT in the dominant family AND price >2× median
        for s in pool:
            fams = family_from_tokens(s["mod"]) | family_from_tokens(s["name"]) | family_from_tokens(s["cp"])
            if dominant in fams:
                continue
            if not fams:
                continue  # no clear other-family signal; skip
            other_family = next(iter(fams))
            ratio = (s["cpg"] / median_cpg) if median_cpg > 0 else 0
            if ratio < 1.5:
                continue
            bugs.append({
                "htc_form": hf,
                "upc": s["upc"],
                "name": s["name"][:80],
                "canonical_path": s["cp"][:50],
                "modifier": s["mod"][:30],
                "dominant_family": dominant,
                "actual_family": other_family,
                "pool_median_cpg": round(median_cpg, 4),
                "this_cpg": round(s["cpg"], 4),
                "ratio": round(ratio, 2),
                "grams": round(s["grams"], 1),
                "cents": s["cents"],
            })

    bugs.sort(key=lambda b: -b["ratio"])
    print(f"  flagged: {len(bugs):,} HTC mismatches", file=sys.stderr)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    cols = list(bugs[0].keys()) if bugs else ["htc_form","upc","name","canonical_path","modifier",
        "dominant_family","actual_family","pool_median_cpg","this_cpg","ratio","grams","cents"]
    with OUT.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for b in bugs: w.writerow(b)
    print(f"  → {OUT}", file=sys.stderr)

    print(f"\n=== TOP 25 by price-ratio severity ===")
    for b in bugs[:25]:
        print(f"  htc={b['htc_form']}  ratio={b['ratio']:.1f}×  dominant={b['dominant_family']:<10} "
              f"actual={b['actual_family']:<10}  ${b['cents']/100:>5.2f}  {b['name'][:55]}")


if __name__ == "__main__":
    main()
