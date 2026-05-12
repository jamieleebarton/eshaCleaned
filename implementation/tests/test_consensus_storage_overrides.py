import importlib.util
import sys
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
V2 = REPO / "retail_mapper" / "v2"
SCRIPT = V2 / "build_consensus_storage_overrides.py"

sys.path.insert(0, str(V2))
spec = importlib.util.spec_from_file_location("build_consensus_storage_overrides", SCRIPT)
storage = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(storage)


def row(**values):
    base = {
        "fdc_id": "1",
        "title": "",
        "branded_food_category": "",
        "category_path_original": "",
        "category_path_fixed": "",
        "product_identity_fixed": "",
        "canonical_path": "",
        "retail_leaf_path": "",
        "processing_storage": "",
        "fndds_desc": "",
        "sr28_desc": "",
        "esha_desc": "",
        "matched_key": "",
        "modifier": "",
    }
    base.update(values)
    return base


class ConsensusStorageOverrideTests(unittest.TestCase):
    def test_frozen_vegetable_under_canned_shelf_moves_to_frozen_vegetables(self):
        active, review = storage.frozen_under_canned_result(
            row(
                title="BIRDS EYE Sweet Mini Corn on the Cob",
                branded_food_category="Vegetables - Prepared/Processed",
                category_path_original="Frozen > Vegetables",
                canonical_path="Pantry > Canned Vegetables > Corn on the Cob",
                retail_leaf_path="Pantry > Canned Vegetables > Corn on the Cob > Sweet Mini",
                processing_storage="frozen",
            ),
            {},
        )

        self.assertIsNone(review)
        self.assertEqual("Frozen > Vegetables", active["category_path_fixed"])
        self.assertEqual("Corn on the Cob", active["product_identity_fixed"])
        self.assertEqual("Sweet Mini", active["modifier"])
        self.assertEqual("frozen", active["processing_storage"])

    def test_freeze_dried_product_under_canned_shelf_goes_to_review(self):
        active, review = storage.frozen_under_canned_result(
            row(
                title="Freeze-Dried Sweet Corn",
                canonical_path="Pantry > Canned Vegetables > Corn",
                retail_leaf_path="Pantry > Canned Vegetables > Corn",
                processing_storage="frozen",
            ),
            {},
        )

        self.assertIsNone(active)
        self.assertEqual("freeze_dried_product_under_canned_shelf_review", review["issue_family"])

    def test_frozen_appetizer_under_canned_vegetables_routes_to_frozen_appetizers(self):
        active, review = storage.frozen_under_canned_result(
            row(
                title="P.F. Chang's Pork Dumplings, Frozen Appetizer",
                branded_food_category="Vegetables - Prepared/Processed",
                canonical_path="Pantry > Canned Vegetables > Dumplings",
                retail_leaf_path="Pantry > Canned Vegetables > Dumplings > Pork",
            ),
            {},
        )

        self.assertIsNone(review)
        self.assertEqual("Frozen > Appetizers", active["category_path_fixed"])
        self.assertEqual("Dumplings", active["product_identity_fixed"])
        self.assertEqual("Pork", active["modifier"])

    def test_reference_soup_text_does_not_block_frozen_vegetable_fix(self):
        active, review = storage.frozen_under_canned_result(
            row(
                title="Ready to Roast Sweet Potatoes, Cauliflower & Broccoli Florets",
                branded_food_category="Vegetables - Prepared/Processed",
                category_path_original="Frozen > Vegetables",
                canonical_path="Pantry > Canned Vegetables > Vegetable Blend",
                retail_leaf_path="Pantry > Canned Vegetables > Vegetable Blend > Sweet Potato Cauliflower Broccoli",
                processing_storage="frozen",
                fndds_desc="vegetable soup blend vegetables",
            ),
            {},
        )

        self.assertIsNone(review)
        self.assertEqual("Frozen > Vegetables", active["category_path_fixed"])

    def test_frozen_fruit_parent_alias_normalizes_to_single_parent(self):
        active = storage.frozen_fruit_alias_override(
            row(
                title="Frozen Sliced Peaches",
                branded_food_category="Frozen Fruit",
                canonical_path="Frozen > Frozen Peaches",
                retail_leaf_path="Frozen > Frozen Peaches > Sliced",
            ),
            {},
        )

        self.assertEqual("Frozen > Frozen Fruit", active["category_path_fixed"])
        self.assertEqual("Peaches", active["product_identity_fixed"])
        self.assertEqual("Sliced", active["modifier"])

    def test_canned_citrus_salad_outside_canned_shelf_is_approved(self):
        active, review = storage.canned_fruit_outside_result(
            row(
                title="Citrus Salad Grapefruit Orange in Light Syrup",
                branded_food_category="Canned Fruit",
                canonical_path="Meal > Salads > Fruit Salad",
                retail_leaf_path="Meal > Salads > Fruit Salad > Grapefruit Orange",
                modifier="Grapefruit Orange",
            ),
            {"ingredients_clean": "grapefruit, oranges, water, sugar, citric acid"},
        )

        self.assertIsNone(review)
        self.assertEqual("Pantry > Canned Fruit", active["category_path_fixed"])
        self.assertEqual("Citrus Salad", active["product_identity_fixed"])
        self.assertEqual("canned", active["processing_storage"])

    def test_canned_fruit_bfc_on_beverage_path_is_review_not_auto_move(self):
        active, review = storage.canned_fruit_outside_result(
            row(
                title="Banana Chia in Coconut Milk",
                branded_food_category="Canned Fruit",
                canonical_path="Beverage > Plant Milk > Coconut Milk",
                retail_leaf_path="Beverage > Plant Milk > Coconut Milk > Banana Chia",
            ),
            {"ingredients_clean": "water, coconut milk, banana puree, chia seeds"},
        )

        self.assertIsNone(active)
        self.assertEqual("canned_fruit_bfc_conflicts_with_current_department_review", review["issue_family"])

    def test_produce_with_canning_liquid_goes_to_review_only(self):
        review = storage.produce_canning_liquid_review(
            row(
                title="Mandarin Oranges in Light Syrup",
                branded_food_category="Pre-Packaged Fruit & Vegetables",
                canonical_path="Produce > Fruits > Mandarin Oranges",
                retail_leaf_path="Produce > Fruits > Mandarin Oranges",
            ),
            {"ingredients_clean": "mandarin oranges, water, sugar, citric acid"},
        )

        self.assertEqual("produce_path_likely_canned_or_shelf_stable_review", review["issue_family"])

    def test_canned_shelf_removes_stale_frozen_storage_facet(self):
        override = storage.stale_frozen_storage_on_canned_shelf(
            row(
                title="SHOPRITE, SWEET PEAS",
                branded_food_category="Canned Vegetables",
                canonical_path="Pantry > Canned Vegetables > Peas",
                retail_leaf_path="Pantry > Canned Vegetables > Peas > Sweet",
                processing_storage="canned | frozen",
            ),
            {"ingredients_clean": "peas, water, salt"},
        )

        self.assertEqual("canned_shelf_storage_facet_contains_stale_frozen", override["issue_family"])
        self.assertEqual("canned", override["processing_storage"])
        self.assertEqual("", override["category_path_fixed"])


if __name__ == "__main__":
    unittest.main()
