import unittest

from implementation import audit_recipe_qa_nutrition_calculation as qa_audit
from implementation.build_calculator_closure_queue import classify_fix


class CalculatorClosureQueueTests(unittest.TestCase):
    def test_sr28_grams_missing_routes_to_household_rules(self):
        required_file, fix_type, _ = classify_fix(
            {
                "blocker_bucket": "grams_missing_or_zero",
                "concept_key": "lime juice|||",
                "product_contract_key": "lime juice|||",
                "nutrition_status": "nutrition_ready_sr28_fallback",
                "line_failure_bucket": "calculation_candidate",
            }
        )
        self.assertEqual(required_file, "reviewed_household_unit_gram_rules.csv")
        self.assertEqual(fix_type, "sr28_measure_or_quantity_policy")

    def test_concept_unresolved_routes_to_normalization_rules(self):
        required_file, fix_type, _ = classify_fix(
            {
                "blocker_bucket": "concept_unresolved",
                "concept_key": "|||",
                "product_contract_key": "|||",
                "nutrition_status": "",
                "line_failure_bucket": "concept_unresolved",
            }
        )
        self.assertEqual(required_file, "approved_normalization_rules.csv")
        self.assertEqual(fix_type, "concept_identity")

    def test_product_zero_routes_to_sr28_fallback(self):
        required_file, fix_type, _ = classify_fix(
            {
                "blocker_bucket": "product_nutrition_zero_or_rounded",
                "concept_key": "chipotle powder|||",
                "product_contract_key": "chipotle powder|||",
                "nutrition_status": "product_nutrition_zero_or_rounded",
                "line_failure_bucket": "calculation_candidate",
            }
        )
        self.assertEqual(required_file, "reviewed_sr28_nutrition_fallbacks.csv")
        self.assertEqual(fix_type, "sr28_nutrition_fallback")

    def test_sr28_product_bucket_routes_to_calculator_wiring(self):
        required_file, fix_type, _ = classify_fix(
            {
                "blocker_bucket": "product_not_candidate_covered",
                "concept_key": "feta cheese|||",
                "product_contract_key": "feta cheese|||",
                "nutrition_status": "nutrition_ready_sr28_fallback",
                "line_failure_bucket": "product_not_candidate_covered",
            }
        )
        self.assertEqual(required_file, "audit_recipe_qa_nutrition_calculation.py")
        self.assertEqual(fix_type, "calculator_wiring")

    def test_reviewed_external_catalog_covers_broken_product_nutrition_buckets(self):
        self.assertIn(
            "product_nutrition_zero_or_rounded",
            qa_audit.EXTERNAL_CATALOG_FALLBACK_BUCKETS,
        )
        self.assertIn("serving_unit_not_grams", qa_audit.EXTERNAL_CATALOG_FALLBACK_BUCKETS)


if __name__ == "__main__":
    unittest.main()
