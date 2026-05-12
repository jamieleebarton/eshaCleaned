from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
IMPLEMENTATION_ROOT = ROOT / "implementation"
if str(IMPLEMENTATION_ROOT) not in sys.path:
    sys.path.insert(0, str(IMPLEMENTATION_ROOT))

import run_category_rewrite_pass as category_pass


class RunCategoryRewritePassTests(unittest.TestCase):
    def test_rows_for_category_filters_on_top_category(self) -> None:
        rows = [
            {
                "esha_code": "1",
                "top_categories_json": '[{"category":"Milk","count":10,"signal":"in_scope_category"}]',
            },
            {
                "esha_code": "2",
                "top_categories_json": '[{"category":"Frozen Dinners & Entrees","count":5,"signal":"in_scope_category"}]',
            },
        ]
        milk = category_pass.rows_for_category(rows, "milk")
        frozen = category_pass.rows_for_category(rows, "Frozen Dinners & Entrees")
        self.assertEqual([row["esha_code"] for row in milk], ["1"])
        self.assertEqual([row["esha_code"] for row in frozen], ["2"])

    def test_delta_kind_detects_status_changes(self) -> None:
        before = {"exactness_status": "unresolved", "recommended_attempt": "strict", "recommended_query": "", "semantic_filter_terms": ""}
        improved = {"exactness_status": "strong", "recommended_attempt": "retail", "recommended_query": "evaporated milk", "semantic_filter_terms": ""}
        changed = {"exactness_status": "strong", "recommended_attempt": "retail_v2", "recommended_query": "evaporated milk", "semantic_filter_terms": ""}
        self.assertEqual(category_pass.delta_kind(before, improved), "improved")
        self.assertEqual(category_pass.delta_kind(improved, before), "regressed")
        self.assertEqual(category_pass.delta_kind(improved, changed), "changed")

    def test_build_delta_rows_carries_before_and_after_fields(self) -> None:
        before_rows = [
            {
                "esha_code": "10",
                "description": "Milk, evaporated",
                "family": "milk",
                "exactness_status": "unresolved",
                "reason": "clean_zero_preferred",
                "recommended_attempt": "no_viable_query",
                "recommended_query": "",
                "exact_product_count": "0",
                "noise_count": "0",
                "top_categories_json": '[{"category":"Milk","count":4,"signal":"in_scope_category"}]',
            }
        ]
        after_rows = [
            {
                "esha_code": "10",
                "description": "Milk, evaporated",
                "family": "milk",
                "exactness_status": "strong",
                "reason": "rewrite_selected",
                "recommended_attempt": "retail_evaporated_milk",
                "recommended_query": "evaporated milk",
                "exact_product_count": "9",
                "noise_count": "1",
                "top_categories_json": '[{"category":"Milk","count":20,"signal":"in_scope_category"}]',
            }
        ]
        delta_rows = category_pass.build_delta_rows(before_rows, after_rows)
        self.assertEqual(len(delta_rows), 1)
        row = delta_rows[0]
        self.assertEqual(row["delta_kind"], "improved")
        self.assertEqual(row["query_after"], "evaporated milk")
        self.assertEqual(row["top_category_after"], "Milk")


if __name__ == "__main__":
    unittest.main()
