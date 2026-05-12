#!/usr/bin/env python3
"""Auto-merge cross-parent same-leaf duplicates that look like bridge
errors. Preserves Frozen/Canned/Fresh distinctions.

Rule: variant_path → canonical_path IF:
  1. Same leaf identity (tokens match)
  2. Variant has < 35% of the canonical's product count (clear minority)
  3. Neither path's top-2 is in the FROZEN/CANNED/FRESH preserve set
     (so we don't collapse `Frozen > Vegetables > Corn` into
      `Pantry > Canned Vegetables > Corn`)
  4. Canonical top-1 is a food category (Pantry, Dairy, etc.)

Keeps:
  Frozen vs Canned vs Fresh same-leaf distinctions
  Parent vs leaf (Beef vs Ground Beef)

Merges:
  Drink Mix at Beverage > Mixes → Beverage > Flavored Drinks > Drink Mix
  Whipped Topping at Pantry > Sweeteners → Dairy > Cream > Whipped Topping
  Pie Filling at Dairy > Pudding → Pantry > Canned Fruit > Pie Filling
"""
from __future__ import annotations

import csv
import shutil
import sqlite3
import sys
from pathlib import Path

csv.field_size_limit(sys.maxsize)

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "recipe_pricing" / "cross_parent_path_duplicates.csv"
DB = ROOT / "recipe_pricing" / "data" / "priced_products_v2.db"
API = ROOT / "recipe_pricing" / "output" / "api_cache_taxonomy_v2.csv"
ING = ROOT / "recipe_mapper" / "v1" / "output" / "recipe_ingredient_taxonomy_v2.csv"
CONSENSUS = ROOT / "retail_mapper" / "v2" / "consensus_full_corpus_audit.csv"
LOG = ROOT / "recipe_pricing" / "remaining_bridge_consolidation_log.csv"

# When BOTH paths' top-2 are in this set, the split is a real distinction
# (frozen/canned/fresh). Don't merge.
PRESERVE_DISTINCT_TOP2 = {
    "Frozen > Vegetables", "Frozen > Fruit", "Frozen > Frozen Fruit",
    "Frozen > Vegetables", "Frozen > Cheesecake", "Frozen > Pancakes",
    "Pantry > Canned Vegetables", "Pantry > Canned Fruit",
    "Pantry > Canned Beans", "Pantry > Canned Meat",
    "Pantry > Pickles", "Pantry > Pickled",
    "Pantry > Dried", "Snack > Dried Fruit",
    "Produce > Vegetables", "Produce > Fruit", "Produce > Salad",
    "Produce > Herbs",
    "Pantry > Soup", "Pantry > Frozen Sides",
    "Frozen > Single Entrees", "Frozen > Vegetables",
    "Frozen > Breakfast Sandwiches", "Frozen > Pizza",
    "Frozen > Meatballs", "Frozen > Burritos", "Frozen > Tacos",
    "Frozen > Fruit Bars",
    "Meal > Pasta Dishes", "Meal > Pizza", "Meal > Sandwiches",
    "Meal > Salads", "Meal > Sushi", "Meal > Composite Dishes",
    "Meal > Single Entrees", "Meal > Breakfast Sandwiches",
    "Pantry > Frozen", "Pantry > Frozen Pasta",
}

FOOD_CATEGORY_TOPS = ("Pantry", "Produce", "Dairy", "Frozen", "Bakery",
                      "Beverage", "Snack", "Meat & Seafood", "Meal",
                      "Sports & Wellness")


def top2(path: str) -> str:
    parts = path.split(" > ")
    return " > ".join(parts[:2]) if len(parts) >= 2 else path


def main() -> int:
    if not INPUT.exists():
        raise SystemExit(f"missing {INPUT}")

    remap: dict[str, str] = {}
    skipped = 0
    with INPUT.open() as f:
        for row in csv.DictReader(f):
            cn, vn = row["canonical_path"], row["variant_path"]
            cn_n = int(row["canonical_n"])
            vn_n = int(row["variant_n"])
            cn_top2 = top2(cn)
            vn_top2 = top2(vn)
            cn_top1 = cn.split(" > ")[0]

            # Rule 1: variant is true minority (< 35% of canonical)
            if cn_n == 0 or vn_n / cn_n >= 0.35:
                skipped += 1
                continue
            # Rule 2: both top-2 in preserve set → KEEP DISTINCT
            if cn_top2 in PRESERVE_DISTINCT_TOP2 and vn_top2 in PRESERVE_DISTINCT_TOP2:
                skipped += 1
                continue
            # Rule 3: canonical must be in a food category
            if not any(cn_top1.startswith(t) for t in FOOD_CATEGORY_TOPS):
                skipped += 1
                continue
            # Rule 4: skip parent/child where they're nested
            if vn.startswith(cn + " > ") or cn.startswith(vn + " > "):
                skipped += 1
                continue
            # Rule 5: same-leaf check — variant's leaf must match canonical's leaf
            cn_leaf = cn.split(" > ")[-1].lower()
            vn_leaf = vn.split(" > ")[-1].lower()
            # Allow plural/singular tolerance
            if cn_leaf != vn_leaf and cn_leaf.rstrip("s") != vn_leaf.rstrip("s"):
                skipped += 1
                continue

            remap[vn] = cn

    print(f"merge candidates: {len(remap):,}", file=sys.stderr)
    print(f"skipped (real distinctions): {skipped:,}", file=sys.stderr)
    print(f"\nFirst 25:", file=sys.stderr)
    for variant, canonical in list(remap.items())[:25]:
        print(f"  {variant}  →  {canonical}", file=sys.stderr)

    # Apply
    backup = DB.with_suffix(".db.before_remaining_bridge_consol")
    if not backup.exists():
        shutil.copy(str(DB), str(backup))
    con = sqlite3.connect(str(DB))
    cur = con.cursor()
    n_db = 0
    for variant, canonical in remap.items():
        cur.execute("UPDATE priced_products SET consensus_canonical = ? WHERE consensus_canonical = ?",
                    (canonical, variant))
        n_db += cur.rowcount
    con.commit()

    def update_csv(path: Path) -> int:
        if not path.exists():
            return 0
        backup = path.with_suffix(path.suffix + ".before_remaining_bridge_consol")
        if not backup.exists():
            shutil.copy(str(path), str(backup))
        tmp = path.with_suffix(".csv.tmp")
        n = 0
        with path.open(newline="") as fin, tmp.open("w", newline="") as fout:
            reader = csv.DictReader(fin)
            writer = csv.DictWriter(fout, fieldnames=reader.fieldnames)
            writer.writeheader()
            for row in reader:
                cp = (row.get("canonical_path") or "").strip()
                if cp in remap:
                    row["canonical_path"] = remap[cp]
                    n += 1
                writer.writerow(row)
        shutil.move(str(tmp), str(path))
        return n

    n_api = update_csv(API)
    n_ing = update_csv(ING)
    n_cons = update_csv(CONSENSUS)

    with LOG.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["variant_path", "canonical_path"])
        w.writeheader()
        for v, c in remap.items():
            w.writerow({"variant_path": v, "canonical_path": c})

    print(f"\n=== TOTAL UPDATES ===", file=sys.stderr)
    print(f"  priced_products:  {n_db:,}", file=sys.stderr)
    print(f"  api_cache:        {n_api:,}", file=sys.stderr)
    print(f"  recipe_ing:       {n_ing:,}", file=sys.stderr)
    print(f"  consensus_full:   {n_cons:,}", file=sys.stderr)
    print(f"  total:            {n_db+n_api+n_ing+n_cons:,}", file=sys.stderr)
    print(f"  → {LOG}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
