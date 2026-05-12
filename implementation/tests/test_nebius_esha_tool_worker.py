from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
IMPLEMENTATION_ROOT = ROOT / "implementation"
if str(IMPLEMENTATION_ROOT) not in sys.path:
    sys.path.insert(0, str(IMPLEMENTATION_ROOT))

import nebius_esha_tool_worker as worker


class NebiusEshaToolWorkerTests(unittest.TestCase):
    def test_packet_needs_tool_followup_for_thin_noisy_packet(self) -> None:
        packet = {
            "esha_code": 49691,
            "assigned_product_codes": {"rows": []},
            "contract_sources": {"match_count": 0},
            "cross_reference_rows": [],
            "card": {
                "index_row": {
                    "total_product_matches": "81",
                    "top_category_count": "57",
                }
            },
        }
        self.assertTrue(worker.packet_needs_tool_followup(packet))

    def test_packet_does_not_need_tool_followup_for_reviewed_packet(self) -> None:
        packet = {
            "esha_code": 1,
            "assigned_product_codes": {"rows": [{"gtin_upc": "0001"}]},
            "contract_sources": {"match_count": 2},
            "cross_reference_rows": [{"source_esha_code": "1", "destination_esha_code": "2"}],
            "card": {
                "index_row": {
                    "total_product_matches": "8",
                    "top_category_count": "3",
                }
            },
        }
        self.assertFalse(worker.packet_needs_tool_followup(packet))

    def test_build_tool_followup_message_names_required_tools(self) -> None:
        packet = {"esha_code": 49691, "esha_description": "Topping, dessert, apple pie filling"}
        message = worker.build_tool_followup_message(packet)
        self.assertIn("matrix_slice", message)
        self.assertIn("product_codes", message)
        self.assertIn("get_card", message)
        self.assertIn("list_cards", message)

    def test_validate_better_destination_references_flags_mismatch(self) -> None:
        final = {
            "reject_products": [
                {
                    "gtin_upc": "891123002459",
                    "better_destination": "ESHA 49692 (Apple Pie, complete)",
                }
            ]
        }
        validation = worker.validate_better_destination_references(
            final,
            descriptions={"49692": "Topping, dessert, bananas"},
        )
        self.assertFalse(validation["ok"])
        self.assertEqual(validation["failures"][0]["error"], "destination_label_mismatch:49692")

    def test_validate_better_destination_references_accepts_matching_label(self) -> None:
        final = {
            "reject_products": [
                {
                    "gtin_upc": "891123002459",
                    "better_destination": "ESHA 22937 (Mayonnaise, chipotle)",
                }
            ]
        }
        validation = worker.validate_better_destination_references(
            final,
            descriptions={"22937": "Mayonnaise, chipotle"},
        )
        self.assertTrue(validation["ok"])
        self.assertEqual(validation["failures"], [])

    def test_repair_feedback_triggers_on_structured_validation_failure(self) -> None:
        final = {"structured_patch_builder": {"status": "semantic_validation_failed"}}
        feedback = worker.repair_feedback(final, {"status": "no_patch"})
        self.assertEqual(feedback["source"], "structured_patch_builder")

    def test_repair_feedback_triggers_on_destination_validation_failure(self) -> None:
        final = {"destination_validation": {"ok": False, "failures": [{"error": "destination_label_mismatch:49692"}]}}
        feedback = worker.repair_feedback(final, {"status": "no_patch"})
        self.assertEqual(feedback["source"], "destination_validation")

    def test_parser_accepts_verifier_model(self) -> None:
        parser = worker.build_parser()
        args = parser.parse_args(["--esha-code", "49691", "--verifier-model", "Qwen/Qwen3-32B"])
        self.assertEqual(args.verifier_model, "Qwen/Qwen3-32B")


if __name__ == "__main__":
    unittest.main()
