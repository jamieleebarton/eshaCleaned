import unittest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from calculator import calculate_line
from surface_lab_calculator import calculate_lab
from schema import NutritionState, ShoppingState


class EndToEndCalculatorTests(unittest.TestCase):
    def test_butter_one_cup(self):
        r = calculate_line(display="1 cup butter, softened", item="butter")
        self.assertEqual(r.canonical_name, "butter")
        self.assertIsNotNone(r.grams)
        self.assertAlmostEqual(r.grams, 227, delta=10)
        self.assertIsNotNone(r.nutrition)
        self.assertGreater(r.nutrition.kcal, 1500)  # 227g butter ≈ 1628 kcal
        self.assertGreater(len(r.products), 0)
        self.assertIn(r.nutrition_state, (NutritionState.EXACT_USDA_ANCHOR, NutritionState.REVIEWED_LOCAL_LABEL_ANCHOR))

    def test_one_egg(self):
        r = calculate_line(display="1 large egg", item="egg")
        self.assertEqual(r.canonical_name, "egg")
        self.assertAlmostEqual(r.grams, 50, delta=5)
        self.assertGreater(r.nutrition.kcal, 50)  # 1 large egg ≈ 72 kcal
        self.assertLess(r.nutrition.kcal, 100)

    def test_non_food_excluded_from_success(self):
        r = calculate_line(display="6 wooden toothpicks", item="wooden toothpicks")
        self.assertEqual(r.nutrition_state, NutritionState.NON_FOOD)
        self.assertEqual(r.shopping_state, ShoppingState.NON_FOOD)

    def test_unknown_line_is_nutrition_unknown(self):
        r = calculate_line(display="1 cup xyzzy gronkplunk", item="xyzzy gronkplunk")
        self.assertEqual(r.nutrition_state, NutritionState.NUTRITION_UNKNOWN)

    def test_grams_hint_respected(self):
        r = calculate_line(display="some butter, melted", item="butter", grams_hint=100.0)
        self.assertEqual(r.grams, 100.0)

    def test_salt_shopping_products_exclude_flavored_and_pickling_noise(self):
        r = calculate_line(display="salt", item="salt")
        top = [p.description.lower() for p in r.products[:10]]
        self.assertTrue(top)
        self.assertTrue(all("canning" not in desc for desc in top))
        self.assertTrue(all("pickling" not in desc for desc in top))
        self.assertTrue(all("celery salt" not in desc for desc in top))
        self.assertTrue(all("season" not in desc for desc in top))

    def test_sugar_uses_granulated_sugar_card_candidates(self):
        r = calculate_line(display="sugar", item="sugar")
        top = [p.description.lower() for p in r.products[:10]]
        self.assertGreater(len(top), 0)
        self.assertIn("shopping_lab_overlay", " ".join(r.path))
        banned = ("tea", "pudding", "dessert mix", "pie filling", "drink")
        self.assertTrue(all(not any(term in desc for term in banned) for desc in top))
        self.assertTrue(all("sugar" in desc for desc in top))

    def test_garlic_uses_fresh_garlic_card_candidates(self):
        r = calculate_line(display="garlic", item="garlic")
        top = [p.description.lower() for p in r.products[:10]]
        self.assertGreater(len(top), 0)
        self.assertIn("shopping_lab_overlay", " ".join(r.path))
        banned = ("minced", "pickled", "sweet", "crushed", "chopped")
        self.assertTrue(all(not any(term in desc for term in banned) for desc in top))
        self.assertTrue(any("garlic" in desc for desc in top))

    def test_butter_uses_plain_butter_card_candidates(self):
        r = calculate_line(display="butter", item="butter")
        top = [p.description.lower() for p in r.products[:10]]
        self.assertGreater(len(top), 0)
        self.assertIn("shopping_lab_overlay", " ".join(r.path))
        banned = ("syrup", "spreadable", "blend", "ghee", "clarified", "peanut butter", "cookie butter")
        self.assertTrue(all(not any(term in desc for term in banned) for desc in top))
        self.assertTrue(any("butter" in desc for desc in top))

    def test_butter_lab_prefers_reviewed_esha_lookup_store(self):
        r = calculate_lab(display="butter", item="butter")
        self.assertGreater(len(r.products), 0)
        self.assertTrue(all(p.source == "esha_reviewed_lookup" for p in r.products[:5]))

    def test_cheddar_cheese_uses_plain_cheddar_card_candidates(self):
        r = calculate_line(display="cheddar cheese", item="cheddar cheese")
        top = [p.description.lower() for p in r.products[:10]]
        self.assertGreater(len(top), 0)
        self.assertIn("shopping_lab_overlay", " ".join(r.path))
        banned = ("jack", "monterey", "cashew", "mexican", "pizza", "mac", "snack", "taco", "mozzarella")
        self.assertTrue(all(not any(term in desc for term in banned) for desc in top))
        self.assertTrue(all("cheddar" in desc for desc in top))

    def test_cheddar_cheese_lab_prefers_reviewed_esha_lookup_store(self):
        r = calculate_lab(display="cheddar cheese", item="cheddar cheese")
        self.assertGreater(len(r.products), 0)
        self.assertTrue(all(p.source == "esha_reviewed_lookup" for p in r.products[:5]))

    def test_tomato_shopping_products_stay_fresh_side(self):
        r = calculate_line(display="tomato", item="tomato")
        top = [p.description.lower() for p in r.products[:10]]
        self.assertTrue(top)
        banned = ("diced", "chopped", "canned", "paste", "sauce", "puree", "green tomato", "breaded")
        self.assertTrue(all(not any(term in desc for term in banned) for desc in top))

    def test_extra_virgin_olive_oil_uses_exact_products(self):
        r = calculate_line(display="extra virgin olive oil", item="extra virgin olive oil")
        self.assertGreater(len(r.products), 0)
        self.assertTrue(
            any(marker in " ".join(r.path) for marker in ("shopping_fts_fallback", "shopping_lab_overlay"))
        )
        self.assertTrue(all("extra virgin" in p.description.lower() for p in r.products[:5]))

    def test_iceberg_lettuce_uses_card_side_head_candidates(self):
        r = calculate_line(display="iceberg lettuce", item="iceberg lettuce")
        top = [p.description.lower() for p in r.products[:5]]
        self.assertGreater(len(top), 0)
        self.assertIn("shopping_lab_overlay", " ".join(r.path))
        self.assertTrue(all("iceberg" in desc for desc in top))
        self.assertTrue(all("shredded" not in desc for desc in top))
        self.assertTrue(all("butter lettuce" not in desc for desc in top))

    def test_onion_uses_plain_fresh_onion_card_candidates(self):
        r = calculate_line(display="onion", item="onion")
        top = [p.description.lower() for p in r.products[:10]]
        self.assertGreater(len(top), 0)
        self.assertIn("shopping_lab_overlay", " ".join(r.path))
        banned = ("ring", "rings", "dip", "soup", "powder", "potato", "pepper", "peppers", "pearl")
        self.assertTrue(all(not any(term in desc for term in banned) for desc in top))
        self.assertTrue(any("onion" in desc for desc in top))

    def test_green_onion_rejects_salad_kit_noise(self):
        r = calculate_line(display="green onion", item="green onion")
        top = [p.description.lower() for p in r.products[:10]]
        self.assertGreater(len(top), 0)
        self.assertIn("shopping_lab_overlay", " ".join(r.path))
        banned = ("salad kit", "cabbage", "romaine", "cilantro", "wonton", "lettuce", "broccoli", "ranch")
        self.assertTrue(all(not any(term in desc for term in banned) for desc in top))
        self.assertTrue(any("green onion" in desc or "green onions" in desc for desc in top))

    def test_mushroom_uses_fresh_white_mushroom_backing(self):
        lab = calculate_lab(display="mushroom", item="mushroom")
        self.assertEqual(lab.esha_code, "7351")
        self.assertGreater(len(lab.products), 0)
        top = [p.description.lower() for p in lab.products[:10]]
        banned = ("enoki", "beech", "gourmet", "soup", "gravy", "pizza", "risotto", "truffle")
        self.assertTrue(all(not any(term in desc for term in banned) for desc in top))
        self.assertTrue(any("mushroom" in desc for desc in top))

    def test_egg_yolk_shops_as_egg_not_fake_yolk_products(self):
        r = calculate_line(display="egg yolk", item="egg yolk")
        self.assertEqual(r.shopping_canonical, "egg")
        self.assertGreater(len(r.products), 0)
        self.assertIn("shopping_lab_overlay", " ".join(r.path))
        top = [p.description.lower() for p in r.products[:10]]
        banned = ("runny yolk", "egg whites", "egg beaters", "liquid egg", "real egg product")
        self.assertTrue(all(not any(term in desc for term in banned) for desc in top))
        self.assertTrue(all("runny yolk" not in desc for desc in top))
        self.assertTrue(any("egg" in desc for desc in top))

    def test_seedless_grapes_shops_as_fresh_seedless_grapes(self):
        r = calculate_line(display="seedless grapes", item="seedless grapes")
        self.assertEqual(r.shopping_canonical, "seedless grapes")
        self.assertGreater(len(r.products), 0)
        self.assertIn("shopping_lab_overlay", " ".join(r.path))
        top = [p.description.lower() for p in r.products[:10]]
        banned = ("juice", "candy", "dip", "smoothie", "yogurt", "frozen")
        self.assertTrue(all(not any(term in desc for term in banned) for desc in top))
        self.assertTrue(all("grape" in desc for desc in top))

    def test_lemon_zest_shops_as_fresh_lemons(self):
        r = calculate_line(display="lemon zest", item="lemon zest")
        self.assertEqual(r.shopping_canonical, "fresh lemons")
        self.assertGreater(len(r.products), 0)
        self.assertIn("shopping_lab_overlay", " ".join(r.path))
        top = [p.description.lower() for p in r.products[:10]]
        banned = ("water", "soda", "jam", "jelly", "preserved", "paste")
        self.assertTrue(all(not any(term in desc for term in banned) for desc in top))
        self.assertTrue(any("lemon" in desc for desc in top))

    def test_crushed_tomatoes_shop_as_crushed_tomatoes(self):
        r = calculate_line(display="crushed tomatoes", item="crushed tomatoes")
        self.assertEqual(r.shopping_canonical, "crushed tomatoes")
        self.assertGreater(len(r.products), 0)
        self.assertIn("shopping_lab_overlay", " ".join(r.path))
        top = [p.description.lower() for p in r.products[:10]]
        banned = ("sauce", "soup", "vodka", "ketchup")
        self.assertTrue(all(not any(term in desc for term in banned) for desc in top))
        self.assertTrue(any("crushed" in desc and "tomato" in desc for desc in top))

    def test_cardamom_pods_use_whole_spice_rows(self):
        r = calculate_line(display="cardamom pods", item="cardamom pods")
        self.assertGreater(len(r.products), 0)
        self.assertIn("shopping_lab_overlay", " ".join(r.path))
        top = [p.description.lower() for p in r.products[:10]]
        banned = ("cookie", "chocolate", "coffee", "gelato", "granola", "jam", "marmalade", "mustard", "pasta", "tea", "yogurt")
        self.assertTrue(all(not any(term in desc for term in banned) for desc in top))
        self.assertTrue(any("cardamom" in desc for desc in top))

    def test_saffron_threads_use_spice_rows(self):
        r = calculate_line(display="saffron threads", item="saffron threads")
        self.assertGreater(len(r.products), 0)
        self.assertIn("shopping_lab_overlay", " ".join(r.path))
        top = [p.description.lower() for p in r.products[:10]]
        banned = ("chip", "oil", "rice", "risotto", "salt", "syrup")
        self.assertTrue(all(not any(term in desc for term in banned) for desc in top))
        self.assertTrue(any("saffron" in desc for desc in top))

    def test_ground_clove_uses_ground_spice_rows(self):
        r = calculate_line(display="ground clove", item="ground clove")
        self.assertGreater(len(r.products), 0)
        self.assertIn("shopping_lab_overlay", " ".join(r.path))
        top = [p.description.lower() for p in r.products[:10]]
        banned = ("candy", "drink", "gum", "oil", "sauce", "soap", "tea", "toothpaste")
        self.assertTrue(all(not any(term in desc for term in banned) for desc in top))
        self.assertTrue(any("clove" in desc for desc in top))

    def test_snow_peas_use_fresh_produce_rows(self):
        r = calculate_line(display="snow peas", item="snow peas")
        self.assertGreater(len(r.products), 0)
        self.assertIn("shopping_lab_overlay", " ".join(r.path))
        top = [p.description.lower() for p in r.products[:10]]
        banned = ("blend", "broccoli", "carrot", "frozen", "noodle", "rice", "salad", "sauce", "stir", "teriyaki")
        self.assertTrue(all(not any(term in desc for term in banned) for desc in top))
        self.assertTrue(any("snow peas" in desc or "snow pea" in desc for desc in top))

    def test_gingersnap_crumbs_shop_as_gingersnap_cookies(self):
        r = calculate_line(display="gingersnap crumbs", item="gingersnap crumbs")
        self.assertEqual(r.shopping_canonical, "gingersnap cookies")
        self.assertGreater(len(r.products), 0)
        self.assertIn("shopping_lab_overlay", " ".join(r.path))
        top = [p.description.lower() for p in r.products[:10]]
        banned = ("latte", "milk chocolate", "nutrition bar", "trail mix", "waffle")
        self.assertTrue(all(not any(term in desc for term in banned) for desc in top))
        self.assertTrue(any("gingersnap" in desc for desc in top))

    def test_oreo_cookie_pie_crust_uses_cookie_pie_crust_overlay(self):
        r = calculate_line(display="oreo cookie pie crust", item="oreo cookie pie crust")
        self.assertEqual(r.shopping_canonical, "cookie pie crust")
        self.assertIn("shopping_lab_overlay", " ".join(r.path))
        self.assertGreater(len(r.products), 0)
        top = [p.description.lower() for p in r.products[:10]]
        banned = ("candy", "melon", "sour punch", "jelly belly", "tootsie")
        self.assertTrue(all(not any(term in desc for term in banned) for desc in top))
        self.assertTrue(any("pie crust" in desc for desc in top))

    def test_dry_white_vermouth_no_longer_routes_to_flour(self):
        lab = calculate_lab(display="dry white vermouth", item="dry white vermouth")
        self.assertEqual(lab.canonical_name, "dry vermouth")
        self.assertNotEqual(lab.shopping_canonical, "all purpose flour")

    def test_fat_free_parmesan_no_longer_uses_regex_backreference_poison(self):
        lab = calculate_lab(display="fat free parmesan", item="fat free parmesan")
        self.assertEqual(lab.canonical_name, "fat free parmesan")
        self.assertEqual(lab.esha_code, "48320")
        self.assertNotEqual(lab.canonical_name, "\\1")

    def test_mayonnaise_accepts_plain_mayo_only(self):
        r = calculate_line(display="mayonnaise", item="mayonnaise")
        self.assertGreater(len(r.products), 0)
        self.assertIn("shopping_lab_overlay", " ".join(r.path))
        top = [p.description.lower() for p in r.products[:10]]
        banned = ("chipotle", "olive oil", "vegan", "pesto", "truffle", "light", "lite", "reduced fat", "fat free")
        self.assertTrue(all(not any(term in desc for term in banned) for desc in top))
        self.assertTrue(all("mayonnaise" in desc for desc in top))

    def test_white_wine_uses_reviewed_lab_products(self):
        r = calculate_line(display="white wine", item="white wine")
        self.assertGreater(len(r.products), 0)
        self.assertIn("shopping_lab_overlay", " ".join(r.path))
        top = [p.description.lower() for p in r.products[:10]]
        self.assertTrue(all("wine" in desc for desc in top))
        self.assertTrue(all("vinegar" not in desc for desc in top))

    def test_whole_ham_quantity_routes_to_whole_ham_shopping(self):
        r = calculate_line(display="4 to 6 lb ham", item="4 to 6 lb ham")
        self.assertEqual(r.shopping_canonical, "whole ham")
        self.assertGreater(len(r.products), 0)
        self.assertIn("shopping_lab_overlay", " ".join(r.path))
        top = [p.description.lower() for p in r.products[:5]]
        self.assertTrue(all("ham" in desc for desc in top))
        self.assertTrue(all("sliced" not in desc for desc in top))
        self.assertTrue(all("deli" not in desc for desc in top))

    def test_all_purpose_flour_uses_reviewed_pack_candidates(self):
        r = calculate_line(display="all purpose flour", item="all purpose flour")
        top = [p.description.lower() for p in r.products[:5]]
        self.assertGreater(len(top), 0)
        self.assertIn("shopping_lab_overlay", " ".join(r.path))
        self.assertTrue(all("flour" in desc for desc in top))
        self.assertTrue(all("all purpose" in desc or "all-purpose" in desc for desc in top))

    def test_fresh_parsley_stays_fresh_herb(self):
        r = calculate_line(display="fresh parsley", item="fresh parsley")
        top = [p.description.lower() for p in r.products[:5]]
        self.assertGreater(len(top), 0)
        self.assertIn("shopping_lab_overlay", " ".join(r.path))
        banned = ("flakes", "garlic", "puree", "potato")
        self.assertTrue(all(not any(term in desc for term in banned) for desc in top))
        self.assertTrue(any("parsley" in desc for desc in top))

    def test_fresh_mint_rejects_frozen_dessert_noise(self):
        r = calculate_line(display="fresh mint", item="fresh mint")
        top = [p.description.lower() for p in r.products[:10]]
        if top:
            banned = ("gelato", "ice cream", "frozen dessert", "mint chip")
            self.assertTrue(all(not any(term in desc for term in banned) for desc in top))

    def test_southern_comfort_uses_reviewed_overlay(self):
        r = calculate_line(display="southern comfort", item="southern comfort")
        self.assertIn("shopping_lab_overlay", " ".join(r.path))

    def test_performance_under_100ms(self):
        import time
        t0 = time.perf_counter()
        for _ in range(10):
            calculate_line(display="1 cup butter", item="butter")
        elapsed_ms = (time.perf_counter() - t0) * 1000 / 10
        self.assertLess(elapsed_ms, 100, f"avg calculate_line took {elapsed_ms:.1f}ms")


if __name__ == "__main__":
    unittest.main()
