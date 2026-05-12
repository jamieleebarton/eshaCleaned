#!/usr/bin/env python3
"""Auto-generate buy_form_path_overrides for the long tail of gap items
in coverage_per_buy_form.csv.

For each canonical_buy_form whose current canonical_path has no products,
search priced_products for the canonical_path where products with all the
canonical's noun words actually live. Emit:

  recipe_pricing/buy_form_path_overrides_auto.csv
    auto-confident overrides (≥5 products, in a food-category top)
  recipe_pricing/buy_form_path_overrides_review.csv
    uncertain matches the operator should eyeball
  recipe_pricing/buy_form_no_match.csv
    items with no match at all (genuinely missing from priced_products)

After running, manually append the auto-file rows to
buy_form_path_overrides.csv (or merge programmatically).
"""
from __future__ import annotations

import csv
import sqlite3
import sys
from pathlib import Path

csv.field_size_limit(sys.maxsize)

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "recipe_pricing" / "data" / "priced_products_v2.db"
COVERAGE = ROOT / "recipe_pricing" / "coverage_per_buy_form.csv"
OUT_AUTO = ROOT / "recipe_pricing" / "buy_form_path_overrides_auto.csv"
OUT_REVIEW = ROOT / "recipe_pricing" / "buy_form_path_overrides_review.csv"
OUT_NOMATCH = ROOT / "recipe_pricing" / "buy_form_no_match.csv"

SOFT = {"fresh","dried","ground","powdered","whole","crushed","chopped","diced","sliced",
        "minced","grated","shredded","frozen","raw","cooked","canned","jarred","pickled",
        "the","a","an","of","and","or","with","for","in","to","on","small","medium","large",
        "extra","big","tiny"}

FOOD_TOPS = ("Pantry", "Produce", "Dairy", "Frozen", "Bakery", "Beverage",
             "Snack", "Meat & Seafood", "Meal")

# Items where automatic match is almost always wrong — skip them
SKIP_BUY_FORMS = {
    # canonical names that are too short or too generic to auto-match safely
    "and", "or", "of", "with",
}


def words_of(s: str) -> list[str]:
    return [w for w in s.lower().replace("-", " ").split() if w and w not in SOFT]


def main() -> int:
    if not DB.exists():
        raise SystemExit(f"missing {DB}")
    if not COVERAGE.exists():
        raise SystemExit(f"missing {COVERAGE}")
    con = sqlite3.connect(str(DB))
    cur = con.cursor()

    n_processed = 0
    n_auto = 0
    n_review = 0
    n_nomatch = 0
    auto_rows = []
    review_rows = []
    nomatch_rows = []

    with COVERAGE.open() as f:
        for row in csv.DictReader(f):
            if row.get("has_sku_at_path") == "yes":
                continue
            bf = (row.get("canonical_buy_form") or "").strip()
            if not bf or bf in SKIP_BUY_FORMS:
                continue
            n_processed += 1
            try:
                rc = int(row.get("recipe_count") or 0)
            except ValueError:
                rc = 0

            nouns = words_of(bf)
            if not nouns:
                continue
            where = " AND ".join("LOWER(name) LIKE '%' || ? || '%'" for _ in nouns)
            sql = f"""
                SELECT consensus_canonical, COUNT(*) FROM priced_products
                WHERE {where}
                  AND available=1 AND grams>0 AND cents>0
                  AND consensus_canonical NOT LIKE 'Non-Food%'
                  AND consensus_canonical != ''
                GROUP BY consensus_canonical
                ORDER BY 2 DESC LIMIT 5
            """
            cur.execute(sql, nouns)
            rows = cur.fetchall()

            # Pick best food-category match
            chosen = None
            for cp, n in rows:
                if any(cp.startswith(t) for t in FOOD_TOPS):
                    chosen = (cp, n)
                    break
            if not chosen and rows:
                chosen = rows[0]

            if not chosen:
                n_nomatch += 1
                nomatch_rows.append({
                    "canonical_buy_form": bf,
                    "recipe_count": rc,
                    "current_path": row.get("canonical_path", ""),
                    "reason": "no products contain all canonical noun words",
                })
                continue

            cp, n_products = chosen
            # Confidence: ≥5 products AND in a food top → auto. Else review.
            if n_products >= 5 and any(cp.startswith(t) for t in FOOD_TOPS):
                n_auto += 1
                auto_rows.append({
                    "canonical_buy_form": bf.lower(),
                    "canonical_path": cp,
                    "reason": f"auto: {n_products} products at this path",
                })
            else:
                n_review += 1
                review_rows.append({
                    "canonical_buy_form": bf,
                    "recipe_count": rc,
                    "current_path": row.get("canonical_path", ""),
                    "suggested_path": cp,
                    "n_products": n_products,
                    "reason": "uncertain (low count or non-food top)",
                })

    OUT_AUTO.parent.mkdir(parents=True, exist_ok=True)
    with OUT_AUTO.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["canonical_buy_form", "canonical_path", "reason"])
        w.writeheader()
        w.writerows(auto_rows)
    with OUT_REVIEW.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=[
            "canonical_buy_form", "recipe_count", "current_path",
            "suggested_path", "n_products", "reason",
        ])
        w.writeheader()
        review_rows.sort(key=lambda r: -r["recipe_count"])
        w.writerows(review_rows)
    with OUT_NOMATCH.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=[
            "canonical_buy_form", "recipe_count", "current_path", "reason",
        ])
        w.writeheader()
        nomatch_rows.sort(key=lambda r: -r["recipe_count"])
        w.writerows(nomatch_rows)

    print(f"\nprocessed:    {n_processed:,} gap canonical_buy_form values", file=sys.stderr)
    print(f"  auto-confident:    {n_auto:,}  → {OUT_AUTO}", file=sys.stderr)
    print(f"  review-needed:     {n_review:,}  → {OUT_REVIEW}", file=sys.stderr)
    print(f"  no-match:          {n_nomatch:,}  → {OUT_NOMATCH}", file=sys.stderr)
    print(f"\nTotal recipe-volume coverage potential:", file=sys.stderr)
    auto_recipe_total = sum(int(r.get("reason","").split()[1] or 0) if r["reason"].startswith("auto:") else 0 for r in auto_rows)
    print(f"  if all auto applied:  surfaces ~{auto_recipe_total:,} additional product matches", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
