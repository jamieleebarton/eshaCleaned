#!/usr/bin/env python3
"""R12a — Full-bridge audit (NOT just picked recipes).

For every recipe-side concept_key, look up the priced concept it resolves to,
then look up the cheapest SKU the planner would pick. Flag mismatches:

  CROSS_CATEGORY     — recipe top category != priced top category
                        (e.g., Pantry > Oil → Sauces > Mayonnaise)
  LEAF_TOKEN_MISS    — recipe-leaf and priced-leaf share no tokens
                        (e.g., Avocado → Grape Leaves)
  SKU_LEAF_MISS      — cheapest SKU has 0 token overlap with recipe-leaf
  WRONG_FORM_PICK    — picked SKU has form/state word recipe didn't ask
  TIER_FALLBACK      — resolution tier is parent_path_only or worse

Output:
  audit_full_bridge_concepts.csv  per recipe-concept row
  audit_full_bridge_summary.csv   rollup by flag
  audit_full_bridge_top.csv       worst offenders by recipe-impact volume
"""
from __future__ import annotations
import csv, json, math, re, sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CR = ROOT / "planner" / "data" / "concept_resolution.json"
CI = ROOT / "planner" / "data" / "concept_index.json"
RCG = ROOT / "planner" / "data" / "recipe_concept_grams.json"
OUT_LINES = ROOT / "recipe_pricing" / "audit_full_bridge_concepts.csv"
OUT_SUM = ROOT / "recipe_pricing" / "audit_full_bridge_summary.csv"
OUT_TOP = ROOT / "recipe_pricing" / "audit_full_bridge_top.csv"

STOP = {"the","a","an","of","and","or","with","fresh","raw","organic",
        "plain","ground","dried","cooked","frozen","canned","prepared",
        "style","flavor","mix","food","whole","ready","grade","unit","oz"}
FORM_STATE = {"sticks","stick","spray","powder","mix","packet","mush","mashed",
              "imitation","cheese product","cheese food","bouillon","panko",
              "instant","marshmallow","pickled","candied","smoked"}


def leaf_toks(p: str) -> set[str]:
    leaf = (p.split(" > ")[-1] if p else "").lower()
    return {t for t in re.findall(r"[a-z]+", leaf)
             if len(t) > 2 and t not in STOP}


def all_path_toks(p: str) -> set[str]:
    return {t for t in re.findall(r"[a-z]+", (p or "").lower())
             if len(t) > 2 and t not in STOP}


def top_cat(p: str) -> str:
    return (p.split(" > ")[0] if p else "")


def cheapest(packages: list, grams_needed: float = 100):
    if not packages: return None
    best = None; bs = 10**12
    for p in packages:
        g = p.get("grams", 0); c = p.get("cents", 0)
        if g <= 0: continue
        n = max(1, math.ceil(grams_needed / g))
        s = n * c
        if s < bs: bs = s; best = p
    return best


def main():
    cr = json.loads(CR.read_text())
    ci = json.loads(CI.read_text())
    rcg = json.loads(RCG.read_text())["concept_grams"]

    # Count recipe-impact: how many recipes touch each recipe-side concept_key
    recipe_freq: Counter = Counter()
    total_g_per_ck: Counter = Counter()
    for rid, d in rcg.items():
        for ck, g in d.items():
            recipe_freq[ck] += 1
            total_g_per_ck[ck] += g

    rows = []
    flag_counts: Counter = Counter()

    for ck, n_recipes in recipe_freq.items():
        cp, _, htc_form = ck.partition("|")
        res = cr.get(ck, {})
        tier = res.get("tier", "NO_MATCH")
        priced_key = res.get("priced_key") or ""

        priced_cp = ""
        cheap_sku = ""
        cheap_cents = 0
        cheap_grams = 0
        if priced_key and priced_key in ci:
            priced_cp = ci[priced_key]["canonical_path"]
            pkg = cheapest(ci[priced_key].get("packages", []))
            if pkg:
                cheap_sku = (pkg.get("name","") or "")[:60]
                cheap_cents = pkg.get("cents", 0)
                cheap_grams = pkg.get("grams", 0)

        rcp_leaf = leaf_toks(cp)
        prc_leaf = leaf_toks(priced_cp)
        rcp_path = all_path_toks(cp)
        prc_path = all_path_toks(priced_cp)
        sku_toks = {t for t in re.findall(r"[a-z]+", cheap_sku.lower())
                     if len(t) > 2 and t not in STOP}

        flags = []
        if tier in ("path_only","parent_path_only","NO_MATCH","form_only"):
            flags.append(f"TIER_{tier.upper()}")
        if priced_cp and top_cat(cp) and top_cat(cp) != top_cat(priced_cp):
            flags.append("CROSS_CATEGORY")
        if priced_cp and rcp_leaf and prc_leaf and not (rcp_leaf & prc_leaf):
            # but if recipe-leaf shares a token anywhere in priced-path, downgrade severity
            if not (rcp_leaf & prc_path):
                flags.append("LEAF_TOKEN_MISS")
            else:
                flags.append("LEAF_DEEPER")  # priced food is deeper variant of recipe
        if cheap_sku and rcp_leaf and sku_toks and not (rcp_leaf & sku_toks):
            flags.append("SKU_LEAF_MISS")
        # Form/state word in SKU not in recipe-side leaf
        sku_lc = cheap_sku.lower()
        for fw in FORM_STATE:
            if fw in sku_lc and fw not in (cp + " " + ck).lower():
                flags.append(f"FORM:{fw[:12]}")
                break

        for f in flags: flag_counts[f] += 1

        if not flags: continue
        rows.append({
            "recipe_cp": cp,
            "htc_form": htc_form,
            "tier": tier,
            "priced_cp": priced_cp,
            "cheapest_sku": cheap_sku,
            "sku_grams": cheap_grams,
            "sku_cents": cheap_cents,
            "n_recipes_touched": n_recipes,
            "total_g_demand": int(total_g_per_ck[ck]),
            "flags": "|".join(flags),
        })

    rows.sort(key=lambda r: -r["n_recipes_touched"])

    if rows:
        with OUT_LINES.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            for r in rows: w.writerow(r)

    # Summary
    with OUT_SUM.open("w", newline="") as f:
        w = csv.writer(f); w.writerow(["flag","n_concepts","n_recipes_total"])
        flag_recipes: Counter = Counter()
        for r in rows:
            for fl in r["flags"].split("|"):
                flag_recipes[fl] += r["n_recipes_touched"]
        for fl, n in flag_counts.most_common():
            w.writerow([fl, n, flag_recipes[fl]])

    # Top offenders by impact (>=20 recipes touched and worst flags)
    important = {"CROSS_CATEGORY","LEAF_TOKEN_MISS","SKU_LEAF_MISS"}
    top = [r for r in rows
            if r["n_recipes_touched"] >= 5
            and any(f in important for f in r["flags"].split("|"))]
    top.sort(key=lambda r: -r["n_recipes_touched"])
    if top:
        with OUT_TOP.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(top[0].keys()))
            w.writeheader()
            for r in top[:300]: w.writerow(r)

    print(f"\nrecipe-side concepts: {len(recipe_freq):,}", file=sys.stderr)
    print(f"flagged concepts:     {len(rows):,}", file=sys.stderr)
    print(f"\nFlag distribution:", file=sys.stderr)
    for fl, n in flag_counts.most_common():
        print(f"  {fl:<22}  {n:>5}  ({flag_recipes[fl]:>6,} recipe-uses)",
              file=sys.stderr)
    print(f"\nTop 25 offenders by recipe-impact (CROSS/LEAF/SKU misses, ≥5 recipes):",
          file=sys.stderr)
    for r in top[:25]:
        print(f"  {r['n_recipes_touched']:>4}× '{r['recipe_cp'][:40]}' → "
              f"'{r['priced_cp'][:40]}' :: {r['cheapest_sku'][:36]}  [{r['flags'][:30]}]",
              file=sys.stderr)
    print(f"\n→ {OUT_LINES}\n→ {OUT_SUM}\n→ {OUT_TOP}", file=sys.stderr)


if __name__ == "__main__":
    main()
