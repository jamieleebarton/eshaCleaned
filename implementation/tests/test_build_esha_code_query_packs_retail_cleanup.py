from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
IMPLEMENTATION_ROOT = ROOT / "implementation"
if str(IMPLEMENTATION_ROOT) not in sys.path:
    sys.path.insert(0, str(IMPLEMENTATION_ROOT))

import build_esha_code_query_packs as packs


class RetailCleanupAttemptTests(unittest.TestCase):
    def test_retail_cleanup_primary_terms_drops_demoted_terms(self) -> None:
        original_cache = packs._QUERY_TERM_DROP_CANDIDATES_CACHE
        try:
            packs._QUERY_TERM_DROP_CANDIDATES_CACHE = {"151": {"aspartame", "wtr"}}
            profile = SimpleNamespace(code="151")
            cleaned = packs.retail_cleanup_primary_terms(profile, ("chocolate", "reduced", "calorie", "aspartame", "powder"))
            self.assertEqual(cleaned, ("chocolate", "reduced", "calorie", "powder"))
        finally:
            packs._QUERY_TERM_DROP_CANDIDATES_CACHE = original_cache

    def test_retail_claim_attempts_for_reduced_calorie_beverage(self) -> None:
        profile = SimpleNamespace(family="beverage", attrs=("dry",))
        attempts = dict(
            packs.retail_claim_attempts_for(
                profile,
                ("chocolate", "reduced", "calorie", "aspartame", "powder"),
            )
        )
        self.assertIn("retail_claim_free", attempts)
        self.assertIn("retail_chocolate_cocoa", attempts)
        self.assertIn("retail_hot_cocoa_sugar_free", attempts)
        self.assertIn("retail_chocolate_drink_sugar_free_mix", attempts)
        self.assertIn("retail_hot_cocoa_no_sugar_added_mix", attempts)
        self.assertIn("free", attempts["retail_claim_free"])
        self.assertIn("cocoa", attempts["retail_chocolate_cocoa"])
        self.assertNotIn("aspartame", attempts["retail_hot_cocoa_sugar_free"])

    def test_query_attempts_for_includes_retail_cleanup(self) -> None:
        original_cache = packs._QUERY_TERM_DROP_CANDIDATES_CACHE
        original_query_terms_for = packs.query_terms_for
        try:
            packs._QUERY_TERM_DROP_CANDIDATES_CACHE = {"151": {"aspartame"}}
            packs.query_terms_for = lambda profile: ("chocolate", "reduced", "calorie", "aspartame", "powder")  # type: ignore[assignment]
            profile = SimpleNamespace(code="151", family="beverage", attrs=("dry",), hard_terms=("chocolate",), fts_terms=(), tokens=())
            attempts = packs.query_attempts_for(profile)
            labels = [label for label, _terms in attempts]
            by_label = {label: terms for label, terms in attempts}
            self.assertIn("retail_cleanup", labels)
            self.assertEqual(by_label["retail_cleanup"], ("chocolate", "reduced", "calorie", "powder"))
            self.assertIn("retail_hot_cocoa_sugar_free", labels)
        finally:
            packs._QUERY_TERM_DROP_CANDIDATES_CACHE = original_cache
            packs.query_terms_for = original_query_terms_for  # type: ignore[assignment]

    def test_retail_claim_attempts_for_hot_cocoa_low_calorie(self) -> None:
        profile = SimpleNamespace(family="beverage", attrs=("dry",))
        attempts = dict(
            packs.retail_claim_attempts_for(
                profile,
                ("hot", "cocoa", "low", "calorie", "aspartame", "packet", "powder"),
            )
        )
        self.assertIn("retail_hot_cocoa_sugar_free_mix", attempts)
        self.assertIn("retail_hot_cocoa_no_sugar_added_mix", attempts)

    def test_query_terms_for_milk_promotes_evaporated_and_skim_attrs(self) -> None:
        profile = SimpleNamespace(
            code="10",
            family="milk",
            hard_terms=("milk",),
            tokens=("milk", "evaporated", "skim"),
            attrs=("skim", "evaporated", "canned"),
        )
        terms = packs.query_terms_for(profile)
        self.assertIn("milk", terms)
        self.assertIn("evaporated", terms)
        self.assertIn("skim", terms)
        self.assertIn("canned", terms)

    def test_query_terms_for_leaf_overrides_block_broadening(self) -> None:
        whole_milk = SimpleNamespace(
            code="1",
            family="milk",
            hard_terms=("milk",),
            tokens=("milk", "whole"),
            attrs=("whole_fat",),
        )
        self.assertEqual(packs.query_terms_for(whole_milk), ("whole", "milk"))

        reduced_milk = SimpleNamespace(
            code="2",
            family="milk",
            hard_terms=("milk",),
            tokens=("milk", "2"),
            attrs=("two_percent",),
        )
        self.assertEqual(packs.query_terms_for(reduced_milk), ("2", "milk"))

        lowfat_milk = SimpleNamespace(
            code="4",
            family="milk",
            hard_terms=("milk",),
            tokens=("milk", "1"),
            attrs=("one_percent",),
        )
        self.assertEqual(packs.query_terms_for(lowfat_milk), ("1", "milk"))

        low_sodium = SimpleNamespace(
            code="52",
            family="milk",
            hard_terms=("milk",),
            tokens=("milk",),
            attrs=("low_sodium",),
        )
        self.assertEqual(packs.query_terms_for(low_sodium), ("low", "sodium", "milk"))

        skim_dry = SimpleNamespace(
            code="67",
            family="milk",
            hard_terms=("milk", "mix"),
            tokens=("milk", "skim"),
            attrs=("skim", "dry"),
        )
        self.assertEqual(packs.query_terms_for(skim_dry), ("skim", "milk", "powder"))

        baby_green_bean = SimpleNamespace(
            code="436",
            family="vegetable",
            hard_terms=("infant", "vegetable", "green", "bean"),
            tokens=("infant", "vegetable", "green", "bean", "potato"),
            attrs=(),
        )
        self.assertEqual(packs.query_terms_for(baby_green_bean), ("baby", "green", "bean", "potato"))

        parmesan = SimpleNamespace(
            code="1075",
            family="cheese",
            hard_terms=("cheese", "parmesan"),
            tokens=("cheese", "parmesan", "grated"),
            attrs=(),
        )
        self.assertEqual(packs.query_terms_for(parmesan), ("parmesan", "grated", "cheese"))

        cheddar_sauce = SimpleNamespace(
            code="9558",
            family="cheese",
            hard_terms=("sauce", "cheese", "cheddar"),
            tokens=("sauce", "cheese", "cheddar", "ready", "serve"),
            attrs=(),
        )
        self.assertEqual(packs.query_terms_for(cheddar_sauce), ("cheddar", "cheese", "sauce"))

        wild_rice_pancake = SimpleNamespace(
            code="16693",
            family="grain",
            hard_terms=("pancake", "wild", "rice", "mix"),
            tokens=("pancake", "wild", "rice", "mix"),
            attrs=("dry",),
        )
        self.assertEqual(packs.query_terms_for(wild_rice_pancake), ("pancake", "wild", "rice", "mix"))

        ten_grain_waffle = SimpleNamespace(
            code="16695",
            family="grain",
            hard_terms=("waffle", "grain", "mix"),
            tokens=("waffle", "grain", "mix", "10"),
            attrs=("dry",),
        )
        self.assertEqual(packs.query_terms_for(ten_grain_waffle), ("pancake", "waffle", "grain", "mix"))

        frozen_pancake = SimpleNamespace(
            code="16642",
            family="prepared_food",
            hard_terms=("pancake", "original"),
            tokens=("pancake", "original", "frozen"),
            attrs=("frozen",),
        )
        self.assertEqual(packs.query_terms_for(frozen_pancake), ("frozen", "pancake"))

        buttermilk_pancake = SimpleNamespace(
            code="16643",
            family="milk",
            hard_terms=("milk", "pancake", "buttermilk"),
            tokens=("pancake", "buttermilk", "frozen"),
            attrs=("frozen",),
        )
        self.assertEqual(packs.query_terms_for(buttermilk_pancake), ("frozen", "pancake", "buttermilk"))

        blueberry_pancake = SimpleNamespace(
            code="16646",
            family="fruit",
            hard_terms=("pancake", "blueberry"),
            tokens=("pancake", "blueberry", "frozen"),
            attrs=("frozen",),
        )
        self.assertEqual(packs.query_terms_for(blueberry_pancake), ("frozen", "pancake", "blueberry"))

        spark_water = SimpleNamespace(
            code="37282",
            family="beverage",
            hard_terms=("drink", "flavored", "water", "spark"),
            tokens=("drink", "flavored", "water", "spark"),
            attrs=(),
        )
        self.assertEqual(packs.query_terms_for(spark_water), ("sparkling", "water"))

        applesauce_original = SimpleNamespace(
            code="46801",
            family="fruit",
            hard_terms=("applesauce", "original"),
            tokens=("applesauce", "original"),
            attrs=(),
        )
        self.assertEqual(packs.query_terms_for(applesauce_original), ("applesauce",))

        applesauce_cinnamon = SimpleNamespace(
            code="46799",
            family="fruit",
            hard_terms=("applesauce", "cinnamon"),
            tokens=("applesauce", "cinnamon"),
            attrs=(),
        )
        self.assertEqual(packs.query_terms_for(applesauce_cinnamon), ("applesauce", "cinnamon"))

        original_tempeh = SimpleNamespace(
            code="91243",
            family="legume",
            hard_terms=("tempeh", "original"),
            tokens=("tempeh", "original"),
            attrs=(),
        )
        self.assertEqual(packs.query_terms_for(original_tempeh), ("tempeh",))

        blueberry_waffle = SimpleNamespace(
            code="52742",
            family="fruit",
            hard_terms=("waffle", "blueberry"),
            tokens=("waffle", "blueberry", "frozen"),
            attrs=(),
        )
        self.assertEqual(packs.query_terms_for(blueberry_waffle), ("frozen", "waffle", "blueberry"))

    def test_diagnostic_rescue_attempts_keep_protected_leaf_terms(self) -> None:
        carob = SimpleNamespace(
            code="43",
            family="beverage",
            hard_terms=("carob", "mix"),
            tokens=("carob", "mix", "powder"),
            attrs=("dry",),
        )
        carob_attempts = [label for label, _ in packs.diagnostic_rescue_attempts_for(carob)]
        self.assertNotIn("drop_one_core_term:carob", carob_attempts)

        vanilla_drink = SimpleNamespace(
            code="618",
            family="beverage",
            hard_terms=("vanilla", "drink"),
            tokens=("vanilla", "drink"),
            attrs=(),
        )
        vanilla_attempts = [label for label, _ in packs.diagnostic_rescue_attempts_for(vanilla_drink)]
        self.assertNotIn("drop_one_core_term:vanilla", vanilla_attempts)
        self.assertNotIn("drop_one_core_term:drink", vanilla_attempts)

        tempeh = SimpleNamespace(
            code="16514",
            family="legume",
            hard_terms=("tempeh", "spicy"),
            tokens=("tempeh", "spicy", "veggie"),
            attrs=(),
        )
        tempeh_attempts = [label for label, _ in packs.diagnostic_rescue_attempts_for(tempeh)]
        self.assertNotIn("drop_one_core_term:tempeh", tempeh_attempts)

        jerky = SimpleNamespace(
            code="16515",
            family="meat",
            hard_terms=("vegetarian", "jerky", "original"),
            tokens=("vegetarian", "jerky", "original"),
            attrs=(),
        )
        jerky_attempts = [label for label, _ in packs.diagnostic_rescue_attempts_for(jerky)]
        self.assertNotIn("drop_one_core_term:jerky", jerky_attempts)

    def test_retail_claim_attempts_for_milk_family_aliases(self) -> None:
        profile = SimpleNamespace(family="milk", attrs=("skim",))
        evaporated = dict(packs.retail_claim_attempts_for(profile, ("milk", "evaporated", "skim", "canned")))
        self.assertIn("retail_evaporated_milk", evaporated)
        self.assertIn("retail_evaporated_skim_milk", evaporated)

        condensed = dict(packs.retail_claim_attempts_for(profile, ("milk", "sweetened", "condensed", "canned")))
        self.assertIn("retail_condensed_milk", condensed)
        self.assertIn("retail_sweetened_condensed_milk", condensed)

        eggnog = dict(packs.retail_claim_attempts_for(profile, ("milk", "eggnog")))
        self.assertEqual(eggnog["retail_eggnog"], ("eggnog",))

        malted = dict(packs.retail_claim_attempts_for(profile, ("malted", "milk", "chocolate", "powder")))
        self.assertIn("retail_malted_milk", malted)
        self.assertIn("retail_malted_milk_mix", malted)
        self.assertIn("retail_chocolate_malted_milk", malted)

        cheddar_sauce = dict(packs.retail_claim_attempts_for(SimpleNamespace(family="cheese", attrs=()), ("sauce", "cheese", "cheddar", "ready", "serve")))
        self.assertIn("retail_cheddar_cheese_sauce", cheddar_sauce)
        self.assertEqual(cheddar_sauce["retail_cheddar_cheese_sauce"], ("cheddar", "cheese", "sauce"))

        jerky_profile = SimpleNamespace(code="16515", family="meat", attrs=())
        jerky_attempts = dict(packs.retail_claim_attempts_for(jerky_profile, ("vegetarian", "jerky", "original")))
        self.assertIn("retail_vegetarian_jerky", jerky_attempts)
        self.assertIn("retail_vegan_jerky", jerky_attempts)
        self.assertIn("retail_original_vegan_jerky", jerky_attempts)

        tempeh_profile = SimpleNamespace(code="16514", family="legume", attrs=())
        tempeh_attempts = dict(packs.retail_claim_attempts_for(tempeh_profile, ("tempeh", "spicy", "veggie")))
        self.assertIn("retail_tempeh", tempeh_attempts)
        self.assertIn("retail_spicy_tempeh", tempeh_attempts)

    def test_recommended_category_terms_for_malted_milk(self) -> None:
        profile = SimpleNamespace(family="milk", attrs=("dry",))
        category_terms = packs.recommended_category_terms_for(profile, ("malted", "milk", "powder"))
        self.assertEqual(category_terms, ("powdered", "not ready to drink"))

    def test_category_terms_for_leaf_overrides(self) -> None:
        self.assertEqual(packs.category_terms_for_profile(SimpleNamespace(code="1")), ("=Milk",))
        self.assertEqual(packs.category_terms_for_profile(SimpleNamespace(code="12470")), ("=Frozen Pancakes, Waffles, French Toast & Crepes",))
        self.assertEqual(packs.category_terms_for_profile(SimpleNamespace(code="16642")), ("=Frozen Pancakes, Waffles, French Toast & Crepes",))
        self.assertEqual(packs.category_terms_for_profile(SimpleNamespace(code="16643")), ("=Frozen Pancakes, Waffles, French Toast & Crepes",))
        self.assertEqual(packs.category_terms_for_profile(SimpleNamespace(code="16646")), ("=Frozen Pancakes, Waffles, French Toast & Crepes",))
        self.assertEqual(packs.category_terms_for_profile(SimpleNamespace(code="37282")), ("=Water",))
        self.assertEqual(packs.category_terms_for_profile(SimpleNamespace(code="52742")), ("=Frozen Pancakes, Waffles, French Toast & Crepes",))
        self.assertEqual(packs.category_terms_for_profile(SimpleNamespace(code="91243")), ("=Other Meats",))
        self.assertEqual(
            packs.category_terms_for_profile(SimpleNamespace(code="46801")),
            ("fruit", "produce", "pre-packaged", "canned fruit", "baby"),
        )
        self.assertEqual(packs.category_terms_for_profile(SimpleNamespace(code="436")), ("baby", "infant"))
        self.assertEqual(
            packs.category_terms_for_profile(SimpleNamespace(code="615")),
            ("plant based milk", "other drinks", "milk additives", "powdered drinks"),
        )
        self.assertEqual(packs.category_terms_for_profile(SimpleNamespace(code="9558")), ("sauce", "condiment", "dip"))
        self.assertEqual(packs.category_terms_for_profile(SimpleNamespace(code="1075")), ("cheese",))

    def test_category_sql_filter_supports_exact_category_terms(self) -> None:
        clause, params = packs.category_sql_filter("p", ("=Milk", "water"))
        self.assertIn(" IN (?", clause)
        self.assertIn("LIKE ?", clause)
        self.assertEqual(params, ["milk", "%water%"])

    def test_product_noise_flags_eggnog_yogurt_variant(self) -> None:
        noise = packs.product_noise(
            "EGGNOG FLAVORED BLENDED LOWFAT YOGURT, EGGNOG",
            "Yogurt",
            "milk",
            {"eggnog"},
            "Cultured lowfat milk, sugar, eggnog flavor.",
        )
        self.assertIn("yogurt", noise)

    def test_product_noise_ignores_plain_eggnog_cream_flavor_language(self) -> None:
        noise = packs.product_noise(
            "EGGNOG",
            "Milk",
            "milk",
            {"eggnog"},
            "Milk, cream, sugar, natural flavor.",
        )
        self.assertNotIn("cream", noise)
        self.assertNotIn("flavor", noise)

    def test_semantic_filter_terms_for_evaporated_milk_drops_canned(self) -> None:
        profile = SimpleNamespace(
            code="10",
            family="milk",
            hard_terms=("milk",),
            tokens=("milk", "evaporated", "skim"),
            attrs=("skim", "evaporated", "canned"),
        )
        filters = packs.semantic_filter_terms_for(profile, packs.query_terms_for(profile))
        self.assertNotIn("canned", filters)

    def test_term_variants_cover_mac_and_fettuccine_aliases(self) -> None:
        self.assertIn("mac", packs.term_variants("macaroni"))
        self.assertIn("macaroni", packs.term_variants("mac"))
        self.assertIn("fettuccine", packs.term_variants("fettuccini"))
        self.assertIn("froyo", packs.term_variants("yogurt"))

    def test_has_prepared_food_context_detects_combo_cues(self) -> None:
        self.assertTrue(packs.has_prepared_food_context({"pot", "pie"}))
        self.assertTrue(packs.has_prepared_food_context({"macaroni", "cheese"}))
        self.assertTrue(packs.has_prepared_food_context({"salisbury", "steak"}))

    def test_category_signal_accepts_prepared_food_categories_for_prepared_context(self) -> None:
        signal = packs.category_signal(
            "Frozen Dinners & Entrees",
            "cheese",
            {"macaroni", "cheese", "frozen"},
            "Macaroni & Cheese, frozen",
        )
        self.assertEqual(signal, "in_scope_category")

    def test_retail_claim_attempts_for_frozen_prepared_food_leaves(self) -> None:
        profile = SimpleNamespace(family="cheese", attrs=("frozen",))
        attempts = dict(packs.retail_claim_attempts_for(profile, ("macaroni", "cheese", "frozen")))
        self.assertIn("retail_mac_and_cheese", attempts)

        lasagna_attempts = dict(packs.retail_claim_attempts_for(profile, ("lasagna", "cheese", "frozen")))
        self.assertIn("retail_lasagna", lasagna_attempts)
        self.assertIn("retail_lasagna_cheese", lasagna_attempts)

        poultry_profile = SimpleNamespace(family="poultry", attrs=("frozen",))
        alfredo_attempts = dict(packs.retail_claim_attempts_for(poultry_profile, ("pasta", "fettuccini", "alfredo", "chicken", "frozen")))
        self.assertIn("retail_fettuccine_alfredo", alfredo_attempts)
        self.assertIn("retail_chicken_alfredo", alfredo_attempts)

        meat_profile = SimpleNamespace(family="meat", attrs=("frozen",))
        pot_pie_attempts = dict(packs.retail_claim_attempts_for(meat_profile, ("pot", "pie", "beef", "frozen")))
        self.assertIn("retail_pot_pie", pot_pie_attempts)
        self.assertIn("retail_pot_pie_beef", pot_pie_attempts)

    def test_retail_claim_attempts_for_frozen_desserts(self) -> None:
        dessert_profile = SimpleNamespace(family="dessert_snack", attrs=())
        attempts = dict(packs.retail_claim_attempts_for(dessert_profile, ("ice", "cream", "bar", "coffee", "almond", "crunch")))
        self.assertNotIn("retail_ice_cream", attempts)
        self.assertIn("retail_ice_cream_bar", attempts)
        generic_attempts = dict(packs.retail_claim_attempts_for(dessert_profile, ("ice", "cream", "vanilla")))
        self.assertIn("retail_ice_cream", generic_attempts)

        yogurt_profile = SimpleNamespace(family="yogurt", attrs=("frozen",))
        froyo_attempts = dict(packs.retail_claim_attempts_for(yogurt_profile, ("yogurt", "sandwich", "frozen")))
        self.assertNotIn("retail_frozen_yogurt", froyo_attempts)
        self.assertNotIn("retail_froyo", froyo_attempts)
        self.assertIn("retail_frozen_yogurt_sandwich", froyo_attempts)
        self.assertIn("retail_froyo_sandwich", froyo_attempts)
        generic_froyo_attempts = dict(packs.retail_claim_attempts_for(yogurt_profile, ("yogurt", "vanilla", "frozen")))
        self.assertIn("retail_frozen_yogurt", generic_froyo_attempts)
        self.assertIn("retail_froyo", generic_froyo_attempts)

    def test_retail_claim_attempts_for_frozen_appetizer_leaves(self) -> None:
        poultry_profile = SimpleNamespace(family="poultry", attrs=("frozen",))
        taquito_attempts = dict(packs.retail_claim_attempts_for(poultry_profile, ("taquito", "chicken", "frozen")))
        self.assertIn("retail_taquito", taquito_attempts)
        self.assertIn("retail_taquito_chicken", taquito_attempts)

        cheese_profile = SimpleNamespace(family="cheese", attrs=("frozen",))
        quiche_attempts = dict(packs.retail_claim_attempts_for(cheese_profile, ("quiche", "florentine", "swiss", "spinach", "frozen")))
        self.assertIn("retail_quiche", quiche_attempts)
        self.assertIn("retail_quiche_florentine", quiche_attempts)

        corn_dog_attempts = dict(packs.retail_claim_attempts_for(poultry_profile, ("corn", "dog", "turkey", "popcorn", "frozen")))
        self.assertIn("retail_corn_dog", corn_dog_attempts)
        self.assertIn("retail_corn_dog_turkey", corn_dog_attempts)
        self.assertIn("retail_popcorn_corn_dog", corn_dog_attempts)

    def test_retail_claim_attempts_for_uncategorized_top_buckets(self) -> None:
        prepared_profile = SimpleNamespace(family="prepared_food", attrs=())
        pizza_attempts = dict(packs.retail_claim_attempts_for(prepared_profile, ("pizza", "original", "crust", "cowboy", "family")))
        self.assertIn("retail_pizza", pizza_attempts)
        self.assertIn("retail_pizza_original_crust", pizza_attempts)

        fries_attempts = dict(packs.retail_claim_attempts_for(prepared_profile, ("french", "fry", "crinkle", "cut", "frozen")))
        self.assertIn("retail_french_fries", fries_attempts)
        self.assertIn("retail_crinkle_cut_fries", fries_attempts)

        beverage_profile = SimpleNamespace(family="beverage", attrs=())
        frappuccino_attempts = dict(packs.retail_claim_attempts_for(beverage_profile, ("coffee", "blended", "frappuccino", "mocha", "whole", "milk", "tall")))
        self.assertIn("retail_frappuccino", frappuccino_attempts)
        self.assertIn("retail_coffee_frappuccino", frappuccino_attempts)
        self.assertIn("retail_mocha_frappuccino", frappuccino_attempts)

        latte_attempts = dict(packs.retail_claim_attempts_for(beverage_profile, ("coffee", "latte", "iced", "skim", "milk", "junior")))
        self.assertIn("retail_latte", latte_attempts)
        self.assertIn("retail_latte_coffee", latte_attempts)

        cocoa_attempts = dict(packs.retail_claim_attempts_for(beverage_profile, ("hot", "cocoa", "white", "chocolate", "skim", "milk", "small")))
        self.assertIn("retail_hot_cocoa", cocoa_attempts)
        self.assertIn("retail_white_hot_cocoa", cocoa_attempts)

        dessert_profile = SimpleNamespace(family="dessert_snack", attrs=())
        creme_frap_attempts = dict(packs.retail_claim_attempts_for(dessert_profile, ("creme", "blended", "frappuccino", "white", "chocolate", "whole", "tall")))
        self.assertIn("retail_creme_frappuccino", creme_frap_attempts)
        self.assertIn("retail_white_frappuccino", creme_frap_attempts)

        cake_attempts = dict(packs.retail_claim_attempts_for(dessert_profile, ("cake", "ice", "cream", "blizzard", "chocolate")))
        self.assertIn("retail_ice_cream_cake", cake_attempts)
        self.assertIn("retail_blizzard_cake", cake_attempts)

        oreo_attempts = dict(packs.retail_claim_attempts_for(dessert_profile, ("cookie", "sandwich", "oreo", "chocolate", "double", "stuf")))
        self.assertIn("retail_oreo_cookie_sandwich", oreo_attempts)
        self.assertIn("retail_oreo_cookie", oreo_attempts)

        candy_bar_attempts = dict(packs.retail_claim_attempts_for(dessert_profile, ("candy", "bar", "milky", "way", "mini")))
        self.assertIn("retail_milky_way_bar", candy_bar_attempts)

        fruit_profile = SimpleNamespace(family="fruit", attrs=("frozen",))
        infant_attempts = dict(packs.retail_claim_attempts_for(fruit_profile, ("infant", "fruit", "banana", "stage")))
        self.assertIn("retail_baby_food", infant_attempts)
        self.assertIn("retail_baby_food_banana", infant_attempts)
        fruit_twist_attempts = dict(packs.retail_claim_attempts_for(fruit_profile, ("fruit", "twists", "strawberry")))
        self.assertIn("retail_fruit_twists", fruit_twist_attempts)
        fruit_foot_attempts = dict(packs.retail_claim_attempts_for(fruit_profile, ("fruit", "foot", "strawberry")))
        self.assertIn("retail_fruit_by_the_foot", fruit_foot_attempts)
        frozen_lemonade_attempts = dict(packs.retail_claim_attempts_for(fruit_profile, ("lemonade", "frozen", "pink")))
        self.assertIn("retail_frozen_lemonade_concentrate", frozen_lemonade_attempts)
        self.assertIn("retail_frozen_pink_lemonade_concentrate", frozen_lemonade_attempts)

        spice_profile = SimpleNamespace(family="spice", attrs=("dry",))
        oatmeal_attempts = dict(packs.retail_claim_attempts_for(spice_profile, ("cereal", "hot", "oatmeal", "apple", "cinnamon", "instant")))
        self.assertIn("retail_oatmeal", oatmeal_attempts)
        self.assertIn("retail_instant_oatmeal", oatmeal_attempts)
        self.assertIn("retail_apple_cinnamon_oatmeal", oatmeal_attempts)
        graham_attempts = dict(packs.retail_claim_attempts_for(spice_profile, ("cracker", "graham", "cinnamon")))
        self.assertIn("retail_graham_crackers", graham_attempts)
        self.assertIn("retail_cinnamon_graham_crackers", graham_attempts)
        wafer_attempts = dict(packs.retail_claim_attempts_for(spice_profile, ("cookie", "vanilla", "wafer")))
        self.assertIn("retail_vanilla_wafer", wafer_attempts)
        formula_attempts = dict(packs.retail_claim_attempts_for(spice_profile, ("formula", "pediasure", "vanilla")))
        self.assertIn("retail_pediasure", formula_attempts)
        self.assertIn("retail_pediasure_vanilla", formula_attempts)

        condiment_profile = SimpleNamespace(family="condiment", attrs=())
        dressing_attempts = dict(packs.retail_claim_attempts_for(condiment_profile, ("salad", "dressing", "italian", "light")))
        self.assertIn("retail_salad_dressing", dressing_attempts)
        self.assertIn("retail_salad_dressing_italian", dressing_attempts)
        miracle_attempts = dict(packs.retail_claim_attempts_for(condiment_profile, ("miracle", "whip", "light")))
        self.assertIn("retail_miracle_whip", miracle_attempts)
        pickle_attempts = dict(packs.retail_claim_attempts_for(condiment_profile, ("pickle", "bread", "butter")))
        self.assertIn("retail_bread_and_butter_pickles", pickle_attempts)

        sandwich_profile = SimpleNamespace(family="cheese", attrs=())
        sandwich_attempts = dict(packs.retail_claim_attempts_for(sandwich_profile, ("sandwich", "roast", "beef", "cheese")))
        self.assertIn("retail_sandwich", sandwich_attempts)
        self.assertIn("retail_sandwich_beef", sandwich_attempts)
        wrap_attempts = dict(packs.retail_claim_attempts_for(sandwich_profile, ("wrap", "cheese", "steak", "chicken")))
        self.assertIn("retail_wrap", wrap_attempts)
        self.assertIn("retail_cheese_steak", wrap_attempts)
        self.assertIn("retail_cheese_steak_wrap", wrap_attempts)

        grain_profile = SimpleNamespace(family="grain", attrs=())
        bagel_attempts = dict(packs.retail_claim_attempts_for(grain_profile, ("bagel", "sesame")))
        self.assertIn("retail_bagel", bagel_attempts)
        self.assertIn("retail_bagel_sesame", bagel_attempts)
        cracker_attempts = dict(packs.retail_claim_attempts_for(grain_profile, ("cracker", "saltine", "unsalted", "tops")))
        self.assertIn("retail_saltine_crackers", cracker_attempts)
        self.assertIn("retail_unsalted_tops_saltines", cracker_attempts)
        helper_attempts = dict(packs.retail_claim_attempts_for(grain_profile, ("hamburger", "helper", "cheeseburger", "macaroni")))
        self.assertIn("retail_hamburger_helper", helper_attempts)

        soup_profile = SimpleNamespace(family="soup", attrs=("canned",))
        pepper_attempts = dict(packs.retail_claim_attempts_for(soup_profile, ("chili", "pepper", "jalapeno", "canned")))
        self.assertIn("retail_jalapeno_peppers", pepper_attempts)
        soup_attempts = dict(packs.retail_claim_attempts_for(soup_profile, ("soup", "chicken", "noodle", "canned")))
        self.assertIn("retail_chicken_noodle_soup", soup_attempts)

        milk_profile = SimpleNamespace(family="milk", attrs=())
        buttermilk_attempts = dict(packs.retail_claim_attempts_for(milk_profile, ("buttermilk", "pancake", "mix")))
        self.assertIn("retail_buttermilk", buttermilk_attempts)
        self.assertIn("retail_buttermilk_pancake_mix", buttermilk_attempts)

        cream_profile = SimpleNamespace(family="cream", attrs=("canned",))
        cream_soup_attempts = dict(packs.retail_claim_attempts_for(cream_profile, ("soup", "cream", "mushroom", "canned")))
        self.assertIn("retail_cream_of_mushroom_soup", cream_soup_attempts)
        sour_cream_attempts = dict(packs.retail_claim_attempts_for(cream_profile, ("sour", "cream")))
        self.assertIn("retail_sour_cream", sour_cream_attempts)

    def test_category_signal_accepts_ice_cream_categories_for_ice_cream_context(self) -> None:
        signal = packs.category_signal(
            "Ice Cream & Frozen Yogurt",
            "dessert_snack",
            {"ice", "cream", "bar", "coffee"},
            "Ice Cream Bar, coffee",
        )
        self.assertEqual(signal, "in_scope_category")

    def test_category_signal_accepts_candy_categories_for_candy_context(self) -> None:
        signal = packs.category_signal(
            "Candy",
            "milk",
            {"candy", "peanut", "butter", "cup", "reese"},
            "Candy, peanut butter cups, Reese's, mini",
        )
        self.assertEqual(signal, "in_scope_category")

    def test_category_signal_accepts_frozen_appetizer_categories_for_prepared_context(self) -> None:
        signal = packs.category_signal(
            "Frozen Appetizers & Hors D'oeuvres",
            "poultry",
            {"taquito", "chicken", "frozen"},
            "Taquitos, chicken, frozen",
        )
        self.assertEqual(signal, "in_scope_category")

    def test_category_signal_accepts_uncategorized_leaf_categories(self) -> None:
        pizza_signal = packs.category_signal(
            "Pizza",
            "prepared_food",
            {"pizza", "original", "crust"},
            "Pizza, original crust, Cowboy, family",
        )
        self.assertEqual(pizza_signal, "in_scope_category")
        fries_signal = packs.category_signal(
            "French Fries, Potatoes & Onion Rings",
            "prepared_food",
            {"french", "fry", "crinkle", "cut", "frozen"},
            "French Fries, crinkle cut, frozen",
        )
        self.assertEqual(fries_signal, "in_scope_category")
        frappuccino_signal = packs.category_signal(
            "Other Drinks",
            "beverage",
            {"coffee", "blended", "frappuccino", "mocha"},
            "Coffee, blended, Frappuccino, mocha",
        )
        self.assertEqual(frappuccino_signal, "in_scope_category")
        baby_signal = packs.category_signal(
            "Baby/Infant  Foods/Beverages",
            "fruit",
            {"infant", "fruit", "banana"},
            "Infant Fruit, banana",
        )
        self.assertEqual(baby_signal, "in_scope_category")
        oatmeal_signal = packs.category_signal(
            "Cereal",
            "spice",
            {"oatmeal", "apple", "cinnamon", "instant"},
            "Instant Oatmeal, apple cinnamon",
        )
        self.assertEqual(oatmeal_signal, "in_scope_category")
        graham_signal = packs.category_signal(
            "Cookies & Biscuits",
            "spice",
            {"graham", "cracker", "cinnamon"},
            "Cinnamon Graham Crackers",
        )
        self.assertEqual(graham_signal, "in_scope_category")
        sandwich_signal = packs.category_signal(
            "Prepared Subs & Sandwiches",
            "cheese",
            {"sandwich", "roast", "beef", "cheese"},
            "Roast Beef Sandwich",
        )
        self.assertEqual(sandwich_signal, "in_scope_category")
        bagel_signal = packs.category_signal(
            "Breads & Buns",
            "grain",
            {"bagel", "sesame"},
            "Sesame Bagel",
        )
        self.assertEqual(bagel_signal, "in_scope_category")
        cracker_signal = packs.category_signal(
            "Crackers & Biscotti",
            "grain",
            {"cracker", "saltine", "unsalted", "tops"},
            "Unsalted Tops Saltine Crackers",
        )
        self.assertEqual(cracker_signal, "in_scope_category")
        soup_signal = packs.category_signal(
            "Prepared Soups",
            "cream",
            {"soup", "cream", "mushroom", "canned"},
            "Cream of Mushroom Soup",
        )
        self.assertEqual(soup_signal, "in_scope_category")

    def test_product_noise_ignores_milk_and_yogurt_for_ice_cream_context(self) -> None:
        noise = packs.product_noise(
            "COFFEE ALMOND TOFFEE CRUNCH ICE CREAM BAR",
            "Ice Cream & Frozen Yogurt",
            "dessert_snack",
            {"ice", "cream", "bar", "coffee", "almond", "crunch"},
            "Milk, cream, almonds",
        )
        self.assertNotIn("milk", noise)
        self.assertNotIn("yogurt", noise)

    def test_product_noise_ignores_candy_coating_terms_for_candy_context(self) -> None:
        noise = packs.product_noise(
            "REESE'S PEANUT BUTTER CUP MINI",
            "Candy",
            "nut_butter",
            {"candy", "peanut", "butter", "cup", "reese", "mini"},
            "Milk chocolate, peanut butter, soy lecithin",
        )
        self.assertNotIn("chocolate", noise)
        self.assertNotIn("milk", noise)
        self.assertNotIn("soy", noise)

    def test_product_noise_ignores_sauce_in_prepared_food_context(self) -> None:
        noise = packs.product_noise(
            "THREE CHEESE TAQUITOS",
            "Frozen Appetizers & Hors D'oeuvres",
            "cheese",
            {"taquito", "three", "cheese", "frozen"},
            "Cheese filling, sauce seasoning",
        )
        self.assertNotIn("sauce", noise)

    def test_term_variants_handle_fry_plural(self) -> None:
        variants = packs.term_variants("fry")
        self.assertIn("fries", variants)

    def test_product_noise_requires_explicit_yogurt_for_frozen_yogurt_context(self) -> None:
        missing = packs.product_noise(
            "ICE CREAM SANDWICH, VANILLA",
            "Ice Cream & Frozen Yogurt",
            "yogurt",
            {"yogurt", "sandwich", "frozen"},
            "Milk, cream, sugar",
        )
        self.assertIn("missing_yogurt", missing)
        good = packs.product_noise(
            "PHISH FOOD FROYO CHOCOLATE FROZEN YOGURT",
            "Ice Cream & Frozen Yogurt",
            "yogurt",
            {"yogurt", "phish", "frozen"},
            "Cultured skim milk",
        )
        self.assertNotIn("missing_yogurt", good)

    def test_classify_product_can_ignore_generated_contracts_for_planner(self) -> None:
        original_eval = packs.esha_contracts.evaluate_facts
        original_source = packs.esha_contracts.contract_source_module
        original_signal = packs.category_signal
        original_noise = packs.product_noise
        try:
            packs.esha_contracts.evaluate_facts = lambda code, facts: SimpleNamespace(status="reject", reason="category mismatch")  # type: ignore[assignment]
            packs.esha_contracts.contract_source_module = lambda code: "esha_contracts.reviewed_nebius_generated"  # type: ignore[assignment]
            packs.category_signal = lambda category, family, source_terms=None, description="": "in_scope_category"  # type: ignore[assignment]
            packs.product_noise = lambda description, category, family, source_terms, ingredients="": []  # type: ignore[assignment]
            profile = SimpleNamespace(code="461", family="prepared_food", tokens=("meal", "turkey"))
            product = {"description": "TURKEY MEAL", "category": "Frozen Dinners & Entrees", "ingredients": ""}
            self.assertEqual(
                packs.classify_product(profile, product, (), allow_generated_contracts=True),
                ("contract_reject", ["category_mismatch"]),
            )
            self.assertEqual(
                packs.classify_product(profile, product, (), allow_generated_contracts=False),
                ("in_scope_category", []),
            )
        finally:
            packs.esha_contracts.evaluate_facts = original_eval  # type: ignore[assignment]
            packs.esha_contracts.contract_source_module = original_source  # type: ignore[assignment]
            packs.category_signal = original_signal  # type: ignore[assignment]
            packs.product_noise = original_noise  # type: ignore[assignment]


if __name__ == "__main__":
    unittest.main()
