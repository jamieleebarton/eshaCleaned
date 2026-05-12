#!/usr/bin/env python3
"""Repair grams_resolved double-conversion bug in recipes_unified.csv.

When grams_resolved is wildly higher than grams_blob (ratio >= 2) AND the
display contains a parenthetical weight range like "(7-10 pounds)" or
"(700-900 g)", the qty parser has misinterpreted a number from the range as
a multiplier. In those cases, trust grams_blob.

Also: if a line's display shows pounds/lbs but grams_resolved < 50g, the
unit-parsing failed entirely; trust grams_blob.

Backs up to recipes_unified.csv.before_grams_fix.
"""
from __future__ import annotations
import csv, re, shutil, sys
from pathlib import Path
csv.field_size_limit(2**30)

ROOT = Path("/Users/jamiebarton/Desktop/esha_audit_bundle")
SRC = ROOT / "recipe_mapper" / "v1" / "output" / "recipes_unified.csv"
BAK = SRC.with_suffix(".csv.before_grams_fix")
TMP = SRC.with_suffix(".csv.tmp")

RANGE_WEIGHT = re.compile(
    r"(?:\b(?:about|approximately|approx\.?|around|~)\s+|\()"
    r"\d+(?:\.\d+)?[\s\-]*(?:to|\-|–|—)[\s\-]*\d+(?:\.\d+)?\s*"
    r"(?:lb|lbs|pound|pounds|kg|g|gram|oz|ounce|ounces)\b",
    re.I,
)
# Plain parenthetical weight (no "about" prefix needed): "(7-10 lbs)"
PARENS_WEIGHT = re.compile(
    r"\(([^)]*\d+(?:\.\d+)?[\s\-]*(?:to|\-|–|—)[\s\-]*\d+(?:\.\d+)?\s*"
    r"(?:lb|lbs|pound|pounds|kg|g|gram|oz|ounce|ounces)[^)]*)\)",
    re.I,
)
def has_weight_range(s: str) -> bool:
    return bool(PARENS_WEIGHT.search(s) or RANGE_WEIGHT.search(s))
LB_HINT = re.compile(r"\b(lb|lbs|pound|pounds)\b", re.I)


def main():
    if not BAK.exists():
        print(f"backup → {BAK}", file=sys.stderr)
        shutil.copy(str(SRC), str(BAK))

    n_total = 0; n_too_high = 0; n_underflow = 0
    with SRC.open() as fin, TMP.open("w", newline="") as fout:
        rd = csv.DictReader(fin)
        wr = csv.DictWriter(fout, fieldnames=rd.fieldnames)
        wr.writeheader()
        for row in rd:
            n_total += 1
            try:
                gr = float(row.get("grams_resolved") or 0)
                gb = float(row.get("grams_blob") or 0)
            except (ValueError, TypeError):
                wr.writerow(row); continue
            disp = (row.get("display") or "")
            disp_l = disp.lower()

            # Bug A: too-high ratio + parenthetical weight range → trust grams_blob
            if gr > 0 and gb > 0 and gr / gb >= 2 and has_weight_range(disp_l):
                row["grams_resolved"] = f"{gb:.2f}"
                n_too_high += 1
            # Bug B: lb in display but grams_resolved is tiny + grams_blob is sane
            elif gr > 0 and gr < 50 and LB_HINT.search(disp_l) and gb >= 100:
                row["grams_resolved"] = f"{gb:.2f}"
                n_underflow += 1
            wr.writerow(row)

    shutil.move(str(TMP), str(SRC))
    print(f"\nrepaired {n_too_high:,} too-high cases", file=sys.stderr)
    print(f"repaired {n_underflow:,} underflow cases", file=sys.stderr)
    print(f"total lines: {n_total:,}", file=sys.stderr)


if __name__ == "__main__":
    main()
