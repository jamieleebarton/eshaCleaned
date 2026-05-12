#!/usr/bin/env python3
from __future__ import annotations

import unittest
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from title_parser import AxisLexicon, parse_row, repo_root


class TitleParserRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.lexicon = AxisLexicon(repo_root())

    def parse(self, title: str, branded_food_category: str = "") -> dict[str, object]:
        return parse_row(
            {"product_description": title, "branded_food_category": branded_food_category},
            self.lexicon,
        )

    def test_pumpkin_spice_almondmilk_routes_to_plant_milk(self) -> None:
        parsed = self.parse("HINT OF PUMPKIN SPICE ALMONDMILK")
        self.assertEqual(parsed["retail_type"], "single")
        self.assertEqual(parsed["form"], "milk")
        self.assertEqual(parsed["category_group"], "Plant-based Milk")
        self.assertEqual(parsed["category"], "Almond Milk")
        self.assertEqual(parsed["flavor"], "pumpkin spice")

    def test_almond_juice_does_not_route_to_almond_milk(self) -> None:
        parsed = self.parse("LEMON GINGER COLD-PRESSED ALMOND JUICE")
        self.assertEqual(parsed["form"], "juice")
        self.assertEqual(parsed["primary_food"], "almond")
        self.assertEqual(parsed["category_group"], "Fruit-based Drinks")
        self.assertIn("Juice > Almond", parsed["retail_leaf"])
        self.assertEqual(parsed["prep_state"], "cold pressed")

    def test_almond_protein_powder_routes_to_protein_powder(self) -> None:
        parsed = self.parse("ALMOND PROTEIN POWDER, UNFLAVORED")
        self.assertEqual(parsed["form"], "protein powder")
        self.assertEqual(parsed["primary_food"], "almond")
        self.assertEqual(parsed["category"], "Almond Protein")
        self.assertIn("Protein Powders", parsed["retail_leaf"])

    def test_apple_noodle_kugel_is_composite_dish(self) -> None:
        parsed = self.parse("APPLE NOODLE KUGEL")
        self.assertEqual(parsed["retail_type"], "composite_dish")
        self.assertEqual(parsed["dish_type"], "kugel")
        self.assertIn("Composite Dishes > Kugel", parsed["retail_leaf"])

    def test_fruit_and_spread_with_title_is_combo_pack(self) -> None:
        parsed = self.parse("APPLE SLICES WITH PEANUT BUTTER")
        self.assertEqual(parsed["retail_type"], "combo_pack")
        self.assertEqual(parsed["pack_format"], "dipper")
        self.assertEqual(parsed["components"], ["apple slices", "peanut butter"])

    def test_hummus_with_pita_chips_is_combo_pack_not_composite(self) -> None:
        parsed = self.parse("HUMMUS WITH PITA CHIPS")
        self.assertEqual(parsed["retail_type"], "combo_pack")
        self.assertEqual(parsed["components"], ["hummus", "pita chips"])
        self.assertNotIn("Composite Dishes", parsed["retail_leaf"])

    def test_coffee_drink_with_almond_milk_is_single_beverage_not_combo_pack(self) -> None:
        parsed = self.parse("CARAMEL PREMIUM ICED COFFEE DRINK WITH ALMOND MILK, CARAMEL", "Other Drinks")
        self.assertEqual(parsed["retail_type"], "single")
        self.assertEqual(parsed["supercategory"], "Beverage")
        self.assertIn(parsed["form"], {"coffee", "drink"})

    def test_protein_shake_with_oats_is_single_beverage_not_combo_pack(self) -> None:
        parsed = self.parse("APPLE CINNAMON FLAVORED HIGH PROTEIN SHAKE WITH OATS, APPLE CINNAMON")
        self.assertEqual(parsed["retail_type"], "single")
        self.assertEqual(parsed["supercategory"], "Beverage")
        self.assertEqual(parsed["form"], "shake")

    def test_cranberries_sweetened_with_apple_juice_are_not_combo_or_juice(self) -> None:
        parsed = self.parse("VINCENT FAMILY, DRIED CRANBERRIES WITH UNSWEETENED APPLE JUICE")
        self.assertEqual(parsed["retail_type"], "single")
        self.assertEqual(parsed["category_group"], "Fruit")
        self.assertNotEqual(parsed["form"], "juice")

    def test_refried_beans_with_lime_juice_are_not_combo_or_juice(self) -> None:
        parsed = self.parse("REFRIED BLACK BEANS WITH LIME JUICE")
        self.assertEqual(parsed["retail_type"], "single")
        self.assertEqual(parsed["category_group"], "Legume")
        self.assertNotEqual(parsed["form"], "juice")

    def test_coffee_cake_with_icing_is_cake_not_combo_or_coffee(self) -> None:
        parsed = self.parse("COFFEE CAKE WITH CREAM CHEESE ICING")
        self.assertEqual(parsed["retail_type"], "single")
        self.assertEqual(parsed["form"], "cake")
        self.assertEqual(parsed["category_group"], "Cake")
        self.assertNotEqual(parsed["category_group"], "Combo Packs")

    def test_green_tea_extract_gum_is_gum_not_combo_or_tea(self) -> None:
        parsed = self.parse("SUGAR FREE HARD MINTS CLEAN BREATH ARTIFICIAL FLAVOR PEPPERMINT WITH GREEN TEA EXTRACT, PEPPERMINT")
        self.assertEqual(parsed["retail_type"], "single")
        self.assertIn(parsed["form"], {"gum", "mints"})
        self.assertIn(parsed["category_group"], {"Candy", "Mints"})
        self.assertNotEqual(parsed["category_group"], "Combo Packs")

    def test_chai_latte_cupcake_mix_is_mix_not_combo_or_latte(self) -> None:
        parsed = self.parse("CHAI LATTE CUPCAKE MIX WITH CINNAMON CHIPS, CHAI SPICE CAKE, & VANILLA BEAN FROSTING MIX, CHAI LATTE")
        self.assertEqual(parsed["retail_type"], "single")
        self.assertEqual(parsed["form"], "mix")
        self.assertNotEqual(parsed["category_group"], "Combo Packs")

    def test_cookies_and_cream_high_protein_shake_stays_shake(self) -> None:
        parsed = self.parse("COOKIES & CREAM HIGH PROTEIN SHAKE, COOKIES & CREAM")
        self.assertEqual(parsed["retail_type"], "single")
        self.assertEqual(parsed["form"], "shake")
        self.assertEqual(parsed["supercategory"], "Beverage")

    def test_fruit_juice_sweetened_cereal_is_cereal_not_juice(self) -> None:
        parsed = self.parse("FRUIT JUICE SWEETENED MILLET RICE CEREAL WITH OATBRAN")
        self.assertEqual(parsed["retail_type"], "single")
        self.assertEqual(parsed["form"], "cereal")
        self.assertNotEqual(parsed["category_group"], "Fruit-based Drinks")

    def test_irish_soda_bread_is_bread_not_soda(self) -> None:
        parsed = self.parse("IRISH SODA BREAD WITH RAISINS, IRISH SODA")
        self.assertEqual(parsed["retail_type"], "single")
        self.assertEqual(parsed["form"], "bread")
        self.assertNotEqual(parsed["supercategory"], "Beverage")

    def test_baked_beans_with_brown_sugar_stays_beans(self) -> None:
        parsed = self.parse("COUNTRY STYLE BAKED BEANS WITH BROWN SUGAR AND BACON")
        self.assertEqual(parsed["retail_type"], "single")
        self.assertEqual(parsed["primary_food"], "beans")
        self.assertEqual(parsed["category_group"], "Legume")

    def test_shake_n_pour_pancake_mix_is_pancake_mix_not_shake(self) -> None:
        parsed = self.parse("SHAKE N POUR PANCAKE MIX, BUTTERMILK")
        self.assertEqual(parsed["retail_type"], "single")
        self.assertEqual(parsed["primary_food"], "pancake")
        self.assertEqual(parsed["form"], "mix")
        self.assertNotEqual(parsed["supercategory"], "Beverage")

    def test_coffee_bar_is_bar_not_coffee(self) -> None:
        parsed = self.parse("LAVENDER VANILLA COFFEE BAR, LAVENDER VANILLA")
        self.assertEqual(parsed["retail_type"], "single")
        self.assertEqual(parsed["primary_food"], "bar")
        self.assertEqual(parsed["form"], "bar")
        self.assertEqual(parsed["supercategory"], "Snack")

    def test_smoothie_with_chia_keeps_with_as_inclusion(self) -> None:
        parsed = self.parse("ACAI BLUEBERRY WATERMELON SMOOTHIE WITH CHIA SEEDS")
        self.assertEqual(parsed["retail_type"], "single")
        self.assertEqual(parsed["form"], "smoothie")
        self.assertEqual(parsed["flavor_blend"], ["acai", "blueberry", "watermelon"])
        self.assertEqual(parsed["inclusions"], ["chia seeds"])

    def test_fully_cooked_bacon_keeps_prep_state(self) -> None:
        parsed = self.parse("FULLY COOKED BACON")
        self.assertEqual(parsed["retail_type"], "single")
        self.assertEqual(parsed["primary_food"], "bacon")
        self.assertEqual(parsed["prep_state"], "fully cooked")
        self.assertIn("Fully Cooked", parsed["retail_leaf"])
        self.assertEqual(parsed["needs_review"], [])

    def test_dairy_almond_blend_is_not_plant_milk(self) -> None:
        parsed = self.parse("ORIGINAL DAIRY + ALMOND BLEND MILK")
        self.assertEqual(parsed["form"], "milk")
        self.assertEqual(parsed["category_group"], "Blended Milks")
        self.assertEqual(parsed["category"], "Dairy+Almond")
        self.assertNotEqual(parsed["category_group"], "Plant-based Milk")

    def test_almond_beverage_with_plant_milk_evidence_routes_to_almond_milk(self) -> None:
        parsed = parse_row(
            {
                "product_description": "VANILLA UNSWEETENED ALMOND BEVERAGE, VANILLA",
                "branded_food_category": "Plant Based Milk",
                "fixy_category": "Plant Based Milk",
                "v6_fndds_description": "Almond milk, sweetened",
                "best_esha_description": "Almond Milk, Almond Breeze, vanilla, unsweetened",
            },
            self.lexicon,
        )
        self.assertEqual(parsed["form"], "milk")
        self.assertEqual(parsed["category_group"], "Plant-based Milk")
        self.assertEqual(parsed["category"], "Almond Milk")
        self.assertEqual(parsed["retail_leaf"], "Beverage > Plant-based Milk > Almond Milk > Vanilla Unsweetened")

    def test_almond_drink_with_plant_milk_evidence_routes_to_almond_milk(self) -> None:
        parsed = parse_row(
            {
                "product_description": "UNSWEETENED ORGANIC ALMOND DRINK, UNSWEETENED",
                "branded_food_category": "Plant Based Milk",
                "v6_fndds_description": "almond milk unsweetened",
                "best_esha_description": "Almond Milk, Almond Breeze, original, unsweetened",
            },
            self.lexicon,
        )
        self.assertEqual(parsed["form"], "milk")
        self.assertEqual(parsed["category_group"], "Plant-based Milk")
        self.assertEqual(parsed["category"], "Almond Milk")

    def test_coconut_milk_drink_coffee_in_plant_bucket_routes_to_coconut_milk(self) -> None:
        parsed = parse_row(
            {
                "product_description": "THAI COCO, COCONUT MILK DRINK, COFFEE",
                "branded_food_category": "Plant Based Milk",
                "v6_fndds_description": "coconut milk",
                "best_esha_description": "Cream Substitute, coconut milk, original",
            },
            self.lexicon,
        )
        self.assertEqual(parsed["form"], "milk")
        self.assertEqual(parsed["category_group"], "Plant-based Milk")
        self.assertEqual(parsed["category"], "Coconut Milk")

    def test_iced_coffee_drink_with_almond_milk_stays_coffee_drink(self) -> None:
        parsed = parse_row(
            {
                "product_description": "PREMIUM ICED COFFEE DRINK WITH ALMOND MILK, VANILLA",
                "branded_food_category": "Other Drinks",
                "v6_fndds_description": "frozen coffee drink with non-dairy milk",
                "best_esha_description": "Coffee, iced, vanilla",
            },
            self.lexicon,
        )
        self.assertNotEqual(parsed["category_group"], "Plant-based Milk")
        self.assertIn(parsed["form"], {"coffee", "drink"})

    def test_coconut_drink_enhancer_does_not_become_coconut_milk(self) -> None:
        parsed = parse_row(
            {
                "product_description": "PINEAPPLE COCONUT DRINK ENHANCER, PINEAPPLE COCONUT",
                "branded_food_category": "Liquid Water Enhancer",
                "v6_fndds_description": "water enhancer",
                "best_esha_description": "Coconut, milk, fresh",
            },
            self.lexicon,
        )
        self.assertNotEqual(parsed["category_group"], "Plant-based Milk")

    def test_soya_beverage_normalizes_to_soy_milk(self) -> None:
        parsed = parse_row(
            {
                "product_description": "SOYA BEVERAGE",
                "branded_food_category": "Plant Based Milk",
                "v6_fndds_description": "soy milk",
            },
            self.lexicon,
        )
        self.assertEqual(parsed["form"], "milk")
        self.assertEqual(parsed["primary_food"], "soy")
        self.assertEqual(parsed["category_group"], "Plant-based Milk")
        self.assertEqual(parsed["category"], "Soy Milk")

    def test_non_dairy_oat_barista_blend_is_not_dairy_blend(self) -> None:
        parsed = parse_row(
            {
                "product_description": "ORIGINAL OAT BARISTA BLEND OATMILK NON-DAIRY BEVERAGE, ORIGINAL OAT BARISTA BLEND",
                "branded_food_category": "Plant Based Milk",
                "fixy_category": "Plant Based Milk",
                "v6_fndds_description": "oat milk",
            },
            self.lexicon,
        )
        self.assertEqual(parsed["form"], "milk")
        self.assertEqual(parsed["category_group"], "Plant-based Milk")
        self.assertEqual(parsed["category"], "Oat Milk")

    def test_plural_plant_base_beverage_uses_source_milk_evidence(self) -> None:
        parsed = parse_row(
            {
                "product_description": "CARAMEL ALMONDS + CASHEWS FLAVORED NUT-BASED BEVERAGE, CARAMEL ALMONDS + CASHEWS",
                "branded_food_category": "Plant Based Milk",
                "v6_fndds_description": "almond milk sweetened",
            },
            self.lexicon,
        )
        self.assertEqual(parsed["form"], "milk")
        self.assertEqual(parsed["primary_food"], "almond")
        self.assertEqual(parsed["category"], "Almond Milk")

    def test_cream_substitute_beverage_does_not_become_plant_milk_without_trusted_bucket(self) -> None:
        parsed = parse_row(
            {
                "product_description": "RICE NON-DAIRY BEVERAGE, ORIGINAL",
                "branded_food_category": "Milk Additives",
                "v6_fndds_description": "coffee creamer",
                "best_esha_description": "Cream Substitute, non-dairy",
            },
            self.lexicon,
        )
        self.assertNotEqual(parsed["category_group"], "Plant-based Milk")

    def test_chocolate_almond_beverage_with_plant_milk_evidence_is_not_chocolate_candy(self) -> None:
        parsed = parse_row(
            {
                "product_description": "CHOCOLATE FLAVORED PLANT BASED NON-DAIRY ALMOND BEVERAGE, CHOCOLATE",
                "branded_food_category": "Plant Based Milk",
                "v6_fndds_description": "Almond milk, sweetened",
                "best_esha_description": "Almond Milk, chocolate",
            },
            self.lexicon,
        )
        self.assertEqual(parsed["form"], "milk")
        self.assertEqual(parsed["category_group"], "Plant-based Milk")
        self.assertEqual(parsed["category"], "Almond Milk")
        self.assertEqual(parsed["flavor"], "chocolate")

    def test_chocolate_protein_plant_beverage_is_beverage_not_chocolate_candy(self) -> None:
        parsed = parse_row(
            {
                "product_description": "CHOCOLATE PROTEIN & COCONUT PLANT BASED BEVERAGE, CHOCOLATE",
                "branded_food_category": "Energy, Protein & Muscle Recovery Drinks",
                "v6_fndds_description": "Nutritional drink or shake, high protein, ready-to-drink, NFS",
                "best_esha_description": "Shake, nutrition, Ensure High Protein, creamy milk chocolate, ready to drink",
            },
            self.lexicon,
        )
        self.assertEqual(parsed["supercategory"], "Beverage")
        self.assertEqual(parsed["form"], "beverage")
        self.assertNotEqual(parsed["category_group"], "Chocolate")

    def test_coconut_water_beverage_does_not_route_to_coconut_milk(self) -> None:
        parsed = parse_row(
            {
                "product_description": "PEACH MANGO FLAVORED COCONUT WATER BEVERAGE, PEACH MANGO",
                "branded_food_category": "Water",
                "v6_fndds_description": "Water, flavored",
            },
            self.lexicon,
        )
        self.assertNotEqual(parsed["category_group"], "Plant-based Milk")
        self.assertNotEqual(parsed["form"], "milk")

    def test_almond_juice_beverage_does_not_route_to_almond_milk(self) -> None:
        parsed = parse_row(
            {
                "product_description": "LEMON GINGER DAILY DETOX COLD-PRESSED ALMOND JUICE BEVERAGE, LEMON GINGER",
                "branded_food_category": "Other Drinks",
                "v6_fndds_description": "Almond milk, sweetened",
                "best_esha_description": "Almond Milk, plain",
            },
            self.lexicon,
        )
        self.assertEqual(parsed["form"], "juice")
        self.assertEqual(parsed["category_group"], "Fruit-based Drinks")

    def test_milk_chocolate_banana_chips_are_not_dairy_milk(self) -> None:
        parsed = self.parse("WEGMANS, MILK CHOCOLATE BANANA CHIPS", "Wholesome Snacks")
        self.assertNotEqual(parsed["category_group"], "Dairy Milk")
        self.assertNotEqual(parsed["form"], "milk")
        self.assertEqual(parsed["form"], "chips")
        self.assertEqual(parsed["flavor"], "milk chocolate")

    def test_milk_chocolate_bar_is_confection_not_milk(self) -> None:
        parsed = self.parse("CRUNCH BANANA MILK CHOCOLATE BAR", "Chocolate")
        self.assertNotEqual(parsed["supercategory"], "Beverage")
        self.assertNotEqual(parsed["form"], "milk")
        self.assertEqual(parsed["form"], "bar")
        self.assertEqual(parsed["flavor"], "milk chocolate")

    def test_chocolate_milk_in_milk_category_stays_dairy_milk(self) -> None:
        parsed = self.parse("BOWL & BASKET CHOCOLATE MILK", "Milk")
        self.assertEqual(parsed["supercategory"], "Beverage")
        self.assertEqual(parsed["category_group"], "Dairy Milk")
        self.assertEqual(parsed["form"], "milk")

    def test_comma_separated_reduced_fat_chocolate_milk_stays_milk(self) -> None:
        parsed = self.parse("REDUCED FAT MILK, CHOCOLATE MILK", "Milk")
        self.assertEqual(parsed["supercategory"], "Beverage")
        self.assertEqual(parsed["category_group"], "Dairy Milk")
        self.assertEqual(parsed["form"], "milk")

    def test_milk_and_dark_chocolate_candies_are_not_dairy_milk(self) -> None:
        parsed = self.parse("DOUBLE CHOCOLATE MILK & DARK CHOCOLATE CANDIES", "Candy")
        self.assertNotEqual(parsed["category_group"], "Dairy Milk")
        self.assertNotEqual(parsed["form"], "milk")
        self.assertEqual(parsed["form"], "candies")

    def test_crisped_rice_milk_chocolate_is_chocolate_not_plant_milk(self) -> None:
        parsed = self.parse("CREAMY MILK CHOCOLATE WITH CRISPED RICE BARS", "Chocolate")
        self.assertEqual(parsed["supercategory"], "Snack")
        self.assertEqual(parsed["category_group"], "Chocolate")
        self.assertEqual(parsed["category"], "Chocolate")
        self.assertEqual(parsed["form"], "bars")

    def test_cadbury_dairy_milk_chocolate_is_confection_not_dairy_milk(self) -> None:
        parsed = self.parse("CADBURY DAIRY MILK CHOCOLATE MILK 470 GR", "Confectionery Products")
        self.assertNotEqual(parsed["category_group"], "Dairy Milk")
        self.assertNotEqual(parsed["form"], "milk")
        self.assertEqual(parsed["category_group"], "Chocolate")

    def test_packaging_pack_does_not_make_almondmilk_combo_pack(self) -> None:
        parsed = self.parse("Silk Dark Chocolate Almondmilk 8 fl. oz. Aseptic Pack", "Milk")
        self.assertEqual(parsed["retail_type"], "single")
        self.assertEqual(parsed["category_group"], "Plant-based Milk")
        self.assertEqual(parsed["form"], "milk")
        self.assertEqual(parsed["flavor"], "dark chocolate")

    def test_applesauce_cup_is_not_combo_pack(self) -> None:
        parsed = self.parse("Zee Zees Applesauce Cup, Wild Watermelon, 4.5 oz.")
        self.assertEqual(parsed["retail_type"], "single")
        self.assertNotEqual(parsed["category_group"], "Combo Packs")

    def test_cake_cups_are_not_combo_pack(self) -> None:
        parsed = self.parse("CAKE CUPS")
        self.assertEqual(parsed["retail_type"], "single")
        self.assertEqual(parsed["category_group"], "Cake")

    def test_bacon_toppings_are_not_combo_pack(self) -> None:
        parsed = self.parse("Bacon Toppings, Precooked, Hickory Smoked, 2/5 lb.")
        self.assertEqual(parsed["retail_type"], "single")
        self.assertEqual(parsed["primary_food"], "bacon")
        self.assertEqual(parsed["supercategory"], "Meat & Seafood")
        self.assertNotEqual(parsed["category_group"], "Combo Packs")


if __name__ == "__main__":
    unittest.main()
