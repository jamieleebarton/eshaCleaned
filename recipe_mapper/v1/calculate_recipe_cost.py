#!/usr/bin/env python3
"""Calculate recipe COST end-to-end via Hestia's package price cache.

Pipeline per ingredient line:
  1. line → modal FNDDS code (from the retail SKUs that share the line's HTC
     + product_identity_fixed) — mirrors how a shopper picks a product
  2. FNDDS code → cheapest available package in food_packages_final.db
     (with walmart_price_cents or kroger_price_cents)
  3. line.grams / package.package_weight_grams × package.price = line cost
  4. sum per recipe

Reports recipe total cost, per-line breakdown, and coverage.
"""
from __future__ import annotations

import csv
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

csv.field_size_limit(sys.maxsize)

ROOT = Path(__file__).resolve().parents[2]
HESTIA_PKG = Path("/Users/jamiebarton/Desktop/Hestia/api/data/food_packages_final.db")
HERE = Path(__file__).resolve().parent
LINES = HERE / "output" / "recipes_unified.csv"
ING_TAGS = HERE / "output" / "recipe_ingredient_htc_tagged.csv"
CON_TAGS = HERE / "output" / "consensus_htc_tagged.csv"


def load_packages() -> dict[str, list[tuple]]:
    """fndds_code → list of (price_cents_min, weight_g, store, description)
    sorted cheapest-per-gram first."""
    out: dict[str, list] = defaultdict(list)
    if not HESTIA_PKG.exists():
        print(f"[!] Hestia package db not found: {HESTIA_PKG}")
        return {}
    con = sqlite3.connect(str(HESTIA_PKG))
    cur = con.execute("""
      SELECT fndds_code, food_description, package_weight_grams,
             walmart_price_cents, kroger_price_cents
      FROM packages
      WHERE package_weight_grams > 0
        AND (walmart_price_cents IS NOT NULL OR kroger_price_cents IS NOT NULL)
    """)
    for fc, desc, w, wp, kp in cur:
        prices = []
        if wp: prices.append((wp, "walmart"))
        if kp: prices.append((kp, "kroger"))
        for cents, store in prices:
            out[fc].append((cents, float(w), store, desc))
    # Sort each list by cents-per-gram (cheapest first)
    for fc in out:
        out[fc].sort(key=lambda r: r[0] / r[1] if r[1] else 1e9)
    return dict(out)


def build_ingredient_to_fndds() -> dict[str, str]:
    """For each recipe ingredient string, find the modal FNDDS code among
    retail SKUs that share the same HTC + product_identity_fixed."""
    # Load HTC per ingredient
    ing_htc: dict[str, str] = {}
    with ING_TAGS.open() as f:
        for r in csv.DictReader(f):
            ing_htc[r["item"].lower()] = r["htc_code"]
    # Index retail SKUs: by HTC → list of (fndds, pid, title)
    retail: dict[str, list[tuple]] = defaultdict(list)
    with CON_TAGS.open() as f:
        for r in csv.DictReader(f):
            retail[r["htc_code"]].append((
                r.get("fndds_code", "").strip(),
                r.get("product_identity_fixed", "").strip(),
                r.get("title", ""),
            ))
    # For each ingredient: find SKUs at same HTC + pid contains ingredient noun;
    # take the modal FNDDS code
    out: dict[str, str] = {}
    for item, code in ing_htc.items():
        skus = retail.get(code, [])
        if not skus:
            continue
        item_tokens = set(item.split())
        modal = Counter()
        for fc, pid, _ in skus:
            if fc and (pid.lower() == item or
                       any(t in pid.lower() for t in item_tokens if len(t) > 3)):
                modal[fc] += 1
        if modal:
            out[item] = modal.most_common(1)[0][0]
        elif skus and skus[0][0]:
            out[item] = skus[0][0]   # fallback to first SKU's FNDDS
    return out


def main() -> int:
    print("loading Hestia package prices...")
    packages = load_packages()
    print(f"  {sum(len(v) for v in packages.values()):,} package-prices "
          f"across {len(packages):,} FNDDS codes")
    print("building ingredient → FNDDS map...")
    ing_to_fndds = build_ingredient_to_fndds()
    print(f"  {len(ing_to_fndds):,} ingredient strings have a FNDDS via consensus")

    targets = ["Best Lemonade", "Low-Fat Berry Blue Frozen Dessert",
               "Chicken Biryani with Saffron", "Banana Bread"]
    chosen_ids = set()
    chosen_titles = {}
    with LINES.open() as f:
        for r in csv.DictReader(f):
            t = r["recipe_title"]
            if any(tt.lower() in t.lower() for tt in targets) and t not in chosen_titles.values():
                chosen_ids.add(int(r["recipe_id"]))
                chosen_titles[int(r["recipe_id"])] = t
                if len(chosen_titles) >= 5:
                    break

    print()
    by_recipe: dict[int, list] = defaultdict(list)
    with LINES.open() as f:
        for r in csv.DictReader(f):
            try:
                rid = int(r["recipe_id"])
            except ValueError:
                continue
            if rid in chosen_ids:
                by_recipe[rid].append(r)

    for rid, title in chosen_titles.items():
        lines = by_recipe.get(rid, [])
        print(f"\n{'=' * 78}")
        print(f"  RECIPE #{rid}: {title}  ({len(lines)} lines)")
        print(f"{'=' * 78}")
        total_cents = 0
        priced = 0
        for L in lines:
            item = L["ingredient_item"].lower()
            grams_raw = L.get("grams_resolved") or ""
            try:
                grams = float(grams_raw) if grams_raw else 0.0
            except ValueError:
                grams = 0.0
            fndds = ing_to_fndds.get(item, "")
            if not grams or not fndds or fndds not in packages:
                print(f"  {item[:30]:<30}  {grams:>6.0f}g  fndds={fndds or '—':<10}  [no price]")
                continue
            # Use cheapest package containing this FNDDS
            cents, pkg_g, store, pkg_desc = packages[fndds][0]
            line_cost_cents = (grams / pkg_g) * cents
            total_cents += line_cost_cents
            priced += 1
            desc_short = (pkg_desc or "")[:25]
            print(f"  {item[:30]:<30}  {grams:>6.0f}g  fndds={fndds:<9} "
                  f"${cents/100:>5.2f} for {pkg_g:>5.0f}g ({store:<7}) "
                  f"= ${line_cost_cents/100:>5.2f}  [{desc_short}]")
        print(f"  {'─' * 70}")
        print(f"  TOTAL ({priced}/{len(lines)} lines priced):  ${total_cents/100:>6.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
