#!/usr/bin/env python3
"""Fix per-lb-as-package and case-pack-as-grams price bugs in priced_products.

Disambiguation:
  Parse weight-range from name (e.g. "Kroger® Spiral Sliced Honey Ham Half (8-10 Lb)"
  or "(2 lbs)" or "X-Y lb"). Compare to stored grams.

  CASE A — grams much bigger than parsed name range (>2×):
    → grams field stores case-pack weight; rewrite to midpoint of parsed range
    → cents likely stores per-unit price; leave as-is

  CASE B — grams within parsed range (within 50%) but implied $/lb tiny:
    → cents stores per-lb rate; multiply cents × parsed_lbs to get package price

  CASE C — neither matches: skip (unfixable without re-scrape)

Backs up DB to priced_products_v2.before_per_lb_fix.db. Logs each fix.
"""
from __future__ import annotations
import csv, re, shutil, sqlite3, sys
from pathlib import Path

ROOT = Path("/Users/jamiebarton/Desktop/esha_audit_bundle")
DB   = ROOT / "recipe_pricing" / "data" / "priced_products_v2.db"
BAK  = DB.with_name("priced_products_v2.before_per_lb_fix.db")
AUDIT = ROOT / "recipe_pricing" / "per_lb_price_audit.csv"
LOG = ROOT / "recipe_pricing" / "per_lb_fixes_applied.csv"

# Parse weight range/single from product name
WEIGHT_PAREN_RE = re.compile(
    r"\(?\s*(\d+(?:\.\d+)?)\s*(?:-|to|–|—)\s*(\d+(?:\.\d+)?)\s*(?:lbs?|pounds?)\b",
    re.I,
)
WEIGHT_SINGLE_RE = re.compile(
    r"\b(\d+(?:\.\d+)?)\s*(?:lbs?|pounds?)\b",
    re.I,
)


def parse_weight_lbs(name: str) -> tuple[float, float] | None:
    """Returns (lo, hi) lbs from name, or None if no clean match."""
    m = WEIGHT_PAREN_RE.search(name or "")
    if m:
        return float(m.group(1)), float(m.group(2))
    m = WEIGHT_SINGLE_RE.search(name or "")
    if m:
        v = float(m.group(1))
        return v, v
    return None


def main():
    if not BAK.exists():
        print(f"backing up DB → {BAK.name}", file=sys.stderr)
        shutil.copy(str(DB), str(BAK))

    with AUDIT.open() as f:
        rows = list(csv.DictReader(f))
    print(f"audit rows: {len(rows):,}", file=sys.stderr)

    case_a_fixes = []  # (upc, old_grams, new_grams, name)
    case_b_fixes = []  # (upc, old_cents, new_cents, name)
    skipped = 0

    for r in rows:
        upc = r["upc"]
        name = r["name"]
        try:
            grams = float(r["grams"])
            cents = int(float(r["stored_cents"]))
            stored_lbs = float(r["lbs"])
        except (KeyError, ValueError):
            skipped += 1; continue

        parsed = parse_weight_lbs(name)
        if not parsed:
            skipped += 1; continue
        lo, hi = parsed
        mid_lbs = (lo + hi) / 2
        mid_g = mid_lbs * 453.592

        # CASE A: grams ≥ 2× parsed midpoint → case-pack-as-grams bug
        if grams >= mid_g * 2:
            case_a_fixes.append((upc, grams, mid_g, mid_lbs, name))
        # CASE B: grams within ±50% of parsed → cents likely per-lb
        elif 0.5 * mid_g <= grams <= 1.5 * mid_g:
            new_cents = int(round(cents * (grams / 453.592)))
            # Only apply if new price is plausible (no extreme inflation)
            if new_cents <= cents * 50:  # avoid pathological multipliers
                case_b_fixes.append((upc, cents, new_cents, mid_lbs, name))
            else:
                skipped += 1
        else:
            skipped += 1

    print(f"  CASE A (case-pack grams):       {len(case_a_fixes):,}", file=sys.stderr)
    print(f"  CASE B (per-lb cents):          {len(case_b_fixes):,}", file=sys.stderr)
    print(f"  skipped (no parse / unclear):   {skipped:,}", file=sys.stderr)

    con = sqlite3.connect(str(DB))
    cur = con.cursor()
    log_rows = []
    n_a = 0; n_b = 0

    for upc, old_g, new_g, lbs, name in case_a_fixes:
        cur.execute("""UPDATE priced_products SET grams = ?,
            cpg = CAST(cents AS REAL) / ?
            WHERE upc = ?""", (new_g, new_g, upc))
        n_a += cur.rowcount
        log_rows.append({"case":"A","upc":upc,"name":name[:80],
                         "field":"grams","old":round(old_g,1),"new":round(new_g,1)})

    for upc, old_c, new_c, lbs, name in case_b_fixes:
        cur.execute("""UPDATE priced_products SET cents = ?,
            cpg = CAST(? AS REAL) / NULLIF(grams, 0)
            WHERE upc = ?""", (new_c, new_c, upc))
        n_b += cur.rowcount
        log_rows.append({"case":"B","upc":upc,"name":name[:80],
                         "field":"cents","old":old_c,"new":new_c})

    con.commit()
    con.close()

    with LOG.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["case","upc","name","field","old","new"])
        w.writeheader()
        for row in log_rows: w.writerow(row)

    print(f"\napplied: CASE A {n_a} rows, CASE B {n_b} rows", file=sys.stderr)
    print(f"  log: {LOG}", file=sys.stderr)
    print(f"rollback: cp {BAK} {DB}", file=sys.stderr)


if __name__ == "__main__":
    main()
