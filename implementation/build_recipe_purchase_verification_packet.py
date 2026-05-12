#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "implementation" / "output"
DEFAULT_REPORT_JSON = OUT_DIR / "one_recipe_506745_purchase_report.json"
DEFAULT_OUT_JSONL = OUT_DIR / "one_recipe_506745_llm_verification_packet.jsonl"


VERIFICATION_TASK = [
    "Compare the original recipe text to the calculator target.",
    "Check whether the nutrition anchor matches the requested food and form.",
    "Check whether each selected store item is a reasonable customer purchase for that original ingredient.",
    "Reject dry mixes, seasoning, prepared meals, soups, deli forms, wrong species, and wrong package forms unless the original recipe explicitly asks for them.",
    "Check whether recipe grams and retail grams make sense, especially cooked-to-dry conversions and count/package parsing.",
]

EXPECTED_RESPONSE_SCHEMA = {
    "decision": "accept | reject | needs_review",
    "issue_type": "ok | wrong_target | wrong_nutrition | wrong_store_item | wrong_form | shopping_gap | bad_grams | bad_package_math",
    "confidence": "0.0-1.0",
    "reason": "short explanation grounded in the provided fields",
    "fix": "specific repair if rejected or needs_review",
}


def _nutrition_anchor(line: dict[str, Any]) -> dict[str, str]:
    if line.get("nutrition_source") == "sr28_direct" and line.get("sr28_fdc_id"):
        return {
            "source": "SR28",
            "code": str(line.get("sr28_fdc_id") or ""),
            "description": "",
        }
    if line.get("nutrition_source") == "fndds_direct" and line.get("fndds_code"):
        return {
            "source": "FNDDS",
            "code": str(line.get("fndds_code") or ""),
            "description": "",
        }
    if line.get("esha_code"):
        return {
            "source": "ESHA",
            "code": str(line.get("esha_code") or ""),
            "description": str(line.get("esha_description") or ""),
        }
    if line.get("sr28_fdc_id"):
        return {
            "source": "SR28",
            "code": str(line.get("sr28_fdc_id") or ""),
            "description": "",
        }
    if line.get("fndds_code"):
        return {
            "source": "FNDDS",
            "code": str(line.get("fndds_code") or ""),
            "description": "",
        }
    return {"source": "", "code": "", "description": ""}


def _offer(line: dict[str, Any], store: str) -> dict[str, Any]:
    selected = line.get(store)
    return {
        "store": store,
        "selected": selected,
        "top_options": line.get(f"{store}_options") or [],
        "status": "selected" if selected else "missing",
    }


def build_records(report: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for recipe in report.get("recipes", []):
        recipe_num = str(recipe.get("recipe_num") or "")
        recipe_name = str(recipe.get("recipe_name") or "")
        for line_index, line in enumerate(recipe.get("lines", []), start=1):
            records.append(
                {
                    "record_id": f"{recipe_num}:{line_index}",
                    "recipe": {
                        "recipe_num": recipe_num,
                        "recipe_name": recipe_name,
                        "line_index": line_index,
                    },
                    "ingredient": {
                        "original_recipe_text": line.get("input") or "",
                        "parsed_item": line.get("original_item") or "",
                        "normalized_shopping_item": line.get("normalized_shopping_item") or "",
                        "recipe_grams": line.get("grams"),
                        "retail_purchase_grams": line.get("shopping_grams", line.get("grams")),
                        "quantity_note": line.get("note") or "",
                    },
                    "calculator": {
                        "canonical_name": line.get("canonical_name") or "",
                        "shopping_canonical": line.get("shopping_canonical") or "",
                        "nutrition_state": line.get("nutrition_state") or "",
                        "nutrition_source": line.get("nutrition_source") or "",
                        "nutrition_anchor": _nutrition_anchor(line),
                        "esha_code": line.get("esha_code") or "",
                        "esha_description": line.get("esha_description") or "",
                        "sr28_fdc_id": line.get("sr28_fdc_id") or "",
                        "fndds_code": line.get("fndds_code") or "",
                        "shopping_state": line.get("shopping_state") or "",
                        "path": line.get("path") or [],
                    },
                    "store_checks": [
                        _offer(line, "walmart"),
                        _offer(line, "kroger"),
                    ],
                    "accepted_examples": line.get("accepted_examples") or [],
                    "rejected_examples": line.get("rejected_examples") or [],
                    "verification_task": VERIFICATION_TASK,
                    "expected_response_schema": EXPECTED_RESPONSE_SCHEMA,
                }
            )
    return records


def write_jsonl(records: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build LLM-ready purchase verification records from a recipe cost report.")
    parser.add_argument("--report-json", type=Path, default=DEFAULT_REPORT_JSON)
    parser.add_argument("--out-jsonl", type=Path, default=DEFAULT_OUT_JSONL)
    args = parser.parse_args()

    report = json.loads(args.report_json.read_text(encoding="utf-8"))
    records = build_records(report)
    write_jsonl(records, args.out_jsonl)
    print(json.dumps({"records": len(records), "out_jsonl": str(args.out_jsonl)}, indent=2))


if __name__ == "__main__":
    main()
