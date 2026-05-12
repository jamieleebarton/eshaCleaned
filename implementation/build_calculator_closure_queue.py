from __future__ import annotations

import argparse
import csv
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DEFAULT_INPUT_DB = ROOT / "output" / "recipe_qa_nutrition_calculation_audit.db"
DEFAULT_OUTPUT_CSV = ROOT / "output" / "calculator_closure_queue.csv"

READY_NUTRITION_STATUSES = {
    "nutrition_ready_g",
    "nutrition_ready_ml_density",
    "nutrition_ready_sr28_anchor",
    "nutrition_ready_sr28_fallback",
    "nutrition_ready_external_catalog",
    "nutrition_ready_split_to_taste_defaults",
}

DONE_BUCKETS = {
    "nutrition_calculable",
    "nutrition_ready_no_buy",
    "intentional_skip",
}

PRODUCT_BUCKETS = {
    "contract_not_passed",
    "product_contract_failed",
    "product_contract_missing",
    "product_not_candidate_covered",
    "product_not_in_audit_scope",
    "product_nutrition_missing",
    "product_nutrition_zero_or_rounded",
    "product_unknown",
    "serving_unit_not_grams",
}

QUANTITY_BUCKETS = {
    "grams_missing_or_zero",
    "manual_quantity_required",
    "quantity_as_needed",
    "quantity_missing",
    "quantity_to_taste",
    "serving_unit_not_supported",
}


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def classify_fix(row: dict[str, object]) -> tuple[str, str, str]:
    bucket = str(row["blocker_bucket"] or "")
    concept_key = str(row["concept_key"] or "")
    nutrition_status = str(row["nutrition_status"] or "")
    line_failure_bucket = str(row["line_failure_bucket"] or "")
    product_contract_key = str(row["product_contract_key"] or "")

    has_concept = bool(concept_key and concept_key != "|||")
    sr28_ready = nutrition_status in {"nutrition_ready_sr28_anchor", "nutrition_ready_sr28_fallback"}
    nutrition_ready = nutrition_status in READY_NUTRITION_STATUSES

    if bucket == "concept_unresolved" or not has_concept:
        return (
            "approved_normalization_rules.csv",
            "concept_identity",
            "Resolve the recipe line to an approved concept or intentional terminal state.",
        )

    if bucket in QUANTITY_BUCKETS:
        if sr28_ready:
            return (
                "reviewed_household_unit_gram_rules.csv",
                "sr28_measure_or_quantity_policy",
                "Concept has SR28 nutrition; add reviewed grams from SR28 measures or quantity policy.",
            )
        return (
            "reviewed_quantity_policies.csv",
            "quantity_policy",
            "Food identity exists but consumed grams are missing or unsupported.",
        )

    if sr28_ready and bucket in PRODUCT_BUCKETS:
        return (
            "audit_recipe_qa_nutrition_calculation.py",
            "calculator_wiring",
            "SR28 nutrition is ready but line is still blocked; calculator wiring is not honoring it.",
        )

    if bucket == "product_nutrition_zero_or_rounded":
        return (
            "reviewed_sr28_nutrition_fallbacks.csv",
            "sr28_nutrition_fallback",
            "Product nutrition is zero/rounded; add or verify SR28 nutrition fallback.",
        )

    if bucket in PRODUCT_BUCKETS:
        if product_contract_key and product_contract_key != concept_key:
            return (
                "approved_product_contracts.csv",
                "shopping_contract_or_sr28_anchor",
                "Product/cart path is blocking a known concept; prefer SR28 nutrition anchor, then cart contract.",
            )
        return (
            "reviewed_sr28_nutrition_fallbacks.csv",
            "sr28_anchor_or_external_catalog",
            "Known concept lacks usable nutrition path; add reviewed SR28 anchor before product fallback.",
        )

    if line_failure_bucket in PRODUCT_BUCKETS and nutrition_ready:
        return (
            "audit_recipe_qa_nutrition_calculation.py",
            "calculator_wiring",
            "Nutrition appears ready but old product failure bucket is still surfacing.",
        )

    return (
        "calculator_closure_review",
        "manual_triage",
        "Unclassified blocker; inspect line, concept, grams, and nutrition status together.",
    )


def rows_from_db(conn: sqlite3.Connection) -> list[dict[str, object]]:
    query = """
        SELECT
            strict_bucket AS blocker_bucket,
            COALESCE(concept_key, '') AS concept_key,
            COALESCE(product_contract_key, '') AS product_contract_key,
            normalized_line,
            MAX(display) AS example_display,
            COUNT(*) AS occurrence_count,
            COUNT(DISTINCT recipe_id) AS recipe_count,
            COALESCE(line_failure_bucket, '') AS line_failure_bucket,
            COALESCE(nutrition_status, '') AS nutrition_status,
            COALESCE(parsed_quantity, '') AS parsed_quantity,
            COALESCE(parsed_unit, '') AS parsed_unit,
            COALESCE(household_unit_rationale, '') AS household_unit_rationale,
            COALESCE(quantity_policy_rationale, '') AS quantity_policy_rationale,
            COALESCE(selected_description, '') AS selected_description,
            COALESCE(selected_category, '') AS selected_category
        FROM ingredient_eval
        WHERE strict_bucket NOT IN ({done})
        GROUP BY
            strict_bucket,
            COALESCE(concept_key, ''),
            COALESCE(product_contract_key, ''),
            normalized_line,
            COALESCE(line_failure_bucket, ''),
            COALESCE(nutrition_status, ''),
            COALESCE(parsed_quantity, ''),
            COALESCE(parsed_unit, '')
        ORDER BY occurrence_count DESC, recipe_count DESC, normalized_line
    """.format(
        done=", ".join("?" for _ in DONE_BUCKETS)
    )
    rows: list[dict[str, object]] = []
    for row in conn.execute(query, tuple(sorted(DONE_BUCKETS))):
        item = dict(row)
        required_file, fix_type, rationale = classify_fix(item)
        item["required_fix_file"] = required_file
        item["fix_type"] = fix_type
        item["fix_rationale"] = rationale
        item["status"] = "todo"
        item["owner"] = ""
        item["verified_at"] = ""
        rows.append(item)
    return rows


def build_queue(input_db: Path, output_csv: Path) -> int:
    conn = sqlite3.connect(input_db)
    conn.row_factory = sqlite3.Row
    try:
        rows = rows_from_db(conn)
    finally:
        conn.close()

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "blocker_bucket",
        "concept_key",
        "product_contract_key",
        "normalized_line",
        "example_display",
        "occurrence_count",
        "recipe_count",
        "line_failure_bucket",
        "nutrition_status",
        "parsed_quantity",
        "parsed_unit",
        "household_unit_rationale",
        "quantity_policy_rationale",
        "selected_description",
        "selected_category",
        "required_fix_file",
        "fix_type",
        "fix_rationale",
        "status",
        "owner",
        "verified_at",
    ]
    with output_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the active calculator closure queue.")
    parser.add_argument("--input-db", type=Path, default=DEFAULT_INPUT_DB)
    parser.add_argument("--output-csv", type=Path, default=DEFAULT_OUTPUT_CSV)
    args = parser.parse_args()
    count = build_queue(args.input_db, args.output_csv)
    print(f"wrote {args.output_csv} ({count} rows) at {now_utc()}")


if __name__ == "__main__":
    main()
