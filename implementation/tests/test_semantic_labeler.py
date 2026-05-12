import sys
import unittest
from pathlib import Path


ROOT = Path("/Users/jamiebarton/Desktop/esha_audit_bundle")
V2 = ROOT / "retail_mapper" / "v2"
if str(V2) not in sys.path:
    sys.path.insert(0, str(V2))

import semantic_labeler as labeler  # noqa: E402


class SemanticLabelerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.taxonomy = {
            "Beverage > Fruit-based Drinks > Juice",
            "Beverage > Fruit-based Drinks > Juice > Grapefruit",
            "Beverage > Seltzer",
            "Beverage > Seltzer > Grapefruit",
            "Beverage > Tea",
            "Beverage > Tea > Grapefruit",
            "Produce > Fruit",
            "Produce > Fruit > Apple",
            "Snack > Candy",
            "Snack > Candy > Gummy",
            "Frozen > Ice Cream",
            "Frozen > Ice Cream > Ice Cream",
            "Frozen > Ice Cream > Ice Cream Sandwich",
            "Frozen > Ice Cream > Gelato",
            "Meal > Pizza",
            "Meal > Pizza > Pizza",
            "Pantry > Sauces & Salsas",
            "Pantry > Sauces & Salsas > Pizza Sauce",
            "Bakery > Crust & Dough",
            "Bakery > Crust & Dough > Pizza Crust",
            "Pantry > Baking > Mix",
            "Pantry > Baking > Mix > Pizza Crust Mix",
        }

    def test_missing_clementine_beverage_becomes_mint_under_juice_parent(self) -> None:
        row = {
            "fdc_id": "564094",
            "title": "ANTIOXIDANT INFUSION COSTA RICA CLEMENTINE",
            "branded_food_category": "Other Drinks",
            "current_esha_desc": "Juice Drink, sparkling, clementine",
            "ing_top5": "Filtered Water | Orange Juice Concentrate | Natural Flavors",
            "retail_leaf": "Beverage > Juice",
        }

        rec = labeler.classify_row(row, self.taxonomy)

        self.assertEqual(rec.parent_path, "Beverage > Fruit-based Drinks > Juice")
        self.assertEqual(rec.proposed_path, "Beverage > Fruit-based Drinks > Juice > Clementine")
        self.assertTrue(rec.mint_required)
        self.assertTrue(rec.parent_exists)

    def test_existing_grapefruit_juice_path_is_reused(self) -> None:
        row = {
            "fdc_id": "g1",
            "title": "RUBY RED GRAPEFRUIT JUICE",
            "branded_food_category": "Fruit & Vegetable Juice",
            "current_esha_desc": "Juice, grapefruit, pulp free",
            "ing_top5": "Grapefruit Juice",
            "retail_leaf": "Beverage > Juice",
        }

        rec = labeler.classify_row(row, self.taxonomy)

        self.assertEqual(rec.existing_path, "Beverage > Fruit-based Drinks > Juice > Grapefruit")
        self.assertFalse(rec.mint_required)

    def test_candy_flavor_list_does_not_become_beverage_grapefruit(self) -> None:
        row = {
            "fdc_id": "c1",
            "title": "GUMMY BEARS CANDY, LEMON, PINK GRAPEFRUIT, WATERMELON",
            "branded_food_category": "Candy",
            "current_esha_desc": "Candy, gummy bears",
            "ing_top5": "Sugar | Corn Syrup",
            "retail_leaf": "Snack > Candy",
        }

        rec = labeler.classify_row(row, self.taxonomy)

        self.assertEqual(rec.proposed_path, "Snack > Candy > Gummy")
        self.assertEqual(rec.supercategory, "Snack")
        self.assertFalse(rec.proposed_path.startswith("Beverage"))

    def test_honey_crisp_apples_are_not_reclassified_as_meal_crisp(self) -> None:
        row = {
            "fdc_id": "a1",
            "title": "WELCH'S, DRIED HONEY CRISP APPLES",
            "branded_food_category": "Wholesome Snacks",
            "current_esha_desc": "Apple, dried",
            "ing_top5": "Apples",
            "retail_leaf": "Produce > Apples > Welch",
            "brand_name": "WELCH'S",
        }

        rec = labeler.classify_row(row, self.taxonomy)

        self.assertEqual(rec.proposed_path, "Produce > Fruit > Apple")
        self.assertIn("crisp_kept_as_variety_not_dish", rec.notes)
        self.assertNotEqual(rec.supercategory, "Meal")

    def test_spaghettios_normalize_to_spaghetti_rings_mint(self) -> None:
        row = {
            "fdc_id": "s1",
            "title": "Campbell's SpaghettiOs Organic Original, 15.8 oz.",
            "branded_food_category": "Dough Based Products / Meals",
            "current_esha_desc": "Dish, carrot, with cheddar, puree, frozen",
            "ing_top5": "Tomato Puree | Pasta",
            "retail_leaf": "Produce > Tomato > Organic",
        }

        rec = labeler.classify_row(row, self.taxonomy)

        self.assertEqual(rec.proposed_path, "Meal > Pasta Dishes > Spaghetti Rings")
        self.assertTrue(rec.mint_required)
        self.assertIn("spaghettios_normalized_to_spaghetti_rings", rec.notes)

    def test_ice_cream_flavor_and_light_stay_filters(self) -> None:
        row = {
            "fdc_id": "i1",
            "title": "LIGHT VANILLA ICE CREAM",
            "branded_food_category": "Ice Cream & Frozen Yogurt",
            "current_esha_desc": "Ice cream, light, vanilla",
            "retail_leaf": "Frozen > Ice Cream > Light Ice Cream > Vanilla",
        }

        rec = labeler.classify_row(row, self.taxonomy)

        self.assertEqual(rec.category_path, "Frozen > Ice Cream")
        self.assertEqual(rec.head, "Ice Cream")
        self.assertEqual(rec.filter_attributes["flavor"], "vanilla")
        self.assertEqual(rec.filter_attributes["fat"], "light")
        self.assertNotIn("Vanilla", rec.head)
        self.assertNotEqual(rec.head, "Light Ice Cream")

    def test_ice_cream_sandwich_promotes_form_not_flavor(self) -> None:
        row = {
            "fdc_id": "i2",
            "title": "VANILLA ICE CREAM SANDWICHES",
            "branded_food_category": "Ice Cream & Frozen Yogurt",
            "current_esha_desc": "Ice cream sandwich, vanilla",
            "retail_leaf": "Frozen > Ice Cream > Vanilla > Sandwich",
        }

        rec = labeler.classify_row(row, self.taxonomy)

        self.assertEqual(rec.category_path, "Frozen > Ice Cream")
        self.assertEqual(rec.head, "Ice Cream Sandwich")
        self.assertEqual(rec.filter_attributes["flavor"], "vanilla")
        self.assertIn("form_promoted_to_head", rec.notes)

    def test_gelato_keeps_flavor_as_filter(self) -> None:
        row = {
            "fdc_id": "i3",
            "title": "AMARETTO DARK CHERRY GELATO",
            "branded_food_category": "Ice Cream & Frozen Yogurt",
            "current_esha_desc": "Gelato, cherry",
            "retail_leaf": "Frozen > Ice Cream > Gelato > Dark > Cherry",
        }

        rec = labeler.classify_row(row, self.taxonomy)

        self.assertEqual(rec.head, "Gelato")
        self.assertIn("cherry", rec.filter_attributes["flavor"])
        self.assertNotIn("Cherry", rec.head)

    def test_pizza_toppings_stay_filters(self) -> None:
        row = {
            "fdc_id": "p1",
            "title": "PEPPERONI MUSHROOM THIN CRUST PIZZA",
            "branded_food_category": "Pizza",
            "current_esha_desc": "Pizza, pepperoni",
            "retail_leaf": "Meal > Composite Dishes > Pizza > Pepperoni > Mushroom",
        }

        rec = labeler.classify_row(row, self.taxonomy)

        self.assertEqual(rec.category_path, "Meal > Pizza")
        self.assertEqual(rec.head, "Pizza")
        self.assertIn("pepperoni", rec.filter_attributes["toppings"])
        self.assertIn("mushroom", rec.filter_attributes["toppings"])
        self.assertIn("thin", rec.filter_attributes["crust"])
        self.assertNotIn("Pepperoni", rec.head)

    def test_pizza_sauce_is_not_a_meal(self) -> None:
        row = {
            "fdc_id": "p2",
            "title": "CLASSIC PIZZA SAUCE",
            "branded_food_category": "Prepared Pasta & Pizza Sauces",
            "current_esha_desc": "Sauce, pizza",
            "retail_leaf": "Meal > Composite Dishes > Pizza",
        }

        rec = labeler.classify_row(row, self.taxonomy)

        self.assertEqual(rec.category_path, "Pantry > Sauces & Salsas")
        self.assertEqual(rec.head, "Pizza Sauce")
        self.assertNotEqual(rec.retail_type, "composite_meal")
        self.assertIn("pizza_adjacent_sauce_not_meal", rec.notes)

    def test_pizza_lunch_combination_is_not_pizza_sauce(self) -> None:
        row = {
            "fdc_id": "p2b",
            "title": "EXTRA CHEESY PIZZA MOZZARELLA CHEESE PRODUCT, PIZZA CRUSTS, PIZZA SAUCE",
            "branded_food_category": "Lunch Snacks & Combinations",
            "current_esha_desc": "Lunch kit, pizza",
            "retail_leaf": "Pantry > Sauces & Salsas > Sauce",
        }

        rec = labeler.classify_row(row, self.taxonomy)

        self.assertEqual(rec.category_path, "Meal > Meal Kits")
        self.assertEqual(rec.head, "Pizza Lunch Kit")
        self.assertNotEqual(rec.head, "Pizza Sauce")
        self.assertIn("pizza_lunch_kit_not_single_pizza_or_sauce", rec.notes)

    def test_pizza_crust_mix_is_not_a_pizza_meal(self) -> None:
        row = {
            "fdc_id": "p3",
            "title": "GLUTEN FREE PIZZA CRUST MIX",
            "branded_food_category": "Pizza Mixes & Other Dry Dinners",
            "current_esha_desc": "Pizza crust mix",
            "retail_leaf": "Meal > Composite Dishes > Pizza",
        }

        rec = labeler.classify_row(row, self.taxonomy)

        self.assertEqual(rec.category_path, "Pantry > Baking > Mix")
        self.assertEqual(rec.head, "Pizza Crust Mix")
        self.assertNotEqual(rec.retail_type, "composite_meal")

    def test_plural_pizza_crusts_are_not_a_pizza_meal(self) -> None:
        row = {
            "fdc_id": "p4",
            "title": "VICOLO, CORN MEAL PIZZA CRUSTS",
            "branded_food_category": "Cake, Cookie & Cupcake Mixes",
            "current_esha_desc": "Pizza crust",
            "retail_leaf": "Meal > Composite Dishes > Pizza",
        }

        rec = labeler.classify_row(row, self.taxonomy)

        self.assertEqual(rec.category_path, "Pantry > Baking > Mix")
        self.assertEqual(rec.head, "Pizza Crust Mix")
        self.assertNotEqual(rec.retail_type, "composite_meal")

    def test_corn_meal_is_not_a_meal(self) -> None:
        row = {
            "fdc_id": "m1",
            "title": "YELLOW CORN MEAL",
            "branded_food_category": "Flours & Corn Meal",
            "current_esha_desc": "Cornmeal",
            "retail_leaf": "Pantry > Baking > Flour > Corn",
        }

        rec = labeler.classify_row(row, self.taxonomy)

        self.assertNotEqual(rec.supercategory, "Meal")
        self.assertFalse(labeler.is_meal_context(row))

    def test_meal_bar_is_not_a_composite_meal(self) -> None:
        row = {
            "fdc_id": "m2",
            "title": "CHOCOLATE CARAMEL PROTEIN MEAL BARS",
            "branded_food_category": "Snack, Energy & Granola Bars",
            "current_esha_desc": "Snack bar",
            "retail_leaf": "Snack > Bars > Bar",
        }

        rec = labeler.classify_row(row, self.taxonomy)

        self.assertNotEqual(rec.supercategory, "Meal")
        self.assertFalse(labeler.is_meal_context(row))

    def test_matzo_meal_is_not_a_composite_meal(self) -> None:
        row = {
            "fdc_id": "m3",
            "title": "WHOLE WHEAT MATZO MEAL",
            "branded_food_category": "Cake, Cookie & Cupcake Mixes",
            "current_esha_desc": "Matzo meal",
            "retail_leaf": "Pantry > Bread > Matzo",
        }

        rec = labeler.classify_row(row, self.taxonomy)

        self.assertNotEqual(rec.supercategory, "Meal")
        self.assertFalse(labeler.is_meal_context(row))


if __name__ == "__main__":
    unittest.main()
