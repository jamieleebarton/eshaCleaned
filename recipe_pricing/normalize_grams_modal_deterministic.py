#!/usr/bin/env python3
"""Collapse high-confidence household-unit gram drift in recipes_unified.csv.

The SR28 normalizer fixes many rows, but it intentionally preserves some
previously-corrected rows and it leaves blob-origin values alone when no SR28
portion match is available. This pass is narrower: for common household units,
if the same (ingredient_item, qty, unit) tuple overwhelmingly agrees on one
gram value, rewrite the outliers to that modal value.

Package-size units are deliberately excluded. "1 can tomatoes" can be 8 oz,
14.5 oz, or 28 oz depending on recipe text; forcing a corpus-wide modal would
destroy real package evidence.

When an SR28/reviewed-household source is present for a drift bucket, that
anchor wins over the statistical modal. The modal is only the fallback for
deterministic tuples that do not have a source-backed row.

Usage:
  python3 recipe_pricing/normalize_grams_modal_deterministic.py --dry-run
  python3 recipe_pricing/normalize_grams_modal_deterministic.py
"""
from __future__ import annotations

import argparse
import csv
import os
import re
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

csv.field_size_limit(2**30)

ROOT = Path(__file__).resolve().parents[1]
RECIPES = ROOT / "recipe_mapper" / "v1" / "output" / "recipes_unified.csv"
LOG = ROOT / "recipe_pricing" / "normalize_grams_modal_deterministic_log.csv"
REVIEW = ROOT / "recipe_pricing" / "normalize_grams_modal_deterministic_review.csv"

SOURCE = "deterministic_modal_normalized"

ANCHOR_GRAMS_SOURCES = {
    "usda_sr28_normalized",
    "reviewed_household_portion_normalized",
}

REPAIRED_QUANTITY_SOURCES = {
    "range_lower_bound",
    "range_clamped_to_blob",
    "text_range_clamped_to_blob",
    "per_pound_parenthetical_fixed",
    "temperature_quantity_restored",
    "total_weight_range_restored",
}

COMPOUND_QUANTITY_PATTERNS = re.compile(
    r"\bplus\s+(?:\d|one|two|three|four|five|six|seven|eight|nine|ten)\b"
    r"|\bfor boiling\b",
    re.I,
)

VARIABLE_PACKAGE_UNITS = {
    "bag", "bags",
    "bottle", "bottles",
    "box", "boxes",
    "can", "cans",
    "carton", "cartons",
    "container", "containers",
    "envelope", "envelopes",
    "jar", "jars",
    "package", "packages",
    "packet", "packets",
    "pkg", "pkgs",
    "pouch", "pouches",
    "sprig", "sprigs",
    "bunch", "bunches",
    "serving", "servings",
}

UNIT_ALIASES = {
    "tsp": "tsp",
    "teaspoon": "tsp",
    "teaspoons": "tsp",
    "tbsp": "tbsp",
    "tablespoon": "tbsp",
    "tablespoons": "tbsp",
    "cup": "cup",
    "cups": "cup",
    "clove": "clove",
    "cloves": "clove",
    "stalk": "stalk",
    "stalks": "stalk",
    "sprig": "sprig",
    "sprigs": "sprig",
    "branch": "sprig",
    "branches": "sprig",
    "slice": "slice",
    "slices": "slice",
    "stick": "stick",
    "sticks": "stick",
    "leaf": "leaf",
    "leaves": "leaf",
    "head": "head",
    "heads": "head",
    "ear": "ear",
    "ears": "ear",
    "piece": "piece",
    "pieces": "piece",
    "pinch": "pinch",
    "pinches": "pinch",
    "dash": "dash",
    "dashes": "dash",
    "oz": "oz",
    "ounce": "oz",
    "ounces": "oz",
    "lb": "lb",
    "lbs": "lb",
    "pound": "lb",
    "pounds": "lb",
    "g": "g",
    "gram": "g",
    "grams": "g",
    "kg": "kg",
    "kilogram": "kg",
    "kilograms": "kg",
    "ml": "ml",
    "milliliter": "ml",
    "milliliters": "ml",
    "millilitre": "ml",
    "millilitres": "ml",
    "fl_oz": "fl_oz",
    "fl oz": "fl_oz",
    "floz": "fl_oz",
    "fluid ounce": "fl_oz",
    "fluid ounces": "fl_oz",
    "pint": "pint",
    "pints": "pint",
    "pt": "pint",
    "quart": "quart",
    "quarts": "quart",
    "qt": "quart",
    "gallon": "gallon",
    "gallons": "gallon",
    "gal": "gallon",
    "l": "liter",
    "liter": "liter",
    "liters": "liter",
    "litre": "liter",
    "litres": "liter",
}

DENSITY_STATE_TOKENS = {
    "whipped",
    "powdered",
    "condensed",
    "concentrated",
    "dehydrated",
    "freeze-dried",
}

FORM_STATE_TOKENS = {
    "packed",
    "unpacked",
    "brownulated",
    "fresh",
    "dried",
    "ground",
    "whole",
    "peppercorn",
    "peppercorns",
    "cracked",
    "crumbled",
    "crushed",
    "chopped",
    "diced",
    "minced",
    "sliced",
    "grated",
    "shredded",
    "julienned",
    "strips",
    "rings",
    "quartered",
    "halved",
    "hulled",
    "mashed",
    "pureed",
    "puree",
    "cubed",
    "cubes",
    "cut",
    "wedges",
    "chunks",
    "drained",
    "sifted",
    "toasted",
    "halves",
    "pieces",
    "small",
    "medium",
    "large",
    "jumbo",
}

TEMP_RANGE_RE = re.compile(
    r"\b(?:70|75|80|85|90|95|100|105|110|115|120)\s*(?:-|to|–|—)\s*"
    r"(?:70|75|80|85|90|95|100|105|110|115|120)\s*°?\s*f\b",
    re.I,
)

REVIEW_ITEM_TERMS = {
    "ice cream",
    "gelato",
    "frozen yogurt",
    "coffee creamer",
}

FORCE_MODAL_TERMS = {
    "black pepper",
    "cheddar cheese",
    "extra virgin olive oil",
    "garlic",
    "mozzarella cheese",
    "olive oil",
    "parmesan cheese",
    "sharp cheddar cheese",
    "vegetable oil",
    "canola oil",
    "onion",
    "onions",
}

EXACT_UNIT_GRAMS = {
    "water": {
        "tsp": 5.0,
        "tbsp": 14.8,
        "cup": 240.0,
        "fl_oz": 29.6,
        "pint": 473.0,
        "quart": 946.0,
        "gallon": 3785.0,
        "ml": 1.0,
        "liter": 1000.0,
    },
    "all-purpose flour": {"tsp": 2.6, "tbsp": 7.8, "cup": 125.0},
    "flour": {"tsp": 2.6, "tbsp": 7.8, "cup": 125.0},
    "plain flour": {"tsp": 2.6, "tbsp": 7.8, "cup": 125.0},
    "white flour": {"tsp": 2.6, "tbsp": 7.8, "cup": 125.0},
    "sugar": {"tsp": 4.0, "tbsp": 12.5, "cup": 200.0},
    "granulated sugar": {"tsp": 4.0, "tbsp": 12.5, "cup": 200.0},
    "baking powder": {"tsp": 4.0, "tbsp": 12.0},
    "olive oil": {"tsp": 4.5, "tbsp": 13.5, "cup": 216.0},
    "extra virgin olive oil": {"tsp": 4.5, "tbsp": 13.5, "cup": 216.0},
    "vegetable oil": {"tsp": 4.5, "tbsp": 13.6, "cup": 218.0},
    "canola oil": {"tsp": 4.5, "tbsp": 13.6, "cup": 218.0},
}

MASS_UNIT_GRAMS = {
    "g": 1.0,
    "kg": 1000.0,
    "oz": 28.349523125,
    "lb": 453.59237,
    "ml": 1.0,
    "liter": 1000.0,
}


def as_float(value: str | None) -> float | None:
    try:
        return float(value or "")
    except (TypeError, ValueError):
        return None


def canonical_unit(value: str | None) -> str | None:
    unit = (value or "").strip().lower().replace(".", "")
    return UNIT_ALIASES.get(unit)


def key_for(row: dict[str, str]) -> tuple[str, float, str] | None:
    item = (row.get("ingredient_item") or "").strip().lower()
    display = (row.get("display") or "").strip().lower()
    qty = as_float(row.get("qty"))
    unit = canonical_unit(row.get("unit"))
    grams = as_float(row.get("grams_resolved"))
    if not item or qty is None or qty <= 0 or unit is None:
        return None
    if grams is None or grams <= 0:
        return None
    if (row.get("grams_source") or "") in REPAIRED_QUANTITY_SOURCES:
        return None
    if COMPOUND_QUANTITY_PATTERNS.search(display):
        return None
    raw_unit = (row.get("unit") or "").strip().lower()
    if raw_unit in VARIABLE_PACKAGE_UNITS or unit in VARIABLE_PACKAGE_UNITS:
        return None
    if qty >= 50 and TEMP_RANGE_RE.search(display):
        return None
    for token in DENSITY_STATE_TOKENS | FORM_STATE_TOKENS:
        if token in display and token not in item:
            return None
    return (item, round(qty, 6), unit)


def exact_rule_value(item: str, qty: float, unit: str) -> float | None:
    grams_per_unit = MASS_UNIT_GRAMS.get(unit)
    if grams_per_unit is not None:
        return round(qty * grams_per_unit, 1)
    for term, unit_map in EXACT_UNIT_GRAMS.items():
        if item == term:
            grams_per_unit = unit_map.get(unit)
            if grams_per_unit is not None:
                return round(qty * grams_per_unit, 1)
    return None


def choose_anchor_grams(bucket: dict) -> float | None:
    anchor_counts: dict[float, int] = defaultdict(int)
    for source, grams_counts in bucket["source_grams"].items():
        if source not in ANCHOR_GRAMS_SOURCES:
            continue
        for grams, count in grams_counts.items():
            anchor_counts[grams] += count
    if not anchor_counts:
        return None
    return sorted(anchor_counts.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]


def should_review_item(item: str) -> bool:
    return any(term in item for term in REVIEW_ITEM_TERMS)


def cup_equivalent(qty: float, unit: str) -> float | None:
    if unit == "cup":
        return qty
    if unit == "tbsp":
        return qty / 16.0
    if unit == "tsp":
        return qty / 48.0
    return None


def implausible_liquid_density(item: str, qty: float, unit: str, modal_g: float) -> bool:
    if "broth" not in item and "stock" not in item:
        return False
    cups = cup_equivalent(qty, unit)
    if not cups:
        return False
    grams_per_cup = modal_g / cups
    return grams_per_cup < 220.0 or grams_per_cup > 265.0


def force_modal_allowed(item: str, modal_share: float) -> bool:
    min_share = 0.50 if "cheese" in item or item == "garlic" else 0.70
    return item in FORCE_MODAL_TERMS and modal_share >= min_share


def build_rules(args: argparse.Namespace) -> tuple[dict[tuple[str, float, str], float], list[dict]]:
    buckets = defaultdict(lambda: {
        "grams": defaultdict(int),
        "sources": defaultdict(int),
        "source_grams": defaultdict(lambda: defaultdict(int)),
        "htcs": defaultdict(int),
        "samples": [],
    })
    rows_seen = 0

    with RECIPES.open() as f:
        for row in csv.DictReader(f):
            rows_seen += 1
            key = key_for(row)
            if key is None:
                continue
            grams = round(float(row["grams_resolved"]), 1)
            bucket = buckets[key]
            bucket["grams"][grams] += 1
            source = row.get("grams_source", "")
            bucket["sources"][source] += 1
            bucket["source_grams"][source][grams] += 1
            bucket["htcs"][row.get("htc_code", "")] += 1
            if len(bucket["samples"]) < 3:
                bucket["samples"].append((row.get("recipe_id", ""), row.get("display", "")[:80]))
            if rows_seen % 500_000 == 0:
                print(f"  {rows_seen:,} rows scanned", file=sys.stderr)

    rules: dict[tuple[str, float, str], float] = {}
    review_rows: list[dict] = []
    for key, bucket in buckets.items():
        grams_counts = bucket["grams"]
        if len(grams_counts) <= 1:
            continue
        n_lines = sum(grams_counts.values())
        ordered = sorted(grams_counts.items(), key=lambda kv: (-kv[1], kv[0]))
        modal_g, modal_count = ordered[0]
        modal_share = modal_count / n_lines
        max_g = max(grams_counts)
        min_g = min(grams_counts)
        ratio = max_g / min_g if min_g > 0 else 0.0
        item, qty, unit = key
        row = {
            "item": item,
            "qty": f"{qty:g}",
            "unit": unit,
            "n_lines": n_lines,
            "n_distinct_grams": len(grams_counts),
            "modal_g": modal_g,
            "modal_count": modal_count,
            "modal_share": round(modal_share, 4),
            "min_g": min_g,
            "max_g": max_g,
            "ratio": round(ratio, 2),
            "all_grams": "|".join(f"{g}g={n}" for g, n in ordered[:8]),
            "sources": "|".join(f"{source}={n}" for source, n in bucket["sources"].items()),
            "n_htcs": len(bucket["htcs"]),
            "sample": " ; ".join(f"{rid}:{display}" for rid, display in bucket["samples"]),
        }
        anchor_g = choose_anchor_grams(bucket)
        exact_g = exact_rule_value(item, qty, unit)
        if should_review_item(item) and not args.all_deterministic_drift:
            row["decision"] = "review"
        elif (
            not args.all_deterministic_drift
            and implausible_liquid_density(
                item, qty, unit,
                anchor_g if anchor_g is not None else exact_g if exact_g is not None else modal_g,
            )
        ):
            row["decision"] = "review"
        elif anchor_g is not None:
            rules[key] = anchor_g
            row["decision"] = "apply"
            row["decision_reason"] = "anchor_source"
            row["modal_g"] = anchor_g
        elif exact_g is not None and n_lines >= args.min_lines:
            rules[key] = exact_g
            row["decision"] = "apply"
            row["decision_reason"] = "exact_unit_rule"
            row["modal_g"] = exact_g
        elif n_lines >= args.min_lines and (
            modal_share >= args.min_modal_share
            or force_modal_allowed(item, modal_share)
        ):
            rules[key] = modal_g
            row["decision"] = "apply"
            row["decision_reason"] = "modal_threshold"
        elif args.all_deterministic_drift:
            rules[key] = modal_g
            row["decision"] = "apply"
            row["decision_reason"] = "determinism_audit_modal"
        else:
            row["decision"] = "review"
            row["decision_reason"] = "below_threshold"
        review_rows.append(row)

    review_rows.sort(key=lambda r: (r["decision"] != "apply", -int(r["n_lines"])))
    return rules, review_rows


def apply_rules(rules: dict[tuple[str, float, str], float], dry_run: bool) -> tuple[int, int, list[dict]]:
    rows_seen = 0
    changed = 0
    samples: list[dict] = []

    def process(row: dict[str, str], writer: csv.DictWriter | None) -> None:
        nonlocal rows_seen, changed
        rows_seen += 1
        key = key_for(row)
        new_g = rules.get(key) if key is not None else None
        old_g = as_float(row.get("grams_resolved"))
        if new_g is not None and old_g is not None and abs(round(old_g, 1) - new_g) > 0.05:
            changed += 1
            if len(samples) < 25:
                item, qty, unit = key
                samples.append({
                    "recipe_id": row.get("recipe_id", ""),
                    "item": item,
                    "qty": f"{qty:g}",
                    "unit": unit,
                    "display": row.get("display", "")[:80],
                    "old_g": round(old_g, 2),
                    "new_g": new_g,
                    "old_source": row.get("grams_source", ""),
                })
            row["grams_resolved"] = f"{new_g:.2f}"
            row["grams_source"] = SOURCE
        if writer is not None:
            writer.writerow(row)
        if rows_seen % 500_000 == 0:
            print(f"  {rows_seen:,} rows applied", file=sys.stderr)

    if dry_run:
        with RECIPES.open() as f:
            for row in csv.DictReader(f):
                process(row, None)
        return rows_seen, changed, samples

    out_dir = RECIPES.parent
    tmp_fd, tmp_path = tempfile.mkstemp(prefix=".unified_modal_norm_", suffix=".csv", dir=str(out_dir))
    os.close(tmp_fd)
    try:
        with RECIPES.open() as f_in, open(tmp_path, "w", newline="") as f_out:
            reader = csv.DictReader(f_in)
            writer = csv.DictWriter(f_out, fieldnames=reader.fieldnames)
            writer.writeheader()
            for row in reader:
                process(row, writer)
        os.replace(tmp_path, RECIPES)
    except Exception:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise
    return rows_seen, changed, samples


def write_review(rows: list[dict]) -> None:
    if not rows:
        return
    with REVIEW.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_log(rows: list[dict], rules: dict[tuple[str, float, str], float]) -> None:
    applied = [row for row in rows if row["decision"] == "apply"]
    if not applied:
        return
    with LOG.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(applied[0].keys()))
        writer.writeheader()
        writer.writerows(applied)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--min-lines", type=int, default=25)
    parser.add_argument("--min-modal-share", type=float, default=0.90)
    parser.add_argument(
        "--all-deterministic-drift",
        action="store_true",
        help=(
            "Apply one gram value to every deterministic drift bucket that "
            "the gram determinism audit would fail. SR28/reviewed anchors "
            "win when present; otherwise the bucket modal is used."
        ),
    )
    args = parser.parse_args()

    if not RECIPES.exists():
        print(f"missing {RECIPES}", file=sys.stderr)
        sys.exit(1)

    print("building deterministic modal gram rules", file=sys.stderr)
    rules, review_rows = build_rules(args)
    write_review(review_rows)
    write_log(review_rows, rules)

    apply_rows = [row for row in review_rows if row["decision"] == "apply"]
    review_only = [row for row in review_rows if row["decision"] == "review"]
    print(f"\neligible household-unit drift buckets: {len(review_rows):,}", file=sys.stderr)
    print(f"rules to apply:                       {len(rules):,}", file=sys.stderr)
    print(f"review-only drift buckets:            {len(review_only):,}", file=sys.stderr)
    print(f"review written to:                    {REVIEW}", file=sys.stderr)
    print(f"log written to:                       {LOG}", file=sys.stderr)

    rows_seen, changed, samples = apply_rules(rules, args.dry_run)
    print(f"\nrows scanned:                         {rows_seen:,}", file=sys.stderr)
    print(f"rows changed:                         {changed:,}", file=sys.stderr)
    if args.dry_run:
        print("mode:                                 dry-run", file=sys.stderr)
    else:
        print("mode:                                 applied", file=sys.stderr)

    print("\nSample changes:", file=sys.stderr)
    for sample in samples[:15]:
        print(
            f"  rid={sample['recipe_id']:>6} {sample['item'][:24]:<24} "
            f"{sample['qty']} {sample['unit']}: {sample['old_g']}g -> "
            f"{sample['new_g']}g ({sample['old_source']})",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
