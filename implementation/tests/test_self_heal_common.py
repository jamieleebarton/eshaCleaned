from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

IMPL = Path(__file__).resolve().parents[1]
if str(IMPL) not in sys.path:
    sys.path.insert(0, str(IMPL))

import self_heal_common as self_heal
import self_heal_policy as policy


class SelfHealRetailRoutingTests(unittest.TestCase):
    def test_wholesome_snack_fruit_uses_fruit_lane_not_generic_snack(self) -> None:
        title_tokens = {"roundy", "large", "apricot"}

        lane = self_heal.category_lane_for("ROUNDY'S, LARGE APRICOTS", "Wholesome Snacks", title_tokens)
        form = self_heal.product_form_for("ROUNDY'S, LARGE APRICOTS", "Wholesome Snacks", lane, title_tokens)
        heads = self_heal.target_heads_for(lane, form, "main", title_tokens)

        self.assertEqual(lane, "fruit")
        self.assertEqual(form, "apricot")
        self.assertIn("Apricot", heads)
        self.assertNotIn("Chips", heads)
        self.assertNotIn("Biscuit", heads)

    def test_donut_flavor_ice_cream_stays_frozen_dessert(self) -> None:
        title_tokens = {"ice", "cream", "coffee", "donut"}

        lane = self_heal.category_lane_for("COFFEE & DONUT ICE CREAM, COFFEE & DONUT", "Ice Cream & Frozen Yogurt", title_tokens)
        form = self_heal.product_form_for("COFFEE & DONUT ICE CREAM, COFFEE & DONUT", "Ice Cream & Frozen Yogurt", lane, title_tokens)
        heads = self_heal.target_heads_for(lane, form, "main", title_tokens)
        category_ok, _ = policy.category_allows_head(
            category="Ice Cream & Frozen Yogurt",
            product_description="COFFEE & DONUT ICE CREAM, COFFEE & DONUT",
            title_tokens=title_tokens,
            candidate_head="Doughnut",
        )

        self.assertEqual(lane, "frozen_dessert")
        self.assertEqual(form, "ice_cream")
        self.assertEqual(heads, ("Ice Cream",))
        self.assertFalse(category_ok)

    def test_donut_brand_coffee_stays_coffee(self) -> None:
        title_tokens = {"original", "donut", "shop", "coffee", "maple", "cream"}

        lane = self_heal.category_lane_for("THE ORIGINAL DONUT SHOP, SWEET & CREAMY MEDIUM ROAST COFFEE", "Coffee", title_tokens)
        form = self_heal.product_form_for("THE ORIGINAL DONUT SHOP, SWEET & CREAMY MEDIUM ROAST COFFEE", "Coffee", lane, title_tokens)
        heads = self_heal.target_heads_for(lane, form, "main", title_tokens)

        self.assertEqual(lane, "coffee")
        self.assertEqual(form, "coffee")
        self.assertEqual(heads, ("Coffee", "Drink"))

    def test_beef_bouillon_cubes_stay_bouillon_not_beef(self) -> None:
        desc = "BEEF BOUILLON CUBES, BEEF"
        title_tokens = {"beef", "bouillon", "cube"}

        lane = self_heal.category_lane_for(desc, "Seasoning Mixes, Salts, Marinades & Tenderizers", title_tokens)
        form = self_heal.product_form_for(desc, "Seasoning Mixes, Salts, Marinades & Tenderizers", lane, title_tokens)
        heads = self_heal.target_heads_for(lane, form, "main", title_tokens)
        category_ok, _ = policy.category_allows_head(
            category="Seasoning Mixes, Salts, Marinades & Tenderizers",
            product_description=desc,
            title_tokens=title_tokens,
            candidate_head="Beef",
        )

        self.assertEqual(lane, "seasoning")
        self.assertEqual(form, "bouillon")
        self.assertEqual(heads, ("Bouillon", "Broth", "Base"))
        self.assertFalse(category_ok)
        self.assertEqual(
            self_heal.bouillon_form_mismatch_reason(form, title_tokens, "Beef, cubes, frozen, 4oz, FS"),
            "bouillon_product_to_non_bouillon",
        )
        self.assertEqual(
            self_heal.bouillon_form_mismatch_reason(form, title_tokens, "Bouillon, beef flavor, dry cube"),
            "",
        )

    def test_cheesecake_flavored_yogurt_smoothie_does_not_become_cake(self) -> None:
        desc = "STRAWBERRY CHEESECAKE CRAVEABLES YOGURT SMOOTHIE, STRAWBERRY CHEESECAKE"
        title_tokens = {"strawberry", "cheesecake", "craveables", "yogurt", "smoothie"}

        lane = self_heal.category_lane_for(desc, "Yogurt", title_tokens)
        form = self_heal.product_form_for(desc, "Yogurt", lane, title_tokens)
        heads = self_heal.target_heads_for(lane, form, "main", title_tokens)
        category_ok, _ = policy.category_allows_head(
            category="Yogurt",
            product_description=desc,
            title_tokens=title_tokens,
            candidate_head="Cake",
        )

        self.assertEqual(lane, "yogurt")
        self.assertEqual(form, "yogurt_smoothie")
        self.assertEqual(heads, ("Yogurt", "Smoothie", "Drink"))
        self.assertFalse(category_ok)
        self.assertNotIn("Cake", heads)

    def test_yogurt_parfait_targets_parfait_or_yogurt_not_cake(self) -> None:
        desc = "STRAWBERRY CHEESECAKE PARFAIT WITH FRESH STRAWBERRIES, STRAWBERRY CHEESECAKE"
        title_tokens = {"strawberry", "cheesecake", "parfait", "fresh", "strawberries"}

        lane = self_heal.category_lane_for(desc, "Yogurt", title_tokens)
        form = self_heal.product_form_for(desc, "Yogurt", lane, title_tokens)
        heads = self_heal.target_heads_for(lane, form, "main", title_tokens)

        self.assertEqual(lane, "yogurt")
        self.assertEqual(form, "yogurt_parfait")
        self.assertEqual(heads, ("Parfait", "Yogurt"))
        self.assertNotIn("Cake", heads)

    def test_plain_brownie_targets_brownie_not_frozen_dessert(self) -> None:
        desc = "SOFT-BAKED FUDGE BROWNIE"
        title_tokens = {"soft", "baked", "fudge", "brownie"}

        lane = self_heal.category_lane_for(desc, "Cakes, Cupcakes, Snack Cakes", title_tokens)
        form = self_heal.product_form_for(desc, "Cakes, Cupcakes, Snack Cakes", lane, title_tokens)
        heads = self_heal.target_heads_for(lane, form, "main", title_tokens)

        self.assertEqual(lane, "dessert")
        self.assertEqual(form, "brownie")
        self.assertEqual(heads, ("Brownie",))
        self.assertEqual(
            self_heal.brownie_form_mismatch_reason(form, "Dessert, brownie with lowfat vanilla ice cream & fudge sauce, frozen"),
            "",
        )
        self.assertEqual(
            self_heal.brownie_form_mismatch_reason(form, "Cake, chocolate"),
            "brownie_form_mismatch:brownie->non_brownie",
        )

    def test_brownie_mix_targets_brownie_mix_codes(self) -> None:
        desc = "Betty Crocker Delights Salted Caramel Brownie Mix"
        title_tokens = {"betty", "crocker", "delights", "salted", "caramel", "brownie", "mix"}

        lane = self_heal.category_lane_for(desc, "Baking/Cooking Mixes/Supplies", title_tokens)
        form = self_heal.product_form_for(desc, "Baking/Cooking Mixes/Supplies", lane, title_tokens)
        heads = self_heal.target_heads_for(lane, form, "main", title_tokens)

        self.assertEqual(lane, "baking_mix")
        self.assertEqual(form, "brownie_mix")
        self.assertEqual(heads, ("Brownie", "Cake", "Baking Mix"))
        self.assertEqual(self_heal.brownie_form_mismatch_reason(form, "Brownie, fudge, dry mix"), "")
        self.assertEqual(
            self_heal.brownie_form_mismatch_reason(form, "Brownie, fudge"),
            "brownie_form_mismatch:brownie_mix->not_dry_mix",
        )

    def test_brownie_flavored_gelato_stays_ice_cream(self) -> None:
        desc = "FUDGE BROWNIE GELATO, FUDGE BROWNIE"
        title_tokens = {"fudge", "brownie", "gelato"}

        lane = self_heal.category_lane_for(desc, "Ice Cream & Frozen Yogurt", title_tokens)
        form = self_heal.product_form_for(desc, "Ice Cream & Frozen Yogurt", lane, title_tokens)
        heads = self_heal.target_heads_for(lane, form, "main", title_tokens)
        category_ok, _ = policy.category_allows_head(
            category="Ice Cream & Frozen Yogurt",
            product_description=desc,
            title_tokens=title_tokens,
            candidate_head="Brownie",
        )

        self.assertEqual(lane, "frozen_dessert")
        self.assertEqual(form, "ice_cream")
        self.assertEqual(heads, ("Ice Cream",))
        self.assertFalse(category_ok)

    def test_brownie_flavored_nutrition_bar_stays_bar(self) -> None:
        desc = "NUTRITION BARS, FUDGE BROWNIE"
        title_tokens = {"nutrition", "bars", "fudge", "brownie"}

        lane = self_heal.category_lane_for(desc, "Snack, Energy & Granola Bars", title_tokens)
        form = self_heal.product_form_for(desc, "Snack, Energy & Granola Bars", lane, title_tokens)
        heads = self_heal.target_heads_for(lane, form, "main", title_tokens)

        self.assertEqual(lane, "bar_snack")
        self.assertEqual(form, "bar")
        self.assertEqual(heads, ("Bar",))
        self.assertNotIn("Brownie", heads)

    def test_peanut_butter_cups_do_not_route_as_crackers_or_brownies(self) -> None:
        desc = "DARK CHOCOLATE MINT REFRIGERATED PEANUT BUTTER CUPS, DARK CHOCOLATE MINT"
        title_tokens = {"dark", "chocolate", "mint", "refrigerated", "peanut", "butter", "cups"}

        lane = self_heal.category_lane_for(desc, "Snack, Energy & Granola Bars", title_tokens)
        form = self_heal.product_form_for(desc, "Snack, Energy & Granola Bars", lane, title_tokens)
        heads = self_heal.target_heads_for(lane, form, "main", title_tokens)

        self.assertEqual(lane, "candy_chocolate")
        self.assertEqual(form, "peanut_butter_cup")
        self.assertEqual(heads, ("Candy", "Chocolate", "Candy Bar"))
        self.assertNotIn("Cracker", heads)
        self.assertNotIn("Brownie", heads)

    def test_dessert_fondue_sauce_uses_topping_lane_not_cookie(self) -> None:
        desc = "TOFFEE FONDUE SAUCE, DARK CHOCOLATE PEANUT BUTTER"
        title_tokens = {"toffee", "fondue", "sauce", "dark", "chocolate", "peanut", "butter"}

        lane = self_heal.category_lane_for(desc, "Baking Decorations & Dessert Toppings", title_tokens)
        form = self_heal.product_form_for(desc, "Baking Decorations & Dessert Toppings", lane, title_tokens)
        heads = self_heal.target_heads_for(lane, form, "main", title_tokens)

        self.assertEqual(lane, "dessert_topping")
        self.assertEqual(form, "dessert_topping")
        self.assertEqual(heads, ("Dessert Topping", "Topping", "Sauce", "Syrup"))
        self.assertNotIn("Cookie", heads)

    def test_cream_cheese_targets_cream_cheese_not_generic_cheddar(self) -> None:
        desc = "PLAIN CREAM CHEESE, PLAIN"
        title_tokens = {"plain", "cream", "cheese"}

        lane = self_heal.category_lane_for(desc, "Cheese", title_tokens)
        form = self_heal.product_form_for(desc, "Cheese", lane, title_tokens)
        heads = self_heal.target_heads_for(lane, form, "main", title_tokens)

        self.assertEqual(lane, "cheese")
        self.assertEqual(form, "cream_cheese")
        self.assertEqual(heads, ("Cream Cheese",))
        self.assertEqual(
            self_heal.cheese_form_mismatch_reason(form, {"cream", "cheese"}, 'Cheese, cheddar, salsa, 1" cube'),
            "cream_cheese_product_to_non_cream_cheese",
        )
        self.assertEqual(self_heal.cheese_form_mismatch_reason(form, {"cream", "cheese"}, "Cream Cheese, plain"), "")

    def test_cheese_food_targets_cheese_food(self) -> None:
        desc = "CHEESE FOOD"
        title_tokens = {"cheese"}

        lane = self_heal.category_lane_for(desc, "Cheese", title_tokens)
        form = self_heal.product_form_for(desc, "Cheese", lane, title_tokens)
        heads = self_heal.target_heads_for(lane, form, "main", title_tokens)

        self.assertEqual(lane, "cheese")
        self.assertEqual(form, "cheese_food")
        self.assertEqual(heads, ("Cheese Food", "Cheese"))
        self.assertEqual(
            self_heal.cheese_form_mismatch_reason(form, {"cheese"}, 'Cheese, cheddar, salsa, 1" cube'),
            "cheese_food_product_to_non_cheese_food",
        )

    def test_generic_cheese_rejects_unasked_salsa_cheddar_subtype(self) -> None:
        self.assertEqual(
            self_heal.cheese_form_mismatch_reason("cheese", {"cheese"}, 'Cheese, cheddar, salsa, 1" cube'),
            "cheese_unasked_subtype:cheddar,cube,salsa",
        )
        self.assertEqual(
            self_heal.cheese_form_mismatch_reason("cheese", {"cheese", "cheddar"}, "Cheese, cheddar"),
            "",
        )

    def test_tomato_basil_cheese_requires_declared_cheese_subtype(self) -> None:
        self.assertEqual(
            self_heal.cheese_form_mismatch_reason(
                "cheese",
                {"cheese", "tomato", "basil", "feta"},
                "Cheese, tomato basil, wheel",
            ),
            "cheese_missing_product_subtype:feta",
        )
        self.assertEqual(
            self_heal.cheese_form_mismatch_reason(
                "cheese",
                {"cheese", "tomato", "basil", "havarti"},
                "Cheese, havarti, creamy, plain",
            ),
            "",
        )
        self.assertEqual(
            self_heal.cheese_form_mismatch_reason(
                "cheese",
                {"cheese", "tomato", "basil", "goat"},
                "Cheese, feta, basil & tomato, crumbles",
            ),
            "cheese_missing_product_subtype:goat",
        )

    def test_stuffed_olives_with_feta_are_olives_not_cheese(self) -> None:
        desc = "GREEK STUFFED OLIVES, FETA CHEESE"
        title_tokens = {"greek", "stuffed", "olif", "feta", "cheese"}

        lane = self_heal.category_lane_for(desc, "Pickles, Olives, Peppers & Relishes", title_tokens)
        form = self_heal.product_form_for(desc, "Pickles, Olives, Peppers & Relishes", lane, title_tokens)
        heads = self_heal.target_heads_for(lane, form, "main", title_tokens)
        category_ok, _ = policy.category_allows_head(
            category="Pickles, Olives, Peppers & Relishes",
            product_description=desc,
            title_tokens=title_tokens,
            candidate_head="Cheese",
        )

        self.assertEqual(lane, "pickles_relish")
        self.assertEqual(form, "olives")
        self.assertEqual(heads, ("Olives",))
        self.assertFalse(category_ok)

    def test_doughnut_head_requires_title_support(self) -> None:
        self.assertIsNotNone(
            policy.narrow_head_requires_title_support("Doughnut", {"dutch", "creme", "curls"}, "DUTCH CREME CURLS")
        )
        self.assertIsNone(
            policy.narrow_head_requires_title_support("Doughnut", {"donut", "bites"}, "DONUT BITES")
        )

    def test_crusts_dough_biscuits_route_to_biscuit_not_doughnut(self) -> None:
        title_tokens = {"jumbo", "flaky", "biscuits", "butter"}

        lane = self_heal.category_lane_for("JUMBO FLAKY BISCUITS, BUTTER", "Crusts & Dough", title_tokens)
        form = self_heal.product_form_for("JUMBO FLAKY BISCUITS, BUTTER", "Crusts & Dough", lane, title_tokens)
        heads = self_heal.target_heads_for(lane, form, "main", title_tokens)

        self.assertEqual(lane, "pastry")
        self.assertEqual(form, "biscuit")
        self.assertEqual(heads, ("Biscuit",))

    def test_potato_salad_with_mayo_dressing_routes_to_salad(self) -> None:
        desc = "HOMESTYLE RUSSET POTATOES & ONIONS IN A CREAMY MAYONNAISE DRESSING POTATO SALAD, HOMESTYLE"
        title_tokens = {"homestyle", "russet", "potatoes", "onions", "creamy", "mayonnaise", "dressing", "potato", "salad"}

        lane = self_heal.category_lane_for(desc, "Pickles, Olives, Peppers & Relishes", title_tokens)
        form = self_heal.product_form_for(desc, "Pickles, Olives, Peppers & Relishes", lane, title_tokens)
        heads = self_heal.target_heads_for(lane, form, "main", title_tokens)

        self.assertEqual(lane, "deli_salad")
        self.assertEqual(form, "potato_salad")
        self.assertEqual(heads, ("Salad",))

    def test_seafood_salad_in_dips_category_allows_salad_head(self) -> None:
        desc = "SOUTHWESTERN STYLE IMITATION CRAB IN A CREAMY SPICY DRESSING SEAFOOD SALAD"
        title_tokens = {"southwestern", "imitation", "crab", "creamy", "spicy", "dressing", "seafood", "salad"}

        lane = self_heal.category_lane_for(desc, "Dips & Salsa", title_tokens)
        form = self_heal.product_form_for(desc, "Dips & Salsa", lane, title_tokens)
        heads = self_heal.target_heads_for(lane, form, "main", title_tokens)
        category_ok, _ = policy.category_allows_head(
            category="Dips & Salsa",
            product_description=desc,
            title_tokens=title_tokens,
            candidate_head="Salad",
        )

        self.assertEqual(lane, "deli_salad")
        self.assertEqual(form, "salad")
        self.assertEqual(heads, ("Salad",))
        self.assertTrue(category_ok)

    def test_bbq_sauce_cannot_use_pasta_sauce_anchor(self) -> None:
        desc = "BBQ SAUCE"
        title_tokens = {"bbq", "sauce"}

        lane = self_heal.category_lane_for(desc, "Ketchup, Mustard, BBQ & Cheese Sauce", title_tokens)
        form = self_heal.product_form_for(desc, "Ketchup, Mustard, BBQ & Cheese Sauce", lane, title_tokens)
        heads = self_heal.target_heads_for(lane, form, "main", title_tokens)

        self.assertEqual(lane, "sauce_condiment")
        self.assertEqual(form, "barbecue_sauce")
        self.assertEqual(heads, ("Sauce",))
        self.assertEqual(
            self_heal.sauce_form_mismatch_reason(form, "Sauce, pasta, roasted red pepper & garlic"),
            "sauce_subtype_mismatch:barbecue_sauce",
        )
        self.assertEqual(self_heal.sauce_form_mismatch_reason(form, "Sauce, barbecue, original"), "")

    def test_buffalo_hotsauce_cannot_use_pasta_sauce_anchor(self) -> None:
        desc = "GARLIC SESAME GOCHU JANG KOREAN HOTSAUCE, GARLIC SESAME"
        title_tokens = {"garlic", "sesame", "gochu", "jang", "korean", "hotsauce", "sauce"}

        lane = self_heal.category_lane_for(desc, "Oriental, Mexican & Ethnic Sauces", title_tokens)
        form = self_heal.product_form_for(desc, "Oriental, Mexican & Ethnic Sauces", lane, title_tokens)

        self.assertEqual(lane, "sauce_condiment")
        self.assertEqual(form, "hot_sauce")
        self.assertEqual(
            self_heal.sauce_form_mismatch_reason(form, "Sauce, pasta, roasted red pepper & garlic"),
            "sauce_subtype_mismatch:hot_sauce",
        )

    def test_water_flavor_must_match_candidate_flavor(self) -> None:
        desc = "MANGO SPARKLING WATER, MANGO"
        title_tokens = {"mango", "sparkling", "water"}

        lane = self_heal.category_lane_for(desc, "Water", title_tokens)
        form = self_heal.product_form_for(desc, "Water", lane, title_tokens)
        heads = self_heal.target_heads_for(lane, form, "main", title_tokens)

        self.assertEqual(lane, "water")
        self.assertEqual(heads, ("Water", "Drink"))
        self.assertEqual(
            self_heal.water_flavor_mismatch_reason(lane, {"mango", "water"}, "Water, flavored, berry burst, sparkling"),
            "water_flavor_missing:mango",
        )
        self.assertEqual(
            self_heal.water_flavor_mismatch_reason(lane, {"mango", "water"}, "Water, flavored, mango, sparkling"),
            "",
        )
        self.assertEqual(
            self_heal.water_flavor_mismatch_reason(lane, {"water"}, "Water, flavored, citrus twist, sparkling"),
            "water_flavor_unasked:citrus",
        )

    def test_clam_chowder_targets_chowder_not_generic_potato_soup(self) -> None:
        desc = "NEW ENGLAND CLAM CHOWDER"
        title_tokens = {"new", "england", "clam", "chowder"}

        lane = self_heal.category_lane_for(desc, "Other Soups", title_tokens)
        form = self_heal.product_form_for(desc, "Other Soups", lane, title_tokens)
        heads = self_heal.target_heads_for(lane, form, "main", title_tokens)

        self.assertEqual(lane, "soup")
        self.assertEqual(form, "chowder")
        self.assertEqual(heads, ("Chowder", "Soup"))
        self.assertEqual(
            self_heal.soup_form_mismatch_reason(form, {"clam", "chowder"}, "Soup, potato, chunky, with roasted onion"),
            "chowder_product_to_non_chowder",
        )
        self.assertEqual(
            self_heal.soup_form_mismatch_reason(form, {"clam", "chowder"}, "Chowder, clam, New England, canned"),
            "",
        )

    def test_tomato_okra_corn_mix_requires_mix_terms(self) -> None:
        desc = "TOMATOES, OKRA & CORN"
        title_tokens = {"tomatoes", "okra", "corn"}

        lane = self_heal.category_lane_for(desc, "Canned Vegetables", title_tokens)
        form = self_heal.product_form_for(desc, "Canned Vegetables", lane, title_tokens)
        heads = self_heal.target_heads_for(lane, form, "main", title_tokens)

        self.assertEqual(lane, "vegetable")
        self.assertEqual(form, "tomato_vegetable_mix")
        self.assertEqual(heads, ("Dish", "Vegetables", "Tomato", "Tomatoes"))
        self.assertEqual(
            self_heal.tomato_form_mismatch_reason(form, {"tomatoes", "okra", "corn"}, "Tomatoes, diced, with garlic & onion, canned"),
            "tomato_mix_missing:corn,okra",
        )
        self.assertEqual(
            self_heal.tomato_form_mismatch_reason(form, {"tomatoes", "okra", "corn"}, "Dish, tomatoes, with okra & corn, stewed"),
            "",
        )

    def test_tomato_sauce_targets_tomato_sauce_not_diced_tomatoes(self) -> None:
        desc = "TOMATO SAUCE, TOMATO"
        title_tokens = {"tomato", "sauce"}

        lane = self_heal.category_lane_for(desc, "Tomatoes", title_tokens)
        form = self_heal.product_form_for(desc, "Tomatoes", lane, title_tokens)
        heads = self_heal.target_heads_for(lane, form, "main", title_tokens)

        self.assertEqual(lane, "vegetable")
        self.assertEqual(form, "tomato_sauce")
        self.assertEqual(heads, ("Tomato Sauce", "Sauce"))
        self.assertEqual(
            self_heal.tomato_form_mismatch_reason(form, {"tomato", "sauce"}, "Tomatoes, diced, with garlic & onion, canned"),
            "tomato_sauce_product_to_non_sauce",
        )
        self.assertEqual(
            self_heal.tomato_form_mismatch_reason(form, {"tomato", "sauce"}, "Tomato Sauce, canned"),
            "",
        )

    def test_horseradish_is_not_mustard(self) -> None:
        desc = "CREAM HORSERADISH, HOT"
        title_tokens = {"cream", "horseradish", "hot"}

        lane = self_heal.category_lane_for(desc, "Oriental, Mexican & Ethnic Sauces", title_tokens)
        form = self_heal.product_form_for(desc, "Oriental, Mexican & Ethnic Sauces", lane, title_tokens)
        heads = self_heal.target_heads_for(lane, form, "main", title_tokens)

        self.assertEqual(lane, "sauce_condiment")
        self.assertEqual(form, "horseradish")
        self.assertEqual(heads, ("Sauce", "Spice"))
        self.assertEqual(
            self_heal.sauce_form_mismatch_reason(form, "Mustard"),
            "sauce_subtype_mismatch:horseradish",
        )
        self.assertEqual(self_heal.sauce_form_mismatch_reason(form, "Sauce, horseradish, cream"), "")

    def test_salad_shrimp_targets_shrimp_not_cod(self) -> None:
        desc = "SALAD SHRIMP"
        title_tokens = {"salad", "shrimp"}

        lane = self_heal.category_lane_for(desc, "Frozen Fish & Seafood", title_tokens)
        form = self_heal.product_form_for(desc, "Frozen Fish & Seafood", lane, title_tokens)
        heads = self_heal.target_heads_for(lane, form, "main", title_tokens)

        self.assertEqual(lane, "fish_seafood")
        self.assertEqual(form, "shrimp")
        self.assertEqual(heads, ("Shrimp",))
        self.assertEqual(
            self_heal.seafood_form_mismatch_reason(form, {"salad", "shrimp"}, "Fish, cod, Pacific, cooked"),
            "seafood_identity_mismatch:shrimp->cod",
        )

    def test_whole_milk_rejects_evaporated_milk(self) -> None:
        desc = "WHOLE MILK"
        title_tokens = {"whole", "milk"}

        lane = self_heal.category_lane_for(desc, "Milk", title_tokens)
        form = self_heal.product_form_for(desc, "Milk", lane, title_tokens)

        self.assertEqual(lane, "milk")
        self.assertEqual(form, "milk")
        self.assertEqual(
            self_heal.milk_form_mismatch_reason(form, {"whole", "milk"}, "Milk, evaporated, with added vitamin A, canned"),
            "milk_subtype_mismatch:fluid_to_preserved_milk:canned,evaporated",
        )
        self.assertEqual(self_heal.milk_form_mismatch_reason(form, {"whole", "milk"}, "Milk, whole, 3.25%"), "")

    def test_hot_cocoa_mix_targets_hot_cocoa_not_juice_drink(self) -> None:
        desc = "HOT COCOA MIX"
        title_tokens = {"hot", "cocoa", "mix"}

        lane = self_heal.category_lane_for(desc, "Powdered Drinks", title_tokens)
        form = self_heal.product_form_for(desc, "Powdered Drinks", lane, title_tokens)
        heads = self_heal.target_heads_for(lane, form, "main", title_tokens)

        self.assertEqual(lane, "powdered_drink")
        self.assertEqual(form, "hot_cocoa")
        self.assertEqual(heads, ("Hot Cocoa",))
        self.assertEqual(
            self_heal.beverage_form_mismatch_reason(lane, form, {"hot", "cocoa", "mix"}, "Juice Drink, fruit flavored"),
            "powdered_drink_to_non_dry_mix",
        )

    def test_concord_grape_jelly_rejects_generic_jelly_when_specific_leaf_exists(self) -> None:
        desc = "JELLY, CONCORD GRAPE"
        title_tokens = {"jelly", "concord", "grape"}

        lane = self_heal.category_lane_for(desc, "Jam, Jelly & Fruit Spreads", title_tokens)
        form = self_heal.product_form_for(desc, "Jam, Jelly & Fruit Spreads", lane, title_tokens)

        self.assertEqual(lane, "sweet_spread")
        self.assertEqual(form, "jelly")
        self.assertEqual(
            self_heal.spread_form_mismatch_reason(form, {"jelly", "concord", "grape"}, "Jelly"),
            "spread_flavor_missing:concord,grape",
        )
        self.assertEqual(
            self_heal.spread_form_mismatch_reason(form, {"jelly", "concord", "grape"}, "Jelly, concord grape"),
            "",
        )

    def test_filled_pasta_targets_ravioli_not_generic_pasta(self) -> None:
        desc = "CHEESE RAVIOLI"
        title_tokens = {"cheese", "ravioli"}

        lane = self_heal.category_lane_for(desc, "Pasta by Shape & Type", title_tokens)
        form = self_heal.product_form_for(desc, "Pasta by Shape & Type", lane, title_tokens)
        heads = self_heal.target_heads_for(lane, form, "main", title_tokens)
        category_ok, _ = policy.category_allows_head(
            category="Pasta by Shape & Type",
            product_description=desc,
            title_tokens=title_tokens,
            candidate_head="Ravioli",
        )

        self.assertEqual(lane, "pasta")
        self.assertEqual(form, "ravioli")
        self.assertEqual(heads, ("Ravioli",))
        self.assertTrue(category_ok)
        self.assertEqual(
            self_heal.prepared_form_mismatch_reason(form, {"cheese", "ravioli"}, "Pasta, cooked from fresh"),
            "prepared_form_mismatch:ravioli_missing_leaf",
        )
        self.assertEqual(
            self_heal.prepared_form_mismatch_reason(form, {"crab", "ravioli"}, "Ravioli, cheese, canned"),
            "prepared_form_mismatch:ravioli_missing_crab_filling",
        )
        self.assertEqual(
            self_heal.prepared_form_mismatch_reason(form, {"cheese", "ravioli"}, "Ravioli, cheese, canned"),
            "",
        )

    def test_whole_milk_candidate_scores_against_whole_milk_leaf(self) -> None:
        fact = pd.Series(
            {
                "target_heads": "Milk",
                "branded_food_category": "Milk",
                "product_description": "WHOLE MILK",
                "title_tokens": "whole milk",
                "ingredient_tokens": "",
                "identity_terms": "whole milk",
                "product_form": "milk",
                "category_lane": "milk",
            }
        )
        candidate = self_heal.full_map.Candidate(
            code="1",
            description="Milk, whole, 3.25%, with added vitamin D",
            family="Milk",
            tokens=frozenset(),
            hard_terms=frozenset(),
            identity_terms=frozenset(),
            meaningful_terms=frozenset(),
            categories=frozenset({"Milk"}),
            category_support=20,
            needs_fix=False,
        )

        self.assertIsNotNone(self_heal.candidate_score(fact, candidate, {}))

    def test_fluid_skim_milk_with_dry_milk_ingredient_still_rejects_dry_milk_leaf(self) -> None:
        fact = pd.Series(
            {
                "target_heads": "Milk",
                "branded_food_category": "Milk",
                "product_description": "GRADE A SKIM MILK",
                "title_tokens": "grade milk skim",
                "ingredient_tokens": "dry milk skim vitamin",
                "identity_terms": "grade milk skim",
                "product_form": "milk",
                "category_lane": "milk",
            }
        )
        candidate = self_heal.full_map.Candidate(
            code="33847",
            description="Milk, skim, agglomerated, extra grade, dry, FS",
            family="Milk",
            tokens=frozenset(),
            hard_terms=frozenset(),
            identity_terms=frozenset(),
            meaningful_terms=frozenset(),
            categories=frozenset({"Milk"}),
            category_support=20,
            needs_fix=False,
        )

        self.assertIsNone(self_heal.candidate_score(fact, candidate, {}))

    def test_eggnog_targets_eggnog_not_condensed_milk(self) -> None:
        desc = "PREMIUM GOLDEN EGG NOG"
        title_tokens = {"premium", "golden", "egg", "nog"}

        lane = self_heal.category_lane_for(desc, "Milk", title_tokens)
        form = self_heal.product_form_for(desc, "Milk", lane, title_tokens)
        heads = self_heal.target_heads_for(lane, form, "main", title_tokens)

        self.assertEqual(lane, "milk")
        self.assertEqual(form, "eggnog")
        self.assertEqual(heads, ("Eggnog", "Eggnog Substitute"))
        self.assertEqual(
            self_heal.milk_form_mismatch_reason(form, {"egg", "nog"}, "Milk, condensed, sweetened, fat free, canned"),
            "milk_subtype_mismatch:eggnog",
        )
        self.assertEqual(self_heal.milk_form_mismatch_reason(form, {"egg", "nog"}, "Eggnog, classic"), "")

    def test_buttermilk_targets_buttermilk_not_generic_milk(self) -> None:
        desc = "1% LOWFAT CULTURED BUTTERMILK"
        title_tokens = {"1", "lowfat", "cultured", "buttermilk"}

        lane = self_heal.category_lane_for(desc, "Milk", title_tokens)
        form = self_heal.product_form_for(desc, "Milk", lane, title_tokens)
        heads = self_heal.target_heads_for(lane, form, "main", title_tokens)

        self.assertEqual(lane, "milk")
        self.assertEqual(form, "buttermilk")
        self.assertEqual(heads, ("Buttermilk",))
        self.assertEqual(
            self_heal.milk_form_mismatch_reason(form, {"buttermilk", "cultured", "lowfat"}, "Milk, 1%, with added calcium & vitamin A & D"),
            "milk_subtype_mismatch:buttermilk",
        )
        self.assertEqual(
            self_heal.milk_form_mismatch_reason(form, {"buttermilk", "cultured", "lowfat"}, "Buttermilk, low fat, 1%, cultured"),
            "",
        )

    def test_plant_milk_targets_matching_plant_milk_not_dairy_milk(self) -> None:
        desc = "Silk Organic Soymilk Unsweetened 64oz, Extended Shelf Life"
        title_tokens = {"silk", "organic", "soymilk", "unsweetened", "extended", "shelf", "life"}

        lane = self_heal.category_lane_for(desc, "Milk/Milk Substitutes", title_tokens)
        form = self_heal.product_form_for(desc, "Milk/Milk Substitutes", lane, title_tokens)
        heads = self_heal.target_heads_for(lane, form, "main", title_tokens)

        self.assertEqual(lane, "plant_milk")
        self.assertEqual(form, "plant_milk")
        self.assertIn("Soy Milk", heads)
        self.assertNotIn("Milk", heads)
        self.assertEqual(
            self_heal.milk_form_mismatch_reason(form, {"soymilk", "soy", "milk"}, "Milk, 1%, with added calcium & vitamin A & D"),
            "milk_subtype_mismatch:plant_milk",
        )
        self.assertEqual(
            self_heal.milk_form_mismatch_reason(form, {"soymilk", "soy", "milk"}, "Soy Milk, original, unsweetened"),
            "",
        )
        self.assertEqual(
            self_heal.milk_form_mismatch_reason(form, {"soymilk", "soy", "milk", "unsweetened"}, "Soy Milk, Plus, for bone health, added calcium"),
            "milk_subtype_mismatch:plant_milk_missing_unsweetened",
        )
        self.assertEqual(
            self_heal.milk_form_mismatch_reason(form, {"coconut", "milk", "original"}, "Cream Substitute, coconut milk, hazelnut"),
            "milk_subtype_mismatch:plant_milk_unasked_variant:hazelnut",
        )
        self.assertEqual(
            self_heal.milk_form_mismatch_reason(form, {"coconut", "milk", "original"}, "Cream Substitute, coconut milk, original"),
            "",
        )

    def test_ready_drink_plant_based_milk_routes_to_plant_milk(self) -> None:
        desc = "Pacific Foods Organic Unsweetened Almond Milk, Plant Based Milk, 32 oz Carton"
        title_tokens = {"pacific", "foods", "organic", "unsweetened", "almond", "milk", "plant", "based", "32", "oz", "carton"}

        lane = self_heal.category_lane_for(desc, "Non Alcoholic Beverages - Ready to Drink", title_tokens)
        form = self_heal.product_form_for(desc, "Non Alcoholic Beverages - Ready to Drink", lane, title_tokens)
        heads = self_heal.target_heads_for(lane, form, "main", title_tokens)

        self.assertEqual(lane, "plant_milk")
        self.assertEqual(form, "plant_milk")
        self.assertEqual(heads, ("Soy Milk", "Almond Milk", "Oat Milk", "Coconut Milk", "Cream Substitute"))

    def test_condensed_milk_in_cream_substitute_category_still_routes_to_milk(self) -> None:
        desc = "LA LECHERA Sweetened Condensed Milk Doypack 800g"
        title_tokens = {"la", "lechera", "sweetened", "condensed", "milk", "doypack", "800g"}

        lane = self_heal.category_lane_for(desc, "Cream/Cream Substitutes", title_tokens)
        form = self_heal.product_form_for(desc, "Cream/Cream Substitutes", lane, title_tokens)
        heads = self_heal.target_heads_for(lane, form, "main", title_tokens)

        self.assertEqual(lane, "milk")
        self.assertEqual(form, "milk")
        self.assertEqual(heads, ("Milk",))

    def test_plain_oatmilk_rejects_unasked_puerto_rican_oat_milk(self) -> None:
        desc = "ORIGINAL OATMILK"
        title_tokens = {"original", "oatmilk"}

        lane = self_heal.category_lane_for(desc, "Milk", title_tokens)
        form = self_heal.product_form_for(desc, "Milk", lane, title_tokens)

        self.assertEqual(lane, "plant_milk")
        self.assertEqual(form, "plant_milk")
        self.assertEqual(
            self_heal.milk_form_mismatch_reason(form, {"oatmilk", "oat", "milk"}, "Oat Milk, Puerto Rican"),
            "milk_subtype_mismatch:plant_milk_unasked_puerto_rican",
        )

    def test_fluid_milk_rejects_dry_or_evaporated_milk(self) -> None:
        self.assertEqual(
            self_heal.milk_form_mismatch_reason("milk", {"fresh", "grade", "milk"}, "Milk, skim, agglomerated, extra grade, dry, FS"),
            "milk_subtype_mismatch:fluid_to_preserved_milk:agglomerated,dry",
        )
        self.assertEqual(
            self_heal.milk_form_mismatch_reason("milk", {"evaporated", "milk"}, "Milk, whole"),
            "milk_subtype_missing_preserved_form:evaporated",
        )
        self.assertEqual(
            self_heal.milk_form_mismatch_reason("milk", {"evaporated", "milk"}, "Milk, whole, dry powder, with added vitamin D"),
            "milk_subtype_preserved_form_mismatch:evaporated->dry",
        )
        self.assertEqual(
            self_heal.milk_form_mismatch_reason("milk", {"condensed", "milk", "sweetened"}, "Milk, nonfat/skim, with added vitamin A & D, instant powder"),
            "milk_subtype_preserved_form_mismatch:condensed->dry",
        )
        self.assertEqual(
            self_heal.milk_form_mismatch_reason("milk", {"skim", "milk"}, "Milk, nonfat, acidophilus bifidus, with added vitamin A & D"),
            "milk_subtype_mismatch:plain_to_cultured_milk",
        )
        self.assertEqual(
            self_heal.milk_form_mismatch_reason("milk", {"skim", "milk"}, "Milk, skim, solids"),
            "milk_subtype_mismatch:fluid_to_milk_solids",
        )
        self.assertEqual(
            self_heal.milk_form_mismatch_reason("milk", {"fresh", "grade", "milk"}, "Milk, 2%, tall"),
            "milk_subtype_mismatch:retail_to_service_size",
        )
        self.assertEqual(
            self_heal.milk_form_mismatch_reason("milk", {"fresh", "grade", "milk"}, "Milk, 1%, with HeartRight"),
            "milk_subtype_mismatch:plain_milk_unasked_variant:heartright",
        )
        self.assertEqual(
            self_heal.milk_form_mismatch_reason("milk", {"fresh", "grade", "milk"}, "Milk, 2%"),
            "milk_subtype_mismatch:generic_to_reduced_fat",
        )
        self.assertEqual(
            self_heal.milk_form_mismatch_reason("milk", {"vitamin", "milk"}, "Milk, evaporated, with added vitamin A, canned"),
            "milk_subtype_mismatch:fluid_to_preserved_milk:canned,evaporated",
        )
        self.assertEqual(
            self_heal.milk_form_mismatch_reason("milk", {"vitamin", "evaporated", "milk"}, "Milk, evaporated"),
            "",
        )

    def test_fat_free_milk_accepts_nonfat_not_reduced_fat_drink(self) -> None:
        self.assertEqual(
            self_heal.milk_form_mismatch_reason(
                "milk",
                {"fat", "free", "milk", "vitamin"},
                "Milk, Nesquik, reduced fat, with added calcium & vitamin A & D, ready to drink",
            ),
            "milk_subtype_missing:nonfat",
        )
        self.assertEqual(
            self_heal.milk_form_mismatch_reason(
                "milk",
                {"fat", "free", "milk", "vitamin"},
                "Milk, nonfat/skim, with added vitamin A & D",
            ),
            "",
        )

    def test_kefir_targets_kefir_not_nonfat_milk(self) -> None:
        desc = "MANGO KEFIR, MANGO"
        title_tokens = {"mango", "kefir"}

        lane = self_heal.category_lane_for(desc, "Milk", title_tokens)
        form = self_heal.product_form_for(desc, "Milk", lane, title_tokens)
        heads = self_heal.target_heads_for(lane, form, "main", title_tokens)

        self.assertEqual(lane, "milk")
        self.assertEqual(form, "kefir")
        self.assertEqual(heads, ("Kefir",))
        self.assertEqual(
            self_heal.milk_form_mismatch_reason(form, {"mango", "kefir"}, "Milk, nonfat, with added vitamin A & D"),
            "milk_subtype_mismatch:kefir",
        )
        self.assertEqual(
            self_heal.milk_form_mismatch_reason(form, {"mango", "kefir"}, "Kefir, blueberry"),
            "milk_subtype_mismatch:kefir_unasked_flavor:blueberry",
        )
        self.assertEqual(self_heal.milk_form_mismatch_reason(form, {"mango", "kefir"}, "Kefir, European, INTL"), "")

    def test_quinoa_in_pasta_category_does_not_become_pasta(self) -> None:
        desc = "TRI-COLOR QUINOA, TRI-COLOR"
        title_tokens = {"tri", "color", "quinoa"}

        lane = self_heal.category_lane_for(desc, "Pasta by Shape & Type", title_tokens)
        form = self_heal.product_form_for(desc, "Pasta by Shape & Type", lane, title_tokens)
        heads = self_heal.target_heads_for(lane, form, "main", title_tokens)

        self.assertEqual(lane, "pasta")
        self.assertEqual(form, "quinoa")
        self.assertEqual(heads, ("Quinoa",))

    def test_fresh_carrots_are_not_carrot_raisin_salad(self) -> None:
        desc = "BABY-CUT CARROTS"
        title_tokens = {"baby", "cut", "carrot"}

        lane = self_heal.category_lane_for(desc, "Pre-Packaged Fruit & Vegetables", title_tokens)
        form = self_heal.product_form_for(desc, "Pre-Packaged Fruit & Vegetables", lane, title_tokens)
        heads = self_heal.target_heads_for(lane, form, "main", title_tokens)

        self.assertEqual(lane, "produce_fruit")
        self.assertEqual(form, "carrot")
        self.assertEqual(heads, ("Carrot",))
        self.assertEqual(
            self_heal.produce_form_mismatch_reason(form, {"baby", "cut", "carrot"}, "Salad, carrot raisin, FS"),
            "produce_product_to_salad",
        )

    def test_coleslaw_is_not_egg_salad(self) -> None:
        desc = "COLE SLAW"
        title_tokens = {"cole", "slaw"}

        lane = self_heal.category_lane_for(desc, "Deli Salads", title_tokens)
        form = self_heal.product_form_for(desc, "Deli Salads", lane, title_tokens)
        heads = self_heal.target_heads_for(lane, form, "main", title_tokens)

        self.assertEqual(lane, "deli_salad")
        self.assertEqual(form, "coleslaw")
        self.assertEqual(heads, ("Coleslaw", "Salad"))
        self.assertEqual(
            self_heal.salad_form_mismatch_reason(form, {"cole", "slaw"}, "Salad, egg, FS"),
            "salad_subtype_mismatch:coleslaw",
        )
        self.assertEqual(self_heal.salad_form_mismatch_reason(form, {"cole", "slaw"}, "Coleslaw, creamy"), "")

    def test_crescent_rolls_are_not_caramel_sweet_rolls(self) -> None:
        desc = "ORIGINAL CRESCENT ROLLS, ORIGINAL"
        title_tokens = {"original", "crescent", "roll"}

        lane = self_heal.category_lane_for(desc, "Crusts & Dough", title_tokens)
        form = self_heal.product_form_for(desc, "Crusts & Dough", lane, title_tokens)
        heads = self_heal.target_heads_for(lane, form, "main", title_tokens)

        self.assertEqual(lane, "pastry")
        self.assertEqual(form, "crescent_roll")
        self.assertEqual(heads, ("Roll",))
        self.assertEqual(
            self_heal.prepared_form_mismatch_reason(form, {"crescent", "roll"}, "Sweet Roll, caramel, frozen dough"),
            "prepared_form_mismatch:crescent_roll:crescent",
        )
        self.assertEqual(
            self_heal.prepared_form_mismatch_reason(form, {"crescent", "roll"}, "Roll, crescent, original, refrigerated dough"),
            "",
        )

    def test_wonton_is_not_sweet_roll(self) -> None:
        desc = "PORK & SHRIMP WONTON"
        title_tokens = {"pork", "shrimp", "wonton"}

        lane = self_heal.category_lane_for(desc, "Crusts & Dough", title_tokens)
        form = self_heal.product_form_for(desc, "Crusts & Dough", lane, title_tokens)
        heads = self_heal.target_heads_for(lane, form, "main", title_tokens)

        self.assertEqual(lane, "pastry")
        self.assertEqual(form, "wonton")
        self.assertEqual(heads, ("Wonton", "Wrappers"))
        self.assertEqual(
            self_heal.prepared_form_mismatch_reason(form, {"pork", "shrimp", "wonton"}, "Sweet Roll, caramel, frozen dough"),
            "prepared_form_mismatch:wonton",
        )


if __name__ == "__main__":
    unittest.main()
