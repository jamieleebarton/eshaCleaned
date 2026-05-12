from __future__ import annotations

import unittest

import run_uncategorized_family_pass as uncategorized_run


class RunUncategorizedFamilyPassTests(unittest.TestCase):
    def test_rows_for_uncategorized_family_filters_only_uncategorized_family(self) -> None:
        rows = [
            {"esha_code": "1", "family": "beverage", "top_categories_json": "[]"},
            {"esha_code": "2", "family": "prepared_food", "top_categories_json": "[]"},
            {"esha_code": "3", "family": "beverage", "top_categories_json": '[{"category":"Coffee","count":4}]'},
        ]
        selected = uncategorized_run.rows_for_uncategorized_family(rows, "beverage")
        self.assertEqual([row["esha_code"] for row in selected], ["1"])


if __name__ == "__main__":
    unittest.main()
