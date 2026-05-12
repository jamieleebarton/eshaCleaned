#!/usr/bin/env python3
"""Find beverage SKUs whose grams field is grossly inconsistent with the
typical bottle/carton/can/multipack norms — Snapple-class scrape bugs.

Snapple Pink Lemonade Bottle: stored grams=11657g for $1.99.
Real bottle is 16 fl oz (473g). 25× scale-up bug.

Approach:
  1. Parse "X fl oz" / "X oz" / "X liter" / "X ml" / "X gallon" from name
  2. Multiply by pack_count if present ("12 pack", "6 pk")
  3. Compare to stored grams; flag where ratio is wildly off

Outputs CSV ranked by severity. Apply via apply_grams_fixes.py shape.
"""
from __future__ import annotations
import csv, re, sqlite3
from pathlib import Path

ROOT = Path("/Users/jamiebarton/Desktop/esha_audit_bundle")
DB   = ROOT / "recipe_pricing" / "data" / "priced_products_v2.db"
OUT  = ROOT / "recipe_pricing" / "beverage_grams_audit.csv"

VOL_RE = re.compile(
    r"\b(\d+(?:\.\d+)?)\s*(fl\.?\s*oz|fluid\s+ounces?|ounces?|oz|"
    r"liters?|litres?|ml|milliliters?|gal|gallons?|qt|quarts?|pt|pints?)\b",
    re.I,
)
PACK_RE = re.compile(r"(?:\(?\s*(\d+)\s*[\-\s]*(?:ct|count|pk|pack|packs)\b"
                       r"|pack\s+of\s+(\d+)\b)", re.I)

UNIT_TO_G = {
    "fl oz": 29.5735, "fl. oz": 29.5735,
    "fluid ounce": 29.5735, "fluid ounces": 29.5735,
    "oz": 28.3495, "ounce": 28.3495, "ounces": 28.3495,
    "liter": 1000.0, "liters": 1000.0, "litre": 1000.0, "litres": 1000.0,
    "ml": 1.0, "milliliter": 1.0, "milliliters": 1.0,
    "gal": 3785.41, "gallon": 3785.41, "gallons": 3785.41,
    "qt": 946.353, "quart": 946.353, "quarts": 946.353,
    "pt": 473.176, "pint": 473.176, "pints": 473.176,
}


def expected_grams(name: str) -> tuple[float, int] | None:
    nl = (name or "").lower()
    matches = VOL_RE.findall(nl)
    candidates = []
    for qty, unit in matches:
        u = unit.replace(".", "").strip()
        if "fl" in u and "oz" in u: u = "fl oz"
        if u not in UNIT_TO_G: continue
        try: g = float(qty) * UNIT_TO_G[u]
        except ValueError: continue
        if 0 < g < 50000: candidates.append(g)
    if not candidates: return None
    pkg_g = max(candidates)
    pack_n = 1
    pm = PACK_RE.search(nl)
    if pm:
        for grp in pm.groups():
            if grp:
                try: pack_n = max(1, int(grp)); break
                except: pass
    return pkg_g, pack_n


def main():
    con = sqlite3.connect(str(DB))
    cur = con.cursor()

    # Per-path median grams: find SKUs ≥ 5× their path's median (Snapple class)
    print("=== Per-path grams outliers (Snapple class) ===")
    cur.execute("""SELECT consensus_canonical, name, grams, cents, upc
        FROM priced_products
        WHERE consensus_canonical LIKE 'Beverage%'
        AND available=1 AND grams>0 AND cents>0""")
    by_path: dict[str, list] = {}
    for cp, n, g, c, upc in cur.fetchall():
        by_path.setdefault(cp, []).append((n, g, c, upc))
    # Heuristic: name suggests SINGLE bottle/can but stored grams = case
    SINGLE_HINTS = ("bottle", "can", "carton", "pouch", "jug", "container")
    MULTIPACK_HINTS = ("pack", "case", "ct", " count", "multipack",
                        "12 ct", "6 ct", "24 ct", "x12", "x24", "12pk", "24pk")
    snapple_class = []
    for cp, items in by_path.items():
        if len(items) < 5: continue
        gs = sorted([i[1] for i in items])
        median = gs[len(gs) // 2]
        for n, g, c, upc in items:
            nl = (n or "").lower()
            looks_single = any(h in nl for h in SINGLE_HINTS) and \
                            not any(m in nl for m in MULTIPACK_HINTS)
            if g >= median * 5 and median > 0 and looks_single:
                snapple_class.append({
                    "upc": upc, "name": n[:90],
                    "grams": round(g, 1),
                    "path_median_grams": round(median, 1),
                    "ratio_vs_median": round(g / median, 1),
                    "cents": c,
                    "canonical_path": cp,
                })
    snapple_class.sort(key=lambda b: -b["ratio_vs_median"])
    print(f"  Snapple-class (≥5× path median): {len(snapple_class)}")
    for b in snapple_class[:15]:
        print(f"  {b['ratio_vs_median']:>5.1f}×  actual={b['grams']:>6.0f}g  "
              f"path-median={b['path_median_grams']:>5.0f}g  ${b['cents']/100:.2f}  {b['name'][:60]}")

    SNAPPLE_OUT = ROOT / "recipe_pricing" / "beverage_snapple_class.csv"
    if snapple_class:
        with SNAPPLE_OUT.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(snapple_class[0].keys()))
            w.writeheader()
            for r in snapple_class: w.writerow(r)
        print(f"  → {SNAPPLE_OUT}\n")

    # Continue to name-parse audit for SKUs whose name DOES declare size
    cur.execute("""SELECT name, grams, cents, consensus_canonical, upc
        FROM priced_products
        WHERE consensus_canonical LIKE 'Beverage%' OR consensus_canonical LIKE '%Lemonade%'
        AND available=1 AND grams>0 AND cents>0""")
    rows = cur.fetchall()
    print(f"=== Name-parse audit ({len(rows):,} beverage SKUs) ===")

    bugs = []; ok = 0; no_size = 0
    for name, grams, cents, cp, upc in rows:
        parsed = expected_grams(name)
        if not parsed:
            no_size += 1; continue
        unit_g, pack_n = parsed
        expected_total = unit_g * pack_n
        ratio_unit = grams / max(1, unit_g)
        ratio_pack = grams / max(1, expected_total)
        # Flag when BOTH single-unit and pack-multiplied are off >5×
        if (ratio_unit > 5 or ratio_unit < 0.2):
            if pack_n == 1 or (ratio_pack > 5 or ratio_pack < 0.2):
                bugs.append({
                    "upc": upc,
                    "name": name[:90],
                    "grams_actual": round(grams, 1),
                    "grams_expected_unit": round(unit_g, 1),
                    "pack_n": pack_n,
                    "grams_expected_pack": round(expected_total, 1),
                    "ratio_unit": round(ratio_unit, 2),
                    "cents": cents,
                    "canonical_path": cp,
                })
        else:
            ok += 1

    print(f"  parseable: {len(rows) - no_size:,}  no-size: {no_size:,}  flagged: {len(bugs):,}")

    bugs.sort(key=lambda b: -abs(b["ratio_unit"] - 1))
    cols = list(bugs[0].keys()) if bugs else ["upc","name","grams_actual","grams_expected_unit",
        "pack_n","grams_expected_pack","ratio_unit","cents","canonical_path"]
    with OUT.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for b in bugs: w.writerow(b)
    print(f"  → {OUT}\n")

    print(f"=== TOP 25 by severity ===")
    for b in bugs[:25]:
        print(f"  {b['ratio_unit']:>6.1f}×  actual={b['grams_actual']:>6.0f}g  "
              f"expected={b['grams_expected_pack']:>6.0f}g (pack={b['pack_n']})  "
              f"${b['cents']/100:>6.2f}  {b['name'][:55]}")


if __name__ == "__main__":
    main()
