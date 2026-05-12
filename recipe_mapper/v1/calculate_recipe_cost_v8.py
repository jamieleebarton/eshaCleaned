#!/usr/bin/env python3
"""V8 recipe cost calculator using resolver + safe offer bridge audit layers."""
from __future__ import annotations

import argparse
import csv
import math
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from audit_recipe_cost_v8_coverage import load_rescue_products, product_index  # noqa: E402
from calculate_recipe_cost_v6 import LINES, PRICED_DB, SAFFRON_CAP_GRAMS, build_concepts  # noqa: E402
from calculate_recipe_cost_v7 import (  # noqa: E402
    EVIDENCE_CSV,
    is_tap_water_item,
    load_priced_products,
    normalized_item,
    recipe_product_allowed,
)
from pricing_concept_resolver import PricingConceptResolver, product_passes_gate  # noqa: E402


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


def has_gate(resolved) -> bool:
    gate = resolved.product_gate
    return any((gate.required_all, gate.required_any, gate.forbidden, gate.required_path_any, gate.forbidden_path))


def pick_product_v8(
    item: str,
    row: dict,
    resolver: PricingConceptResolver,
    fallback_info: dict | None,
    by_concept: dict[tuple[str, str], list[dict]],
) -> tuple[dict | None, str, str]:
    fallback = (fallback_info or {}).get("concepts") or set()
    resolved = resolver.resolve(item, fallback_concepts=fallback)
    candidates: list[tuple[dict, str, tuple[str, str]]] = []

    for concept in resolved.match_concepts(include_equivalents=True):
        for product in by_concept.get(concept, []):
            if product.get("offer_layer") == "rescue_candidate" and not has_gate(resolved):
                continue
            if not recipe_product_allowed(item, row, product):
                continue
            if not product_passes_gate(resolved, product):
                continue
            layer = "resolver" if resolved.source != "legacy_fast_concepts" else "v7_evidence"
            if concept not in resolved.concepts:
                layer = f"{layer}+safe_equivalence"
            if product.get("offer_layer") == "rescue_candidate":
                layer = f"{layer}+rescue_offer"
            candidates.append((product, layer, concept))

    if not candidates:
        detail = resolved.source
        if resolved.concepts:
            detail += " " + " | ".join(f"{c[0]}[{c[1]}]" if c[1] else c[0] for c in sorted(resolved.concepts))
        elif resolved.nutrition_anchor:
            detail += f" {resolved.nutrition_anchor}"
        return None, "NO_SAFE_MATCH", detail

    top_score = max(product["evidence_score"] for product, _, _ in candidates)
    price_pool = [entry for entry in candidates if entry[0]["evidence_score"] >= top_score - 8]
    price_pool.sort(key=lambda entry: (entry[0]["cpg"], entry[0]["cents"], -entry[0]["evidence_score"]))
    product, layer, concept = price_pool[0]
    detail = f"{layer}; {concept[0]}" + (f" [{concept[1]}]" if concept[1] else "")
    return product, layer, detail


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--priced-db", type=Path, default=PRICED_DB)
    parser.add_argument("--evidence", type=Path, default=EVIDENCE_CSV)
    parser.add_argument("--target", action="append", default=[], help="recipe title substring; repeatable")
    parser.add_argument("--max-recipes", type=int, default=5)
    parser.add_argument("--no-rescue-evidence", dest="rescue_evidence", action="store_false")
    parser.set_defaults(rescue_evidence=True)
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

    print(f"loading consensus fallback concepts for {len(test_items)} ingredients...")
    fallback_concepts = build_concepts(test_items)
    resolver = PricingConceptResolver()
    print("loading v8 priced offers...")
    approved = load_priced_products(args.priced_db, args.evidence)
    rescue = load_rescue_products(args.priced_db, args.evidence) if args.rescue_evidence else []
    offers = approved + rescue
    by_concept = product_index(offers)
    print(f"  {len(approved):,} approved offers + {len(rescue):,} rescue candidates")

    for rid, title in chosen.items():
        rows = by_recipe.get(rid, [])
        print(f"\n{'=' * 80}")
        print(f"  RECIPE #{rid}: {title}  ({len(rows)} lines)")
        print("  v8: resolver + approved evidence + strict gated rescue offers")
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

            product, layer, detail = pick_product_v8(item, row, resolver, fallback_concepts.get(item), by_concept)
            if not product:
                print(f"  {item[:30]:<30}  {grams:>6.0f}g  [{layer}] {detail}")
                continue

            key = product["upc"]
            if key not in packages:
                packages[key] = {"pkg": product, "need": 0.0, "lines": [], "detail": detail}
            packages[key]["need"] += grams
            packages[key]["lines"].append((item, grams, layer))
            priced_count += 1

        total_cents = 0
        for entry in packages.values():
            product = entry["pkg"]
            need = float(entry["need"])
            count = max(1, math.ceil(need / product["grams"]))
            cost = count * product["cents"]
            total_cents += cost
            items_str = " + ".join(f"{it} ({g:.0f}g)" for it, g, _ in entry["lines"])
            layers = ", ".join(sorted({layer for _, _, layer in entry["lines"]}))
            print(f"  {items_str[:60]:<60}  need {need:>5.0f}g")
            print(
                f"      -> {count}x [{product['name'][:42]:<42}] "
                f"{product['grams']:>6.0f}g @ ${product['cents']/100:>5.2f}/{product['source']:<7} "
                f"= ${cost/100:>6.2f}  "
                f"[{product['taxonomy_status']}, score={product['evidence_score']:.1f}, {layers}]"
            )

        print(f"  {'-' * 76}")
        if tap_water_grams:
            print(f"  tap water total: {tap_water_grams:.0f}g = $0.00")
        print(f"  TOTAL ({priced_count}/{len(rows)} lines safe-priced, {len(packages)} packages): ${total_cents/100:>7.2f}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
