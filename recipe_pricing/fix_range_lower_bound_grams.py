#!/usr/bin/env python3
"""Generalized fix for the range_lower_bound parenthetical bug.

Symptom: a recipe line like
  "1 lb ground beef (80-85% lean)"
  "3/4 lb butter, softened to 65-70°F"
  "2/3 cup water (110-115°F)"
  "1 cup ground beef (15-22% fat)"
gets parsed with the parenthetical's first number as the quantity, so
qty=80 lb / 65 lb / 110 cups / 15 oz, blowing grams_resolved up by 10×–80×
the true value. In every case observed, `grams_blob` already holds the
correct (leading-quantity) value.

Fix predicate: rows where
  grams_source == "range_lower_bound"
  AND grams_blob > 0
  AND grams_resolved > grams_blob × 5

→ set grams_resolved = grams_blob; mark grams_source = "range_clamped_to_blob".

Idempotent. Atomic file replace.

Usage:
  python3 recipe_pricing/fix_range_lower_bound_grams.py [--dry-run]
"""
from __future__ import annotations
import argparse, csv, os, sys, tempfile
from pathlib import Path

csv.field_size_limit(2**30)
ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "recipe_mapper" / "v1" / "output" / "recipes_unified.csv"
RATIO_THRESHOLD = 5.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    src = CSV_PATH
    if not src.exists():
        print(f"missing {src}", file=sys.stderr); sys.exit(1)

    rows_seen = 0; fixed = 0
    samples = []

    if args.dry_run:
        with src.open() as f:
            r = csv.DictReader(f)
            for row in r:
                rows_seen += 1
                if row.get("grams_source") != "range_lower_bound": continue
                try: blob = float(row.get("grams_blob") or 0)
                except: continue
                try: res = float(row.get("grams_resolved") or 0)
                except: continue
                if blob <= 0 or res <= blob * RATIO_THRESHOLD: continue
                fixed += 1
                if len(samples) < 15:
                    samples.append((row["recipe_id"], (row.get("display","") or "")[:60], res, blob))
        print(f"\nscanned {rows_seen:,} rows", file=sys.stderr)
        print(f"would fix {fixed:,} rows", file=sys.stderr)
        for s in samples:
            print(f"  rid={s[0]:>6}  '{s[1]}'  {s[2]:.0f}g → {s[3]:.0f}g", file=sys.stderr)
        return

    out_dir = src.parent
    tmp_fd, tmp_path = tempfile.mkstemp(prefix=".unified_patch_", suffix=".csv", dir=str(out_dir))
    os.close(tmp_fd)
    try:
        with src.open() as f_in, open(tmp_path, "w", newline="") as f_out:
            r = csv.DictReader(f_in)
            w = csv.DictWriter(f_out, fieldnames=r.fieldnames)
            w.writeheader()
            for row in r:
                rows_seen += 1
                if row.get("grams_source") == "range_lower_bound":
                    try: blob = float(row.get("grams_blob") or 0)
                    except: blob = 0
                    try: res = float(row.get("grams_resolved") or 0)
                    except: res = 0
                    if blob > 0 and res > blob * RATIO_THRESHOLD:
                        fixed += 1
                        if len(samples) < 15:
                            samples.append((row["recipe_id"], (row.get("display","") or "")[:60], res, blob))
                        row["grams_resolved"] = f"{blob:.2f}"
                        row["grams_source"] = "range_clamped_to_blob"
                w.writerow(row)
        os.replace(tmp_path, src)
    except Exception:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise

    print(f"\npatched {fixed:,} rows in {src}", file=sys.stderr)
    for s in samples:
        print(f"  rid={s[0]:>6}  '{s[1]}'  {s[2]:.0f}g → {s[3]:.0f}g", file=sys.stderr)


if __name__ == "__main__":
    main()
