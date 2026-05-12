from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from planner.household_free import (  # noqa: E402
    canonical_path_from_concept_key,
    household_free_decision,
    is_household_free_recipe_concept,
)


class HouseholdFreeTests(unittest.TestCase):
    def test_exact_recipe_water_and_ice_are_household_free(self) -> None:
        for key in [
            "Beverage > Water|D502600*",
            "Beverage > Water > Tap Water|D502600*",
            "Beverage > Ice|D502600*",
        ]:
            with self.subTest(key=key):
                decision = household_free_decision(key, "Beverage > Water|D502600*")
                self.assertTrue(decision.is_free)
                self.assertIn("recipe_path:", decision.reason)

    def test_water_named_foods_are_not_household_free(self) -> None:
        for key in [
            "Produce > Fruit > Watermelon|7501600H",
            "Pantry > Canned Vegetables > Water Chestnuts|6A07600P",
            "Beverage > Coconut Water|D129600Z",
            "Beverage > Sparkling Water|D206600V",
            "Beverage > Water > Tonic Water|D25J600A",
            "Beverage > Water > Rose Water|D129600Z",
            "Snack > Crackers > Water Crackers|J007000T",
        ]:
            with self.subTest(key=key):
                self.assertFalse(is_household_free_recipe_concept(key))

    def test_recipe_identity_overrides_broadened_priced_water_resolution(self) -> None:
        decision = household_free_decision(
            "Beverage > Water > Tonic Water|D25J600A",
            "Beverage > Water|D502600*",
        )

        self.assertFalse(decision.is_free)

    def test_extracts_canonical_path_without_substring_logic(self) -> None:
        self.assertEqual(
            canonical_path_from_concept_key("Pantry > Canned Vegetables > Water Chestnuts|6A07600P"),
            "Pantry > Canned Vegetables > Water Chestnuts",
        )


if __name__ == "__main__":
    unittest.main()
