from __future__ import annotations

import csv
import sqlite3
import sys
import unittest
from pathlib import Path


IMPLEMENTATION_ROOT = Path(__file__).resolve().parents[1]
if str(IMPLEMENTATION_ROOT) not in sys.path:
    sys.path.insert(0, str(IMPLEMENTATION_ROOT))

from build_normalized_item_bridge import NormalizedItemBridgeResolver, build_bridge  # noqa: E402
from resolver_context import DEFAULT_ARTIFACTS  # noqa: E402


class Namespace:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class NormalizedItemBridgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.resolver = NormalizedItemBridgeResolver(
            DEFAULT_ARTIFACTS.dictionary_csv,
            DEFAULT_ARTIFACTS.supplemental_concepts_csv,
            DEFAULT_ARTIFACTS.approved_normalization_rules_csv,
            DEFAULT_ARTIFACTS.product_contract_audit_csv,
        )

    def resolve(self, item: str) -> dict[str, str]:
        return self.resolver.resolve(item, 1)

    def test_bridge_file_has_one_row_per_9k_item(self) -> None:
        args = Namespace(
            input_csv=DEFAULT_ARTIFACTS.recipeqa_item_review_ge10_csv,
            dictionary_csv=DEFAULT_ARTIFACTS.dictionary_csv,
            supplemental_csv=DEFAULT_ARTIFACTS.supplemental_concepts_csv,
            approved_rules_csv=DEFAULT_ARTIFACTS.approved_normalization_rules_csv,
            product_audit_csv=DEFAULT_ARTIFACTS.product_contract_audit_csv,
            output_csv=DEFAULT_ARTIFACTS.normalized_item_bridge_csv,
            output_db=DEFAULT_ARTIFACTS.normalized_item_bridge_db,
            summary_json=DEFAULT_ARTIFACTS.normalized_item_bridge_summary_json,
        )
        summary = build_bridge(args)
        with DEFAULT_ARTIFACTS.recipeqa_item_review_ge10_csv.open(newline="", encoding="utf-8") as handle:
            input_count = sum(1 for _ in csv.DictReader(handle))
        self.assertEqual(input_count, summary["rows"])
        self.assertEqual(9735, summary["rows"])

        conn = sqlite3.connect(DEFAULT_ARTIFACTS.normalized_item_bridge_db)
        try:
            total, distinct_items, bad_ready = conn.execute(
                """
                SELECT
                    COUNT(*),
                    COUNT(DISTINCT normalized_item),
                    SUM(CASE WHEN bridge_status = 'concept_ready'
                              AND (canonical_concept_key = '' OR canonical_concept_key = '|||')
                             THEN 1 ELSE 0 END)
                FROM normalized_item_bridge
                """
            ).fetchone()
        finally:
            conn.close()
        self.assertEqual(total, distinct_items)
        self.assertEqual(0, bad_ready)

    def test_core_foods_resolve_to_expected_concepts(self) -> None:
        expected = {
            "butter": "butter|||",
            "unsalted butter": "unsalted butter|||",
            "ground cinnamon": "cinnamon|||",
            "boneless skinless chicken breasts": "chicken breast|||",
            "cooked chicken": "chicken|||cooked",
            "cooked chicken breast": "chicken breast|||cooked",
            "cream cheese": "cream cheese|||",
            "peanut butter": "peanut butter|||",
            "milk chocolate chips": "milk chocolate chip|||",
            "green beans": "green bean|||",
        }
        for item, concept_key in expected.items():
            with self.subTest(item=item):
                row = self.resolve(item)
                self.assertEqual("concept_ready", row["bridge_status"])
                self.assertEqual(concept_key, row["canonical_concept_key"])

    def test_line_like_surfaces_resolve_through_rules_without_polluting_the_bridge(self) -> None:
        expected = {
            "orange juice, chilled": "orange juice|||",
            "orange juice, freshly squeezed": "orange juice|||fresh",
        }
        for item, concept_key in expected.items():
            with self.subTest(item=item):
                row = self.resolve(item)
                self.assertEqual("concept_ready", row["bridge_status"])
                self.assertEqual(concept_key, row["canonical_concept_key"])

    def test_compound_nouns_do_not_collapse_to_head_noun(self) -> None:
        forbidden = {
            "cream cheese": "cheese|||",
            "peanut butter": "butter|||",
            "milk chocolate chips": "milk|||",
            "green bean casserole": "green bean|||",
        }
        for item, bad_key in forbidden.items():
            with self.subTest(item=item):
                row = self.resolve(item)
                self.assertNotEqual(bad_key, row["canonical_concept_key"])

    def test_optional_or_regexes_do_not_turn_single_foods_into_alternatives(self) -> None:
        expected = {
            "olive oil": "olive oil|||",
            "lemon juice": "lemon juice|||",
            "dijon mustard": "dijon mustard|||",
        }
        for item, concept_key in expected.items():
            with self.subTest(item=item):
                row = self.resolve(item)
                self.assertEqual("concept_ready", row["bridge_status"])
                self.assertEqual(concept_key, row["canonical_concept_key"])

    def test_true_or_surfaces_remain_alternatives(self) -> None:
        row = self.resolve("olive oil or canola oil")
        self.assertEqual("true_alternative_options", row["bridge_status"])
        self.assertIn("olive oil|||", row["canonical_concept_key"])
        self.assertIn("canola oil|||", row["canonical_concept_key"])

    def test_reviewed_external_catalog_covers_missing_product_card_rows(self) -> None:
        row = self.resolve("miracle whip")
        self.assertEqual("concept_ready", row["bridge_status"])
        self.assertEqual("miracle whip|||", row["canonical_concept_key"])
        self.assertEqual("external_catalog_covered", row["product_contract_status"])


if __name__ == "__main__":
    unittest.main()
