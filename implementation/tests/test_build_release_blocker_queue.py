import csv
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
IMPLEMENTATION_ROOT = ROOT / "implementation"
if str(IMPLEMENTATION_ROOT) not in sys.path:
    sys.path.insert(0, str(IMPLEMENTATION_ROOT))

from build_release_blocker_queue import blocker_reason, brokenness, load_progress_rows  # noqa: E402


class ReleaseBlockerQueueTest(unittest.TestCase):
    def test_load_progress_rows_rejects_empty_source(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "progress.csv"
            path.write_text("rank,normalized_item,check_status\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "empty cleanup progress file"):
                load_progress_rows(path)

    def test_brokenness_prefers_contract_failures(self):
        row = {
            "product_contract_status": "contract_failed",
            "issue_class": "ok",
            "check_status": "done",
        }
        self.assertEqual(brokenness(row), 4)

    def test_blocker_reason_surfaces_nonterminal_status(self):
        row = {
            "product_contract_status": "contract_missing",
            "issue_class": "broad_query_warning",
            "check_status": "todo",
        }
        reason = blocker_reason(row)
        self.assertIn("contract=contract_missing", reason)
        self.assertIn("issue=broad_query_warning", reason)
        self.assertIn("status=todo", reason)


if __name__ == "__main__":
    unittest.main()
