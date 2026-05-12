#!/usr/bin/env python3
"""A4 — Food-group attribution audit.

Hestia tags each recipe with a 7-element food_groups vector:
  0=vegetables, 1=fruits, 2=grains, 3=dairy, 4=protein_foods, 5=fats, 6=other

For each recipe, we roll up our htc-coded ingredient grams into the same 7
buckets using a simple HTC-prefix → group mapping, then compare dominant
group + L1 distance vs Hestia's vector.

Read-only.

Outputs:
  recipe_pricing/audit_food_groups.csv — top divergences
"""
from __future__ import annotations
import csv, json, sys
from collections import defaultdict, Counter
from pathlib import Path

import torch

csv.field_size_limit(2**30)
ROOT = Path(__file__).resolve().parents[1]
RECIPES = ROOT / "recipe_mapper" / "v1" / "output" / "recipes_unified.csv"
TENSOR_PATH = Path("/Users/jamiebarton/Desktop/Hestia/api/data/tensor_cache/recipe_db_tensors.pt")
OUT = ROOT / "recipe_pricing" / "audit_food_groups.csv"

GROUP_NAMES = ["vegetables", "fruits", "grains", "dairy", "protein", "fats", "other"]

# HTC code first-2-digit prefix → food group index
# HTC bucket 1=dairy, 2=meat&seafood, 3=eggs/legumes, 4=nuts/seeds,
# 5=grains, 6=vegetables, 7=fruits, 8=fats, 9=condiments
HTC_GROUP_MAP = {
    # Dairy / eggs cross-mapping
    "10": 3,   "11": 3,   "12": 3,   "13": 3,   "14": 3,   # dairy
    "15": 4,   "16": 4,                                      # eggs
    # Meat & Seafood / Legumes / Nuts → protein
    "20": 4,   "21": 4,   "22": 4,   "23": 4,   "24": 4,
    "25": 4,   "26": 4,   "27": 4,                            # meat
    "30": 4,   "31": 4,   "32": 4,                            # eggs/legumes
    "33": 4,   "34": 4,                                       # legumes
    "40": 4,   "41": 4,   "42": 4,                            # legumes
    "43": 4,   "44": 4,                                       # nuts/seeds
    # Grains
    "50": 2,   "51": 2,   "52": 2,   "53": 2,   "54": 2,
    "55": 2,   "56": 2,   "57": 2,   "58": 2,
    # Vegetables / Fruits
    "60": 0,   "61": 0,   "62": 0,   "63": 0,   "64": 0,
    "65": 0,   "66": 0,   "67": 0,   "68": 0,   "69": 0,
    "70": 0,   "71": 0,   "72": 0,   "73": 0,   "74": 0,
    "75": 0,   "76": 0,   "77": 0,   "78": 0,
    "60": 1,   "61": 1,   "62": 1,   "63": 1,                  # actually fruits in many systems
    # Fats / oils
    "80": 5,   "81": 5,   "82": 5,   "83": 5,   "84": 5,   "85": 5,
    # Sugar/condiments → other
    "90": 6,   "91": 6,   "92": 6,   "93": 6,   "94": 6,
    "95": 6,   "96": 6,   "97": 6,   "98": 6,   "99": 6,
}


def htc_to_group(htc: str) -> int | None:
    if not htc or len(htc) < 2: return None
    return HTC_GROUP_MAP.get(htc[:2])


def main():
    print("loading Hestia tensors…", file=sys.stderr)
    cached = torch.load(str(TENSOR_PATH), map_location="cpu", weights_only=False)
    rids = cached["recipe_ids"].tolist()
    fg = cached["food_groups"]            # [N, 7]
    rid_to_idx = {int(r): i for i, r in enumerate(rids)}
    print(f"  {len(rids):,} recipes; food_groups shape {tuple(fg.shape)}", file=sys.stderr)

    # Aggregate our group vectors per recipe: grams summed by group bucket
    our_groups: dict[str, list] = defaultdict(lambda: [0.0]*7)
    title: dict[str, str] = {}

    rows_seen = 0
    with RECIPES.open() as f:
        r = csv.DictReader(f)
        for row in r:
            rows_seen += 1
            if rows_seen % 500_000 == 0:
                print(f"  {rows_seen:,} lines processed", file=sys.stderr)
            rid = row.get("recipe_id","")
            if not rid: continue
            try: g = float(row.get("grams_resolved") or 0)
            except: g = 0
            if g <= 0: continue
            htc = (row.get("htc_code") or "").strip()
            grp = htc_to_group(htc)
            if grp is None: continue
            our_groups[rid][grp] += g
            if rid not in title:
                title[rid] = row.get("recipe_title","")[:60]

    # Compare per-recipe to Hestia
    out_rows = []
    agree = 0; total = 0
    for rid, vec in our_groups.items():
        try: rid_int = int(rid)
        except: continue
        idx = rid_to_idx.get(rid_int)
        if idx is None: continue
        total += 1
        # Normalize ours to match Hestia's scale (Hestia is fractional 0..1 typically)
        our_sum = sum(vec) or 1.0
        our_norm = [v/our_sum for v in vec]
        hes_vec = fg[idx].tolist()
        hes_sum = sum(hes_vec) or 1.0
        hes_norm = [v/hes_sum for v in hes_vec]
        our_dom = max(range(7), key=lambda i: our_norm[i])
        hes_dom = max(range(7), key=lambda i: hes_norm[i])
        if our_dom == hes_dom: agree += 1
        l1 = sum(abs(o-h) for o, h in zip(our_norm, hes_norm))
        if our_dom != hes_dom or l1 > 0.5:
            out_rows.append({
                "recipe_id": rid,
                "name": title.get(rid, ""),
                "our_dominant": GROUP_NAMES[our_dom],
                "hes_dominant": GROUP_NAMES[hes_dom],
                "l1_distance": round(l1, 2),
                "our_vec": "|".join(f"{GROUP_NAMES[i]}:{v:.2f}" for i, v in enumerate(our_norm) if v >= 0.05),
                "hes_vec": "|".join(f"{GROUP_NAMES[i]}:{v:.2f}" for i, v in enumerate(hes_norm) if v >= 0.05),
            })

    pct_agree = agree / max(1, total) * 100
    print(f"\nrecipes compared: {total:,}", file=sys.stderr)
    print(f"dominant-group agreement: {agree:,}  ({pct_agree:.1f}%)", file=sys.stderr)

    out_rows.sort(key=lambda r: -r["l1_distance"])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    if out_rows:
        with OUT.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(out_rows[0].keys()))
            w.writeheader()
            for r in out_rows[:500]: w.writerow(r)

    print(f"\n→ {OUT}  ({len(out_rows[:500])} divergent recipes, sorted by L1 distance)",
          file=sys.stderr)


if __name__ == "__main__":
    main()
