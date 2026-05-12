from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

import build_uncategorized_workbench as uncategorized


class UncategorizedWorkbenchTests(unittest.TestCase):
    def test_bucket_key_prefers_non_state_query_terms(self) -> None:
        row = {
            "family": "milk",
            "query_terms_before": "milk | evaporated | canned | frozen",
            "semantic_filter_terms": "canned | unsalted",
        }
        family, query_terms, semantic_filters = uncategorized.bucket_key_for_row(row)
        self.assertEqual(family, "milk")
        self.assertEqual(query_terms, ("milk", "evaporated"))
        self.assertEqual(semantic_filters, ("canned", "unsalted"))

    def test_build_outputs_writes_family_and_bucket_indexes(self) -> None:
        rows = [
            {
                "esha_code": "10",
                "description": "Milk, evaporated, canned",
                "family": "milk",
                "query_terms_before": "milk | evaporated | canned",
                "semantic_filter_terms": "canned",
                "reason": "clean_zero_preferred",
                "top_categories_json": "[]",
            },
            {
                "esha_code": "48",
                "description": "Hot Cocoa, prepared from dry mix with water",
                "family": "beverage",
                "query_terms_before": "hot | cocoa | mix | water | dry",
                "semantic_filter_terms": "",
                "reason": "clean_zero_preferred",
                "top_categories_json": "[]",
            },
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = Path(tmpdir) / "uncategorized"
            uncategorized.build_outputs(rows, out_dir)
            self.assertTrue((out_dir / "family_index.csv").exists())
            self.assertTrue((out_dir / "bucket_index.csv").exists())
            self.assertTrue((out_dir / "milk" / "summary.md").exists())
            with (out_dir / "family_index.csv").open(newline="", encoding="utf-8") as handle:
                family_rows = list(csv.DictReader(handle))
            self.assertEqual([row["family"] for row in family_rows], ["beverage", "milk"])


if __name__ == "__main__":
    unittest.main()
