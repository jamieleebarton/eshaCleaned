#!/usr/bin/env python3
"""Classify each baking-mix-tree SKU as mix-vs-baked using multi-signal evidence.

For each SKU currently at 'Pantry > Baking Mixes' or 'Bakery > Cookie Dough':
  Compute a mix-confidence score from:
    + Title says 'mix', 'powder', 'dry', 'just add' → +mix
    + BFC explicitly says 'Mixes' → +mix
    + SR28 desc says 'dry mix' → +mix
    + FNDDS desc says 'mix' → +mix
    + Ingredients start with flour + sugar + leavening (no fat/eggs as top ingredients) → +mix
    + Title says 'baked', 'snack cake', 'ready to eat' → +baked
    + BFC says 'Snack Cakes' / 'Cookies & Biscuits' (without 'Mix') → +baked
    + Ingredients have eggs/oil/butter as primary → +baked

If verdict = baked AND currently in baking mixes → propose reroute.

Output: retail_mapper/v2/mix_vs_baked_audit.csv with verdict per SKU.
Also prints a top-line summary.
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import Counter
from pathlib import Path

V2 = Path("/Users/jamiebarton/Desktop/esha_audit_bundle/retail_mapper/v2")
AUDIT = V2 / "full_corpus_audit.csv"
OUT = V2 / "mix_vs_baked_audit.csv"

csv.field_size_limit(sys.maxsize)

# Keyword sets
MIX_TITLE_RX  = re.compile(r"\b(dry mix|mix|powder|powdered|just add|combine with|prepared with)\b", re.I)
BAKED_TITLE_RX = re.compile(r"\b(baked|snack cake|ready to eat|ready[- ]to[- ]eat|fresh baked|hand[- ]baked|fully baked|pre[- ]baked|individually wrapped)\b", re.I)
KIT_TITLE_RX = re.compile(r"\bkit\b|\bcookie house\b|\bgingerbread house\b", re.I)
DOUGH_TITLE_RX = re.compile(r"\b(dough|refrigerated|ready[- ]to[- ]bake|break[- ]&[- ]bake|break[- ]and[- ]bake)\b", re.I)

MIX_BFC = {
    "Cake, Cookie & Cupcake Mixes", "Baking/Cooking Mixes/Supplies",
    "Bread & Muffin Mixes", "Pancake/Waffle Mixes", "Brownie Mixes",
    "Biscuits & Bread Mixes", "Pie Crusts & Fillings",
}
BAKED_BFC = {
    "Cakes, Cupcakes, Snack Cakes", "Cookies & Biscuits", "Bread & Buns",
    "Muffins", "Doughnuts", "Pies", "Pastries",
    "Bagels, Muffins, Doughnuts & Pastries",
}

# Top ingredients suggesting MIX (raw dry-goods first)
MIX_TOP_INGREDIENTS = ("flour", "sugar", "wheat flour", "enriched flour", "cake flour", "baking soda",
                      "baking powder", "leavening", "cornmeal", "cornstarch", "wheat starch")
# Top ingredients suggesting BAKED (wet/processed)
BAKED_TOP_INGREDIENTS = ("eggs", "butter", "oil", "vegetable oil", "canola oil", "soybean oil",
                        "shortening", "milk", "water", "buttermilk", "egg whites")


def classify(title: str, bfc: str, fndds_desc: str, sr28_desc: str, ingredients: str) -> tuple[str, dict]:
    """Returns (verdict, signals_dict). verdict ∈ {'mix','baked','dough','kit','unknown'}."""
    signals = {"title_mix": 0, "title_baked": 0, "title_dough": 0, "title_kit": 0,
               "bfc_mix": 0, "bfc_baked": 0,
               "fndds_mix": 0, "sr28_mix": 0,
               "ing_mix": 0, "ing_baked": 0}
    title_l = (title or "").lower()
    fndds_l = (fndds_desc or "").lower()
    sr28_l = (sr28_desc or "").lower()
    ing_l = (ingredients or "").lower()

    if KIT_TITLE_RX.search(title_l):
        signals["title_kit"] = 1
    if DOUGH_TITLE_RX.search(title_l):
        signals["title_dough"] = 1
    if MIX_TITLE_RX.search(title_l):
        signals["title_mix"] = 1
    if BAKED_TITLE_RX.search(title_l):
        signals["title_baked"] = 1

    if bfc in MIX_BFC: signals["bfc_mix"] = 1
    if bfc in BAKED_BFC: signals["bfc_baked"] = 1

    if "mix" in fndds_l: signals["fndds_mix"] = 1
    if "dry mix" in sr28_l or " mix" in sr28_l: signals["sr28_mix"] = 1

    # Top-3 ingredients check
    if ing_l:
        first_ings = [s.strip() for s in re.split(r"[,;.]", ing_l)[:3]]
        first_str = " ".join(first_ings)
        for kw in MIX_TOP_INGREDIENTS:
            if kw in first_str:
                signals["ing_mix"] += 1
        for kw in BAKED_TOP_INGREDIENTS:
            if kw in first_str:
                signals["ing_baked"] += 1

    # Verdict
    mix_score = (signals["title_mix"] * 2 + signals["bfc_mix"] * 2 +
                 signals["fndds_mix"] + signals["sr28_mix"] + signals["ing_mix"])
    baked_score = (signals["title_baked"] * 2 + signals["bfc_baked"] * 2 + signals["ing_baked"])
    dough_score = signals["title_dough"] * 3
    kit_score = signals["title_kit"] * 3

    scores = {"mix": mix_score, "baked": baked_score, "dough": dough_score, "kit": kit_score}
    top_label = max(scores, key=scores.get)
    if scores[top_label] == 0:
        return "unknown", signals
    return top_label, signals


def main(apply_mode: bool) -> None:
    n_total = 0
    counts = Counter()
    out_rows: list[dict] = []
    flagged_misplaced: list[dict] = []

    with AUDIT.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            cp = (r.get("canonical_path") or "").strip()
            if not (cp.startswith("Pantry > Baking Mixes") or
                    cp.startswith("Bakery > Cookie Dough") or
                    cp.startswith("Bakery > Cookie Kits") or
                    cp.startswith("Bakery > Dough")):
                continue
            n_total += 1
            title = r.get("title", "") or ""
            bfc = r.get("branded_food_category", "") or ""
            fndds_desc = r.get("fndds_desc", "") or ""
            sr28_desc = r.get("sr28_desc", "") or ""
            ingredients = (r.get("ingredients_clean") or r.get("ingredients") or "")
            verdict, signals = classify(title, bfc, fndds_desc, sr28_desc, ingredients)
            counts[(cp.split(" > ")[0] + " > " + cp.split(" > ")[1], verdict)] += 1

            # Flag if verdict contradicts current location
            current_label = "mix" if cp.startswith("Pantry > Baking Mixes") else \
                            "dough" if cp.startswith("Bakery > Cookie Dough") else \
                            "kit" if cp.startswith("Bakery > Cookie Kits") else \
                            "dough" if cp.startswith("Bakery > Dough") else "unknown"
            if verdict != current_label and verdict != "unknown":
                flagged_misplaced.append({
                    "fdc_id": r.get("fdc_id", ""),
                    "title": title[:60],
                    "current_path": cp,
                    "current_label": current_label,
                    "verdict": verdict,
                    "bfc": bfc,
                    "fndds_desc": fndds_desc,
                    "sr28_desc": sr28_desc,
                    "signals": str(signals),
                })

    print(f"  total SKUs in mix/dough/kit trees: {n_total:,}")
    print()
    print(f"  Per current-tree → verdict breakdown:")
    for (tree, verdict), n in sorted(counts.items(), key=lambda x: (-x[1])):
        print(f"    {tree:<30}  verdict={verdict:<10}  {n:>5}")
    print()
    print(f"  Total flagged (verdict ≠ current location): {len(flagged_misplaced):,}")

    if flagged_misplaced:
        cols = ["fdc_id", "title", "current_path", "current_label", "verdict",
                "bfc", "fndds_desc", "sr28_desc", "signals"]
        with OUT.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=cols)
            w.writeheader()
            w.writerows(flagged_misplaced)
        print(f"  wrote {OUT.name}")
        print()
        print("  Top 20 flagged samples:")
        for r in flagged_misplaced[:20]:
            print(f"    fdc={r['fdc_id']} \"{r['title']}\" : {r['current_label']} → {r['verdict']}")
            print(f"      now: {r['current_path']}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--apply", action="store_true")
    args = p.parse_args()
    main(args.apply)
