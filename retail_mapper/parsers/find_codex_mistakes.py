#!/usr/bin/env python3
"""Compare a generated parser CSV against the current parser and list fixes."""
from __future__ import annotations

import argparse
import csv
import os

from title_parser import AxisLexicon, parse_row, repo_root, serialize


FIELDS = [
    "issue_type",
    "fdc_id",
    "gtin_upc",
    "product_description",
    "branded_food_category",
    "old_retail_type",
    "old_category_group",
    "old_category",
    "old_primary_food",
    "old_form",
    "old_flavor",
    "old_retail_leaf",
    "old_components",
    "new_retail_type",
    "new_category_group",
    "new_category",
    "new_primary_food",
    "new_form",
    "new_flavor",
    "new_retail_leaf",
    "new_components",
    "reason",
]


def classify_issue(old: dict[str, str], new: dict[str, object]) -> tuple[str, str] | None:
    title = old.get("product_description", "").lower()
    old_type = old.get("retail_type", "")
    new_type = str(new.get("retail_type", ""))
    old_form = old.get("form", "")
    new_form = str(new.get("form", ""))
    old_group = old.get("category_group", "")
    new_group = str(new.get("category_group", ""))

    if old_type == "combo_pack" and new_type == "single":
        if " with " in f" {title} ":
            return (
                "false_combo_pack_with_ingredient_or_inclusion",
                "Old parse treated 'with' ingredient/inclusion wording as a retail combo pack.",
            )
        return (
            "false_combo_pack_non_combo_wording",
            "Old parse emitted combo_pack but current parser keeps it as a single retail item.",
        )

    if old_form != new_form and {old_form, new_form} & {"coffee", "tea", "latte", "juice", "shake", "drink", "beverage"}:
        return (
            "wrong_main_form_from_flavor_or_ingredient",
            "Old parse selected a beverage/flavor/ingredient word as the main form.",
        )

    if old_group != new_group and old_group in {"Combo Packs", "Coffee", "Tea", "Juice"}:
        return (
            "wrong_category_from_flavor_or_ingredient",
            "Old parse routed by a flavor or ingredient term instead of the actual product.",
        )

    return None


def main() -> int:
    root = repo_root()
    parser = argparse.ArgumentParser(description="Find parser mistakes fixed by the current parser.")
    parser.add_argument("--input", default=os.path.join(root, "product_esha_fixy.v6.csv"))
    parser.add_argument("--old-parsed", default=os.path.join(root, "codex_parsed_titles_audit.csv"))
    parser.add_argument("--output", default=os.path.join(root, "codex_found_mistakes.csv"))
    args = parser.parse_args()

    lexicon = AxisLexicon(root)
    count = 0
    with (
        open(args.input, newline="") as src_fh,
        open(args.old_parsed, newline="") as old_fh,
        open(args.output, "w", newline="") as out_fh,
    ):
        source_reader = csv.DictReader(src_fh)
        old_reader = csv.DictReader(old_fh)
        writer = csv.DictWriter(out_fh, fieldnames=FIELDS)
        writer.writeheader()
        for source, old in zip(source_reader, old_reader):
            new = parse_row(source, lexicon)
            issue = classify_issue(old, new)
            if not issue:
                continue
            issue_type, reason = issue
            writer.writerow(
                {
                    "issue_type": issue_type,
                    "fdc_id": source.get("fdc_id", ""),
                    "gtin_upc": source.get("gtin_upc", ""),
                    "product_description": source.get("product_description", ""),
                    "branded_food_category": source.get("branded_food_category", ""),
                    "old_retail_type": old.get("retail_type", ""),
                    "old_category_group": old.get("category_group", ""),
                    "old_category": old.get("category", ""),
                    "old_primary_food": old.get("primary_food", ""),
                    "old_form": old.get("form", ""),
                    "old_flavor": old.get("flavor", ""),
                    "old_retail_leaf": old.get("retail_leaf", ""),
                    "old_components": old.get("components", ""),
                    "new_retail_type": serialize(new.get("retail_type", "")),
                    "new_category_group": serialize(new.get("category_group", "")),
                    "new_category": serialize(new.get("category", "")),
                    "new_primary_food": serialize(new.get("primary_food", "")),
                    "new_form": serialize(new.get("form", "")),
                    "new_flavor": serialize(new.get("flavor", "")),
                    "new_retail_leaf": serialize(new.get("retail_leaf", "")),
                    "new_components": serialize(new.get("components", [])),
                    "reason": reason,
                }
            )
            count += 1
    print(f"Wrote {count:,} mistake rows to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
