#!/usr/bin/env python3
"""Build Codex retail-mapper CSV outputs and focused audit files."""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from collections import Counter

from title_parser import (
    OUTPUT_FIELDS,
    AxisLexicon,
    base_normalize,
    clean_duplicate_tail,
    has_milk_chocolate_context,
    has_phrase,
    plant_milk_bases_from_tokens,
    plant_milk_evidence,
    repo_root,
    select_plant_milk_base,
    tokens_for,
    write_parsed_csv,
)


SOURCE_FIELDS = [
    "gtin_upc",
    "fdc_id",
    "product_description",
    "branded_food_category",
    "fixy_category",
    "v6_fndds_description",
    "best_esha_description",
    "top_ingredient_terms",
]


def load_json_list(value: str) -> list[object]:
    try:
        parsed = json.loads(value or "[]")
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def evidence_label(row: dict[str, str]) -> str:
    labels = [
        ("bfc", row.get("branded_food_category", "")),
        ("fixy", row.get("fixy_category", "")),
        ("fndds", row.get("v6_fndds_description", "")),
        ("esha", row.get("best_esha_description", "")),
        ("ingredients", row.get("top_ingredient_terms", "")),
    ]
    return " | ".join(f"{key}={value}" for key, value in labels if value)


def chocolate_status(source: dict[str, str], parsed: dict[str, str], tokens: list[str]) -> str:
    parsed_group = parsed.get("category_group", "")
    parsed_form = parsed.get("form", "")
    parsed_super = parsed.get("supercategory", "")
    bfc = base_normalize(source.get("branded_food_category", ""))
    confection_bucket = parsed_group == "Chocolate" or bfc in {"chocolate", "candy"}
    dessert_or_named_drink = (
        parsed_form in {"ice cream", "bars", "bar", "shake", "tea"}
        or bfc in {"ice cream frozen yogurt", "iced bottle tea", "protein drinks", "breakfast drinks"}
        or bfc == "energy protein muscle recovery drinks"
    )

    if confection_bucket and "milk" in tokens and "chocolate" in tokens:
        return "milk_chocolate_confection_ok"

    if has_milk_chocolate_context(tokens):
        plant_base = select_plant_milk_base(source, tokens)
        if parsed_group == "Plant-based Milk" and plant_milk_evidence(source, tokens, plant_base):
            return "plant_milk_chocolate_flavor"
        if parsed_form == "milk" or parsed_group == "Dairy Milk":
            return "milk_chocolate_routed_as_milk"
        return "milk_chocolate_confection_ok"

    if has_phrase(tokens, "chocolate milk"):
        if parsed_form == "milk" and parsed_super == "Beverage":
            return "chocolate_milk_ok"
        if dessert_or_named_drink:
            return "chocolate_milk_flavor_context_ok"
        return "chocolate_milk_not_milk"

    if parsed_group == "Plant-based Milk":
        return "plant_milk_chocolate_flavor"
    if parsed_form == "milk" and parsed_super == "Beverage":
        return "dairy_chocolate_flavor"
    return "chocolate_and_milk_other_context"


def plant_beverage_status(source: dict[str, str], parsed: dict[str, str], tokens: list[str]) -> str:
    plant_base = select_plant_milk_base(source, tokens)
    if parsed.get("category_group") == "Plant-based Milk":
        return "plant_milk_normalized"
    if plant_base and plant_milk_evidence(source, tokens, plant_base):
        return "still_generic_with_milk_evidence"
    return "not_milk_context"


def combined_rows(input_path: str, parsed_path: str):
    with open(input_path, newline="") as src_fh, open(parsed_path, newline="") as parsed_fh:
        source_reader = csv.DictReader(src_fh)
        parsed_reader = csv.DictReader(parsed_fh)
        for source, parsed in zip(source_reader, parsed_reader):
            yield source, parsed


def build_helper_outputs(
    input_path: str,
    parsed_path: str,
    out_dir: str,
    lexicon: AxisLexicon,
) -> Counter[tuple[str, str]]:
    summary: Counter[tuple[str, str]] = Counter()
    needs_review_path = os.path.join(out_dir, "codex_parsed_titles_needs_review.csv")
    chocolate_path = os.path.join(out_dir, "codex_chocolate_milk_phrase_audit.csv")
    plant_path = os.path.join(out_dir, "codex_plant_beverage_audit.csv")

    with (
        open(needs_review_path, "w", newline="") as needs_fh,
        open(chocolate_path, "w", newline="") as chocolate_fh,
        open(plant_path, "w", newline="") as plant_fh,
    ):
        needs_writer = csv.DictWriter(needs_fh, fieldnames=OUTPUT_FIELDS)
        chocolate_fields = SOURCE_FIELDS + [
            "parsed_category_group",
            "parsed_category",
            "parsed_primary_food",
            "parsed_form",
            "parsed_flavor",
            "parsed_retail_leaf",
            "status",
            "evidence",
        ]
        plant_fields = chocolate_fields
        chocolate_writer = csv.DictWriter(chocolate_fh, fieldnames=chocolate_fields)
        plant_writer = csv.DictWriter(plant_fh, fieldnames=plant_fields)
        needs_writer.writeheader()
        chocolate_writer.writeheader()
        plant_writer.writeheader()

        for source, parsed in combined_rows(input_path, parsed_path):
            summary[("total", "rows")] += 1
            retail_type = parsed.get("retail_type", "")
            supercategory = parsed.get("supercategory", "")
            category_group = parsed.get("category_group", "")
            if retail_type:
                summary[("retail_type", retail_type)] += 1
            if supercategory:
                summary[("supercategory", supercategory)] += 1
            if category_group:
                summary[("category_group", category_group)] += 1

            needs_review = load_json_list(parsed.get("needs_review", ""))
            axis_review_issues = load_json_list(parsed.get("axis_review_issues", ""))
            for issue in axis_review_issues:
                summary[("axis_review_issue", str(issue))] += 1
            if axis_review_issues:
                summary[("total", "axis_review_rows")] += 1

            if needs_review or axis_review_issues:
                summary[("total", "needs_review")] += 1
                needs_writer.writerow({field: parsed.get(field, "") for field in OUTPUT_FIELDS})

            tokens = tokens_for(lexicon.normalize(clean_duplicate_tail(source.get("product_description", ""))))
            parsed_projection = {
                "parsed_category_group": parsed.get("category_group", ""),
                "parsed_category": parsed.get("category", ""),
                "parsed_primary_food": parsed.get("primary_food", ""),
                "parsed_form": parsed.get("form", ""),
                "parsed_flavor": parsed.get("flavor", ""),
                "parsed_retail_leaf": parsed.get("retail_leaf", ""),
            }
            source_projection = {field: source.get(field, "") for field in SOURCE_FIELDS}

            if "chocolate" in tokens and "milk" in tokens:
                status = chocolate_status(source, parsed, tokens)
                summary[("chocolate_status", status)] += 1
                if status in {"milk_chocolate_routed_as_milk", "chocolate_milk_not_milk"}:
                    summary[("chocolate_issue", status)] += 1
                chocolate_writer.writerow(
                    {
                        **source_projection,
                        **parsed_projection,
                        "status": status,
                        "evidence": evidence_label(source),
                    }
                )

            if {"beverage", "drink"} & set(tokens) and plant_milk_bases_from_tokens(tokens):
                status = plant_beverage_status(source, parsed, tokens)
                summary[("plant_beverage_status", status)] += 1
                plant_writer.writerow(
                    {
                        **source_projection,
                        **parsed_projection,
                        "status": status,
                        "evidence": evidence_label(source),
                    }
                )

    return summary


def write_summary(summary: Counter[tuple[str, str]], output_path: str) -> None:
    total_rows = summary.get(("total", "rows"), 0)
    section_totals: dict[str, int] = {}
    for (section, _), count in summary.items():
        section_totals[section] = section_totals.get(section, 0) + count

    preferred_sections = [
        "total",
        "retail_type",
        "supercategory",
        "category_group",
        "axis_review_issue",
        "chocolate_issue",
        "chocolate_status",
        "plant_beverage_status",
    ]
    with open(output_path, "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["section", "key", "count", "share"])
        for section in preferred_sections:
            items = [(key, count) for (sec, key), count in summary.items() if sec == section]
            if section not in {"total", "chocolate_issue"}:
                items.sort(key=lambda item: (-item[1], item[0]))
            else:
                items.sort(key=lambda item: item[0])
            denom = total_rows if section in {"total", "retail_type", "supercategory", "category_group"} else section_totals.get(section, 0)
            for key, count in items:
                share = count / denom if denom else 0
                writer.writerow([section, key, count, f"{share:.6f}"])


def build_arg_parser() -> argparse.ArgumentParser:
    root = repo_root()
    parser = argparse.ArgumentParser(description="Build Codex retail parser CSVs and audit sidecars.")
    parser.add_argument("--input", default=os.path.join(root, "product_esha_fixy.v6.csv"))
    parser.add_argument("--parsed-output", default=os.path.join(root, "codex_parsed_titles_audit.csv"))
    parser.add_argument("--summary-output", default=os.path.join(root, "codex_parsed_titles_audit_summary.csv"))
    parser.add_argument("--rebuild-parsed", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    root = repo_root()
    lexicon = AxisLexicon(root)
    if args.rebuild_parsed or not os.path.exists(args.parsed_output):
        count = write_parsed_csv(args.input, args.parsed_output, lexicon)
        print(f"Wrote {count:,} parsed rows to {args.parsed_output}", file=sys.stderr)
    summary = build_helper_outputs(args.input, args.parsed_output, root, lexicon)
    write_summary(summary, args.summary_output)
    print(f"Wrote audit sidecars and summary to {root}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
