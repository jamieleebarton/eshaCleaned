#!/usr/bin/env python3
"""Golden tests for the priced-product consensus bridge dry-run scorer."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from build_priced_consensus_bridge_v2 import (  # noqa: E402
    ConsensusConcept,
    concept_index,
    decide_product_bridge,
)


def product(
    name: str,
    *,
    category_path: str = "Home Page/Food",
    htc_code: str = "",
    consensus_pid: str = "",
    consensus_canonical: str = "",
    bridge_status: str = "",
) -> dict[str, object]:
    return {
        "name": name,
        "category_path": category_path,
        "category_path_walmart": category_path,
        "htc_code": htc_code,
        "consensus_pid": consensus_pid,
        "consensus_canonical": consensus_canonical,
        "bridge_status": bridge_status,
    }


class PricedConsensusBridgeV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        concepts = [
            ConsensusConcept("Salt", "Pantry > Spices & Seasonings > Salt", htc_groups=frozenset({"E0"}), count=500),
            ConsensusConcept("Lemon Juice", "Pantry > Sauces & Salsas > Lemon Juice", htc_groups=frozenset({"F7"}), count=200),
            ConsensusConcept("Yogurt", "Dairy > Yogurt", htc_groups=frozenset({"10"}), count=1000),
            ConsensusConcept("Onions", "Produce > Vegetables > Onions", htc_groups=frozenset({"60"}), count=700),
            ConsensusConcept("Yellow Onions", "Produce > Vegetables > Onions > Yellow Onions", htc_groups=frozenset({"60"}), count=100),
            ConsensusConcept("Cloves", "Pantry > Spices & Seasonings > Cloves", htc_groups=frozenset({"E2"}), count=100),
            ConsensusConcept("Salad Dressing", "Pantry > Salad Dressings", htc_groups=frozenset({"F7"}), count=900),
            ConsensusConcept("Lime", "Frozen > Frozen Fruit > Lime", htc_groups=frozenset({"73"}), count=50),
            ConsensusConcept("Butter", "Dairy > Butter", htc_groups=frozenset({"10"}), count=400),
            ConsensusConcept("Ice Cream", "Frozen > Ice Cream", htc_groups=frozenset({"13"}), count=800),
            ConsensusConcept("Almonds", "Snack > Nuts > Almonds", htc_groups=frozenset({"A0"}), count=300),
            ConsensusConcept("Half and Half", "Dairy > Cream > Half and Half", htc_groups=frozenset({"10"}), count=120),
            ConsensusConcept("Cinnamon", "Pantry > Spices & Seasonings > Cinnamon", htc_groups=frozenset({"E2"}), count=120),
            ConsensusConcept("Apples", "Pantry > Canned Fruit > Apples", htc_groups=frozenset({"70"}), count=100),
            ConsensusConcept("Water", "Beverage > Water", htc_groups=frozenset({"D0"}), count=400),
            ConsensusConcept("Tonic Water", "Beverage > Water > Tonic Water", htc_groups=frozenset({"D0"}), count=80),
            ConsensusConcept("Eggs", "Dairy > Eggs", htc_groups=frozenset({"50"}), count=200),
            ConsensusConcept("Cereal", "Pantry > Cereal", htc_groups=frozenset({"80"}), count=500),
            ConsensusConcept("Sandwich", "Meal > Sandwich", modifier="Multi Grain", htc_groups=frozenset({"80"}), count=200),
            ConsensusConcept("Juice", "Beverage > Juice", htc_groups=frozenset({"D0"}), count=500),
            ConsensusConcept("Salsa", "Pantry > Sauces & Salsas > Salsa", modifier="Mango Peach", htc_groups=frozenset({"F7"}), count=300),
            ConsensusConcept("Tomato Juice", "Beverage > Juice > Tomato Juice", htc_groups=frozenset({"D0"}), count=100),
            ConsensusConcept("Sauce", "Pantry > Sauces & Salsas > Sauce", modifier="Tomato", htc_groups=frozenset({"F7"}), count=300),
            ConsensusConcept("Cheese", "Dairy > Cheese", htc_groups=frozenset({"10"}), count=500),
            ConsensusConcept("Soup", "Pantry > Soup", modifier="Cheddar", htc_groups=frozenset({"10"}), count=300),
            ConsensusConcept("Seasoning", "Pantry > Spices & Seasonings > Seasoning", modifier="Salted", htc_groups=frozenset({"E2"}), count=300),
            ConsensusConcept("Seasoning", "Pantry > Spices & Seasonings > Seasoning", modifier="Lemon", htc_groups=frozenset({"E2"}), count=300),
            ConsensusConcept("Bacon Grease", "Pantry > Sauces & Salsas > Bacon Grease", htc_groups=frozenset({"F0"}), count=20),
            ConsensusConcept("Extract", "Pantry > Baking Extracts", htc_groups=frozenset({"E2"}), count=100),
            ConsensusConcept("Sandwich Cookies", "Bakery > Cookies > Sandwich Cookies", htc_groups=frozenset({"80"}), count=100),
            ConsensusConcept("Baking Mix", "Pantry > Baking Mixes > Baking Mix", htc_groups=frozenset({"80"}), count=100),
            ConsensusConcept("Bread", "Bakery > Bread", htc_groups=frozenset({"80"}), count=100),
            ConsensusConcept("Olive Oil", "Pantry > Oil > Olive Oil", htc_groups=frozenset({"F0"}), count=100),
            ConsensusConcept("Oil", "Pantry > Oil", htc_groups=frozenset({"F0"}), count=100),
            ConsensusConcept("Mackerel", "Meat & Seafood > Fish > Mackerel", htc_groups=frozenset({"40"}), count=100),
        ]
        cls.index = concept_index(concepts)

    def assertAcceptedAs(self, row: dict[str, object], pid: str) -> None:
        decision = decide_product_bridge(row, self.index)
        self.assertEqual("accepted", decision.status, decision)
        self.assertEqual(pid, decision.proposed_pid, decision)

    def assertNotAcceptedAs(self, row: dict[str, object], pid: str) -> None:
        decision = decide_product_bridge(row, self.index)
        self.assertFalse(
            decision.status == "accepted" and decision.proposed_pid == pid,
            decision,
        )

    def test_positive_staples(self) -> None:
        self.assertAcceptedAs(
            product(
                "Kroger Salt",
                category_path="Home Page/Food/Pantry/Spices & Seasonings/Salt",
                htc_code="E0000006",
            ),
            "Salt",
        )
        self.assertAcceptedAs(
            product("Great Value Lemon 100% Juice, 32 fl oz", htc_code="F700100$"),
            "Lemon Juice",
        )
        self.assertAcceptedAs(
            product("Kroger Plain Low Fat Yogurt Tub", category_path="Home Page/Food/Dairy/Yogurt", htc_code="1000000D"),
            "Yogurt",
        )
        self.assertAcceptedAs(
            product("Fresh Yellow Onions, 3 lb Bag", category_path="Home Page/Food/Produce/Fresh Vegetables/Onions", htc_code="6000100K"),
            "Yellow Onions",
        )
        self.assertAcceptedAs(
            product("Great Value Ground Cloves, 2 oz", category_path="Home Page/Food/Pantry/Spices & Seasonings", htc_code="E200002B"),
            "Cloves",
        )

    def test_rejects_water_softener_salt(self) -> None:
        decision = decide_product_bridge(
            product(
                "Morton Clean and Protect Water Softener Salt Pellets, 40 lb",
                category_path="Home Page/Home Improvement/Plumbing/Water Filtration & Water Softeners/Water Softener Salt",
                htc_code="D000600$",
                consensus_pid="Salt",
                consensus_canonical="Pantry > Spices & Seasonings > Salt",
                bridge_status="title_match",
            ),
            self.index,
        )
        self.assertEqual("reject_non_food", decision.status, decision)

    def test_dressing_is_not_lime(self) -> None:
        decision = decide_product_bridge(
            product(
                "Briannas Home Style Creamy Cilantro Lime, 12 oz Bottle",
                category_path="Home Page/Food/Pantry/Salad dressings & toppings/Shop all salad dressings & toppings",
                htc_code="F700100$",
                consensus_pid="Lime",
                consensus_canonical="Frozen > Frozen Fruit > Lime",
                bridge_status="title_match",
            ),
            self.index,
        )
        self.assertEqual("accepted", decision.status, decision)
        self.assertEqual("Salad Dressing", decision.proposed_pid, decision)

    def test_butter_pecan_ice_cream_is_not_butter(self) -> None:
        decision = decide_product_bridge(
            product(
                "Edy's/Dreyer's Butter Pecan, 1.5 Qt",
                category_path="Home Page/Food/Frozen Foods/Ice Cream & Novelties/Ice Cream",
                htc_code="1300200A",
                consensus_pid="Butter",
                consensus_canonical="Dairy > Butter",
                bridge_status="title_match",
            ),
            self.index,
        )
        self.assertEqual("accepted", decision.status, decision)
        self.assertEqual("Ice Cream", decision.proposed_pid, decision)

    def test_made_with_almonds_is_not_almonds(self) -> None:
        decision = decide_product_bridge(
            product(
                "nutpods Non Dairy Half & Half Alternative made with Almonds and Coconuts",
                category_path="Natural & Organic Beverages Dairy",
                htc_code="1300000$",
                consensus_pid="Almonds",
                consensus_canonical="Snack > Nuts > Almonds",
                bridge_status="title_match",
            ),
            self.index,
        )
        self.assertEqual("accepted", decision.status, decision)
        self.assertEqual("Half and Half", decision.proposed_pid, decision)

    def test_cinnamon_component_is_not_spice_identity(self) -> None:
        decision = decide_product_bridge(
            product(
                "Margaret Holmes Fried Apples with Cinnamon",
                category_path="Home Page/Food/Pantry/Canned Fruit",
                htc_code="7300000T",
                consensus_pid="Cinnamon",
                consensus_canonical="Pantry > Spices & Seasonings > Cinnamon",
                bridge_status="title_match",
            ),
            self.index,
        )
        self.assertEqual("accepted", decision.status, decision)
        self.assertEqual("Apples", decision.proposed_pid, decision)

    def test_tonic_water_is_not_plain_water(self) -> None:
        decision = decide_product_bridge(
            product(
                "Kroger Tonic Water with Quinine",
                category_path="Home Page/Food/Beverages/Water/Tonic Water",
                htc_code="D000600$",
                consensus_pid="Water",
                consensus_canonical="Beverage > Water",
                bridge_status="title_match",
            ),
            self.index,
        )
        self.assertEqual("accepted", decision.status, decision)
        self.assertEqual("Tonic Water", decision.proposed_pid, decision)

    def test_vegan_spread_is_not_eggs(self) -> None:
        self.assertNotAcceptedAs(
            product(
                "Best Foods Vegan Spread, Plant Based, Free From Eggs",
                category_path="Home Page/Food/Pantry/Condiments/Mayonnaise",
                htc_code="F000000H",
                consensus_pid="Eggs",
                consensus_canonical="Dairy > Eggs",
                bridge_status="title_match",
            ),
            "Eggs",
        )

    def test_composite_modifier_is_not_product_identity(self) -> None:
        decision = decide_product_bridge(
            product(
                "Multi Grain Cheerios, Heart Healthy Breakfast Cereal, Gluten Free, 9 oz",
                category_path="Home Page/Food/Breakfast & Cereal/Cereal & Granola/Healthy Cereal",
                htc_code="8000000A",
                consensus_pid="Cereal",
                consensus_canonical="Pantry > Cereal",
                bridge_status="title_match",
            ),
            self.index,
        )
        self.assertEqual("accepted", decision.status, decision)
        self.assertEqual("Cereal", decision.proposed_pid, decision)

    def test_beverage_juice_is_not_salsa_or_sauce(self) -> None:
        decision = decide_product_bridge(
            product(
                "Great Value Mango Peach Flavored, 100% Juice, 64 fl oz",
                category_path="Home Page/Food/Beverages/Juices/Kids & Multipack Juices",
                htc_code="D000100A",
                consensus_pid="Juice",
                consensus_canonical="Beverage > Juice",
                bridge_status="title_match",
            ),
            self.index,
        )
        self.assertEqual("accepted", decision.status, decision)
        self.assertEqual("Juice", decision.proposed_pid, decision)

        decision = decide_product_bridge(
            product(
                "Red Gold Fresh Squeezed Tomato Juice, 46 oz Can",
                category_path="Home Page/Food/Pantry/Canned goods/Canned tomatoes, sauce & puree",
                htc_code="D000100A",
                consensus_pid="Tomato Juice",
                consensus_canonical="Beverage > Juice > Tomato Juice",
                bridge_status="title_match",
            ),
            self.index,
        )
        self.assertEqual("accepted", decision.status, decision)
        self.assertEqual("Tomato Juice", decision.proposed_pid, decision)

    def test_dairy_singletons_are_not_rule_b_modifiers(self) -> None:
        decision = decide_product_bridge(
            product(
                "Great Value Sweet Cream Salted Butter, 16 oz, 4 Sticks",
                category_path="Home Page/Food/Dairy & Eggs/Butter & Margarine/Butter Sticks",
                htc_code="1000000D",
                consensus_pid="Butter",
                consensus_canonical="Dairy > Butter",
                bridge_status="title_match",
            ),
            self.index,
        )
        self.assertEqual("accepted", decision.status, decision)
        self.assertEqual("Butter", decision.proposed_pid, decision)

        decision = decide_product_bridge(
            product(
                "Red Apple Cheese Natural Gruyere Wisconsin Cheese, 7 oz Square",
                category_path="Home Page/Food/Dairy & Eggs/Cheese/Specialty Cheese",
                htc_code="1000000D",
                consensus_pid="Cheese",
                consensus_canonical="Dairy > Cheese",
                bridge_status="title_match",
            ),
            self.index,
        )
        self.assertEqual("accepted", decision.status, decision)
        self.assertEqual("Cheese", decision.proposed_pid, decision)

    def test_cast_iron_seasoning_context_does_not_override_bacon_grease(self) -> None:
        self.assertNotAcceptedAs(
            product(
                "Bacon Up Bacon Grease 14 oz Tub, Fry, Cook, Bake, Griddle & Cast Iron Seasoning, Rendered Animal Fat",
                category_path="Home Page/Food/Pantry/Cooking oils & vinegar/Cooking oils",
                htc_code="F000000H",
                consensus_pid="Bacon Grease",
                consensus_canonical="Pantry > Sauces & Salsas > Bacon Grease",
                bridge_status="title_match",
            ),
            "Seasoning",
        )

    def test_extracts_cookies_mixes_and_in_oil_are_not_embedded_identities(self) -> None:
        self.assertNotAcceptedAs(
            product(
                "McCormick Non-GMO Gluten Free Pure Lemon Extract, 2.0 fl oz Box",
                category_path="Home Page/Food/Pantry/Herbs, spices & seasoning mixes/Extracts",
                htc_code="E200002B",
                consensus_pid="Extract",
                consensus_canonical="Pantry > Baking Extracts",
                bridge_status="title_match",
            ),
            "Seasoning",
        )
        self.assertNotAcceptedAs(
            product(
                "OREO Thins Mint Creme Chocolate Sandwich Cookies, 9.21 oz",
                category_path="Home Page/Food/Snacks/Cookies",
                htc_code="8000000A",
                consensus_pid="Sandwich Cookies",
                consensus_canonical="Bakery > Cookies > Sandwich Cookies",
                bridge_status="title_match",
            ),
            "Sandwich",
        )
        self.assertNotAcceptedAs(
            product(
                "Fleischmann's Simply Homemade Corn Bread Baking Mix, 15 oz",
                category_path="Home Page/Food/Baking/Easy to Make/Baking Mixes",
                htc_code="8000000A",
                consensus_pid="Baking Mix",
                consensus_canonical="Pantry > Baking Mixes > Baking Mix",
                bridge_status="title_match",
            ),
            "Bread",
        )
        self.assertNotAcceptedAs(
            product(
                "King Oscar Wild Caught Skinless & Boneless Mackerel in Olive Oil 4.05 oz",
                category_path="Home Page/Food/Pantry/Canned Seafood",
                htc_code="4000000A",
                consensus_pid="Mackerel",
                consensus_canonical="Meat & Seafood > Fish > Mackerel",
                bridge_status="title_match",
            ),
            "Olive Oil",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
