#!/usr/bin/env python3
"""Recompute htc_full_code on every row in priced_products_v2.db.

Round 5 re-tagged htc_code and htc_form_code with the current encoder, but
left htc_full_code with values from an earlier tagging run — so the bucket
portion of htc_full_code no longer matches htc_code. This script
recomputes:

  htc_full_code = ~bucket-variant-claims

Where:
  bucket  = htc_code (the current 8-char identity code)
  variant = SHA256[:6] of retail_leaf_path SUFFIX (past canonical_path)
  claims  = 4-hex bitfield from product claims (organic, gluten-free, etc.)

Claims source: parse from product name + product_meta JSON if present.

Backs up DB. Idempotent. Atomic.

Usage:
  python3 recipe_pricing/populate_htc_full_code.py [--dry-run]
"""
from __future__ import annotations
import argparse, json, shutil, sqlite3, sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "recipe_pricing" / "data" / "priced_products_v2.db"
BAK = DB.with_suffix(".before_round8_full_code.db")

sys.path.insert(0, str(ROOT / "recipe_mapper" / "v1"))
from htc.full_code import compose_full_code, claim_bits_from_str  # noqa: E402

# Keywords in product name → claim string. Cheap-and-good heuristic.
NAME_CLAIM_KEYS = {
    "organic":     "organic",
    "non gmo":     "non_gmo",
    "non-gmo":     "non_gmo",
    "gluten free": "gluten_free",
    "gluten-free": "gluten_free",
    "dairy free":  "dairy_free",
    "dairy-free":  "dairy_free",
    "lactose free":"dairy_free",
    "vegan":       "vegan",
    "vegetarian":  "vegetarian",
    "kosher":      "kosher",
    "halal":       "halal",
    "sugar free":  "sugar_free",
    "sugar-free":  "sugar_free",
    "no sugar":    "sugar_free",
    "low fat":     "low_fat",
    "fat free":    "low_fat",
    "low sodium":  "low_sodium",
    "no salt":     "low_sodium",
    "high protein":"high_protein",
    "whole grain": "whole_grain",
    "whole wheat": "whole_grain",
    "fair trade":  "fair_trade",
    "natural":     "natural",
}


def claims_from_name(name: str) -> str:
    """Return pipe-separated claim names found in product name."""
    nl = (name or "").lower()
    found = set()
    for kw, claim in NAME_CLAIM_KEYS.items():
        if kw in nl:
            found.add(claim)
    return "|".join(sorted(found))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not DB.exists():
        print(f"missing {DB}", file=sys.stderr); sys.exit(1)
    if not args.dry_run and not BAK.exists():
        print(f"backing up DB → {BAK.name}", file=sys.stderr)
        shutil.copy(str(DB), str(BAK))

    con = sqlite3.connect(str(DB))
    cur = con.cursor()
    rows = cur.execute("""
        SELECT rowid, name, htc_code, consensus_canonical, retail_leaf_path,
               htc_full_code
        FROM priced_products
    """).fetchall()
    print(f"scanning {len(rows):,} rows…", file=sys.stderr)

    updates = []
    n_changed = 0
    n_no_htc = 0
    samples = []
    claim_counts: Counter = Counter()

    for rowid, name, htc_code, cp, rlp, old_full in rows:
        if not htc_code:
            n_no_htc += 1
            continue
        claims = claims_from_name(name or "")
        new_full = compose_full_code(htc_code, cp or "", rlp or cp or "", claims)
        for c in claims.split("|"):
            if c: claim_counts[c] += 1
        if new_full != (old_full or ""):
            n_changed += 1
            updates.append((new_full, rowid))
            if len(samples) < 12:
                samples.append({
                    "name": (name or "")[:50],
                    "old": old_full or "(none)",
                    "new": new_full,
                    "claims": claims or "(none)",
                })

    print(f"\nrows scanned:    {len(rows):,}", file=sys.stderr)
    print(f"no htc_code:     {n_no_htc:,}  (skipped)", file=sys.stderr)
    print(f"new full codes:  {n_changed:,}", file=sys.stderr)
    print(f"\nClaim distribution:", file=sys.stderr)
    for c, n in claim_counts.most_common():
        print(f"  {c:<14}  {n:,}", file=sys.stderr)
    print(f"\nSample changes:", file=sys.stderr)
    for s in samples[:10]:
        print(f"  '{s['name']}'", file=sys.stderr)
        print(f"     old: {s['old']}", file=sys.stderr)
        print(f"     new: {s['new']}  (claims={s['claims']})", file=sys.stderr)

    if args.dry_run:
        print(f"\n(dry-run; no updates written)", file=sys.stderr)
        return

    print(f"\napplying {len(updates):,} updates…", file=sys.stderr)
    cur.executemany("UPDATE priced_products SET htc_full_code = ? WHERE rowid = ?", updates)
    con.commit()
    print("done.", file=sys.stderr)


if __name__ == "__main__":
    main()
