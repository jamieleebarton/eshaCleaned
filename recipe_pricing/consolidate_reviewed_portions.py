#!/usr/bin/env python3
"""Consolidate legacy household unit rules into the active portion authority.

Active authority:
  recipe_pricing/reviewed_household_portions.csv

Legacy compatibility copy:
  implementation/reviewed_household_unit_gram_rules.csv

The legacy file used concept_key-style rows. This script copies any approved
legacy rule that is missing from the active file, preserving facet-bearing
concept keys when needed. Existing active rows win.
"""
from __future__ import annotations

import argparse
import csv
import os
import shutil
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ACTIVE = ROOT / "recipe_pricing" / "reviewed_household_portions.csv"
LEGACY = ROOT / "implementation" / "reviewed_household_unit_gram_rules.csv"
BACKUP = ACTIVE.with_suffix(".csv.before_portion_consolidation")

FIELDNAMES = [
    "item",
    "unit",
    "grams_per_unit",
    "portion_label",
    "display_contains",
    "display_excludes",
    "evidence",
    "reason",
]


def norm_grams(value: str | float) -> str:
    grams = float(value)
    text = f"{grams:.4f}".rstrip("0").rstrip(".")
    return text or "0"


def legacy_item(concept_key: str) -> str:
    ck = (concept_key or "").strip().lower()
    if ck == "*":
        return "*"
    if ck.endswith("|||") and "|" not in ck[:-3]:
        return ck[:-3]
    return ck


def load_active() -> tuple[list[dict[str, str]], set[tuple[str, str, str]]]:
    rows: list[dict[str, str]] = []
    keys: set[tuple[str, str, str]] = set()
    with ACTIVE.open(newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            rows.append({name: row.get(name, "") for name in FIELDNAMES})
            item = (row.get("item") or "").strip().lower()
            unit = (row.get("unit") or "").strip().lower()
            grams_raw = (row.get("grams_per_unit") or "").strip()
            if item and unit and grams_raw:
                try:
                    keys.add((item, unit, norm_grams(grams_raw)))
                except ValueError:
                    continue
    return rows, keys


def build_missing_rows(active_keys: set[tuple[str, str, str]]) -> list[dict[str, str]]:
    missing: list[dict[str, str]] = []
    with LEGACY.open(newline="") as handle:
        for row in csv.DictReader(handle):
            if (row.get("review_status") or "").strip() != "approved":
                continue
            item = legacy_item(row.get("concept_key") or "")
            unit = (row.get("unit") or "").strip().lower()
            grams_raw = (row.get("grams_per_unit") or "").strip()
            if not item or not unit or not grams_raw:
                continue
            try:
                grams = norm_grams(grams_raw)
            except ValueError:
                continue
            key = (item, unit, grams)
            if key in active_keys:
                continue
            missing.append({
                "item": item,
                "unit": unit,
                "grams_per_unit": grams,
                "portion_label": "",
                "display_contains": "",
                "display_excludes": "",
                "evidence": (
                    "migrated from implementation/reviewed_household_unit_gram_rules.csv "
                    f"({row.get('rule_id') or 'legacy_rule'})"
                ),
                "reason": row.get("rationale") or "legacy approved household unit rule",
            })
            active_keys.add(key)
    return missing


def write_rows(rows: list[dict[str, str]], dry_run: bool) -> None:
    if dry_run:
        return
    if not BACKUP.exists():
        shutil.copy(str(ACTIVE), str(BACKUP))
    tmp_fd, tmp_path = tempfile.mkstemp(prefix=".reviewed_portions_", suffix=".csv", dir=str(ACTIVE.parent))
    os.close(tmp_fd)
    try:
        with open(tmp_path, "w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
            writer.writeheader()
            writer.writerows(rows)
        os.replace(tmp_path, ACTIVE)
    except Exception:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not ACTIVE.exists():
        raise SystemExit(f"missing active portion authority: {ACTIVE}")
    if not LEGACY.exists():
        raise SystemExit(f"missing legacy compatibility file: {LEGACY}")

    active_rows, active_keys = load_active()
    missing = build_missing_rows(active_keys)
    rows = active_rows + missing
    write_rows(rows, args.dry_run)

    print(f"active rows before: {len(active_rows):,}")
    print(f"missing legacy rows added: {len(missing):,}")
    print(f"active rows after: {len(rows):,}")
    if args.dry_run:
        print("mode: dry-run")
    else:
        print(f"updated: {ACTIVE}")


if __name__ == "__main__":
    main()
