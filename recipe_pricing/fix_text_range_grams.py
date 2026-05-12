#!/usr/bin/env python3
"""F1 v2 — Catch text-range gram bugs that round-2's F1 missed.

Round-2's fix_range_lower_bound_grams.py only patched lines where
grams_source == "range_lower_bound" AND grams_resolved > grams_blob × 5.

Some bugs slip through with:
  (a) grams_source blank (resolver didn't tag the source)
  (b) ratio between 3 and 5 (still wrong, just less dramatically)

Both have a "X to Y" or "X–Y" range in the display text and grams_blob holds
the correct leading-qty value while grams_resolved was multiplied by the
range's lower bound.

Predicate (any of):
  - grams_source contains "range" AND grams_resolved > grams_blob × 3
  - grams_resolved > grams_blob × 3 AND display contains a digit-range pattern
    ("X to Y", "X–Y", "X-Y" with whitespace) AND grams_resolved > 200g

Idempotent. Atomic file replace.

Usage:
  python3 recipe_pricing/fix_text_range_grams.py [--dry-run]
"""
from __future__ import annotations
import argparse, csv, os, re, sys, tempfile
from pathlib import Path

csv.field_size_limit(2**30)
ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "recipe_mapper" / "v1" / "output" / "recipes_unified.csv"

# "1 to 2", "3-4", "30–35", "1⁄4 to 1⁄2"
RANGE_RE = re.compile(r"\b\d+(?:[\.\/⁄]\d+)?\s*(?:to|[-–—])\s*\d+(?:[\.\/⁄]\d+)?\b", re.I)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--ratio-threshold", type=float, default=3.0)
    args = ap.parse_args()

    src = CSV_PATH
    if not src.exists():
        print(f"missing {src}", file=sys.stderr); sys.exit(1)

    rows_seen = 0; fixed = 0
    samples = []

    def should_fix(row: dict) -> tuple[bool, float, float]:
        try: blob = float(row.get("grams_blob") or 0)
        except: blob = 0
        try: res = float(row.get("grams_resolved") or 0)
        except: res = 0
        if blob <= 0 or res <= blob * args.ratio_threshold: return (False, blob, res)
        src_field = (row.get("grams_source") or "").lower()
        disp = row.get("display") or ""
        if "range" in src_field:
            return (True, blob, res)
        # Need range pattern in text and meaningful absolute value to avoid
        # over-correcting tiny spice lines
        if RANGE_RE.search(disp) and res > 200:
            return (True, blob, res)
        return (False, blob, res)

    if args.dry_run:
        with src.open() as f:
            r = csv.DictReader(f)
            for row in r:
                rows_seen += 1
                ok, blob, res = should_fix(row)
                if not ok: continue
                fixed += 1
                if len(samples) < 20:
                    samples.append((row["recipe_id"], (row.get("display","") or "")[:55], res, blob))
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
                ok, blob, res = should_fix(row)
                if ok:
                    fixed += 1
                    if len(samples) < 20:
                        samples.append((row["recipe_id"], (row.get("display","") or "")[:55], res, blob))
                    row["grams_resolved"] = f"{blob:.2f}"
                    row["grams_source"] = "text_range_clamped_to_blob"
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
