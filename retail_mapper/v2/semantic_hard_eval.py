#!/usr/bin/env python3
"""Stress-test semantic head/filter normalization on real retail rows.

The goal is not coverage. It samples high-friction cohorts where naive path
generation tends to fragment identities: ice cream flavors/forms, pizza vs
pizza-adjacent products, real meals, and meal false friends.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from dataclasses import asdict
from pathlib import Path

import semantic_labeler as labeler


REPO = Path("/Users/jamiebarton/Desktop/esha_audit_bundle")
V2 = REPO / "retail_mapper" / "v2"
DEFAULT_INPUT = V2 / "retail_leaf_v2_enriched_v2.csv"
DEFAULT_TAXONOMY = REPO / "implementation" / "output" / "taxonomy_paths_cleaned.csv"
DEFAULT_CSV = V2 / "semantic_hard_eval.csv"
DEFAULT_SUMMARY = V2 / "semantic_hard_eval_summary.json"

csv.field_size_limit(sys.maxsize)

COHORTS = (
    "ice_cream_plain",
    "ice_cream_form",
    "pizza_meal",
    "pizza_adjacent",
    "meal_composite",
    "meal_false_friend",
)

ICE_CREAM_HEADS = {
    "Frozen Yogurt",
    "Gelato",
    "Ice Cream",
    "Ice Cream Bar",
    "Ice Cream Cake",
    "Ice Cream Cone",
    "Ice Cream Mix",
    "Ice Cream Sandwich",
    "Ice Cream Sundae",
    "Sherbet",
    "Sorbet",
}

PIZZA_ADJACENT_TOKENS = {
    "crust",
    "crusts",
    "dough",
    "roll",
    "rolls",
    "sauce",
    "sauces",
}


def has_any_phrase(text: str, phrases: tuple[str, ...]) -> bool:
    return any(phrase in text for phrase in phrases)


def ice_cream_form_expected(row: dict[str, str]) -> bool:
    title_norm = labeler.normalize_text(row.get("title", ""))
    tokens = set(labeler.tokens_for(row.get("title", "")))
    return (
        has_any_phrase(
            title_norm,
            (
                "ice cream sandwich",
                "ice cream bar",
                "ice cream cake",
                "ice cream cone",
                "ice cream mix",
                "frozen yogurt",
            ),
        )
        or bool(tokens & {"gelato", "sorbet", "sherbet", "sundae", "sundaes"})
    )


def pizza_adjacent_expected(row: dict[str, str]) -> bool:
    title_tokens = set(labeler.tokens_for(row.get("title", "")))
    title_norm = labeler.normalize_text(row.get("title", ""))
    bfc_norm = labeler.normalize_text(row.get("branded_food_category", ""))
    return (
        bool(title_tokens & {"dough", "roll", "rolls", "sauce", "sauces"})
        or "pizza crust" in title_norm
        or "pizza crusts" in title_norm
        or "lunch snacks" in bfc_norm
        or "pizza sauces" in bfc_norm
        or "crusts dough" in bfc_norm
    )


def meal_false_friend_expected(row: dict[str, str]) -> bool:
    title = row.get("title", "")
    title_norm = labeler.normalize_text(title)
    title_tokens = set(labeler.tokens_for(title))
    bfc_norm = labeler.normalize_text(row.get("branded_food_category", ""))
    return (
        "cornmeal" in title_tokens
        or "corn meal" in title_norm
        or "cake meal" in title_norm
        or "matzo meal" in title_norm
        or "matzoh meal" in title_norm
        or "oatmeal" in title_tokens
        or "oat meal" in title_norm
        or "meal replacement" in title_norm
        or (bool(title_tokens & {"bar", "bars"}) and ("bar" in bfc_norm or "snack energy granola bars" in bfc_norm))
        or (bool(title_tokens & {"roll", "rolls", "bun", "buns", "bread", "breads"}) and "bread" in bfc_norm)
        or (bool(title_tokens & {"biscuit", "biscuits"}) and "breakfast sandwiches biscuits meals" in bfc_norm)
        or ("breakfast drinks" in bfc_norm and "meal" in title_tokens)
        or ("meal" in title_tokens and any(hint in bfc_norm for hint in labeler.MEAL_FALSE_FRIEND_BFC_HINTS))
    )


def matching_cohorts(row: dict[str, str]) -> list[str]:
    cohorts: list[str] = []
    bfc_norm = labeler.normalize_text(row.get("branded_food_category", ""))
    likely_real_ice_cream = bfc_norm == "ice cream frozen yogurt" or "frozen dessert" in bfc_norm
    ice_cream_context = labeler.is_ice_cream_context(row)
    pizza_context = labeler.is_pizza_context(row)
    if ice_cream_context and likely_real_ice_cream:
        cohorts.append("ice_cream_form" if ice_cream_form_expected(row) else "ice_cream_plain")
    if pizza_context:
        cohorts.append("pizza_adjacent" if pizza_adjacent_expected(row) else "pizza_meal")
    if meal_false_friend_expected(row) and not pizza_context:
        cohorts.append("meal_false_friend")
    if labeler.is_meal_context(row) and not pizza_context and not ice_cream_context:
        cohorts.append("meal_composite")
    return cohorts


def issue_flags(cohort: str, row: dict[str, str], record: labeler.SemanticRecord) -> list[str]:
    issues: list[str] = []
    head_tokens = labeler.token_set(record.head)
    title_tokens = labeler.token_set(row.get("title", ""))

    if cohort.startswith("ice_cream"):
        flavor_tokens = (title_tokens & labeler.ICE_CREAM_FLAVOR_TOKENS) - {"cream"}
        if record.category_path != "Frozen > Ice Cream":
            issues.append("ice_cream_wrong_category")
        if record.head not in ICE_CREAM_HEADS:
            issues.append("ice_cream_unexpected_head")
        if head_tokens & flavor_tokens:
            issues.append("ice_cream_flavor_promoted")
        if record.head == "Light Ice Cream":
            issues.append("ice_cream_diet_or_fat_promoted")
        if cohort == "ice_cream_form" and record.head == "Ice Cream":
            issues.append("ice_cream_form_not_promoted")

    if cohort == "pizza_meal":
        topping_tokens = title_tokens & labeler.PIZZA_TOPPING_TOKENS
        if record.category_path != "Meal > Pizza":
            issues.append("pizza_meal_wrong_category")
        if record.head != "Pizza":
            issues.append("pizza_topping_or_variant_promoted")
        if head_tokens & topping_tokens:
            issues.append("pizza_topping_in_head")

    if cohort == "pizza_adjacent":
        if record.category_path == "Meal > Pizza":
            issues.append("pizza_adjacent_routed_to_meal")
        bfc_norm = labeler.normalize_text(row.get("branded_food_category", ""))
        lunch_pack = "lunch snacks" in bfc_norm or (
            "lunch" in title_tokens and bool({"pack", "combination"} & title_tokens)
        )
        if record.head == "Pizza Roll":
            pass
        elif lunch_pack:
            if record.head != "Pizza Lunch Kit":
                issues.append("pizza_lunch_kit_wrong_head")
        elif "dough" in title_tokens:
            if record.head != "Pizza Dough":
                issues.append("pizza_dough_wrong_head")
        elif "sauce" in title_tokens:
            if record.head != "Pizza Sauce":
                issues.append("pizza_sauce_wrong_head")
        elif "crust" in title_tokens and record.head not in {"Pizza Crust", "Pizza Crust Mix"}:
            issues.append("pizza_crust_wrong_head")

    if cohort == "meal_false_friend":
        if record.supercategory == "Meal":
            issues.append("meal_false_friend_routed_to_meal")

    if cohort == "meal_composite":
        if record.supercategory != "Meal":
            issues.append("meal_not_routed_to_meal")
        if len(labeler.tokens_for(record.head)) > 4:
            issues.append("meal_head_too_specific")
        if record.form == "entree" and not record.base_identity:
            issues.append("meal_missing_dish_identity")

    return issues


def summarize(records: list[dict[str, object]], scanned_rows: int) -> dict[str, object]:
    by_cohort: dict[str, dict[str, object]] = {}
    for cohort in COHORTS:
        cohort_rows = [row for row in records if row["cohort"] == cohort]
        issue_counter = Counter()
        head_counter = Counter()
        category_counter = Counter()
        for row in cohort_rows:
            issue_counter.update(row["issue_flags"])
            head_counter[row["head"]] += 1
            category_counter[row["category_path"]] += 1
        by_cohort[cohort] = {
            "rows": len(cohort_rows),
            "mint_required": sum(1 for row in cohort_rows if row["mint_required"]),
            "parent_missing": sum(1 for row in cohort_rows if not row["parent_exists"]),
            "issue_counts": dict(issue_counter.most_common()),
            "top_heads": dict(head_counter.most_common(12)),
            "top_category_paths": dict(category_counter.most_common(12)),
        }

    issue_counter = Counter()
    for row in records:
        issue_counter.update(row["issue_flags"])

    examples = [
        {
            "cohort": row["cohort"],
            "fdc_id": row["fdc_id"],
            "title": row["title"],
            "branded_food_category": row["branded_food_category"],
            "current_leaf": row["current_leaf"],
            "category_path": row["category_path"],
            "head": row["head"],
            "issue_flags": row["issue_flags"],
        }
        for row in records
        if row["issue_flags"]
    ][:25]

    return {
        "scanned_rows": scanned_rows,
        "sampled_records": len(records),
        "issue_counts": dict(issue_counter.most_common()),
        "by_cohort": by_cohort,
        "issue_examples": examples,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run semantic hard eval over real retail rows.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--taxonomy", type=Path, default=DEFAULT_TAXONOMY)
    parser.add_argument("--limit-per-cohort", type=int, default=100)
    parser.add_argument("--max-rows", type=int, default=0)
    parser.add_argument("--csv-out", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--summary-out", type=Path, default=DEFAULT_SUMMARY)
    args = parser.parse_args()

    taxonomy = labeler.load_taxonomy(args.taxonomy)
    samples: dict[str, list[dict[str, object]]] = defaultdict(list)
    scanned_rows = 0

    with args.input.open(errors="replace", newline="") as handle:
        for row in csv.DictReader(handle):
            scanned_rows += 1
            if args.max_rows and scanned_rows > args.max_rows:
                break

            take = [cohort for cohort in matching_cohorts(row) if len(samples[cohort]) < args.limit_per_cohort]
            if not take:
                if all(len(samples[cohort]) >= args.limit_per_cohort for cohort in COHORTS):
                    break
                continue

            record = labeler.classify_row(row, taxonomy)
            record_dict = asdict(record)
            for cohort in take:
                issues = issue_flags(cohort, row, record)
                samples[cohort].append(
                    {
                        "cohort": cohort,
                        "fdc_id": row.get("fdc_id", ""),
                        "title": row.get("title", ""),
                        "branded_food_category": row.get("branded_food_category", ""),
                        "current_leaf": row.get("retail_leaf", ""),
                        "category_path": record.category_path,
                        "head": record.head,
                        "filter_attributes": record.filter_attributes,
                        "proposed_path": record.proposed_path,
                        "existing_path": record.existing_path,
                        "mint_required": record.mint_required,
                        "parent_exists": record.parent_exists,
                        "confidence": record.confidence,
                        "notes": record.notes,
                        "issue_flags": issues,
                        "record": record_dict,
                    }
                )

            if all(len(samples[cohort]) >= args.limit_per_cohort for cohort in COHORTS):
                break

    records = [row for cohort in COHORTS for row in samples[cohort]]
    args.csv_out.parent.mkdir(parents=True, exist_ok=True)
    with args.csv_out.open("w", newline="", encoding="utf-8") as handle:
        fieldnames = [
            "cohort",
            "fdc_id",
            "title",
            "branded_food_category",
            "current_leaf",
            "category_path",
            "head",
            "filter_attributes",
            "proposed_path",
            "existing_path",
            "mint_required",
            "parent_exists",
            "confidence",
            "notes",
            "issue_flags",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in records:
            out = {field: row.get(field, "") for field in fieldnames}
            out["filter_attributes"] = json.dumps(out["filter_attributes"], sort_keys=True)
            out["notes"] = "|".join(out["notes"])
            out["issue_flags"] = "|".join(out["issue_flags"])
            writer.writerow(out)

    summary = summarize(records, scanned_rows)
    with args.summary_out.open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2, sort_keys=True)
        handle.write("\n")

    print(f"scanned_rows: {scanned_rows}")
    print(f"sampled_records: {len(records)}")
    print(f"csv: {args.csv_out}")
    print(f"summary: {args.summary_out}")
    print(f"issue_counts: {json.dumps(summary['issue_counts'], sort_keys=True)}")
    for cohort in COHORTS:
        data = summary["by_cohort"][cohort]
        print(
            f"{cohort}: rows={data['rows']} mint={data['mint_required']} "
            f"parent_missing={data['parent_missing']} issues={json.dumps(data['issue_counts'], sort_keys=True)}"
        )


if __name__ == "__main__":
    main()
