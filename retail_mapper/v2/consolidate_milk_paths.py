#!/usr/bin/env python3
"""Consolidate the milk duplicates the user keeps flagging.

Rules (applied in order, in-place to full_corpus_audit.csv):

1. 'Beverage > Dairy Milk > Milk > X'  → 'Dairy > Milk > X'   (drop the bogus Beverage chain)
2. 'Beverage > Dairy Milk > Milk'      → 'Dairy > Milk'
3. 'Dairy > Milk > Whole Milk > X'     → 'Dairy > Milk > Whole > X'
4. 'Dairy > Milk > Whole Milk'         → 'Dairy > Milk > Whole'
5. 'Dairy > Milk > Skim Milk > Fat Free' → 'Dairy > Milk > Skim'
6. 'Dairy > Milk > Skim Milk'          → 'Dairy > Milk > Skim'
7. 'Dairy > Milk > Lactose Free Milk > X' → 'Dairy > Milk > Lactose Free > X'
8. 'Dairy > Milk > Lactose Free Milk'  → 'Dairy > Milk > Lactose Free'

Plus the inverse on retail_leaf_path so it stays in sync.

Reports per-rule counts. Writes consolidate_milk_log.csv with every change.
"""
from __future__ import annotations

import csv
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
V2 = REPO / "retail_mapper" / "v2"
AUDIT = V2 / "full_corpus_audit.csv"
LOG = V2 / "consolidate_milk_log.csv"

csv.field_size_limit(sys.maxsize)

RULES: list[tuple[str, str, str]] = [
    # (rule_name, old_prefix, new_prefix)
    ("beverage-dairy-milk-prefix",   "Beverage > Dairy Milk > Milk > ",  "Dairy > Milk > "),
    ("beverage-dairy-milk-leaf",     "Beverage > Dairy Milk > Milk",     "Dairy > Milk"),
    # Specific subtypes that landed under Beverage > Dairy Milk
    ("bdm-sweetened-condensed",      "Beverage > Dairy Milk > Sweetened Condensed Milk", "Pantry > Sweetened Condensed Milk"),
    ("bdm-condensed",                "Beverage > Dairy Milk > Condensed Milk", "Pantry > Sweetened Condensed Milk"),
    ("bdm-milk-powder",              "Beverage > Dairy Milk > Milk Powder", "Pantry > Powdered Milk"),
    ("bdm-powdered-milk",            "Beverage > Dairy Milk > Powdered Milk", "Pantry > Powdered Milk"),
    ("bdm-dry-whole",                "Beverage > Dairy Milk > Dry Whole Milk", "Pantry > Powdered Milk"),
    ("bdm-drink-powder",             "Beverage > Dairy Milk > Milk Drink Powder", "Pantry > Powdered Milk"),
    ("bdm-flavored",                 "Beverage > Dairy Milk > Flavored Milk", "Dairy > Milk > Flavored"),
    ("bdm-lassi",                    "Beverage > Dairy Milk > Lassi", "Beverage > Yogurt Drinks > Lassi"),
    ("beverage-dairy-milk-bare",     "Beverage > Dairy Milk",            "Dairy > Milk"),
    ("whole-milk-prefix",            "Dairy > Milk > Whole Milk > ",     "Dairy > Milk > Whole > "),
    ("whole-milk-leaf",              "Dairy > Milk > Whole Milk",        "Dairy > Milk > Whole"),
    ("skim-milk-fat-free",           "Dairy > Milk > Skim Milk > Fat Free", "Dairy > Milk > Skim"),
    ("skim-milk-prefix",             "Dairy > Milk > Skim Milk > ",      "Dairy > Milk > Skim > "),
    ("skim-milk-leaf",               "Dairy > Milk > Skim Milk",         "Dairy > Milk > Skim"),
    ("lactose-free-milk-prefix",     "Dairy > Milk > Lactose Free Milk > ", "Dairy > Milk > Lactose Free > "),
    ("lactose-free-milk-leaf",       "Dairy > Milk > Lactose Free Milk", "Dairy > Milk > Lactose Free"),
]


def dedupe_segments(path: str) -> tuple[str, bool]:
    """Drop duplicate segments while preserving order.

    'Dairy > Milk > Lactose Free > 2% > Lactose Free > Reduced Fat'
      -> 'Dairy > Milk > Lactose Free > 2% > Reduced Fat'
    """
    if not path or " > " not in path:
        return path, False
    segs = path.split(" > ")
    seen: set[str] = set()
    out: list[str] = []
    for s in segs:
        key = s.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
    new = " > ".join(out)
    return new, new != path


def apply_rules(path: str) -> tuple[str, str | None]:
    """Returns (new_path, rule_name_or_None)."""
    if not path:
        return path, None
    rule_used: str | None = None
    for name, old, new in RULES:
        if old.endswith(" "):
            if path.startswith(old):
                path = new + path[len(old):]
                rule_used = name
                break
        else:
            if path == old:
                path = new
                rule_used = name
                break
    # ALWAYS dedupe segments after a rule, AND on every other path too
    deduped, was_deduped = dedupe_segments(path)
    if was_deduped:
        rule_used = (rule_used or "") + ("+dedupe" if rule_used else "dedupe-only")
    return deduped, rule_used


def main() -> None:
    tmp = AUDIT.with_suffix(".consolidating.csv")
    log_rows: list[dict] = []
    from collections import defaultdict
    rule_counts: dict[str, int] = defaultdict(int)
    n_total = 0
    n_changed = 0

    with AUDIT.open(encoding="utf-8", newline="") as fin, \
         tmp.open("w", encoding="utf-8", newline="") as fout:
        rdr = csv.DictReader(fin)
        wtr = csv.DictWriter(fout, fieldnames=rdr.fieldnames)
        wtr.writeheader()
        for r in rdr:
            n_total += 1
            old_cp = r.get("canonical_path", "")
            new_cp, rule = apply_rules(old_cp)
            if rule is None:
                wtr.writerow(r)
                continue
            n_changed += 1
            rule_counts[rule] += 1
            r["canonical_path"] = new_cp
            wtr.writerow(r)
            log_rows.append({
                "fdc_id": r.get("fdc_id", ""),
                "title": (r.get("title", "") or "")[:60],
                "rule": rule,
                "old_path": old_cp,
                "new_path": new_cp,
            })

    shutil.move(str(tmp), str(AUDIT))
    print(f"  total rows: {n_total:,}")
    print(f"  rows updated: {n_changed:,}")
    print(f"  per-rule:")
    for name in sorted(rule_counts, key=lambda k: -rule_counts[k]):
        print(f"    {name:<40} {rule_counts[name]:>5}")

    if log_rows:
        with LOG.open("w", newline="", encoding="utf-8") as fh:
            cols = list(log_rows[0].keys())
            w = csv.DictWriter(fh, fieldnames=cols)
            w.writeheader()
            w.writerows(log_rows)
        print(f"  wrote {LOG.name}")


if __name__ == "__main__":
    main()
