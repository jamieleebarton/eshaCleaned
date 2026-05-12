#!/usr/bin/env python3
"""A3 — Calorie reconstruction audit.

For each recipe, sum (line_grams × cal_per_g) using Hestia's
ingredient_lookup.json:per_100g.calories. Compare to Hestia's
nutrition[:,0] × servings tensor value for the same recipe_id.

Recipes with reconstructed cal off by >2x have a bug (gram parsing or
ingredient mis-identification). Read-only.

Outputs:
  recipe_pricing/audit_cal_reconstruction.csv — top divergences
"""
from __future__ import annotations
import csv, json, sys
from collections import defaultdict, Counter
from pathlib import Path

import torch

csv.field_size_limit(2**30)
ROOT = Path(__file__).resolve().parents[1]
RECIPES = ROOT / "recipe_mapper" / "v1" / "output" / "recipes_unified.csv"
ILU_PATH = Path("/Users/jamiebarton/Desktop/Hestia/api/data/ingredient_lookup.json")
TENSOR_PATH = Path("/Users/jamiebarton/Desktop/Hestia/api/data/tensor_cache/recipe_db_tensors.pt")
OUT = ROOT / "recipe_pricing" / "audit_cal_reconstruction.csv"


def main():
    print("loading ingredient_lookup…", file=sys.stderr)
    ilu = json.loads(ILU_PATH.read_text())
    # ingredient → cal_per_g
    cal_per_g: dict[str, float] = {}
    for k, v in ilu.items():
        p = v.get("per_100g") or {}
        c = p.get("calories")
        if c is not None:
            cal_per_g[k.lower().strip()] = float(c) / 100.0
    print(f"  {len(cal_per_g):,} ingredients with cal/g", file=sys.stderr)

    print("loading Hestia recipe tensors…", file=sys.stderr)
    cached = torch.load(str(TENSOR_PATH), map_location="cpu", weights_only=False)
    rids = cached["recipe_ids"].tolist()       # int recipe IDs
    nutr = cached["nutrition"]                  # [N, 4]: cal/serv, prot, carbs, fat
    serv = cached["servings"]                   # [N]
    rid_to_idx = {int(r): i for i, r in enumerate(rids)}
    print(f"  {len(rids):,} recipes in Hestia tensor", file=sys.stderr)

    # Aggregate per recipe: sum line_grams * cal/g; track misses
    per_recipe: dict[str, dict] = defaultdict(
        lambda: {"our_cal": 0.0, "missing": 0, "n_lines": 0,
                  "top_contrib": [],  "name": ""})

    rows_seen = 0
    with RECIPES.open() as f:
        r = csv.DictReader(f)
        for row in r:
            rows_seen += 1
            if rows_seen % 500_000 == 0:
                print(f"  {rows_seen:,} lines processed", file=sys.stderr)
            rid = row.get("recipe_id","")
            if not rid: continue
            d = per_recipe[rid]
            d["name"] = row.get("recipe_title","")
            d["n_lines"] += 1
            ing = (row.get("ingredient_item") or "").lower().strip()
            try: g = float(row.get("grams_resolved") or 0)
            except: g = 0
            if not ing or g <= 0:
                if g <= 0 and ing:
                    d["missing"] += 1
                continue
            cpg = cal_per_g.get(ing)
            if cpg is None:
                d["missing"] += 1
                continue
            cal = g * cpg
            d["our_cal"] += cal
            if len(d["top_contrib"]) < 3 or any(cal > c[1] for c in d["top_contrib"]):
                d["top_contrib"].append((ing, cal))
                d["top_contrib"].sort(key=lambda x: -x[1])
                d["top_contrib"] = d["top_contrib"][:3]

    # Compute deltas
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
        out_rows.append({
            "recipe_id": rid,
            "name": d["name"][:60],
            "n_lines": d["n_lines"],
            "missing_lines": d["missing"],
            "our_cal": round(our, 0),
            "hes_total_cal": round(hes_total, 0),
            "ratio": round(ratio, 2),
            "top3": "|".join(f"{i}:{c:.0f}cal" for i, c in d["top_contrib"]),
            "flags": ",".join(flags),
        })

    # Print flag summary
    print(f"\nFlag distribution:", file=sys.stderr)
    for f, n in flag_counts.most_common():
        print(f"  {f:<25}  {n:>7,}", file=sys.stderr)

    # Sort by absolute distance from 1.0 (most divergent first)
    out_rows.sort(key=lambda r: -abs(r["ratio"] - 1.0) * (r["hes_total_cal"] / 1000.0))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    if out_rows:
        with OUT.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(out_rows[0].keys()))
            w.writeheader()
            for r in out_rows[:200]: w.writerow(r)

    print(f"\n→ {OUT}  ({len(out_rows[:200])} flagged recipes, sorted by impact)",
          file=sys.stderr)


if __name__ == "__main__":
    main()
