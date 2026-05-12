#!/usr/bin/env python3
"""Repair qty/unit parse failures caused by unicode fraction slash.

Rows like "1⁄2 head lettuce" previously came through as qty=1, unit blank
because the extractor handled vulgar fraction characters (½) but not the
digit + U+2044 fraction slash form (1⁄2). This pass only repairs rows whose
display contains a unicode fraction slash and where the current unit is blank.
It does not touch grams; run normalize_grams_to_sr28.py afterward so the
normal reviewed/SR28 bridge owns gram changes.
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RECIPES = ROOT / "recipe_mapper" / "v1" / "output" / "recipes_unified.csv"
LOG = ROOT / "recipe_pricing" / "repair_unicode_fraction_qty_units_log.csv"

sys.path.insert(0, str(ROOT / "recipe_mapper" / "v1"))
from htc.qty_units import extract_qty_unit  # noqa: E402

csv.field_size_limit(2**30)

FRACTION_SLASHES = ("⁄", "∕", "／")


def has_fraction_slash(value: str) -> bool:
    return any(ch in (value or "") for ch in FRACTION_SLASHES)


def fmt_qty(value: float) -> str:
    return f"{value:.6g}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    scanned = candidates = changed = 0
    samples: list[dict[str, str]] = []

    def process(row: dict[str, str], writer: csv.DictWriter | None = None) -> None:
        nonlocal scanned, candidates, changed
        scanned += 1
        display = row.get("display") or ""
        if not has_fraction_slash(display):
            if writer:
                writer.writerow(row)
            return
        candidates += 1
        current_unit = (row.get("unit") or "").strip()
        if current_unit:
            if writer:
                writer.writerow(row)
            return
        qty, unit, _residual = extract_qty_unit(display)
        if qty is None or not unit:
            if writer:
                writer.writerow(row)
            return
        old_qty = row.get("qty") or ""
        row["qty"] = fmt_qty(qty)
        row["unit"] = unit
        changed += 1
        if len(samples) < 25:
            samples.append({
                "recipe_id": row.get("recipe_id") or "",
                "item": row.get("ingredient_item") or "",
                "display": display,
                "old_qty": old_qty,
                "new_qty": row["qty"],
                "unit": unit,
            })
        if writer:
            writer.writerow(row)

    if args.dry_run:
        with RECIPES.open() as f:
            reader = csv.DictReader(f)
            for row in reader:
                process(row)
    else:
        tmp_fd, tmp_path = tempfile.mkstemp(prefix=".unicode_fraction_qty_", suffix=".csv", dir=str(RECIPES.parent))
        os.close(tmp_fd)
        try:
            with RECIPES.open() as f_in, open(tmp_path, "w", newline="") as f_out:
                reader = csv.DictReader(f_in)
                writer = csv.DictWriter(f_out, fieldnames=reader.fieldnames)
                writer.writeheader()
                for row in reader:
                    process(row, writer)
            os.replace(tmp_path, RECIPES)
        except Exception:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            raise

        with LOG.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["recipe_id", "item", "display", "old_qty", "new_qty", "unit"])
            writer.writeheader()
            writer.writerows(samples)

    print(f"rows scanned:      {scanned:,}")
    print(f"slash candidates: {candidates:,}")
    print(f"qty/unit repaired:{changed:,}")
    print("sample repairs:")
    for sample in samples[:15]:
        print(
            f"  rid={sample['recipe_id']} {sample['item']!r}: "
            f"{sample['display']!r} {sample['old_qty']} -> {sample['new_qty']} {sample['unit']}"
        )
    if not args.dry_run:
        print(f"log written: {LOG}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
