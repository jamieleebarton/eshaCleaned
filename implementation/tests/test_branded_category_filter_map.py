from __future__ import annotations

import importlib
import sqlite3
import sys
import unittest
from pathlib import Path


IMPLEMENTATION_ROOT = Path(__file__).resolve().parents[1]
if str(IMPLEMENTATION_ROOT) not in sys.path:
    sys.path.insert(0, str(IMPLEMENTATION_ROOT))

from build_branded_category_filter_map import (  # noqa: E402
    build_rows,
    infer_mapping,
    main as rebuild_category_filter_map,
    validate_critical_rows,
)


class BrandedCategoryFilterMapTests(unittest.TestCase):
    def test_critical_category_gates_are_stable(self) -> None:
        self.assertEqual("allow", infer_mapping("Canned Vegetables").simple_ingredient_gate)
        self.assertEqual("allow", infer_mapping("Frozen Vegetables").simple_ingredient_gate)
        self.assertEqual("allow", infer_mapping("Pre-Packaged Fruit & Vegetables").simple_ingredient_gate)
        self.assertEqual("block", infer_mapping("Frozen Dinners & Entrees").simple_ingredient_gate)
        self.assertEqual("block", infer_mapping("Vegetable Based Products / Meals").simple_ingredient_gate)
        self.assertEqual("concept_specific", infer_mapping("Herbs & Spices").simple_ingredient_gate)
        self.assertEqual(
            "concept_specific",
            infer_mapping("Seasoning Mixes, Salts, Marinades & Tenderizers").simple_ingredient_gate,
        )

    def test_vendor_taxonomy_text_is_review_not_simple_ingredient(self) -> None:
        row = infer_mapping("Includes shelf-stable vegetables, green beans, and vegetable side dishes")
        self.assertEqual("review", row.simple_ingredient_gate)
        self.assertEqual("vendor_taxonomy_text", row.category_family)

    def test_generated_rows_pass_critical_validation(self) -> None:
        validate_critical_rows(build_rows())

    def test_product_search_uses_safe_same_family_fallback_categories(self) -> None:
        rebuild_category_filter_map()
        product_cards = importlib.import_module("build_product_card_coverage_85")
        product_cards = importlib.reload(product_cards)

        card = product_cards.ProductCard(
            route="product",
            query="green beans",
            allowed_categories=("Vegetables",),
            required_all=("green", "beans"),
            forbidden_any=("almondine", "casserole", "meal", "dinner"),
            source="test",
        )
        fallback_categories = set(product_cards.fallback_categories_for_card(card))
        self.assertIn("Canned Vegetables", fallback_categories)
        self.assertIn("Frozen Vegetables", fallback_categories)
        self.assertNotIn("Frozen Dinners & Entrees", fallback_categories)
        self.assertNotIn("Vegetable Based Products / Meals", fallback_categories)

        conn = sqlite3.connect(product_cards.PRODUCT_DB)
        conn.row_factory = sqlite3.Row
        try:
            selected, accepted, rejected, searched_count = product_cards.choose_product(conn, card)
        finally:
            conn.close()

        self.assertGreater(searched_count, 0)
        self.assertIsNotNone(selected)
        self.assertGreater(len(accepted), 0)
        accepted_categories = {candidate.category for candidate in accepted}
        self.assertLessEqual(accepted_categories, fallback_categories | {"Vegetables"})
        self.assertTrue(all(candidate.reject_reason is None for candidate in accepted))
        self.assertTrue(
            all(candidate.category not in {"Frozen Dinners & Entrees", "Vegetable Based Products / Meals", "Candy"} for candidate in accepted)
        )
        self.assertTrue(all(candidate.category != "Frozen Dinners & Entrees" for candidate in rejected))


if __name__ == "__main__":
    unittest.main()
