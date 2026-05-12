#!/usr/bin/env python3
"""Fix case-pack-as-grams: SKUs with "(N pack)" / "Pack of N" in name where
N > 1 and stored grams matches a single-unit weight, not pack total.

Symptom: King Arthur "(8 pack) ... 5 lb Bag" stored grams=2268 (1 bag),
cents=$42.38 (full 8-pack). Per-gram looks 8× too expensive.

Fix: multiply grams × pack_n so per-gram math reflects what you actually
get for the price.
"""
from __future__ import annotations
import csv, re, shutil, sqlite3, sys
from pathlib import Path

ROOT = Path("/Users/jamiebarton/Desktop/esha_audit_bundle")
DB   = ROOT / "recipe_pricing" / "data" / "priced_products_v2.db"
BAK  = DB.with_name("priced_products_v2.before_multipack_fix.db")
LOG  = ROOT / "recipe_pricing" / "multipack_fixes.csv"

PACK_RE = re.compile(
    r"\(?\s*(\d+)\s*[\-\s]*(?:ct|count|pk|pack|packs)\b"
    r"|pack\s+of\s+(\d+)\b",
    re.I,
)
# Single-unit size in name — same as audit_grams_scrape
SIZE_RE = re.compile(
    r"\b(\d+(?:\.\d+)?)\s*"
    r"(fl\.?\s*oz|fluid\s+ounces?|ounces?|oz|lbs?|pounds?|kg|kilograms?|grams?|g)\b",
    re.I,
)
UNIT_TO_G = {
    "oz": 28.3495, "ounce": 28.3495, "ounces": 28.3495,
    "fl oz": 29.5735, "fl. oz": 29.5735,
    "lb": 453.592, "lbs": 453.592, "pound": 453.592, "pounds": 453.592,
    "kg": 1000.0, "kilogram": 1000.0,
    "g": 1.0, "gram": 1.0, "grams": 1.0,
}


def parse_pack_n(name: str) -> int:
    m = PACK_RE.search(name or "")
    if not m: return 1
    for g in m.groups():
        if g:
            try: return max(1, int(g))
            except: continue
    return 1


def parse_unit_grams(name: str) -> float | None:
    """Largest single-unit size in name."""
    candidates = []
    for qty, unit in SIZE_RE.findall((name or "").lower()):
        u = unit.replace(".", "").strip()
        if "fl" in u and "oz" in u: u = "fl oz"
        if u not in UNIT_TO_G: continue
        try: g = float(qty) * UNIT_TO_G[u]
        except: continue
        if 0 < g < 30000: candidates.append(g)
    return max(candidates) if candidates else None


def main():
    if not BAK.exists():
        print(f"backing up DB → {BAK.name}", file=sys.stderr)
        shutil.copy(str(DB), str(BAK))

    con = sqlite3.connect(str(DB))
    cur = con.cursor()
    cur.execute("""SELECT DISTINCT upc, name, grams, cents
        FROM priced_products WHERE available=1 AND grams>0 AND cents>0""")
    rows = cur.fetchall()
    print(f"scanning {len(rows):,} distinct SKUs for case-pack bugs…", file=sys.stderr)

    fixes = []
    for upc, name, grams, cents in rows:
        pack_n = parse_pack_n(name)
        if pack_n <= 1: continue
        unit_g = parse_unit_grams(name)
        if unit_g is None: continue
        # If stored grams is within ±10% of single-unit weight, it's the bug
        if 0.9 * unit_g <= grams <= 1.1 * unit_g:
            new_grams = unit_g * pack_n
            fixes.append((upc, grams, new_grams, pack_n, name))

    print(f"  found {len(fixes):,} case-pack bugs", file=sys.stderr)

    n_updated = 0
    log_rows = []
    for upc, old_g, new_g, pack_n, name in fixes:
        cur.execute("""UPDATE priced_products SET grams = ?,
            cpg = CAST(cents AS REAL) / ?
            WHERE upc = ?""", (new_g, new_g, upc))
        n_updated += cur.rowcount
        log_rows.append({"upc": upc, "name": name[:90],
                         "pack_n": pack_n, "old_grams": round(old_g,1),
                         "new_grams": round(new_g,1)})
    con.commit()
    con.close()

    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["upc","name","pack_n","old_grams","new_grams"])
        w.writeheader()
        for r in log_rows: w.writerow(r)
    print(f"\napplied {n_updated} row updates ({len(fixes)} distinct UPCs)", file=sys.stderr)
    print(f"  → log: {LOG}", file=sys.stderr)
    print(f"\nTOP 15 fixes:", file=sys.stderr)
    for r in log_rows[:15]:
        print(f"  pack={r['pack_n']}  {r['old_grams']:.0f}g → {r['new_grams']:.0f}g  {r['name'][:60]}",
              file=sys.stderr)


if __name__ == "__main__":
    main()
