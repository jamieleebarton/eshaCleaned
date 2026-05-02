#!/usr/bin/env python3
"""Hierarchical BFC distribution audit — find misplaced SKUs at the
shallowest level first (family), then type, then deeper.

Concept: At the family level, an Alcohol BFC SKU should be in Beverage.
If 5% land in Pantry/Snack, those 5% are clearly misplaced — much more
useful signal than picking through individual paths.

Output:
  retail_mapper/v2/bfc_family_distribution.csv  — per BFC, distribution
    at family / family>type / 3-segment level
  retail_mapper/v2/bfc_family_outliers.csv      — SKUs at non-dominant
    family for their BFC (priority fix queue)

Console: top 30 BFCs with biggest family-level scatter.
"""
from __future__ import annotations

import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path

V2 = Path(__file__).resolve().parent
AUDIT = V2 / "full_corpus_audit.csv"
DIST_OUT = V2 / "bfc_family_distribution.csv"
OUTLIERS_OUT = V2 / "bfc_family_outliers.csv"

csv.field_size_limit(sys.maxsize)

# Minimum BFC SKU count to bother analyzing
MIN_BFC_SIZE = 20
# Minimum dominance for a level to be considered "the canonical home"
DOMINANCE_THRESHOLD = 0.50


def main() -> None:
    print(f"Reading {AUDIT.name}...")
    rows = list(csv.DictReader(AUDIT.open(encoding="utf-8")))
    print(f"  loaded {len(rows):,} rows")

    # For each BFC, count distribution at multiple prefix depths
    # depth 1 = family only, depth 2 = family > type, depth 3 = family>type>variant
    bfc_dist: dict[str, dict[int, Counter]] = defaultdict(lambda: defaultdict(Counter))
    bfc_total: dict[str, int] = defaultdict(int)
    bfc_rows: dict[str, list[dict]] = defaultdict(list)

    for r in rows:
        bfc = (r.get("branded_food_category") or "").strip()
        cp = (r.get("canonical_path") or "").strip()
        if not (bfc and cp):
            continue
        segs = cp.split(" > ")
        bfc_total[bfc] += 1
        bfc_rows[bfc].append(r)
        for depth in (1, 2, 3):
            prefix = " > ".join(segs[:depth])
            bfc_dist[bfc][depth][prefix] += 1

    # Write distribution report
    with DIST_OUT.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["bfc", "total_skus", "depth", "prefix", "count", "pct"])
        for bfc in sorted(bfc_total, key=bfc_total.get, reverse=True):
            total = bfc_total[bfc]
            for depth in (1, 2, 3):
                for prefix, n in bfc_dist[bfc][depth].most_common():
                    w.writerow([bfc, total, depth, prefix, n, f"{n/total:.1%}"])
    print(f"  wrote {DIST_OUT.name}")

    # For each BFC with enough SKUs, identify the dominant family. SKUs in
    # non-dominant families are the priority fix queue.
    bfc_dominant_family: dict[str, str] = {}
    for bfc, dists in bfc_dist.items():
        total = bfc_total[bfc]
        if total < MIN_BFC_SIZE:
            continue
        dom_family, dom_n = dists[1].most_common(1)[0]
        if dom_n / total >= DOMINANCE_THRESHOLD:
            bfc_dominant_family[bfc] = dom_family

    n_outliers = 0
    bfc_outlier_breakdown: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    with OUTLIERS_OUT.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=[
            "bfc", "expected_family", "actual_family", "fdc_id",
            "title", "canonical_path", "retail_leaf_path",
        ])
        w.writeheader()
        for bfc, expected in bfc_dominant_family.items():
            for r in bfc_rows[bfc]:
                cp = (r.get("canonical_path") or "").strip()
                actual_family = cp.split(" > ", 1)[0]
                if actual_family != expected:
                    n_outliers += 1
                    bfc_outlier_breakdown[bfc][actual_family] += 1
                    w.writerow({
                        "bfc": bfc,
                        "expected_family": expected,
                        "actual_family": actual_family,
                        "fdc_id": r.get("fdc_id", ""),
                        "title": (r.get("title") or "")[:120],
                        "canonical_path": cp,
                        "retail_leaf_path": (r.get("retail_leaf_path") or "")[:200],
                    })
    print(f"  wrote {OUTLIERS_OUT.name}: {n_outliers:,} family-level outlier SKUs")

    # Console: top 30 worst-offender BFCs
    print()
    print("=" * 100)
    print(f"TOP 30 BFCs WITH FAMILY-LEVEL SCATTER (>= {MIN_BFC_SIZE} SKUs)")
    print("=" * 100)
    breakdown_list = sorted(
        bfc_outlier_breakdown.items(),
        key=lambda x: -sum(x[1].values()),
    )
    for bfc, families in breakdown_list[:30]:
        total = bfc_total[bfc]
        expected = bfc_dominant_family[bfc]
        n_misplaced = sum(families.values())
        print(f"\n  BFC={bfc!r}  total={total:,}  expected={expected!r}")
        print(f"    {n_misplaced:,} SKUs ({n_misplaced/total:.1%}) in WRONG family:")
        for fam, n in sorted(families.items(), key=lambda x: -x[1]):
            print(f"      [{n:>5,}] {fam}")


if __name__ == "__main__":
    main()
