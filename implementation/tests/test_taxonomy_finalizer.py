from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


REPO = Path("/Users/jamiebarton/Desktop/esha_audit_bundle")
FINALIZER_PATH = REPO / "retail_mapper" / "v2" / "taxonomy_finalizer.py"


def load_finalizer_module():
    spec = importlib.util.spec_from_file_location("taxonomy_finalizer", FINALIZER_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class TaxonomyFinalizerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = load_finalizer_module()

    def finalize(self, **overrides):
        row = {
            "fdc_id": "1",
            "title": "",
            "branded_food_category": "",
            "category_path_fixed": "",
            "product_identity_fixed": "",
            "canonical_path": "",
            "variant": "",
            "flavor": "",
            "claims": "",
            "form_texture_cut": "",
        }
        row.update(overrides)
        return self.mod.finalize_taxonomy_row(row)

    def assert_clean(self, finalized):
        row = {
            "category_path_fixed": finalized.category_path_fixed,
            "canonical_path": finalized.canonical_path,
            "modifier": finalized.modifier,
            "retail_leaf_path": finalized.retail_leaf_path,
        }
        self.assertEqual([], self.mod.path_defects(row))

    def test_unsweetened_original_almondmilk_drops_original_and_dedupes_claim(self):
        finalized = self.finalize(
            title="UNSWEETENED ORIGINAL ALMONDMILK",
            branded_food_category="Plant Based Milk",
            category_path_fixed="Beverage > Plant Milk",
            product_identity_fixed="Almond Milk",
            canonical_path="Beverage > Plant Milk > Almond Milk",
            variant="unsweetened_original",
            claims="unsweetened",
        )

        self.assertEqual("Beverage > Plant Milk", finalized.category_path_fixed)
        self.assertEqual("Almond Milk", finalized.product_identity_fixed)
        self.assertEqual("Beverage > Plant Milk > Almond Milk", finalized.canonical_path)
        self.assertEqual("Unsweetened", finalized.modifier)
        self.assertEqual(
            "Beverage > Plant Milk > Almond Milk > Unsweetened",
            finalized.retail_leaf_path,
        )
        self.assert_clean(finalized)

    def test_bad_cola_almondmilk_is_forced_back_to_plant_milk(self):
        finalized = self.finalize(
            title="UNSWEETENED CHOCOLATE ALMONDMILK",
            branded_food_category="Plant Based Milk",
            category_path_fixed="Beverage > Plant Milk",
            product_identity_fixed="Almond Milk",
            canonical_path="Beverage > Carbonated > Cola > Unsweetened",
            flavor="chocolate",
            claims="unsweetened",
        )

        self.assertEqual("Beverage > Plant Milk > Almond Milk", finalized.canonical_path)
        self.assertEqual("Chocolate > Unsweetened", finalized.modifier)
        self.assertEqual(
            "Beverage > Plant Milk > Almond Milk > Chocolate > Unsweetened",
            finalized.retail_leaf_path,
        )
        self.assert_clean(finalized)

    def test_milked_peanuts_are_peanut_milk_not_dairy_milk(self):
        finalized = self.finalize(
            title="CHOCOLATE MILKED PEANUTS",
            branded_food_category="Plant Based Milk",
            category_path_fixed="Beverage > Plant Milk",
            product_identity_fixed="Chocolate Milk",
            canonical_path="Dairy > Milk",
            flavor="chocolate",
        )

        self.assertEqual("Peanut Milk", finalized.product_identity_fixed)
        self.assertEqual("Beverage > Plant Milk > Peanut Milk", finalized.canonical_path)
        self.assertEqual("Chocolate", finalized.modifier)
        self.assert_clean(finalized)

    def test_plant_based_claim_is_not_appended_under_plant_milk(self):
        finalized = self.finalize(
            title="PLANT BASED VANILLA UNSWEETENED ALMOND MILK",
            branded_food_category="Plant Based Milk",
            category_path_fixed="Beverage > Plant Milk",
            product_identity_fixed="Almond Milk",
            canonical_path="Beverage > Plant Milk > Almond Milk",
            flavor="vanilla",
            claims="plant_based|unsweetened|non_dairy",
        )

        self.assertEqual("Beverage > Plant Milk > Almond Milk", finalized.canonical_path)
        self.assertEqual("Vanilla > Unsweetened", finalized.modifier)
        self.assertEqual(
            "Beverage > Plant Milk > Almond Milk > Vanilla > Unsweetened",
            finalized.retail_leaf_path,
        )
        self.assertNotIn("Plant Based", finalized.retail_leaf_path)
        self.assertNotIn("Non Dairy", finalized.retail_leaf_path)
        self.assert_clean(finalized)

    def test_plant_based_claim_is_retained_when_route_is_not_plant_based(self):
        finalized = self.finalize(
            title="PLANT BUTTER WITH SEA SALT",
            branded_food_category="Butter & Spread",
            category_path_fixed="Dairy > Butter",
            product_identity_fixed="Butter",
            canonical_path="Dairy > Butter",
            claims="plant_based",
        )

        self.assertEqual("Dairy > Butter", finalized.canonical_path)
        self.assertEqual("Plant Based", finalized.modifier)
        self.assertEqual("Dairy > Butter > Plant Based", finalized.retail_leaf_path)
        self.assert_clean(finalized)

    def test_seafood_steaks_do_not_route_to_beef_steak(self):
        finalized = self.finalize(
            title="HAKE STEAKS",
            branded_food_category="Frozen Fish & Seafood",
            category_path_fixed="Meat & Seafood > Beef > Steak",
            product_identity_fixed="Steaks",
            canonical_path="Meat & Seafood > Beef > Steak > Steaks",
        )

        self.assertEqual("Meat & Seafood > Fish", finalized.category_path_fixed)
        self.assertEqual("Hake", finalized.product_identity_fixed)
        self.assertEqual("Meat & Seafood > Fish > Hake", finalized.canonical_path)
        self.assert_clean(finalized)

    def test_cookie_butter_is_not_dairy_butter(self):
        finalized = self.finalize(
            title="COOKIE BUTTER, SPICED COOKIE SPREAD",
            branded_food_category="Honey, Jam, Marmalade & Spreads",
            category_path_fixed="Dairy > Butter",
            product_identity_fixed="Cookie Butter",
            canonical_path="Dairy > Butter > Cookie Butter",
        )

        self.assertEqual("Pantry > Spreads", finalized.category_path_fixed)
        self.assertEqual("Pantry > Spreads > Cookie Butter", finalized.canonical_path)
        self.assert_clean(finalized)

    def test_identity_echoes_are_not_appended_to_canonical_path(self):
        finalized = self.finalize(
            title="WHITE CHEDDAR CRUNCHY SUPERFOOD SNACK",
            category_path_fixed="Snack > Chips",
            product_identity_fixed="Snack",
            canonical_path="Snack > Chips > Snack",
            flavor="white_cheddar",
        )

        self.assertEqual("Snack > Chips", finalized.canonical_path)
        self.assertEqual("White Cheddar", finalized.modifier)
        self.assert_clean(finalized)

    def test_duplicate_identity_segment_is_removed_from_macaroni_path(self):
        finalized = self.finalize(
            title="ELBOW MACARONI SHELLS",
            category_path_fixed="Pantry > Pasta > Macaroni > Shells",
            product_identity_fixed="Macaroni",
            canonical_path="Pantry > Pasta > Macaroni > Shells > Macaroni",
        )

        self.assertEqual("Pantry > Pasta > Macaroni > Shells", finalized.canonical_path)
        self.assert_clean(finalized)

    def test_modifier_dedupes_across_facet_levels(self):
        finalized = self.finalize(
            title="GLAZED PECANS",
            category_path_fixed="Snack > Nuts",
            product_identity_fixed="Pecans",
            canonical_path="Snack > Nuts > Pecans",
            variant="glazed",
            form_texture_cut="glazed",
        )

        self.assertEqual("Glazed", finalized.modifier)
        self.assertEqual("Snack > Nuts > Pecans > Glazed", finalized.retail_leaf_path)
        self.assert_clean(finalized)

    def test_combined_category_parent_remains_canonical_prefix(self):
        finalized = self.finalize(
            title="APPLE BUTTER MESQUITE SAUCE",
            category_path_fixed="Pantry > Sauces & Salsas",
            product_identity_fixed="Sauce",
            canonical_path="Pantry > Sauce",
            variant="apple_butter_mesquite",
        )

        self.assertEqual("Pantry > Sauces & Salsas", finalized.category_path_fixed)
        self.assertEqual("Pantry > Sauces & Salsas > Sauce", finalized.canonical_path)
        self.assertEqual(
            "Pantry > Sauces & Salsas > Sauce > Apple Butter Mesquite",
            finalized.retail_leaf_path,
        )
        self.assert_clean(finalized)

    def test_frozen_pork_bun_is_appetizer_not_bakery_bun(self):
        finalized = self.finalize(
            title="TERIYAKI BBQ PORK BUN, TERIYAKI",
            branded_food_category="Frozen Appetizers & Hors D'oeuvres",
            category_path_fixed="Bakery > Buns",
            product_identity_fixed="Buns",
            canonical_path="Bakery > Buns",
            variant="teriyaki_bbq_pork",
        )

        self.assertEqual("Frozen > Appetizers", finalized.category_path_fixed)
        self.assertEqual("Stuffed Buns", finalized.product_identity_fixed)
        self.assertEqual("Frozen > Appetizers > Stuffed Buns", finalized.canonical_path)
        self.assertEqual(
            "Frozen > Appetizers > Stuffed Buns > Teriyaki BBQ Pork",
            finalized.retail_leaf_path,
        )
        self.assert_clean(finalized)

    def test_prepared_sub_on_bun_is_sandwich_not_bakery_bun(self):
        finalized = self.finalize(
            title="TURKEY & CHEESE MINI SUB ON WHITE BUN, TURKEY & CHEESE",
            branded_food_category="Prepared Subs & Sandwiches",
            category_path_fixed="Bakery > Buns",
            product_identity_fixed="Buns",
            canonical_path="Bakery > Buns",
            variant="turkey_cheese",
        )

        self.assertEqual("Meal > Sandwiches", finalized.category_path_fixed)
        self.assertEqual("Sub Sandwich", finalized.product_identity_fixed)
        self.assertEqual("Meal > Sandwiches > Sub Sandwich", finalized.canonical_path)
        self.assertEqual(
            "Meal > Sandwiches > Sub Sandwich > Turkey Cheese",
            finalized.retail_leaf_path,
        )
        self.assert_clean(finalized)

    def test_breakfast_bagel_with_eggs_is_breakfast_sandwich_not_bagel(self):
        finalized = self.finalize(
            title="SFS TONY'S 51% WG BREAKFAST BAGEL WITH MOZZARELLA AND EGGS NET WT 16.80 LBS 96CT",
            branded_food_category="Savoury Bakery Products",
            category_path_fixed="Bakery > Bagels",
            product_identity_fixed="Breakfast Bagel Sandwich",
            canonical_path="Bakery > Bagels > Breakfast Bagel Sandwich",
            variant="mozzarella|egg",
            claims="whole_grain",
            fndds_desc="Egg, cheese, and steak on bagel",
            esha_desc="Breakfast Sandwich, egg & cheese, with bagel",
        )

        self.assertEqual("Meal > Breakfast Sandwiches", finalized.category_path_fixed)
        self.assertEqual("Breakfast Sandwich", finalized.product_identity_fixed)
        self.assertEqual(
            "Meal > Breakfast Sandwiches > Breakfast Sandwich",
            finalized.canonical_path,
        )
        self.assertEqual("Mozzarella Egg > Whole Grain", finalized.modifier)
        self.assertEqual(
            "Meal > Breakfast Sandwiches > Breakfast Sandwich > Mozzarella Egg > Whole Grain",
            finalized.retail_leaf_path,
        )
        self.assert_clean(finalized)

    def test_plain_egg_bagels_stay_bagels_not_breakfast_sandwiches(self):
        finalized = self.finalize(
            title="EGG BAGELS, EGG",
            branded_food_category="Breads & Buns",
            category_path_fixed="Bakery > Bagels",
            product_identity_fixed="Bagels",
            canonical_path="Bakery > Bagels",
            variant="egg",
        )

        self.assertEqual("Bakery > Bagels", finalized.category_path_fixed)
        self.assertEqual("Bakery > Bagels", finalized.canonical_path)
        self.assertEqual("Egg", finalized.modifier)
        self.assertEqual("Bakery > Bagels > Egg", finalized.retail_leaf_path)
        self.assert_clean(finalized)

    def test_frozen_egg_roll_is_appetizer_not_bakery_roll(self):
        finalized = self.finalize(
            title="KOREAN STYLE BEEF EGG ROLLS SPICY BEEF",
            branded_food_category="Frozen Appetizers & Hors D'oeuvres",
            category_path_fixed="Bakery > Rolls",
            product_identity_fixed="Rolls",
            canonical_path="Bakery > Rolls",
            variant="spicy_beef",
        )

        self.assertEqual("Frozen > Appetizers", finalized.category_path_fixed)
        self.assertEqual("Egg Rolls", finalized.product_identity_fixed)
        self.assertEqual("Frozen > Appetizers > Egg Rolls", finalized.canonical_path)
        self.assert_clean(finalized)

    def test_biscotti_has_one_canonical_shelf_even_when_bfc_says_cookies(self):
        finalized = self.finalize(
            title="TRADITIONAL ITALIAN BISCOTTINI, PUMPKIN PECAN",
            branded_food_category="Cookies & Biscuits",
            category_path_fixed="Bakery > Cookies",
            product_identity_fixed="Biscotti",
            canonical_path="Bakery > Cookies > Biscotti",
            variant="pumpkin_pecan",
        )

        self.assertEqual("Bakery > Biscotti", finalized.category_path_fixed)
        self.assertEqual("Biscotti", finalized.product_identity_fixed)
        self.assertEqual("Bakery > Biscotti", finalized.canonical_path)
        self.assertEqual("Bakery > Biscotti > Pumpkin Pecan", finalized.retail_leaf_path)
        self.assert_clean(finalized)

    def test_crackers_have_one_shelf_even_when_bfc_says_biscuits_cookies(self):
        finalized = self.finalize(
            title="NABISCO TRISCUIT CRACKERS REDUCED FAT1X8 OZ",
            branded_food_category="Biscuits/Cookies",
            category_path_fixed="Snack > Crackers",
            product_identity_fixed="Crackers",
            canonical_path="Snack > Crackers",
            variant="whole_wheat",
            claims="reduced_fat",
        )

        self.assertEqual("Snack > Crackers", finalized.category_path_fixed)
        self.assertEqual("Crackers", finalized.product_identity_fixed)
        self.assertEqual("Snack > Crackers", finalized.canonical_path)
        self.assertEqual("Whole Wheat > Reduced Fat", finalized.modifier)
        self.assertEqual(
            "Snack > Crackers > Whole Wheat > Reduced Fat",
            finalized.retail_leaf_path,
        )
        self.assert_clean(finalized)

    def test_lunch_kit_with_crackers_is_not_crackers(self):
        finalized = self.finalize(
            title="BUMBLE BEE SNACK ON THE RUN! TUNA SALAD KIT WITH CRACKERS, 3.5 OZ",
            branded_food_category="Prepared Subs & Sandwiches",
            category_path_fixed="Meal > Lunch Kits",
            product_identity_fixed="Lunch Kit",
            canonical_path="Meal > Lunch Kits",
            variant="tuna_salad",
        )

        self.assertEqual("Meal > Lunch Kits", finalized.category_path_fixed)
        self.assertEqual("Lunch Kit", finalized.product_identity_fixed)
        self.assertEqual("Meal > Lunch Kits", finalized.canonical_path)
        self.assertEqual("Tuna Salad", finalized.modifier)
        self.assert_clean(finalized)

    def test_sandwich_cookie_is_not_prepared_sandwich(self):
        finalized = self.finalize(
            title="CINNAMON BUN CREME SANDWICH COOKIES, CINNAMON BUN CREME",
            branded_food_category="Cookies & Biscuits",
            category_path_fixed="Bakery > Buns",
            product_identity_fixed="Sandwich Buns",
            canonical_path="Bakery > Buns > Sandwich Buns",
            variant="cinnamon_bun_creme",
            flavor="cinnamon",
            form_texture_cut="sandwich",
        )

        self.assertEqual("Bakery > Cookies", finalized.category_path_fixed)
        self.assertEqual("Cookies", finalized.product_identity_fixed)
        self.assertEqual("Bakery > Cookies", finalized.canonical_path)
        self.assert_clean(finalized)

    def test_pinto_beans_are_not_baking_mix(self):
        finalized = self.finalize(
            title="PINTO BEANS",
            branded_food_category="Canned & Bottled Beans",
            category_path_fixed="Pantry > Baking Mixes",
            product_identity_fixed="Pinto Beans",
            canonical_path="Pantry > Baking Mixes > Pinto Beans",
        )

        self.assertEqual("Pantry > Beans", finalized.category_path_fixed)
        self.assertEqual("Pinto Beans", finalized.product_identity_fixed)
        self.assertEqual("Pantry > Beans > Pinto Beans", finalized.canonical_path)
        self.assert_clean(finalized)

    def test_lentils_are_not_baking_mix(self):
        finalized = self.finalize(
            title="ORGANIC GREEN LENTILS WITH ONION & BAY LEAF",
            branded_food_category="Vegetable and Lentil Mixes",
            category_path_fixed="Pantry > Baking Mixes",
            product_identity_fixed="Lentils",
            canonical_path="Pantry > Baking Mixes > Lentils",
            variant="onion_bay_leaf",
        )

        self.assertEqual("Pantry > Beans", finalized.category_path_fixed)
        self.assertEqual("Green Lentils", finalized.product_identity_fixed)
        self.assertEqual("Pantry > Beans > Green Lentils", finalized.canonical_path)
        self.assertEqual("Onion Bay Leaf", finalized.modifier)
        self.assert_clean(finalized)

    def test_carnitas_burrito_is_meal_not_baking_mix(self):
        finalized = self.finalize(
            title="CARNITAS BURRITO",
            branded_food_category="Mexican Dinner Mixes",
            category_path_fixed="Pantry > Baking Mixes",
            product_identity_fixed="Burrito",
            canonical_path="Pantry > Baking Mixes > Burrito",
            variant="carnitas",
        )

        self.assertEqual("Meal > Burritos", finalized.category_path_fixed)
        self.assertEqual("Burrito", finalized.product_identity_fixed)
        self.assertEqual("Meal > Burritos", finalized.canonical_path)
        self.assertEqual("Carnitas", finalized.modifier)
        self.assertEqual("Meal > Burritos > Carnitas", finalized.retail_leaf_path)
        self.assert_clean(finalized)

    def test_blackeye_peas_are_beans_not_baking_mix(self):
        finalized = self.finalize(
            title="HAM FLAVOR BLACKEYE PEAS, HAM",
            branded_food_category="Vegetable and Lentil Mixes",
            category_path_fixed="Pantry > Baking Mixes",
            product_identity_fixed="Peas",
            canonical_path="Pantry > Baking Mixes > Peas",
            variant="ham",
        )

        self.assertEqual("Pantry > Beans", finalized.category_path_fixed)
        self.assertEqual("Black-Eyed Peas", finalized.product_identity_fixed)
        self.assertEqual("Pantry > Beans > Black-Eyed Peas", finalized.canonical_path)
        self.assertEqual("Ham", finalized.modifier)
        self.assert_clean(finalized)

    def test_ice_cream_cones_are_not_baking_mix(self):
        finalized = self.finalize(
            title="Keebler Cones Cake 600ct",
            branded_food_category="Ice Cream/Ice Novelties (Shelf Stable)",
            category_path_fixed="Pantry > Baking Mixes",
            product_identity_fixed="Ice Cream Cone",
            canonical_path="Pantry > Baking Mixes > Ice Cream Cone",
            variant="cake",
        )

        self.assertEqual("Snack > Ice Cream Cones", finalized.category_path_fixed)
        self.assertEqual("Ice Cream Cone", finalized.product_identity_fixed)
        self.assertEqual("Snack > Ice Cream Cones", finalized.canonical_path)
        self.assertEqual("Cake", finalized.modifier)
        self.assertEqual("Snack > Ice Cream Cones > Cake", finalized.retail_leaf_path)
        self.assert_clean(finalized)

    def test_pie_crust_mix_is_baking_mix_not_finished_pie(self):
        finalized = self.finalize(
            title="PIE CRUST GLUTEN FREE MIX, PIE CRUST",
            branded_food_category="Crusts & Dough",
            category_path_fixed="Bakery > Pie",
            product_identity_fixed="Pie Crust Mix",
            canonical_path="Bakery > Pie > Pie Crust Mix",
            claims="gluten_free",
            fndds_desc="pie crust mix",
            esha_desc="Crust, pie, dry mix",
        )

        self.assertEqual("Pantry > Baking Mixes", finalized.category_path_fixed)
        self.assertEqual("Pie Crust Mix", finalized.product_identity_fixed)
        self.assertEqual("Pantry > Baking Mixes > Pie Crust Mix", finalized.canonical_path)
        self.assertEqual("Gluten Free", finalized.modifier)
        self.assertEqual(
            "Pantry > Baking Mixes > Pie Crust Mix > Gluten Free",
            finalized.retail_leaf_path,
        )
        self.assert_clean(finalized)

    def test_pie_shells_are_crust_components_not_finished_pies(self):
        finalized = self.finalize(
            title="DEEP DISH PIE SHELLS",
            branded_food_category="Crusts & Dough",
            category_path_fixed="Bakery > Pie",
            product_identity_fixed="Pie Shells",
            canonical_path="Bakery > Pie > Pie Shells",
            variant="deep_dish",
            fndds_desc="pie shell",
            esha_desc='Shell, pie, graham cracker, prepared from recipe, baked, 9"',
        )

        self.assertEqual("Bakery > Pie Crusts", finalized.category_path_fixed)
        self.assertEqual("Pie Shells", finalized.product_identity_fixed)
        self.assertEqual("Bakery > Pie Crusts > Pie Shells", finalized.canonical_path)
        self.assertEqual("Deep Dish", finalized.modifier)
        self.assertEqual(
            "Bakery > Pie Crusts > Pie Shells > Deep Dish",
            finalized.retail_leaf_path,
        )
        self.assert_clean(finalized)

    def test_pina_colada_mix_is_cocktail_mixer_not_baking_mix(self):
        finalized = self.finalize(
            title="PINA COLADA MIX",
            branded_food_category="Alcohol",
            category_path_fixed="Pantry > Baking Mixes",
            product_identity_fixed="Mix",
            canonical_path="Pantry > Baking Mixes > Mix",
        )

        self.assertEqual("Beverage > Cocktail Mixers", finalized.category_path_fixed)
        self.assertEqual("Cocktail Mix", finalized.product_identity_fixed)
        self.assertEqual(
            "Beverage > Cocktail Mixers > Cocktail Mix",
            finalized.canonical_path,
        )
        self.assertEqual("Pina Colada", finalized.modifier)
        self.assertEqual(
            "Beverage > Cocktail Mixers > Cocktail Mix > Pina Colada",
            finalized.retail_leaf_path,
        )
        self.assert_clean(finalized)

    def test_pina_colada_juice_without_mix_cue_stays_juice(self):
        finalized = self.finalize(
            title="PINA COLADA JUICE, PINA COLADA",
            branded_food_category="Alcohol",
            category_path_fixed="Beverage > Juice",
            product_identity_fixed="Juice",
            canonical_path="Beverage > Juice",
            flavor="pina_colada",
        )

        self.assertEqual("Beverage > Juice", finalized.category_path_fixed)
        self.assertEqual("Juice", finalized.product_identity_fixed)
        self.assertEqual("Beverage > Juice", finalized.canonical_path)
        self.assertEqual("Pina Colada", finalized.modifier)
        self.assertEqual("Beverage > Juice > Pina Colada", finalized.retail_leaf_path)
        self.assert_clean(finalized)

    def test_alcohol_bfc_drink_mix_is_beverage_not_pantry_mix(self):
        finalized = self.finalize(
            title="GREEN APPLE UNSWEETENED DRINK MIX, GREEN APPLE",
            branded_food_category="Alcohol",
            category_path_fixed="Pantry > Mixes",
            product_identity_fixed="Drink Mix",
            canonical_path="Pantry > Mixes > Drink Mix",
            flavor="green_apple",
            claims="unsweetened",
        )

        self.assertEqual("Beverage > Mixes", finalized.category_path_fixed)
        self.assertEqual("Drink Mix", finalized.product_identity_fixed)
        self.assertEqual("Beverage > Mixes > Drink Mix", finalized.canonical_path)
        self.assertEqual("Green Apple > Unsweetened", finalized.modifier)
        self.assertEqual(
            "Beverage > Mixes > Drink Mix > Green Apple > Unsweetened",
            finalized.retail_leaf_path,
        )
        self.assert_clean(finalized)

    def test_alcohol_bfc_syrup_is_cocktail_syrup_not_pantry_sweetener(self):
        finalized = self.finalize(
            title="TRIPLE SEC SYRUP",
            branded_food_category="Alcohol",
            category_path_fixed="Pantry > Sweeteners",
            product_identity_fixed="Syrup",
            canonical_path="Pantry > Sweeteners > Syrup",
            variant="triple_sec",
        )

        self.assertEqual("Beverage > Cocktail Mixers", finalized.category_path_fixed)
        self.assertEqual("Cocktail Syrup", finalized.product_identity_fixed)
        self.assertEqual(
            "Beverage > Cocktail Mixers > Cocktail Syrup",
            finalized.canonical_path,
        )
        self.assertEqual("Triple Sec", finalized.modifier)
        self.assertEqual(
            "Beverage > Cocktail Mixers > Cocktail Syrup > Triple Sec",
            finalized.retail_leaf_path,
        )
        self.assert_clean(finalized)

    def test_alcohol_bfc_beer_salt_is_cocktail_rimmer_not_pantry_seasoning(self):
        finalized = self.finalize(
            title="LIME PREMIUM FLAVORED BEER SALT",
            branded_food_category="Alcohol",
            category_path_fixed="Pantry > Spices & Seasonings",
            product_identity_fixed="Seasoning",
            canonical_path="Pantry > Spices & Seasonings > Seasoning",
            flavor="lime",
        )

        self.assertEqual("Beverage > Cocktail Mixers", finalized.category_path_fixed)
        self.assertEqual("Cocktail Rimmer", finalized.product_identity_fixed)
        self.assertEqual(
            "Beverage > Cocktail Mixers > Cocktail Rimmer",
            finalized.canonical_path,
        )
        self.assertEqual("Lime", finalized.modifier)
        self.assertEqual(
            "Beverage > Cocktail Mixers > Cocktail Rimmer > Lime",
            finalized.retail_leaf_path,
        )
        self.assert_clean(finalized)

    def test_alcohol_bfc_bloody_mary_seasoning_is_cocktail_rimmer(self):
        finalized = self.finalize(
            title="BLOODY MARY SEASONING",
            branded_food_category="Alcohol",
            category_path_fixed="Pantry > Spices & Seasonings",
            product_identity_fixed="Seasoning",
            canonical_path="Pantry > Spices & Seasonings > Seasoning",
            variant="bloody_mary",
        )

        self.assertEqual("Beverage > Cocktail Mixers", finalized.category_path_fixed)
        self.assertEqual("Cocktail Rimmer", finalized.product_identity_fixed)
        self.assertEqual(
            "Beverage > Cocktail Mixers > Cocktail Rimmer > Bloody Mary",
            finalized.retail_leaf_path,
        )
        self.assert_clean(finalized)

    def test_alcohol_bfc_olive_brine_is_cocktail_brine(self):
        finalized = self.finalize(
            title="PREMIUM OLIVE BRINE",
            branded_food_category="Alcohol",
            category_path_fixed="Pantry > Sauces & Salsas",
            product_identity_fixed="Olive Brine",
            canonical_path="Pantry > Sauces & Salsas > Olive Brine",
        )

        self.assertEqual("Beverage > Cocktail Mixers", finalized.category_path_fixed)
        self.assertEqual("Cocktail Brine", finalized.product_identity_fixed)
        self.assertEqual(
            "Beverage > Cocktail Mixers > Cocktail Brine",
            finalized.canonical_path,
        )
        self.assert_clean(finalized)

    def test_alcohol_bfc_protein_shake_mix_is_beverage(self):
        finalized = self.finalize(
            title="PROTEIN SHAKE MIX, DUTCH CHOCOLATE",
            branded_food_category="Alcohol",
            category_path_fixed="Pantry > Mixes",
            product_identity_fixed="Chocolate Milk Mix",
            canonical_path="Pantry > Mixes > Chocolate Milk Mix",
            flavor="dutch_chocolate",
            claims="high_protein",
        )

        self.assertEqual("Beverage > Protein Drinks", finalized.category_path_fixed)
        self.assertEqual("Protein Shake Mix", finalized.product_identity_fixed)
        self.assertEqual(
            "Beverage > Protein Drinks > Protein Shake Mix > Dutch Chocolate > High Protein",
            finalized.retail_leaf_path,
        )
        self.assert_clean(finalized)

    def test_cocktail_rimming_sugar_is_not_baking_mix(self):
        finalized = self.finalize(
            title="COCKTAIL RIMMING SUGAR, LEMON",
            branded_food_category="Alcohol",
            category_path_fixed="Pantry > Baking Mixes",
            product_identity_fixed="Rimming Sugar",
            canonical_path="Pantry > Baking Mixes > Rimming Sugar",
            flavor="lemon",
        )

        self.assertEqual("Beverage > Cocktail Mixers", finalized.category_path_fixed)
        self.assertEqual("Cocktail Rimmer", finalized.product_identity_fixed)
        self.assertEqual(
            "Beverage > Cocktail Mixers > Cocktail Rimmer",
            finalized.canonical_path,
        )
        self.assertEqual("Lemon", finalized.modifier)
        self.assertEqual(
            "Beverage > Cocktail Mixers > Cocktail Rimmer > Lemon",
            finalized.retail_leaf_path,
        )
        self.assert_clean(finalized)

    def test_au_gratin_potatoes_are_not_baking_mix(self):
        finalized = self.finalize(
            title="POTATO CLASSICS, AU GRATIN POTATOES WITH A CREAMY SAUCE MIX, AU GRATIN",
            branded_food_category="Vegetable and Lentil Mixes",
            category_path_fixed="Pantry > Baking Mixes",
            product_identity_fixed="Potato Mix",
            canonical_path="Pantry > Baking Mixes > Potato Mix",
            variant="au_gratin",
        )

        self.assertEqual("Pantry > Packaged Sides", finalized.category_path_fixed)
        self.assertEqual("Potatoes", finalized.product_identity_fixed)
        self.assertEqual("Pantry > Packaged Sides > Potatoes", finalized.canonical_path)
        self.assertEqual("Au Gratin", finalized.modifier)
        self.assertEqual(
            "Pantry > Packaged Sides > Potatoes > Au Gratin",
            finalized.retail_leaf_path,
        )
        self.assert_clean(finalized)

    def test_sliced_reduced_sodium_potato_mix_keeps_facets_under_potatoes(self):
        finalized = self.finalize(
            title="DEHYDRATED REDUCED SODIUM AU GRATIN POTATO MIX",
            branded_food_category="Vegetable and Lentil Mixes",
            category_path_fixed="Pantry > Baking Mixes",
            product_identity_fixed="Potato Mix",
            canonical_path="Pantry > Baking Mixes > Potato Mix",
            variant="au_gratin",
            claims="reduced_sodium",
            form_texture_cut="sliced",
        )

        self.assertEqual("Pantry > Packaged Sides", finalized.category_path_fixed)
        self.assertEqual("Potatoes", finalized.product_identity_fixed)
        self.assertEqual("Pantry > Packaged Sides > Potatoes", finalized.canonical_path)
        self.assertEqual("Au Gratin > Reduced Sodium > Sliced", finalized.modifier)
        self.assertEqual(
            "Pantry > Packaged Sides > Potatoes > Au Gratin > Reduced Sodium > Sliced",
            finalized.retail_leaf_path,
        )
        self.assert_clean(finalized)

    def test_gravy_mix_is_not_baking_mix(self):
        finalized = self.finalize(
            title="BEEF FLAVORED INSTANT GRAVY MIX, BEEF",
            branded_food_category="Gravy Mix",
            category_path_fixed="Pantry > Baking Mixes",
            product_identity_fixed="Gravy Mix",
            canonical_path="Pantry > Baking Mixes > Gravy Mix",
            variant="beef",
        )

        self.assertEqual("Pantry > Gravy", finalized.category_path_fixed)
        self.assertEqual("Beef Gravy", finalized.product_identity_fixed)
        self.assertEqual("Pantry > Gravy > Beef Gravy", finalized.canonical_path)
        self.assert_clean(finalized)

    def test_hamburger_helper_is_meal_kit_not_baking_mix(self):
        finalized = self.finalize(
            title="Beef Pasta Hamburger Helper",
            branded_food_category="Baking/Cooking Mixes/Supplies",
            category_path_fixed="Pantry > Baking Mixes",
            product_identity_fixed="Hamburger Helper",
            canonical_path="Pantry > Baking Mixes > Hamburger Helper",
            variant="beef_pasta",
        )

        self.assertEqual("Pantry > Meal Kits", finalized.category_path_fixed)
        self.assertEqual("Hamburger Helper", finalized.product_identity_fixed)
        self.assertEqual("Pantry > Meal Kits > Hamburger Helper", finalized.canonical_path)
        self.assert_clean(finalized)

    def test_coating_mix_is_not_baking_mix(self):
        finalized = self.finalize(
            title="EXTRA CRISPY CROUSTILLANT COATING MIX, EXTRA CRISPY",
            branded_food_category="Seasoning Mixes, Salts, Marinades & Tenderizers",
            category_path_fixed="Pantry > Baking Mixes",
            product_identity_fixed="Coating Mix",
            canonical_path="Pantry > Baking Mixes > Coating Mix",
            variant="extra_crispy",
        )

        self.assertEqual("Pantry > Coatings & Breadings", finalized.category_path_fixed)
        self.assertEqual("Coating Mix", finalized.product_identity_fixed)
        self.assertEqual(
            "Pantry > Coatings & Breadings > Coating Mix",
            finalized.canonical_path,
        )
        self.assertEqual("Extra Crispy", finalized.modifier)
        self.assert_clean(finalized)

    def test_nori_is_not_baking_mix(self):
        finalized = self.finalize(
            title="RISING TIDE SEA VEGETABLES, ORGANIC RAW SUSHI NORI",
            branded_food_category="Vegetable and Lentil Mixes",
            category_path_fixed="Pantry > Baking Mixes",
            product_identity_fixed="Nori",
            canonical_path="Pantry > Baking Mixes > Nori",
            claims="organic",
            form_texture_cut="raw",
        )

        self.assertEqual("Pantry > Seaweed", finalized.category_path_fixed)
        self.assertEqual("Nori", finalized.product_identity_fixed)
        self.assertEqual("Pantry > Seaweed > Nori", finalized.canonical_path)
        self.assertEqual("Organic", finalized.modifier)
        self.assert_clean(finalized)

    def test_taco_shells_do_not_live_under_cookies(self):
        finalized = self.finalize(
            title="Old El Paso Stand 'N Stuff Zesty Ranch Flavored Taco Shells 10 Count",
            branded_food_category="Biscuits/Cookies",
            category_path_fixed="Bakery > Cookies",
            product_identity_fixed="Tortillas",
            canonical_path="Bakery > Cookies > Tortillas",
            variant="taco_shells_zesty_ranch",
        )

        self.assertEqual("Bakery > Tortillas", finalized.category_path_fixed)
        self.assertEqual("Taco Shells", finalized.product_identity_fixed)
        self.assertEqual("Bakery > Tortillas > Taco Shells", finalized.canonical_path)
        self.assertEqual("Zesty Ranch", finalized.modifier)
        self.assertEqual(
            "Bakery > Tortillas > Taco Shells > Zesty Ranch",
            finalized.retail_leaf_path,
        )
        self.assert_clean(finalized)

    def test_tortilla_wraps_do_not_live_under_cookies(self):
        finalized = self.finalize(
            title='Mexican Original 12" Tomato Flavored Press Flour Tortilla Wrap',
            branded_food_category="Biscuits/Cookies",
            category_path_fixed="Bakery > Cookies",
            product_identity_fixed="Tortillas",
            canonical_path="Bakery > Cookies > Tortillas",
            variant="tomato",
        )

        self.assertEqual("Bakery > Tortillas", finalized.category_path_fixed)
        self.assertEqual("Tortillas", finalized.product_identity_fixed)
        self.assertEqual("Bakery > Tortillas", finalized.canonical_path)
        self.assertEqual("Tomato", finalized.modifier)
        self.assertEqual("Bakery > Tortillas > Tomato", finalized.retail_leaf_path)
        self.assert_clean(finalized)

    def test_produce_salad_kit_is_not_croutons(self):
        finalized = self.finalize(
            title=(
                "CHOPPED CAESAR ROMAINE LETTUCE, PARMESAN CAESAR DRESSING, "
                "GRATED PARMESAN CHEESE, HERB SEASONED CROUTONS & CRACKED "
                "PEPPER SALAD KIT"
            ),
            branded_food_category="Pre-Packaged Fruit & Vegetables",
            category_path_fixed="Bakery > Croutons",
            product_identity_fixed="Croutons",
            canonical_path="Bakery > Croutons",
            variant="caesar_cracked_pepper",
            form_texture_cut="chopped",
        )

        self.assertEqual("Produce > Salad Kits", finalized.category_path_fixed)
        self.assertEqual("Salad Kit", finalized.product_identity_fixed)
        self.assertEqual("Produce > Salad Kits", finalized.canonical_path)
        self.assertEqual("Caesar Cracked Pepper > Chopped", finalized.modifier)
        self.assertEqual(
            "Produce > Salad Kits > Caesar Cracked Pepper > Chopped",
            finalized.retail_leaf_path,
        )
        self.assert_clean(finalized)

    def test_ice_cream_cake_is_frozen_not_bakery_cake(self):
        finalized = self.finalize(
            title="LIMITED EDITION PREMIUM ICE CREAM CAKE",
            branded_food_category="Cakes, Cupcakes, Snack Cakes",
            category_path_fixed="Bakery > Cake",
            product_identity_fixed="Cake",
            canonical_path="Bakery > Cake",
            variant="ice_cream",
            fndds_desc="ice cream cake",
            matched_key="ice cream cake",
        )

        self.assertEqual("Frozen > Ice Cream Cakes", finalized.category_path_fixed)
        self.assertEqual("Ice Cream Cake", finalized.product_identity_fixed)
        self.assertEqual("Frozen > Ice Cream Cakes", finalized.canonical_path)
        self.assert_clean(finalized)

    def test_ice_cream_bar_is_frozen_not_bakery_cookie(self):
        finalized = self.finalize(
            title="COOKIES 'N CREAM ICE CREAM BAR, COOKIES 'N CREAM",
            branded_food_category="Cookies & Biscuits",
            category_path_fixed="Bakery > Cookies",
            product_identity_fixed="Cookies",
            canonical_path="Bakery > Cookies",
            variant="cookies_n_cream",
            form_texture_cut="bar",
            fndds_desc="ice cream bar",
            matched_key="ice cream bar",
        )

        self.assertEqual("Frozen > Ice Cream Bars", finalized.category_path_fixed)
        self.assertEqual("Ice Cream Bar", finalized.product_identity_fixed)
        self.assertEqual("Frozen > Ice Cream Bars", finalized.canonical_path)
        self.assertEqual("Cookies N Cream", finalized.modifier)
        self.assert_clean(finalized)

    def test_cookie_bfc_does_not_pull_real_ice_cream_back_to_cookies(self):
        finalized = self.finalize(
            title="WESTERN FAMILY, COOKIES & CREAM, ARTIFICIALLY FLAVORED VANILLA ICE CREAM",
            branded_food_category="Cookies & Biscuits",
            category_path_fixed="Frozen > Ice Cream",
            product_identity_fixed="Ice Cream",
            canonical_path="Frozen > Ice Cream",
            variant="cookies_and_cream",
            flavor="vanilla",
            fndds_desc="ice cream vanilla",
            esha_desc="Ice Cream, vanilla",
            matched_key="ice cream vanilla",
        )

        self.assertEqual("Frozen > Ice Cream", finalized.category_path_fixed)
        self.assertEqual("Ice Cream", finalized.product_identity_fixed)
        self.assertEqual("Frozen > Ice Cream", finalized.canonical_path)
        self.assertEqual("Cookies And Cream Vanilla", finalized.modifier)
        self.assert_clean(finalized)

    def test_ice_cream_filled_cupcake_is_frozen_not_bakery_cupcake(self):
        finalized = self.finalize(
            title="SHOT CAKES, COOKIE DOUGH ICE CREAM FILLLED CUPCAKE, VANILLA ICE CREAM",
            branded_food_category="Cakes, Cupcakes, Snack Cakes",
            category_path_fixed="Bakery > Cupcakes",
            product_identity_fixed="Cupcakes",
            canonical_path="Bakery > Cupcakes",
            variant="cookie_dough|vanilla_ice_cream",
            fndds_desc="cake or cupcake",
            esha_desc="Cupcake, snack, chocolate, with cream filling",
        )

        self.assertEqual("Frozen > Ice Cream Cakes", finalized.category_path_fixed)
        self.assertEqual("Ice Cream Cake", finalized.product_identity_fixed)
        self.assertEqual("Frozen > Ice Cream Cakes", finalized.canonical_path)
        self.assertEqual("Cookie Dough Vanilla", finalized.modifier)
        self.assert_clean(finalized)

    def test_ice_cream_sandwich_is_frozen_not_meal_sandwich(self):
        finalized = self.finalize(
            title="VANILLA ICE CREAM SANDWICHES",
            branded_food_category="Ice Cream & Frozen Yogurt",
            category_path_fixed="Meal > Sandwiches",
            product_identity_fixed="Sandwich",
            canonical_path="Meal > Sandwiches > Sandwich",
            flavor="vanilla",
        )

        self.assertEqual("Frozen > Ice Cream Sandwiches", finalized.category_path_fixed)
        self.assertEqual("Ice Cream Sandwich", finalized.product_identity_fixed)
        self.assertEqual(
            "Frozen > Ice Cream Sandwiches > Ice Cream Sandwich",
            finalized.canonical_path,
        )
        self.assertEqual("Vanilla", finalized.modifier)
        self.assert_clean(finalized)

    def test_cookie_ice_cream_flavor_stays_cookie(self):
        finalized = self.finalize(
            title="NABISCO CHIPS AHOY! COOKIES CHEWY ICE CREAM CREATIONS ROCKY ROAD1X9.500 OZ",
            branded_food_category="Biscuits/Cookies",
            category_path_fixed="Bakery > Cookies",
            product_identity_fixed="Cookies",
            canonical_path="Bakery > Cookies",
            flavor="rocky_road|chocolate_chip",
            form_texture_cut="chewy",
            fndds_desc="Nabisco Chips Ahoy!",
            matched_key="cookies & cream ice cream",
        )

        self.assertEqual("Bakery > Cookies", finalized.category_path_fixed)
        self.assertEqual("Cookies", finalized.product_identity_fixed)
        self.assertEqual("Bakery > Cookies", finalized.canonical_path)
        self.assert_clean(finalized)

    def test_ice_cream_sundae_toaster_pastry_stays_pastry(self):
        finalized = self.finalize(
            title="FROSTED ICE CREAM SUNDAE FLAVORED TOASTER PASTRIES",
            branded_food_category="Croissants, Sweet Rolls, Muffins & Other Pastries",
            category_path_fixed="Bakery > Toaster Pastries",
            product_identity_fixed="Toaster Pastries",
            canonical_path="Bakery > Toaster Pastries",
            flavor="ice_cream_sundae",
            form_texture_cut="frosted",
            fndds_desc="pastry",
        )

        self.assertEqual("Bakery > Toaster Pastries", finalized.category_path_fixed)
        self.assertEqual("Toaster Pastries", finalized.product_identity_fixed)
        self.assertEqual("Bakery > Toaster Pastries", finalized.canonical_path)
        self.assert_clean(finalized)

    def test_ice_cream_cups_are_cones_not_bakery_cookies(self):
        finalized = self.finalize(
            title="GLUTEN FREE ICE CREAM CUPS",
            branded_food_category="Cookies & Biscuits",
            category_path_fixed="Bakery > Cookies",
            product_identity_fixed="Cookies",
            canonical_path="Bakery > Cookies",
            claims="gluten_free",
            matched_key="cookies & cream ice cream",
        )

        self.assertEqual("Snack > Ice Cream Cones", finalized.category_path_fixed)
        self.assertEqual("Ice Cream Cone", finalized.product_identity_fixed)
        self.assertEqual("Snack > Ice Cream Cones", finalized.canonical_path)
        self.assertEqual("Gluten Free", finalized.modifier)
        self.assert_clean(finalized)

    def test_breads_and_buns_sandwich_bread_is_not_prepared_sandwich(self):
        finalized = self.finalize(
            title="100% WHOLE WHEAT SANDWICH BREAD, 100% WHOLE WHEAT",
            branded_food_category="Breads & Buns",
            category_path_fixed="Meal > Sandwiches",
            product_identity_fixed="Sandwich",
            canonical_path="Meal > Sandwiches > Sandwich",
            variant="whole_wheat",
        )

        self.assertEqual("Bakery > Bread", finalized.category_path_fixed)
        self.assertEqual("Sandwich Bread", finalized.product_identity_fixed)
        self.assertEqual("Bakery > Bread > Sandwich Bread", finalized.canonical_path)
        self.assertEqual("Whole Wheat", finalized.modifier)
        self.assert_clean(finalized)

    def test_breads_and_buns_hamburger_rolls_are_buns_not_hamburgers(self):
        finalized = self.finalize(
            title="ENRICHED WHITE SESAME SEED HAMBURGER ROLLS, WHITE",
            branded_food_category="Breads & Buns",
            category_path_fixed="Meal > Sandwiches",
            product_identity_fixed="Hamburger",
            canonical_path="Meal > Sandwiches > Hamburger",
            variant="sesame_seed",
        )

        self.assertEqual("Bakery > Buns", finalized.category_path_fixed)
        self.assertEqual("Hamburger Buns", finalized.product_identity_fixed)
        self.assertEqual("Bakery > Buns > Hamburger Buns", finalized.canonical_path)
        self.assertEqual("Sesame Seed", finalized.modifier)
        self.assert_clean(finalized)

    def test_prepared_sub_does_not_keep_sandwich_roll_identity(self):
        finalized = self.finalize(
            title="CHICKEN PROVANCE ON SEEDED ITALIAN ROLL SUB SANDWICH",
            branded_food_category="Prepared Subs & Sandwiches",
            category_path_fixed="Meal > Sandwiches",
            product_identity_fixed="Sandwich Rolls",
            canonical_path="Meal > Sandwiches > Sandwich Rolls",
            variant="chicken_provance_seeded_italian",
        )

        self.assertEqual("Meal > Sandwiches", finalized.category_path_fixed)
        self.assertEqual("Sub Sandwich", finalized.product_identity_fixed)
        self.assertEqual("Meal > Sandwiches > Sub Sandwich", finalized.canonical_path)
        self.assertEqual("Chicken Provance Seeded Italian", finalized.modifier)
        self.assert_clean(finalized)

    def test_almondmilk_creamer_is_creamer_not_plant_milk(self):
        finalized = self.finalize(
            title="VANILLA ALMONDMILK CREAMER WITH COCONUT CREAM, VANILLA",
            branded_food_category="Milk Additives",
            category_path_fixed="Beverage > Plant Milk",
            product_identity_fixed="Almond Milk",
            canonical_path="Beverage > Plant Milk > Almond Milk",
            flavor="vanilla",
        )

        self.assertEqual("Beverage > Coffee Creamer", finalized.category_path_fixed)
        self.assertEqual("Coffee Creamer", finalized.product_identity_fixed)
        self.assertEqual("Beverage > Coffee Creamer", finalized.canonical_path)
        self.assertEqual("Vanilla", finalized.modifier)
        self.assert_clean(finalized)

    def test_churro_coffee_creamer_is_not_bakery_churro(self):
        finalized = self.finalize(
            title="CINNAMON CHURRO COFFEE CREAMER",
            branded_food_category="Milk Additives",
            category_path_fixed="Bakery > Pastry > Churros",
            product_identity_fixed="Churros",
            canonical_path="Bakery > Pastry > Churros",
            flavor="cinnamon_churro",
        )

        self.assertEqual("Beverage > Coffee Creamer", finalized.category_path_fixed)
        self.assertEqual("Coffee Creamer", finalized.product_identity_fixed)
        self.assertEqual("Beverage > Coffee Creamer", finalized.canonical_path)
        self.assertEqual("Cinnamon Churro", finalized.modifier)
        self.assert_clean(finalized)

    def test_biscotti_ground_coffee_is_coffee_not_biscotti(self):
        finalized = self.finalize(
            title="INDULGENT BLENDS CHOCOLATE RASPBERRY BISCOTTI GROUND COFFEE",
            branded_food_category="Coffee",
            category_path_fixed="Bakery > Biscotti",
            product_identity_fixed="Biscotti",
            canonical_path="Bakery > Biscotti",
            flavor="chocolate_raspberry",
        )

        self.assertEqual("Beverage > Coffee", finalized.category_path_fixed)
        self.assertEqual("Ground Coffee", finalized.product_identity_fixed)
        self.assertEqual("Beverage > Coffee > Ground Coffee", finalized.canonical_path)
        self.assertEqual("Chocolate Raspberry", finalized.modifier)
        self.assert_clean(finalized)

    def test_charcuterie_roll_and_go_is_not_bakery_roll(self):
        finalized = self.finalize(
            title="ROLL & GO PROSCIUTTO AND MOZZARELLA, 8 COUNT, 5 OZ",
            branded_food_category="Pepperoni, Salami & Cold Cuts",
            category_path_fixed="Bakery > Rolls",
            product_identity_fixed="Rolls",
            canonical_path="Bakery > Rolls",
            variant="prosciutto_mozzarella",
        )

        self.assertEqual("Meat & Seafood > Charcuterie", finalized.category_path_fixed)
        self.assertEqual("Charcuterie Rolls", finalized.product_identity_fixed)
        self.assertEqual(
            "Meat & Seafood > Charcuterie > Charcuterie Rolls",
            finalized.canonical_path,
        )
        self.assertEqual("Prosciutto Mozzarella", finalized.modifier)
        self.assert_clean(finalized)

    def test_snack_sandwich_bar_is_still_snack_bar(self):
        finalized = self.finalize(
            title="CINNAMON OAT & APPLE SOFT-BAKED SANDWICH BREAKFAST BARS",
            branded_food_category="Snack, Energy & Granola Bars",
            category_path_fixed="Meal > Sandwiches",
            product_identity_fixed="Breakfast Bars",
            canonical_path="Meal > Sandwiches > Breakfast Bars",
            variant="cinnamon_oat_apple",
        )

        self.assertEqual("Snack > Bars", finalized.category_path_fixed)
        self.assertEqual("Breakfast Bars", finalized.product_identity_fixed)
        self.assertEqual("Snack > Bars > Breakfast Bars", finalized.canonical_path)
        self.assertEqual("Cinnamon Oat Apple", finalized.modifier)
        self.assert_clean(finalized)

    def test_salmon_bar_is_not_fish_shelf(self):
        finalized = self.finalize(
            title="SALMON SEA SALT-PEPPER BAR",
            branded_food_category="Snack, Energy & Granola Bars",
            category_path_fixed="Meat & Seafood > Fish",
            product_identity_fixed="Salmon",
            canonical_path="Meat & Seafood > Fish > Salmon",
            flavor="pepper",
        )

        self.assertEqual("Snack > Bars", finalized.category_path_fixed)
        self.assertEqual("Snack Bar", finalized.product_identity_fixed)
        self.assertEqual("Snack > Bars", finalized.canonical_path)
        self.assertEqual("Pepper", finalized.modifier)
        self.assert_clean(finalized)

    def test_churro_cereal_is_cereal_not_churros(self):
        finalized = self.finalize(
            title="Churros Cinnamon Toast Crunch Cereal",
            branded_food_category="Processed Cereal Products",
            category_path_fixed="Bakery > Pastry > Churros",
            product_identity_fixed="Churros",
            canonical_path="Bakery > Pastry > Churros",
            flavor="cinnamon_toast_crunch",
        )

        self.assertEqual("Pantry > Cereal", finalized.category_path_fixed)
        self.assertEqual("Cereal", finalized.product_identity_fixed)
        self.assertEqual("Pantry > Cereal", finalized.canonical_path)
        self.assertEqual("Cinnamon Toast Crunch", finalized.modifier)
        self.assert_clean(finalized)

    def test_churro_cornbread_mix_is_baking_mix_not_churro(self):
        finalized = self.finalize(
            title="Old El Paso Cinnamon Churro Cornbread Mix",
            branded_food_category="Baking/Cooking Mixes/Supplies",
            category_path_fixed="Bakery > Pastry > Churros",
            product_identity_fixed="Churros",
            canonical_path="Bakery > Pastry > Churros",
            flavor="cinnamon_churro",
        )

        self.assertEqual("Pantry > Baking Mixes", finalized.category_path_fixed)
        self.assertEqual("Cornbread Mix", finalized.product_identity_fixed)
        self.assertEqual("Pantry > Baking Mixes > Cornbread Mix", finalized.canonical_path)
        self.assertEqual("Cinnamon Churro", finalized.modifier)
        self.assert_clean(finalized)

    def test_churro_banana_bites_are_fruit_snack_not_churro_identity(self):
        finalized = self.finalize(
            title="CINNAMON CHURRO BANANA BITES, CINNAMON CHURRO",
            branded_food_category="Wholesome Snacks",
            category_path_fixed="Bakery > Pastry > Churros",
            product_identity_fixed="Churros",
            canonical_path="Bakery > Pastry > Churros",
            flavor="cinnamon_churro",
        )

        self.assertEqual("Snack > Fruit Snacks", finalized.category_path_fixed)
        self.assertEqual("Banana Bites", finalized.product_identity_fixed)
        self.assertEqual("Snack > Fruit Snacks > Banana Bites", finalized.canonical_path)
        self.assertEqual("Cinnamon Churro", finalized.modifier)
        self.assert_clean(finalized)

    def test_churro_cupcakes_are_cupcakes_not_churro_identity(self):
        finalized = self.finalize(
            title="CINNAMON CHURRO HANDCRAFTED CUPCAKES, CINNAMON CHURRO",
            branded_food_category="Cakes, Cupcakes, Snack Cakes",
            category_path_fixed="Bakery > Pastry > Churros",
            product_identity_fixed="Churros",
            canonical_path="Bakery > Pastry > Churros",
            flavor="cinnamon_churro",
        )

        self.assertEqual("Bakery > Cupcakes", finalized.category_path_fixed)
        self.assertEqual("Cupcakes", finalized.product_identity_fixed)
        self.assertEqual("Bakery > Cupcakes", finalized.canonical_path)
        self.assertEqual("Cinnamon Churro", finalized.modifier)
        self.assert_clean(finalized)

    def test_farro_is_grain_not_baking_mix(self):
        finalized = self.finalize(
            title="ALL NATURAL FOUR CHEESE FARRO",
            branded_food_category="Vegetable and Lentil Mixes",
            category_path_fixed="Pantry > Baking Mixes",
            product_identity_fixed="Farro Mix",
            canonical_path="Pantry > Baking Mixes > Farro Mix",
            variant="four_cheese",
        )

        self.assertEqual("Pantry > Rice & Grains", finalized.category_path_fixed)
        self.assertEqual("Farro", finalized.product_identity_fixed)
        self.assertEqual("Pantry > Rice & Grains > Farro", finalized.canonical_path)
        self.assertEqual("Four Cheese", finalized.modifier)
        self.assert_clean(finalized)

    def test_dried_mushrooms_are_not_baking_mix(self):
        finalized = self.finalize(
            title="MARDONA, DRIED MOREL MUSHROOMS",
            branded_food_category="Vegetable and Lentil Mixes",
            category_path_fixed="Pantry > Baking Mixes",
            product_identity_fixed="Dried Morel Mushrooms",
            canonical_path="Pantry > Baking Mixes > Dried Morel Mushrooms",
        )

        self.assertEqual("Pantry > Dried Vegetables", finalized.category_path_fixed)
        self.assertEqual("Dried Mushrooms", finalized.product_identity_fixed)
        self.assertEqual(
            "Pantry > Dried Vegetables > Dried Mushrooms",
            finalized.canonical_path,
        )
        self.assert_clean(finalized)

    def test_toor_dal_is_bean_not_baking_mix(self):
        finalized = self.finalize(
            title="TOOR DAL SPLIT PIGEON PEAS",
            branded_food_category="Vegetable and Lentil Mixes",
            category_path_fixed="Pantry > Baking Mixes",
            product_identity_fixed="Peas",
            canonical_path="Pantry > Baking Mixes > Peas",
            form_texture_cut="split",
        )

        self.assertEqual("Pantry > Beans", finalized.category_path_fixed)
        self.assertEqual("Toor Dal", finalized.product_identity_fixed)
        self.assertEqual("Pantry > Beans > Toor Dal", finalized.canonical_path)
        self.assertEqual("Split", finalized.modifier)
        self.assert_clean(finalized)

    def test_potato_pancake_mix_is_packaged_side_not_baking_mix(self):
        finalized = self.finalize(
            title="HOMESTYLE POTATO LATKE MIX",
            branded_food_category="Vegetable and Lentil Mixes",
            category_path_fixed="Pantry > Baking Mixes",
            product_identity_fixed="Pancake Mix",
            canonical_path="Pantry > Baking Mixes > Pancake Mix",
            variant="potato_latke",
        )

        self.assertEqual("Pantry > Packaged Sides", finalized.category_path_fixed)
        self.assertEqual("Potato Pancake Mix", finalized.product_identity_fixed)
        self.assertEqual(
            "Pantry > Packaged Sides > Potato Pancake Mix",
            finalized.canonical_path,
        )
        self.assertEqual("Latke", finalized.modifier)
        self.assert_clean(finalized)

    def test_wasabi_peas_are_snack_not_baking_mix(self):
        finalized = self.finalize(
            title="WASABI PEAS, WASABI",
            branded_food_category="Vegetable and Lentil Mixes",
            category_path_fixed="Pantry > Baking Mixes",
            product_identity_fixed="Veggie Snacks",
            canonical_path="Pantry > Baking Mixes > Veggie Snacks",
            flavor="wasabi",
        )

        self.assertEqual("Snack > Veggie Snacks", finalized.category_path_fixed)
        self.assertEqual("Wasabi Peas", finalized.product_identity_fixed)
        self.assertEqual("Snack > Veggie Snacks > Wasabi Peas", finalized.canonical_path)
        self.assertEqual("Plain", finalized.modifier)
        self.assert_clean(finalized)

    def test_churro_protein_powder_is_protein_powder_not_pastry(self):
        finalized = self.finalize(
            title="ORGANIC PROTEIN POWDER, CHURRO CARAMEL SWIRL",
            branded_food_category="Energy, Protein & Muscle Recovery Drinks",
            category_path_fixed="Bakery > Pastry > Churros",
            product_identity_fixed="Churros",
            canonical_path="Bakery > Pastry > Churros",
            flavor="churro_caramel_swirl",
            claims="organic|high_protein",
        )

        self.assertEqual("Sports & Wellness > Protein Powders", finalized.category_path_fixed)
        self.assertEqual("Protein Powder", finalized.product_identity_fixed)
        self.assertEqual("Sports & Wellness > Protein Powders", finalized.canonical_path)
        self.assertEqual("Churro Caramel Swirl > Organic > High Protein", finalized.modifier)
        self.assert_clean(finalized)

    def test_frozen_churros_are_frozen_not_bakery_pastry(self):
        finalized = self.finalize(
            title="CHURROS WITH DULCE DE LECHE",
            branded_food_category="Frozen Bread & Dough",
            category_path_fixed="Bakery > Pastry > Churros",
            product_identity_fixed="Churros",
            canonical_path="Bakery > Pastry > Churros",
            flavor="dulce_de_leche",
        )

        self.assertEqual("Frozen > Churros", finalized.category_path_fixed)
        self.assertEqual("Churros", finalized.product_identity_fixed)
        self.assertEqual("Frozen > Churros", finalized.canonical_path)
        self.assertEqual("Dulce De Leche", finalized.modifier)
        self.assert_clean(finalized)


if __name__ == "__main__":
    unittest.main()
