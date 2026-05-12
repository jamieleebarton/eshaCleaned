#!/usr/bin/env python3
"""R8a — Package-overshoot audit for meat/produce lines.

For each picked-recipe line where the planner buys multiple packages to
cover the recipe's gram need (e.g., 1 head iceberg = 539g, pack = 454g,
ceil(539/454) = 2 packs = 908g), flag when:

  total_purchased_g / grams_needed > 1.5

(i.e., we bought 1.5x or more of what the recipe asked for).

Then check if the same canonical_path has a SKU whose pack_size >=
grams_needed AND total_spend is lower than the multi-pack option.

Restricted to Meat & Seafood / Produce paths per user direction (other
categories like spices/oils have unavoidable overshoot due to small
recipe needs vs minimum pack sizes).

Outputs:
  recipe_pricing/audit_pack_overshoot.csv  — overshoot lines + alternative SKU suggestions
"""
from __future__ import annotations
import csv, json, math, sys
from collections import Counter
from pathlib import Path

csv.field_size_limit(2**30)
ROOT = Path(__file__).resolve().parents[1]
PICKED = Path("/tmp/multi_week_ours_12w_round7.json")
RCG = ROOT / "planner" / "data" / "recipe_concept_grams.json"
CR = ROOT / "planner" / "data" / "concept_resolution.json"
CI = ROOT / "planner" / "data" / "concept_index.json"
OUT = ROOT / "recipe_pricing" / "audit_pack_overshoot.csv"

OVERSHOOT_THRESHOLD = 1.5  # purchased / needed > this triggers flag
TARGET_TOP_PREFIXES = ("Meat & Seafood", "Produce", "Frozen > Vegetables",
                        "Frozen > Frozen Fruit", "Bakery > Bread")


def total_spend(grams_needed: float, sku_g: float, sku_c: int):
    if not sku_g or sku_g <= 0: return (0, 10**12)
    if grams_needed <= 0: return (1, sku_c)
    n = max(1, math.ceil(grams_needed / sku_g))
    return (n, n * sku_c)


def main():
    pj = json.loads(PICKED.read_text())
    picked: set = set()
    for w in pj.get("weeks", []):
        for x in w.get("recipe_ids") or []:
            picked.add(str(x))
    print(f"loaded {len(picked):,} picked recipe IDs", file=sys.stderr)

    rcg = json.loads(RCG.read_text())["concept_grams"]
    cr = json.loads(CR.read_text())
    ci = json.loads(CI.read_text())
    print(f"concept data loaded", file=sys.stderr)

    out_rows = []
    n_overshoot = 0
    n_better_alt = 0

    for rid in picked:
        cg = rcg.get(rid, {})
        for ck, grams in cg.items():
            cp, _ = ck.split("|", 1) if "|" in ck else (ck, "")
            if not any(cp.startswith(p) for p in TARGET_TOP_PREFIXES):
                continue
            res = cr.get(ck, {})
            priced_key = res.get("priced_key")
            if not priced_key: continue
            concept = ci.get(priced_key, {})
            packages = concept.get("packages", []) or []
            if not packages: continue

            # Find planner's actual pick (cheapest by total_spend at this gram need)
            best = None; best_spend = 10**12
            for p in packages:
                n_p, spend = total_spend(grams, p.get("grams", 0), p.get("cents", 0))
                if spend < best_spend:
                    best_spend = spend; best = (p, n_p, spend)
            if not best: continue
            pick, pick_n_packs, pick_spend = best
            purchased_g = pick_n_packs * pick.get("grams", 0)
            if grams <= 0: continue
            ratio = purchased_g / grams
            if ratio < OVERSHOOT_THRESHOLD: continue
            n_overshoot += 1

            # Find alternative: a single-pack SKU whose pack_size >= grams
            single_alts = []
            for p in packages:
                if p.get("grams", 0) >= grams:
                    single_alts.append(p)
            single_alts.sort(key=lambda p: p.get("cents", 0))
            alt = single_alts[0] if single_alts else None
            alt_better = False
            alt_str = ""
            if alt and alt.get("cents", 0) < pick_spend:
                alt_better = True
                n_better_alt += 1
                alt_str = f"{alt['name'][:50]} ({alt['grams']:.0f}g, ${alt['cents']/100:.2f})"

            out_rows.append({
                "recipe_id": rid,
                "canonical_path": cp,
                "grams_needed": round(grams, 0),
                "picked_sku": pick.get("name", "")[:60],
                "pack_size": pick.get("grams", 0),
                "n_packs": pick_n_packs,
                "purchased_g": purchased_g,
                "spend_$": round(pick_spend / 100, 2),
                "overshoot_ratio": round(ratio, 2),
                "single_pack_alt": alt_str,
                "alt_is_cheaper": int(alt_better),
            })

    out_rows.sort(key=lambda r: -r["overshoot_ratio"])

    OUT.parent.mkdir(parents=True, exist_ok=True)
    if out_rows:
        with OUT.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(out_rows[0].keys()))
            w.writeheader()
            for r in out_rows: w.writerow(r)

    print(f"\noverShoot lines: {n_overshoot:,}", file=sys.stderr)
    print(f"  single-pack alternative AVAILABLE and CHEAPER: {n_better_alt:,}", file=sys.stderr)
    print(f"\n=== Top 15 overshoot picks ===", file=sys.stderr)
    for r in out_rows[:15]:
        flag = " ⚠ better-alt" if r["alt_is_cheaper"] else ""
        print(f"  rid={r['recipe_id']:>6}  {r['canonical_path'][:35]:<35}  "
              f"need={r['grams_needed']:>5.0f}g  buy={r['n_packs']}×{r['pack_size']:.0f}g="
              f"{r['purchased_g']:.0f}g (ratio={r['overshoot_ratio']:.2f}){flag}",
              file=sys.stderr)
    print(f"\n→ {OUT}", file=sys.stderr)


if __name__ == "__main__":
    main()
