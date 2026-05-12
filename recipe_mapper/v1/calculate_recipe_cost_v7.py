#!/usr/bin/env python3
"""V7 recipe cost calculator using adjudicated priced-product evidence.

This version does not trust raw priced_products.consensus_* fields. It only
prices with rows approved by build_priced_product_evidence_v1.py, and it does
not use broad head-noun fallback for retail products.
"""
from __future__ import annotations

import argparse
import csv
import math
import re
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from calculate_recipe_cost_v6 import (  # noqa: E402
    LINES,
    PRICED_DB,
    RULE_B_PIDS,
    SAFFRON_CAP_GRAMS,
    build_concepts,
)

HERE = Path(__file__).resolve().parent
EVIDENCE_CSV = HERE / "output" / "priced_product_evidence_v1.csv"

APPROVED_TAXONOMY_STATUSES = {"approved_taxonomy", "approved_existing"}

PLAIN_FRUIT_ITEMS = {
    "apples", "apricots", "bananas", "blackberries", "blueberries",
    "cherries", "cranberries", "grapes", "mango", "mangoes", "oranges",
    "peaches", "pineapple", "raspberries", "strawberries",
}

PLAIN_NUT_SEED_ITEMS = {
    "almonds", "cashews", "hazelnuts", "macadamia nuts", "peanuts",
    "pecans", "pine nuts", "pistachios", "walnuts", "pumpkin seeds",
    "sesame seeds", "sunflower seeds",
}

SWEET_ADDITION_RE = re.compile(
    r"\b(chocolate|milk chocolate|dark chocolate|white chocolate|candy|"
    r"caramel|yogurt[-\s]*covered|covered|coated|peanut butter chips?)\b",
    re.I,
)

MIX_OR_TOPPER_RE = re.compile(
    r"\b(salad toppers?|trail mix|snack mix|party mix|cranberries|raisins)\b",
    re.I,
)

SALT_BLEND_RE = re.compile(
    r"\b(black pepper|pepper\s*&\s*salt|celery salt|onion salt|garlic salt|"
    r"bacon flavored|seasoning salt|seasoned salt)\b",
    re.I,
)


def normalized_item(value: str) -> str:
    return (value or "").strip().lower()


def is_tap_water_item(item: str) -> bool:
    item_lc = normalized_item(item)
    return item_lc in {"water", "fresh water", "tap water", "plain water", "ice", "ice cube", "ice cubes"}


def load_evidence(path: Path) -> dict[int, dict[str, str]]:
    out: dict[int, dict[str, str]] = {}
    with path.open(encoding="utf-8", errors="replace", newline="") as handle:
        for row in csv.DictReader(handle):
            if row.get("taxonomy_status") not in APPROVED_TAXONOMY_STATUSES:
                continue
            try:
                rowid = int(row.get("rowid") or 0)
            except ValueError:
                continue
            if not rowid or not row.get("proposed_canonical"):
                continue
            out[rowid] = row
    return out


def load_priced_products(db_path: Path, evidence_path: Path) -> list[dict]:
    evidence = load_evidence(evidence_path)
    if not evidence:
        raise RuntimeError(f"No approved product evidence rows found in {evidence_path}")

    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    rowids = sorted(evidence)
    out: list[dict] = []

    # Avoid a giant IN list in one statement on sqlite builds with low limits.
    for i in range(0, len(rowids), 900):
        chunk = rowids[i:i + 900]
        marks = ",".join("?" for _ in chunk)
        sql = f"""
            SELECT rowid, source, upc, name, brand, grams, cents,
                   htc_code, htc_group, category_path, category_path_walmart
            FROM priced_products
            WHERE rowid IN ({marks})
              AND marketplace = 0 AND available = 1
              AND grams > 0 AND cents > 0
        """
        for row in con.execute(sql, chunk):
            ev = evidence[int(row["rowid"])]
            pid = ev.get("proposed_pid") or ""
            canonical = ev.get("proposed_canonical") or ""
            modifier = (ev.get("proposed_modifier") or "").split(" > ")[0].strip()
            out.append({
                "rowid": int(row["rowid"]),
                "source": row["source"] or "",
                "upc": row["upc"] or f"rowid:{row['rowid']}",
                "name": row["name"] or "",
                "brand": row["brand"] or "",
                "grams": float(row["grams"]),
                "cents": int(row["cents"]),
                "cpg": int(row["cents"]) / float(row["grams"]),
                "htc": row["htc_code"] or "",
                "htc_group": row["htc_group"] or "",
                "category_path": row["category_path"] or "",
                "category_path_walmart": row["category_path_walmart"] or "",
                "pid": pid,
                "canonical": canonical,
                "modifier": modifier,
                "taxonomy_status": ev.get("taxonomy_status") or "",
                "nutrition_status": ev.get("nutrition_status") or "",
                "evidence_score": float(ev.get("total_score") or 0),
            })
    return out


def product_concept(product: dict) -> tuple[str, str]:
    modifier = product["modifier"].lower() if product["pid"] in RULE_B_PIDS else ""
    return product["canonical"], modifier


def recipe_allowed_prefixes(row: dict) -> tuple[str, ...]:
    blob = " ".join(
        str(row.get(key) or "").lower()
        for key in ("ingredient_item", "display", "facet_form", "facet_processing", "facet_modifier")
    )
    item_text = str(row.get("ingredient_item") or "").lower()
    if re.search(r"\bground\s+(beef|turkey|pork|chicken|lamb|veal)\b", item_text):
        return ()
    if item_text in {
        "powdered sugar", "confectioners sugar", "confectioner's sugar",
        "icing sugar", "cocoa powder", "unsweetened cocoa powder",
        "dry mustard", "mustard powder", "active dry yeast",
    }:
        return ()
    if re.search(r"\bbay\s+leaves?\b", item_text):
        return ("Pantry > Spices & Seasonings",)
    if re.search(r"\b(leaves?|sprigs?|bunches?|bunch)\b", blob):
        return ("Produce >",)
    if (
        re.search(r"\b(ground|powder|powdered|dried|dry)\b", blob)
        and item_text not in {"baking powder", "baking soda"}
    ):
        return ("Pantry > Spices & Seasonings",)
    if "fresh or frozen" in blob:
        return ()
    if re.search(r"\bfrozen\b", blob):
        return ("Frozen >",)
    if re.search(r"\bcanned\b|\bcan\b", blob):
        return ("Pantry >",)
    return ()


def path_allowed(path: str, prefixes: tuple[str, ...]) -> bool:
    if not prefixes:
        return True
    for prefix in prefixes:
        if prefix.endswith(" >"):
            if path == prefix[:-2] or path.startswith(prefix):
                return True
        elif path == prefix or path.startswith(prefix + " >"):
            return True
    return False


def simple_item_key(item: str) -> str:
    words = [w for w in re.findall(r"[a-z0-9]+", item.lower()) if w not in {"ripe", "fresh", "raw", "whole"}]
    return " ".join(words)


def recipe_product_allowed(item: str, row: dict, product: dict) -> bool:
    if not path_allowed(product["canonical"], recipe_allowed_prefixes(row)):
        return False

    item_key = simple_item_key(item)
    title = product["name"].lower()
    if item_key in PLAIN_FRUIT_ITEMS and SWEET_ADDITION_RE.search(title):
        return False
    if item_key in PLAIN_NUT_SEED_ITEMS and (
        SWEET_ADDITION_RE.search(title) or MIX_OR_TOPPER_RE.search(title)
    ):
        return False
    if item_key == "salt" and SALT_BLEND_RE.search(title):
        return False
    return True


def pick_product(item: str, info: dict, priced_products: list[dict], row: dict | None = None) -> dict | None:
    if not info or not info.get("concepts"):
        return None
    valid_concepts = info["concepts"]
    candidates: list[dict] = []
    row = row or {}
    for product in priced_products:
        concept = product_concept(product)
        if concept in valid_concepts and recipe_product_allowed(item, row, product):
            candidates.append(product)

    if not candidates:
        return None

    # First require close evidence, then choose a practical package price.
    # This keeps weak cheap rows out without making a tiny premium pack beat
    # an otherwise equivalent commodity package.
    top_score = max(p["evidence_score"] for p in candidates)
    price_pool = [p for p in candidates if p["evidence_score"] >= top_score - 8]
    price_pool.sort(key=lambda p: (p["cpg"], p["cents"], -p["evidence_score"]))
    return price_pool[0]


def choose_target_recipes(targets: list[str], max_recipes: int) -> dict[int, str]:
    chosen: dict[int, str] = {}
    with LINES.open(encoding="utf-8", errors="replace", newline="") as handle:
        for row in csv.DictReader(handle):
            title = row["recipe_title"]
            if any(target.lower() in title.lower() for target in targets) and title not in chosen.values():
                chosen[int(row["recipe_id"])] = title
                if len(chosen) >= max_recipes:
                    break
    return chosen


def load_recipe_lines(recipe_ids: set[int]) -> dict[int, list[dict]]:
    by_recipe: dict[int, list[dict]] = defaultdict(list)
    with LINES.open(encoding="utf-8", errors="replace", newline="") as handle:
        for row in csv.DictReader(handle):
            try:
                rid = int(row["recipe_id"])
            except ValueError:
                continue
            if rid in recipe_ids:
                by_recipe[rid].append(row)
    return by_recipe


def grams_for_line(row: dict) -> float:
    try:
        grams = float(row.get("grams_resolved") or 0)
    except ValueError:
        grams = 0.0
    item = normalized_item(row.get("ingredient_item") or "")
    if "saffron" in item and grams > SAFFRON_CAP_GRAMS:
        return SAFFRON_CAP_GRAMS
    return grams


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--priced-db", type=Path, default=PRICED_DB)
    parser.add_argument("--evidence", type=Path, default=EVIDENCE_CSV)
    parser.add_argument("--target", action="append", default=[], help="recipe title substring; repeatable")
    parser.add_argument("--max-recipes", type=int, default=5)
    args = parser.parse_args()

    targets = args.target or [
        "Best Lemonade",
        "Low-Fat Berry Blue Frozen Dessert",
        "Chicken Biryani with Saffron",
        "Banana Bread",
    ]
    chosen = choose_target_recipes(targets, args.max_recipes)
    recipe_ids = set(chosen)
    by_recipe = load_recipe_lines(recipe_ids)

    test_items: set[str] = set()
    for rows in by_recipe.values():
        for row in rows:
            item = normalized_item(row.get("ingredient_item") or "")
            if item and not is_tap_water_item(item):
                test_items.add(item)

    print(f"loading consensus tree concepts for {len(test_items)} ingredients...")
    concepts = build_concepts(test_items)
    print(f"  {sum(1 for value in concepts.values() if value['concepts'])}/{len(concepts)} ingredients have tree concepts")
    print("loading adjudicated priced products...")
    priced_products = load_priced_products(args.priced_db, args.evidence)
    print(f"  {len(priced_products):,} approved priced products")

    for rid, title in chosen.items():
        rows = by_recipe.get(rid, [])
        print(f"\n{'=' * 80}")
        print(f"  RECIPE #{rid}: {title}  ({len(rows)} lines)")
        print("  v7: adjudicated evidence layer only; no retail head-noun fallback")
        print(f"{'=' * 80}")

        packages: dict[str, dict] = {}
        priced_count = 0
        tap_water_grams = 0.0

        for row in rows:
            item = normalized_item(row.get("ingredient_item") or "")
            grams = grams_for_line(row)
            if grams <= 0:
                print(f"  {item[:30]:<30}  {grams:>6.0f}g  [no quantity]")
                continue

            if is_tap_water_item(item):
                tap_water_grams += grams
                priced_count += 1
                print(f"  {item[:30]:<30}  {grams:>6.0f}g  tap water default = $0.00")
                continue

            info = concepts.get(item)
            product = pick_product(item, info, priced_products, row) if info else None
            if not product:
                print(f"  {item[:30]:<30}  {grams:>6.0f}g  [NO_SAFE_MATCH]")
                continue

            key = product["upc"]
            if key not in packages:
                packages[key] = {"pkg": product, "need": 0.0, "lines": []}
            packages[key]["need"] += grams
            packages[key]["lines"].append((item, grams))
            priced_count += 1

        total_cents = 0
        for entry in packages.values():
            product = entry["pkg"]
            need = float(entry["need"])
            count = max(1, math.ceil(need / product["grams"]))
            cost = count * product["cents"]
            total_cents += cost
            items_str = " + ".join(f"{it} ({g:.0f}g)" for it, g in entry["lines"])
            print(f"  {items_str[:60]:<60}  need {need:>5.0f}g")
            print(
                f"      -> {count}x [{product['name'][:42]:<42}] "
                f"{product['grams']:>6.0f}g @ ${product['cents']/100:>5.2f}/{product['source']:<7} "
                f"= ${cost/100:>6.2f}  "
                f"[{product['taxonomy_status']}, pid={product['pid']}, score={product['evidence_score']:.1f}]"
            )

        print(f"  {'-' * 76}")
        if tap_water_grams:
            print(f"  tap water total: {tap_water_grams:.0f}g = $0.00")
        print(f"  TOTAL ({priced_count}/{len(rows)} lines safe-priced, {len(packages)} packages): ${total_cents/100:>7.2f}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
