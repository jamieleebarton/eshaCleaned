#!/usr/bin/env python3
"""Find priced_products SKUs whose grams field disagrees wildly with the size
declared in the product name (Snapple-class bugs).

Approach: regex-parse the unit and quantity from the name (e.g. "32 fl oz",
"5 lb", "16 oz", "907 g"). Compute expected grams. Flag where
actual_grams / expected_grams is outside [1/5, 5].

Outputs CSV ranked by absolute ratio. Top cases are obvious scrape errors:
case-pack weight stored as unit weight, missing decimal, per-lb price
columns being labeled as grams, etc.
"""
from __future__ import annotations
import csv, math, re, sqlite3
from pathlib import Path

ROOT = Path("/Users/jamiebarton/Desktop/esha_audit_bundle")
DB   = ROOT / "recipe_pricing" / "data" / "priced_products_v2.db"
OUT  = ROOT / "recipe_pricing" / "grams_scrape_audit.csv"

# Match: "(N) oz", "(N) fl oz", "(N) lb", "(N) lbs", "(N) pound", "(N) g",
# "(N) kg", "(N) ounce", "(N) gram", with optional decimal
SIZE_RE = re.compile(
    r"\b(\d+(?:\.\d+)?)\s*"
    r"(fl\.?\s*oz|fluid\s+ounces?|ounces?|oz|lbs?|pounds?|kg|kilograms?|grams?|g)\b",
    re.I,
)
# Pack-count: "12 ct", "6 pack", "(2 pack)", "Twin Pack", "X-Pack of N"
PACK_RE = re.compile(
    r"(?:\(?\s*(\d+)\s*[\-\s]*(?:ct|count|pk|pack|packs)\b"
    r"|pack\s+of\s+(\d+)\b)",
    re.I,
)

UNIT_TO_G = {
    "oz": 28.3495, "ounce": 28.3495, "ounces": 28.3495,
    "fl oz": 29.5735, "fl. oz": 29.5735,  # fl oz of water; close enough for liquids
    "fluid ounce": 29.5735, "fluid ounces": 29.5735,
    "lb": 453.592, "lbs": 453.592, "pound": 453.592, "pounds": 453.592,
    "kg": 1000.0, "kilogram": 1000.0, "kilograms": 1000.0,
    "g": 1.0, "gram": 1.0, "grams": 1.0,
}


# Reject sizes that appear inside nutrition-claim phrases ("0g sugar",
# "5g protein", "less than 1g sodium") — these are not package sizes.
_NUTRITION_CLAIM = re.compile(
    r"\d+\s*g\s+(of\s+)?(sugar|protein|fat|carb|sodium|salt|fiber|calorie|cal|added)",
    re.I,
)


def expected_grams_from_name(name: str) -> float | None:
    """Parse declared size from product name. Returns expected grams of a
    SINGLE unit (no pack multiplier applied)."""
    nl = (name or "").lower()
    # Strip nutrition-claim phrases before searching
    nl_stripped = _NUTRITION_CLAIM.sub("", nl)
    matches = SIZE_RE.findall(nl_stripped)
    if not matches:
        return None
    # If multiple sizes appear, prefer the LARGEST plausible one (the package
    # size, not e.g. a "2 oz serving" hint).
    candidates = []
    for qty, unit in matches:
        u = unit.replace(".", "").strip()
        # Normalize "fl oz" — re may have captured "fl oz" as unit already
        if "fl" in u and "oz" in u: u = "fl oz"
        if u not in UNIT_TO_G:
            continue
        try:
            g = float(qty) * UNIT_TO_G[u]
        except ValueError:
            continue
        if g <= 0 or g > 50000:  # discard "0 oz" claims and absurd values
            continue
        candidates.append(g)
    if not candidates:
        return None
    return max(candidates)


def main():
    con = sqlite3.connect(str(DB))
    cur = con.cursor()
    cur.execute("""SELECT name, grams, cents, consensus_canonical, upc, brand
        FROM priced_products WHERE available=1 AND grams>0 AND cents>0
        AND name IS NOT NULL""")
    rows = cur.fetchall()
    print(f"scanning {len(rows):,} SKUs…")

    bugs = []
    parsed_ok = 0; no_size = 0
    for name, grams, cents, cp, upc, brand in rows:
        expected = expected_grams_from_name(name)
        if expected is None:
            no_size += 1
            continue
        parsed_ok += 1
        # Account for pack count if present
        pack_m = PACK_RE.search(name.lower())
        pack_n = 1
        if pack_m:
            for g in pack_m.groups():
                if g:
                    try: pack_n = max(1, int(g)); break
                    except: pass
        # Compare to grams field
        # ratio_unit  = actual/expected (single unit)
        # ratio_pack  = actual/(expected*pack)
        ratio_unit = grams / max(1, expected)
        ratio_pack = grams / max(1, expected * pack_n)
        # Flag only if BOTH single-unit AND pack-multiplied are off by >5x
        if ratio_unit > 5 or ratio_unit < 0.2:
            if pack_n == 1 or (ratio_pack > 5 or ratio_pack < 0.2):
                bugs.append({
                    "name": name[:90],
                    "grams_actual": round(grams, 1),
                    "grams_expected": round(expected, 1),
                    "ratio_unit": round(ratio_unit, 2),
                    "pack_n": pack_n,
                    "ratio_pack": round(ratio_pack, 2),
                    "cents": cents,
                    "implied_unit_price": round(cents / max(1, grams) * 100 / 100, 4),
                    "canonical_path": (cp or "")[:35],
                    "upc": upc,
                    "brand": (brand or "")[:25],
                })

    bugs.sort(key=lambda b: -abs(b["ratio_unit"] - 1))
    print(f"  parsed size from name: {parsed_ok:,}")
    print(f"  no recognizable size:  {no_size:,}")
    print(f"  flagged grams bugs:    {len(bugs):,}")
    print(f"\nratio_unit distribution:")
    buckets = {"<0.1": 0, "0.1-0.2": 0, "5-10": 0, "10-50": 0, ">50": 0}
    for b in bugs:
        r = b["ratio_unit"]
        if r < 0.1: buckets["<0.1"] += 1
        elif r < 0.2: buckets["0.1-0.2"] += 1
        elif r > 50: buckets[">50"] += 1
        elif r > 10: buckets["10-50"] += 1
        else: buckets["5-10"] += 1
    for k, v in buckets.items(): print(f"  {k}: {v}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    cols = ["name","grams_actual","grams_expected","ratio_unit","pack_n",
             "ratio_pack","cents","implied_unit_price","canonical_path","upc","brand"]
    with OUT.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for b in bugs: w.writerow(b)
    print(f"\n→ {OUT}")

    print(f"\n=== TOP 30 worst (largest |ratio_unit - 1|) ===")
    for b in bugs[:30]:
        print(f"  {b['ratio_unit']:>7.1f}× actual={b['grams_actual']:>7.0f}g  "
              f"expected={b['grams_expected']:>6.0f}g  pack={b['pack_n']}  "
              f"${b['cents']/100:>5.2f}  {b['name'][:55]}")


if __name__ == "__main__":
    main()
