#!/usr/bin/env python3
"""Apply grams corrections to priced_products from the scrape-audit CSV.

For each flagged row (ratio_unit > 5 or < 0.2), set
  new_grams = expected_grams × pack_n
where expected_grams was parsed from the SKU name and pack_n is the
declared multipack count.

Skips non-food paths (Personal Care, Pet, Beauty, Supplements) — those
SKUs shouldn't be picked anyway and a wrong grams there can't hurt the
recipe pricing layer.

Backs up priced_products.before_grams_fix.db beside the live DB.
"""
from __future__ import annotations
import csv, shutil, sqlite3, sys
from pathlib import Path

ROOT = Path("/Users/jamiebarton/Desktop/esha_audit_bundle")
DB   = ROOT / "recipe_pricing" / "data" / "priced_products_v2.db"
BAK  = DB.with_name("priced_products_v2.before_grams_fix.db")
AUDIT = ROOT / "recipe_pricing" / "grams_scrape_audit.csv"

NON_FOOD_PREFIXES = (
    "Non-Food", "Personal Care", "Beauty", "Pet", "Household",
    "Medicine", "Sports & Wellness > Supplement",
)


def main():
    if not BAK.exists():
        print(f"backing up DB → {BAK.name}", file=sys.stderr)
        shutil.copy(str(DB), str(BAK))

    # Load corrections
    rows = list(csv.DictReader(AUDIT.open()))
    print(f"audit rows: {len(rows):,}", file=sys.stderr)

    fixes: list[tuple[str, float, float, float]] = []  # (upc, old_g, new_g, ratio)
    skipped_non_food = 0
    skipped_low_confidence = 0

    for r in rows:
        cp = r.get("canonical_path") or ""
        if any(cp.startswith(p) for p in NON_FOOD_PREFIXES):
            skipped_non_food += 1; continue
        try:
            actual = float(r["grams_actual"])
            expected = float(r["grams_expected"])
            pack_n = max(1, int(r["pack_n"]))
            ratio = float(r["ratio_unit"])
        except (ValueError, KeyError):
            skipped_low_confidence += 1; continue
        if expected <= 0:
            skipped_low_confidence += 1; continue
        # Confidence gate: only fix when off by >5x or <0.2x (matches audit gate)
        if not (ratio > 5 or ratio < 0.2):
            skipped_low_confidence += 1; continue
        new_g = expected * pack_n
        upc = r.get("upc", "")
        if not upc:
            skipped_low_confidence += 1; continue
        fixes.append((upc, actual, new_g, ratio))

    print(f"  → fixing: {len(fixes):,} SKUs", file=sys.stderr)
    print(f"  skipped non-food: {skipped_non_food}", file=sys.stderr)
    print(f"  skipped low-confidence/missing: {skipped_low_confidence}", file=sys.stderr)

    # Apply UPDATEs and recompute cpg. De-dupe by UPC first since priced_products
    # has many duplicate rows per UPC (a single UPDATE WHERE upc=? hits all of them).
    seen = set()
    deduped = []
    for upc, old_g, new_g, ratio in fixes:
        if upc in seen: continue
        seen.add(upc); deduped.append((upc, old_g, new_g, ratio))
    print(f"  → distinct UPCs: {len(deduped):,}", file=sys.stderr)

    con = sqlite3.connect(str(DB))
    cur = con.cursor()
    n_updated = 0; n_no_match = 0
    for upc, old_g, new_g, ratio in deduped:
        # Match by UPC alone — the audit already proved these are wrong;
        # if the row's grams isn't exactly old_g it just means duplicate
        # rows have already been touched, but they all want the same new_g.
        cur.execute(
            "UPDATE priced_products SET grams = ?, "
            "cpg = CASE WHEN ? > 0 THEN CAST(cents AS REAL) / ? ELSE cpg END "
            "WHERE upc = ?",
            (new_g, new_g, new_g, upc),
        )
        if cur.rowcount > 0:
            n_updated += cur.rowcount
        else:
            n_no_match += 1
    con.commit()
    print(f"\nupdated rows: {n_updated:,}", file=sys.stderr)
    print(f"no UPC match (already corrected?): {n_no_match}", file=sys.stderr)

    # Spot-check: previously-broken SKUs
    print("\n=== Spot-check ===", file=sys.stderr)
    spot_upcs = [f[0] for f in fixes[:5]]
    for upc in spot_upcs:
        cur.execute("SELECT name, grams, cents FROM priced_products WHERE upc = ? LIMIT 1", (upc,))
        row = cur.fetchone()
        if row:
            n, g, c = row
            print(f"  upc={upc} grams={g:.1f} cents={c}  {n[:55]}", file=sys.stderr)
    con.close()
    print(f"\n✓ corrections applied; rollback via: cp {BAK} {DB}", file=sys.stderr)


if __name__ == "__main__":
    main()
