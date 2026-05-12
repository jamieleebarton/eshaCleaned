#!/usr/bin/env python3
"""Patch recipes_unified.csv: when a line's display text contains the pattern
"(N per pound|lb|kilo|kg|piece|each)" AND grams_source=="range_lower_bound"
AND grams_resolved looks suspiciously larger than grams_blob, the parser
mis-read the parenthetical as a quantity. Fix by setting grams_resolved=grams_blob.

Affects 5 known recipes (verified via audit_residual_flags), e.g.
recipe 469462 line 11: "1 1/2 pounds raw shrimp (31-40 per pound)" was
parsed as 31 lb (=14053g) instead of 1.5 lb (=680g).

Idempotent. Writes to a tempfile + atomic rename.

Usage:
  python3 recipe_pricing/fix_per_pound_parenthetical_grams.py [--dry-run]
"""
from __future__ import annotations
import argparse, csv, os, re, sys, tempfile
from pathlib import Path
csv.field_size_limit(2**30)

ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "recipe_mapper" / "v1" / "output" / "recipes_unified.csv"

# Match "(31 per pound)" / "(31-40 per pound)" / "(15 to 20 per pound)" etc.
PER_PATTERN = re.compile(
    r"\([0-9]+\s*(?:to|[-–—])?\s*[0-9]*\s*(?:count\s+)?per\s+(?:pound|lb|kilo|kg|piece|each|oz|ounce)\b",
    re.I,
)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    src = CSV_PATH
    if not src.exists():
        print(f"missing {src}", file=sys.stderr); sys.exit(1)

    fixed = 0
    rows_seen = 0
    samples = []
    out_dir = src.parent
    if args.dry_run:
        # Just count
        with src.open() as f:
            r = csv.DictReader(f)
            for row in r:
                rows_seen += 1
                if (row.get("grams_source") == "range_lower_bound"
                    and PER_PATTERN.search(row.get("display","") or "")):
                    blob = float(row.get("grams_blob") or 0)
                    res  = float(row.get("grams_resolved") or 0)
                    if blob > 0 and res > blob * 2:
                        fixed += 1
                        if len(samples) < 10:
                            samples.append((row["recipe_id"], row.get("display","")[:60], blob, res))
        print(f"\nscanned {rows_seen:,} rows", file=sys.stderr)
        print(f"would fix {fixed} rows", file=sys.stderr)
        for s in samples:
            print(f"  rid={s[0]}  '{s[1]}'  {s[3]} → {s[2]}", file=sys.stderr)
        return

    tmp_fd, tmp_path = tempfile.mkstemp(prefix=".unified_patch_", suffix=".csv", dir=str(out_dir))
    os.close(tmp_fd)
    try:
        with src.open() as f_in, open(tmp_path, "w", newline="") as f_out:
            r = csv.DictReader(f_in)
            w = csv.DictWriter(f_out, fieldnames=r.fieldnames)
            w.writeheader()
            for row in r:
                rows_seen += 1
                if (row.get("grams_source") == "range_lower_bound"
                    and PER_PATTERN.search(row.get("display","") or "")):
                    try: blob = float(row.get("grams_blob") or 0)
                    except: blob = 0
                    try: res  = float(row.get("grams_resolved") or 0)
                    except: res = 0
                    if blob > 0 and res > blob * 2:
                        fixed += 1
                        if len(samples) < 10:
                            samples.append((row["recipe_id"], row.get("display","")[:60], blob, res))
                        row["grams_resolved"] = f"{blob:.2f}"
                        row["grams_source"] = "per_pound_parenthetical_fixed"
                w.writerow(row)
        # Atomic rename
        os.replace(tmp_path, src)
    except Exception:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise

    print(f"\npatched {fixed} rows in {src}", file=sys.stderr)
    for s in samples:
        print(f"  rid={s[0]}  '{s[1]}'  {s[3]:.0f}g → {s[2]:.0f}g", file=sys.stderr)


if __name__ == "__main__":
    main()
