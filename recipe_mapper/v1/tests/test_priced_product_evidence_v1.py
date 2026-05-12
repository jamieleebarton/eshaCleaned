#!/usr/bin/env python3
"""Regression tests for the adjudicated priced-product evidence layer."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from build_priced_product_evidence_v1 import (  # noqa: E402
    EvidenceConcept,
    concept_index,
    decide_product,
)
from calculate_recipe_cost_v7 import is_tap_water_item, pick_product  # noqa: E402


def concept(
    pid: str,
    canonical: str,
    *,
    htc: set[str] | None = None,
    refs: set[str] | None = None,
    count: int = 100,
) -> EvidenceConcept:
    return EvidenceConcept(
        pid=pid,
        canonical=canonical,
        count=count,
        htc_prefixes=frozenset(htc or set()),
        reference_tokens=frozenset(refs or set(pid.lower().split())),
        avg_confidence=0.95,
        max_match_score=90.0,
    )


def product(
    name: str,
    *,
    category_path: str = "Home Page/Food",
    htc_code: str = "",
    consensus_pid: str = "",
    consensus_canonical: str = "",
    bridge_status: str = "title_match",
) -> dict[str, object]:
    return {
        "rowid": "test",
        "name": name,
        "category_path": category_path,
        "category_path_walmart": category_path,
        "htc_code": htc_code,
        "consensus_pid": consensus_pid,
        "consensus_canonical": consensus_canonical,
        "bridge_status": bridge_status,
    }


class PricedProductEvidenceV1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.index = concept_index([
            concept("Salt", "Pantry > Spices & Seasonings > Salt", htc={"E0"}),
            concept("Butter", "Dairy > Butter", htc={"10"}),
            concept("Ice Cream", "Frozen > Ice Cream", htc={"13"}, refs={"ice", "cream", "butter", "pecan"}),
            concept("Bananas", "Produce > Fruit > Bananas", htc={"60"}, refs={"banana", "bananas"}),
            concept("Almonds", "Snack > Nuts > Almonds", htc={"A0"}),
            concept(
                "Half and Half",
                "Beverage > Coffee Creamer > Half & Half",
                htc={"13"},
                refs={"half", "cream", "almond", "coconut"},
            ),
            concept("Cinnamon", "Pantry > Spices & Seasonings > Cinnamon", htc={"E2"}),
            concept("Candy", "Snack > Candy", htc={"80"}, refs={"candy", "bar", "creme", "chocolate"}),
            concept("Sandwich Cookies", "Bakery > Cookies > Sandwich Cookies", htc={"80"}),
            concept("Tomato Juice", "Beverage > Juice > Tomato Juice", htc={"D0"}, refs={"tomato", "juice"}),
        ])

    def test_rejects_water_softener_salt(self) -> None:
        decision = decide_product(
            product(
                "Morton Clean and Protect Water Softener Salt Pellets, 40 lb",
                category_path="Home Page/Home Improvement/Plumbing/Water Filtration & Water Softeners/Water Softener Salt",
                htc_code="D000600$",
                consensus_pid="Salt",
                consensus_canonical="Pantry > Spices & Seasonings > Salt",
            ),
            self.index,
        )
        self.assertEqual("reject_non_food", decision.taxonomy_status, decision)

    def test_butter_pecan_ice_cream_is_not_butter(self) -> None:
        decision = decide_product(
            product(
                "Edy's/Dreyer's Butter Pecan, 1.5 Qt",
                category_path="Home Page/Food/Frozen Foods/Ice Cream & Novelties/Ice Cream",
                htc_code="1300200A",
                consensus_pid="Butter",
                consensus_canonical="Dairy > Butter",
            ),
            self.index,
        )
        self.assertEqual("approved_taxonomy", decision.taxonomy_status, decision)
        self.assertEqual("Ice Cream", decision.proposed_pid, decision)

    def test_made_with_almonds_is_not_almonds(self) -> None:
        decision = decide_product(
            product(
                "nutpods Non Dairy Half & Half Alternative made with Almonds and Coconuts",
                category_path="Natural & Organic Beverages Dairy",
                htc_code="1300000$",
                consensus_pid="Almonds",
                consensus_canonical="Snack > Nuts > Almonds",
            ),
            self.index,
        )
        self.assertEqual("approved_taxonomy", decision.taxonomy_status, decision)
        self.assertEqual("Half and Half", decision.proposed_pid, decision)

    def test_salad_topper_mix_is_not_plain_almonds(self) -> None:
        decision = decide_product(
            product(
                "Great Value Dried Sweetened Cranberries & Honey Roasted Almonds Salad Topper, 3 oz",
                category_path="Home Page/Food/Snacks, Cookies & Chips/Nuts, Trail Mix & Seeds/Nuts",
                htc_code="A000430A",
                consensus_pid="Almonds",
                consensus_canonical="Snack > Nuts > Almonds",
                bridge_status="bridged",
            ),
            self.index,
        )
        self.assertFalse(decision.taxonomy_status.startswith("approved"), decision)
        self.assertIn("mix_or_sweet_component_identity", decision.hard_vetoes, decision)

    def test_chocolate_banana_dessert_is_not_plain_bananas(self) -> None:
        decision = decide_product(
            product(
                "Reese's Banana Slices in Milk Chocolate and Reese's Peanut Butter Chips, 8 oz (Frozen)",
                category_path="Home Page/Food/Frozen Foods/Frozen Fruits & Vegetables/Frozen Fruit",
                htc_code="60002005",
                consensus_pid="Peanut Butter Chips",
                consensus_canonical="Pantry > Baking Decorations > Peanut Butter Chips",
            ),
            self.index,
        )
        self.assertFalse(decision.taxonomy_status.startswith("approved"), decision)
        self.assertIn("sweet_coated_component_identity", decision.hard_vetoes, decision)

    def test_cinnamon_toaster_treats_are_not_approved_as_spice(self) -> None:
        decision = decide_product(
            product(
                "Kroger Frosted Brown Sugar Cinnamon Toaster Treats",
                category_path="Home Page/Food/Breakfast & Cereal/Toaster Pastries",
                htc_code="8000000A",
                consensus_pid="Cinnamon",
                consensus_canonical="Pantry > Spices & Seasonings > Cinnamon",
            ),
            self.index,
        )
        self.assertFalse(decision.taxonomy_status.startswith("approved"), decision)
        self.assertIn("major_category_conflict", decision.hard_vetoes, decision)

    def test_candy_context_beats_cookie_flavor_text(self) -> None:
        decision = decide_product(
            product(
                "Hershey's Cookies 'n' Creme Candy Bar",
                category_path="Home Page/Food/Snacks/Candy/Chocolate Candy",
                htc_code="8000000A",
                consensus_pid="Sandwich Cookies",
                consensus_canonical="Bakery > Cookies > Sandwich Cookies",
            ),
            self.index,
        )
        self.assertEqual("approved_taxonomy", decision.taxonomy_status, decision)
        self.assertEqual("Candy", decision.proposed_pid, decision)

    def test_tomato_juice_keeps_specific_beverage_identity(self) -> None:
        decision = decide_product(
            product(
                "Red Gold Fresh Squeezed Tomato Juice, 46 oz Can",
                category_path="Home Page/Food/Pantry/Canned goods/Canned tomatoes, sauce & puree",
                htc_code="D000100A",
                consensus_pid="Tomato Juice",
                consensus_canonical="Beverage > Juice > Tomato Juice",
            ),
            self.index,
        )
        self.assertTrue(decision.taxonomy_status.startswith("approved"), decision)
        self.assertEqual("Tomato Juice", decision.proposed_pid, decision)

    def test_v7_tap_water_rule_is_exact(self) -> None:
        self.assertTrue(is_tap_water_item("fresh water"))
        self.assertFalse(is_tap_water_item("coconut water"))
        self.assertFalse(is_tap_water_item("tonic water"))

    def test_v7_product_picker_has_no_head_noun_fallback(self) -> None:
        row = {
            "pid": "Ice Cream",
            "canonical": "Frozen > Ice Cream",
            "modifier": "",
            "evidence_score": 95.0,
            "cpg": 0.01,
            "cents": 100,
        }
        self.assertIsNone(pick_product("butter", {"concepts": {("Dairy > Butter", "")}}, [row]))

    def test_v7_product_picker_applies_recipe_form_and_composite_gates(self) -> None:
        mint_gum = {
            "pid": "Mints",
            "canonical": "Snack > Candy > Mints",
            "modifier": "",
            "name": "Mentos Pure White Sweet Mint Sugar Free Gum Bottle 50 Count",
            "evidence_score": 95.0,
            "cpg": 0.01,
            "cents": 100,
        }
        self.assertIsNone(
            pick_product(
                "mint",
                {"concepts": {("Snack > Candy > Mints", "")}},
                [mint_gum],
                {"ingredient_item": "mint", "display": "1/2 cup mint leaves", "facet_form": "leaves"},
            )
        )

        chocolate_bananas = {
            "pid": "Bananas",
            "canonical": "Produce > Fruit > Bananas",
            "modifier": "",
            "name": "Reese's Banana Slices in Milk Chocolate and Reese's Peanut Butter Chips",
            "evidence_score": 95.0,
            "cpg": 0.01,
            "cents": 100,
        }
        plain_bananas = {
            "pid": "Bananas",
            "canonical": "Produce > Fruit > Bananas",
            "modifier": "",
            "name": "Great Value Sliced Bananas, 16 oz Bag",
            "evidence_score": 60.0,
            "cpg": 0.02,
            "cents": 200,
        }
        picked = pick_product(
            "bananas",
            {"concepts": {("Produce > Fruit > Bananas", "")}},
            [chocolate_bananas, plain_bananas],
            {"ingredient_item": "bananas", "display": "4 bananas, mashed"},
        )
        self.assertEqual(plain_bananas, picked)

        lemon_juice = {
            "pid": "Lemon Juice",
            "canonical": "Beverage > Juice > Lemon Juice",
            "modifier": "",
            "name": "Santa Cruz Organic 100% Pure Lemon Juice",
            "evidence_score": 90.0,
            "cpg": 0.01,
            "cents": 100,
        }
        picked = pick_product(
            "fresh lemon juice",
            {"concepts": {("Beverage > Juice > Lemon Juice", "")}},
            [lemon_juice],
            {"ingredient_item": "fresh lemon juice", "display": "1 cup fresh lemon juice"},
        )
        self.assertEqual(lemon_juice, picked)

        baking_powder = {
            "pid": "Baking Powder",
            "canonical": "Pantry > Baking Extracts > Baking Powder",
            "modifier": "",
            "name": "Great Value Double Acting Baking Powder",
            "evidence_score": 65.0,
            "cpg": 0.01,
            "cents": 100,
        }
        picked = pick_product(
            "baking powder",
            {"concepts": {("Pantry > Baking Extracts > Baking Powder", "")}},
            [baking_powder],
            {"ingredient_item": "baking powder", "display": "1 teaspoon baking powder"},
        )
        self.assertEqual(baking_powder, picked)

        blueberries = {
            "pid": "Blueberries",
            "canonical": "Produce > Fruit > Blueberries",
            "modifier": "",
            "name": "Great Value Wild Blueberries, 40 oz (Frozen)",
            "evidence_score": 67.0,
            "cpg": 0.01,
            "cents": 100,
        }
        picked = pick_product(
            "blueberries",
            {"concepts": {("Produce > Fruit > Blueberries", "")}},
            [blueberries],
            {"ingredient_item": "blueberries", "display": "4 cups blueberries, fresh or frozen"},
        )
        self.assertEqual(blueberries, picked)

        expensive_salt = {
            "pid": "Salt",
            "canonical": "Pantry > Spices & Seasonings > Salt",
            "modifier": "",
            "name": "Real Salt Fine Salt Sea Salt, 2 oz",
            "evidence_score": 90.0,
            "cpg": 0.30,
            "cents": 1900,
        }
        cheap_salt = {
            "pid": "Salt",
            "canonical": "Pantry > Spices & Seasonings > Salt",
            "modifier": "",
            "name": "Great Value Coarse Sea Salt, 17.6 oz",
            "evidence_score": 84.0,
            "cpg": 0.005,
            "cents": 250,
        }
        salt_blend = {
            "pid": "Salt",
            "canonical": "Pantry > Spices & Seasonings > Salt",
            "modifier": "",
            "name": "Great Value Black Pepper & Iodized Salt",
            "evidence_score": 92.0,
            "cpg": 0.001,
            "cents": 100,
        }
        picked = pick_product(
            "salt",
            {"concepts": {("Pantry > Spices & Seasonings > Salt", "")}},
            [expensive_salt, cheap_salt, salt_blend],
            {"ingredient_item": "salt", "display": "1 teaspoon salt"},
        )
        self.assertEqual(cheap_salt, picked)


if __name__ == "__main__":
    unittest.main(verbosity=2)
