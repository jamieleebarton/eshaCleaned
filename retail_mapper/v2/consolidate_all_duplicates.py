#!/usr/bin/env python3
"""Consolidate ALL duplicate canonical_paths in one pass.

Rules in order. Each is exact-prefix or exact-equality match. The first
matching rule wins. Plus a final dedupe-segments pass.

Categories:
  A. Singular/plural unify (Bars→Bar, Cones→Cone, etc.)
  C1. Beverage > Mixes → Pantry > Mixes (DeepSeek-invented duplicate)
  C2. Beverage > Coffee Creamer → Dairy > Cream > Coffee Creamer
  C3. Snack > Dried Fruit → Pantry > Dried Fruit (consolidate to one bucket)
  C4. Beverage > Protein Powders → Pantry > Protein Powders
  C5. Meal > Pizza > Calzone → Frozen > Pizza > Calzone
  C6. Meal > Breakfast Burritos → Frozen > Breakfast > Burritos

DELIBERATELY NOT consolidating:
  - Canned X vs Fresh X (Pantry > Canned Vegetables > Spinach vs Produce > Vegetables > Spinach)
  - Cheese Crisps vs Cheese (Snack > Cheese Crisps > Cheddar vs Dairy > Cheese > Cheddar)
  - Cookie Dough vs Cookies (raw vs finished)
  - Whole Grain / Sea Salt leaf cross-family pairs (those need real reroutes via evidence,
    not segment rewrites — they're claim-leaf misclassifications)
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
LOG = V2 / "consolidate_all_duplicates_log.csv"

csv.field_size_limit(sys.maxsize)

# (rule_name, old, new, mode) — mode: 'prefix' = match path.startswith(old); 'exact' = path == old
RULES: list[tuple[str, str, str, str]] = [
    # ─── C2: Coffee Creamer (consolidate to Dairy > Cream > Coffee Creamer) ───
    ("C2-creamer-liquid",       "Beverage > Coffee Creamer > Liquid", "Dairy > Cream > Coffee Creamer > Liquid", "exact"),
    ("C2-creamer-concentrated", "Beverage > Coffee Creamer > Concentrated", "Dairy > Cream > Coffee Creamer > Concentrated", "exact"),
    ("C2-creamer-prefix",       "Beverage > Coffee Creamer > ", "Dairy > Cream > Coffee Creamer > ", "prefix"),
    ("C2-creamer-bare",         "Beverage > Coffee Creamer", "Dairy > Cream > Coffee Creamer", "exact"),

    # ─── C1: Beverage > Mixes (consolidate to Pantry > Mixes) ───
    ("C1-bev-mixes-prefix",     "Beverage > Mixes > ", "Pantry > Mixes > ", "prefix"),
    ("C1-bev-mixes-bare",       "Beverage > Mixes", "Pantry > Mixes", "exact"),

    # ─── C4: Protein Powders → Pantry ───
    ("C4-protein-powder-prefix", "Beverage > Protein Powders > ", "Pantry > Protein Powders > ", "prefix"),
    ("C4-protein-powder-bare",  "Beverage > Protein Powders", "Pantry > Protein Powders", "exact"),

    # ─── C3: Dried Fruit (consolidate to Pantry > Dried Fruit) ───
    # Snack > Dried Fruit and Pantry > Dried Fruit overlap heavily; pick Pantry.
    ("C3-snack-dried-fruit-prefix", "Snack > Dried Fruit > ", "Pantry > Dried Fruit > ", "prefix"),
    ("C3-snack-dried-fruit-bare",   "Snack > Dried Fruit", "Pantry > Dried Fruit", "exact"),

    # ─── C5: Calzone — frozen wins ───
    ("C5-calzone",              "Meal > Pizza > Calzone", "Frozen > Pizza > Calzone", "exact"),

    # ─── C6: Breakfast Burritos — frozen wins ───
    ("C6-bfast-burritos",       "Meal > Breakfast Burritos", "Frozen > Breakfast > Burritos", "exact"),
    ("C6-burrito-bowl",         "Meal > Composite Dishes > Burrito Bowl", "Frozen > Single Entrees > Burrito > Bowl", "exact"),

    # ─── A: Singular/plural unify (always to singular) ───
    ("A-ice-cream-bars",        "Frozen > Ice Cream > Bars", "Frozen > Ice Cream > Bar", "exact"),
    ("A-ice-cream-bars-prefix", "Frozen > Ice Cream > Bars > ", "Frozen > Ice Cream > Bar > ", "prefix"),
    ("A-ice-cream-cones",       "Frozen > Ice Cream > Cones", "Frozen > Ice Cream > Cone", "exact"),
    ("A-ice-cream-sandwiches",  "Frozen > Ice Cream > Sandwiches", "Frozen > Ice Cream > Sandwich", "exact"),
    ("A-ic-sandwiches-leaf",    "Frozen > Ice Cream > Ice Cream Sandwiches", "Frozen > Ice Cream > Ice Cream Sandwich", "exact"),
    ("A-ground-beef-patties",   "Meat & Seafood > Beef > Ground Beef > Patties", "Meat & Seafood > Beef > Ground Beef > Patty", "exact"),
    ("A-ground-beef-patties-pre", "Meat & Seafood > Beef > Ground Beef > Patties > ", "Meat & Seafood > Beef > Ground Beef > Patty > ", "prefix"),
    ("A-decorated-cookies",     "Snack > Cookies > Decorated Cookies", "Snack > Cookies > Decorated Cookie", "exact"),
    ("A-pb-cookies",            "Snack > Cookies > Peanut Butter Cookies", "Snack > Cookies > Peanut Butter Cookie", "exact"),
    ("A-oatmeal-raisin",        "Snack > Cookies > Oatmeal Raisin Cookies", "Snack > Cookies > Oatmeal Raisin Cookie", "exact"),
    ("A-chicken-sandwiches",    "Frozen > Appetizers > Chicken Sandwiches", "Frozen > Appetizers > Chicken Sandwich", "exact"),
    ("A-sugar-cookies",         "Bakery > Cookie Dough > Sugar Cookies", "Bakery > Cookie Dough > Sugar Cookie", "exact"),
    ("A-smores-cereal",         "Pantry > Cereal > S'Mores Cereal", "Pantry > Cereal > S'mores Cereal", "exact"),
    ("A-smores-bars",           "Snack > Bars > Granola Bars > Chewy > S'Mores", "Snack > Bars > Granola Bars > Chewy > S'mores", "exact"),
]


def dedupe_segments(path: str) -> tuple[str, bool]:
    if not path or " > " not in path: return path, False
    segs = path.split(" > ")
    seen: set[str] = set()
    out: list[str] = []
    for s in segs:
        k = s.lower()
        if k in seen: continue
        seen.add(k); out.append(s)
    new = " > ".join(out)
    return new, new != path


def apply_rules(path: str) -> tuple[str, str | None]:
    if not path: return path, None
    rule_used: str | None = None
    for name, old, new, mode in RULES:
        if mode == "prefix" and path.startswith(old):
            path = new + path[len(old):]
            rule_used = name
            break
        if mode == "exact" and path == old:
            path = new
            rule_used = name
            break
    deduped, was_dd = dedupe_segments(path)
    if was_dd:
        rule_used = (rule_used + "+dedupe") if rule_used else "dedupe-only"
    return deduped, rule_used


def main() -> None:
    tmp = AUDIT.with_suffix(".consolidating.csv")
    log_rows: list[dict] = []
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
    for rule in sorted(rule_counts, key=lambda k: -rule_counts[k]):
        print(f"    {rule:<35} {rule_counts[rule]:>5}")

    if log_rows:
        cols = list(log_rows[0].keys())
        with LOG.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=cols)
            w.writeheader()
            w.writerows(log_rows)
        print(f"  wrote {LOG.name}")


if __name__ == "__main__":
    main()
