from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
MAPPER = ROOT / "recipe_mapper" / "v1"
if str(MAPPER) not in sys.path:
    sys.path.insert(0, str(MAPPER))

from htc.encoder import encode
from planner.form_facet_audit import (
    concept_sku_class_findings,
    gram_bridge_findings,
    line_sku_findings,
)
from planner.line_identity_overrides import line_canonical_path_override


class FormFacetAuditTests(unittest.TestCase):
    def test_blueberry_bagel_requires_blueberry_package(self) -> None:
        findings = line_sku_findings(
            {"display": "2 blueberry bagels", "ingredient_item": "blueberry bagels"},
            "Bakery > Bagels|G00G000T",
            ["Kroger Plain Bagels"],
        )

        self.assertTrue(any(f.issue_type == "wrong_facet" for f in findings))

    def test_blueberry_bagel_accepts_blueberry_package(self) -> None:
        findings = line_sku_findings(
            {"display": "2 blueberry bagels", "ingredient_item": "blueberry bagels"},
            "Bakery > Bagels|G00G000T",
            ["Kroger Blueberry Bagels"],
        )

        self.assertFalse(findings)

    def test_generic_ham_rejects_lunchmeat(self) -> None:
        findings = line_sku_findings(
            {"display": "1 cup cooked ham", "ingredient_item": "ham"},
            "Meat & Seafood > Ham|2401000E",
            ["Buddig Black Forest Ham Lunch Meat 2oz"],
        )

        self.assertTrue(any(f.issue_type == "wrong_form" for f in findings))

    def test_deli_ham_allows_lunchmeat(self) -> None:
        findings = line_sku_findings(
            {"display": "4 slices deli ham", "ingredient_item": "deli ham"},
            "Meal > Sandwiches > Lunch Meat|H0000013",
            ["Buddig Black Forest Ham Lunch Meat 2oz"],
        )

        self.assertFalse(findings)

    def test_smoked_ham_slices_allow_deli_sliced_package(self) -> None:
        findings = line_sku_findings(
            {"display": "6 slices smoked ham, cooked", "ingredient_item": "smoked ham"},
            "Meat & Seafood > Ham > Smoked Ham|2401841A",
            ["Kroger® Smoked Ham Deli Sliced"],
        )

        self.assertFalse(findings)

    def test_sliced_ham_rejects_lunch_kit(self) -> None:
        findings = line_sku_findings(
            {"display": "4 slices ham", "ingredient_item": "ham"},
            "Meat & Seafood > Ham|2401000E",
            ["Armour LunchMaker Ham Smalls"],
        )

        self.assertTrue(any(f.issue_type == "wrong_form" for f in findings))

    def test_sliced_ham_routes_to_lunch_meat(self) -> None:
        self.assertEqual(
            line_canonical_path_override("ham", "4 slices ham"),
            "Meal > Sandwiches > Lunch Meat",
        )

    def test_deli_corned_beef_routes_to_lunch_meat(self) -> None:
        self.assertEqual(
            line_canonical_path_override(
                "corned beef",
                "4 ounces deli corned beef, thinly sliced",
            ),
            "Meal > Sandwiches > Lunch Meat",
        )

    def test_corned_beef_hash_does_not_route_to_lunch_meat(self) -> None:
        self.assertIsNone(
            line_canonical_path_override("corned beef", "1 can corned beef hash")
        )

    def test_tomato_path_override_is_not_planner_regex(self) -> None:
        self.assertIsNone(
            line_canonical_path_override(
                "tomatoes",
                "2 medium tomatoes, coarsely chopped",
            )
        )

    def test_fresh_tomato_varieties_encode_to_fresh_form(self) -> None:
        examples = [
            ("tomato", "1 tomato, sliced"),
            ("roma tomato", "1 Roma tomato, seeds and gel removed, chopped"),
            ("roma tomatoes", "1-2 Roma tomatoes, chopped"),
            ("plum tomatoes", "3 plum tomatoes, thinly sliced"),
            ("cherry tomatoes", "1/2 cup cherry tomatoes, quartered"),
        ]
        for item, display in examples:
            with self.subTest(item=item, display=display):
                self.assertEqual(
                    encode(
                        "",
                        description=display,
                        extra=item,
                        food_name=item,
                        canonical_path="",
                        identity_mode=False,
                    ).code,
                    "6701100*",
                )

    def test_canned_tomatoes_do_not_encode_as_fresh_form(self) -> None:
        self.assertNotEqual(
            encode(
                "",
                description="1 can (14.5 oz) diced tomatoes",
                extra="tomatoes",
                food_name="tomatoes",
                canonical_path="",
                identity_mode=False,
            ).code,
            "6701100*",
        )

    def test_head_lettuce_grams_must_not_be_100g(self) -> None:
        findings = gram_bridge_findings({
            "display": "1 head lettuce, leaves separated",
            "ingredient_item": "lettuce",
            "grams_resolved": "100",
        })

        self.assertTrue(any(f.issue_type == "bad_grams" for f in findings))

    def test_cups_of_shredded_head_lettuce_are_not_head_unit(self) -> None:
        self.assertFalse(gram_bridge_findings({
            "display": "4 cups head lettuce, shredded",
            "ingredient_item": "head lettuce",
            "unit": "cup",
            "grams_resolved": "112",
        }))

    def test_shredded_lettuce_routes_to_shredded_path(self) -> None:
        self.assertEqual(
            line_canonical_path_override("lettuce", "2 cups lettuce, shredded"),
            "Produce > Vegetables > Shredded Lettuce",
        )

    def test_lettuce_leaves_do_not_route_to_shredded_path(self) -> None:
        self.assertEqual(
            line_canonical_path_override("lettuce", "4 lettuce leaves"),
            "Produce > Vegetables > Lettuce",
        )

    def test_lettuce_leaves_reject_shredded_package(self) -> None:
        findings = line_sku_findings(
            {"display": "4 lettuce leaves", "ingredient_item": "lettuce"},
            "Produce > Vegetables > Lettuce|6010000S",
            ["Marketside Fresh Shredded Iceberg Lettuce, 8 oz Bag"],
        )

        self.assertTrue(any(f.issue_type == "wrong_form" for f in findings))

    def test_neufchatel_routes_to_neufchatel_path(self) -> None:
        self.assertEqual(
            line_canonical_path_override("neufchatel cheese", "8 ounces neufchatel cheese"),
            "Dairy > Cheese > Neufchatel",
        )

    def test_one_pound_bridge(self) -> None:
        self.assertFalse(gram_bridge_findings({
            "display": "1 lb bacon",
            "ingredient_item": "bacon",
            "qty": "1",
            "unit": "lb",
            "grams_resolved": "454",
        }))
        self.assertTrue(gram_bridge_findings({
            "display": "1 lb bacon",
            "ingredient_item": "bacon",
            "qty": "1",
            "unit": "lb",
            "grams_resolved": "900",
        }))

    def test_pound_display_beats_parenthetical_slice_count(self) -> None:
        self.assertFalse(gram_bridge_findings({
            "display": "1 lb thick-sliced bacon (about 12 to 15 slices)",
            "ingredient_item": "thick-sliced bacon",
            "qty": "12",
            "unit": "lb",
            "grams_resolved": "454",
        }))

    def test_total_weight_range_is_a_total_not_each_piece(self) -> None:
        bad = gram_bridge_findings({
            "display": "6 boneless skinless chicken breasts, about 1.5 to 2 pounds total",
            "ingredient_item": "boneless skinless chicken breasts",
            "qty": "1.5",
            "unit": "",
            "grams_resolved": "226.75",
        })
        self.assertTrue(any(f.issue_type == "bad_grams" for f in bad))

        good = gram_bridge_findings({
            "display": "6 boneless skinless chicken breasts, about 1.5 to 2 pounds total",
            "ingredient_item": "boneless skinless chicken breasts",
            "qty": "1.5",
            "unit": "",
            "grams_resolved": "907",
        })
        self.assertFalse(good)

    def test_fractional_pound_bridge(self) -> None:
        examples = [
            ("1 1/2 lbs ground beef", "680.39"),
            ("1/2 lb mushrooms, sliced", "227"),
            ("1⁄4 lb shredded cheddar cheese", "113"),
            ("3/4 pound boneless skinless chicken breast", "340.2"),
        ]
        for display, grams in examples:
            with self.subTest(display=display):
                self.assertFalse(gram_bridge_findings({
                    "display": display,
                    "ingredient_item": display,
                    "qty": "1",
                    "unit": "lb",
                    "grams_resolved": grams,
                }))

    def test_low_salt_seasoning_is_not_a_salt_teaspoon_audit(self) -> None:
        self.assertFalse(gram_bridge_findings({
            "display": "1/2 teaspoon aha herb seasoning or low-salt seasoning",
            "ingredient_item": "aha herb seasoning",
            "qty": "0.5",
            "unit": "teaspoon",
            "grams_resolved": "1.43",
        }))

    def test_lean_pork_rejects_sausage_package(self) -> None:
        findings = line_sku_findings(
            {"display": "3/4 lb lean pork, diced", "ingredient_item": "lean pork"},
            "Meat & Seafood > Pork|2109008=",
            ["Kroger® Mild Pork Sausage Roll"],
        )

        self.assertTrue(any(f.issue_type == "wrong_form" for f in findings))

    def test_chorizo_rejects_generic_pork_sausage_package(self) -> None:
        findings = line_sku_findings(
            {"display": "1 lb chorizo sausage, casings removed", "ingredient_item": "chorizo sausage"},
            "Meat & Seafood > Sausage > Chorizo Sausage|2451000Z",
            ["Kroger® Maple Pork Sausage"],
        )

        self.assertTrue(any(f.issue_type == "wrong_form" for f in findings))

    def test_chorizo_accepts_chorizo_package(self) -> None:
        findings = line_sku_findings(
            {"display": "1 lb chorizo sausage, casings removed", "ingredient_item": "chorizo sausage"},
            "Meat & Seafood > Sausage > Chorizo Sausage|2451000Z",
            ["Kroger® Chorizo Ground Sausage"],
        )

        self.assertFalse(findings)

    def test_customer_line_wrong_class_examples_are_blockers(self) -> None:
        examples = [
            (
                "Dairy > Cheese > Cheddar|1101000H",
                ["Sargento® Sharp Natural Cheddar Cheese Snack Sticks, 12-Count"],
            ),
            (
                "Produce > Vegetables > Baby Carrots|6102000N",
                ["Libby's® Peas & Carrots 4-4 oz. Cups"],
            ),
            (
                "Pantry > Oil > Vegetable Oil|B00W600V",
                ["Blue Bonnet Vegetable Oil Sticks"],
            ),
            (
                "Pantry > Sweeteners > Sugar > Brown Sugar|C00J000W",
                ["Madhava Organic Light Blue Agave Nectar"],
            ),
            (
                "Produce > Vegetables > Avocado|6018000R",
                ["Alafia Grape Leaves, 16 oz"],
            ),
            (
                "Dairy > Cream > Creme Fraiche|116B0001",
                ["McCormick Strawberries & Cream Finishing Sugar, 3.16 oz Bottle"],
            ),
            (
                "Meat & Seafood > Bacon|24020000",
                ["MorningStar Farms® Veggie Breakfast Original Meatless Bacon Strips"],
            ),
            (
                "Pantry > Spices & Seasonings > Oregano|E304400U",
                ["Soeos Whole Bay Leaves, Dried for Soups"],
            ),
            (
                "Produce > Fruit > Limes|7235000=",
                ["Ocean Spray® Citrus Splash - Grapefruit, Lemon and Lime 50.7 fl oz Bottle"],
            ),
            (
                "Pantry > Sauces & Salsas > Hot Pepper Sauce|F69N600Z",
                ["Knorr Professional Hollandaise Sauce Mix"],
            ),
            (
                "Frozen > Vegetables > Pierogies|6100000C",
                ["Great Value Buttery Complete Potatoes, 4 oz, Pouch"],
            ),
            (
                "Meat & Seafood > Pork|2109000V",
                ["Kroger® Mild Pork Sausage Roll"],
            ),
            (
                "Meat & Seafood > Sausage > Chorizo Sausage|2451000Z",
                ["Kroger® Maple Pork Sausage"],
            ),
        ]
        for concept_key, package_names in examples:
            with self.subTest(concept_key=concept_key):
                findings = concept_sku_class_findings(concept_key, package_names)
                self.assertTrue(any(f.issue_type == "wrong_class" for f in findings))

    def test_customer_line_wrong_class_examples_allow_fixed_products(self) -> None:
        examples = [
            ("Dairy > Cheese > Cheddar|1101005P", ["Great Value Mild Cheddar Shredded Cheese, 32 oz Bag"]),
            ("Produce > Vegetables > Baby Carrots|6104000Y", ["Kroger® Cut and Peeled Baby Carrots"]),
            ("Pantry > Oil > Vegetable Oil|B00W600V", ["Great Value Vegetable Oil, 1 Gallon Bottle"]),
            ("Pantry > Sweeteners > Sugar > Brown Sugar|C00K000E", ["Great Value Light Brown Sugar, 32 oz"]),
            ("Produce > Vegetables > Avocado|60161003", ["Fresh Medium Ripe Avocado"]),
            ("Meat & Seafood > Bacon|24020000", ["Smithfield® Hometown Original Bacon"]),
            ("Pantry > Spices & Seasonings > Oregano|E303000R", ["Great Value Oregano Leaves, 0.87 oz"]),
            ("Produce > Fruit > Limes|7237100*", ["Fresh Limes - Each"]),
            ("Meat & Seafood > Pork|2109000V", ["Smithfield® Pork Tenderloin, 18.4 oz"]),
            ("Meat & Seafood > Sausage > Chorizo Sausage|2451000Z", ["Kroger® Chorizo Ground Sausage"]),
        ]
        for concept_key, package_names in examples:
            with self.subTest(concept_key=concept_key):
                self.assertFalse(concept_sku_class_findings(concept_key, package_names))


if __name__ == "__main__":
    unittest.main()
