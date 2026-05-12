from __future__ import annotations

import sys
import unittest
from pathlib import Path


IMPLEMENTATION = Path(__file__).resolve().parents[1]
if str(IMPLEMENTATION) not in sys.path:
    sys.path.insert(0, str(IMPLEMENTATION))

from build_hestia_esha_native_artifacts import (
    MANUAL_PACKAGE_ROWS,
    PACKAGE_NATIVE_KEY_OVERRIDES,
    _classify_protein_source,
    _coverage_package_seed_rule,
    _esha_identity_gate,
    _egg_count_package_grams,
    _nonfood_product_reason,
    _package_native_key_product_reason,
    _package_price_reason,
    _package_product_reason,
    _resolve_item,
    _sr28_fallback_allowed,
)
from sparse_cascade_planner.build_recipe_qa_native_recipes import _recipe_resolution_label
from sparse_cascade_planner.build_product_identity_bridge import classify_product_identity


class EshaNativeArtifactTests(unittest.TestCase):
    def test_rejects_raw_chicken_breast_to_lunchmeat(self) -> None:
        ok, reason = _esha_identity_gate("chicken breast", "Lunchmeat, chicken breast")
        self.assertFalse(ok)
        self.assertIn("lunchmeat", reason)

    def test_plain_mayonnaise_accepts_plain_mayo_leaf(self) -> None:
        ok, reason = _esha_identity_gate("mayonnaise", "Dressing, mayonnaise")
        self.assertTrue(ok)
        self.assertEqual(reason, "esha_identity_ok")

    def test_canned_form_token_is_not_identity_overlap(self) -> None:
        ok, reason = _esha_identity_gate(
            "Pumpkin, cooked, from canned, fat not added in cooking",
            "Baked Beans, maple sugar, canned",
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "no_identity_overlap")

    def test_canned_pumpkin_accepts_canned_pumpkin_leaf(self) -> None:
        ok, reason = _esha_identity_gate(
            "Pumpkin, cooked, from canned, fat not added in cooking",
            "Pumpkin, canned, unsalted",
        )
        self.assertTrue(ok)
        self.assertEqual(reason, "esha_identity_ok")

    def test_pumpkin_pie_mix_rejects_ice_cream_cake_leaf(self) -> None:
        ok, reason = _esha_identity_gate(
            "LIBBY'S Easy Pumpkin Pie Mix 30 oz. Can",
            'Cake, ice cream, Blizzard, pumpkin pie, 1/10 of 10"',
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "esha_adds_prepared_form:cake,cream,ice")

    def test_pumpkin_pie_mix_accepts_pumpkin_pie_filling_leaf(self) -> None:
        ok, reason = _esha_identity_gate(
            "LIBBY'S Easy Pumpkin Pie Mix 30 oz. Can",
            "Pie Filling, pumpkin, canned",
        )
        self.assertTrue(ok)
        self.assertEqual(reason, "esha_identity_ok")

    def test_compound_almondmilk_token_matches_almond_milk_leaf(self) -> None:
        ok, reason = _esha_identity_gate(
            "ORIGINAL ALMONDMILK",
            "Almond Milk, Almond Breeze, original",
        )
        self.assertTrue(ok)
        self.assertEqual(reason, "esha_identity_ok")

    def test_regular_plural_tokens_match_singular_leaf(self) -> None:
        ok, reason = _esha_identity_gate("DRIED HONEY CRISP APPLES", "Apple, dried")
        self.assertTrue(ok)
        self.assertEqual(reason, "esha_identity_ok")

    def test_generic_dressing_does_not_collapse_to_mayonnaise(self) -> None:
        ok, reason = _esha_identity_gate("herb dressing", "Dressing, mayonnaise")
        self.assertFalse(ok)
        self.assertEqual(reason, "esha_adds_mayonnaise_identity")

    def test_plain_egg_uses_shell_egg_not_egg_roll(self) -> None:
        line = _resolve_item("Egg, whole, raw, fresh", 50, allow_sr28_fallback=True, allow_fndds_fallback=False)
        self.assertEqual(line.ingredient_key, "ESHA:19500")
        self.assertEqual(line.esha_description, "Egg, whole, raw")
        self.assertEqual(line.sr28_code, "171287")

    def test_liquid_egg_whites_use_egg_white_leaf(self) -> None:
        line = _resolve_item("pasteurized liquid egg whites", 100, allow_sr28_fallback=True, allow_fndds_fallback=False)
        self.assertEqual(line.ingredient_key, "ESHA:21111")
        self.assertEqual(line.esha_description, "Egg, white, raw, large")
        self.assertEqual(line.sr28_code, "172183")

    def test_old_dried_yolk_surface_uses_raw_yolk_leaf(self) -> None:
        line = _resolve_item("Egg, yolk, dried", 34, allow_sr28_fallback=True, allow_fndds_fallback=False)
        self.assertEqual(line.ingredient_key, "ESHA:19508")
        self.assertEqual(line.esha_description, "Egg Yolk, raw, large")

    def test_soft_egg_sandwich_buns_do_not_buy_shell_eggs(self) -> None:
        line = _resolve_item("soft egg sandwich buns", 100, allow_sr28_fallback=True, allow_fndds_fallback=False)
        self.assertEqual(line.ingredient_key, "")
        self.assertEqual(line.key_source, "unresolved")
        self.assertIn("egg_word_is_bread_product_not_shell_egg", ",".join(line.path))

    def test_recipe_water_is_not_purchasable(self) -> None:
        line = _resolve_item("Water, bottled, generic", 650, allow_sr28_fallback=True, allow_fndds_fallback=False)
        self.assertEqual(line.ingredient_key, "")
        self.assertEqual(line.key_source, "excluded_non_purchasable")
        self.assertIn("water_is_not_a_planner_purchase", ",".join(line.path))

    def test_recipe_hot_water_and_ice_are_not_purchasable(self) -> None:
        for label in ("hot water", "ice", "ice cubes"):
            with self.subTest(label=label):
                line = _resolve_item(label, 100, allow_sr28_fallback=True, allow_fndds_fallback=False)
                self.assertEqual(line.ingredient_key, "")
                self.assertEqual(line.key_source, "excluded_non_purchasable")
                self.assertIn("water_is_not_a_planner_purchase", ",".join(line.path))

    def test_ground_coriander_uses_seed_not_coriander_leaf(self) -> None:
        line = _resolve_item("ground coriander", 8, allow_sr28_fallback=True, allow_fndds_fallback=False)
        self.assertEqual(line.ingredient_key, "SR28:170922")
        self.assertEqual(line.sr28_description, "Spices, coriander seed")

    def test_plain_spaghetti_uses_dry_pasta_key(self) -> None:
        line = _resolve_item("spaghetti", 100, allow_sr28_fallback=True, allow_fndds_fallback=False)
        self.assertEqual(line.ingredient_key, "SR28:169736")
        self.assertEqual(line.sr28_description, "Pasta, dry, enriched")

    def test_common_recipe_aliases_use_priced_native_identities(self) -> None:
        cases = {
            "breadcrumbs": "SR28:174928",
            "cornflour": "ESHA:30000",
            "sultanas": "ESHA:3934",
            "button mushrooms": "ESHA:7351",
            "grape tomatoes": "ESHA:90530",
            "red onions": "ESHA:7805",
            "rubbed sage": "ESHA:35048",
            "fresh ginger": "ESHA:90442",
            "ginger powder": "ESHA:4086",
            "pickled ginger": "ESHA:33708",
        }
        for label, expected_key in cases.items():
            with self.subTest(label=label):
                line = _resolve_item(label, 100, allow_sr28_fallback=True, allow_fndds_fallback=False)
                self.assertEqual(line.ingredient_key, expected_key)

    def test_recipe_ginger_display_context_resolves_ambiguous_item(self) -> None:
        cases = [
            ("1 teaspoon ginger, minced", "ginger", 5.0, "fresh ginger"),
            ("1/2 teaspoon ginger", "ginger", 1.0, "ground ginger"),
            ("2 ounces ginger", "ginger", 57.0, "fresh ginger"),
            ("1 tablespoon pickled ginger", "ginger", 15.0, "pickled ginger"),
            ("1 tablespoon ginger syrup", "ginger", 20.0, "ginger syrup"),
        ]
        for display, item, grams, expected in cases:
            with self.subTest(display=display):
                self.assertEqual(_recipe_resolution_label(display, item, grams), expected)

    def test_exact_sr28_description_fallback_resolves_no_surface_spice(self) -> None:
        line = _resolve_item("Spices, marjoram, dried", 3, allow_sr28_fallback=True, allow_fndds_fallback=False)
        self.assertEqual(line.ingredient_key, "SR28:170928")
        self.assertEqual(line.key_source, "sr28_reference_exact")
        self.assertEqual(line.nutrition_source, "sr28_direct")

    def test_exact_sr28_description_fallback_beats_rejected_surface_esha(self) -> None:
        line = _resolve_item("Spices, chili powder", 8, allow_sr28_fallback=True, allow_fndds_fallback=False)
        self.assertEqual(line.ingredient_key, "SR28:171319")
        self.assertEqual(line.key_source, "sr28_reference_exact")
        self.assertIn("surface_route_unresolved:no_identity_overlap", ",".join(line.path))

    def test_exact_sr28_description_fallback_uses_sr28_food_when_not_in_surface(self) -> None:
        line = _resolve_item("Sweet potato leaves, raw", 100, allow_sr28_fallback=True, allow_fndds_fallback=False)
        self.assertEqual(line.ingredient_key, "SR28:169303")
        self.assertEqual(line.key_source, "sr28_description_exact")

    def test_fndds_description_exact_resolves_when_no_sr28_reference_exists(self) -> None:
        line = _resolve_item("Coffee, instant, reconstituted", 100, allow_sr28_fallback=True, allow_fndds_fallback=False)
        self.assertEqual(line.ingredient_key, "FNDDS:92103000")
        self.assertEqual(line.key_source, "fndds_description_exact")
        self.assertEqual(line.nutrition_source, "fndds_direct")

    def test_compound_identity_tokens_allow_safe_sr28_fallback(self) -> None:
        crab = _resolve_item("LUMP CRABMEAT", 100, allow_sr28_fallback=True, allow_fndds_fallback=False)
        self.assertEqual(crab.ingredient_key, "ESHA:19153")
        chestnut = _resolve_item("WATER CHESTNUTS", 100, allow_sr28_fallback=True, allow_fndds_fallback=False)
        self.assertEqual(chestnut.ingredient_key, "SR28:170067")

    def test_raw_cut_roast_can_fallback_to_raw_sr28_cut(self) -> None:
        line = _resolve_item("CHUCK ROAST", 454, allow_sr28_fallback=True, allow_fndds_fallback=False)
        self.assertEqual(line.ingredient_key, "SR28:174056")

    def test_pasta_shape_aliases_do_not_use_wrong_esha_shape(self) -> None:
        fettuccine = _resolve_item("FETTUCCINE", 100, allow_sr28_fallback=True, allow_fndds_fallback=False)
        self.assertEqual(fettuccine.ingredient_key, "SR28:169736")
        angel_hair = _resolve_item("ANGEL HAIR", 100, allow_sr28_fallback=True, allow_fndds_fallback=False)
        self.assertEqual(angel_hair.ingredient_key, "SR28:169736")

    def test_exact_product_title_fallback_uses_v6_fndds_truth(self) -> None:
        pancetta = _resolve_item("PANCETTA", 100, allow_sr28_fallback=True, allow_fndds_fallback=False)
        self.assertEqual(pancetta.ingredient_key, "FNDDS:22600201")
        self.assertEqual(pancetta.key_source, "product_title_fndds_exact")
        self.assertEqual(pancetta.nutrition_source, "fndds_direct")

        syrup = _resolve_item(
            "Lyle's Golden Syrup Plastic bottle",
            100,
            allow_sr28_fallback=True,
            allow_fndds_fallback=False,
        )
        self.assertEqual(syrup.ingredient_key, "FNDDS:91300010")
        self.assertEqual(syrup.key_source, "product_title_fndds_exact")

    def test_manual_exact_calculator_proxies_resolve_top_recipe_gaps(self) -> None:
        grand_marnier = _resolve_item("grand marnier", 100, allow_sr28_fallback=True, allow_fndds_fallback=False)
        self.assertEqual(grand_marnier.ingredient_key, "FNDDS:93201000")
        self.assertEqual(grand_marnier.nutrition_source, "fndds_direct")

        cognac = _resolve_item("cognac", 100, allow_sr28_fallback=True, allow_fndds_fallback=False)
        self.assertEqual(cognac.ingredient_key, "FNDDS:93501000")

        creme_de_cacao = _resolve_item("creme de cacao", 100, allow_sr28_fallback=True, allow_fndds_fallback=False)
        self.assertEqual(creme_de_cacao.ingredient_key, "ESHA:15612")
        self.assertEqual(creme_de_cacao.nutrition_source, "esha_tier_a_label_median")

        espresso = _resolve_item(
            "ESPRESSO INSTANT POWDER, ESPRESSO",
            100,
            allow_sr28_fallback=True,
            allow_fndds_fallback=False,
        )
        self.assertEqual(espresso.ingredient_key, "ESHA:20013")

    def test_manual_exact_residual_recipe_gaps_stay_calculatable(self) -> None:
        cases = {
            "banana muffin mix": "FNDDS:58610004",
            "banana nut muffin mix": "FNDDS:58610005",
            "chocolate sandwich cooky": "FNDDS:53209015",
            "strawberry pie filling": "FNDDS:63203701",
            "Corn, canned, cooked with oil": "ESHA:38910",
            "cool whip fat-free": "FNDDS:12220270",
            "dried breadcrumbs": "SR28:174928",
            "stout": "FNDDS:93101000",
            "chocolate protein powder": "SR28:173180",
            "char siu": "FNDDS:27120030",
        }
        for label, expected_key in cases.items():
            with self.subTest(label=label):
                line = _resolve_item(label, 100, allow_sr28_fallback=True, allow_fndds_fallback=False)
                self.assertEqual(line.ingredient_key, expected_key)
                self.assertIsNotNone(line.nutrition)

    def test_manual_exact_banana_muffins_use_specific_esha_leaf(self) -> None:
        banana_nut = _resolve_item("banana nut muffin", 100, allow_sr28_fallback=True, allow_fndds_fallback=False)
        self.assertEqual(banana_nut.ingredient_key, "ESHA:18966")
        self.assertEqual(banana_nut.esha_description, "Muffin, banana nut")

        banana = _resolve_item("banana muffins", 100, allow_sr28_fallback=True, allow_fndds_fallback=False)
        self.assertEqual(banana.ingredient_key, "ESHA:25738")
        self.assertEqual(banana.esha_description, "Muffin, banana")

    def test_product_identity_bridge_classifies_banana_muffin_products(self) -> None:
        banana_nut_mix = classify_product_identity("Martha White Banana Nut Muffin Mix, 7.6 oz Bag")
        self.assertIsNotNone(banana_nut_mix)
        self.assertEqual(banana_nut_mix.ingredient_key, "FNDDS:58610005")

        banana_mix = classify_product_identity("Jiffy Banana Muffin Mix")
        self.assertIsNotNone(banana_mix)
        self.assertEqual(banana_mix.ingredient_key, "FNDDS:58610004")

        baked = classify_product_identity("Bakery Fresh Banana Nut Muffins with Walnut Topping")
        self.assertIsNotNone(baked)
        self.assertEqual(baked.ingredient_key, "ESHA:18966")

        variety = classify_product_identity("Marketside Blueberry & Banana Nut Muffin Variety Pack")
        self.assertIsNone(variety)

    def test_row_gate_still_rejects_banana_muffin_product_for_walnuts(self) -> None:
        reason = _package_product_reason(
            {
                "canonical_normalized": "walnuts",
                "name": "Bakery Fresh Banana Nut Muffins with Walnut Topping",
            }
        )
        self.assertIn("product_title_adds_prepared_food", reason)

    def test_olive_oil_mayonnaise_does_not_collapse_to_plain_mayo(self) -> None:
        ok, reason = _esha_identity_gate("olive oil mayonnaise", "Dressing, mayonnaise")
        self.assertFalse(ok)
        self.assertIn("drops_mayonnaise_subtype", reason)

    def test_chipotle_mayonnaise_uses_chipotle_leaf(self) -> None:
        line = _resolve_item("chipotle mayonnaise", 100, allow_sr28_fallback=True, allow_fndds_fallback=False)
        self.assertEqual(line.ingredient_key, "ESHA:22937")
        self.assertEqual(line.esha_description, "Dressing, mayonnaise, chipotle")

    def test_unmapped_flavored_mayonnaise_does_not_buy_plain_mayo(self) -> None:
        line = _resolve_item("rosemary mayonnaise", 100, allow_sr28_fallback=True, allow_fndds_fallback=False)
        self.assertEqual(line.ingredient_key, "")
        self.assertIn("drops_mayonnaise_subtype", line.gate_reason)

    def test_canadian_bacon_uses_canadian_bacon_leaf(self) -> None:
        line = _resolve_item("canadian bacon", 100, allow_sr28_fallback=True, allow_fndds_fallback=False)
        self.assertEqual(line.ingredient_key, "ESHA:12008")
        self.assertEqual(line.esha_description, "Canadian Bacon, cured")

    def test_usda_top_round_steak_surface_uses_round_steak_leaf(self) -> None:
        line = _resolve_item(
            'Beef, round, top round steak, boneless, separable lean and fat, trimmed to 0" fat, all grades, raw',
            454,
            allow_sr28_fallback=True,
            allow_fndds_fallback=False,
        )
        self.assertEqual(line.ingredient_key, "ESHA:11409")
        self.assertEqual(line.esha_description, 'Beef, bottom round steak, raw, 1/8" trim')

    def test_usda_top_round_steak_one_eighth_trim_surface_uses_round_steak_leaf(self) -> None:
        line = _resolve_item(
            'Beef, round, top round, steak, separable lean and fat, trimmed to 1/8" fat, all grades, raw',
            680,
            allow_sr28_fallback=True,
            allow_fndds_fallback=False,
        )
        self.assertEqual(line.ingredient_key, "ESHA:11409")
        self.assertEqual(line.esha_description, 'Beef, bottom round steak, raw, 1/8" trim')

    def test_vegan_bacon_does_not_buy_pork_bacon(self) -> None:
        line = _resolve_item("vegan bacon", 100, allow_sr28_fallback=True, allow_fndds_fallback=False)
        self.assertEqual(line.ingredient_key, "ESHA:7509")
        self.assertEqual(line.esha_description, "Vegetarian Meat, bacon, strips")

    def test_vegetarian_bacon_is_not_classified_as_pork(self) -> None:
        source = _classify_protein_source("vegan bacon Vegetarian Meat, bacon, strips Bacon, meatless", "")
        self.assertEqual(source, "legumes")

    def test_bacon_bits_use_bacon_bits_leaf(self) -> None:
        line = _resolve_item("bacon bits", 100, allow_sr28_fallback=True, allow_fndds_fallback=False)
        self.assertEqual(line.ingredient_key, "ESHA:27096")
        self.assertEqual(line.esha_description, "Bacon, bits, real, serving")

    def test_bacon_seasoning_does_not_buy_plain_bacon(self) -> None:
        line = _resolve_item("bacon seasoning", 100, allow_sr28_fallback=True, allow_fndds_fallback=False)
        self.assertEqual(line.ingredient_key, "")
        self.assertTrue(line.gate_reason == "no_esha_code" or "drops_bacon_subtype" in line.gate_reason)

    def test_roast_chicken_does_not_fallback_to_raw_chicken_breast(self) -> None:
        line = _resolve_item("roast chicken", 100, allow_sr28_fallback=True, allow_fndds_fallback=False)
        self.assertNotEqual(line.ingredient_key, "SR28:171509")

    def test_plain_ham_uses_cured_roasted_ham_leaf(self) -> None:
        line = _resolve_item("ham", 100, allow_sr28_fallback=True, allow_fndds_fallback=False)
        self.assertEqual(line.ingredient_key, "ESHA:12005")
        self.assertEqual(line.esha_description, "Pork, cured ham, whole, roasted")

    def test_usda_ham_steak_surface_uses_ham_steak_leaf(self) -> None:
        line = _resolve_item(
            "Pork, cured, ham, steak, boneless, extra lean, unheated",
            907,
            allow_sr28_fallback=True,
            allow_fndds_fallback=False,
        )
        self.assertEqual(line.ingredient_key, "ESHA:12132")
        self.assertEqual(line.esha_description, "Pork, cured ham, steak, extra lean")

    def test_beef_stew_meat_surface_uses_raw_stew_meat_leaf(self) -> None:
        line = _resolve_item("BEEF STEW MEAT", 1134, allow_sr28_fallback=True, allow_fndds_fallback=False)
        self.assertEqual(line.ingredient_key, "ESHA:27997")
        self.assertEqual(line.esha_description, "Beef, stew meat, chuck, raw")
        self.assertEqual(line.nutrition_source, "sr28_direct")

    def test_usda_pork_chop_surface_uses_raw_pork_chop_leaf(self) -> None:
        line = _resolve_item(
            "Pork, fresh, loin, center loin (chops), bone-in, separable lean only, raw",
            908,
            allow_sr28_fallback=True,
            allow_fndds_fallback=False,
        )
        self.assertEqual(line.ingredient_key, "ESHA:12028")
        self.assertEqual(line.esha_description, "Pork, chop, whole loin, raw")
        self.assertEqual(line.nutrition_source, "sr28_direct")

    def test_usda_boneless_pork_chop_surface_uses_raw_pork_chop_leaf(self) -> None:
        line = _resolve_item(
            "Pork, fresh, loin, center loin (chops), boneless, separable lean only, raw",
            908,
            allow_sr28_fallback=True,
            allow_fndds_fallback=False,
        )
        self.assertEqual(line.ingredient_key, "ESHA:12028")
        self.assertEqual(line.esha_description, "Pork, chop, whole loin, raw")

    def test_usda_pork_shoulder_surface_uses_raw_pork_shoulder_leaf(self) -> None:
        line = _resolve_item(
            "Pork, fresh, shoulder, whole, separable lean and fat, raw",
            2268,
            allow_sr28_fallback=True,
            allow_fndds_fallback=False,
        )
        self.assertEqual(line.ingredient_key, "ESHA:12221")
        self.assertEqual(line.esha_description, "Pork, shoulder, whole, raw")
        self.assertEqual(line.nutrition_source, "sr28_direct")

    def test_whole_raw_chicken_surface_uses_skin_on_whole_chicken_leaf(self) -> None:
        line = _resolve_item(
            "Chicken, broilers or fryers, meat and skin, raw",
            1580,
            allow_sr28_fallback=True,
            allow_fndds_fallback=False,
        )
        self.assertEqual(line.ingredient_key, "ESHA:15071")
        self.assertEqual(line.esha_description, "Chicken, whole, unpeeled, raw")
        self.assertEqual(line.nutrition_source, "sr28_direct")

    def test_package_plain_ham_uses_same_native_leaf(self) -> None:
        self.assertEqual(PACKAGE_NATIVE_KEY_OVERRIDES["ham"][0], "ESHA:12005")

    def test_package_stew_meat_uses_raw_beef_leaf(self) -> None:
        self.assertEqual(PACKAGE_NATIVE_KEY_OVERRIDES["beef stew meat"][0], "ESHA:27997")
        self.assertEqual(PACKAGE_NATIVE_KEY_OVERRIDES["stew meat"][0], "ESHA:27997")

    def test_package_pork_chop_uses_raw_pork_chop_leaf(self) -> None:
        self.assertEqual(PACKAGE_NATIVE_KEY_OVERRIDES["pork chop"][0], "ESHA:12028")

    def test_package_pork_shoulder_uses_raw_pork_shoulder_leaf(self) -> None:
        self.assertEqual(PACKAGE_NATIVE_KEY_OVERRIDES["pork shoulder"][0], "ESHA:12221")

    def test_package_whole_chicken_uses_skin_on_whole_chicken_leaf(self) -> None:
        self.assertEqual(PACKAGE_NATIVE_KEY_OVERRIDES["whole chicken"][0], "ESHA:15071")

    def test_manual_package_seed_covers_fresh_parsley_sprigs(self) -> None:
        parsley_rows = [row for row in MANUAL_PACKAGE_ROWS if row["key"] == "ESHA:26013"]
        self.assertGreaterEqual(len(parsley_rows), 2)
        self.assertTrue(any(row["walmart_price_cents"] == 178 for row in parsley_rows))

    def test_manual_package_seed_covers_raw_egg_yolk(self) -> None:
        egg_yolk_rows = [row for row in MANUAL_PACKAGE_ROWS if row["key"] == "ESHA:19508"]
        self.assertGreaterEqual(len(egg_yolk_rows), 2)
        self.assertTrue(any(row["grams"] == 300.0 and row["walmart_price_cents"] == 96 for row in egg_yolk_rows))

    def test_manual_package_seed_covers_ham_steak(self) -> None:
        ham_steak_rows = [row for row in MANUAL_PACKAGE_ROWS if row["key"] == "ESHA:12132"]
        self.assertGreaterEqual(len(ham_steak_rows), 3)
        self.assertTrue(any(row["kroger_price_cents"] == 250 for row in ham_steak_rows))

    def test_manual_package_seed_covers_beef_stew_meat(self) -> None:
        stew_rows = [row for row in MANUAL_PACKAGE_ROWS if row["key"] == "ESHA:27997"]
        self.assertGreaterEqual(len(stew_rows), 3)
        self.assertTrue(any(row["walmart_price_cents"] == 878 for row in stew_rows))

    def test_manual_package_seed_covers_pork_chop(self) -> None:
        pork_chop_rows = [row for row in MANUAL_PACKAGE_ROWS if row["key"] == "ESHA:12028"]
        self.assertGreaterEqual(len(pork_chop_rows), 3)
        self.assertTrue(any(row["kroger_price_cents"] == 479 for row in pork_chop_rows))

    def test_manual_package_seed_covers_pork_shoulder(self) -> None:
        rows = [row for row in MANUAL_PACKAGE_ROWS if row["key"] == "ESHA:12221"]
        self.assertGreaterEqual(len(rows), 3)
        self.assertTrue(any(row["grams"] == 2268.0 and row["walmart_price_cents"] == 1499 for row in rows))

    def test_manual_package_seed_covers_whole_chicken(self) -> None:
        rows = [row for row in MANUAL_PACKAGE_ROWS if row["key"] == "ESHA:15071"]
        self.assertGreaterEqual(len(rows), 2)
        self.assertTrue(any(row["walmart_price_cents"] == 695 for row in rows))

    def test_package_nonfood_filter_allows_angel_hair_pasta(self) -> None:
        self.assertEqual(_nonfood_product_reason("Great Value Pot Perfect Angel Hair Pasta, 16 oz"), "")

    def test_package_nonfood_filter_rejects_hair_care_oil(self) -> None:
        reason = _nonfood_product_reason("Sweet Almond Oil for Skin, Body, Face, and Hair Growth Moisturizer")
        self.assertIn("nonfood_personal_care", reason)

    def test_package_nonfood_filter_rejects_soap_body_oil_and_litter(self) -> None:
        cases = [
            "Kroger Honey Citrus & Shea Butter Scent Liquid Hand Soap",
            "Nourishing Dry Body Oil - White Truffle by Cuccio Naturale for Unisex",
            "ARM & HAMMER Cat Litter Deodorizer with Baking Soda",
            "Vaseline Lock In Moisture Cocoa Butter Healing Petroleum Jelly for Dry Skin",
        ]
        for name in cases:
            with self.subTest(name=name):
                self.assertTrue(_nonfood_product_reason(name))

    def test_native_key_gate_rejects_bad_store_backed_identities(self) -> None:
        cases = [
            (
                "ESHA:10480",
                "Private Selection Natural USDA Choice Angus Beef Top Sirloin Steak",
                "missing",
            ),
            (
                "ESHA:10480",
                "Pennington Feeding Frenzy Berry Treat Suet Cake, Wild Bird Food",
                "nonfood",
            ),
            (
                "ESHA:502",
                "Great Value 98% Fat Free and 50% Less Sodium Cream of Chicken Condensed Soup",
                "missing_heavy_cream",
            ),
            (
                "ESHA:26037",
                "Simple Truth Protein Red Pepper and Italian Cheese Egg White Egg Bites",
                "white_pepper_product_adds_wrong_form",
            ),
            (
                "ESHA:63413",
                "Kroger Maple and Brown Sugar Protein Instant Oatmeal",
                "brown_sugar_product_adds_wrong_form",
            ),
            (
                "SR28:168450",
                "Kroger Roasted and Salted Pumpkin Seeds",
                "missing_canned_pumpkin_product_form",
            ),
            (
                "ESHA:38579",
                "Barilla Ready Pasta Rotini Fully Cooked Non-GMO Microwave Pasta",
                "dry_pasta_product_adds_wrong_form",
            ),
            (
                "ESHA:90965",
                "Winsor & Newton Safflower Oil, 75ml",
                "vegetable_oil_product_adds_wrong_form",
            ),
            (
                "ESHA:51685",
                "Great Value Sweetened Coconut Flakes",
                "missing",
            ),
            (
                "ESHA:13477",
                "Great Value Red Bean, 15.5 oz",
                "missing",
            ),
            (
                "ESHA:633",
                "Cheetos Simply Minis White Cheddar Cheese Chips",
                "cheddar_product_adds_wrong_form",
            ),
            (
                "SR28:171192",
                "McCormick Thick And Zesty Spaghetti Sauce Seasoning Mix",
                "combo_or_prepared_product",
            ),
            (
                "SR28:173448",
                "Velveeta Shells and Cheese Bacon Macaroni and Cheese Dinner",
                "combo_or_prepared_product",
            ),
            (
                "SR28:169731",
                "Miracle Noodle Egg White Angel Hair Vermicelli Pasta, Ready to Eat Egg White Noodles",
                "dry_egg_noodle_product_adds_wrong_form",
            ),
            (
                "ESHA:33320",
                "Knorr No Artificial Flavors Pesto Sauce Dry Spices and Seasonings Mix",
                "pesto_product_adds_wrong_form",
            ),
            (
                "ESHA:5116",
                "Progresso Vegetable Classics Green Split Pea Soup",
                "green_pea_product_adds_wrong_form",
            ),
            (
                "ESHA:5116",
                "Harvest Snaps Zesty Ranch Green Pea Snack Crisps",
                "green_pea_product_adds_wrong_form",
            ),
            (
                "ESHA:17230",
                "Great Value Chunk Style Pink Salmon Skinless Boneless, 5 oz",
                "salmon_product_adds_wrong_form",
            ),
            (
                "ESHA:17230",
                "Wild Caught Canadian Pacific Smoked King Salmon Filet",
                "salmon_product_adds_wrong_form",
            ),
            (
                "ESHA:3072",
                "Rose's Sweetened Lime Juice, 12 fl oz, Bottle",
                "lime_juice_product_adds_wrong_form",
            ),
            (
                "ESHA:31748",
                "Evolution Fresh Organic Greens & Ginger Cold-Pressed Vegetable & Fruit Juice Blend",
                "missing_ginger_syrup_product_identity",
            ),
            (
                "ESHA:38579",
                "Kroger 16 oz Spaghetti Pasta",
                "dry_pasta_product_adds_wrong_form",
            ),
            (
                "ESHA:33708",
                "Canada Dry Ginger Ale Soda Mini Cans",
                "missing_pickled_ginger_product_identity",
            ),
            (
                "ESHA:90442",
                "The Spice Way Ginger Powder - Pure Dry Ground Powdered Root - 8 oz.",
                "fresh_ginger_product_adds_wrong_form",
            ),
            (
                "ESHA:4086",
                "Organic Ginger Root",
                "missing_ground_ginger_product_identity",
            ),
            (
                "ESHA:90212",
                "Marzetti Asiago Peppercorn Dressing",
                "missing_black_pepper_product_identity",
            ),
            (
                "ESHA:90212",
                "Kroger Cook In Bag Peppercorn Seasoned Pork Loin Filet",
                "missing_black_pepper_product_identity",
            ),
            (
                "ESHA:26003",
                "Pillsbury Orange Cinnabon Cinnamon Rolls with Orange Icing",
                "ground_cinnamon_product_adds_wrong_form",
            ),
            (
                "ESHA:26003",
                "Cinnamon Toast Crunch Cinnadust Seasoning Blend",
                "ground_cinnamon_product_adds_wrong_form",
            ),
            (
                "ESHA:1817",
                "Great Value Sugar Snap Pea Stir-Fry, 20 oz (Frozen) Vegetables Mix",
                "frozen_pea_product_adds_wrong_form",
            ),
            (
                "ESHA:1817",
                "Great Value Frozen Peas and Carrots, 12 oz (Steamable)",
                "frozen_pea_product_adds_wrong_form",
            ),
            (
                "ESHA:28000",
                "Bakery Fresh Glazed Yeast Donuts",
                "active_dry_yeast_product_adds_wrong_form",
            ),
            (
                "ESHA:28000",
                "Bragg Nutritional Yeast Seasoning",
                "active_dry_yeast_product_adds_wrong_form",
            ),
            (
                "ESHA:4557",
                "Kroger Raisin Apple & Walnut High Fiber Instant Oatmeal",
                "walnut_product_adds_wrong_form",
            ),
            (
                "ESHA:4557",
                "Bakery Fresh Banana Walnut Loaf Cake",
                "walnut_product_adds_wrong_form",
            ),
            (
                "ESHA:15762",
                "Kroger 99% Fat Free Chicken Broth",
                "missing_chicken_bouillon_product_identity",
            ),
            (
                "ESHA:15762",
                "Kitchen Basics Chicken Bone Broth, 8.25 oz Carton",
                "missing_chicken_bouillon_product_identity",
            ),
            (
                "ESHA:15762",
                "Knorr Tomato with Chicken Flavor Bouillon Cubes",
                "chicken_bouillon_product_adds_wrong_form",
            ),
            (
                "ESHA:24144",
                "Pillsbury Moist Supreme German Chocolate Cake Mix, 15.25 oz Box",
                "milk_chocolate_product_adds_wrong_form",
            ),
            (
                "ESHA:24144",
                "Kroger Semi Sweet Mini Chocolate Chips",
                "milk_chocolate_product_adds_wrong_form",
            ),
            (
                "ESHA:1235",
                "Kroger Chunky Blue Cheese Salad Dressing",
                "blue_cheese_product_adds_wrong_form",
            ),
            (
                "ESHA:1235",
                "Kraft Roka Blue Cheese Spread with Philadelphia Cream Cheese",
                "blue_cheese_product_adds_wrong_form",
            ),
            (
                "ESHA:1235",
                "Blue Diamond Nut-Thins Pepper Jack Cheese Almond Rice Crackers",
                "blue_cheese_product_adds_wrong_form",
            ),
            (
                "SR28:169655",
                "Mott's No Sugar Added Cinnamon Applesauce Cups",
                "sugar_product_adds_wrong_form",
            ),
            (
                "SR28:169655",
                "Pop-Tarts Frosted Brown Sugar Cinnamon Toaster Pastries",
                "sugar_product_adds_wrong_form",
            ),
            (
                "SR28:169655",
                "Trident Cinnamon Sugar Free Gum",
                "sugar_product_adds_wrong_form",
            ),
            (
                "SR28:169655",
                "Stacy's Pita Chips Cinnamon Sugar",
                "combo_or_prepared_product",
            ),
        ]
        for key, name, expected in cases:
            with self.subTest(key=key, name=name):
                reason = _package_native_key_product_reason({"name": name}, key)
                self.assertIn(expected, reason)

    def test_native_key_gate_accepts_real_store_products(self) -> None:
        cases = [
            ("ESHA:633", "Kroger Medium Cheddar Sliced Cheese"),
            ("ESHA:502", "Great Value Heavy Whipping Cream"),
            ("ESHA:25765", "Land O Lakes Salted Butter in Half Sticks, 4 Half Sticks, 8 oz Pack"),
            ("ESHA:26037", "Rani White Pepper Whole Spice 3oz Jar"),
            ("ESHA:63413", "C&H Premium Pure Cane Light Brown Sugar"),
            ("ESHA:38579", "Ronco 8 oz Large Elbow Macaroni"),
            ("ESHA:90965", "Crisco Pure Canola Oil, Cooking Oil, 1 gal"),
            ("ESHA:13477", "Great Value Black Beans, 15 oz Can"),
            ("ESHA:51685", "Vita Coco Coconut Water"),
            ("SR28:171192", "Hunt's Tomato Sauce"),
            ("SR28:169731", "Inn Maid Wide Egg Noodles"),
            ("SR28:173448", "Velveeta Original Cheese Loaf"),
            ("SR28:171413", "Bertolli Extra Virgin Olive Oil"),
            ("SR28:168450", "Libby's 100% Pure Canned Pumpkin"),
            ("ESHA:33320", "Barilla Rustic Basil Pesto Pasta Sauce, 6.5 oz"),
            ("ESHA:5116", "Simple Truth Frozen Green Peas"),
            ("ESHA:17230", "Kroger Fresh Farm Raised Atlantic Salmon Fillet"),
            ("ESHA:3072", "Kroger 100% Lime Juice"),
            ("ESHA:38579", "Kroger Elbow Macaroni Pasta"),
            ("ESHA:33708", "The Ginger People Organic Pickled Sushi Ginger"),
            ("ESHA:90442", "Organic Ginger Root"),
            ("ESHA:4086", "Kroger Ground Ginger Shaker"),
            ("ESHA:90212", "Smart Way Ground Black Pepper"),
            ("ESHA:26003", "Great Value Kosher Ground Cinnamon"),
            ("ESHA:1817", "Great Value Frozen Sweet Peas, 32 oz Bag"),
            ("ESHA:28000", "Red Star Active Dry Yeast 2 lb. bag"),
            ("ESHA:4557", "Great Value Natural Walnut Halves & Pieces, 7.25 Oz"),
            ("ESHA:15762", "Great Value Chicken Bouillon Powder 3.75 oz Jar"),
            ("ESHA:24144", "Ritter Sport Milk Chocolate Candy Bar with Crunchy Whole Hazelnuts"),
            ("ESHA:1235", "Frigo Crumble Blue Cheese Cup"),
            ("SR28:169655", "Great Value Cinnamon Sugar, 3.62 oz"),
            ("SR28:169655", "Smart Way 4lb Granulated Sugar Bag"),
        ]
        for key, name in cases:
            with self.subTest(key=key, name=name):
                self.assertEqual(_package_native_key_product_reason({"name": name}, key), "")

    def test_coverage_package_seed_uses_high_impact_consensus_identities(self) -> None:
        cases = [
            ("Swanson® Chicken Broth", "SR28:174536"),
            ("Fresh Large Green Bell Pepper", "ESHA:6846"),
            ("Kroger® Ground Cumin Shaker", "ESHA:26503"),
            ("Kroger® Half and Half Quart", "SR28:171255"),
            ("Simple Truth Organic™ Cage Free 100% Liquid Egg Whites", "ESHA:21111"),
            ("Private Selection® Ground Coriander Seed Shaker", "SR28:170922"),
            ("Hunt's Tomato Sauce", "SR28:171192"),
            ("Kroger® Sweetened Coconut Flakes", "ESHA:4511"),
            ("Simple Truth Organic® Fresh Seedless Mandarin Oranges Bag", "ESHA:31312"),
            ("Green Onions", "ESHA:90485"),
            ("Kroger® Cut and Peeled Baby Carrots", "ESHA:9329"),
            ("Kroger® Tomato Puree", "SR28:170460"),
            ("Kroger No Salt Golden Whole Kernel Sweet Corn", "ESHA:45268"),
            ("Fresh Banana", "ESHA:51329"),
            ("Kroger® Puff Pastry Sheets", "SR28:172790"),
            ("Simple Truth® Halves & Pieces Walnuts", "ESHA:49277"),
            ("Sun-Maid® California Golden Raisins", "ESHA:3934"),
            ("Kroger® Red Food Coloring", "FNDDS:94000000"),
            ("Progresso Plain Style Bread Crumbs", "SR28:174928"),
            ("Baker's Semi-Sweet Chocolate Premium Baking Bar with 56% Cacao", "ESHA:41524"),
            ("Baker's Unsweetened Chocolate Premium Baking Bar with 100 % Cacao", "ESHA:24169"),
            ("Ghirardelli® Premium 60% Cacao Bittersweet Chocolate Baking Bar", "ESHA:4356"),
            ("Great Value White Chocolate Baking Bar", "ESHA:90659"),
            ("Knox Original Unflavored Gelatin, 4 ct. Packets", "ESHA:23429"),
            ("Kroger® 100% Whole Wheat Hamburger Buns", "FNDDS:51320070"),
            ("Chicken of the Sea Wild Caught Lump Crabmeat 6 oz", "SR28:171966"),
            ("Great Value Cooked Ham, 16 oz", "ESHA:91505"),
            ("Pillsbury Refrigerated Crescent Dinner Rolls", "ESHA:16638"),
            ("Great Value Yellow Mustard Seeds", "ESHA:26110"),
            ("Old El Paso Refried Beans", "ESHA:13478"),
            ("Keebler Ready Crust Graham Cracker Pie Crust", "SR28:167520"),
            ("Colgin Liquid Smoke", "ESHA:53417"),
            ("Indian Head Yellow Cornmeal", "ESHA:38004"),
            ("Fresh Bean Sprouts", "SR28:169957"),
            ("Simple Truth® Frozen Green Peas", "ESHA:1817"),
            ("Del Monte Sweet Peas", "ESHA:5116"),
            ("Spice World Ready-to-Use Minced Ginger", "ESHA:90442"),
            ("Kroger® Ground Ginger Shaker", "ESHA:4086"),
        ]
        for name, expected_key in cases:
            with self.subTest(name=name):
                rule = _coverage_package_seed_rule({"name": name, "grams": "453.592"})
                self.assertIsNotNone(rule)
                self.assertEqual(rule["key"], expected_key)

    def test_coverage_package_seed_rejects_component_or_wrong_form_titles(self) -> None:
        cases = [
            "Kroger® Chicken Breast Fajitas with Bell Peppers and Onions",
            "Daisy Sour Cream French Onion Dip, 16 oz Tub",
            "No Yolks® Egg White Pasta Dumplings",
            "Simple Truth® Dark Chocolate Coated Almonds with Sea Salt",
            "Banana Boat Sport Ultra SPF 30 Sunscreen Spray",
            "Laura Scudders Green Onion Dip Mix",
            "NPG Purple Sweet Potato Powder Natural Food Coloring Powder",
            "Simple Truth Organic® Unsweetened Coconut Flakes",
            "Chef Boyardee Spaghetti Rings",
            "Gorton’s Crunchy Breaded Fish Sticks with Panko Breadcrumbs",
            "Agar Agar Powder Vegan Unflavored Gelatin Substitute",
            "Kroger® Crab Select Imitation Crab Meat",
            "Bar-S Deli Style Smoked Ham Lunch Meat",
            "Beech-Nut Stage 1 Baby Food, Chicken & Chicken Broth",
            "Canada Dry Ginger Ale Soda Mini Cans",
            "Kroger® Ginger Snaps Cookies",
            "Great Value Sugar Snap Pea Stir-Fry, 20 oz (Frozen) Vegetables Mix",
            "Knorr Cheesy Cheddar Rotini Pasta Sides",
            "Campbell's SpaghettiOs Shapes Canned Pasta",
            "Chef Boyardee Spaghetti and Meatballs in Tomato Sauce",
            "Great Value Pork & Beans in Tomato Sauce",
        ]
        for name in cases:
            with self.subTest(name=name):
                self.assertIsNone(_coverage_package_seed_rule({"name": name, "grams": "453.592"}))

    def test_package_product_gate_accepts_plain_mayo(self) -> None:
        reason = _package_product_reason(
            {
                "canonical_normalized": "mayonnaise",
                "name": "Duke's Real Mayonnaise, 16 oz Jar, Smooth & Creamy Mayo",
            }
        )
        self.assertEqual(reason, "")

    def test_package_product_gate_rejects_olive_oil_mayo(self) -> None:
        reason = _package_product_reason(
            {
                "canonical_normalized": "mayonnaise",
                "name": "Kroger Olive Oil Mayo",
            }
        )
        self.assertIn("mayonnaise_product_adds_subtype", reason)

    def test_package_product_gate_rejects_mayo_for_salad_oil(self) -> None:
        reason = _package_product_reason(
            {
                "canonical_normalized": "salad oil",
                "name": "Kroger Olive Oil Mayo",
            }
        )
        self.assertEqual(reason, "mayo_product_for_non_mayo_canonical")

    def test_package_product_gate_rejects_fat_free_mayo_missing_subtype(self) -> None:
        reason = _package_product_reason(
            {
                "canonical_normalized": "mayo fat free mayonnaise dressing",
                "name": "Hellmann's Olive Oil Mayo",
            }
        )
        self.assertIn("mayonnaise_product_adds_subtype", reason)

    def test_package_product_gate_rejects_face_cream(self) -> None:
        reason = _package_product_reason(
            {
                "canonical_normalized": "light cream",
                "name": "Nature Skin Shop Derma Light Brightening Face Cream 1 oz",
            }
        )
        self.assertIn("nonfood_personal_care", reason)

    def test_package_product_gate_rejects_turkey_sausage_for_turkey_bacon(self) -> None:
        reason = _package_product_reason(
            {
                "canonical_normalized": "turkey bacon",
                "name": "Banquet Brown N Serve Turkey Sausage Links",
            }
        )
        self.assertIn("missing_bacon_product_identity", reason)

    def test_package_product_gate_rejects_turkey_bacon_for_plain_bacon(self) -> None:
        reason = _package_product_reason(
            {
                "canonical_normalized": "bacon",
                "name": "Butterball Turkey Bacon Original",
            }
        )
        self.assertIn("bacon_product_adds_subtype", reason)

    def test_package_product_gate_accepts_matching_turkey_bacon(self) -> None:
        reason = _package_product_reason(
            {
                "canonical_normalized": "turkey bacon",
                "name": "Butterball Turkey Bacon Original",
            }
        )
        self.assertEqual(reason, "")

    def test_package_product_gate_rejects_bacon_seasoning_for_plain_bacon(self) -> None:
        reason = _package_product_reason(
            {
                "canonical_normalized": "bacon",
                "name": "HI-West Hickory Bacon BBQ Seasoning 5oz",
            }
        )
        self.assertIn("bacon_product_adds_form", reason)

    def test_package_product_gate_rejects_imitation_bacon_bits_for_real_bits(self) -> None:
        reason = _package_product_reason(
            {
                "canonical_normalized": "bacon bits",
                "name": "Great Value Imitation Bacon Bits, 3 oz",
            }
        )
        self.assertIn("bacon_product_adds_meatless_subtype", reason)

    def test_package_product_gate_rejects_pickle_chip_for_canned_ham(self) -> None:
        reason = _package_product_reason(
            {
                "canonical_normalized": "canned ham",
                "name": "Kroger Hamburger Dill Pickle Chips",
            }
        )
        self.assertEqual(reason, "missing_ham_product_identity")

    def test_package_product_gate_rejects_lunchmeat_for_plain_ham(self) -> None:
        reason = _package_product_reason(
            {
                "canonical_normalized": "ham",
                "name": "Bar-S Deli Style Smoked Ham Lunch Meat, 16 oz",
            }
        )
        self.assertEqual(reason, "ham_product_adds_lunchmeat_form")

    def test_package_product_gate_rejects_generic_meat_surface(self) -> None:
        reason = _package_product_reason(
            {
                "canonical_normalized": "meat",
                "name": "Bar-S Classic Bologna",
            }
        )
        self.assertEqual(reason, "generic_meat_surface_not_purchase_specific_enough")

    def test_package_product_gate_accepts_beef_stew_meat(self) -> None:
        reason = _package_product_reason(
            {
                "canonical_normalized": "beef stew meat",
                "name": "Lean Beef Stew Meat, Tray, Fresh, 0.75 - 1.25 lb",
            }
        )
        self.assertEqual(reason, "")

    def test_package_product_gate_accepts_boneless_stew_beef(self) -> None:
        reason = _package_product_reason(
            {
                "canonical_normalized": "stew meat",
                "name": "Boneless Stew Beef Family Pack",
            }
        )
        self.assertEqual(reason, "")

    def test_package_product_gate_rejects_beef_stew_seasoning(self) -> None:
        reason = _package_product_reason(
            {
                "canonical_normalized": "beef stew meat",
                "name": "Great Value Beef Stew Seasoning Mix, 1.5 oz",
            }
        )
        self.assertIn("beef_stew_meat_product_adds_prepared_form", reason)

    def test_package_product_gate_rejects_canned_beef_stew(self) -> None:
        reason = _package_product_reason(
            {
                "canonical_normalized": "beef stew meat",
                "name": "DINTY MOORE Beef Stew with Potatoes & Carrots, 20 oz Steel Can",
            }
        )
        self.assertIn("beef_stew_meat_product_adds_prepared_form", reason)

    def test_package_product_gate_rejects_prepared_beef_stew_without_meat_pack_identity(self) -> None:
        reason = _package_product_reason(
            {
                "canonical_normalized": "beef stew meat",
                "name": "KR Beef Stew 20 oz",
            }
        )
        self.assertEqual(reason, "missing_beef_stew_meat_product_identity")

    def test_package_product_gate_accepts_plain_pork_chop(self) -> None:
        reason = _package_product_reason(
            {
                "canonical_normalized": "pork chop",
                "name": "Thin Cut Bone-In Pork Loin Center-Cut Chop",
            }
        )
        self.assertEqual(reason, "")

    def test_package_product_gate_rejects_pork_chop_frozen_meal(self) -> None:
        reason = _package_product_reason(
            {
                "canonical_normalized": "pork chop",
                "name": "Marie Callender's Country Fried Pork Chop & Gravy Frozen Meal",
            }
        )
        self.assertIn("pork_chop_product_adds_prepared_form", reason)

    def test_package_product_gate_rejects_stuffed_pork_chop(self) -> None:
        reason = _package_product_reason(
            {
                "canonical_normalized": "pork chop",
                "name": "Marketside Pork Chops stuffed with Bacon & Cheddar Cheese",
            }
        )
        self.assertIn("pork_chop_product_adds_prepared_form", reason)

    def test_package_product_gate_rejects_pork_chop_patty(self) -> None:
        reason = _package_product_reason(
            {
                "canonical_normalized": "pork chop",
                "name": "Healthy Answer Pork Choppee - Pork Chop Patty, 40 Pieces of 4 Ounce",
            }
        )
        self.assertIn("pork_chop_product_adds_prepared_form", reason)

    def test_package_product_gate_accepts_plain_pork_shoulder(self) -> None:
        reason = _package_product_reason(
            {
                "canonical_normalized": "pork shoulder",
                "name": "Kroger Fresh Natural Pork Shoulder Butt Bone In",
            }
        )
        self.assertEqual(reason, "")

    def test_package_product_gate_rejects_ham_shank_for_pork_shoulder(self) -> None:
        reason = _package_product_reason(
            {
                "canonical_normalized": "pork shoulder",
                "name": "Sugardale Ham Shank Portion (limit 2 At Sale Price)",
            }
        )
        self.assertEqual(reason, "missing_pork_shoulder_product_identity")

    def test_package_product_gate_rejects_tamales_for_pork_shoulder(self) -> None:
        reason = _package_product_reason(
            {
                "canonical_normalized": "pork shoulder",
                "name": "La Preferida Beef & Pork Tamales with Sauce",
            }
        )
        self.assertEqual(reason, "missing_pork_shoulder_product_identity")

    def test_package_product_gate_accepts_raw_whole_chicken(self) -> None:
        reason = _package_product_reason(
            {
                "canonical_normalized": "whole chicken",
                "name": "Foster Farms Fresh & Natural Cage Free Whole Chicken",
            }
        )
        self.assertEqual(reason, "")

    def test_package_product_gate_rejects_rotisserie_for_raw_whole_chicken(self) -> None:
        reason = _package_product_reason(
            {
                "canonical_normalized": "whole chicken",
                "name": "(Hot) Freshness Guaranteed Traditional Rotisserie Whole Chicken",
            }
        )
        self.assertIn("whole_chicken_product_adds_prepared_form", reason)

    def test_package_product_gate_accepts_round_steak(self) -> None:
        reason = _package_product_reason(
            {
                "canonical_normalized": "round steak",
                "name": "Beef Round Steak, 0.97 - 2.5 lb Tray",
            }
        )
        self.assertEqual(reason, "")

    def test_package_product_gate_rejects_ground_beef_for_round_steak(self) -> None:
        reason = _package_product_reason(
            {
                "canonical_normalized": "round steak",
                "name": "85% Lean / 15% Fat Ground Beef Round, 1 lb Tray, Fresh, All Natural",
            }
        )
        self.assertEqual(reason, "missing_round_steak_product_identity")

    def test_package_product_gate_rejects_deli_pastrami_for_round_steak(self) -> None:
        reason = _package_product_reason(
            {
                "canonical_normalized": "round steak",
                "name": "Private Selection Top Round Angus Uncured Deli Pastrami Sliced",
            }
        )
        self.assertEqual(reason, "missing_round_steak_product_identity")

    def test_native_key_gate_rejects_tenderloin_for_pork_chop_key(self) -> None:
        reason = _package_native_key_product_reason(
            {
                "canonical_normalized": "pork steak",
                "name": "Kroger Fresh Natural Pork Tenderloin",
            },
            "ESHA:12028",
        )
        self.assertEqual(reason, "missing_pork_chop_product_identity")

    def test_native_key_gate_rejects_lone_pork_loin_for_pork_chop_key(self) -> None:
        reason = _package_native_key_product_reason(
            {
                "canonical_normalized": "boneless pork loin",
                "name": "Kroger Fresh Natural Pork Loin Boneless",
            },
            "ESHA:12028",
        )
        self.assertEqual(reason, "missing_pork_chop_product_identity")

    def test_native_key_gate_accepts_real_pork_chop_for_pork_chop_key(self) -> None:
        reason = _package_native_key_product_reason(
            {
                "canonical_normalized": "pork loin",
                "name": "Pork Loin Center Cut Chops Bone-In",
            },
            "ESHA:12028",
        )
        self.assertEqual(reason, "")

    def test_native_key_gate_rejects_beans_for_pork_shoulder_key(self) -> None:
        reason = _package_native_key_product_reason(
            {
                "canonical_normalized": "pork and beans",
                "name": "Kroger Pork & Beans",
            },
            "ESHA:12221",
        )
        self.assertEqual(reason, "missing_pork_shoulder_product_identity")

    def test_native_key_gate_accepts_real_pork_shoulder_for_pork_shoulder_key(self) -> None:
        reason = _package_native_key_product_reason(
            {
                "canonical_normalized": "fresh pork",
                "name": "Kroger Fresh Natural Pork Shoulder Butt Bone In",
            },
            "ESHA:12221",
        )
        self.assertEqual(reason, "")

    def test_native_key_gate_rejects_rotisserie_for_whole_chicken_key(self) -> None:
        reason = _package_native_key_product_reason(
            {
                "canonical_normalized": "chicken",
                "name": "(Hot) Freshness Guaranteed Traditional Rotisserie Whole Chicken",
            },
            "ESHA:15071",
        )
        self.assertIn("whole_chicken_product_adds_prepared_form", reason)

    def test_native_key_gate_rejects_parsley_flakes_for_fresh_parsley_key(self) -> None:
        reason = _package_native_key_product_reason(
            {
                "canonical_normalized": "fresh parsley",
                "name": "Great Value Parsley Flakes, 0.4 oz",
            },
            "ESHA:26013",
        )
        self.assertIn("fresh_parsley_product_adds_wrong_form", reason)

    def test_native_key_gate_accepts_real_fresh_parsley_for_fresh_parsley_key(self) -> None:
        reason = _package_native_key_product_reason(
            {
                "canonical_normalized": "fresh parsley",
                "name": "Simple Truth Organic Italian Parsley",
            },
            "ESHA:26013",
        )
        self.assertEqual(reason, "")

    def test_package_price_gate_rejects_ham_sale_unit_price(self) -> None:
        reason = _package_price_reason(
            {
                "canonical_normalized": "ham",
                "name": "Kroger Spiral Sliced Honey Ham Half (8-10 Lb) (limit 2 At Sale Price)",
            },
            "ESHA:12005",
            4082.328,
            85,
        )
        self.assertIn("ham_probable_unit_price", reason)

    def test_package_price_gate_rejects_implausibly_cheap_large_ham(self) -> None:
        reason = _package_price_reason(
            {
                "canonical_normalized": "ham",
                "name": "Private Selection Bone In Spiral Sliced Ham with Brown Sugar Glaze",
            },
            "ESHA:12005",
            4898.794,
            349,
        )
        self.assertEqual(reason, "ham_implausible_large_package_unit_price")

    def test_package_price_gate_rejects_implausibly_cheap_large_pork_chops(self) -> None:
        reason = _package_price_reason(
            {
                "canonical_normalized": "pork chop",
                "name": "Pork Center Cut Loin Chops Thin Boneless, 5 count, 0.83 - 1.03 lb",
            },
            "ESHA:12028",
            6556.643,
            537,
        )
        self.assertEqual(reason, "pork_chop_implausible_large_package_unit_price")

    def test_package_price_gate_rejects_pork_chop_per_pound_price_as_package(self) -> None:
        reason = _package_price_reason(
            {
                "canonical_normalized": "pork chop",
                "name": "Kroger Pork Loin Assorted End Chop Bone",
            },
            "ESHA:12028",
            1202.019,
            399,
        )
        self.assertEqual(reason, "pork_chop_implausible_low_unit_price")

    def test_package_price_gate_rejects_pork_shoulder_per_pound_price_as_package(self) -> None:
        reason = _package_price_reason(
            {
                "canonical_normalized": "pork shoulder",
                "name": "Kroger Fresh Natural Pork Shoulder Butt Bone In",
            },
            "ESHA:12221",
            3401.94,
            299,
        )
        self.assertEqual(reason, "pork_shoulder_implausible_low_unit_price")

    def test_package_price_gate_rejects_large_fresh_parsley_pack(self) -> None:
        reason = _package_price_reason(
            {
                "canonical_normalized": "fresh parsley",
                "name": "Parsley",
            },
            "ESHA:26013",
            453.592,
            119,
        )
        self.assertEqual(reason, "fresh_parsley_implausible_large_package")

    def test_egg_count_package_grams_corrects_cooked_egg_count(self) -> None:
        grams = _egg_count_package_grams(
            {
                "canonical_normalized": "boiled egg",
                "name": "Great Value Cage-Free Grade AA Large White Eggs, 6 Count",
            },
            "ESHA:35876",
            6000.0,
        )
        self.assertEqual(grams, 300.0)

    def test_package_product_gate_rejects_pancake_mix_for_buttermilk(self) -> None:
        reason = _package_product_reason(
            {
                "canonical_normalized": "whole buttermilk",
                "name": "Pearl Milling Company Complete Pancake Mix Buttermilk",
            }
        )
        self.assertIn("buttermilk_product_adds_form", reason)

    def test_package_product_gate_rejects_goat_milk_for_buttermilk(self) -> None:
        reason = _package_product_reason(
            {
                "canonical_normalized": "whole buttermilk",
                "name": "Meyenberg Fresh Whole Goat Milk",
            }
        )
        self.assertEqual(reason, "missing_buttermilk_product_identity")

    def test_package_product_gate_rejects_filled_evaporated_milk(self) -> None:
        reason = _package_product_reason(
            {
                "canonical_normalized": "evaporated milk",
                "name": "Iberia Evaporated Filled Milk, 12 fl oz",
            }
        )
        self.assertEqual(reason, "evaporated_milk_product_adds_subtype:filled")

    def test_package_product_gate_rejects_lunchmeat_for_chicken_breast(self) -> None:
        reason = _package_product_reason(
            {
                "canonical_normalized": "chicken breast",
                "name": "Deli Fresh Rotisserie Seasoned Chicken Breast Lunch Meat",
            }
        )
        self.assertIn("chicken_breast_product_adds_prepared_form", reason)

    def test_package_product_gate_rejects_breaded_chicken_for_raw_breast(self) -> None:
        reason = _package_product_reason(
            {
                "canonical_normalized": "chicken breast",
                "name": "Just Bare Fully Cooked Lightly Breaded Chicken Breast Original Fillets",
            }
        )
        self.assertIn("chicken_breast_product_adds_prepared_form", reason)

    def test_egg_count_package_grams_corrects_count_as_kilograms(self) -> None:
        grams = _egg_count_package_grams(
            {
                "canonical_normalized": "eggs",
                "name": "Great Value Cage-Free Large White Eggs, 12 Count",
            },
            "ESHA:19500",
            12000.0,
        )
        self.assertEqual(grams, 600.0)

    def test_package_product_gate_accepts_shell_eggs(self) -> None:
        reason = _package_product_reason(
            {
                "canonical_normalized": "egg",
                "name": "Kroger Grade A Large White Eggs",
            }
        )
        self.assertEqual(reason, "")

    def test_package_product_gate_rejects_egg_roll_for_shell_egg(self) -> None:
        reason = _package_product_reason(
            {
                "canonical_normalized": "egg",
                "name": "Tai Pei Chicken Egg Rolls",
            }
        )
        self.assertIn("egg_product_adds_subtype", reason)

    def test_no_identity_overlap_does_not_fallback_to_generic_mayo(self) -> None:
        self.assertFalse(
            _sr28_fallback_allowed(
                "remoulade",
                "Salad dressing, mayonnaise, regular",
                "no_identity_overlap",
            )
        )

    def test_prepared_form_reject_can_fallback_to_matching_sr28(self) -> None:
        self.assertTrue(
            _sr28_fallback_allowed(
                "chicken breast",
                "Chicken, broilers or fryers, breast, skinless, boneless, meat only, raw",
                "esha_adds_prepared_form:lunchmeat",
            )
        )


if __name__ == "__main__":
    unittest.main()
