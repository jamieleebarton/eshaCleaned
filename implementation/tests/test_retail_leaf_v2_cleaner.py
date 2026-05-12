from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


REPO = Path("/Users/jamiebarton/Desktop/esha_audit_bundle")
CLEANER_PATH = REPO / "retail_mapper" / "v2" / "clean_retail_leaf_v2.py"


def load_cleaner_module():
    spec = importlib.util.spec_from_file_location("retail_leaf_v2_cleaner", CLEANER_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class RetailLeafV2CleanerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = load_cleaner_module()
        cls.cleaner = cls.mod.RetailLeafCleaner(enable_group_smoothing=False)

    def clean(self, **overrides):
        row = {
            "fdc_id": "1",
            "gtin_upc": "",
            "title": "",
            "branded_food_category": "",
            "current_esha": "",
            "current_esha_desc": "",
            "retail_leaf": "",
            "confidence": "1.0",
            "top_score": "",
            "second_score": "",
            "sources_agreed": "0",
            "gap_flag": "False",
            "provenance": "",
            "distinctive_tokens": "",
            "distinctive_bigrams": "",
            "product_form_guess": "",
        }
        row.update(overrides)
        return self.cleaner.clean_row(row, apply_group=False)

    def test_rejects_embed_only_cashew_for_beef_jerky(self):
        decision = self.clean(
            title="BEEF JERKY",
            branded_food_category="Other Snacks",
            current_esha="10051",
            current_esha_desc="Beef, jerky, large piece",
            retail_leaf="Snack > Plant-based Milk > Cashew",
            confidence="0.468",
        )
        self.assertEqual(decision.clean_retail_leaf, "Meat & Seafood > Jerky > Beef")
        self.assertEqual(decision.clean_status, "accepted_router")

    def test_repairs_contradictory_almondmilk_sweetener_tail(self):
        decision = self.clean(
            title="ORIGINAL UNSWEETENED ALMONDMILK, ORIGINAL",
            branded_food_category="Plant Based Milk",
            current_esha="14480",
            current_esha_desc="Almond Milk, Almond Breeze, original, unsweetened",
            retail_leaf="Beverage > Plant-based Milk > Almond > Unsweetened > Sweetened",
        )
        self.assertEqual(
            decision.clean_retail_leaf,
            "Beverage > Plant-based Milk > Almond Milk > Plain Unsweetened",
        )
        self.assertNotIn("Sweetened", decision.clean_retail_leaf.split(" > ")[-1].replace("Unsweetened", ""))

    def test_routes_calcium_hydroxide_to_baking_additive_not_muffin(self):
        decision = self.clean(
            title="FINEST QUALITY CALCIUM HYDROXIDE",
            branded_food_category="Baking Additives & Extracts",
            current_esha="51117",
            current_esha_desc="Baking Soda, calcium carbonate",
            retail_leaf="Bakery > Muffin",
            confidence="0.161",
            gap_flag="True",
        )
        self.assertEqual(decision.clean_retail_leaf, "Pantry > Baking > Additive > Calcium Hydroxide")

    def test_routes_pepper_jelly_to_spreads_not_produce(self):
        decision = self.clean(
            title="HABANERO PEPPER JELLY",
            branded_food_category="Jam, Jelly & Fruit Spreads",
            retail_leaf="Produce > Vegetable > Pepper > Jelly > Habanero",
            confidence="0.471",
            sources_agreed="1",
            provenance='{"b1_parser":{"leaf":"Produce > Vegetable > Pepper > Jelly > Habanero","score":2.0}}',
        )
        self.assertEqual(decision.clean_retail_leaf, "Pantry > Spreads > Jelly > Pepper > Habanero")

    def test_routes_evaporated_filled_milk_to_subtype(self):
        decision = self.clean(
            title="GRACE EVAPORATED FILLED MILK, 12 FL OZ",
            branded_food_category="Milk",
            current_esha="20952",
            current_esha_desc="Milk, evaporated",
            retail_leaf="Beverage > Dairy Milk",
            confidence="0.735",
            sources_agreed="1",
        )
        self.assertEqual(decision.clean_retail_leaf, "Beverage > Dairy Milk > Evaporated Filled Milk")

    def test_buttermilk_biscuit_mix_stays_baking_product(self):
        decision = self.clean(
            title="BUTTERMILK BISCUIT MIX, BUTTERMILK",
            branded_food_category="Cake, Cookie & Cupcake Mixes",
            current_esha="217",
            current_esha_desc="Buttermilk, low fat, 1%, cultured",
            retail_leaf="Dairy > Buttermilk",
        )
        self.assertEqual(decision.clean_retail_leaf, "Pantry > Baking > Mix > Biscuit > Buttermilk")

    def test_gap_embedding_nugget_for_dunkaroos_is_not_accepted(self):
        decision = self.clean(
            title="Vanilla Dunkaroos 6 Count",
            branded_food_category="Baking/Cooking Mixes/Supplies",
            current_esha="49216",
            current_esha_desc="Baking Mix, vanilla, dry",
            retail_leaf="Frozen > Nugget",
            confidence="0.156",
            gap_flag="True",
        )
        self.assertNotEqual(decision.clean_retail_leaf, "Frozen > Nugget")
        self.assertEqual(decision.clean_status, "review")

    def test_plant_milk_bfc_rescues_abbreviated_almond_title(self):
        decision = self.clean(
            title="So Delicious Asep Almond 32oz Unsweetened",
            branded_food_category="Plant Based Milk",
            retail_leaf="Snack > Nuts & Seeds > Almond > Delicious",
        )
        self.assertEqual(
            decision.clean_retail_leaf,
            "Beverage > Plant-based Milk > Almond Milk > Plain Unsweetened",
        )

    def test_coffee_drink_with_almond_milk_component_is_not_milk(self):
        decision = self.clean(
            title="ROCKSTAR, ROASTED ENERGY + COFEE DRINK WITH ALMOND MILK, WHITE CHOCOLATE, WHITE CHOCOLATE",
            branded_food_category="Energy, Protein & Muscle Recovery Drinks",
            retail_leaf="Beverage > Dairy Milk > Chocolate Milk",
        )
        self.assertNotIn("Dairy Milk", decision.clean_retail_leaf)
        self.assertEqual(decision.clean_retail_leaf.split(" > ")[0], "Beverage")

    def test_milk_chocolate_candies_do_not_route_to_dairy_milk(self):
        decision = self.clean(
            title="THE ORIGINAL CARAMEL APPLE! GOURMET MILK CHOCOLATE CANDIES, ORIGINAL CARAMEL APPLE",
            branded_food_category="Candy",
            retail_leaf="Beverage > Dairy Milk > Chocolate Milk",
        )
        self.assertEqual(decision.clean_retail_leaf, "Snack > Chocolate > Candies > Milk Chocolate")

    def test_plant_based_jerky_is_not_meat(self):
        decision = self.clean(
            title="Off-Piste Provisions Plant-Based Jerky Original 50g",
            branded_food_category="Other Snacks",
            retail_leaf="Meat & Seafood > Bacon",
        )
        self.assertEqual(decision.clean_retail_leaf, "Snack > Jerky > Plant-based")

    def test_baking_cocoa_gets_baking_leaf(self):
        decision = self.clean(
            title="POWDERED BAKING COCOA",
            branded_food_category="Baking Additives & Extracts",
            retail_leaf="Other > Reference > FUNNEL:baking cocoa",
            confidence="0.229",
            gap_flag="True",
        )
        self.assertEqual(decision.clean_retail_leaf, "Pantry > Baking > Cocoa")

    def test_milkshake_gets_shake_leaf_not_chocolate_snack(self):
        decision = self.clean(
            title="CHOCOLATE MILKSHAKE",
            branded_food_category="Other Drinks",
            retail_leaf="Snack > Chocolate",
        )
        self.assertEqual(decision.clean_retail_leaf, "Beverage > Shake > Milkshake > Chocolate")

    def test_pb_j_bar_does_not_route_to_spread_shelf(self):
        decision = self.clean(
            title="PB & JELLY PROTEIN BAR, PB & JELLY",
            branded_food_category="Snack, Energy & Granola Bars",
            retail_leaf="Pantry > Spreads > Jelly > Protein Bar",
            provenance='{"b1_parser":{"leaf":"Pantry > Spreads > Jelly > Protein Bar","score":2.0}}',
        )
        self.assertEqual(decision.clean_retail_leaf, "Snack > Bar > Protein > Peanut Butter")

    def test_milkshake_protein_powder_is_powder_not_milkshake(self):
        decision = self.clean(
            title="CHOCOLATE MILKSHAKE 100% WHEY PROTEIN POWDER, CHOCOLATE MILKSHAKE",
            branded_food_category="Energy, Protein & Muscle Recovery Drinks",
            retail_leaf="Beverage > Shake > Milkshake > Chocolate",
        )
        self.assertEqual(decision.clean_retail_leaf, "Pantry > Protein Powders > Whey Protein > Chocolate")

    def test_chocolate_baking_mix_is_not_chocolate_snack(self):
        decision = self.clean(
            title="NANACAKES, CHOCOLATE BAKING MIX",
            branded_food_category="Cake, Cookie & Cupcake Mixes",
            retail_leaf="Snack > Chocolate",
        )
        self.assertTrue(decision.clean_retail_leaf.startswith("Pantry > Baking > Mix"))

    def test_no_salt_added_mushrooms_do_not_become_salt(self):
        decision = self.clean(
            title="NO SALT ADDED MUSHROOM PIECES & STEMS",
            branded_food_category="Canned Vegetables",
            retail_leaf="Pantry > Spices > Salt",
            provenance='{"b1_parser":{"leaf":"Pantry > Spices > Salt","score":2.0}}',
        )
        self.assertEqual(decision.clean_retail_leaf, "Pantry > Canned > Vegetable > Mushroom")

    def test_cream_brand_fat_free_milk_is_milk_subtype(self):
        decision = self.clean(
            title="CREAM-O-LAND, FAT FREE MILK",
            branded_food_category="Milk",
            retail_leaf="Beverage > Dairy Milk > Cream Milk",
            provenance='{"b1_parser":{"leaf":"Beverage > Dairy Milk > Cream Milk","score":2.0}}',
        )
        self.assertEqual(decision.clean_retail_leaf, "Beverage > Dairy Milk > Fat Free Milk")

    def test_taxonomy_recovers_grapefruit_juice_identity_over_color_tail(self):
        decision = self.clean(
            fdc_id="2549102",
            gtin_upc="48500018569",
            title="NO PULP RED GRAPERFRUIT JUICE, NO PULP RED GRAPERFRUIT",
            branded_food_category="Fruit & Vegetable Juice, Nectars & Fruit Drinks",
            current_esha="31694",
            current_esha_desc="Juice, grapefruit, pulp free",
            retail_leaf="Beverage > Juice",
            confidence="1",
            top_score="4.4",
            second_score="3.37",
            sources_agreed="0",
            provenance=(
                '{"b1_parser":{"leaf":"Beverage > Fruit-based Drinks > Juice > Red"},'
                '"b_neg1_esha_anchor":{"anchor_leaf":"Beverage > Juice"},'
                '"b0_bfc":{"hint":"Beverage > Juice"}}'
            ),
        )
        self.assertEqual(decision.clean_retail_leaf, "Beverage > Fruit-based Drinks > Juice > Grapefruit")
        self.assertIn("taxonomy_identity", decision.clean_sources)

    def test_jelly_beans_are_candy_not_spread(self):
        decision = self.clean(
            title="THE ORIGINAL GOURMET JELLY BEANS, SUNKIST ORANGE, SUNKIST LEMON, SUNKIST PINK GRAPEFRUIT",
            branded_food_category="Candy",
            retail_leaf="Pantry > Spreads > Jelly > Original > Bean",
        )
        self.assertEqual(decision.clean_retail_leaf, "Snack > Candy > Jelly Beans")

    def test_gummies_with_fruit_flavors_are_candy_not_produce(self):
        decision = self.clean(
            title=(
                "CHERRY, STRAWBERRY, MANGO, PINEAPPLE, LEMON, ORANGE, GREEN APPLE, "
                "WATERMELON, PINK GRAPEFRUIT, LIME, BLUE RASPBERRY, GRAPE MINI GUMMIES"
            ),
            branded_food_category="Candy",
            retail_leaf="Snack > Candy > Bear",
        )
        self.assertEqual(decision.clean_retail_leaf, "Snack > Candy > Gummy")

    def test_jelly_slices_are_candy_not_fruit_spread(self):
        decision = self.clean(
            title="GRAPEFRUIT JELLY SLICES",
            branded_food_category="Candy",
            retail_leaf="Pantry > Spreads > Jelly",
        )
        self.assertEqual(decision.clean_retail_leaf, "Snack > Candy > Jelly Slices")

    def test_fruit_bowl_candy_is_not_composite_dish(self):
        decision = self.clean(
            fdc_id="1951343",
            gtin_upc="71570007096",
            title=(
                "FRUIT BOWL, BLUEBERRY, COCONUT, GREEN APPLE, JUICY PEAR, SUNKIST LEMON, "
                "LEMON LIME, PEACH, SUNKIST PINK GRAPEFRUIT, PLUM, POMEGRANATE, "
                "RASPBERRY, RED APPLE, SUNKIST TANGERINE, TOP BANANA, VERY CHERRY, WATERMELON"
            ),
            branded_food_category="Candy",
            current_esha="3197",
            current_esha_desc='Pomegranate, fresh, 4"',
            retail_leaf="Pantry > Sweeteners > Sugar > Post Breakfast Bowls",
            provenance='{"b0_bfc":{"hint":"Snack > Candy"},"b_neg1_esha_anchor":{"anchor_leaf":"Produce > Pomegranate"}}',
        )
        self.assertNotEqual(decision.parser["retail_type"], "composite_dish")
        self.assertEqual(decision.clean_retail_leaf, "Snack > Candy")

    def test_bagel_variety_router_keeps_compound_type(self):
        decision = self.clean(
            fdc_id="2612011",
            gtin_upc="42187503783",
            title="APPLE CINNAMON BAGELS, APPLE CINNAMON",
            branded_food_category="Breads & Buns",
            current_esha="33208",
            current_esha_desc="Bagel, apple, baked",
            retail_leaf="Bakery",
            confidence="1",
        )
        self.assertEqual(decision.clean_retail_leaf, "Pantry > Bread > Bagels > Apple Cinnamon")
        self.assertIn("bread_variety_router", decision.clean_reason)

    def test_bagel_router_ignores_packaging_and_style_words(self):
        decision = self.clean(
            fdc_id="2474507",
            gtin_upc="718000000000",
            title="ASIAGO 5 NEW YORK STYLE BAGELS, ASIAGO",
            branded_food_category="Breads & Buns",
            current_esha="18950",
            current_esha_desc="Bagel, asiago",
            retail_leaf="Bakery",
            confidence="1",
        )
        self.assertEqual(decision.clean_retail_leaf, "Pantry > Bread > Bagels > Asiago")
        self.assertNotIn("New York", decision.clean_retail_leaf)

    def test_bagel_router_prefers_variety_over_prep_state(self):
        decision = self.clean(
            fdc_id="1926497",
            gtin_upc="867000000000",
            title="KETTLE BOILED BAGELS, ASIAGO BAGELS",
            branded_food_category="Breads & Buns",
            current_esha="18950",
            current_esha_desc="Bagel, asiago",
            retail_leaf="Bakery",
            confidence="1",
        )
        self.assertEqual(decision.clean_retail_leaf, "Pantry > Bread > Bagels > Asiago")
        self.assertNotIn("Kettle", decision.clean_retail_leaf)

    def test_bread_bfc_and_esha_anchor_override_cheese_parser(self):
        decision = self.clean(
            fdc_id="2640036",
            gtin_upc="788000000000",
            title="ASIAGO AND PARMESAN CHEESE, ASIAGO",
            branded_food_category="Breads & Buns",
            current_esha="33210",
            current_esha_desc="Bagel, asiago parmesan",
            retail_leaf="Bakery",
            confidence="1",
        )
        self.assertEqual(decision.clean_retail_leaf, "Pantry > Bread > Bagel > Asiago Parmesan")

    def test_exact_root_only_current_leaf_is_not_accepted(self):
        decision = self.clean(
            title="MYSTERY PRODUCT",
            branded_food_category="",
            current_esha_desc="",
            retail_leaf="Bakery",
            confidence="1",
            sources_agreed="0",
        )
        self.assertEqual(decision.clean_status, "review")
        self.assertEqual(decision.clean_retail_leaf, "")

    def test_breads_buns_root_only_bakery_falls_back_to_bread_parent(self):
        decision = self.clean(
            fdc_id="477477",
            gtin_upc="20042509",
            title="BOLILLOS",
            branded_food_category="Breads & Buns",
            current_esha="71839",
            current_esha_desc="Bread, 6 flour, wheat free",
            retail_leaf="Bakery",
            confidence="1",
            sources_agreed="0",
            provenance=(
                '{"b_neg1_esha_anchor":{"anchor_leaf":"Pantry > Bread"},'
                '"b0_bfc":{"hint":"Pantry > Bread"},'
                '"b8_ingredient_fndds":{"resolved_leaf":"Pantry > Bread"}}'
            ),
        )
        self.assertEqual(decision.clean_retail_leaf, "Pantry > Bread > Bolillos")
        self.assertNotEqual(decision.clean_retail_leaf, "Bakery")

    def test_root_only_bakery_examples_recover_bread_product_type_when_title_has_it(self):
        examples = [
            ("SEASONED GROUTONS, SEASONED", "Pantry > Croutons > Seasoned"),
            ("UNSALTED MATZOS", "Pantry > Bread > Matzo"),
            ("CONCHAS", "Pantry > Bread > Conchas"),
            ("SHARROCK'S, CRUMPETS", "Pantry > Bread > Crumpets"),
        ]
        for title, expected in examples:
            with self.subTest(title=title):
                decision = self.clean(
                    title=title,
                    branded_food_category="Breads & Buns",
                    current_esha="71839",
                    current_esha_desc="Bread, 6 flour, wheat free",
                    retail_leaf="Bakery",
                    confidence="1",
                    sources_agreed="0",
                    provenance='{"b0_bfc":{"hint":"Pantry > Bread"}}',
                )
                self.assertEqual(decision.clean_retail_leaf, expected)


if __name__ == "__main__":
    unittest.main()
