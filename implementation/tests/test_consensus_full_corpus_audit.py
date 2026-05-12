import importlib.util
import sys
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
V2 = REPO / "retail_mapper" / "v2"
SCRIPT = V2 / "build_consensus_full_corpus_audit.py"

sys.path.insert(0, str(V2))
spec = importlib.util.spec_from_file_location("build_consensus_full_corpus_audit", SCRIPT)
consensus = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(consensus)


class ConsensusFullCorpusAuditTests(unittest.TestCase):
    def test_restores_pantry_parent_only_for_pantry_flat_paths(self):
        full = {
            "canonical_path": "Pantry > Sauce",
            "retail_leaf_path": "Pantry > Sauce > Tomato",
            "branded_food_category": "Prepared Pasta & Pizza Sauces",
            "title": "TOMATO SAUCE",
        }
        codex = {
            "canonical_path": "Pantry > Sauces & Salsas > Sauce",
            "retail_leaf_path": "Pantry > Sauces & Salsas > Sauce > Tomato",
        }
        self.assertEqual(
            "take_codex:restore_sauces_salsas_parent",
            consensus.codex_side_reason(full, codex),
        )

        full["canonical_path"] = "Dairy > Cheese"
        self.assertEqual("", consensus.codex_side_reason(full, codex))

    def test_keeps_full_storage_and_source_category_wins(self):
        self.assertEqual(
            "keep_full:frozen_vegetables_storage_department",
            consensus.full_side_reason(
                {
                    "branded_food_category": "Frozen Vegetables",
                    "canonical_path": "Frozen > Vegetables > Green Beans",
                    "retail_leaf_path": "Frozen > Vegetables > Green Beans > Plain",
                },
                {"canonical_path": "Produce > Vegetables > Green Beans"},
            ),
        )
        self.assertEqual(
            "keep_full:nut_seed_butters_not_dairy_butter",
            consensus.full_side_reason(
                {
                    "branded_food_category": "Nut & Seed Butters",
                    "canonical_path": "Pantry > Nut Butters > Peanut Butter",
                    "retail_leaf_path": "Pantry > Nut Butters > Peanut Butter > Plain",
                },
                {"canonical_path": "Dairy > Butter > Peanut Butter"},
            ),
        )
        self.assertEqual(
            "keep_full:canned_vegetables_stay_pantry",
            consensus.full_side_reason(
                {
                    "branded_food_category": "Canned Vegetables",
                    "canonical_path": "Pantry > Canned Vegetables > Peas",
                    "retail_leaf_path": "Pantry > Canned Vegetables > Peas > Plain",
                },
                {"canonical_path": "Produce > Vegetables > Peas"},
            ),
        )

    def test_codex_salad_and_real_churro_wins(self):
        self.assertEqual(
            "take_codex:title_level_salad_over_dirty_pickle_bfc",
            consensus.codex_side_reason(
                {
                    "branded_food_category": "Pickles, Olives, Peppers & Relishes",
                    "title": "FRESH CHICKEN CAESAR SALAD",
                    "canonical_path": "Pantry > Pickles > Salad",
                    "retail_leaf_path": "Pantry > Pickles > Salad > Chicken Caesar",
                },
                {
                    "canonical_path": "Meal > Salads",
                    "retail_leaf_path": "Meal > Salads > Chicken Caesar",
                },
            ),
        )
        self.assertEqual(
            "take_codex:actual_churro_product_not_cookie",
            consensus.codex_side_reason(
                {
                    "branded_food_category": "Cookies & Biscuits",
                    "title": "MINI CHURROS",
                    "canonical_path": "Bakery > Cookies > Churros",
                    "retail_leaf_path": "Bakery > Cookies > Churros > Mini",
                },
                {
                    "canonical_path": "Bakery > Pastry > Churros",
                    "retail_leaf_path": "Bakery > Pastry > Churros > Mini",
                },
            ),
        )

    def test_true_cookies_stay_bakery(self):
        self.assertEqual(
            "keep_full:true_cookies_stay_bakery",
            consensus.full_side_reason(
                {
                    "branded_food_category": "Cookies & Biscuits",
                    "canonical_path": "Bakery > Cookies",
                    "retail_leaf_path": "Bakery > Cookies > Sandwich Chocolate",
                },
                {
                    "canonical_path": "Snack > Cookies",
                    "retail_leaf_path": "Snack > Cookies > Sandwich Chocolate",
                },
            ),
        )

    def test_consensus_normalization_repairs_residual_source_leaks(self):
        row = {
            "branded_food_category": "Canned Vegetables",
            "category_path_fixed": "Produce > Vegetables",
            "canonical_path": "Produce > Vegetables > Peas",
            "product_identity_fixed": "Peas",
            "modifier": "Sweet",
            "retail_leaf_path": "Produce > Vegetables > Peas > Sweet",
        }
        self.assertEqual(
            "consensus_normalize:canned_vegetables_to_pantry",
            consensus.consensus_normalization_reason(row),
        )
        self.assertEqual("Pantry > Canned Vegetables > Peas > Sweet", row["retail_leaf_path"])
        self.assertEqual("Pantry > Canned Vegetables > Peas", row["canonical_path"])

        row = {
            "branded_food_category": "Frozen Vegetables",
            "category_path_fixed": "Pantry > Canned Vegetables",
            "canonical_path": "Pantry > Canned Vegetables > Green Beans",
            "product_identity_fixed": "Green Beans",
            "modifier": "Plain",
            "retail_leaf_path": "Pantry > Canned Vegetables > Green Beans > Plain",
        }
        self.assertEqual(
            "consensus_normalize:frozen_vegetables_to_frozen",
            consensus.consensus_normalization_reason(row),
        )
        self.assertEqual("Frozen > Vegetables > Green Beans > Plain", row["retail_leaf_path"])

    def test_repair_path_shape_aligns_stale_category_fields(self):
        row = {
            "category_path_fixed": "Pantry > Cookie Mix",
            "canonical_path": "Pantry > Baking Mixes > Cookie Mix",
            "product_identity_fixed": "Cookie Mix",
            "modifier": "Chocolate",
            "retail_leaf_path": "Pantry > Baking Mixes > Cookie Mix > Chocolate",
        }
        self.assertTrue(consensus.repair_path_shape(row))
        self.assertEqual("Pantry > Baking Mixes", row["category_path_fixed"])
        self.assertEqual([], consensus.path_defects(row))

        row = {
            "category_path_fixed": "Pantry",
            "canonical_path": "Pantry > Salad Dressing",
            "product_identity_fixed": "Salad Dressing",
            "modifier": "Raspberry",
            "retail_leaf_path": "Pantry > Salad Dressings > Raspberry",
        }
        self.assertTrue(consensus.repair_path_shape(row))
        self.assertEqual("Pantry > Salad Dressings", row["canonical_path"])
        self.assertEqual([], consensus.path_defects(row))


if __name__ == "__main__":
    unittest.main()
