#!/usr/bin/env python3
"""Coverage report — for every recipe line in the cleaned classifier output,
determine whether the calculator CAN actually compute cost + macros for it.

For each line, classify into one of:

  COVERED_FULL       : decision=calculate, has SKU, has FNDDS macros
  COVERED_COST_ONLY  : decision=calculate, has SKU, but no FNDDS macros (no macro calc)
  COVERED_SHOP_ONLY  : decision=shop_only (to_taste/garnish/optional) — has SKU, no qty calc
  SKIP_DERIVATIVE    : decision=skip (intentional)
  REVIEW             : decision=review (unbuyable/nonsense)
  GAP_NO_CANONICAL_PATH    : canonical_buy_form has no buy_form_lookup entry
  GAP_NO_SKU_AT_PATH       : canonical_path has no available products
  GAP_NO_CANONICAL_BUY_FORM: classifier didn't produce a canonical_buy_form

Aggregates per-canonical_buy_form (which buy_forms cause most failures) and
per-recipe (% of recipes that calculate end-to-end vs partial vs blocked).

Outputs:
  recipe_pricing/coverage_per_buy_form.csv    — top gaps by recipe-volume
  recipe_pricing/coverage_per_recipe.csv      — per-recipe status
  recipe_pricing/coverage_summary.txt         — aggregate stats
"""
from __future__ import annotations

import csv
import json
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

csv.field_size_limit(sys.maxsize)

ROOT = Path(__file__).resolve().parents[1]
CLEANED_CLS = ROOT / "recipe_pricing" / "buyability_classifications_cleaned.jsonl"
BUY_FORM_LOOKUP = ROOT / "recipe_pricing" / "buy_form_to_canonical_path.csv"
PRICED_DB = ROOT / "recipe_pricing" / "data" / "priced_products_v2.db"
EXCLUDED_UPCS = ROOT / "recipe_pricing" / "priced_products_excluded.csv"
FNDDS_NUTRIENTS = ROOT / "data" / "fndds" / "fndds_nutrient_lookup.csv"

OUT_BF = ROOT / "recipe_pricing" / "coverage_per_buy_form.csv"
OUT_RECIPE = ROOT / "recipe_pricing" / "coverage_per_recipe.csv"
OUT_SUMMARY = ROOT / "recipe_pricing" / "coverage_summary.txt"


def name_passes_filter_basic(name: str, canonical_buy_form: str) -> bool:
    """Mirror of calculator's any-noun filter — also concat-tolerant
    (cornstarch ↔ corn starch, breadcrumbs ↔ bread crumbs)."""
    nl = name.lower().replace("-", " ")
    nl_nospace = nl.replace(" ", "")
    cl = canonical_buy_form.lower().replace("-", " ")
    SOFT = {"fresh","dried","ground","powdered","whole","crushed","chopped",
            "diced","sliced","minced","grated","shredded","frozen","raw",
            "cooked","canned","jarred","pickled","the","a","an","of","and","or",
            "with","for","in","to","on","small","medium","large","extra","big","tiny"}
    words = [w for w in cl.split() if w and w not in SOFT]
    if not words:
        return True
    for w in words:
        if w in nl or (w + "s") in nl or w.rstrip("s") in nl:
            return True
        if w in nl_nospace or (w + "s") in nl_nospace or w.rstrip("s") in nl_nospace:
            return True
    full_concat = "".join(words)
    if full_concat in nl_nospace or (full_concat + "s") in nl_nospace:
        return True
    return False


def main() -> int:
    print("loading buy_form lookup + overrides...", file=sys.stderr)
    bfl: dict[str, str] = {}
    overridden: set[str] = set()  # canonical_buy_form values that came from manual override
    with BUY_FORM_LOOKUP.open() as f:
        for row in csv.DictReader(f):
            bf = (row.get("canonical_buy_form") or "").lower().strip()
            cp = (row.get("canonical_path") or "").strip()
            if bf and cp:
                bfl[bf] = cp
    overrides_path = ROOT / "recipe_pricing" / "buy_form_path_overrides.csv"
    if overrides_path.exists():
        with overrides_path.open() as f:
            for row in csv.DictReader(f):
                bf = (row.get("canonical_buy_form") or "").lower().strip()
                cp = (row.get("canonical_path") or "").strip()
                if bf and cp:
                    bfl[bf] = cp
                    overridden.add(bf)

    print("loading excluded upcs...", file=sys.stderr)
    excluded: set[str] = set()
    if EXCLUDED_UPCS.exists():
        with EXCLUDED_UPCS.open() as f:
            for row in csv.DictReader(f):
                upc = (row.get("upc") or "").strip()
                if upc:
                    excluded.add(upc)

    print("loading FNDDS macros...", file=sys.stderr)
    fndds_set: set[str] = set()
    with FNDDS_NUTRIENTS.open() as f:
        for row in csv.DictReader(f):
            code = (row.get("fndds_code") or "").strip()
            if code:
                fndds_set.add(code)

    print("indexing priced_products by canonical_path...", file=sys.stderr)
    con = sqlite3.connect(str(PRICED_DB))
    cur = con.cursor()
    cur.execute("""
        SELECT consensus_canonical, upc, name, consensus_fndds
        FROM priced_products
        WHERE consensus_canonical != '' AND available = 1
          AND grams > 0 AND cents > 0
    """)
    path_to_products: defaultdict[str, list[tuple]] = defaultdict(list)
    for cp, upc, name, fndds in cur.fetchall():
        if upc in excluded:
            continue
        path_to_products[cp].append((upc, name or "", fndds or ""))

    # Per-canonical_buy_form: does it have a path? Does the path have a product?
    # Does any product have FNDDS? When canonical_buy_form was manually
    # overridden, we trust the override and skip the noun filter — overrides
    # often map synonyms (scallion → Green Onions, kahlua → Rum).
    bf_status: dict[str, dict] = {}
    def _check_path(cp: str, bf: str, skip_filter: bool):
        """Check a single path for SKUs that match the buy_form. Returns
        (has_sku, has_macros, n_skus)."""
        n = 0; has_sku=False; has_macros=False
        for upc, name, fndds in path_to_products.get(cp, []):
            if not skip_filter and not name_passes_filter_basic(name, bf):
                continue
            has_sku = True; n += 1
            if fndds and fndds in fndds_set:
                has_macros = True
                break
        return has_sku, has_macros, n

    def status_for(bf: str) -> dict:
        if bf in bf_status:
            return bf_status[bf]
        s = {"has_path": False, "has_sku": False, "has_macros": False,
             "n_skus": 0, "path_used": "", "fallback": False}
        cp = bfl.get(bf)
        if cp:
            s["has_path"] = True
            s["path_used"] = cp
            skip_filter = bf in overridden
            has_sku, has_macros, n = _check_path(cp, bf, skip_filter)
            s["has_sku"] = has_sku; s["has_macros"] = has_macros; s["n_skus"] = n
            # ANCESTOR FALLBACK: if no SKUs at leaf, walk UP one level and
            # check if parent has SKUs. Use parent as proxy for cost+macro.
            # Skip Non-Food paths and paths < 3 segments (too generic).
            if not has_sku and " > " in cp and not cp.startswith("Non-Food"):
                segments = cp.split(" > ")
                if len(segments) >= 3:
                    parent = " > ".join(segments[:-1])
                    # Skip the noun filter at parent (we're approximating)
                    has_sku2, has_macros2, n2 = _check_path(parent, bf, True)
                    if has_sku2 and n2 >= 3:
                        s["has_sku"] = True
                        s["has_macros"] = has_macros2
                        s["n_skus"] = n2
                        s["path_used"] = parent
                        s["fallback"] = True
        bf_status[bf] = s
        return s

    # Walk cleaned classifications, classify every line into a coverage bucket
    print("scanning cleaned classifications...", file=sys.stderr)
    line_buckets: Counter = Counter()
    bf_recipe_volume: defaultdict[str, dict] = defaultdict(
        lambda: {"recipe_count": 0, "first_display": ""})
    recipe_status: list[dict] = []

    with CLEANED_CLS.open() as f:
        for n, line in enumerate(f, 1):
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            ings = r.get("ingredients", [])
            cls_list = r.get("classifications", [])
            recipe_buckets = Counter()
            for c in cls_list:
                idx = c.get("line_index")
                ing = ings[idx] if idx is not None and idx < len(ings) else {}
                bu = c.get("buyability") or ""
                us = c.get("usage") or ""
                canon = (c.get("canonical_buy_form") or "").lower().strip()
                identity_resolved = c.get("identity_resolved", True)
                # Apply DERIVATIVE override (lemon zest, ice cubes, etc.)
                if bfl.get(canon) == "DERIVATIVE":
                    bu = "derivative"
                # User_choice_unresolved: classifier flagged "additional X" / "assorted Y"
                # → not a true gap, just user input needed
                if identity_resolved is False and bu == "buyable":
                    bucket = "user_choice_unresolved"
                # decision logic
                elif bu == "derivative":
                    # Try to resolve via base_ingredients (don't skip)
                    base = c.get("base_ingredients") or []
                    primary_base = (base[0] if base else "").lower().strip()
                    if not primary_base or primary_base == "water":
                        bucket = "skip_derivative"   # zero contribution OK
                    else:
                        if not status_for(primary_base)["has_path"]:
                            bucket = "gap_derivative_no_base_path"
                        elif not status_for(primary_base)["has_sku"]:
                            bucket = "gap_derivative_no_base_sku"
                        elif not status_for(primary_base)["has_macros"]:
                            bucket = "covered_cost_only"
                        else:
                            bucket = "covered_full"  # derivative resolved via base
                elif bu in ("unbuyable", "nonsense"):
                    bucket = "review"
                elif us in ("to_taste", "garnish", "optional"):
                    # shop_only — needs SKU but not qty calc
                    if not canon:
                        bucket = "gap_no_canonical_buy_form"
                    elif not status_for(canon)["has_path"]:
                        bucket = "gap_no_canonical_path"
                    elif not status_for(canon)["has_sku"]:
                        bucket = "gap_no_sku_at_path"
                    else:
                        bucket = "covered_shop_only"
                else:
                    # decision=calculate → needs SKU + grams + macros for full
                    if not canon:
                        bucket = "gap_no_canonical_buy_form"
                    elif not status_for(canon)["has_path"]:
                        bucket = "gap_no_canonical_path"
                    elif not status_for(canon)["has_sku"]:
                        bucket = "gap_no_sku_at_path"
                    elif not status_for(canon)["has_macros"]:
                        bucket = "covered_cost_only"
                    else:
                        bucket = "covered_full"
                line_buckets[bucket] += 1
                recipe_buckets[bucket] += 1

                # Track per-buy-form gap volume
                if bucket.startswith("gap_") and canon:
                    bf_recipe_volume[canon]["recipe_count"] += 1
                    if not bf_recipe_volume[canon]["first_display"]:
                        bf_recipe_volume[canon]["first_display"] = (ing.get("display") or "")[:80]
            # Classify this recipe overall
            if recipe_buckets["review"] > 0:
                rstatus = "broken"
            elif sum(v for k, v in recipe_buckets.items() if k.startswith("gap_")) > 0:
                rstatus = "partial_gap"
            elif recipe_buckets["covered_cost_only"] > 0:
                rstatus = "covered_cost_only"
            else:
                rstatus = "covered_full"
            recipe_status.append({"recipe_id": r.get("recipe_id"),
                                   "title": (r.get("title") or "")[:60],
                                   "n_lines": len(cls_list), "status": rstatus,
                                   **dict(recipe_buckets)})
            if n % 50_000 == 0:
                print(f"  scanned {n:,}", file=sys.stderr)

    # Output 1: per-canonical_buy_form gaps (top by recipe-volume)
    print("writing per-buy-form gap report...", file=sys.stderr)
    bf_rows = []
    for bf, info in bf_recipe_volume.items():
        s = bf_status.get(bf, {})
        if s.get("has_path") and s.get("has_sku"):
            continue  # not actually a gap
        bf_rows.append({
            "canonical_buy_form": bf,
            "recipe_count": info["recipe_count"],
            "has_canonical_path": "yes" if s.get("has_path") else "",
            "canonical_path": bfl.get(bf, ""),
            "has_sku_at_path": "yes" if s.get("has_sku") else "",
            "n_skus": s.get("n_skus", 0),
            "first_display": info["first_display"],
        })
    bf_rows.sort(key=lambda r: -r["recipe_count"])
    with OUT_BF.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=[
            "canonical_buy_form", "recipe_count", "has_canonical_path",
            "canonical_path", "has_sku_at_path", "n_skus", "first_display",
        ])
        w.writeheader()
        w.writerows(bf_rows)

    # Output 2: per-recipe status
    print("writing per-recipe status...", file=sys.stderr)
    keep_keys = ["covered_full", "covered_cost_only", "covered_shop_only",
                 "skip_derivative", "review", "gap_no_canonical_buy_form",
                 "gap_no_canonical_path", "gap_no_sku_at_path"]
    with OUT_RECIPE.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=[
            "recipe_id", "title", "n_lines", "status", *keep_keys,
        ])
        w.writeheader()
        for r in recipe_status:
            row = {k: r.get(k, 0) for k in keep_keys}
            row.update({
                "recipe_id": r["recipe_id"], "title": r["title"],
                "n_lines": r["n_lines"], "status": r["status"],
            })
            w.writerow(row)

    # Output 3: summary
    total_lines = sum(line_buckets.values())
    recipe_totals = Counter(r["status"] for r in recipe_status)
    total_recipes = len(recipe_status)
    summary = []
    summary.append(f"COVERAGE REPORT — {total_recipes:,} recipes / {total_lines:,} lines\n")
    summary.append(f"\n=== LINE-LEVEL ===")
    for k in ("covered_full", "covered_cost_only", "covered_shop_only",
              "skip_derivative", "review",
              "gap_no_canonical_buy_form", "gap_no_canonical_path",
              "gap_no_sku_at_path"):
        v = line_buckets.get(k, 0)
        summary.append(f"  {k:<30} {v:>10,}  ({v/total_lines:.1%})")

    summary.append(f"\n=== RECIPE-LEVEL ===")
    for k in ("covered_full", "covered_cost_only", "partial_gap", "broken"):
        v = recipe_totals.get(k, 0)
        summary.append(f"  {k:<30} {v:>10,}  ({v/total_recipes:.1%})")

    summary.append(f"\n=== TOP 30 GAP CANONICAL_BUY_FORMS BY RECIPE VOLUME ===")
    for r in bf_rows[:30]:
        summary.append(
            f"  [{r['recipe_count']:>5}] {r['canonical_buy_form']:<32} "
            f"path:{'Y' if r['has_canonical_path'] else 'N'} "
            f"sku:{'Y' if r['has_sku_at_path'] else 'N'} "
            f"({r['canonical_path'][:40] or '—'})"
        )

    s = "\n".join(summary)
    OUT_SUMMARY.write_text(s + "\n")
    print(s)
    print(f"\n  → {OUT_BF}\n  → {OUT_RECIPE}\n  → {OUT_SUMMARY}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
