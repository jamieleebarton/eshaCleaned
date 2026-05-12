from __future__ import annotations

import sys
import unittest
from pathlib import Path


IMPLEMENTATION = Path(__file__).resolve().parents[1]
if str(IMPLEMENTATION) not in sys.path:
    sys.path.insert(0, str(IMPLEMENTATION))

from build_recipe_purchase_verification_packet import build_records  # noqa: E402


class RecipePurchaseVerificationPacketTests(unittest.TestCase):
    def test_build_records_includes_original_text_products_and_schema(self) -> None:
        report = {
            "recipes": [
                {
                    "recipe_num": "506745",
                    "recipe_name": "Booyah",
                    "lines": [
                        {
                            "input": "1/2 gallon beef gravy",
                            "original_item": "beef gravy",
                            "normalized_shopping_item": "Gravy, instant beef, dry",
                            "grams": 1893.0,
                            "shopping_grams": 1893.0,
                            "canonical_name": "beef gravy",
                            "shopping_canonical": "beef gravy",
                            "esha_code": "53023",
                            "esha_description": "Gravy, beef, canned",
                            "nutrition_state": "reviewed_local_label_anchor",
                            "nutrition_source": "esha_tier_a_label_median",
                            "shopping_state": "shopping_candidates_strong",
                            "walmart": {"name": "Great Value Homestyle Beef Flavored Gravy, 12 oz Glass Jar"},
                            "walmart_options": [{"name": "Great Value Homestyle Beef Flavored Gravy, 12 oz Glass Jar"}],
                            "kroger": None,
                            "kroger_options": [],
                            "accepted_examples": [{"name": "Great Value Homestyle Beef Flavored Gravy, 12 oz Glass Jar"}],
                            "rejected_examples": [{"name": "Great Value Brown Gravy Mix, 0.87 oz"}],
                            "path": ["context_surface_item:display_requires_ready_beef_gravy:'beef gravy'"],
                            "note": "accepted retail bridge",
                        }
                    ],
                }
            ]
        }

        records = build_records(report)

        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record["ingredient"]["original_recipe_text"], "1/2 gallon beef gravy")
        self.assertEqual(record["ingredient"]["normalized_shopping_item"], "Gravy, instant beef, dry")
        self.assertEqual(record["calculator"]["shopping_canonical"], "beef gravy")
        self.assertEqual(record["calculator"]["nutrition_anchor"]["code"], "53023")
        self.assertEqual(record["calculator"]["esha_code"], "53023")
        self.assertEqual(record["store_checks"][0]["status"], "selected")
        self.assertEqual(record["store_checks"][1]["status"], "missing")
        self.assertIn("expected_response_schema", record)
        self.assertIn("wrong_store_item", record["expected_response_schema"]["issue_type"])

    def test_nutrition_anchor_prefers_actual_sr28_source(self) -> None:
        report = {
            "recipes": [
                {
                    "recipe_num": "1",
                    "recipe_name": "Stock",
                    "lines": [
                        {
                            "input": "1 gallon chicken stock",
                            "original_item": "chicken stock",
                            "grams": 3785.0,
                            "shopping_grams": 3785.0,
                            "canonical_name": "chicken stock",
                            "shopping_canonical": "chicken stock",
                            "sr28_fdc_id": "172884",
                            "esha_code": "50343",
                            "esha_description": "Broth, chicken, canned",
                            "nutrition_state": "reviewed_local_label_anchor",
                            "nutrition_source": "sr28_direct",
                            "shopping_state": "shopping_candidates_strong",
                            "walmart": None,
                            "kroger": None,
                        }
                    ],
                }
            ]
        }

        record = build_records(report)[0]

        self.assertEqual(record["calculator"]["nutrition_anchor"]["source"], "SR28")
        self.assertEqual(record["calculator"]["nutrition_anchor"]["code"], "172884")


if __name__ == "__main__":
    unittest.main()
