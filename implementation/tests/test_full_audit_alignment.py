from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path


IMPLEMENTATION_ROOT = Path(__file__).resolve().parents[1]
if str(IMPLEMENTATION_ROOT) not in sys.path:
    sys.path.insert(0, str(IMPLEMENTATION_ROOT))

from audit_full_recipe_calculation import evaluate_line  # noqa: E402


def mapped_row(
    *,
    line: str,
    base: str,
    status: str = "surface_alias_match",
    action: str = "dictionary_match",
    parsed_quantity: str = "",
    parsed_unit: str = "",
    components: str = "",
) -> dict[str, str]:
    return {
        "normalized_line": line,
        "recipe_count": "1",
        "example_raw_line": line,
        "parsed_quantity": parsed_quantity,
        "parsed_unit": parsed_unit,
        "cleaned_surface": base,
        "concept_base_food": base,
        "concept_variant": "",
        "concept_form": "",
        "concept_state": "",
        "dictionary_match_status": status,
        "resolution_action": action,
        "approved_rule_components": components,
    }


class FullAuditAlignmentTests(unittest.TestCase):
    def test_external_catalog_counts_as_calculation_candidate_with_quantity(self) -> None:
        row = mapped_row(
            line="1/2 cup dry white wine",
            base="white wine",
            status="approved_alias_match",
            action="approved_alias",
            parsed_quantity="1/2",
            parsed_unit="cup",
        )
        product_statuses = {
            "white wine|||": {
                "audit_status": "not_candidate_covered",
                "policy": "",
            }
        }

        result = evaluate_line(row, product_statuses, {"white wine|||"}, set(), {})

        self.assertEqual("external_catalog_covered", result["product_audit_status"])
        self.assertEqual("calculation_candidate", result["failure_bucket"])

    def test_to_taste_defaults_are_not_full_audit_blockers(self) -> None:
        row = mapped_row(line="salt, to taste", base="salt")
        product_statuses = {
            "salt|||": {
                "audit_status": "contract_passed",
                "policy": "buy_exact",
            }
        }

        result = evaluate_line(row, product_statuses, set(), {"salt|||"}, {})

        self.assertEqual("quantity_default_applied", result["quantity_bucket"])
        self.assertEqual("calculation_candidate", result["failure_bucket"])

    def test_reviewed_quantity_policy_counts_as_calculation_candidate(self) -> None:
        row = mapped_row(line="salt", base="salt")
        product_statuses = {
            "salt|||": {
                "audit_status": "contract_passed",
                "policy": "buy_exact",
            }
        }
        quantity_policies = {
            ("salt|||", "grams_missing_or_zero"): [
                {"include": re.compile("."), "exclude": None},
            ]
        }

        result = evaluate_line(row, product_statuses, set(), set(), quantity_policies)

        self.assertEqual("quantity_default_applied", result["quantity_bucket"])
        self.assertEqual("calculation_candidate", result["failure_bucket"])

    def test_split_to_taste_defaults_use_component_keys(self) -> None:
        row = mapped_row(
            line="salt and pepper to taste",
            base="",
            status="approved_split_match",
            action="approved_split",
            components="salt|||;black pepper|||",
        )
        product_statuses = {
            "salt|||": {
                "audit_status": "contract_passed",
                "policy": "buy_exact",
            },
            "black pepper|||": {
                "audit_status": "contract_passed",
                "policy": "buy_exact",
            },
        }

        result = evaluate_line(
            row,
            product_statuses,
            set(),
            {"salt|||", "black pepper|||"},
            {},
        )

        self.assertEqual("contract_passed", result["product_audit_status"])
        self.assertEqual("quantity_default_applied", result["quantity_bucket"])
        self.assertEqual("calculation_candidate", result["failure_bucket"])


if __name__ == "__main__":
    unittest.main()
