from __future__ import annotations

import sys
import unittest
from pathlib import Path


IMPLEMENTATION = Path(__file__).resolve().parents[1]
if str(IMPLEMENTATION) not in sys.path:
    sys.path.insert(0, str(IMPLEMENTATION))

from plan_verification_suite import (  # noqa: E402
    RuleVerifier,
    SeedRecipe,
    VerificationClaim,
    build_seed_plans,
    recipe_risk_terms,
    select_seed_recipes,
)
from surface_lab_calculator import LabProduct, _product_acceptance_reason, _review_products, calculate_lab  # noqa: E402


def claim(**overrides: object) -> VerificationClaim:
    base = {
        "claim_id": "claim-1",
        "plan_id": "plan-1",
        "config_id": "cfg",
        "recipe_num": "1",
        "recipe_name": "Recipe",
        "line_index": 1,
        "store": "walmart",
        "ingredient_label": "all purpose flour",
        "grams_needed": 100.0,
        "canonical_name": "all purpose flour",
        "shopping_canonical": "all purpose flour",
        "nutrition_key": "ESHA:1000",
        "nutrition_state": "reviewed_local_label_anchor",
        "nutrition_source": "esha_tier_a_label_median",
        "product_name": "Great Value All-Purpose Flour",
        "package_grams": 907.2,
        "packages_to_buy": 1,
    }
    base.update(overrides)
    return VerificationClaim(**base)


class PlanVerificationSuiteTests(unittest.TestCase):
    def test_recipe_risk_terms_finds_fragile_and_package_math_cases(self) -> None:
        score, terms = recipe_risk_terms(
            "Ham Dinner",
            {
                "spiral sliced ham": 2400.0,
                "strawberry pie filling": 600.0,
                "eggs": 300.0,
            },
        )
        self.assertGreaterEqual(score, 10)
        self.assertTrue(any(term.startswith("meat_cut:ham") for term in terms))
        self.assertTrue(any(term == "mapper_fragile:pie filling" for term in terms))
        self.assertTrue(any(term.startswith("package_math:egg") for term in terms))

    def test_select_seed_recipes_prefers_risky_rows_but_keeps_filler(self) -> None:
        recipes = [
            SeedRecipe("1", "Plain Salad", {"lettuce": 100.0}, 0, []),
            SeedRecipe("2", "Ham Roast", {"whole ham": 2000.0}, 8, ["meat_cut:ham"]),
            SeedRecipe("3", "Cookie Pie", {"chocolate sandwich cooky": 150.0}, 8, ["mapper_fragile:cookies"]),
            SeedRecipe("4", "Rice", {"rice": 100.0}, 0, []),
        ]
        selected = select_seed_recipes(recipes, 3)
        self.assertEqual([recipe.recipe_num for recipe in selected[:2]], ["2", "3"])
        self.assertEqual(len(selected), 3)

    def test_build_seed_plans_chunks_recipes_across_configs(self) -> None:
        recipes = [SeedRecipe(str(i), f"R{i}", {"flour": 100.0}, 0, []) for i in range(5)]
        plans = build_seed_plans(recipes, recipes_per_plan=2, configs=[{"config_id": "a"}, {"config_id": "b"}])
        self.assertEqual(len(plans), 3)
        self.assertEqual(plans[0].plan_id, "seed_0001_a")
        self.assertEqual(plans[1].plan_id, "seed_0002_b")
        self.assertEqual(len(plans[2].recipes), 1)

    def test_rule_verifier_rejects_pie_filling_to_pie_shell(self) -> None:
        verdict = RuleVerifier().verify(
            claim(
                ingredient_label="strawberry pie filling",
                canonical_name="strawberry pie filling",
                shopping_canonical="strawberry pie filling",
                nutrition_key="FNDDS:53391000",
                fndds_code="53391000",
                fndds_description="Pie shell",
                product_name="Duncan Hines Strawberry Pie Filling",
            )
        )
        self.assertEqual(verdict.decision, "reject")
        self.assertEqual(verdict.issue_type, "wrong_fndds")

    def test_rule_verifier_rejects_cookie_to_ice_cream(self) -> None:
        verdict = RuleVerifier().verify(
            claim(
                ingredient_label="chocolate sandwich cooky",
                canonical_name="chocolate sandwich cooky",
                shopping_canonical="chocolate sandwich cookie",
                nutrition_key="FNDDS:13111010",
                fndds_code="13111010",
                fndds_description="Cookies & cream ice cream",
                product_name="Oreo Chocolate Sandwich Cookies",
            )
        )
        self.assertEqual(verdict.decision, "reject")
        self.assertEqual(verdict.issue_type, "wrong_fndds")

    def test_rule_verifier_rejects_deli_ham_for_whole_ham(self) -> None:
        verdict = RuleVerifier().verify(
            claim(
                ingredient_label="whole bone in ham",
                canonical_name="ham",
                shopping_canonical="bone-in smoked ham",
                product_name="Oscar Mayer Deli Fresh Sliced Honey Ham",
            )
        )
        self.assertEqual(verdict.decision, "reject")
        self.assertEqual(verdict.issue_type, "wrong_form")

    def test_rule_verifier_allows_lunchmeat_for_sliced_or_chopped_ham(self) -> None:
        verifier = RuleVerifier()
        for label in ("4 slices ham", "1 cup chopped ham", "1 1/2 cups ham, diced"):
            with self.subTest(label=label):
                verdict = verifier.verify(
                    claim(
                        ingredient_label=label,
                        canonical_name="ham",
                        shopping_canonical="ham",
                        product_name="Great Value Honey Ham Lunchmeat Plastic Tub, 9 oz",
                    )
                )
                self.assertEqual(verdict.decision, "accept")

    def test_rule_verifier_rejects_sliced_bologna_for_roll_bologna(self) -> None:
        verdict = RuleVerifier().verify(
            claim(
                ingredient_label="1 (5-6 lb) roll all-beef bologna",
                canonical_name="beef bologna",
                shopping_canonical="beef bologna",
                product_name="Wunderbar German Brand Beef Bologna, Deli Sliced",
            )
        )

        self.assertEqual(verdict.decision, "reject")
        self.assertEqual(verdict.issue_type, "wrong_form")

    def test_rule_verifier_rejects_seasoning_for_meat(self) -> None:
        verdict = RuleVerifier().verify(
            claim(
                ingredient_label="chicken breast",
                canonical_name="chicken breast",
                shopping_canonical="chicken breast",
                product_name="McCormick Chicken Seasoning Mix",
            )
        )
        self.assertEqual(verdict.decision, "reject")
        self.assertEqual(verdict.issue_type, "wrong_store_item")

    def test_rule_verifier_rejects_egg_count_as_kilograms(self) -> None:
        verdict = RuleVerifier().verify(
            claim(
                ingredient_label="eggs",
                canonical_name="egg",
                shopping_canonical="egg",
                product_name="Great Value Large Eggs, 12 Count",
                package_grams=12000.0,
            )
        )
        self.assertEqual(verdict.decision, "reject")
        self.assertEqual(verdict.issue_type, "bad_package_math")

    def test_rule_verifier_accepts_clean_cookie_claim(self) -> None:
        verdict = RuleVerifier().verify(
            claim(
                ingredient_label="chocolate sandwich cooky",
                canonical_name="chocolate sandwich cooky",
                shopping_canonical="chocolate sandwich cookie",
                nutrition_key="FNDDS:53209015",
                fndds_code="53209015",
                fndds_description="Cookie, chocolate sandwich",
                product_name="Oreo Chocolate Sandwich Cookies",
                package_grams=396.9,
            )
        )
        self.assertEqual(verdict.decision, "accept")
        self.assertEqual(verdict.issue_type, "ok")

    def test_calculator_resolves_manual_fndds_fragile_items(self) -> None:
        cookie = calculate_lab("chocolate sandwich cooky", item="chocolate sandwich cooky", grams=150.0)
        pie_filling = calculate_lab("strawberry pie filling", item="strawberry pie filling", grams=600.0)
        beef_gravy = calculate_lab("1/2 gallon beef gravy", item="beef gravy", grams=1893.0)

        self.assertEqual(cookie.fndds_code, "53209015")
        self.assertEqual(cookie.nutrition_state, "reviewed_local_label_anchor")
        self.assertEqual(cookie.nutrition_source, "fndds_direct")
        self.assertEqual(pie_filling.fndds_code, "63203701")
        self.assertEqual(pie_filling.nutrition_state, "reviewed_local_label_anchor")
        self.assertEqual(pie_filling.nutrition_source, "fndds_direct")
        self.assertEqual(beef_gravy.canonical_name, "beef gravy")
        self.assertEqual(beef_gravy.esha_code, "53023")

    def test_recipe_506745_surface_context_and_shopping_overrides(self) -> None:
        parsley = calculate_lab("5 cups chopped parsley", item="parsley", grams=60.0)
        green_beans = calculate_lab("2 gallons green beans", item="green beans", grams=7571.0)
        corn = calculate_lab("2 gallons corn kernels", item="corn kernels", grams=7571.0)
        tomatoes = calculate_lab("5 lbs fresh tomatoes, diced", item="fresh tomatoes", grams=2268.0)
        chicken = calculate_lab("1 1/2 gallons chicken, cut into pieces and browned", item="chicken", grams=5678.0)
        hamburger = calculate_lab(
            "2 1/2 gallons leftover hamburger patties, crumbled",
            item="hamburger patties",
            grams=9464.0,
        )
        veal = calculate_lab("1/2 gallon leftover veal, shredded", item="veal", grams=1893.0)

        self.assertEqual(parsley.canonical_name, "fresh parsley")
        self.assertEqual(parsley.esha_code, "26013")
        self.assertEqual(green_beans.shopping_canonical, "fresh green beans")
        self.assertEqual(corn.canonical_name, "corn")
        self.assertEqual(corn.shopping_canonical, "corn")
        self.assertEqual(tomatoes.shopping_canonical, "tomatoes")
        self.assertEqual(chicken.sr28_fdc_id, "171447")
        self.assertEqual(chicken.esha_code, "15071")
        self.assertEqual(hamburger.shopping_canonical, "hamburger")
        self.assertTrue(hamburger.products)
        self.assertEqual(veal.shopping_state, "shopping_gap")
        self.assertEqual(veal.esha_code, "")
        self.assertEqual(veal.products, [])

    def test_sparse_audit_surface_repairs(self) -> None:
        peppercorns = calculate_lab("2 teaspoons whole black peppercorns", item="whole black peppercorns", grams=4.0)
        peanut_butter = calculate_lab("CREAMY PEANUT BUTTER, CREAMY", item="CREAMY PEANUT BUTTER, CREAMY", grams=128.0)
        bananas = calculate_lab("6 large ripe bananas, peeled and mashed", item="ripe bananas", grams=720.0)
        canned_corn = calculate_lab("4 cans (15 oz each) whole kernel corn, drained", item="whole kernel corn", grams=1700.0)
        canned_green_beans = calculate_lab("1 can (14 oz) green beans, drained", item="green beans", grams=397.0)
        fresh_eggs = calculate_lab("2 fresh eggs", item="fresh eggs", grams=100.0)
        toasted_bread = calculate_lab(
            "Bread, white, commercially prepared, toasted",
            item="Bread, white, commercially prepared, toasted",
            grams=100.0,
        )
        pork_chops = calculate_lab(
            "6 bone-in pork rib chops (about 7 oz each, 3/4-inch thick)",
            item="bone-in pork rib chops",
            grams=1190.0,
        )
        whole_ham = calculate_lab("3 lbs cured bone-in ham (large piece)", item="cured bone-in ham", grams=1360.0)
        dried_apples = calculate_lab(
            "Apples, dried, sulfured, uncooked",
            item="Apples, dried, sulfured, uncooked",
            grams=15.0,
        )
        canned_spaghetti = calculate_lab(
            "1 can (7 oz) canned spaghetti in tomato sauce",
            item="canned spaghetti in tomato sauce",
            grams=200.0,
        )
        orange_mix = calculate_lab(
            "3 tablespoons orange-flavored sweetened drink mix (like Kool-Aid)",
            item="orange-flavored sweetened drink mix",
            grams=36.0,
        )
        meatballs = calculate_lab(
            "350 g fully cooked Italian-style meatballs (frozen or refrigerated)",
            item="fully cooked Italian-style meatballs",
            grams=350.0,
        )
        yogurt_cheese = calculate_lab("3 cups yogurt cheese", item="yogurt cheese", grams=720.0)
        oil_or_butter = calculate_lab("1 teaspoon oil or butter", item="oil or butter", grams=5.0)
        pork_side_ribs = calculate_lab("5 lbs pork side ribs", item="pork side ribs", grams=2268.0)
        plastic_wrap = calculate_lab("Plastic wrap, for marinating", item="plastic wrap", grams=10.0)
        aluminum_foil = calculate_lab("Aluminum foil, for wrapping", item="aluminum foil", grams=15.0)
        ziploc_bags = calculate_lab("12 quart-size ziploc bags", item="ziploc bags", grams=300.0)
        mashed_bananas = calculate_lab("1 1/2 cups mashed ripe bananas", item="mashed ripe bananas", grams=340.0)
        whole_oats = calculate_lab("1 cup uncooked whole oats", item="uncooked whole oats", grams=80.0)
        yellow_squash = calculate_lab("4 large yellow squash", item="yellow squash", grams=1360.0)
        pork_ribs = calculate_lab("2 racks pork ribs, membrane removed", item="pork ribs", grams=2268.0)
        kosher_salt = calculate_lab("1 teaspoon kosher salt", item="kosher salt", grams=6.0)
        italian_seasoning = calculate_lab("1 tablespoon Italian seasoning", item="italian seasoning", grams=5.0)

        self.assertNotEqual(peppercorns.canonical_name, r"\1")
        self.assertEqual(peppercorns.sr28_fdc_id, "170931")
        self.assertEqual(peanut_butter.canonical_name, "peanut butter")
        self.assertEqual(peanut_butter.shopping_canonical, "peanut butter")
        self.assertEqual(bananas.shopping_canonical, "banana")
        self.assertEqual(canned_corn.canonical_name, "canned corn")
        self.assertEqual(canned_corn.shopping_canonical, "canned corn")
        self.assertEqual(canned_green_beans.shopping_canonical, "canned green beans")
        self.assertTrue(canned_green_beans.products)
        self.assertFalse(any("frozen" in product.description.lower() for product in canned_green_beans.products))
        self.assertEqual(fresh_eggs.sr28_fdc_id, "171287")
        self.assertEqual(toasted_bread.shopping_canonical, "white bread")
        self.assertEqual(pork_chops.shopping_canonical, "pork chop")
        self.assertEqual(whole_ham.shopping_canonical, "whole ham")
        self.assertEqual(dried_apples.sr28_fdc_id, "171691")
        self.assertEqual(canned_spaghetti.fndds_code, "58146150")
        self.assertEqual(orange_mix.fndds_code, "92900110")
        self.assertEqual(meatballs.sr28_fdc_id, "171638")
        self.assertEqual(yogurt_cheese.shopping_canonical, "greek yogurt")
        self.assertEqual(oil_or_butter.shopping_canonical, "vegetable oil")
        self.assertEqual(pork_side_ribs.sr28_fdc_id, "168305")
        self.assertEqual(plastic_wrap.shopping_state, "non_food")
        self.assertEqual(aluminum_foil.shopping_state, "non_food")
        self.assertEqual(ziploc_bags.shopping_state, "non_food")
        self.assertEqual(mashed_bananas.shopping_canonical, "banana")
        self.assertEqual(whole_oats.sr28_fdc_id, "173904")
        self.assertFalse(any("seed" in product.description.lower() for product in yellow_squash.products))
        self.assertFalse(any("patty" in product.description.lower() for product in pork_ribs.products))
        self.assertEqual(kosher_salt.sr28_fdc_id, "173468")
        self.assertEqual(italian_seasoning.sr28_fdc_id, "171328")

    def test_recipe_506745_product_filter_rejects_wrong_forms(self) -> None:
        def product(description: str) -> LabProduct:
            return LabProduct(
                gtin_upc="",
                description=description,
                brand_name="walmart",
                category="",
                source="retail_surface_bridge:walmart",
            )

        ok, _ = _product_acceptance_reason(
            product("Great Value Homestyle Beef Flavored Gravy, 12 oz Glass Jar"),
            "beef gravy",
        )
        self.assertTrue(ok)

        bad_cases = [
            ("Great Value Brown Gravy Mix, 0.87 oz", "beef gravy"),
            ("Marshalls Creek Spices XL BAKED VEAL SEASONING REFILL 26 oz", "veal"),
            ("Kroger® Beef Brisket BBQ Baked Beans", "beef brisket"),
            ("Colorado Premium's Fresh Corned Beef Brisket Point, 2.0- 4.25 lb", "beef brisket"),
            ("Jack Daniel's Seasoned Beef Brisket, Fully Cooked, Ready to Heat, 20 oz Tray", "beef brisket"),
            ("Private Selection® Chuck & Brisket Ground Beef Patties", "beef brisket"),
            ("Knorr Concentrated Chicken Stock Gluten Free, 8.45 oz", "chicken stock"),
            ("Better Than Bouillon Premium Roasted Chicken Base, Shelf-Stable, 8 oz Jar", "chicken stock"),
            ("Flame Grilled Hamburger Beef Patty On A Bun", "hamburger patty"),
            ("Great Value Shredded Chicken Breast with Rib Meat, 10 oz Can", "chicken"),
            ("Great Value Seasoned Potato Hash Brown Patties", "potato"),
            ("Great Value Parsley Flakes, 0.4 oz", "fresh parsley"),
            ("Belveder Red Cabbage with Apple", "red cabbage"),
            ("Great Value Peppercorn Medley Grinder, 3.9 oz", "black peppercorn"),
            ("Fusion Select Premium Szechuan Peppercorn Spice Seasoning", "black peppercorn"),
            ("Great Value Sliced Bananas, 16 oz Bag", "banana"),
            ("Jumex Strawberry-Banana Nectar Can", "banana"),
            ("Tyson Slow Cooker Pork Roast Meal Kit with Vegetables & Seasoning", "pork roast"),
            ("Home Chef Cold Pork Loin", "pork roast"),
            ("Del Monte Fire Roasted Whole Kernel Corn, Canned Vegetables, 14.75 oz Can", "canned corn"),
            ("Great Value Peanut Butter Chocolate Cups", "peanut butter"),
            ("Domino Premium Pure Cane Dark Brown Sugar Zipper-Pack", "light brown sugar"),
            ("Morton Iodized Salt, 26 oz", "kosher salt"),
            ("Great Value Vegetable Oil No-Stick Cooking Spray", "vegetable oil"),
            ("Badia Ground Cloves, 1.75 oz", "clove"),
            ("Freshness Guaranteed Hawaiian Dinner Rolls, Regular, 16 oz, 12 Count", "italian roll"),
            ("Campbell’s® Chunky® Healthy Request® Split Pea and Ham Soup with Smoke Flavor", "split pea"),
            ("Great Value Navy Bean, 15.5 oz Can", "navy bean"),
            ("Ben's Original Ready Rice Jasmine Rice, Easy Dinner Side, 8.5 Ounce Pouch", "rice"),
            ("Knorr Rice Sides Chicken Fried Rice with Long Grain Rice and Vermicelli Pasta Rice Sides", "rice"),
            ("Great Value Cut Green Beans, 12 oz Bag (Frozen)", "canned green beans"),
            ("Early Prolific Straightneck Summer Squash Garden Seeds - 7 g Packet", "yellow squash"),
            ("Holten Meat 4-1 St Louis Pork Rib Patty, 4 Ounce -- 40 per case", "pork ribs"),
            ("Lloyd's Seasoned and Smoked St. Louis Style Pork Rib in BBQ Sauce", "pork ribs"),
            ("Kroger® Hot Honey Flavored Pork Baby Back Ribs", "pork ribs"),
            ("Holten Meat Boneless Breaded Pork Loin Chop - Pork Patty Fritter", "pork chop"),
            ("Sara Lee Premium Meats Gluten Free Honey Ham, Deli Sliced", "whole ham"),
            ("Brakebush Country Krisp Wings, Fully Cooked, Breaded, Bone-In Chicken Wings", "italian meatballs"),
        ]
        for description, canonical in bad_cases:
            with self.subTest(description=description, canonical=canonical):
                ok, reason = _product_acceptance_reason(product(description), canonical)
                self.assertFalse(ok, reason)

        good_cases = [
            ("Beef Brisket, 12.94 - 21.56 lb", "beef brisket"),
            ("Private Selection® Natural Angus Beef Brisket with Salt and Pepper", "beef brisket"),
            ("Swanson Chicken Stock", "chicken stock"),
            ("Simple Truth Organic® Free Range Chicken Stock", "chicken stock"),
            ("Great Value Green Split Peas, 1 lb", "split pea"),
            ("Kroger® Green Split Peas", "split pea"),
            ("Great Value Navy Beans, 1 lb", "navy bean"),
            ("Kroger® Navy Beans", "navy bean"),
            ("Great Value Long Grain Enriched Rice, 20 lb", "rice"),
            ("Botan Calrose Rice", "rice"),
            ("McCormick Whole Black Peppercorns, 4.25 oz", "black peppercorn"),
            ("Fresh Bunch of Bananas – 5-7 Bananas", "banana"),
            ("Kroger® Fresh Natural Pork Loin Boneless", "pork roast"),
            ("Del Monte Fresh Cut Golden Sweet Whole Kernel Corn, Canned Vegetables, 15.25 oz Can", "canned corn"),
            ("Great Value Creamy Peanut Butter 16oz", "peanut butter"),
            ("(3 pack) Great Value Coarse Kosher Salt, 48 oz", "kosher salt"),
            ("Domino Premium Pure Cane Light Brown Sugar Zipper-Pack", "light brown sugar"),
            ("Private Selection® Turbinado Cane Sugar", "turbinado sugar"),
            ("1-2-3 Vegetable Oil, 1 Gallon", "vegetable oil"),
            ("Ty Ling Liquid Pure Sesame Oil, 6.2 fl oz, Glass Bottle", "sesame oil"),
            ("Great Value Deluxe Mixed Nuts, 10 oz", "mixed nuts"),
            ("Badia Cloves, 16 Ounce", "clove"),
            ("Freshness Guaranteed White Sub Rolls, 16 oz, 6 Count", "italian roll"),
            ("Del Monte Petite Cut Green Beans, Canned Vegetables, 14.5 oz Can", "canned green beans"),
            ("Organic Yellow Squash", "yellow squash"),
            ("Ibp Trusted Excellence Pork Backrib - 2.5 Up Vacuum Pack, 8.73 Pound -- 6 per case", "pork ribs"),
            ("Fresh Bone-In Pork Loin Chops, 2 lb", "pork chop"),
            ("Spiral Sliced Bone-In Ham Half", "whole ham"),
            ("Italian Style Meatballs, Frozen, 32 oz", "italian meatballs"),
        ]
        for description, canonical in good_cases:
            with self.subTest(description=description, canonical=canonical):
                ok, reason = _product_acceptance_reason(product(description), canonical)
                self.assertTrue(ok, reason)

    def test_retail_product_review_keeps_later_store_candidates(self) -> None:
        walmart_products = [
            LabProduct(
                gtin_upc=str(i),
                description=f"Great Value Iodized Salt, {i} oz",
                brand_name="walmart",
                category="",
                source="retail_surface_bridge:walmart",
            )
            for i in range(30)
        ]
        kroger = LabProduct(
            gtin_upc="kroger-salt",
            description="Kroger Iodized Salt, 26 oz",
            brand_name="kroger",
            category="",
            source="retail_surface_bridge:kroger",
        )

        accepted, _ = _review_products([*walmart_products, kroger], "salt")

        self.assertTrue(any(product.source == "retail_surface_bridge:kroger" for product in accepted))


if __name__ == "__main__":
    unittest.main()
