#!/usr/bin/env python3
"""Audit: same canonical_path → multiple htc_codes (encoder non-determinism).

Per HTC_SPEC, products at the same canonical_path should share an htc_code
identity (positions 1-4 = group/family/food_slot must match). When they
don't, it's because positions 5-7 (form/processing/ptype) got populated
differently across SKUs at the same path.

Outputs CSV ranked by # of distinct codes per path. Surfaces what tokens
in product names/modifiers caused the different codes — guides the next
CLAIMS_TOKENS extension in food_slots.py.
"""
from __future__ import annotations
import csv, sqlite3, sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path("/Users/jamiebarton/Desktop/esha_audit_bundle")
DB   = ROOT / "recipe_pricing" / "data" / "priced_products_v2.db"
OUT  = ROOT / "recipe_pricing" / "htc_determinism_audit.csv"


def main():
    con = sqlite3.connect(str(DB))
    cur = con.cursor()
    cur.execute("""SELECT consensus_canonical, REPLACE(htc_code,'~','') AS hc,
        consensus_modifier, name, COUNT(*) AS n
        FROM priced_products
        WHERE available=1
          AND consensus_canonical IS NOT NULL AND consensus_canonical != ''
          AND htc_code IS NOT NULL AND htc_code NOT IN ('','00000000')
        GROUP BY consensus_canonical, hc, consensus_modifier, name
    """)
    rows = cur.fetchall()
    print(f"scanning {len(rows):,} (path, htc, modifier, name) groups…", file=sys.stderr)

    # Group by canonical_path → set of htc_codes
    by_path: dict[str, dict[str, list[tuple[str, str, int]]]] = defaultdict(lambda: defaultdict(list))
    for cp, hc, mod, name, n in rows:
        if not cp or not hc: continue
        by_path[cp][hc].append((mod or "", name or "", n))

    # Surface paths with >1 htc_code
    bugs = []
    for cp, codes in by_path.items():
        if len(codes) < 2: continue
        # Total SKU count at this path
        total = sum(n for code_rows in codes.values() for _, _, n in code_rows)
        bugs.append({
            "canonical_path": cp,
            "n_distinct_htc": len(codes),
            "total_skus": total,
            "htc_codes_with_counts": "; ".join(
                f"{c}({sum(n for _,_,n in rows)})"
                for c, rows in sorted(codes.items(), key=lambda kv: -sum(n for _,_,n in kv[1]))
            ),
            "sample_modifiers": "|".join(sorted(set(
                m for code_rows in codes.values() for m, _, _ in code_rows if m
            )))[:200],
        })

    bugs.sort(key=lambda b: -b["total_skus"])
    print(f"  paths with multiple htc_codes: {len(bugs):,}", file=sys.stderr)
    print(f"  total SKUs in fragmented paths: {sum(b['total_skus'] for b in bugs):,}", file=sys.stderr)

    with OUT.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["canonical_path","n_distinct_htc","total_skus",
            "htc_codes_with_counts","sample_modifiers"])
        w.writeheader()
        for b in bugs: w.writerow(b)
    print(f"  → {OUT}", file=sys.stderr)

    print(f"\n=== TOP 20 fragmented paths ===")
    for b in bugs[:20]:
        print(f"  {b['n_distinct_htc']:>2} codes, {b['total_skus']:>4} SKUs  {b['canonical_path'][:55]}")
        print(f"      codes: {b['htc_codes_with_counts'][:130]}")
        if b["sample_modifiers"]:
            print(f"      modifiers: {b['sample_modifiers'][:120]}")


if __name__ == "__main__":
    main()
