#!/usr/bin/env python3
"""Recipe cost calculator backed only by the HTC/tree offer bridge."""
from __future__ import annotations

import argparse
import csv
import math
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from calculate_recipe_cost_v6 import LINES, SAFFRON_CAP_GRAMS  # noqa: E402

HERE = Path(__file__).resolve().parent
BRIDGE = HERE / "output" / "htc_tree_offer_bridge_v1.csv"


def normalized_item(value: str) -> str:
    return (value or "").strip().lower()


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


def load_recipe_lines(recipe_ids: set[int]) -> dict[int, list[dict[str, str]]]:
    by_recipe: dict[int, list[dict[str, str]]] = defaultdict(list)
    with LINES.open(encoding="utf-8", errors="replace", newline="") as handle:
        for row in csv.DictReader(handle):
            try:
                rid = int(row["recipe_id"])
            except ValueError:
                continue
            if rid in recipe_ids:
                by_recipe[rid].append(row)
    return by_recipe


def grams_for_line(row: dict[str, str]) -> float:
    try:
        grams = float(row.get("grams_resolved") or 0)
    except ValueError:
        grams = 0.0
    item = normalized_item(row.get("ingredient_item") or "")
    if "saffron" in item and grams > SAFFRON_CAP_GRAMS:
        return SAFFRON_CAP_GRAMS
    return grams


def load_bridge(path: Path, scope: str) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    with path.open(encoding="utf-8", errors="replace", newline="") as handle:
        for row in csv.DictReader(handle):
            if (row.get("store_scope") or "") != scope:
                continue
            item = normalized_item(row.get("ingredient_item") or "")
            if item:
                out[item] = row
    return out


def product_from_bridge(row: dict[str, str]) -> dict[str, object] | None:
    if row.get("terminal_status") != "safe_priced":
        return None
    try:
        grams = float(row.get("grams") or 0)
        cents = int(float(row.get("cents") or 0))
    except ValueError:
        return None
    if grams <= 0 or cents <= 0:
        return None
    return {
        "key": row.get("upc") or row.get("product_rowid") or "",
        "source": row.get("source") or "",
        "name": row.get("name") or "",
        "grams": grams,
        "cents": cents,
        "cpg": cents / grams,
        "recipe_tree": row.get("recipe_tree_canonical") or "",
        "product_tree": row.get("product_tree_canonical") or "",
        "score": row.get("match_score") or "",
        "htc": row.get("product_htc_code") or "",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bridge", type=Path, default=BRIDGE)
    parser.add_argument("--store", choices=["all", "kroger", "walmart"], default="all")
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
    by_recipe = load_recipe_lines(set(chosen))
    bridge = load_bridge(args.bridge, args.store)

    for rid, title in chosen.items():
        rows = by_recipe.get(rid, [])
        packages: dict[str, dict[str, object]] = {}
        terminal_counts: defaultdict[str, int] = defaultdict(int)
        tap_water_grams = 0.0

        print(f"\n{'=' * 80}")
        print(f"  RECIPE #{rid}: {title}  ({len(rows)} lines)")
        print(f"  HTC/tree calculator v1  store={args.store}")
        print(f"{'=' * 80}")

        for row in rows:
            item = normalized_item(row.get("ingredient_item") or "")
            grams = grams_for_line(row)
            bridge_row = bridge.get(item)
            if grams <= 0:
                terminal_counts["no_quantity"] += 1
                print(f"  {item[:30]:<30}  {grams:>6.0f}g  [no quantity]")
                continue
            if not bridge_row:
                terminal_counts["not_in_bridge"] += 1
                print(f"  {item[:30]:<30}  {grams:>6.0f}g  [not_in_bridge]")
                continue
            status = bridge_row.get("terminal_status") or "unknown"
            if status == "safe_tap_water":
                terminal_counts[status] += 1
                tap_water_grams += grams
                print(f"  {item[:30]:<30}  {grams:>6.0f}g  tap water default = $0.00")
                continue
            product = product_from_bridge(bridge_row)
            if not product:
                terminal_counts[status] += 1
                detail = bridge_row.get("match_detail") or bridge_row.get("recipe_tree_canonical") or ""
                print(f"  {item[:30]:<30}  {grams:>6.0f}g  [{status}] {detail[:90]}")
                continue
            terminal_counts["safe_priced"] += 1
            key = f"{product['source']}:{product['key']}"
            if key not in packages:
                packages[key] = {"pkg": product, "need": 0.0, "lines": []}
            packages[key]["need"] = float(packages[key]["need"]) + grams
            packages[key]["lines"].append((item, grams))

        total_cents = 0
        for entry in packages.values():
            product = entry["pkg"]
            need = float(entry["need"])
            count = max(1, math.ceil(need / float(product["grams"])))
            cost = count * int(product["cents"])
            total_cents += cost
            items_str = " + ".join(f"{it} ({g:.0f}g)" for it, g in entry["lines"])
            print(f"  {items_str[:60]:<60}  need {need:>5.0f}g")
            print(
                f"      -> {count}x [{str(product['name'])[:42]:<42}] "
                f"{float(product['grams']):>6.0f}g @ ${int(product['cents'])/100:>5.2f}/{product['source']:<7} "
                f"= ${cost/100:>6.2f}  [HTC={product['htc']}, score={product['score']}]"
            )

        priced_lines = terminal_counts["safe_priced"] + terminal_counts["safe_tap_water"]
        print(f"  {'-' * 76}")
        if tap_water_grams:
            print(f"  tap water total: {tap_water_grams:.0f}g = $0.00")
        print(f"  terminal statuses: {dict(sorted(terminal_counts.items()))}")
        print(f"  TOTAL ({priced_lines}/{len(rows)} lines safe, {len(packages)} packages): ${total_cents/100:>7.2f}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
