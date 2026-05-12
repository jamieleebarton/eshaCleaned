import unittest
from pathlib import Path
from implementation.resolver_context import DEFAULT_ARTIFACTS


class TestConceptCandidatePaths(unittest.TestCase):
    def test_fndds_main_food_desc_path(self):
        p = DEFAULT_ARTIFACTS.fndds_main_food_desc_csv
        self.assertTrue(p.name == "MainFoodDesc16.csv")
        self.assertIn("data/fndds", str(p))

    def test_fndds_sr_links_path(self):
        p = DEFAULT_ARTIFACTS.fndds_sr_links_csv
        self.assertTrue(p.name == "FNDDSSRLinks.csv")

    def test_scratch_dir_path(self):
        p = DEFAULT_ARTIFACTS.concept_candidate_scratch_dir
        self.assertIn("scratch/20260413_fndds_concept_expansion", str(p))

    def test_proposed_concepts_csv(self):
        self.assertEqual(
            DEFAULT_ARTIFACTS.proposed_concepts_csv.name,
            "proposed_concepts.csv",
        )

    def test_proposed_rules_csv(self):
        self.assertEqual(
            DEFAULT_ARTIFACTS.proposed_normalization_rules_csv.name,
            "proposed_normalization_rules.csv",
        )

    def test_proposed_contracts_csv(self):
        self.assertEqual(
            DEFAULT_ARTIFACTS.proposed_product_contracts_csv.name,
            "proposed_product_contracts.csv",
        )

    def test_quarantine_csv(self):
        self.assertEqual(
            DEFAULT_ARTIFACTS.concept_candidate_quarantine_csv.name,
            "quarantined_rows.csv",
        )


if __name__ == "__main__":
    unittest.main()
