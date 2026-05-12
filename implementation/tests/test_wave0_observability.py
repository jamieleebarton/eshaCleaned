from __future__ import annotations

import argparse
import sys
import unittest
from pathlib import Path


IMPLEMENTATION_ROOT = Path(__file__).resolve().parents[1]
if str(IMPLEMENTATION_ROOT) not in sys.path:
    sys.path.insert(0, str(IMPLEMENTATION_ROOT))

from build_top2500_cleanup_progress import validate_coverage_rows  # noqa: E402
from build_top_ingredient_coverage_audit import validate_required_inputs  # noqa: E402
from build_wrong_product_accepted_queue import build_queue, parse_example  # noqa: E402


class Wave0ObservabilityTests(unittest.TestCase):
    def test_validate_coverage_rows_rejects_empty_audit(self) -> None:
        with self.assertRaisesRegex(ValueError, "empty coverage audit"):
            validate_coverage_rows([], Path("/tmp/fake_top2500_coverage.csv"))

    def test_validate_required_inputs_rejects_missing_upstreams(self) -> None:
        args = argparse.Namespace(
            bridge_csv=Path("/tmp/missing_bridge.csv"),
            bridge_summary_json=Path("/tmp/missing_bridge_summary.json"),
            line_summary_json=Path("/tmp/missing_line_summary.json"),
            canonical_csv=Path("/tmp/missing_canonical.csv"),
            process_eval_csv=Path("/tmp/missing_process.csv"),
            wrongness_csv=Path("/tmp/missing_wrongness.csv"),
            cleanup_queue_csv=Path("/tmp/missing_cleanup.csv"),
            ingredient_card_csv=Path("/tmp/missing_cards.csv"),
        )
        with self.assertRaisesRegex(FileNotFoundError, "missing 8 input"):
            validate_required_inputs(args)

    def test_parse_example_extracts_bad_product(self) -> None:
        parsed = parse_example("523: cream cheese frosting||cheese| -> CREAM CHEESE FROSTING")
        self.assertEqual(parsed["example_occurrence_count"], "523")
        self.assertEqual(parsed["normalized_item"], "cream cheese frosting")
        self.assertEqual(parsed["qualifier"], "cheese")
        self.assertEqual(parsed["observed_bad_product"], "CREAM CHEESE FROSTING")

    def test_build_queue_emits_wrong_product_and_contract_audit_rows(self) -> None:
        rows = [
            {
                "work_id": "product_contract_failed_candidates",
                "status": "todo",
                "priority": "P0",
                "risk_level": "high",
                "row_count": "137",
                "occurrence_count": "25672",
                "examples": "5414: blueberry|||fresh -> BLUEBERRIES | 520: butter flavor crisco||butter| -> SHORTENING",
                "source_artifact": "/tmp/audit.csv",
                "notes": "These are proven cart mistakes, not missing coverage.",
            },
            {
                "work_id": "product_covered_needs_contract_audit",
                "status": "todo",
                "priority": "P0",
                "risk_level": "high",
                "row_count": "802",
                "occurrence_count": "51431",
                "examples": "599: soup||| | 590: stock|||",
                "source_artifact": "/tmp/audit.csv",
                "notes": "Covered product reachability is not product safety until contracts are audited.",
            },
        ]
        queue = build_queue(rows)
        self.assertEqual(len(queue), 4)
        self.assertEqual(queue[0]["source_work_id"], "product_contract_failed_candidates")
        self.assertEqual(queue[0]["queue_class"], "wrong_product_accepted")
        self.assertEqual(queue[0]["normalized_item"], "blueberry")
        self.assertEqual(queue[0]["observed_bad_product"], "BLUEBERRIES")

        audit_rows = [row for row in queue if row["source_work_id"] == "product_covered_needs_contract_audit"]
        self.assertEqual(len(audit_rows), 2)
        self.assertTrue(all(row["queue_class"] == "covered_product_contract_needs_audit" for row in audit_rows))


if __name__ == "__main__":
    unittest.main()
