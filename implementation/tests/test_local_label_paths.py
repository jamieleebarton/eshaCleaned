import unittest

from implementation.resolver_context import DEFAULT_ARTIFACTS


class TestLocalLabelPaths(unittest.TestCase):
    def test_proposed_local_label_concepts_csv(self):
        self.assertEqual(
            DEFAULT_ARTIFACTS.proposed_local_label_concepts_csv.name,
            "proposed_local_label_concepts.csv",
        )
        self.assertIn(
            "scratch/20260413_fndds_concept_expansion",
            str(DEFAULT_ARTIFACTS.proposed_local_label_concepts_csv),
        )

    def test_proposed_local_label_rules_csv(self):
        self.assertEqual(
            DEFAULT_ARTIFACTS.proposed_local_label_rules_csv.name,
            "proposed_local_label_rules.csv",
        )

    def test_proposed_local_label_contracts_csv(self):
        self.assertEqual(
            DEFAULT_ARTIFACTS.proposed_local_label_contracts_csv.name,
            "proposed_local_label_contracts.csv",
        )

    def test_local_label_unmatched_csv(self):
        self.assertEqual(
            DEFAULT_ARTIFACTS.local_label_unmatched_csv.name,
            "local_label_unmatched.csv",
        )

    def test_proposed_seed_parents_csv(self):
        self.assertEqual(
            DEFAULT_ARTIFACTS.proposed_seed_parents_csv.name,
            "proposed_seed_parents.csv",
        )


if __name__ == "__main__":
    unittest.main()
