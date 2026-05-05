#!/usr/bin/env python3
"""P4 — Build the gram-weight resolver: HTC code → unit → grams.

The SR-28 food_portion.csv is the gram-weight Rosetta stone, but legacy SR
data left measure_unit_id=9999 ('undetermined') and put the actual unit name
in the `modifier` text column. We parse it.

Source pools:
  data/sr28_csv/sr_legacy_food.csv  → NDB_No → fdc_id
  data/sr28_csv/food_portion.csv    → fdc_id → modifier (unit) + gram_weight
  data/sr28_csv/measure_unit.csv    → standard unit ids (rare for SR-28)

Bridge: consensus_htc_tagged.csv has htc_code + sr28_code per retail row.
Group by htc_code, pull all sr28_codes, look up portions, aggregate.

Output: htc_gram_weights.csv  (htc_code, unit, grams, n_sources, sr_codes)
        sr28_gram_weights.csv (sr28_ndb_no, fdc_id, description, unit, grams)
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path

csv.field_size_limit(sys.maxsize)

ROOT = Path(__file__).resolve().parents[2]
SR28 = ROOT / "data" / "sr28_csv"
HERE = Path(__file__).resolve().parent
DEFAULT_TAGGED = HERE / "output" / "consensus_htc_tagged.csv"
OUT_HTC = HERE / "output" / "htc_gram_weights.csv"
OUT_SR28 = HERE / "output" / "sr28_gram_weights.csv"
OUT_DEFAULTS = HERE / "output" / "htc_group_default_grams.csv"


# Normalize messy modifier text → canonical unit. Returns None if not a unit.
UNIT_RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"^\s*(?:1\s*)?cup\b", re.I), "cup"),
    (re.compile(r"^\s*(?:1\s*)?tbsp|tablespoon", re.I), "tbsp"),
    (re.compile(r"^\s*(?:1\s*)?tsp|teaspoon", re.I), "tsp"),
    (re.compile(r"^\s*(?:1\s*)?fl\.?\s*oz|fluid ounce", re.I), "fl_oz"),
    (re.compile(r"^\s*(?:1\s*)?(?:dry\s*)?oz\b|ounce", re.I), "oz"),
    (re.compile(r"^\s*(?:1\s*)?\bml\b|milliliter", re.I), "ml"),
    (re.compile(r"^\s*(?:1\s*)?\bl\b\s*$|^liter|^litre", re.I), "l"),
    (re.compile(r"^\s*(?:1\s*)?\bg\b\s*$|^gram", re.I), "g"),
    (re.compile(r"^\s*(?:1\s*)?\bkg\b|kilogram", re.I), "kg"),
    (re.compile(r"^\s*(?:1\s*)?\blb\b|pound", re.I), "lb"),
    (re.compile(r"^\s*(?:1\s*)?quart", re.I), "quart"),
    (re.compile(r"^\s*(?:1\s*)?pint", re.I), "pint"),
    (re.compile(r"^\s*(?:1\s*)?gallon", re.I), "gallon"),
    (re.compile(r"^\s*(?:1\s*)?dash", re.I), "dash"),
    (re.compile(r"^\s*(?:1\s*)?pinch", re.I), "pinch"),
    (re.compile(r"^\s*(?:1\s*)?slice", re.I), "slice"),
    (re.compile(r"^\s*(?:1\s*)?stick", re.I), "stick"),
    (re.compile(r"^\s*(?:1\s*)?package|pkg", re.I), "package"),
    (re.compile(r"^\s*(?:1\s*)?serving", re.I), "serving"),
    (re.compile(r"^\s*(?:1\s*)?piece|^\s*1\b", re.I), "piece"),
]


def normalize_unit(modifier: str) -> str | None:
    if not modifier:
        return None
    s = modifier.strip().lower()
    for pat, name in UNIT_RULES:
        if pat.search(s):
            return name
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tagged", type=Path, default=DEFAULT_TAGGED)
    args = ap.parse_args()

    OUT_HTC.parent.mkdir(parents=True, exist_ok=True)

    # ── Step 1: build SR-28 NDB → fdc_id and reverse lookups
    print("[1/4] reading sr_legacy_food.csv")
    ndb_to_fdc: dict[str, str] = {}
    with (SR28 / "sr_legacy_food.csv").open() as f:
        r = csv.DictReader(f)
        for row in r:
            ndb_to_fdc[row["NDB_number"]] = row["fdc_id"]
    fdc_to_ndb = {v: k for k, v in ndb_to_fdc.items()}
    print(f"  {len(ndb_to_fdc):,} NDB→fdc rows")

    # ── Step 2: build fdc_id → description from food.csv
    print("[2/4] reading food.csv (sr_legacy_food only, for descriptions)")
    fdc_desc: dict[str, str] = {}
    with (SR28 / "food.csv").open() as f:
        r = csv.DictReader(f)
        for row in r:
            if row.get("data_type") == "sr_legacy_food":
                fdc_desc[row["fdc_id"]] = row.get("description", "")
    print(f"  {len(fdc_desc):,} sr_legacy_food rows")

    # ── Step 3: aggregate food_portion.csv by (fdc_id, normalized_unit)
    print("[3/4] reading food_portion.csv and parsing modifier column for units")
    portions: dict[tuple[str, str], list[float]] = defaultdict(list)
    raw_count = 0
    matched_count = 0
    with (SR28 / "food_portion.csv").open() as f:
        r = csv.DictReader(f)
        for row in r:
            raw_count += 1
            fdc = row["fdc_id"]
            mod = row.get("modifier", "") or ""
            unit = normalize_unit(mod)
            if not unit:
                continue
            try:
                gw = float(row.get("gram_weight") or 0)
            except ValueError:
                continue
            if gw <= 0:
                continue
            try:
                amt = float(row.get("amount") or 1)
            except ValueError:
                amt = 1.0
            if amt > 0:
                portions[(fdc, unit)].append(gw / amt)
                matched_count += 1
    print(f"  {raw_count:,} raw portion rows; {matched_count:,} matched a known unit")

    # Write SR-28 grams CSV
    with OUT_SR28.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["fdc_id", "ndb_number", "description", "unit",
                    "grams_per_unit_median", "n_observations"])
        for (fdc, unit), gws in sorted(portions.items()):
            w.writerow([fdc, fdc_to_ndb.get(fdc, ""), fdc_desc.get(fdc, ""),
                        unit, f"{statistics.median(gws):.2f}", len(gws)])
    print(f"  -> {OUT_SR28} ({len(portions):,} rows)")

    # ── Step 4: bridge HTC ↔ SR-28 via consensus_htc_tagged.csv
    print("[4/4] joining consensus tags → SR-28 portions per HTC code")
    htc_to_sr_codes: dict[str, set[str]] = defaultdict(set)
    htc_to_group: dict[str, str] = {}
    with args.tagged.open() as f:
        r = csv.DictReader(f)
        for row in r:
            code = row.get("htc_code") or ""
            sr = (row.get("sr28_code") or "").strip()
            if not code or not sr:
                continue
            htc_to_sr_codes[code].add(sr)
            htc_to_group.setdefault(code, row.get("htc_group", ""))
    print(f"  {len(htc_to_sr_codes):,} HTC codes have at least 1 SR-28 link in consensus")

    # ── Aggregate per HTC code
    htc_unit_grams: dict[tuple[str, str], list[float]] = defaultdict(list)
    htc_unit_sources: dict[tuple[str, str], set[str]] = defaultdict(set)
    for code, sr_set in htc_to_sr_codes.items():
        for sr in sr_set:
            fdc = ndb_to_fdc.get(sr)
            if not fdc:
                continue
            for (fdc_p, unit), gws in portions.items():
                if fdc_p == fdc:
                    htc_unit_grams[(code, unit)].extend(gws)
                    htc_unit_sources[(code, unit)].add(sr)

    with OUT_HTC.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["htc_code", "htc_group", "unit",
                    "grams_per_unit_median", "n_sr_codes", "sr_codes_sample"])
        for (code, unit), gws in sorted(htc_unit_grams.items()):
            sources = sorted(htc_unit_sources[(code, unit)])
            w.writerow([
                code, htc_to_group.get(code, ""), unit,
                f"{statistics.median(gws):.2f}",
                len(sources),
                "|".join(sources[:10]),
            ])
    print(f"  -> {OUT_HTC} ({len(htc_unit_grams):,} (htc_code,unit) rows)")

    # ── Group-level fallbacks: for HTC codes without retail SR-28 links,
    # use the median across all HTCs in the same group.
    group_unit_grams: dict[tuple[str, str], list[float]] = defaultdict(list)
    for (code, unit), gws in htc_unit_grams.items():
        g = htc_to_group.get(code, "")
        if g:
            group_unit_grams[(g, unit)].extend(gws)
    with OUT_DEFAULTS.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["htc_group", "unit", "grams_per_unit_median", "n_observations"])
        for (g, unit), gws in sorted(group_unit_grams.items()):
            w.writerow([g, unit, f"{statistics.median(gws):.2f}", len(gws)])
    print(f"  -> {OUT_DEFAULTS} ({len(group_unit_grams):,} group-level rows)")

    # ── Sanity probes
    print()
    print("=== sanity probes ===")
    probes = [
        ("Salt, table",          "tsp"),
        ("Salt, table",          "cup"),
        ("Spices, cardamom",     "tsp"),
        ("Spices, saffron",      "tsp"),
        ("Spices, cloves, ground", "tsp"),
        ("Milk, whole, 3.25% milkfat, with added vitamin D", "cup"),
        ("Milk, whole, 3.25% milkfat, with added vitamin D", "fl_oz"),
        ("Sugar, granulated",     "cup"),
        ("Butter, salted",        "tbsp"),
        ("Olive oil",             "tbsp"),
    ]
    desc_to_fdc = {v: k for k, v in fdc_desc.items()}
    for desc, unit in probes:
        fdc = desc_to_fdc.get(desc)
        if not fdc:
            # try a startswith match
            for k, v in fdc_desc.items():
                if v.startswith(desc.split(",")[0]):
                    fdc = k
                    break
        if not fdc:
            print(f"  '{desc}' [{unit}] -> [no fdc]")
            continue
        gws = portions.get((fdc, unit), [])
        gpu = statistics.median(gws) if gws else None
        print(f"  '{desc[:50]}' [{unit}] -> {gpu} g  (from {len(gws)} obs, fdc={fdc})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
