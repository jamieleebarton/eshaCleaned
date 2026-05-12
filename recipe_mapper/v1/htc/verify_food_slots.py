#!/usr/bin/env python3
"""Verify HTC food slots and check digits across emitted artifacts."""
from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
V1 = HERE.parent
REPO = V1.parent.parent
sys.path.insert(0, str(V1))

from htc.encoder import crockford_check  # noqa: E402

csv.field_size_limit(sys.maxsize)

DEFAULT_FILES = [
    V1 / "output" / "consensus_htc_tagged.csv",
    V1 / "output" / "recipe_ingredient_htc_tagged.csv",
    REPO / "recipe_pricing" / "output" / "api_cache_htc_tagged.csv",
]


def valid_check(code: str) -> bool:
    return len(code) == 8 and crockford_check(code[:7]) == code[7]


def scan_file(path: Path) -> dict[str, object]:
    rows = bad = food00 = 0
    distinct_codes: set[str] = set()
    with path.open(encoding="utf-8", errors="replace", newline="") as handle:
        for row in csv.DictReader(handle):
            rows += 1
            code = row.get("htc_code") or ""
            distinct_codes.add(code)
            if not valid_check(code):
                bad += 1
            if (row.get("htc_food") or code[2:4]) == "00":
                food00 += 1
    return {
        "path": str(path),
        "rows": rows,
        "distinct_codes": len(distinct_codes),
        "bad_check_digits": bad,
        "food_slot_00_rows": food00,
    }


def verify_retail_spots(path: Path) -> list[str]:
    by_identity: dict[str, Counter[str]] = defaultdict(Counter)
    wanted = {
        "Garlic", "Onions", "Leeks", "Shallots",
        "Cheddar", "Mozzarella", "Parmesan",
        "Milk", "Bagels",
    }
    with path.open(encoding="utf-8", errors="replace", newline="") as handle:
        for row in csv.DictReader(handle):
            pid = row.get("product_identity_fixed") or ""
            if pid in wanted:
                by_identity[pid][row.get("htc_code") or ""] += 1
    failures: list[str] = []
    if by_identity["Garlic"] and by_identity["Onions"]:
        if by_identity["Garlic"].most_common(1)[0][0] == by_identity["Onions"].most_common(1)[0][0]:
            failures.append("Garlic and Onions still share their modal HTC code")
    if by_identity["Cheddar"] and by_identity["Mozzarella"]:
        if by_identity["Cheddar"].most_common(1)[0][0] == by_identity["Mozzarella"].most_common(1)[0][0]:
            failures.append("Cheddar and Mozzarella still share their modal HTC code")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="*", type=Path, default=DEFAULT_FILES)
    args = parser.parse_args()

    failed = False
    for path in args.files:
        if not path.exists():
            print(f"missing: {path}")
            failed = True
            continue
        report = scan_file(path)
        print(report)
        if report["bad_check_digits"]:
            failed = True

    retail = V1 / "output" / "consensus_htc_tagged.csv"
    if retail.exists():
        spot_failures = verify_retail_spots(retail)
        for failure in spot_failures:
            print(f"FAIL: {failure}")
        failed = failed or bool(spot_failures)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
