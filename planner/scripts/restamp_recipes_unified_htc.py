#!/usr/bin/env python3
"""Re-stamp recipes_unified.csv ingredient lines with fresh HTC codes.

Reads recipe_ingredient_taxonomy_v2.csv (which has the corrected canonical_path
per ingredient title) and re-encodes each title through the live encoder so the
htc_code column reflects the current canonical_path, not whatever stale code
the original recipes_unified shipped with.

Output: recipes_unified.htc_fixed.csv (same shape as recipes_unified.csv)
"""
from __future__ import annotations
import csv, json, sys, shutil
from pathlib import Path

csv.field_size_limit(sys.maxsize)
sys.path.insert(0, "/Users/jamiebarton/Desktop/esha_audit_bundle")
from recipe_mapper.v1.htc.encoder import encode

ROOT = Path("/Users/jamiebarton/Desktop/esha_audit_bundle")
V2 = ROOT / "recipe_mapper" / "v1" / "output" / "recipe_ingredient_taxonomy_v2.csv"
UNIFIED = ROOT / "recipe_mapper" / "v1" / "output" / "recipes_unified.csv"
OUT = ROOT / "recipe_mapper" / "v1" / "output" / "recipes_unified.htc_fixed.csv"


def main():
    print("encoding fresh htc per ingredient title from v2 taxonomy…", file=sys.stderr)
    title_to_htc: dict[str, str] = {}
    title_to_path: dict[str, str] = {}
    title_to_pif: dict[str, str] = {}
    with V2.open() as f:
        for row in csv.DictReader(f):
            title = (row.get("title") or "").strip().lower()
            cp    = (row.get("canonical_path") or "").strip()
            pif   = (row.get("product_identity_fixed") or "").strip()
            if not title: continue
            h = encode("", description=title, food_name=pif,
                         canonical_path=cp, identity_mode=False)
            title_to_htc[title] = h.code
            title_to_path[title] = cp
            title_to_pif[title] = pif
    print(f"  {len(title_to_htc):,} fresh htc codes", file=sys.stderr)

    print(f"\nre-stamping {UNIFIED.name}…", file=sys.stderr)
    n_total = 0
    n_changed = 0
    n_unmatched = 0
    with UNIFIED.open() as fin, OUT.open("w", newline="") as fout:
        rd = csv.DictReader(fin)
        wr = csv.DictWriter(fout, fieldnames=rd.fieldnames)
        wr.writeheader()
        for row in rd:
            n_total += 1
            old = (row.get("htc_code") or "").strip().lstrip("~")
            item_key = (row.get("ingredient_item") or "").strip().lower()
            new = title_to_htc.get(item_key)
            if new is None:
                n_unmatched += 1
            else:
                if new != old:
                    n_changed += 1
                row["htc_code"] = new
            wr.writerow(row)
            if n_total % 500_000 == 0:
                print(f"  {n_total:,} lines processed", file=sys.stderr)

    print(f"\nfinished re-stamping:", file=sys.stderr)
    print(f"  total lines:           {n_total:,}", file=sys.stderr)
    print(f"  htc changed:           {n_changed:,}  ({n_changed/n_total*100:.1f}%)", file=sys.stderr)
    print(f"  ingredient title unmatched in v2 taxonomy: {n_unmatched:,}", file=sys.stderr)
    print(f"  → {OUT}", file=sys.stderr)


if __name__ == "__main__":
    main()
