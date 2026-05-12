from __future__ import annotations

import csv
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
IMPLEMENTATION_ROOT = ROOT / "implementation"
if str(IMPLEMENTATION_ROOT) not in sys.path:
    sys.path.insert(0, str(IMPLEMENTATION_ROOT))

import build_category_workbench as workbench


class CategoryWorkbenchTests(unittest.TestCase):
    def test_category_slug_normalizes_names(self) -> None:
        self.assertEqual(workbench.category_slug("Frozen Dinners & Entrees"), "frozen_dinners_and_entrees")

    def test_category_slug_truncates_very_long_names(self) -> None:
        slug = workbench.category_slug("A " + ("very long category " * 20))
        self.assertLessEqual(len(slug), 96)
        self.assertRegex(slug, r"_[0-9a-f]{10}$")

    def test_category_index_rows_rolls_up_counts(self) -> None:
        rows = [
            {
                "esha_code": "1",
                "family": "milk",
                "exactness_status": "strong",
                "reason": "current_query_retained",
                "top_categories_json": '[{"category":"Milk","count":10,"signal":"in_scope_category"}]',
                "selected_attempt_before": "strict",
                "selected_attempt_after": "",
            },
            {
                "esha_code": "2",
                "family": "milk",
                "exactness_status": "unresolved",
                "reason": "clean_zero_preferred",
                "top_categories_json": '[{"category":"Milk","count":8,"signal":"in_scope_category"}]',
                "selected_attempt_before": "strict",
                "selected_attempt_after": "",
            },
            {
                "esha_code": "3",
                "family": "prepared_food",
                "exactness_status": "strong",
                "reason": "rewrite_selected",
                "top_categories_json": '[{"category":"Frozen Dinners & Entrees","count":5,"signal":"in_scope_category"}]',
                "selected_attempt_before": "strict",
                "selected_attempt_after": "retail_casserole",
            },
        ]
        index_rows = workbench.category_index_rows(rows)
        milk_row = next(row for row in index_rows if row["branded_food_category"] == "Milk")
        self.assertEqual(milk_row["rows"], 2)
        self.assertEqual(milk_row["strong"], 1)
        self.assertEqual(milk_row["unresolved"], 1)
        frozen_row = next(row for row in index_rows if row["branded_food_category"] == "Frozen Dinners & Entrees")
        self.assertEqual(frozen_row["auto_rewrites"], 1)

    def test_write_category_outputs_creates_expected_files(self) -> None:
        rows = [
            {
                "esha_code": "3",
                "description": "Green bean casserole",
                "family": "prepared_food",
                "selected_attempt_before": "strict",
                "selected_attempt_after": "retail_casserole",
                "recommended_attempt": "retail_casserole",
                "query_before": "",
                "query_after": "",
                "recommended_query": "green bean casserole",
                "query_terms_before": "green | bean | casserole",
                "query_terms_after": "green | bean | casserole",
                "recommended_query_terms": "green | bean | casserole",
                "category_terms_after": "frozen dinner",
                "demoted_query_terms": "",
                "translated_query_terms": "{}",
                "semantic_filter_terms": "prepared_food",
                "term_roles_json": "{}",
                "top_categories_json": '[{"category":"Frozen Dinners & Entrees","count":5,"signal":"in_scope_category"}]',
                "title_match_count": "12",
                "in_scope_category_count": "7",
                "noise_count": "1",
                "exact_product_count": "6",
                "exactness_status": "strong",
                "routing_fix_applied": "true",
                "reason": "rewrite_selected",
            },
            {
                "esha_code": "4",
                "description": "Apple drink weird",
                "family": "beverage",
                "selected_attempt_before": "strict",
                "selected_attempt_after": "",
                "recommended_attempt": "no_viable_query",
                "query_before": "",
                "query_after": "",
                "recommended_query": "",
                "query_terms_before": "apple | aspartame | water",
                "query_terms_after": "",
                "recommended_query_terms": "",
                "category_terms_after": "powdered",
                "demoted_query_terms": "aspartame | water",
                "translated_query_terms": "{}",
                "semantic_filter_terms": "aspartame | water",
                "term_roles_json": "{}",
                "top_categories_json": '[{"category":"Powdered Drinks","count":2,"signal":"review"}]',
                "title_match_count": "0",
                "in_scope_category_count": "0",
                "noise_count": "0",
                "exact_product_count": "0",
                "exactness_status": "unresolved",
                "routing_fix_applied": "false",
                "reason": "clean_zero_preferred",
            },
        ]
        with tempfile.TemporaryDirectory() as tmp_dir:
            out_dir = Path(tmp_dir) / "frozen_dinners_and_entrees"
            workbench.write_category_outputs(out_dir, "Frozen Dinners & Entrees", rows, list(rows[0].keys()))
            self.assertTrue((out_dir / "cards.csv").exists())
            self.assertTrue((out_dir / "unresolved.csv").exists())
            self.assertTrue((out_dir / "strong_rewrites.csv").exists())
            self.assertTrue((out_dir / "summary.md").exists())
            with (out_dir / "reason_counts.csv").open(newline="", encoding="utf-8") as handle:
                counts = list(csv.DictReader(handle))
            self.assertEqual(counts[0]["reason"], "rewrite_selected")
            summary = (out_dir / "summary.md").read_text(encoding="utf-8")
            self.assertIn("Frequent Query Terms In Unresolved Rows", summary)


if __name__ == "__main__":
    unittest.main()
