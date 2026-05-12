#!/usr/bin/env python3
"""Find unit-parser failures in recipes_unified.csv.

Heuristics:
  1. grams_resolved ≥ 5000g for a single ingredient line that's NOT a soup/stock/water/marinade
  2. grams_resolved ≤ 5g for a 1+ lb / 1+ kg quantity
  3. qty in display includes 'lb', 'pound', 'kg' but grams_resolved < 50g
  4. ingredient mentions 'whole [animal]' (whole chicken/ham/turkey) but grams < 800g

Output: grams_audit.csv ranked by severity.
"""
from __future__ import annotations
import csv, re, sys
from pathlib import Path

csv.field_size_limit(2**30)
ROOT = Path("/Users/jamiebarton/Desktop/esha_audit_bundle")
UNIFIED = ROOT / "recipe_mapper" / "v1" / "output" / "recipes_unified.csv"
OUT = ROOT / "recipe_pricing" / "grams_audit.csv"

# Soups/stews can be huge — exempt
SOUP_HINTS = ("soup","stew","broth","stock","water","marinade","brine")

LB_RE = re.compile(r"\b(\d+(?:\.\d+)?(?:[\s\-]*(?:to|\-)[\s\-]*\d+(?:\.\d+)?)?)\s*(?:lb|lbs|pound|pounds)\b", re.I)
KG_RE = re.compile(r"\b(\d+(?:\.\d+)?)\s*(?:kg|kgs|kilogram)", re.I)
WHOLE_ANIMAL_RE = re.compile(r"\bwhole\s+(ham|chicken|turkey|duck|goose|fish|salmon|trout|lamb|beef|brisket)\b", re.I)


def main():
    print("scanning recipes_unified for grams anomalies…", file=sys.stderr)
    bugs = []
    n_lines = 0
    with UNIFIED.open() as f:
        for row in csv.DictReader(f):
            n_lines += 1
            disp = (row.get("display") or "")
            disp_l = disp.lower()
            try: g = float(row.get("grams_resolved") or 0)
            except: continue
            if g <= 0: continue
            try: gb = float(row.get("grams_blob") or 0)
            except: gb = 0
            try: qty = float(row.get("qty") or 0)
            except: qty = 0
            unit = (row.get("unit") or "").strip()
            rid = row.get("recipe_id","")

            # Skip soups/stocks
            if any(h in disp_l for h in SOUP_HINTS): continue

            # Bug class 1: insanely high grams (≥5kg) for a non-soup line
            if g >= 5000:
                bugs.append({
                    "kind": "too_high",
                    "rid": rid, "display": disp[:80],
                    "qty": qty, "unit": unit,
                    "grams_resolved": g, "grams_blob": gb,
                    "ratio": round(g / max(1, gb), 2) if gb else None,
                })
                continue

            # Bug class 2: lb/kg in display but grams_resolved < 50
            lb_m = LB_RE.search(disp_l)
            if lb_m and g < 50:
                bugs.append({
                    "kind": "lb_underflow",
                    "rid": rid, "display": disp[:80],
                    "qty": qty, "unit": unit,
                    "grams_resolved": g, "grams_blob": gb,
                    "lb_match": lb_m.group(0),
                })
                continue
            kg_m = KG_RE.search(disp_l)
            if kg_m and g < 50:
                bugs.append({
                    "kind": "kg_underflow",
                    "rid": rid, "display": disp[:80],
                    "qty": qty, "unit": unit,
                    "grams_resolved": g, "grams_blob": gb,
                    "kg_match": kg_m.group(0),
                })
                continue

            # Bug class 3: whole animal but grams < 800
            wm = WHOLE_ANIMAL_RE.search(disp_l)
            if wm and g < 800:
                bugs.append({
                    "kind": "whole_animal_underflow",
                    "rid": rid, "display": disp[:80],
                    "qty": qty, "unit": unit,
                    "grams_resolved": g,
                    "animal": wm.group(1),
                })

    print(f"\nscanned {n_lines:,} ingredient lines; {len(bugs):,} suspect", file=sys.stderr)
    by_kind = {}
    for b in bugs: by_kind[b["kind"]] = by_kind.get(b["kind"], 0) + 1
    for k, n in by_kind.items(): print(f"  {k:<26} {n:>5,}", file=sys.stderr)

    # Sort: too_high by ratio descending, then lb_underflow by lb amount
    bugs.sort(key=lambda b: -b.get("grams_resolved", 0))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="") as f:
        cols = ["kind","rid","display","qty","unit","grams_resolved","grams_blob",
                 "ratio","lb_match","kg_match","animal"]
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for b in bugs:
            w.writerow({k: b.get(k, "") for k in cols})
    print(f"  → {OUT}", file=sys.stderr)

    print(f"\n=== Top 20 by severity (grams_resolved DESC, too_high cases) ===", file=sys.stderr)
    too_high = [b for b in bugs if b["kind"] == "too_high"]
    for b in too_high[:20]:
        print(f"  rid={b['rid']:<7} g={b['grams_resolved']:>7.0f}g (gb={b['grams_blob']:.0f}, ratio={b['ratio']})  "
              f"qty={b['qty']} unit={b['unit']!r}  {b['display'][:55]}", file=sys.stderr)

    print(f"\n=== Top 10 lb_underflow ===", file=sys.stderr)
    lbu = [b for b in bugs if b["kind"] == "lb_underflow"]
    for b in lbu[:10]:
        print(f"  rid={b['rid']:<7} g={b['grams_resolved']:.1f}g  qty={b['qty']} unit={b['unit']!r}  "
              f"matched={b['lb_match']!r}  {b['display'][:50]}", file=sys.stderr)


if __name__ == "__main__":
    main()
