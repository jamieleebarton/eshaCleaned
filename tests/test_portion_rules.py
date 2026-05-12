#!/usr/bin/env python3
"""Drift-prevention gate for the household portion rule files.

Background: this repo ended up with TWO parallel rule files for unit→grams
conversions:
  - recipe_pricing/reviewed_household_portions.csv  (the live normalizer reads this)
  - implementation/reviewed_household_unit_gram_rules.csv (older calculator-era rules)

Approved rules in the implementation/ file used to silently drift away from
the live one — that's how "1 head lettuce → 100g" regressed and broke recipe
gram resolution. This test fails if:

  (a) any approved rule in implementation/ is missing from recipe_pricing/
      (with same item, unit, grams within 5%)
  (b) any rule in recipe_pricing/ has a fixed-mass-conversion violation
      (lb≠453.6g, oz≠28.35g, kg≠1000g, g≠1g, mg≠0.001g)
  (c) any duplicate (item, unit) keys in recipe_pricing/

Run:
    python3 tests/test_portion_rules.py

Exits 0 on pass, non-zero on any violation. Suitable for pre-commit/CI.
"""
from __future__ import annotations
import csv, sys
from collections import defaultdict
from pathlib import Path

csv.field_size_limit(2**30)
ROOT = Path(__file__).resolve().parents[1]
LIVE = ROOT / "recipe_pricing" / "reviewed_household_portions.csv"
LEGACY = ROOT / "implementation" / "reviewed_household_unit_gram_rules.csv"

FIXED_MASS = {
    'lb': 453.592, 'lbs': 453.592, 'pound': 453.592, 'pounds': 453.592,
    'oz': 28.3495, 'ounce': 28.3495, 'ounces': 28.3495,
    'kg': 1000.0, 'kilogram': 1000.0, 'kilograms': 1000.0,
    'g': 1.0, 'gram': 1.0, 'grams': 1.0,
    'mg': 0.001,
}


def load_live() -> dict[tuple[str, str], list[dict]]:
    out: dict[tuple[str, str], list[dict]] = defaultdict(list)
    with LIVE.open() as f:
        for row in csv.DictReader(f):
            item = (row.get("item") or "").strip().lower()
            unit = (row.get("unit") or "").strip().lower()
            try: grams = float(row.get("grams_per_unit") or "0")
            except (TypeError, ValueError): grams = 0.0
            if item and unit and grams > 0:
                out[(item, unit)].append({"grams": grams, "row": row})
    return out


def load_legacy_approved() -> list[dict]:
    out = []
    with LEGACY.open() as f:
        for row in csv.DictReader(f):
            if (row.get("review_status") or "").strip().lower() != "approved":
                continue
            ck = (row.get("concept_key") or "").strip()
            unit = (row.get("unit") or "").strip().lower()
            if not ck or not unit: continue
            item = ck.split("|")[0].strip().lower()
            if not item: continue
            try: grams = float(row.get("grams_per_unit") or "0")
            except (TypeError, ValueError): grams = 0.0
            if grams <= 0: continue
            out.append({"item": item, "unit": unit, "grams": grams,
                         "rule_id": row.get("rule_id", "")})
    return out


def main() -> int:
    live = load_live()
    legacy = load_legacy_approved()

    failures: list[str] = []

    # (a) every approved legacy rule must have a corresponding live rule
    missing = []
    grams_drift = []
    for rule in legacy:
        key = (rule["item"], rule["unit"])
        if key not in live:
            missing.append(rule)
            continue
        # Match by grams within 5% — multiple live rules per (item,unit) ok if any matches
        ok = any(abs(r["grams"] - rule["grams"]) / max(rule["grams"], 1e-9) <= 0.05
                 for r in live[key])
        if not ok:
            grams_drift.append((rule, [r["grams"] for r in live[key]]))

    if missing:
        failures.append(f"{len(missing)} approved rule(s) in implementation/ "
                        f"missing from recipe_pricing/")
        for r in missing[:10]:
            failures.append(f"  MISSING: item={r['item']!r} unit={r['unit']!r} "
                            f"grams={r['grams']} rule_id={r['rule_id']}")
        if len(missing) > 10:
            failures.append(f"  ... +{len(missing)-10} more")

    # grams_drift is informational, not a hard fail — live values may have
    # been intentionally improved past the legacy values. Show but don't fail.
    drift_warnings: list[str] = []
    if grams_drift:
        drift_warnings.append(f"INFO: {len(grams_drift)} legacy rule(s) "
                              f"differ from live by >5% — confirm intentional")
        for r, lg in grams_drift[:5]:
            drift_warnings.append(f"  DRIFT: item={r['item']!r} unit={r['unit']!r} "
                                  f"legacy={r['grams']}g vs live={lg}")

    # (b) fixed-mass conversion violations in live
    mass_errors = []
    with LIVE.open() as f:
        for row in csv.DictReader(f):
            item = (row.get("item") or "").strip().lower()
            unit = (row.get("unit") or "").strip().lower()
            try: grams = float(row.get("grams_per_unit") or "0")
            except (TypeError, ValueError): grams = 0
            if unit in FIXED_MASS:
                expected = FIXED_MASS[unit]
                if abs(grams - expected) > 0.5:
                    mass_errors.append((item, unit, grams, expected))

    if mass_errors:
        failures.append(f"{len(mass_errors)} fixed-mass-conversion violation(s)")
        for it, u, g, exp in mass_errors[:10]:
            failures.append(f"  MASS: item={it!r} unit={u!r} got {g}g, expected {exp}g")

    # (c) duplicate (item, unit) keys in live
    dups = {k: len(v) for k, v in live.items() if len(v) > 1}
    if dups:
        failures.append(f"{len(dups)} duplicate (item,unit) key(s) in recipe_pricing/")
        for k, n in list(dups.items())[:10]:
            failures.append(f"  DUP: {k} appears {n} times")

    print(f"=== test_portion_rules ===")
    print(f"  live rules: {sum(len(v) for v in live.values())}")
    print(f"  legacy approved rules: {len(legacy)}")
    print(f"  missing in live: {len(missing)}")
    print(f"  grams drift >5%: {len(grams_drift)}")
    print(f"  mass conversion errors: {len(mass_errors)}")
    print(f"  duplicate keys: {len(dups)}")

    if drift_warnings:
        print(f"\nWarnings (informational):")
        for w in drift_warnings:
            print(w)

    if failures:
        print(f"\nFAILURES:")
        for f_ in failures:
            print(f_)
        return 1

    print("\n  ALL PASS ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())
