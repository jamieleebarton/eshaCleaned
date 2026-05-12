#!/usr/bin/env python3
"""Regression tests for recipe pricing concept resolution."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pricing_concept_resolver import (  # noqa: E402
    PricingConceptResolver,
    product_passes_gate,
)


def product(name: str, *, canonical: str = "", category_path: str = "Home Page/Food") -> dict[str, str]:
    return {
        "name": name,
        "canonical": canonical,
        "category_path": category_path,
        "category_path_walmart": category_path,
    }


class PricingConceptResolverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.resolver = PricingConceptResolver()

    def assertResolvesTo(self, item: str, concept: tuple[str, str]) -> None:
        resolved = self.resolver.resolve(item)
        self.assertIn(concept, resolved.concepts, resolved)

    def test_high_volume_recipe_aliases_resolve_to_tree_concepts(self) -> None:
        cases = {
            "all-purpose flour": ("Pantry > Flour", ""),
            "granulated sugar": ("Pantry > Sweeteners > Sugar", ""),
            "unsalted butter": ("Dairy > Butter", ""),
            "kosher salt": ("Pantry > Spices & Seasonings > Salt", ""),
            "sharp cheddar cheese": ("Dairy > Cheese > Cheddar", ""),
            "parmesan cheese": ("Dairy > Cheese > Parmesan", ""),
            "heavy cream": ("Dairy > Cream > Heavy Cream", ""),
            "ground cinnamon": ("Pantry > Spices & Seasonings > Cinnamon", ""),
            "black pepper": ("Pantry > Spices & Seasonings > Black Pepper", ""),
            "egg yolks": ("Dairy > Eggs", ""),
            "garlic cloves": ("Produce > Vegetables > Garlic", ""),
            "corn starch": ("Pantry > Flour > Corn Starch", ""),
            "ground beef": ("Meat & Seafood > Beef > Ground Beef", ""),
            "bay leaves": ("Pantry > Spices & Seasonings > Bay Leaves", ""),
            "applesauce": ("Pantry > Applesauce", ""),
            "vanilla yogurt": ("Dairy > Yogurt", ""),
        }
        for item, concept in cases.items():
            with self.subTest(item=item):
                self.assertResolvesTo(item, concept)

    def test_safe_equivalence_preserves_spice_identity(self) -> None:
        resolved = self.resolver.resolve("black pepper")
        self.assertIn(
            ("Pantry > Spices & Seasonings > Spice Blend", "black pepper"),
            resolved.match_concepts(),
        )
        self.assertNotIn(
            ("Pantry > Spices & Seasonings > Spice Blend", "lemon"),
            resolved.match_concepts(),
        )

    def test_gates_accept_real_staples(self) -> None:
        positives = [
            ("all-purpose flour", "Arrowhead Mills Unbleached Organic All Purpose Flour", "Pantry > Flour"),
            ("granulated sugar", "Great Value Pure Granulated Sugar", "Pantry > Sweeteners > Sugar"),
            ("unsalted butter", "Great Value Sweet Cream Unsalted Butter", "Dairy > Butter"),
            ("kosher salt", "Morton Coarse Kosher Salt", "Pantry > Spices & Seasonings > Salt"),
            ("ground cinnamon", "Great Value Ground Cinnamon", "Pantry > Spices & Seasonings > Cinnamon"),
            ("parmesan cheese", "Great Value Grated Parmesan Cheese", "Dairy > Cheese > Parmesan"),
            ("heavy cream", "Great Value Heavy Whipping Cream", "Dairy > Cream > Heavy Whipping Cream"),
            ("ground beef", "All Natural 80% Lean 20% Fat Ground Beef", "Meat & Seafood > Beef > Ground Beef"),
            ("egg whites", "Kroger Large White Eggs", "Dairy > Eggs > Egg Whites"),
            ("applesauce", "Mott's Unsweetened Applesauce", "Pantry > Applesauce"),
            ("vanilla yogurt", "Kroger Vanilla Lowfat Yogurt", "Dairy > Yogurt"),
        ]
        for item, title, canonical in positives:
            with self.subTest(item=item):
                resolved = self.resolver.resolve(item)
                self.assertTrue(
                    product_passes_gate(resolved, product(title, canonical=canonical, category_path=canonical)),
                    resolved,
                )

    def test_gates_reject_retail_noise(self) -> None:
        negatives = [
            ("kosher salt", "McCormick Gourmet Kosher All Natural Celery Salt"),
            ("black pepper", "Lemon Pepper Seasoning Blend"),
            ("ground cinnamon", "Kroger Brown Sugar Cinnamon Toaster Treats"),
            ("unsalted butter", "Edy's Butter Pecan Ice Cream"),
            ("parmesan cheese", "Ragu Parmesan Romano Pasta Sauce"),
            ("heavy cream", "Nutpods Almond Coconut Coffee Creamer"),
            ("egg", "Best Foods Vegan Spread Free From Eggs"),
            ("garlic cloves", "Garlic Butter Broccoli"),
            ("ground beef", "Plant Based Ground Beef Crumbles"),
            ("egg whites", "Eggylicious Whole Egg Powder"),
            ("applesauce", "Mott's Mango Peach Applesauce"),
            ("vanilla yogurt", "Vanilla Frozen Yogurt Bars"),
        ]
        for item, title in negatives:
            with self.subTest(item=item):
                resolved = self.resolver.resolve(item)
                self.assertFalse(
                    product_passes_gate(resolved, product(title, canonical="Pantry > Spices & Seasonings")),
                    resolved,
                )


if __name__ == "__main__":
    unittest.main()
