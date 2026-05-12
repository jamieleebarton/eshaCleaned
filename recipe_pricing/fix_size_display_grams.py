#!/usr/bin/env python3
"""Repair package gram blowups using size_display/package-size evidence.

The older name parser catches some scrape bugs, but it misses rows where the
reliable package size lives in size_display. Common symptoms:

  * "64 fl oz" bottle stored as 15,789g instead of 1,893g.
  * "16 oz, 4 count" butter stored as 1,814g instead of 454g.
  * "8.2 oz, 10 Count" tortillas stored as 2,325g instead of 232g.

This pass is intentionally conservative. It fixes rows where stored grams are
clearly inflated relative to the parsed package size, and avoids per-unit
multipacks like juice boxes, bottles, pouches, bags, packets, and small bars.
"""
from __future__ import annotations

import argparse
import csv
import re
import shutil
import sqlite3
import sys
from pathlib import Path


ROOT = Path("/Users/jamiebarton/Desktop/esha_audit_bundle")
DB = ROOT / "recipe_pricing" / "data" / "priced_products_v2.db"
BAK = DB.with_name("priced_products_v2.before_size_display_grams_fix.db")
LOG = ROOT / "recipe_pricing" / "size_display_grams_fixes.csv"

NUM_RE = r"(?:\d+(?:\.\d+)?|\.\d+)"

SIZE_RE = re.compile(
    rf"(?<![\d.])({NUM_RE})\s*"
    r"(fl\.?\s*oz|fo|fluid\s+ounces?|ounces?|oz|lbs?|pounds?|kg|kilograms?|"
    r"grams?|g|ml|milliliters?|l|liters?|litres?|gal|gallon|gallons|qt|quart|quarts)\b",
    re.I,
)
PACK_SIZE_RE = re.compile(
    rf"(?<![\d.])(\d+)\s*(ct|count|pk|pack|packs|bottles?|cans?|pouches?|"
    rf"boxes?|bags?|packets?)\s*/\s*({NUM_RE})\s*"
    r"(fl\.?\s*oz|fo|fluid\s+ounces?|ounces?|oz|lbs?|pounds?|kg|kilograms?|"
    r"grams?|g|ml|milliliters?|l|liters?|litres?)\b",
    re.I,
)
COUNT_RE = re.compile(r"\b(\d+)\s*(?:ct|count)\b", re.I)
PACK_RE = re.compile(
    r"\b(\d+)[\s-]*(?:pk|pack|packs)\b|pack\s+of\s+(\d+)",
    re.I,
)

UNIT_TO_G = {
    "oz": 28.3495,
    "ounce": 28.3495,
    "ounces": 28.3495,
    "fl oz": 29.5735,
    "fo": 29.5735,
    "fluid ounce": 29.5735,
    "fluid ounces": 29.5735,
    "lb": 453.592,
    "lbs": 453.592,
    "pound": 453.592,
    "pounds": 453.592,
    "kg": 1000.0,
    "kilogram": 1000.0,
    "kilograms": 1000.0,
    "g": 1.0,
    "gram": 1.0,
    "grams": 1.0,
    "ml": 1.0,
    "milliliter": 1.0,
    "milliliters": 1.0,
    "l": 1000.0,
    "liter": 1000.0,
    "liters": 1000.0,
    "litre": 1000.0,
    "litres": 1000.0,
    "gal": 3785.41,
    "gallon": 3785.41,
    "gallons": 3785.41,
    "qt": 946.353,
    "quart": 946.353,
    "quarts": 946.353,
}

DIMENSION_RE = re.compile(
    r"\b(width|height|depth|length)\b|\d+(?:\.\d+)?\s*x\s*\d+(?:\.\d+)?",
    re.I,
)
NUTRITION_CLAIM_RE = re.compile(
    r"\d+(?:\.\d+)?\s*g\s+(?:of\s+)?"
    r"(?:protein|sugar|fat|carb|carbs|fiber|sodium|salt|calories?)\b",
    re.I,
)
PREPARED_YIELD_RE = re.compile(
    r"\b(?:makes?|yields?)\s+\d+(?:\.\d+)?\s*"
    r"(?:fl\.?\s*oz|fo|fluid\s+ounces?|ounces?|oz|lbs?|pounds?|kg|kilograms?|"
    r"grams?|g|ml|milliliters?|l|liters?|litres?|gal|gallon|gallons|qt|quart|quarts)"
    r"(?:\s+(?:total|prepared|when\s+prepared))?\b",
    re.I,
)
PER_UNIT_CONTAINER_RE = re.compile(
    r"\b(bottles?|cans?|pouches?|juice boxes?|boxes?|cups?|bags?|packets?|"
    r"sachets?|pods?|jars?|packs?)\b",
    re.I,
)
SMALL_PER_UNIT_RE = re.compile(
    r"\b(bars?|sticks?|rolls?|cones?|pops?|ice pops?|freezer pops?)\b", re.I)
BEVERAGE_PATH_RE = re.compile(r"^beverage\b", re.I)


def _norm_unit(unit: str) -> str:
    unit = unit.lower().replace(".", "").strip()
    if unit == "fo":
        return "fo"
    if "fl" in unit and "oz" in unit:
        return "fl oz"
    return unit


def _size_grams(qty: str, unit: str) -> float | None:
    u = _norm_unit(unit)
    mult = UNIT_TO_G.get(u)
    if mult is None:
        return None
    try:
        grams = float(qty) * mult
    except ValueError:
        return None
    if grams <= 0 or grams > 60000:
        return None
    return grams


def parse_pack_size_display(text: str) -> float | None:
    """Parse explicit displays like '8 pk / 6.75 fl oz' as total package.

    Grocery displays using "ct/count" usually pair a count with total net
    weight ("6 ct / 20 oz" bagels). Container words like bottles/pouches use
    per-container weight ("8 pk / 6.75 fl oz" juice boxes).
    """
    if not text:
        return None
    m = PACK_SIZE_RE.search(text)
    if not m:
        return None
    count_n = int(m.group(1))
    count_unit = (m.group(2) or "").lower()
    unit_g = _size_grams(m.group(3), m.group(4))
    if unit_g is None:
        return None
    if count_unit in {"ct", "count"}:
        return unit_g
    return count_n * unit_g


def parse_largest_size(text: str) -> float | None:
    candidates = parse_size_candidates(text)
    if not candidates:
        return None
    return max(candidates)


def parse_size_candidates(text: str) -> list[float]:
    if not text or DIMENSION_RE.search(text):
        return []
    cleaned = PREPARED_YIELD_RE.sub("", text)
    cleaned = NUTRITION_CLAIM_RE.sub("", cleaned)
    candidates = []
    for qty, unit in SIZE_RE.findall(cleaned):
        grams = _size_grams(qty, unit)
        if grams is not None:
            candidates.append(grams)
    return candidates


def parse_count(text: str) -> int | None:
    counts = []
    for m in COUNT_RE.finditer(text or ""):
        try:
            counts.append(int(m.group(1)))
        except ValueError:
            pass
    return max(counts) if counts else None


def parse_pack(text: str) -> int | None:
    packs = []
    for m in PACK_RE.finditer(text or ""):
        for group in m.groups():
            if group:
                try:
                    packs.append(int(group))
                except ValueError:
                    pass
    return max(packs) if packs else None


def likely_per_unit_multipack(name: str, canonical_path: str, expected_g: float) -> bool:
    text = name or ""
    path = canonical_path or ""
    count_n = parse_count(text)
    if count_n and expected_g < 15:
        return True
    if path.lower().startswith("sports & wellness"):
        return True
    if count_n and path.lower().startswith("snack > fruit snacks") and expected_g < 100:
        return True
    if count_n and path.lower().startswith("frozen > ice pops") and expected_g < 125:
        return True
    if count_n and BEVERAGE_PATH_RE.search(canonical_path or "") and expected_g < 700:
        return True
    if PER_UNIT_CONTAINER_RE.search(text) and expected_g < 250:
        return True
    if SMALL_PER_UNIT_RE.search(text) and expected_g < 125:
        return True
    return False


def choose_expected_grams(name: str, size_display: str) -> tuple[float | None, str]:
    pack_display = parse_pack_size_display(size_display or "")
    if pack_display is not None:
        return pack_display, "size_display_pack"

    display_g = parse_largest_size(size_display or "")
    name_g = parse_largest_size(name or "")
    candidates: list[tuple[float, str]] = []
    if display_g is not None:
        candidates.append((display_g, "size_display"))
    if name_g is not None:
        candidates.append((name_g, "name"))
    if not candidates:
        return None, ""
    return max(candidates, key=lambda item: item[0])


def planned_fix(row: tuple) -> dict | None:
    upc, name, grams, cents, size_display, canonical_path = row
    if not upc or not name or not grams or grams <= 0:
        return None

    expected_g, source = choose_expected_grams(name, size_display or "")
    if expected_g is None or expected_g <= 0:
        return None

    ratio = float(grams) / expected_g
    count_n = parse_count(name)
    pack_n = parse_pack(name)

    # Case-pack rows are usually legitimate when actual grams match pack * size.
    if pack_n and abs(ratio - pack_n) <= max(0.35, pack_n * 0.08):
        return None

    reason = ""
    new_grams = expected_g
    if ratio >= 4.5:
        if likely_per_unit_multipack(name, canonical_path or "", expected_g):
            return None
        reason = "size_display_overinflated"
        if pack_n and source != "size_display_pack":
            name_sizes = parse_size_candidates(name or "")
            already_total = any(
                s < expected_g and abs((expected_g / pack_n) - s) <= max(2.0, s * 0.2)
                for s in name_sizes
            )
            if not already_total:
                new_grams = expected_g * pack_n
                reason = "pack_size_overinflated"
    elif count_n and count_n >= 2 and abs(ratio - count_n) <= max(0.35, count_n * 0.08):
        if likely_per_unit_multipack(name, canonical_path or "", expected_g):
            return None
        reason = "count_multiplied_total_package_size"
    else:
        return None

    return {
        "upc": upc,
        "name": name,
        "canonical_path": canonical_path or "",
        "size_display": size_display or "",
        "source": source,
        "reason": reason,
        "count_n": count_n or "",
        "pack_n": pack_n or "",
        "old_grams": round(float(grams), 3),
        "new_grams": round(new_grams, 3),
        "ratio": round(ratio, 3),
        "cents": int(cents or 0),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    con = sqlite3.connect(str(DB))
    cur = con.cursor()
    cur.execute(
        """SELECT DISTINCT upc, name, grams, cents, size_display, consensus_canonical
           FROM priced_products
           WHERE available=1
             AND IFNULL(non_food_path, 0)=0
             AND grams>0
             AND cents>0
             AND name IS NOT NULL"""
    )
    fixes = []
    for row in cur.fetchall():
        fix = planned_fix(row)
        if fix:
            fixes.append(fix)
    fixes.sort(key=lambda r: (-float(r["ratio"]), r["name"]))

    if args.limit:
        preview = fixes[:args.limit]
    else:
        preview = fixes[:25]

    print(f"candidate UPC fixes: {len(fixes):,}", file=sys.stderr)
    for row in preview:
        print(
            f"  {row['ratio']:>7}x {row['old_grams']:>9}g -> {row['new_grams']:>8}g "
            f"{row['reason']} | {row['name'][:72]}",
            file=sys.stderr,
        )

    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("w", newline="") as handle:
        cols = [
            "upc", "name", "canonical_path", "size_display", "source", "reason",
            "count_n", "pack_n", "old_grams", "new_grams", "ratio", "cents",
        ]
        writer = csv.DictWriter(handle, fieldnames=cols)
        writer.writeheader()
        writer.writerows(fixes)
    print(f"log: {LOG}", file=sys.stderr)

    if args.dry_run:
        con.close()
        return

    if fixes and not BAK.exists():
        print(f"backing up DB -> {BAK.name}", file=sys.stderr)
        shutil.copy(str(DB), str(BAK))

    updated = 0
    for fix in fixes:
        cur.execute(
            """UPDATE priced_products
               SET grams = ?,
                   cpg = CAST(cents AS REAL) / ?
               WHERE upc = ?""",
            (fix["new_grams"], fix["new_grams"], fix["upc"]),
        )
        updated += cur.rowcount
    con.commit()
    con.close()
    print(f"updated rows: {updated:,}", file=sys.stderr)


if __name__ == "__main__":
    main()
