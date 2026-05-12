import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "implementation"))

from nebius_contract_patch_builder import nutrient_sanity_check  # noqa: E402


class NutrientSanityTest(unittest.TestCase):
    def test_passes_when_proposed_code_matches_current(self):
        report = nutrient_sanity_check(current_esha_code=1, proposed_esha_code=1)
        self.assertTrue(report["passed"])

    def test_fails_when_nutrient_distance_huge(self):
        # butter (8000) -> whole milk (1) is a category shift; should flag
        report = nutrient_sanity_check(current_esha_code=8000, proposed_esha_code=1)
        self.assertFalse(report["passed"])
        self.assertIn("distance", report)
        self.assertGreater(report["distance"], 150.0)

    def test_passes_when_categories_agree(self):
        # whole milk -> 2% milk: acceptable proxy
        report = nutrient_sanity_check(current_esha_code=1, proposed_esha_code=2)
        self.assertTrue(report["passed"])
        self.assertLess(report["distance"], 150.0)

    def test_missing_code_returns_passed_with_reason(self):
        report = nutrient_sanity_check(current_esha_code=None, proposed_esha_code=1)
        self.assertTrue(report["passed"])
        self.assertIn("reason", report)


if __name__ == "__main__":
    unittest.main()
