from __future__ import annotations

import sys
import unittest
from pathlib import Path


IMPLEMENTATION_ROOT = Path(__file__).resolve().parents[1]
if str(IMPLEMENTATION_ROOT) not in sys.path:
    sys.path.insert(0, str(IMPLEMENTATION_ROOT))

from rft_clean_product_map import (  # noqa: E402
    should_quarantine_spread_gap,
    should_promote_cinnamon_applesauce,
    unsafe_dairy_inherited_route,
)


class RFTCleanProductMapRegressionTests(unittest.TestCase):
    def _row(self, verdict: str = "WEAK") -> dict[str, str]:
        return {
            "product_description": "HABANERO PEPPER JELLY",
            "branded_food_category": "Jam, Jelly & Fruit Spreads",
            "rft_verdict": verdict,
            "best_esha_original_code": "48230",
            "best_esha_code": "48230",
        }

    def test_spread_gap_quarantines_cheese_incumbent(self) -> None:
        self.assertTrue(
            should_quarantine_spread_gap(
                self._row(),
                "Cheese, monterey jack, with habanero peppers, shredded",
            )
        )

    def test_spread_gap_quarantines_plain_pepper_incumbent(self) -> None:
        self.assertTrue(
            should_quarantine_spread_gap(
                self._row("NEEDS_NEW_CONCEPT"),
                "Chile Pepper, habanero, red, fresh",
            )
        )

    def test_spread_gap_keeps_spread_family_incumbent(self) -> None:
        self.assertFalse(
            should_quarantine_spread_gap(
                self._row(),
                "Jelly",
            )
        )

    def test_exact_spread_route_does_not_quarantine(self) -> None:
        self.assertFalse(
            should_quarantine_spread_gap(
                self._row("EXACT"),
                "Cheese, monterey jack, with habanero peppers, shredded",
            )
        )


class RFTCleanProductMapDairyRegressionTests(unittest.TestCase):
    def test_inherited_creamer_to_coffee_is_unsafe(self) -> None:
        row = {
            "product_description": "COFFEE CREAMER",
            "branded_food_category": "Cream/Cream Substitutes",
        }
        self.assertTrue(
            unsafe_dairy_inherited_route(row, "coffee", "inherited")
        )

    def test_inherited_almond_milk_to_plain_milk_is_unsafe(self) -> None:
        row = {
            "product_description": "Silk Almondmilk Original",
            "branded_food_category": "Plant Based Milk",
        }
        self.assertTrue(
            unsafe_dairy_inherited_route(row, "milk", "inherited")
        )

    def test_exact_condensed_milk_route_is_allowed(self) -> None:
        row = {
            "product_description": "Sweetened Condensed Milk",
            "branded_food_category": "Milk",
        }
        self.assertFalse(
            unsafe_dairy_inherited_route(row, "milk, condensed, sweetened", "exact")
        )

    def test_inherited_fat_free_milk_to_skim_is_allowed(self) -> None:
        row = {
            "product_description": "Fat Free Milk",
            "branded_food_category": "Milk",
        }
        self.assertFalse(
            unsafe_dairy_inherited_route(row, "milk, skim, calcium fortified", "inherited")
        )


class RFTCleanProductMapApplesauceRegressionTests(unittest.TestCase):
    def test_cinnamon_applesauce_promotes_when_only_packaging_is_missing(self) -> None:
        row = {
            "rft_verdict": "NEEDS_NEW_CONCEPT",
            "rft_concept_tokens": "applesauce|cinnamon",
            "rft_missing": "go|squeeze",
        }
        self.assertTrue(should_promote_cinnamon_applesauce(row, "46799"))

    def test_cinnamon_applesauce_does_not_promote_other_concepts(self) -> None:
        row = {
            "rft_verdict": "WEAK",
            "rft_concept_tokens": "apple|cinnamon|sauce",
            "rft_missing": "",
        }
        self.assertFalse(should_promote_cinnamon_applesauce(row, "46799"))

    def test_cinnamon_applesauce_does_not_promote_unknown_missing_identity(self) -> None:
        row = {
            "rft_verdict": "WEAK",
            "rft_concept_tokens": "applesauce|cinnamon",
            "rft_missing": "pear",
        }
        self.assertFalse(should_promote_cinnamon_applesauce(row, "46799"))


if __name__ == "__main__":
    unittest.main()
