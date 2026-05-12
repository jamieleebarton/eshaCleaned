#!/usr/bin/env python3
"""A4 v2 — Food-group attribution using exact Hestia FNDDS-prefix mapping.

Replaces v1's guessed HTC-prefix mapping with the canonical FNDDS-prefix
mapping from Hestia's layer0_fix_prefixes.py:

  Dairy:      11, 12, 13, 14
  Protein:    20-28, 31-34, 41-43
  Grains:     50-59
  Fruits:     61-67
  Vegetables: 71-78
  Fats:       81, 82, 83, 89
  Other:      91-95, 99

Group order matches Hestia's tensor: 0=veg, 1=fruits, 2=grains, 3=dairy,
4=protein, 5=fats, 6=other.

Per-line FNDDS source (in priority order):
  1. hestia_fndds from FULL_v5 line CSV (Hestia's per-recipe attribution)
  2. ingredient_lookup.json[ingredient_item].fndds_code (Hestia's name map)

Read-only.

Outputs:
  recipe_pricing/audit_food_groups_v2.csv — top divergent recipes
"""
from __future__ import annotations
import csv, json, sys
from collections import defaultdict, Counter
from pathlib import Path

import torch

csv.field_size_limit(2**30)
ROOT = Path(__file__).resolve().parents[1]
LINES = ROOT / "planner" / "data" / "recipe_line_comparison_FULL_v6.csv"
ILU_PATH = Path("/Users/jamiebarton/Desktop/Hestia/api/data/ingredient_lookup.json")
TENSOR_PATH = Path("/Users/jamiebarton/Desktop/Hestia/api/data/tensor_cache/recipe_db_tensors.pt")
OUT = ROOT / "recipe_pricing" / "audit_food_groups_v2.csv"

# Food group index in Hestia's tensor (col order)
GROUP_NAMES = ["vegetables", "fruits", "grains", "dairy", "protein", "fats", "other"]

# FNDDS 2-digit prefix → group index
PREFIX_TO_GROUP: dict[str, int] = {}
for p in ("11", "12", "13", "14"):                                       PREFIX_TO_GROUP[p] = 3   # dairy
for p in ("20", "21", "22", "23", "24", "25", "26", "27", "28",
           "31", "32", "33", "34", "41", "42", "43"):                     PREFIX_TO_GROUP[p] = 4   # protein
for p in ("50","51","52","53","54","55","56","57","58","59"):             PREFIX_TO_GROUP[p] = 2   # grains
for p in ("61","62","63","64","65","66","67"):                            PREFIX_TO_GROUP[p] = 1   # fruits
for p in ("71","72","73","74","75","76","77","78"):                       PREFIX_TO_GROUP[p] = 0   # vegetables
for p in ("81","82","83","89"):                                           PREFIX_TO_GROUP[p] = 5   # fats
for p in ("91","92","93","94","95","99"):                                 PREFIX_TO_GROUP[p] = 6   # other


def fndds_to_group_idx(code: str) -> int | None:
    if not code or len(code) < 2: return None
    return PREFIX_TO_GROUP.get(code[:2])


def main():
    print("loading ingredient_lookup (fallback for missing hestia_fndds)…", file=sys.stderr)
    ilu = json.loads(ILU_PATH.read_text())
    name_to_fndds: dict[str, str] = {}
    for k, v in ilu.items():
        f = (v.get("fndds_code") or "").strip()
        if f:
            name_to_fndds[k.lower().strip()] = f
    print(f"  {len(name_to_fndds):,} ingredient → fndds mappings", file=sys.stderr)

    print("loading Hestia recipe tensors…", file=sys.stderr)
    cached = torch.load(str(TENSOR_PATH), map_location="cpu", weights_only=False)
    rids = cached["recipe_ids"].tolist()
    fg = cached["food_groups"]            # [N, 7] gram totals per group
    rid_to_idx = {int(r): i for i, r in enumerate(rids)}

    # Aggregate our group vectors
    our_groups: dict[str, list] = defaultdict(lambda: [0.0]*7)
    title: dict[str, str] = {}
    n_have_hes = 0; n_have_lookup = 0; n_no_fndds = 0; n_unknown_prefix = 0

    rows_seen = 0
    with LINES.open() as f:
        r = csv.DictReader(f)
        for row in r:
            rows_seen += 1
            if rows_seen % 500_000 == 0:
                print(f"  {rows_seen:,} lines processed", file=sys.stderr)
            rid = row.get("recipe_id","")
            if not rid: continue
            try: g = float(row.get("our_grams") or 0)
            except: g = 0
            if g <= 0: continue
            # 1) hestia_fndds
            fn = (row.get("hestia_fndds") or "").strip()
            if fn and fn != "0":
                n_have_hes += 1
            else:
                # 2) ingredient_lookup fallback
                ing = (row.get("ingredient_text") or "").lower().strip()
                ing_first = ing.split(",")[0].strip()
                fn = name_to_fndds.get(ing) or name_to_fndds.get(ing_first) or ""
                if fn:
                    n_have_lookup += 1
                else:
                    n_no_fndds += 1
                    continue
            grp = fndds_to_group_idx(fn)
            if grp is None:
                n_unknown_prefix += 1
                continue
            our_groups[rid][grp] += g
            if rid not in title:
                title[rid] = row.get("recipe_name","")[:60]

    print(f"\nLine-level FNDDS source:", file=sys.stderr)
    print(f"  via hestia_fndds:          {n_have_hes:,}", file=sys.stderr)
    print(f"  via ingredient_lookup:     {n_have_lookup:,}", file=sys.stderr)
    print(f"  no fndds (skipped):        {n_no_fndds:,}", file=sys.stderr)
    print(f"  unknown prefix (skipped):  {n_unknown_prefix:,}", file=sys.stderr)

    # Compare to Hestia
    out_rows = []
    agree = 0; total = 0
    for rid, vec in our_groups.items():
        try: rid_int = int(rid)
        except: continue
        idx = rid_to_idx.get(rid_int)
        if idx is None: continue
        total += 1
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
    print(f"\n→ {OUT}  ({len(out_rows[:500])} divergent recipes)", file=sys.stderr)


if __name__ == "__main__":
    main()
