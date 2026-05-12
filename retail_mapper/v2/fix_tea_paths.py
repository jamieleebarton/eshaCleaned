#!/usr/bin/env python3
"""Fix tea-path naming in retail_leaf_path.

Issues:
  1. 'Herb Tea' segment   →  'Herbal Tea'
  2. Apostrophe-stripped possessives ('Cat S Claw' → "Cat's Claw")
  3. Misnested flavors:  'Beverage > Tea > Herbal {flavor} > X'  where
     {flavor} is NOT a tea-variety word →  insert 'Tea' parent:
     'Beverage > Tea > Herbal Tea > {flavor} > X'

Operates on `retail_leaf_path` column. Writes log to fix_tea_paths_log.csv.
"""
from __future__ import annotations

import csv
import re
import shutil
import sys
from collections import defaultdict
from pathlib import Path

V2 = Path("/Users/jamiebarton/Desktop/esha_audit_bundle/retail_mapper/v2")
AUDIT = V2 / "full_corpus_audit.csv"
LOG = V2 / "fix_tea_paths_log.csv"

csv.field_size_limit(sys.maxsize)

# Possessive fixes: "X S Y" where the X+S+Y is a known/likely possessive
POSSESSIVES = [
    (re.compile(r"\bCat S Claw\b", re.I),       "Cat's Claw"),
    (re.compile(r"\bSolomon S Seal\b", re.I),   "Solomon's Seal"),
    (re.compile(r"\bSt John S Wort\b", re.I),   "St John's Wort"),
    (re.compile(r"\bShepherd S Purse\b", re.I), "Shepherd's Purse"),
    (re.compile(r"\bMother S Milk\b", re.I),    "Mother's Milk"),
    (re.compile(r"\bMonk S Pepper\b", re.I),    "Monk's Pepper"),
]

# Words that legitimately follow "Herbal" inside the tea tree
TEA_VARIETIES = {"tea", "blend", "infusion", "tisane"}


def fix_herb_tea(path: str) -> tuple[str, bool]:
    """Replace any 'Herb Tea' segment with 'Herbal Tea'."""
    segs = path.split(" > ")
    new = [s if s.lower() != "herb tea" else "Herbal Tea" for s in segs]
    new_path = " > ".join(new)
    return new_path, new_path != path


def fix_possessives(path: str) -> tuple[str, bool]:
    new = path
    for rx, repl in POSSESSIVES:
        new = rx.sub(repl, new)
    return new, new != path


def fix_misnested_herbal(path: str) -> tuple[str, bool]:
    """If a tea path has segment 'Herbal X' where X is not a tea-variety,
    rewrite as 'Herbal Tea > X'."""
    if not path.startswith("Beverage > Tea > "):
        return path, False
    segs = path.split(" > ")
    out: list[str] = []
    changed = False
    for s in segs:
        m = re.match(r"^Herbal\s+(.+)$", s, re.I)
        if m and m.group(1).split()[0].lower() not in TEA_VARIETIES:
            out.append("Herbal Tea")
            out.append(m.group(1))
            changed = True
        else:
            out.append(s)
    return " > ".join(out), changed


def main() -> None:
    tmp = AUDIT.with_suffix(".fixing.csv")
    log_rows: list[dict] = []
    rule_counts: dict[str, int] = defaultdict(int)
    n_total = 0

    with AUDIT.open(encoding="utf-8", newline="") as fin, \
         tmp.open("w", encoding="utf-8", newline="") as fout:
        rdr = csv.DictReader(fin)
        wtr = csv.DictWriter(fout, fieldnames=rdr.fieldnames)
        wtr.writeheader()
        for r in rdr:
            n_total += 1
            old = r.get("retail_leaf_path", "") or ""
            new = old
            applied: list[str] = []

            new, ch = fix_herb_tea(new)
            if ch: applied.append("herb-tea-to-herbal-tea")

            new, ch = fix_misnested_herbal(new)
            if ch: applied.append("misnested-herbal-flavor")

            new, ch = fix_possessives(new)
            if ch: applied.append("possessive-restore")

            if applied:
                for n in applied:
                    rule_counts[n] += 1
                r["retail_leaf_path"] = new
                log_rows.append({
                    "fdc_id": r.get("fdc_id", ""),
                    "title": (r.get("title", "") or "")[:60],
                    "rules": ",".join(applied),
                    "old_path": old,
                    "new_path": new,
                })
            wtr.writerow(r)

    shutil.move(str(tmp), str(AUDIT))
    print(f"  total rows: {n_total:,}")
    print(f"  rows updated: {len(log_rows):,}")
    print(f"  per-rule:")
    for n in sorted(rule_counts, key=lambda k: -rule_counts[k]):
        print(f"    {n:<30} {rule_counts[n]:>5}")

    if log_rows:
        cols = list(log_rows[0].keys())
        with LOG.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=cols)
            w.writeheader()
            w.writerows(log_rows)
        print(f"  wrote {LOG.name}")


if __name__ == "__main__":
    main()
