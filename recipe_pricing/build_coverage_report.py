#!/usr/bin/env python3
"""Coverage report — for every unique recipe ingredient, can we calculate
macros and cost RIGHT NOW?

Calculable means:
  1. We have a canonical_path AND a retail_leaf_path → links to a real
     FDC retail leaf, where Walmart/Kroger products live.
  2. We have at least 1 walmart_hit OR 1 nutrition_hit → a concrete product
     row from which we can read grams + macros + price.

Buckets:
  - covered_full      : walmart_hits>0 AND nutrition_hits>0 (price + macros)
  - covered_macros    : nutrition_hits>0 only (have macros, no price)
  - covered_price     : walmart_hits>0 only (have price, no macros)
  - missing_both      : neither — uncalculable, BIGGEST GAP
  - non_food          : non_food=1 — should be filtered upstream
  - no_path           : no canonical_path at all

Output:
  recipe_pricing/coverage_report.csv
  recipe_pricing/coverage_summary.txt
"""
from __future__ import annotations

import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path

csv.field_size_limit(sys.maxsize)

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "recipe_mapper" / "v1" / "output" / "ingredient_full_audit.csv"
OUT_CSV = ROOT / "recipe_pricing" / "coverage_report.csv"
OUT_SUMMARY = ROOT / "recipe_pricing" / "coverage_summary.txt"


def main() -> int:
    rows = []
    with AUDIT.open() as f:
        for row in csv.DictReader(f):
            try:
                rc = int(row.get("recipe_count", "0") or 0)
                walmart = int(row.get("walmart_hits", "0") or 0)
                nutr = int(row.get("nutrition_hits", "0") or 0)
            except ValueError:
                rc, walmart, nutr = 0, 0, 0
            cp = (row.get("canonical_path") or "").strip()
            rlp = (row.get("retail_leaf_path") or "").strip()
            non_food = (row.get("non_food", "") or "").strip() in ("1", "true", "True")
            if non_food:
                bucket = "non_food"
            elif not cp:
                bucket = "no_path"
            elif walmart > 0 and nutr > 0:
                bucket = "covered_full"
            elif nutr > 0:
                bucket = "covered_macros"
            elif walmart > 0:
                bucket = "covered_price"
            else:
                bucket = "missing_both"
            rows.append({
                "item": row.get("item", ""),
                "recipe_count": rc,
                "canonical_path": cp,
                "retail_leaf_path": rlp,
                "walmart_hits": walmart,
                "nutrition_hits": nutr,
                "join_status": row.get("join_status", ""),
                "non_food": "1" if non_food else "",
                "coverage_bucket": bucket,
            })

    # Item-weighted and recipe-weighted summaries
    item_counts: Counter[str] = Counter(r["coverage_bucket"] for r in rows)
    recipe_counts: defaultdict[str, int] = defaultdict(int)
    for r in rows:
        recipe_counts[r["coverage_bucket"]] += r["recipe_count"]
    total_items = sum(item_counts.values())
    total_recipes = sum(recipe_counts.values())

    # Sort the report: missing_both first by recipe_count desc (the worst
    # gaps that hit most recipes), then covered_macros, then covered_price,
    # then non_food/no_path
    BUCKET_ORDER = ["missing_both", "covered_macros", "covered_price",
                    "non_food", "no_path", "covered_full"]
    rows.sort(key=lambda r: (BUCKET_ORDER.index(r["coverage_bucket"]),
                              -r["recipe_count"]))

    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=[
            "item", "recipe_count", "coverage_bucket",
            "canonical_path", "retail_leaf_path",
            "walmart_hits", "nutrition_hits",
            "join_status", "non_food",
        ])
        w.writeheader()
        w.writerows(rows)

    # Text summary
    lines = []
    lines.append(f"Coverage report — {total_items:,} unique items, {total_recipes:,} recipe-references\n")
    lines.append(f"{'bucket':<20} {'items':>10} {'item_pct':>10} {'recipe_refs':>12} {'recipe_pct':>10}")
    lines.append("-" * 70)
    for b in BUCKET_ORDER:
        ic = item_counts.get(b, 0)
        rc = recipe_counts.get(b, 0)
        lines.append(f"{b:<20} {ic:>10,} {ic/total_items:>10.1%} {rc:>12,} {rc/total_recipes:>10.1%}")
    lines.append("")
    lines.append("Top 30 missing_both by recipe_count (uncalculable items hitting most recipes):")
    missing = [r for r in rows if r["coverage_bucket"] == "missing_both"][:30]
    for r in missing:
        lines.append(f"  [{r['recipe_count']:>5}] {r['item']:<40} cp={r['canonical_path'] or '—'}")

    summary = "\n".join(lines)
    OUT_SUMMARY.write_text(summary + "\n")
    print(summary)
    print(f"\n  → {OUT_CSV}")
    print(f"  → {OUT_SUMMARY}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
