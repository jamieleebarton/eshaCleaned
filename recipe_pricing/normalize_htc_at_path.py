#!/usr/bin/env python3
"""At each canonical_path that defines ONE food identity, force all products
to share a single htc_form code.

Approach:
  1. Group SKUs by canonical_path.
  2. Within each path, group htc_form codes by their identity prefix
     (positions 1-4: group, family, food slot). Codes that differ only at
     positions 5-7 (form, processing, ptype) are the same food.
  3. If a path has 2+ codes sharing the same identity prefix, collapse them
     to the one with form/processing/ptype = 0 (the canonical "identity"
     code that matches what the recipe-side encoder produces).
  4. UPDATE priced_products.

This eliminates the gratuitous granularity from `cultured` / `pasteurized` /
`organic` form bits that were set on products but not on recipes — the same
food fragmented into mini-pools.

Backs up DB.
"""
from __future__ import annotations
import csv, shutil, sqlite3, sys
from collections import defaultdict
from pathlib import Path

ROOT = Path("/Users/jamiebarton/Desktop/esha_audit_bundle")
DB   = ROOT / "recipe_pricing" / "data" / "priced_products_v2.db"
BAK  = DB.with_name("priced_products_v2.before_htc_normalize.db")
LOG  = ROOT / "recipe_pricing" / "htc_normalize.csv"

# Crockford check digit (so the rewritten codes are valid)
CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
CHECK = CROCKFORD + "*~$=U"


def crockford_check(c7: str) -> str:
    val = 0
    for ch in c7:
        idx = CROCKFORD.index(ch.upper()) if ch.upper() in CROCKFORD else 0
        val = val * 32 + idx
    return CHECK[val % 37]


def main():
    if not BAK.exists():
        print(f"backing up DB → {BAK.name}", file=sys.stderr)
        shutil.copy(str(DB), str(BAK))

    con = sqlite3.connect(str(DB))
    cur = con.cursor()
    cur.execute("""SELECT consensus_canonical, REPLACE(htc_form_code,'~','') AS hf,
        COUNT(*), MIN(cents), MAX(cents)
        FROM priced_products
        WHERE consensus_canonical IS NOT NULL AND consensus_canonical != ''
          AND htc_form_code IS NOT NULL
          AND htc_form_code NOT IN ('','00000000')
          AND available = 1
        GROUP BY consensus_canonical, hf""")
    rows = cur.fetchall()
    print(f"scanning {len(rows):,} (path, htc) combos…", file=sys.stderr)

    by_path: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for cp, hf, n, _, _ in rows:
        by_path[cp].append((hf, n))

    # For each path, find collapsible groups
    fixes: list[tuple[str, str, str, int]] = []  # (cp, old_hf, new_hf, n_skus)
    for cp, codes in by_path.items():
        if len(codes) < 2: continue
        # Group by identity prefix (first 4 chars: group + family + food slot)
        by_identity: dict[str, list[tuple[str, int]]] = defaultdict(list)
        for hf, n in codes:
            if len(hf) < 8: continue
            identity = hf[:4]
            by_identity[identity].append((hf, n))
        for identity, members in by_identity.items():
            if len(members) < 2: continue
            # Pick the canonical code: form=0, processing=0, ptype=0
            #    code = identity + "000" + check_digit
            canonical_7 = identity + "000"
            canonical_code = canonical_7 + crockford_check(canonical_7)
            # Collapse all members to the canonical code
            for hf, n in members:
                if hf != canonical_code:
                    fixes.append((cp, hf, canonical_code, n))

    print(f"  collapsible (path, old_htc, new_htc) triplets: {len(fixes):,}", file=sys.stderr)

    # Apply
    n_rows = 0
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["canonical_path","old_htc","new_htc","n_skus"])
        w.writeheader()
        for cp, old_hf, new_hf, n in fixes:
            cur.execute("""UPDATE priced_products SET htc_form_code = ?
                WHERE consensus_canonical = ? AND REPLACE(htc_form_code,'~','') = ?""",
                (new_hf, cp, old_hf))
            n_rows += cur.rowcount
            w.writerow({"canonical_path": cp, "old_htc": old_hf,
                         "new_htc": new_hf, "n_skus": n})
    con.commit()
    print(f"\nupdated {n_rows} rows ({len(fixes)} distinct path/htc collapses)", file=sys.stderr)
    print(f"  → log: {LOG}", file=sys.stderr)

    print(f"\nTOP 15 collapses by SKU count:", file=sys.stderr)
    fixes.sort(key=lambda x: -x[3])
    for cp, old_hf, new_hf, n in fixes[:15]:
        print(f"  {n:>3} SKUs  {cp[:45]:<45}  {old_hf} → {new_hf}", file=sys.stderr)


if __name__ == "__main__":
    main()
