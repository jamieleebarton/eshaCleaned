#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from typing import Any

from run_recipe_cost_smoke import (
    DEFAULT_RECIPES_CSV,
    DEFAULT_RETAIL_BRIDGE_CSV,
    NO_PURCHASE_KEYS,
    _best_offer,
    _load_retail_offers,
    _parse_shopping_items,
    _short,
)
from surface_lab_calculator import calculate_lab, configure_data_sources, normalize_key


OUT_DIR = Path(__file__).resolve().parent / "output"
DEFAULT_OUT_JSON = OUT_DIR / "recipe_cost_audit.json"
DEFAULT_OUT_MD = OUT_DIR / "recipe_cost_audit.md"


FRESH_CANONICALS = {
    "apple",
    "fresh lemon",
    "fresh lemons",
    "garlic",
    "green bell pepper",
    "mushroom",
    "onion",
    "orange",
    "tomato",
    "white mushroom",
}

CONDIMENT_CANONICALS = {
    "hot sauce",
    "pizza sauce",
    "soy sauce",
    "tomato sauce",
    "worcestershire sauce",
}


def _offer_flags(label: str, lab: dict[str, Any], offer: dict[str, Any]) -> list[str]:
    canonical = normalize_key(lab.get("shopping_canonical") or lab.get("canonical_name") or label)
    name = normalize_key(offer.get("name") or "")
    tokens = set(name.split())
    package_grams = float(offer.get("package_grams") or 0)
    flags: list[str] = []

    if "egg" in canonical and ("egg" in tokens or "eggs" in tokens) and (package_grams < 300 or package_grams > 1500):
        flags.append("review_package_grams_for_eggs")
    elif package_grams > 10000:
        flags.append("review_package_grams_gt_10kg")

    if "juice" in canonical and (tokens & {"beverage", "cocktail", "drink", "punch"}):
        flags.append("review_juice_drink_form")

    if canonical in FRESH_CANONICALS and (tokens & {"canned", "dried", "freeze", "frozen", "juice", "powder"}):
        flags.append("review_fresh_item_form")

    if (
        canonical not in CONDIMENT_CANONICALS
        and "sauce" not in canonical
        and "dressing" not in canonical
        and "marinade" not in canonical
        and (tokens & {"dressing", "marinade", "sauce"})
        and "cheese" not in canonical
    ):
        flags.append("review_prepared_sauce_form")

    if "sausage" in canonical and (tokens & {"chicken", "hot", "pasta", "ravioli", "sauce", "soup", "sweet", "turkey"}):
        flags.append("review_sausage_variant_or_prepared_form")

    if canonical in {"lemon peel", "orange peel"}:
        flags.append("review_raw_peel_should_buy_fresh_citrus")

    return flags


def _line_is_no_purchase(label: str, lab: dict[str, Any]) -> bool:
    keys = {
        normalize_key(label),
        normalize_key(lab.get("shopping_canonical") or ""),
        normalize_key(lab.get("canonical_name") or ""),
    }
    return bool(keys & NO_PURCHASE_KEYS)


def run_audit(*, recipes_csv: Path, retail_bridge_csv: Path, limit_recipes: int) -> dict[str, Any]:
    configure_data_sources(retail_surface_bridge_csv=retail_bridge_csv)
    offers = _load_retail_offers(retail_bridge_csv)

    recipes_seen = 0
    recipes_with_items = 0
    line_count = 0
    no_purchase_count = 0
    line_lab_cache: dict[str, dict[str, Any]] = {}
    top_gaps: Counter[str] = Counter()
    top_gap_grams: Counter[str] = Counter()
    review_flags: Counter[str] = Counter()
    review_examples: list[dict[str, Any]] = []
    low_coverage_recipes: list[dict[str, Any]] = []
    zero_price_recipes: list[dict[str, Any]] = []

    with recipes_csv.open(newline="", encoding="utf-8-sig", errors="replace") as handle:
        for recipe in csv.DictReader(handle):
            raw_items = (recipe.get("shopping_items_dict") or "").strip()
            if not raw_items or raw_items == "{}":
                continue
            shopping_items = _parse_shopping_items(raw_items)
            if not shopping_items:
                continue
            recipes_seen += 1
            if limit_recipes and recipes_seen > limit_recipes:
                break
            recipes_with_items += 1

            totals = {
                "purchasable_grams": 0.0,
                "walmart_covered_grams": 0.0,
                "kroger_covered_grams": 0.0,
                "nutrition_unknown_lines": 0,
                "gap_lines": 0,
            }
            recipe_gaps: list[str] = []

            for label, grams in shopping_items.items():
                line_count += 1
                cache_key = normalize_key(label)
                lab = line_lab_cache.get(cache_key)
                if lab is None:
                    lab = asdict(calculate_lab(display=label, item=label, grams=100.0))
                    line_lab_cache[cache_key] = lab

                if lab.get("nutrition_state") == "nutrition_unknown":
                    totals["nutrition_unknown_lines"] += 1
                if _line_is_no_purchase(label, lab):
                    no_purchase_count += 1
                    continue

                totals["purchasable_grams"] += grams
                products = lab.get("products") or []
                walmart = _best_offer(products, offers, "walmart", grams)
                kroger = _best_offer(products, offers, "kroger", grams)
                if walmart:
                    totals["walmart_covered_grams"] += grams
                if kroger:
                    totals["kroger_covered_grams"] += grams

                if not walmart and not kroger:
                    totals["gap_lines"] += 1
                    top_gaps[label] += 1
                    top_gap_grams[label] += int(round(grams))
                    recipe_gaps.append(label)

                for source, offer in (("walmart", walmart), ("kroger", kroger)):
                    if not offer:
                        continue
                    flags = _offer_flags(label, lab, offer)
                    for flag in flags:
                        review_flags[flag] += 1
                        if len(review_examples) < 50:
                            review_examples.append(
                                {
                                    "flag": flag,
                                    "source": source,
                                    "recipe_num": recipe.get("recipeNum", ""),
                                    "recipe_name": recipe.get("recipeName", ""),
                                    "label": label,
                                    "canonical": lab.get("shopping_canonical") or lab.get("canonical_name"),
                                    "product": offer.get("name"),
                                    "package_grams": offer.get("package_grams"),
                                    "package_usd": offer.get("package_usd"),
                                }
                            )

            purchasable = totals["purchasable_grams"]
            walmart_cov = totals["walmart_covered_grams"] / purchasable if purchasable else 0.0
            kroger_cov = totals["kroger_covered_grams"] / purchasable if purchasable else 0.0
            recipe_summary = {
                "recipe_num": recipe.get("recipeNum", ""),
                "recipe_name": recipe.get("recipeName", ""),
                "line_count": len(shopping_items),
                "walmart_coverage_pct": walmart_cov,
                "kroger_coverage_pct": kroger_cov,
                "gap_lines": totals["gap_lines"],
                "nutrition_unknown_lines": totals["nutrition_unknown_lines"],
                "gap_examples": recipe_gaps[:5],
            }
            if purchasable and walmart_cov == 0.0 and kroger_cov == 0.0:
                zero_price_recipes.append(recipe_summary)
            if purchasable and max(walmart_cov, kroger_cov) < 0.80:
                low_coverage_recipes.append(recipe_summary)

    return {
        "recipes_csv": str(recipes_csv),
        "retail_bridge_csv": str(retail_bridge_csv),
        "limit_recipes": limit_recipes,
        "recipes_scanned": recipes_with_items,
        "line_count": line_count,
        "unique_lines_resolved": len(line_lab_cache),
        "no_purchase_lines": no_purchase_count,
        "zero_price_recipe_count": len(zero_price_recipes),
        "low_coverage_recipe_count": len(low_coverage_recipes),
        "low_coverage_recipes": low_coverage_recipes[:50],
        "zero_price_recipes": zero_price_recipes[:50],
        "top_gap_items": [
            {"item": item, "count": count, "approx_grams": top_gap_grams[item]}
            for item, count in top_gaps.most_common(40)
        ],
        "review_flags": dict(review_flags),
        "review_examples": review_examples,
    }


def write_markdown(report: dict[str, Any], path: Path) -> None:
    lines = [
        "# Recipe Cost Audit",
        "",
        f"- recipes scanned: `{report['recipes_scanned']}`",
        f"- recipe lines scanned: `{report['line_count']}`",
        f"- unique lines resolved: `{report['unique_lines_resolved']}`",
        f"- zero-price recipes: `{report['zero_price_recipe_count']}`",
        f"- low-coverage recipes: `{report['low_coverage_recipe_count']}`",
        "",
        "## Top Gap Items",
        "",
        "| item | count | approx grams |",
        "| --- | ---: | ---: |",
    ]
    for row in report["top_gap_items"][:25]:
        lines.append(f"| {_short(row['item'], 72)} | {row['count']} | {row['approx_grams']} |")

    lines.extend(["", "## Low Coverage Recipe Examples", "", "| recipe | Walmart | Kroger | gaps | examples |", "| --- | ---: | ---: | ---: | --- |"])
    for row in report["low_coverage_recipes"][:25]:
        lines.append(
            "| "
            + " | ".join(
                [
                    _short(f"{row['recipe_num']} {row['recipe_name']}", 54),
                    f"{row['walmart_coverage_pct']:.0%}",
                    f"{row['kroger_coverage_pct']:.0%}",
                    str(row["gap_lines"]),
                    _short("; ".join(row["gap_examples"]), 90),
                ]
            )
            + " |"
        )

    lines.extend(["", "## Review Flags", "", "| flag | count |", "| --- | ---: |"])
    for flag, count in sorted(report["review_flags"].items(), key=lambda item: item[1], reverse=True):
        lines.append(f"| {flag} | {count} |")

    lines.extend(["", "## Review Examples", "", "| flag | recipe | item | canonical | source | product |", "| --- | --- | --- | --- | --- | --- |"])
    for row in report["review_examples"][:30]:
        lines.append(
            "| "
            + " | ".join(
                [
                    row["flag"],
                    _short(f"{row['recipe_num']} {row['recipe_name']}", 34),
                    _short(row["label"], 38),
                    _short(row.get("canonical") or "", 30),
                    row["source"],
                    _short(row["product"], 70),
                ]
            )
            + " |"
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit recipe pricing coverage and suspicious retail selections.")
    parser.add_argument("--recipes-csv", type=Path, default=DEFAULT_RECIPES_CSV)
    parser.add_argument("--retail-bridge-csv", type=Path, default=DEFAULT_RETAIL_BRIDGE_CSV)
    parser.add_argument("--limit-recipes", type=int, default=500)
    parser.add_argument("--out-json", type=Path, default=DEFAULT_OUT_JSON)
    parser.add_argument("--out-md", type=Path, default=DEFAULT_OUT_MD)
    args = parser.parse_args()

    report = run_audit(
        recipes_csv=args.recipes_csv,
        retail_bridge_csv=args.retail_bridge_csv,
        limit_recipes=args.limit_recipes,
    )
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_markdown(report, args.out_md)
    print(json.dumps({"recipes_scanned": report["recipes_scanned"], "out_json": str(args.out_json), "out_md": str(args.out_md)}, indent=2))


if __name__ == "__main__":
    main()
