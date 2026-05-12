# implementation/tests/test_non_food.py
import unittest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from non_food_words import is_non_food


class NonFoodLexiconTests(unittest.TestCase):
    def test_parchment_paper_is_non_food(self):
        self.assertTrue(is_non_food("parchment paper"))

    def test_toothpicks_is_non_food(self):
        self.assertTrue(is_non_food("toothpicks"))
        self.assertTrue(is_non_food("wooden toothpicks"))

    def test_plastic_wrap_is_non_food(self):
        self.assertTrue(is_non_food("plastic wrap"))
        self.assertTrue(is_non_food("saran wrap"))

    def test_aluminum_foil_is_non_food(self):
        self.assertTrue(is_non_food("aluminum foil"))
        self.assertTrue(is_non_food("tin foil"))

    def test_skewers_is_non_food(self):
        self.assertTrue(is_non_food("barbecue skewers"))
        self.assertTrue(is_non_food("wooden skewers"))
        self.assertTrue(is_non_food("bamboo skewers"))

    def test_butter_is_food(self):
        self.assertFalse(is_non_food("butter"))

    def test_salt_is_food(self):
        self.assertFalse(is_non_food("salt"))

    def test_case_insensitive(self):
        self.assertTrue(is_non_food("TOOTHPICKS"))
        self.assertTrue(is_non_food("Parchment Paper"))

    def test_zero_grams_alone_is_not_sufficient(self):
        """Guardrail #8: non_food requires lexicon hit, not grams=0."""
        # this function doesn't take grams — that's the whole point
        self.assertFalse(is_non_food("water"))  # zero-kcal food, not non-food


if __name__ == "__main__":
    unittest.main()
