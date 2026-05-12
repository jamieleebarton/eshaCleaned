from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


IMPLEMENTATION_ROOT = Path(__file__).resolve().parents[1]
if str(IMPLEMENTATION_ROOT) not in sys.path:
    sys.path.insert(0, str(IMPLEMENTATION_ROOT))

from build_top2500_cleanup_progress import build_progress, write_summary  # noqa: E402


class Top2500CleanupProgressTests(unittest.TestCase):
    def test_preserves_named_custom_statuses(self) -> None:
        coverage_rows = [
            {
                "rank": "1",
                "normalized_item": "veal cutlet",
                "occurrence_count": "500",
                "issue_priority": "P2",
                "check_status": "",
                "issue_class": "md_card_or_query_gap",
                "esha_code": "11582",
                "esha_description": "Veal cutlet",
                "selected_canonical_surface": "veal cutlet",
                "product_contract_status": "external_catalog_covered",
                "pack_path": "/tmp/veal.md",
                "recommended_action": "fix card",
            }
        ]
        existing_rows = [
            {
                "rank": "1",
                "normalized_item": "veal cutlet",
                "occurrence_count": "500",
                "issue_priority": "P2",
                "check_status": "c2e_tiebreak_applied",
                "issue_class": "md_card_or_query_gap",
                "esha_code": "11582",
                "esha_description": "Veal cutlet",
                "selected_canonical_surface": "veal cutlet",
                "product_contract_status": "external_catalog_covered",
                "pack_path": "/tmp/veal.md",
                "recommended_action": "fix card",
            }
        ]
        rows = build_progress(coverage_rows, existing_rows=existing_rows)
        self.assertEqual(rows[0]["check_status"], "c2e_tiebreak_applied")

    def test_regression_overrides_terminal_status(self) -> None:
        coverage_rows = [
            {
                "rank": "2",
                "normalized_item": "milk",
                "occurrence_count": "1000",
                "issue_priority": "P1",
                "check_status": "",
                "issue_class": "esha_assignment_suspicious",
                "esha_code": "1",
                "esha_description": "Milk",
                "selected_canonical_surface": "milk",
                "product_contract_status": "contract_passed",
                "pack_path": "/tmp/milk.md",
                "recommended_action": "review",
            }
        ]
        existing_rows = [
            {
                "rank": "2",
                "normalized_item": "milk",
                "occurrence_count": "1000",
                "issue_priority": "OK",
                "check_status": "done",
                "issue_class": "ok",
                "esha_code": "1",
                "esha_description": "Milk",
                "selected_canonical_surface": "milk",
                "product_contract_status": "contract_passed",
                "pack_path": "/tmp/milk.md",
                "recommended_action": "review",
            }
        ]
        rows = build_progress(coverage_rows, existing_rows=existing_rows)
        self.assertEqual(rows[0]["check_status"], "todo")

    def test_summary_counts_unresolved_named_statuses_by_priority(self) -> None:
        rows = [
            {
                "rank": "1",
                "normalized_item": "veal cutlet",
                "occurrence_count": "500",
                "issue_priority": "P2",
                "check_status": "c2e_tiebreak_applied",
                "issue_class": "md_card_or_query_gap",
                "esha_code": "11582",
                "esha_description": "Veal cutlet",
                "selected_canonical_surface": "veal cutlet",
                "product_contract_status": "external_catalog_covered",
                "pack_path": "/tmp/veal.md",
                "recommended_action": "fix card",
            },
            {
                "rank": "2",
                "normalized_item": "salt",
                "occurrence_count": "250",
                "issue_priority": "P3",
                "check_status": "reviewed_terminal",
                "issue_class": "md_card_broad_query_warning",
                "esha_code": "34714",
                "esha_description": "Salt",
                "selected_canonical_surface": "salt",
                "product_contract_status": "contract_passed",
                "pack_path": "/tmp/salt.md",
                "recommended_action": "spot check",
            },
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            out_md = Path(temp_dir) / "summary.md"
            write_summary(rows, out_md)
            text = out_md.read_text(encoding="utf-8")
            self.assertIn("| c2e_tiebreak_applied | 1 | 500 |", text)
            self.assertIn("| 1 | md_card_or_query_gap |", text)


if __name__ == "__main__":
    unittest.main()
