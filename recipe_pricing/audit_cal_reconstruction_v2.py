#!/usr/bin/env python3
"""A3 v2 — Calorie reconstruction using OUR fndds_nutrient_lookup.csv.

The v1 audit used Hestia's narrow `ingredient_lookup.json` (2,500 entries,
name-keyed) and saw 8.3% of lines missing nutrition. We have our own
fndds_nutrient_lookup.csv with 11,924 FNDDS codes and full energy_kcal data.

This v2 looks up cal via Hestia's hestia_fndds attribution per line (which
A5 confirmed is 99% family-correct), against our FNDDS nutrient table.

Inputs:
  planner/data/recipe_line_comparison_FULL_v5.csv  — line-level data with
                                                      our_grams + hestia_fndds
  data/fndds/fndds_nutrient_lookup.csv             — FNDDS → energy_kcal/100g

Tensor:
  Hestia's recipe_db_tensors.pt nutrition[:,0] × servings = total recipe cal.

Outputs:
  recipe_pricing/audit_cal_reconstruction_v2.csv — top divergences
"""
from __future__ import annotations
import csv, sys
from collections import defaultdict, Counter
from pathlib import Path

import torch

csv.field_size_limit(2**30)
ROOT = Path(__file__).resolve().parents[1]
LINES = ROOT / "planner" / "data" / "recipe_line_comparison_FULL_v5.csv"
FNDDS = ROOT / "data" / "fndds" / "fndds_nutrient_lookup.csv"
TENSOR_PATH = Path("/Users/jamiebarton/Desktop/Hestia/api/data/tensor_cache/recipe_db_tensors.pt")
OUT = ROOT / "recipe_pricing" / "audit_cal_reconstruction_v2.csv"


def main():
    print("loading FNDDS nutrient lookup…", file=sys.stderr)
    fndds_kcal: dict[str, float] = {}
    with FNDDS.open() as f:
        r = csv.DictReader(f)
        for row in r:
            code = (row.get("fndds_code") or "").strip()
            try: kcal = float(row.get("energy_kcal") or 0)
            except: kcal = 0
            if code and kcal > 0:
                fndds_kcal[code] = kcal
    print(f"  {len(fndds_kcal):,} FNDDS codes with energy_kcal", file=sys.stderr)

    print("loading Hestia recipe tensors…", file=sys.stderr)
    cached = torch.load(str(TENSOR_PATH), map_location="cpu", weights_only=False)
    rids = cached["recipe_ids"].tolist()
    nutr = cached["nutrition"]
    serv = cached["servings"]
    rid_to_idx = {int(r): i for i, r in enumerate(rids)}

    # Aggregate per recipe: sum line.grams * fndds_kcal/100 (our_grams + hestia_fndds)
    per_recipe: dict[str, dict] = defaultdict(
        lambda: {"our_cal": 0.0, "missing": 0, "n_lines": 0,
                  "name": "", "top_contrib": []})

    rows_seen = 0
    with LINES.open() as f:
        r = csv.DictReader(f)
        for row in r:
            rows_seen += 1
            if rows_seen % 500_000 == 0:
                print(f"  {rows_seen:,} lines processed", file=sys.stderr)
            rid = row.get("recipe_id","")
            if not rid: continue
            d = per_recipe[rid]
            d["name"] = row.get("recipe_name","")
            d["n_lines"] += 1
            try: g = float(row.get("our_grams") or 0)
            except: g = 0
            if g <= 0: continue
            fn = (row.get("hestia_fndds") or "").strip()
            kcal_per_100 = fndds_kcal.get(fn)
            if kcal_per_100 is None:
                d["missing"] += 1
                continue
            cal = g * kcal_per_100 / 100.0
            d["our_cal"] += cal
            d["top_contrib"].append(((row.get("fndds_desc") or fn)[:30], cal))

    out_rows = []
    flag_counts: Counter = Counter()
    for rid, d in per_recipe.items():
        try: rid_int = int(rid)
        except: continue
        idx = rid_to_idx.get(rid_int)
        if idx is None:
            flag_counts["NOT_IN_HESTIA"] += 1
            continue
        servings = float(serv[idx].item()) or 4.0
        hes_total = float(nutr[idx, 0].item()) * servings
        if hes_total <= 0:
            flag_counts["HESTIA_NO_CAL"] += 1
            continue
        our = d["our_cal"]
        flags = []
        if d["missing"] > 5: flags.append("LINES_MISSING_NUTRITION")
        if our <= 0:
            flags.append("OUR_NO_CAL")
            ratio = 0.0
        else:
            ratio = our / hes_total
            if ratio > 2.0: flags.append("OFF_2X_HIGH")
            elif ratio < 0.5: flags.append("OFF_2X_LOW")
        for fl in flags: flag_counts[fl] += 1
        if not flags: continue
        d["top_contrib"].sort(key=lambda x: -x[1])
        out_rows.append({
            "recipe_id": rid,
            "name": d["name"][:60],
            "n_lines": d["n_lines"],
            "missing_lines": d["missing"],
            "our_cal": round(our, 0),
            "hes_total_cal": round(hes_total, 0),
            "ratio": round(ratio, 2),
            "top3": "|".join(f"{i}:{c:.0f}cal" for i, c in d["top_contrib"][:3]),
            "flags": ",".join(flags),
        })

    print(f"\nFlag distribution (audit v2 with our FNDDS lookup):", file=sys.stderr)
    total_recipes = len(per_recipe)
    for f, n in flag_counts.most_common():
        print(f"  {f:<25}  {n:>7,}  ({n*100/max(1,total_recipes):>5.1f}%)", file=sys.stderr)

    # Compute overall miss rate
    total_lines = sum(d["n_lines"] for d in per_recipe.values())
    total_missing = sum(d["missing"] for d in per_recipe.values())
    print(f"\nLine-level nutrition coverage:", file=sys.stderr)
    print(f"  total lines:    {total_lines:,}", file=sys.stderr)
    print(f"  missing lookup: {total_missing:,}  ({total_missing*100/max(1,total_lines):.1f}%)",
          file=sys.stderr)

    out_rows.sort(key=lambda r: -abs(r["ratio"] - 1.0) * (r["hes_total_cal"] / 1000.0))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    if out_rows:
        with OUT.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(out_rows[0].keys()))
            w.writeheader()
            for r in out_rows[:200]: w.writerow(r)
    print(f"\n→ {OUT}", file=sys.stderr)


if __name__ == "__main__":
    main()
