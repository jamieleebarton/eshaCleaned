#!/usr/bin/env python3
"""Build a row-level semantic normalization audit table.

This is intentionally a thin CSV: it keeps the source identifiers and current
leaf, then appends the proposed semantic category/head/filter record so the
current taxonomy can be audited row by row.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

import semantic_hard_eval
import semantic_labeler


REPO = Path("/Users/jamiebarton/Desktop/esha_audit_bundle")
V2 = REPO / "retail_mapper" / "v2"
DEFAULT_INPUT = V2 / "retail_leaf_v2_enriched_v2.csv"
DEFAULT_TAXONOMY = REPO / "implementation" / "output" / "taxonomy_paths_cleaned.csv"
DEFAULT_OUTPUT = V2 / "semantic_normalization_audit.csv"
DEFAULT_ISSUES_OUTPUT = V2 / "semantic_normalization_issue_queue.csv"
DEFAULT_SUMMARY = V2 / "semantic_normalization_audit_summary.json"

csv.field_size_limit(sys.maxsize)

FIELDNAMES = [
    "fdc_id",
    "gtin_upc",
    "title",
    "brand_name",
    "brand_owner",
    "branded_food_category",
    "current_esha",
    "current_esha_desc",
    "current_leaf",
    "semantic_category_path",
    "semantic_head",
    "semantic_filter_attributes",
    "semantic_proposed_path",
    "semantic_existing_path",
    "semantic_status",
    "semantic_parent_exists",
    "semantic_retail_type",
    "semantic_supercategory",
    "semantic_family",
    "semantic_form",
    "semantic_base_identity",
    "semantic_confidence",
    "semantic_notes",
    "hard_eval_cohorts",
    "hard_eval_issue_flags",
]


def semantic_status(record: semantic_labeler.SemanticRecord) -> str:
    if record.existing_path:
        return "existing"
    if record.parent_exists:
        return "mint_parent_exists"
    return "mint_missing_parent"


def dedupe_preserve(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out


def audit_row(row: dict[str, str], taxonomy: set[str]) -> dict[str, object]:
    record = semantic_labeler.classify_row(row, taxonomy)
    cohorts = semantic_hard_eval.matching_cohorts(row)
    issue_flags: list[str] = []
    for cohort in cohorts:
        issue_flags.extend(semantic_hard_eval.issue_flags(cohort, row, record))
    issue_flags = dedupe_preserve(issue_flags)

    return {
        "fdc_id": row.get("fdc_id", ""),
        "gtin_upc": row.get("gtin_upc", ""),
        "title": row.get("title", ""),
        "brand_name": row.get("brand_name", ""),
        "brand_owner": row.get("brand_owner", ""),
        "branded_food_category": row.get("branded_food_category", ""),
        "current_esha": row.get("current_esha", ""),
        "current_esha_desc": row.get("current_esha_desc", ""),
        "current_leaf": row.get("retail_leaf", ""),
        "semantic_category_path": record.category_path,
        "semantic_head": record.head,
        "semantic_filter_attributes": json.dumps(record.filter_attributes, sort_keys=True),
        "semantic_proposed_path": record.proposed_path,
        "semantic_existing_path": record.existing_path,
        "semantic_status": semantic_status(record),
        "semantic_parent_exists": record.parent_exists,
        "semantic_retail_type": record.retail_type,
        "semantic_supercategory": record.supercategory,
        "semantic_family": record.family,
        "semantic_form": record.form,
        "semantic_base_identity": record.base_identity,
        "semantic_confidence": record.confidence,
        "semantic_notes": "|".join(record.notes),
        "hard_eval_cohorts": "|".join(cohorts),
        "hard_eval_issue_flags": "|".join(issue_flags),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build semantic normalization audit CSV.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--taxonomy", type=Path, default=DEFAULT_TAXONOMY)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--issues-output", type=Path, default=DEFAULT_ISSUES_OUTPUT)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    taxonomy = semantic_labeler.load_taxonomy(args.taxonomy)

    counters: dict[str, Counter[str]] = {
        "semantic_status": Counter(),
        "semantic_category_path": Counter(),
        "semantic_head": Counter(),
        "semantic_notes": Counter(),
        "hard_eval_cohorts": Counter(),
        "hard_eval_issue_flags": Counter(),
        "current_leaf": Counter(),
    }
    rows_total = 0
    semantic_rows = 0
    fallback_rows = 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with (
        args.input.open(errors="replace", newline="") as source,
        args.output.open("w", newline="", encoding="utf-8") as dest,
        args.issues_output.open("w", newline="", encoding="utf-8") as issue_dest,
    ):
        reader = csv.DictReader(source)
        writer = csv.DictWriter(dest, fieldnames=FIELDNAMES)
        issue_writer = csv.DictWriter(issue_dest, fieldnames=FIELDNAMES)
        writer.writeheader()
        issue_writer.writeheader()

        for row in reader:
            rows_total += 1
            out = audit_row(row, taxonomy)
            writer.writerow(out)
            if out["hard_eval_issue_flags"]:
                issue_writer.writerow(out)

            if out["semantic_notes"] == "fallback_record":
                fallback_rows += 1
            else:
                semantic_rows += 1

            counters["semantic_status"].update([str(out["semantic_status"])])
            counters["semantic_category_path"].update([str(out["semantic_category_path"])])
            counters["semantic_head"].update([str(out["semantic_head"])])
            counters["current_leaf"].update([str(out["current_leaf"])])
            for note in str(out["semantic_notes"]).split("|"):
                if note:
                    counters["semantic_notes"].update([note])
            for cohort in str(out["hard_eval_cohorts"]).split("|"):
                if cohort:
                    counters["hard_eval_cohorts"].update([cohort])
            for issue in str(out["hard_eval_issue_flags"]).split("|"):
                if issue:
                    counters["hard_eval_issue_flags"].update([issue])

            if args.limit and rows_total >= args.limit:
                break

    summary = {
        "input": str(args.input),
        "taxonomy": str(args.taxonomy),
        "output": str(args.output),
        "issues_output": str(args.issues_output),
        "rows_total": rows_total,
        "semantic_router_rows": semantic_rows,
        "fallback_rows": fallback_rows,
        "semantic_router_rate": round(semantic_rows / rows_total, 4) if rows_total else 0,
        "top_counts": {
            name: dict(counter.most_common(40))
            for name, counter in counters.items()
        },
    }
    with args.summary.open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2, sort_keys=True)
        handle.write("\n")

    print(f"rows_total: {rows_total}")
    print(f"semantic_router_rows: {semantic_rows}")
    print(f"fallback_rows: {fallback_rows}")
    print(f"output: {args.output}")
    print(f"issues_output: {args.issues_output}")
    print(f"summary: {args.summary}")
    print(f"hard_eval_issue_flags: {json.dumps(summary['top_counts']['hard_eval_issue_flags'], sort_keys=True)}")


if __name__ == "__main__":
    main()
