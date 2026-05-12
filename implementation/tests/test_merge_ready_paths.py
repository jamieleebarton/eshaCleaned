import unittest
from implementation.resolver_context import DEFAULT_ARTIFACTS


class TestMergeReadyPaths(unittest.TestCase):
    def test_merge_ready_dir(self):
        self.assertIn("merge_ready", str(DEFAULT_ARTIFACTS.merge_ready_dir))

    def test_auto_concepts(self):
        self.assertEqual(DEFAULT_ARTIFACTS.merge_ready_auto_concepts_csv.name, "merge_ready_auto_concepts.csv")

    def test_auto_rules(self):
        self.assertEqual(DEFAULT_ARTIFACTS.merge_ready_auto_rules_csv.name, "merge_ready_auto_rules.csv")

    def test_auto_contracts(self):
        self.assertEqual(DEFAULT_ARTIFACTS.merge_ready_auto_contracts_csv.name, "merge_ready_auto_contracts.csv")

    def test_review_concepts(self):
        self.assertEqual(DEFAULT_ARTIFACTS.merge_ready_review_concepts_csv.name, "merge_ready_review_concepts.csv")

    def test_review_rules(self):
        self.assertEqual(DEFAULT_ARTIFACTS.merge_ready_review_rules_csv.name, "merge_ready_review_rules.csv")

    def test_review_contracts(self):
        self.assertEqual(DEFAULT_ARTIFACTS.merge_ready_review_contracts_csv.name, "merge_ready_review_contracts.csv")

    def test_rejected(self):
        self.assertEqual(DEFAULT_ARTIFACTS.merge_rejected_csv.name, "merge_rejected.csv")

    def test_parent_updates(self):
        self.assertEqual(DEFAULT_ARTIFACTS.proposed_parent_contract_updates_csv.name, "proposed_parent_contract_updates.csv")


if __name__ == "__main__":
    unittest.main()
