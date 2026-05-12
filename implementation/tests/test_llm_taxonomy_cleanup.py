import json
import sys
import unittest
from pathlib import Path


ROOT = Path("/Users/jamiebarton/Desktop/esha_audit_bundle")
V2 = ROOT / "retail_mapper" / "v2"
if str(V2) not in sys.path:
    sys.path.insert(0, str(V2))

import llm_taxonomy_cleanup as cleanup  # noqa: E402


GOLD = V2 / "llm_taxonomy_gold_cases.jsonl"
DIABOLICAL = V2 / "llm_taxonomy_diabolical_cases.jsonl"


def load_gold():
    rows = []
    for path in (GOLD, DIABOLICAL):
        with path.open(encoding="utf-8") as handle:
            rows.extend(json.loads(line) for line in handle if line.strip())
    return rows


class LlmTaxonomyCleanupTests(unittest.TestCase):
    def test_all_gold_expected_records_pass_contract(self) -> None:
        for case in load_gold():
            with self.subTest(case=case["name"]):
                self.assertEqual(cleanup.validate_record(case["expected"], case["source"]), [])

    def test_bad_outputs_are_rejected(self) -> None:
        for case in load_gold():
            for idx, bad in enumerate(case.get("bad_outputs", [])):
                with self.subTest(case=case["name"], bad=idx):
                    errors = cleanup.validate_record(bad, case["source"]) + cleanup.compare_record(bad, case["expected"])
                    self.assertTrue(errors)

    def test_diabolical_suite_is_loaded(self) -> None:
        names = {case["name"] for case in load_gold()}

        self.assertIn("diabolical_honey_mustard_pretzel_pieces", names)
        self.assertIn("diabolical_pizza_crust_mix_not_pizza", names)
        self.assertIn("diabolical_broccoli_cheddar_soup_not_cheese", names)
        self.assertIn("diabolical_chicken_burgers_not_cheese_or_vegetarian", names)
        self.assertIn("diabolical_vague_tuscan_meat_cheese_infer_sandwich", names)
        self.assertIn("diabolical_hatch_green_chile_asiago_cheese_crisps", names)
        self.assertIn("diabolical_sesame_garlic_chicken_meal_starter", names)
        self.assertIn("diabolical_chicken_apple_sausage_flatbread_breakfast_sandwich", names)

    def test_claim_order_is_semantic_not_alphabetical(self) -> None:
        self.assertEqual(cleanup.order_claims(["organic", "unsweetened"]), ["unsweetened", "organic"])
        self.assertNotEqual(cleanup.order_claims(["organic", "unsweetened"]), sorted(["organic", "unsweetened"]))

    def test_attributes_must_be_snake_case(self) -> None:
        case = load_gold()[0]
        bad = dict(case["expected"])
        bad["claims"] = ["Unsweetened", "Organic"]

        errors = cleanup.validate_record(bad, case["source"])

        self.assertIn("attribute_not_normalized:claims:Unsweetened", errors)
        self.assertIn("attribute_not_normalized:claims:Organic", errors)

    def test_tree_paths_are_derived_from_product_then_facets(self) -> None:
        case = next(row for row in load_gold() if row["name"] == "plant_milk_claim_order_and_facets")

        self.assertEqual(
            cleanup.build_tree_paths(case["expected"]),
            [
                "Retail Taxonomy > Beverage > Plant Milk > Almond Milk",
                "Retail Taxonomy > Beverage > Plant Milk > Almond Milk > @flavor > chocolate",
                "Retail Taxonomy > Beverage > Plant Milk > Almond Milk > @claims > unsweetened",
                "Retail Taxonomy > Beverage > Plant Milk > Almond Milk > @claims > organic",
            ],
        )

    def test_exact_gold_comparison_catches_well_formed_wrong_identity(self) -> None:
        case = next(row for row in load_gold() if row["name"] == "prepared_pasta_not_alfredo_sauce")
        bad = case["bad_outputs"][0]

        errors = cleanup.compare_record(bad, case["expected"])

        self.assertTrue(any(error.startswith("mismatch:product_identity") for error in errors))
        self.assertTrue(any(error.startswith("mismatch:canonical_path") for error in errors))

    def test_component_cut_stays_off_top_level_facets(self) -> None:
        case = next(row for row in load_gold() if row["name"] == "prepared_pasta_not_alfredo_sauce")
        expected = case["expected"]
        chicken = next(component for component in expected["components"] if component["identity"] == "Chicken Breast")

        self.assertEqual(expected["form_texture_cut"], [])
        self.assertEqual(chicken["form_texture_cut"], ["diced"])
        errors = cleanup.compare_record(case["bad_outputs"][1], expected)
        self.assertTrue(any(error.startswith("mismatch:form_texture_cut") for error in errors))
        self.assertTrue(any(error.startswith("mismatch:components") for error in errors))

    def test_combination_meal_requires_component_structure(self) -> None:
        case = next(row for row in load_gold() if row["name"] == "combination_meatloaf_meal_components")

        self.assertEqual([component["identity"] for component in case["expected"]["components"]], ["Meatloaf", "Mashed Potatoes", "Corn"])
        self.assertIn("combination_meal_missing_components", cleanup.validate_record(case["bad_outputs"][0], case["source"]))

    def test_alfredo_pizza_routes_to_pizza_with_sauce_component(self) -> None:
        case = next(row for row in load_gold() if row["name"] == "alfredo_ham_bacon_pizza_not_alfredo_sauce")
        expected = case["expected"]

        self.assertEqual(expected["product_identity"], "Pizza")
        self.assertIn({"identity": "Alfredo Sauce", "role": "sauce", "variant": [], "flavor": [], "form_texture_cut": [], "processing_storage": [], "claims": []}, expected["components"])
        errors = cleanup.compare_record(case["bad_outputs"][0], expected)
        self.assertTrue(any(error.startswith("mismatch:product_identity") for error in errors))
        self.assertTrue(any(error.startswith("mismatch:components") for error in errors))

    def test_vague_title_can_use_ingredients_to_infer_identity(self) -> None:
        case = next(row for row in load_gold() if row["name"] == "diabolical_vague_tuscan_meat_cheese_infer_sandwich")
        expected = case["expected"]

        self.assertEqual(expected["product_identity"], "Sandwich")
        self.assertIn("title_identity_inferred_from_ingredients", expected["review_flags"])
        self.assertIn({"identity": "French Roll", "role": "bread", "variant": [], "flavor": [], "form_texture_cut": [], "processing_storage": [], "claims": []}, expected["components"])

    def test_generic_cheese_does_not_guess_specific_type(self) -> None:
        case = next(row for row in load_gold() if row["name"] == "diabolical_hard_aged_cheese_no_unproven_specific_guess")
        expected = case["expected"]

        self.assertEqual(expected["product_identity"], "Cheese")
        self.assertEqual(expected["variant"], ["aged"])
        self.assertEqual(expected["form_texture_cut"], ["hard"])
        self.assertIn("specific_identity_missing", expected["review_flags"])

    def test_cheese_crisps_keep_crisp_identity_and_compound_flavor(self) -> None:
        case = next(row for row in load_gold() if row["name"] == "diabolical_hatch_green_chile_asiago_cheese_crisps")
        expected = case["expected"]

        self.assertEqual(expected["product_identity"], "Cheese Crisps")
        self.assertEqual(expected["variant"], ["asiago"])
        self.assertEqual(expected["flavor"], ["hatch_green_chile"])

    def test_meal_starter_is_not_collapsed_to_chicken(self) -> None:
        case = next(row for row in load_gold() if row["name"] == "diabolical_sesame_garlic_chicken_meal_starter")
        expected = case["expected"]

        self.assertEqual(expected["retail_type"], "meal_kit")
        self.assertEqual(expected["category_path"], "Meal > Meal Starters")
        self.assertEqual(expected["product_identity"], "Meal Starter")
        self.assertEqual(expected["variant"], ["sesame_garlic_chicken"])

    def test_flatbread_breakfast_sandwich_is_not_collapsed_to_chicken(self) -> None:
        case = next(row for row in load_gold() if row["name"] == "diabolical_chicken_apple_sausage_flatbread_breakfast_sandwich")
        expected = case["expected"]

        self.assertEqual(expected["product_identity"], "Breakfast Sandwich")
        self.assertEqual(expected["category_path"], "Frozen > Breakfast Sandwiches")
        self.assertEqual(expected["claims"], [])
        self.assertIn("flatbread", expected["form_texture_cut"])
        self.assertIn({"identity": "Multi-Grain Flatbread", "role": "bread", "variant": [], "flavor": [], "form_texture_cut": ["flatbread"], "processing_storage": [], "claims": []}, expected["components"])


if __name__ == "__main__":
    unittest.main()
