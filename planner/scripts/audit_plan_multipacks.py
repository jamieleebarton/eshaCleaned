#!/usr/bin/env python3
"""Audit selected plan packages for multipack/count package weight errors.

This is stricter than the general reasonableness audit. It focuses on rows
where package text includes a count/pack/container claim and checks whether the
planner's package grams represent the total edible package, not one unit, not a
doubled case pack, and not packaging/glass weight.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "recipe_pricing"))

from fix_size_display_grams import parse_largest_size  # noqa: E402


NUM = r"(?:\d+(?:\.\d+)?|\.\d+)"
UNIT_RE = r"(?:fl\.?\s*oz|fo|fluid\s+ounces?|ounces?|oz|lbs?|pounds?|kg|kilograms?|grams?|g|ml|milliliters?|l|liters?|litres?)"
COUNT_WORD_RE = re.compile(
    r"\b(?:\d+\s*(?:ct|count|pk|pack|packs|bottles?|cans?|pouches?|cups?|boxes?|bags?|packets?)|pack\s+of\s+\d+|multipack)\b",
    re.I,
)
COUNT_UNIT_SLASH_RE = re.compile(
    rf"\b(\d+)\s*(bottles?|cans?|pouches?|cups?|boxes?|bags?|packets?)\s*/\s*({NUM})\s*({UNIT_RE})\b",
    re.I,
)
COUNT_CT_SLASH_RE = re.compile(
    rf"\b(\d+)\s*(?:ct|count)\s*/\s*({NUM})\s*({UNIT_RE})\b",
    re.I,
)
PACK_CONTAINER_RE = re.compile(
    rf"(?:\((\d+)\s*pack\)|\b(\d+)\s*pack\b).*?\b({NUM})\s*({UNIT_RE})\s*(?:can|bottle|pouch|cup|box|bag|packet)\b",
    re.I,
)
SMALL_UNIT_COUNT_RE = re.compile(
    rf"\b({NUM})\s*({UNIT_RE})\s*,?\s*(\d+)\s*(?:ct|count|pack|packs)\b",
    re.I,
)

UNIT_TO_G = {
    "oz": 28.3495,
    "ounce": 28.3495,
    "ounces": 28.3495,
    "fl oz": 29.5735,
    "fo": 29.5735,
    "fluid ounce": 29.5735,
    "fluid ounces": 29.5735,
    "lb": 453.592,
    "lbs": 453.592,
    "pound": 453.592,
    "pounds": 453.592,
    "kg": 1000.0,
    "kilogram": 1000.0,
    "kilograms": 1000.0,
    "g": 1.0,
    "gram": 1.0,
    "grams": 1.0,
    "ml": 1.0,
    "milliliter": 1.0,
    "milliliters": 1.0,
    "l": 1000.0,
    "liter": 1000.0,
    "liters": 1000.0,
    "litre": 1000.0,
    "litres": 1000.0,
}


def unit_grams(qty: str, unit: str) -> float | None:
    norm = unit.lower().replace(".", "").strip()
    if "fl" in norm and "oz" in norm:
        norm = "fl oz"
    mult = UNIT_TO_G.get(norm)
    if mult is None:
        return None
    return float(qty) * mult


def expected_total_grams(name: str, display: str) -> tuple[float | None, str]:
    text = f"{display} {name}".strip()

    slash = COUNT_UNIT_SLASH_RE.search(display or "")
    if slash:
        each = unit_grams(slash.group(3), slash.group(4))
        if each:
            return int(slash.group(1)) * each, "display_count_container_x_unit"

    ct_slash = COUNT_CT_SLASH_RE.search(display or "")
    if ct_slash:
        count = int(ct_slash.group(1))
        size_g = unit_grams(ct_slash.group(2), ct_slash.group(3))
        if size_g:
            if size_g <= 125:
                return count * size_g, "display_count_x_small_unit"
            return size_g, "display_count_with_total_net_weight"

    pack_container = PACK_CONTAINER_RE.search(name or "")
    if pack_container:
        count = int(pack_container.group(1) or pack_container.group(2))
        each = unit_grams(pack_container.group(3), pack_container.group(4))
        if each:
            return count * each, "name_pack_x_container_size"

    small_count = SMALL_UNIT_COUNT_RE.search(display or "")
    if small_count:
        each = unit_grams(small_count.group(1), small_count.group(2))
        count = int(small_count.group(3))
        if each and each <= 125:
            return count * each, "display_small_unit_x_count"

    display_g = parse_largest_size(display or "")
    if display_g:
        return display_g, "display_total_size"

    small_count = SMALL_UNIT_COUNT_RE.search(name or "")
    if small_count:
        each = unit_grams(small_count.group(1), small_count.group(2))
        count = int(small_count.group(3))
        if each and each <= 125:
            return count * each, "name_small_unit_x_count"

    name_g = parse_largest_size(name or "")
    if name_g:
        return name_g, "name_total_size"
    if COUNT_WORD_RE.search(text):
        return None, "count_without_parseable_weight"
    return None, ""


def iter_selected_packages(plan: dict):
    for week in plan.get("weeks", []) or []:
        for row in week.get("ingredient_purchases", []) or []:
            packages = row.get("selected_packages") or []
            for pkg in packages:
                yield week.get("week"), row.get("concept_key", ""), pkg


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("plan_json", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    plan = json.loads(args.plan_json.read_text())
    rows: list[dict[str, object]] = []
    flagged = 0
    audited = 0
    for week, concept, pkg in iter_selected_packages(plan):
        name = pkg.get("name") or ""
        display = pkg.get("display") or ""
        if not COUNT_WORD_RE.search(f"{name} {display}"):
            continue
        audited += 1
        grams = float(pkg.get("grams") or 0)
        expected, source = expected_total_grams(name, display)
        ratio = (grams / expected) if expected and grams > 0 else 0.0
        status = "ok"
        if expected is None:
            status = "review_no_expected_weight"
        elif ratio < 0.75 or ratio > 1.25:
            status = "flag_package_grams_vs_multipack_text"
            flagged += 1
        rows.append({
            "week": week,
            "status": status,
            "concept_key": concept,
            "upc": pkg.get("upc") or "",
            "name": name,
            "display": display,
            "grams": round(grams, 3),
            "cents": int(pkg.get("cents") or 0),
            "expected_g": round(expected, 3) if expected else "",
            "expected_source": source,
            "ratio": round(ratio, 3) if expected else "",
        })

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("w", newline="") as handle:
            fieldnames = [
                "week", "status", "concept_key", "upc", "name", "display",
                "grams", "cents", "expected_g", "expected_source", "ratio",
            ]
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    print(f"multipack/count selected packages audited: {audited}")
    print(f"flags: {flagged}")
    for row in rows:
        if row["status"].startswith("flag_"):
            print(
                f"W{row['week']} {row['status']} ratio={row['ratio']} "
                f"{row['name'][:90]} [{row['concept_key']}]"
            )
    if args.out:
        print(f"-> {args.out}")


if __name__ == "__main__":
    main()
