#!/usr/bin/env python3
"""A2 — Empty-grams audit.

Find lines where grams_resolved is 0 but the display text contains a
measurable quantity (digit + unit-keyword), and the line isn't an
intentional zero-grams line ("to taste", "for serving", "optional").

These are silent underprice contributors — the planner adds the recipe
without paying for these ingredients.

Outputs:
  recipe_pricing/audit_empty_grams.csv     — top patterns by canonical_path
"""
from __future__ import annotations
import csv, re, sys
from collections import Counter, defaultdict
from pathlib import Path

csv.field_size_limit(2**30)
ROOT = Path(__file__).resolve().parents[1]
RECIPES = ROOT / "recipe_mapper" / "v1" / "output" / "recipes_unified.csv"
TAX = ROOT / "recipe_mapper" / "v1" / "output" / "recipe_ingredient_taxonomy_v2.csv"
OUT = ROOT / "recipe_pricing" / "audit_empty_grams.csv"

# A measurable-quantity pattern: digit (or ½/¼/⅓/etc.) + unit-keyword
QTY_RE = re.compile(
    r"\b\d+(?:[\.\/]\d+)?\s*(?:cup|cups|tbsp|tablespoon|tablespoons|tsp|teaspoon|teaspoons|"
    r"lb|lbs|pound|pounds|oz|ounce|ounces|fl\s?oz|gram|grams|g\b|kg|ml|liter|litre|"
    r"can|cans|jar|jars|box|boxes|bottle|bottles|piece|pieces|stalk|head|clove|cloves)",
    re.I,
)
QTY_FRACT = re.compile(r"[½¼¾⅓⅔⅛⅜⅝⅞]")

# Skip lines that are intentionally zero-grams
INTENTIONAL_ZERO = (
    "to taste", "for serving", "for garnish", "as needed",
    "optional", "for sprinkling", "for dusting", "for topping",
    "to drizzle", "for drizzling", "for finishing",
    "pinch of", "dash of",
)


def has_measurable_qty(s: str) -> bool:
    if not s: return False
    if QTY_RE.search(s): return True
    if QTY_FRACT.search(s) and re.search(r"(cup|tbsp|tsp|oz|lb|gram)", s, re.I):
        return True
    return False


def main():
    # Build ingredient_item → canonical_path lookup from taxonomy_v2
    ing_to_cp: dict[str, str] = {}
    if TAX.exists():
        with TAX.open() as f:
            r = csv.DictReader(f)
            for row in r:
                k = (row.get("ingredient_item") or "").lower().strip()
                cp = (row.get("canonical_path") or "").strip()
                if k and cp:
                    ing_to_cp[k] = cp
        print(f"loaded {len(ing_to_cp):,} ingredient → canonical_path", file=sys.stderr)

    n_total = 0; n_zero = 0; n_silent = 0
    by_path: Counter = Counter()
    by_path_recipes: dict[str, list] = defaultdict(list)
    detail_rows: list[dict] = []
    skipped = Counter()

    with RECIPES.open() as f:
        r = csv.DictReader(f)
        for row in r:
            n_total += 1
            if n_total % 500_000 == 0:
                print(f"  {n_total:,} lines processed", file=sys.stderr)
            try: g = float(row.get("grams_resolved") or 0)
            except: g = 0
            if g > 0: continue
            n_zero += 1
            disp = (row.get("display") or "").lower()
            if any(p in disp for p in INTENTIONAL_ZERO):
                skipped["intentional"] += 1
                continue
            if not has_measurable_qty(disp):
                skipped["no_qty"] += 1
                continue
            n_silent += 1
            ing = (row.get("ingredient_item") or "").lower().strip()
            cp = ing_to_cp.get(ing) or "(unknown path)"
            by_path[cp] += 1
            if len(by_path_recipes[cp]) < 5:
                by_path_recipes[cp].append({
                    "rid": row.get("recipe_id",""),
                    "display": (row.get("display","") or "")[:80],
                    "ing": ing,
                })

    print(f"\nrows: {n_total:,}", file=sys.stderr)
    print(f"  grams=0 total:          {n_zero:,}  ({n_zero*100/n_total:.1f}%)", file=sys.stderr)
    print(f"  zeroed but measurable:  {n_silent:,}  (silent underprice)", file=sys.stderr)
    print(f"  skipped intentional:    {skipped['intentional']:,}", file=sys.stderr)
    print(f"  skipped no-quantity:    {skipped['no_qty']:,}", file=sys.stderr)

    # Emit top-25 patterns
    out_rows = []
    for cp, n in by_path.most_common(50):
        sample = by_path_recipes[cp][0] if by_path_recipes[cp] else {}
        out_rows.append({
            "canonical_path": cp,
            "n_silent_zero_lines": n,
            "sample_recipe": sample.get("rid",""),
            "sample_display": sample.get("display",""),
            "sample_ingredient": sample.get("ing",""),
        })
    OUT.parent.mkdir(parents=True, exist_ok=True)
    if out_rows:
        with OUT.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(out_rows[0].keys()))
            w.writeheader()
            for r in out_rows: w.writerow(r)

    print(f"\n→ {OUT}  ({len(out_rows)} top patterns)", file=sys.stderr)


if __name__ == "__main__":
    main()
