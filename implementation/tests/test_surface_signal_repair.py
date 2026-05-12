import csv
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "implementation"))

from run_surface_signal_repair import CANONICAL_CSV, repair_rows


def canonical_fieldnames() -> list[str]:
    with CANONICAL_CSV.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle).fieldnames or [])


FIELDNAMES = canonical_fieldnames()


def make_dirty_row(
    surface: str,
    *,
    nutrition_code: str,
    nutrition_code_type: str,
    nutrition_match_state: str,
    sr28_code: str = "",
    sr28_description: str = "",
    sr28_match_type: str = "",
    fndds_code: str = "",
    fndds_description: str = "",
    fndds_match_type: str = "",
    esha_code: str = "",
    esha_description: str = "",
    esha_match_type: str = "",
    proxy_code: str = "",
    proxy_description: str = "",
    proxy_reason: str = "",
    product_proxy_code: str = "",
    product_anchor_code: str = "",
    product_anchor_description: str = "",
    notes: str = "",
) -> dict[str, str]:
    row = {field: "" for field in FIELDNAMES}
    row["canonical_surface"] = surface
    row["canonical_normalized"] = surface
    row["canonical_shopping_item"] = surface
    row["decision_reason"] = "canonical shopping item"
    row["nutrition_code"] = nutrition_code
    row["nutrition_code_type"] = nutrition_code_type
    row["nutrition_match_state"] = nutrition_match_state
    row["sr28_code"] = sr28_code
    row["sr28_description"] = sr28_description
    row["sr28_match_type"] = sr28_match_type
    row["fndds_code"] = fndds_code
    row["fndds_description"] = fndds_description
    row["fndds_match_type"] = fndds_match_type
    row["esha_code"] = esha_code
    row["esha_description"] = esha_description
    row["esha_match_type"] = esha_match_type
    row["proxy_source"] = "sr28" if proxy_code else ""
    row["proxy_code"] = proxy_code
    row["proxy_description"] = proxy_description
    row["proxy_target"] = proxy_description
    row["proxy_reason"] = proxy_reason
    row["proxy_review_status"] = "needs_review" if proxy_code else ""
    row["product_proxy_match_state"] = "reference_proxy_candidate" if product_proxy_code else ""
    row["hestia_product_proxy_code"] = product_proxy_code
    row["product_proxy_review_status"] = "needs_review" if product_proxy_code else ""
    row["product_proxy_basis"] = "exact SR28/FNDDS backbone proxy target; Hestia proxy candidate, not a source-code promotion" if product_proxy_code else ""
    row["product_proxy_sr28_anchor_code"] = product_anchor_code
    row["product_proxy_sr28_anchor_description"] = product_anchor_description
    row["product_proxy_sr28_anchor_match_type"] = f"surface_signal_repair:code:{product_anchor_code}" if product_anchor_code else ""
    row["product_proxy_sr28_anchor_basis"] = "forced_family_floor" if product_anchor_code else ""
    row["notes"] = notes
    return row


def make_dirty_vanilla_bucket_row(surface: str) -> dict[str, str]:
    return make_dirty_row(
        surface,
        nutrition_code="SR28:167575",
        nutrition_code_type="sr28_reference_match",
        nutrition_match_state="sr28_match",
        sr28_code="167575",
        sr28_description="Ice creams, vanilla",
        sr28_match_type="sr28_terminal_proxy:code:167575",
        fndds_match_type="cleared_wrong_family:non_chocolate",
        esha_code="2004",
        esha_description="Ice Cream, vanilla",
        esha_match_type="esha_terminal_proxy:code:2004",
        proxy_code="167575",
        proxy_description="Ice creams, vanilla",
        proxy_reason="forced family floor; replaced wrong-family nutrition backbone",
        product_proxy_code=f"HXP-SR28-167575-{surface.upper().replace(' ', '-')}",
        product_anchor_code="167575",
        product_anchor_description="Ice creams, vanilla",
        notes="ice cream family; source_gap:fndds no safe FNDDS counterpart after exact/proxy backfill; SR28 backbone retained",
    )


class SurfaceSignalRepairIceCreamBucketTests(unittest.TestCase):
    def test_waffle_bowls_stop_using_vanilla_ice_cream(self):
        row = make_dirty_vanilla_bucket_row("ice cream waffle bowls")

        repair_rows([row])

        self.assertEqual("175000", row["sr28_code"])
        self.assertEqual("Ice cream cones, cake or wafer-type", row["sr28_description"])
        self.assertEqual("62443", row["esha_code"])
        self.assertEqual("Cone, ice cream, waffle bowl", row["esha_description"])
        self.assertEqual("", row["hestia_product_proxy_code"])

    def test_caramel_topping_moves_to_topping_family(self):
        row = make_dirty_vanilla_bucket_row("caramel ice cream topping")

        repair_rows([row])

        self.assertEqual("168841", row["sr28_code"])
        self.assertEqual("91304010", row["fndds_code"])
        self.assertEqual("23070", row["esha_code"])
        self.assertEqual("Topping, caramel", row["esha_description"])
        self.assertEqual("", row["proxy_code"])

    def test_frosty_stops_using_sprite_float(self):
        row = make_dirty_vanilla_bucket_row("frosty")
        row["esha_code"] = "31322"
        row["esha_description"] = "Ice Cream Float, Frosty, Sprite"
        row["esha_match_type"] = "phrase"

        repair_rows([row])

        self.assertEqual("2176", row["esha_code"])
        self.assertEqual("Frozen Dessert, Frosty", row["esha_description"])
        self.assertEqual("", row["sr28_code"])
        self.assertEqual("reviewed_nutrition_unknown", row["nutrition_match_state"])
        self.assertNotEqual("31322", row["esha_code"])

    def test_ice_cream_sticks_are_cleared_as_non_food(self):
        row = make_dirty_vanilla_bucket_row("ice cream sticks")

        repair_rows([row])

        self.assertEqual("", row["nutrition_code"])
        self.assertEqual("", row["sr28_code"])
        self.assertEqual("", row["esha_code"])
        self.assertEqual("reviewed_nutrition_unknown", row["nutrition_match_state"])
        self.assertEqual("non_food_accessory_manual_review", row["unmatched_reason"])

    def test_low_fat_vanilla_gets_light_vanilla_floor(self):
        row = make_dirty_vanilla_bucket_row("low-fat vanilla ice cream")

        repair_rows([row])

        self.assertEqual("167572", row["sr28_code"])
        self.assertEqual("13110100", row["fndds_code"])
        self.assertEqual("2009", row["esha_code"])
        self.assertEqual("Ice Cream, vanilla, light", row["esha_description"])

    def test_sugar_free_vanilla_gets_no_sugar_added_floor(self):
        row = make_dirty_vanilla_bucket_row("sugar-free vanilla ice cream")

        repair_rows([row])

        self.assertEqual("169631", row["sr28_code"])
        self.assertEqual("13110320", row["fndds_code"])
        self.assertEqual("52151", row["esha_code"])
        self.assertEqual("Ice Cream, vanilla, light, no sugar added", row["esha_description"])


class SurfaceSignalRepairFruitAndCrackerBucketTests(unittest.TestCase):
    def test_raspberry_syrup_stops_using_canned_raspberries(self):
        row = make_dirty_row(
            "raspberry syrup",
            nutrition_code="SR28:167756",
            nutrition_code_type="sr28_reference_match",
            nutrition_match_state="sr28_match",
            sr28_code="167756",
            sr28_description="Raspberries, canned, red, heavy syrup pack, solids and liquids",
            fndds_code="63219130",
            fndds_description="Raspberries, cooked or canned, in heavy syrup",
            esha_code="15605",
            esha_description="Syrup, raspberry",
            esha_match_type="exact",
            notes="syrup family; family floor preserved named identity",
        )

        repair_rows([row])

        self.assertEqual("169578", row["sr28_code"])
        self.assertEqual("Syrups, table blends, pancake", row["sr28_description"])
        self.assertEqual("15605", row["esha_code"])
        self.assertEqual("", row["fndds_code"])

    def test_tamarind_juice_gets_exact_tamarind_drink_chain(self):
        row = make_dirty_row(
            "tamarind juice",
            nutrition_code="HXP-SR28-167763-TAMARIND-JUICE",
            nutrition_code_type="hestia_reference_proxy_candidate",
            nutrition_match_state="reference_proxy_candidate",
            sr28_code="167763",
            sr28_description="Tamarinds, raw",
            esha_code="3984",
            esha_description="Juice, fruit fiesta",
            esha_match_type="esha_terminal_proxy:code:3984",
            proxy_code="167763",
            proxy_description="Tamarinds, raw",
            proxy_reason="tamarind proxy candidate; tamarind backbone",
            product_proxy_code="HXP-SR28-167763-TAMARIND-JUICE",
            product_anchor_code="167763",
            product_anchor_description="Tamarinds, raw",
            notes="juice family; family floor preserved named identity",
        )

        repair_rows([row])

        self.assertEqual("167786", row["sr28_code"])
        self.assertEqual("92510650", row["fndds_code"])
        self.assertEqual("21133", row["esha_code"])
        self.assertEqual("Juice Drink, tamarind nectar, canned", row["esha_description"])

    def test_watermelon_rind_is_cleared_not_mapped_to_orange_peel(self):
        row = make_dirty_row(
            "watermelon rind",
            nutrition_code="HXP-PRODUCT-WATERMELON-RIND",
            nutrition_code_type="hestia_product_proxy_candidate",
            nutrition_match_state="product_proxy_candidate",
            sr28_code="167765",
            sr28_description="Watermelon, raw",
            fndds_code="63149010",
            fndds_description="Watermelon, raw",
            esha_code="3088",
            esha_description="Orange Peel, fresh, grated",
            esha_match_type="esha_terminal_proxy:exact:orange peel",
            proxy_code="167765",
            proxy_description="Watermelon, raw",
            proxy_reason="watermelon proxy candidate",
            product_proxy_code="HXP-PRODUCT-WATERMELON-RIND",
            product_anchor_code="167765",
            product_anchor_description="Watermelon, raw",
        )

        repair_rows([row])

        self.assertEqual("", row["nutrition_code"])
        self.assertEqual("", row["sr28_code"])
        self.assertEqual("", row["esha_code"])
        self.assertEqual("fruit_rind_manual_review", row["unmatched_reason"])

    def test_cheez_it_crackers_stop_using_woven_wheat_floor(self):
        row = make_dirty_row(
            "cheez it crackers",
            nutrition_code="HXP-SR28-167933-CHEEZ-IT-CRACKER",
            nutrition_code_type="hestia_reference_proxy_candidate",
            nutrition_match_state="reference_proxy_candidate",
            sr28_code="167933",
            sr28_description="Crackers, whole-wheat, reduced fat",
            fndds_code="54337060",
            fndds_description="Crackers, woven wheat, reduced fat",
            esha_code="52967",
            esha_description="Cracker, Cheez-It, big",
            proxy_code="167933",
            proxy_description="Crackers, whole-wheat, reduced fat",
            proxy_reason="crispbread/cracker proxy candidate; whole-wheat cracker backbone",
            product_proxy_code="HXP-SR28-167933-CHEEZ-IT-CRACKER",
            product_anchor_code="167933",
            product_anchor_description="Crackers, whole-wheat, reduced fat",
        )

        repair_rows([row])

        self.assertEqual("174975", row["sr28_code"])
        self.assertEqual("54304005", row["fndds_code"])
        self.assertEqual("53775", row["esha_code"])
        self.assertEqual("Cracker, Cheez-It, original", row["esha_description"])

    def test_graham_crust_stops_using_whole_wheat_crackers(self):
        row = make_dirty_row(
            "deep dish graham cracker crust",
            nutrition_code="HXP-SR28-167933-DEEP-DISH-GRAHAM-CRACKER-CRUST",
            nutrition_code_type="hestia_reference_proxy_candidate",
            nutrition_match_state="reference_proxy_candidate",
            sr28_code="167933",
            sr28_description="Crackers, whole-wheat, reduced fat",
            fndds_code="54337060",
            fndds_description="Crackers, woven wheat, reduced fat",
            esha_code="52879",
            esha_description="Crackers, Toppers, original",
            proxy_code="167933",
            proxy_description="Crackers, whole-wheat, reduced fat",
            proxy_reason="crispbread/cracker proxy candidate; whole-wheat cracker backbone",
            product_proxy_code="HXP-SR28-167933-DEEP-DISH-GRAHAM-CRACKER-CRUST",
            product_anchor_code="167933",
            product_anchor_description="Crackers, whole-wheat, reduced fat",
        )

        repair_rows([row])

        self.assertEqual("167520", row["sr28_code"])
        self.assertEqual("53391100", row["fndds_code"])
        self.assertEqual("48475", row["esha_code"])
        self.assertEqual("Crust, pie, graham cracker, Honey Maid, ready to use", row["esha_description"])


class SurfaceSignalRepairSyrupJuiceSorbetToppingTests(unittest.TestCase):
    def test_coffee_syrup_stops_using_brewed_coffee(self):
        row = make_dirty_row(
            "coffee syrup",
            nutrition_code="HXP-PRODUCT-COFFEE-SYRUP",
            nutrition_code_type="hestia_product_proxy_candidate",
            nutrition_match_state="product_proxy_candidate",
            sr28_code="171890",
            sr28_description="Beverages, coffee, brewed, prepared with tap water",
            fndds_code="92100000",
            fndds_description="Coffee, NS as to type",
            esha_code="15627",
            esha_description="Syrup, coffee",
            proxy_code="171890",
            proxy_description="Beverages, coffee, brewed, prepared with tap water",
            proxy_reason="brewed coffee proxy candidate; review strength/additions",
            product_proxy_code="HXP-PRODUCT-COFFEE-SYRUP",
            product_anchor_code="171890",
            product_anchor_description="Beverages, coffee, brewed, prepared with tap water",
            notes="syrup family; family floor preserved named identity",
        )

        repair_rows([row])

        self.assertEqual("169578", row["sr28_code"])
        self.assertEqual("Syrups, table blends, pancake", row["sr28_description"])
        self.assertEqual("", row["fndds_code"])
        self.assertEqual("15627", row["esha_code"])
        self.assertEqual("", row["proxy_code"])

    def test_blueberry_cranberry_juice_stops_using_raw_cranberries(self):
        row = make_dirty_row(
            "blueberry cranberry juice",
            nutrition_code="HXP-PRODUCT-BLUEBERRY-CRANBERRY-JUICE",
            nutrition_code_type="hestia_product_proxy_candidate",
            nutrition_match_state="product_proxy_candidate",
            sr28_code="171722",
            sr28_description="Cranberries, raw",
            esha_code="3984",
            esha_description="Juice, fruit fiesta",
            proxy_code="171722",
            proxy_description="Cranberries, raw",
            proxy_reason="berry juice proxy candidate",
            product_proxy_code="HXP-PRODUCT-BLUEBERRY-CRANBERRY-JUICE",
            product_anchor_code="171722",
            product_anchor_description="Cranberries, raw",
        )

        repair_rows([row])

        self.assertEqual("", row["sr28_code"])
        self.assertEqual("64100200", row["fndds_code"])
        self.assertEqual("Cranberry juice blend, 100% juice", row["fndds_description"])
        self.assertEqual("4944", row["esha_code"])
        self.assertEqual("Juice, cranberry blueberry", row["esha_description"])

    def test_generic_sorbet_stops_using_lemon_exact(self):
        row = make_dirty_row(
            "sorbet",
            nutrition_code="HXP-SR28-168113-SORBET",
            nutrition_code_type="hestia_reference_proxy_candidate",
            nutrition_match_state="reference_proxy_candidate",
            sr28_code="168113",
            sr28_description="Frozen novelties, juice type, orange",
            esha_code="19318",
            esha_description="Sorbet, lemon",
            proxy_code="168113",
            proxy_description="Frozen novelties, juice type, orange",
            proxy_reason="frozen novelty proxy candidate",
            product_proxy_code="HXP-SR28-168113-SORBET",
            product_anchor_code="168113",
            product_anchor_description="Frozen novelties, juice type, orange",
        )

        repair_rows([row])

        self.assertEqual("", row["sr28_code"])
        self.assertEqual("63430100", row["fndds_code"])
        self.assertEqual("Sorbet, fruit, noncitrus flavor", row["fndds_description"])
        self.assertEqual("", row["esha_code"])

    def test_hot_fudge_topping_stops_using_sugar_free_only(self):
        row = make_dirty_row(
            "hot fudge topping",
            nutrition_code="HXP-PRODUCT-HOT-FUDGE-TOPPING",
            nutrition_code_type="hestia_product_proxy_candidate",
            nutrition_match_state="product_proxy_candidate",
            sr28_code="167987",
            sr28_description="Candies, fudge, chocolate, prepared-from-recipe",
            esha_code="54307",
            esha_description="Topping, hot fudge, sugar free, fat free",
            proxy_code="167987",
            proxy_description="Candies, fudge, chocolate, prepared-from-recipe",
            proxy_reason="fudge proxy candidate",
            product_proxy_code="HXP-PRODUCT-HOT-FUDGE-TOPPING",
            product_anchor_code="167987",
            product_anchor_description="Candies, fudge, chocolate, prepared-from-recipe",
        )

        repair_rows([row])

        self.assertEqual("", row["sr28_code"])
        self.assertEqual("91304020", row["fndds_code"])
        self.assertEqual("54289", row["esha_code"])
        self.assertEqual("Topping, hot fudge, spoonable", row["esha_description"])

    def test_strawberry_ice_cream_topping_stops_using_vanilla_ice_cream(self):
        row = make_dirty_row(
            "strawberry ice cream topping",
            nutrition_code="HXP-PRODUCT-STRAWBERRY-TOPPING-ICE-CREAM",
            nutrition_code_type="hestia_product_proxy_candidate",
            nutrition_match_state="product_proxy_candidate",
            sr28_code="168810",
            sr28_description="Ice creams, strawberry",
            esha_code="2004",
            esha_description="Ice Cream, vanilla",
            proxy_code="168810",
            proxy_description="Ice creams, strawberry",
            proxy_reason="strawberry ice cream proxy candidate",
            product_proxy_code="HXP-PRODUCT-STRAWBERRY-TOPPING-ICE-CREAM",
            product_anchor_code="168810",
            product_anchor_description="Ice creams, strawberry",
        )

        repair_rows([row])

        self.assertEqual("", row["sr28_code"])
        self.assertEqual("91361020", row["fndds_code"])
        self.assertEqual("35498", row["esha_code"])
        self.assertEqual("Topping, dessert, strawberry", row["esha_description"])

    def test_blueberry_topping_stops_using_plain_blueberries(self):
        row = make_dirty_row(
            "blueberry topping",
            nutrition_code="HXP-SR28-171711-BLUEBERRY-TOPPING",
            nutrition_code_type="hestia_reference_proxy_candidate",
            nutrition_match_state="reference_proxy_candidate",
            sr28_code="171711",
            sr28_description="Blueberries, raw",
            fndds_code="63203010",
            fndds_description="Blueberries, raw",
            esha_code="9237",
            esha_description="Blueberries, dried",
            proxy_code="171711",
            proxy_description="Blueberries, raw",
            proxy_reason="blueberry proxy candidate",
            product_proxy_code="HXP-SR28-171711-BLUEBERRY-TOPPING",
            product_anchor_code="171711",
            product_anchor_description="Blueberries, raw",
        )

        repair_rows([row])

        self.assertEqual("", row["sr28_code"])
        self.assertEqual("91361020", row["fndds_code"])
        self.assertEqual("35472", row["esha_code"])
        self.assertEqual("Topping, dessert, blueberry", row["esha_description"])

    def test_lemon_juiced_stops_using_lemon_zest(self):
        row = make_dirty_row(
            "lemon juiced",
            nutrition_code="HXP-SR28-167746-LEMON-JUICED",
            nutrition_code_type="hestia_reference_proxy_candidate",
            nutrition_match_state="reference_proxy_candidate",
            sr28_code="167746",
            sr28_description="Lemons, raw, without peel",
            fndds_code="61113010",
            fndds_description="Lemon, raw",
            esha_code="31962",
            esha_description="Lemon Zest",
            proxy_code="167746",
            proxy_description="Lemons, raw, without peel",
            proxy_reason="lemon proxy candidate",
            product_proxy_code="HXP-SR28-167746-LEMON-JUICED",
            product_anchor_code="167746",
            product_anchor_description="Lemons, raw, without peel",
        )

        repair_rows([row])

        self.assertEqual("", row["sr28_code"])
        self.assertEqual("61204010", row["fndds_code"])
        self.assertEqual("3068", row["esha_code"])
        self.assertEqual("Juice, lemon, fresh", row["esha_description"])


class SurfaceSignalRepairCondimentBucketTests(unittest.TestCase):
    def test_abalone_sauce_stops_using_raw_abalone(self):
        row = make_dirty_row(
            "abalone sauce",
            nutrition_code="SR28:174212",
            nutrition_code_type="sr28_reference_match",
            nutrition_match_state="sr28_match",
            sr28_code="174212",
            sr28_description="Mollusks, abalone, mixed species, raw",
            esha_match_type="cleared_wrong_family:non_barbecue_sauce",
            proxy_code="174212",
            proxy_description="Mollusks, abalone, mixed species, raw",
            proxy_reason="sauce family floor",
            product_proxy_code="HXP-SR28-174212-ABALONE-SAUCE",
            product_anchor_code="174212",
            product_anchor_description="Mollusks, abalone, mixed species, raw",
        )

        repair_rows([row])

        self.assertEqual("", row["sr28_code"])
        self.assertEqual("27150200", row["fndds_code"])
        self.assertEqual("Oyster sauce", row["fndds_description"])
        self.assertEqual("53473", row["esha_code"])
        self.assertEqual("Sauce, oyster, ready to serve", row["esha_description"])

    def test_habanero_hot_sauce_stops_using_fresh_pepper(self):
        row = make_dirty_row(
            "habanero hot sauce",
            nutrition_code="",
            nutrition_code_type="",
            nutrition_match_state="reviewed_nutrition_unknown",
            esha_code="37877",
            esha_description="Chile Pepper, habanero, orange, fresh",
            esha_match_type="esha_terminal_proxy:code:37877",
            notes="sauce family; family floor preserved named identity",
        )

        repair_rows([row])

        self.assertEqual("", row["sr28_code"])
        self.assertEqual("75511010", row["fndds_code"])
        self.assertEqual("Hot pepper sauce", row["fndds_description"])
        self.assertEqual("21452", row["esha_code"])
        self.assertEqual("Sauce, hot", row["esha_description"])

    def test_chipotle_sauce_with_lime_juice_stops_using_raw_pepper(self):
        row = make_dirty_row(
            "lawry's baja chipotle sauce with lime juice",
            nutrition_code="SR28:174527",
            nutrition_code_type="sr28_reference_match",
            nutrition_match_state="sr28_match",
            sr28_code="174527",
            sr28_description="Sauce, ready-to-serve, pepper or hot",
            fndds_code="75122000",
            fndds_description="Pepper, raw, NFS",
            esha_code="13367",
            esha_description="Chile Pepper, hot",
            esha_match_type="audit_repair:esha_terminal_proxy:code:13367",
        )

        repair_rows([row])

        self.assertEqual("", row["sr28_code"])
        self.assertEqual("75511010", row["fndds_code"])
        self.assertEqual("Hot pepper sauce", row["fndds_description"])
        self.assertEqual("33313", row["esha_code"])
        self.assertEqual("Sauce, chipotle", row["esha_description"])

    def test_jalapeno_relish_stops_using_fresh_pepper(self):
        row = make_dirty_row(
            "jalapeño relish",
            nutrition_code="",
            nutrition_code_type="",
            nutrition_match_state="reviewed_nutrition_unknown",
            esha_code="39180",
            esha_description="Chile Pepper, jalapeno",
            esha_match_type="esha_terminal_proxy:code:39180",
        )

        repair_rows([row])

        self.assertEqual("", row["sr28_code"])
        self.assertEqual("75515010", row["fndds_code"])
        self.assertEqual("Vegetable relish", row["fndds_description"])
        self.assertEqual("52391", row["esha_code"])
        self.assertEqual("Sandwich Topping, relish", row["esha_description"])

    def test_relish_sandwich_spread_stops_using_margarine(self):
        row = make_dirty_row(
            "relish sandwich spread",
            nutrition_code="",
            nutrition_code_type="",
            nutrition_match_state="reviewed_nutrition_unknown",
            esha_code="8041",
            esha_description="Spread, margarine, reduced calorie, unspecified oil, 37%fat",
            esha_match_type="esha_terminal_proxy:phrase:spread margarine",
        )

        repair_rows([row])

        self.assertEqual("171409", row["sr28_code"])
        self.assertEqual("81302040", row["fndds_code"])
        self.assertEqual("9438", row["esha_code"])
        self.assertEqual("Dressing, mayonnaise, with relish, Sandwich Spread", row["esha_description"])

    def test_red_wine_vinegar_graph_consensus_stops_using_wine(self):
        row = make_dirty_row(
            "red wine vinegar",
            nutrition_code="SR28:173190",
            nutrition_code_type="sr28_reference_match",
            nutrition_match_state="sr28_match",
            sr28_code="173190",
            sr28_description="Alcoholic beverage, wine, table, red",
            fndds_code="93401010",
            fndds_description="Wine, table, red",
            esha_code="22501",
            esha_description="Wine, red",
            esha_match_type="esha_terminal_proxy:code:22501",
        )

        with patch("run_surface_signal_repair.load_graph_consensus_esha_codes", return_value={"red wine vinegar": "27204"}):
            repair_rows([row])

        self.assertEqual("172240", row["sr28_code"])
        self.assertEqual("64401000", row["fndds_code"])
        self.assertEqual("27204", row["esha_code"])
        self.assertEqual("Vinegar, red wine", row["esha_description"])

    def test_pineapple_sherbet_stops_using_raw_pineapple(self):
        row = make_dirty_row(
            "pineapple sherbet",
            nutrition_code="SR28:169124",
            nutrition_code_type="sr28_reference_match",
            nutrition_match_state="sr28_match",
            sr28_code="169124",
            sr28_description="Pineapple, raw, all varieties",
            fndds_code="63141010",
            fndds_description="Pineapple, raw",
            esha_code="27367",
            esha_description="Pineapple",
            esha_match_type="canonical_to_esha",
        )

        repair_rows([row])

        self.assertEqual("", row["sr28_code"])
        self.assertEqual("13150000", row["fndds_code"])
        self.assertEqual("Sherbet, all flavors", row["fndds_description"])
        self.assertEqual("", row["esha_code"])

    def test_mixed_fruit_sherbet_stops_using_fruit_cocktail(self):
        row = make_dirty_row(
            "mixed fruit sherbet",
            nutrition_code="SR28:173027",
            nutrition_code_type="sr28_reference_match",
            nutrition_match_state="sr28_match",
            sr28_code="173027",
            sr28_description="Fruit cocktail, (peach and pineapple and pear and grape and cherry), canned, light syrup, solids and liquids",
            esha_code="3164",
            esha_description="Fruit Cocktail, canned, with juice",
            esha_match_type="esha_terminal_proxy:exact:fruit cocktail",
        )

        repair_rows([row])

        self.assertEqual("", row["sr28_code"])
        self.assertEqual("13150000", row["fndds_code"])
        self.assertEqual("Sherbet, all flavors", row["fndds_description"])
        self.assertEqual("", row["esha_code"])

    def test_habanero_juice_is_cleared_instead_of_fresh_pepper(self):
        row = make_dirty_row(
            "habanero juice",
            nutrition_code="",
            nutrition_code_type="",
            nutrition_match_state="reviewed_nutrition_unknown",
            esha_code="37877",
            esha_description="Chile Pepper, habanero, orange, fresh",
            esha_match_type="audit_repair:esha_terminal_proxy:code:37877",
        )

        repair_rows([row])

        self.assertEqual("", row["nutrition_code"])
        self.assertEqual("", row["fndds_code"])
        self.assertEqual("", row["esha_code"])
        self.assertEqual("specialty_juice_manual_review", row["unmatched_reason"])

    def test_garlic_yogurt_dressing_gets_yogurt_dressing_floor(self):
        row = make_dirty_row(
            "garlic yogurt dressing",
            nutrition_code="SR28:171417",
            nutrition_code_type="sr28_reference_match",
            nutrition_match_state="sr28_match",
            sr28_code="171417",
            sr28_description="Salad dressing, home recipe, vinegar and oil",
            proxy_code="171417",
            proxy_description="Salad dressing, home recipe, vinegar and oil",
            proxy_reason="dressing family floor",
        )

        repair_rows([row])

        self.assertEqual("", row["sr28_code"])
        self.assertEqual("83115000", row["fndds_code"])
        self.assertEqual("Yogurt dressing", row["fndds_description"])
        self.assertEqual("", row["esha_code"])

    def test_yogurt_cheese_is_cleared_not_cheddar(self):
        row = make_dirty_row(
            "yogurt cheese",
            nutrition_code="SR28:173414",
            nutrition_code_type="sr28_reference_match",
            nutrition_match_state="sr28_match",
            sr28_code="173414",
            sr28_description="Cheese, cheddar (Includes foods for USDA's Food Distribution Program)",
            esha_code="33342",
            esha_description="Cheese, cheddar",
            esha_match_type="esha_terminal_proxy:code:33342",
        )

        repair_rows([row])

        self.assertEqual("", row["nutrition_code"])
        self.assertEqual("", row["sr28_code"])
        self.assertEqual("", row["esha_code"])
        self.assertEqual("specialty_yogurt_cheese_manual_review", row["unmatched_reason"])

    def test_chocolate_jello_pudding_mix_stops_using_gelatin(self):
        row = make_dirty_row(
            "chocolate jello pudding mix",
            nutrition_code="SR28:168775",
            nutrition_code_type="sr28_reference_match",
            nutrition_match_state="sr28_match",
            sr28_code="168775",
            sr28_description="Gelatin desserts, dry mix",
            fndds_code="91500200",
            fndds_description="Gelatin powder, sweetened, dry",
            esha_code="90717",
            esha_description="Gelatin, sweetened, dry mix",
            esha_match_type="esha_terminal_proxy:code:90717",
        )

        repair_rows([row])

        self.assertEqual("169603", row["sr28_code"])
        self.assertEqual("13210220", row["fndds_code"])
        self.assertEqual("2635", row["esha_code"])
        self.assertEqual("Pudding, chocolate, dry mix", row["esha_description"])


class SurfaceSignalRepairGraphConsensusTests(unittest.TestCase):
    def test_graph_consensus_chili_sauce_stops_using_hot_pepper(self):
        row = make_dirty_row(
            "tomato chili sauce",
            nutrition_code="",
            nutrition_code_type="",
            nutrition_match_state="reviewed_nutrition_unknown",
            esha_code="13367",
            esha_description="Chile Pepper, hot",
            esha_match_type="esha_terminal_proxy:code:13367",
        )
        row["canonical_normalized"] = "chili sauce"
        row["canonical_shopping_item"] = "chili sauce"

        with patch("run_surface_signal_repair.load_graph_consensus_esha_codes", return_value={"chili sauce": "434"}):
            repair_rows([row])

        self.assertEqual("171595", row["sr28_code"])
        self.assertEqual("74402010", row["fndds_code"])
        self.assertEqual("434", row["esha_code"])
        self.assertEqual("Sauce, chili", row["esha_description"])

    def test_graph_consensus_pickle_relish_stops_using_sour_pickles(self):
        row = make_dirty_row(
            "sweet pickle relish",
            nutrition_code="SR28:168561",
            nutrition_code_type="sr28_reference_match",
            nutrition_match_state="sr28_match",
            sr28_code="168561",
            sr28_description="Pickle relish, sweet",
            fndds_code="75511200",
            fndds_description="Pickles, mixed",
            esha_code="13358",
            esha_description="Pickles, sour",
            esha_match_type="exact",
        )

        with patch("run_surface_signal_repair.load_graph_consensus_esha_codes", return_value={"sweet pickle relish": "18032"}):
            repair_rows([row])

        self.assertEqual("168561", row["sr28_code"])
        self.assertEqual("75503020", row["fndds_code"])
        self.assertEqual("18032", row["esha_code"])
        self.assertEqual("Relish, pickle, sweet", row["esha_description"])

    def test_graph_consensus_spaghetti_squash_stops_using_pasta(self):
        row = make_dirty_row(
            "spaghetti squash",
            nutrition_code="",
            nutrition_code_type="",
            nutrition_match_state="reviewed_nutrition_unknown",
            esha_code="38579",
            esha_description="Pasta, semolina, macaroni, elbow, dry",
            esha_match_type="esha_terminal_proxy:code:38579",
            notes="Top2500 batch16 reviewed spaghetti squash to spaghetti squash; stale broad assignment cleared.",
        )

        with patch("run_surface_signal_repair.load_graph_consensus_esha_codes", return_value={"spaghetti squash": "5455"}):
            repair_rows([row])

        self.assertEqual("169299", row["sr28_code"])
        self.assertEqual("75233220", row["fndds_code"])
        self.assertEqual("5455", row["esha_code"])
        self.assertEqual("Squash, spaghetti, cooked, drained", row["esha_description"])

    def test_graph_consensus_vegetarian_chili_stops_using_raw_peppers(self):
        row = make_dirty_row(
            "vegetarian chili",
            nutrition_code="SR28:170106",
            nutrition_code_type="sr28_reference_match",
            nutrition_match_state="sr28_match",
            sr28_code="170106",
            sr28_description="Peppers, hot chili, red, raw",
            esha_code="13367",
            esha_description="Chile Pepper, hot",
            esha_match_type="esha_terminal_proxy:code:13367",
        )

        with patch("run_surface_signal_repair.load_graph_consensus_esha_codes", return_value={"vegetarian chili": "7760"}):
            repair_rows([row])

        self.assertEqual("", row["sr28_code"])
        self.assertEqual("41812450", row["fndds_code"])
        self.assertEqual("7760", row["esha_code"])
        self.assertEqual("Chili, vegetarian, canned", row["esha_description"])

    def test_graph_consensus_nutritional_yeast_clears_bakers_yeast(self):
        row = make_dirty_row(
            "nutritional yeast flakes",
            nutrition_code="SR28:175043",
            nutrition_code_type="sr28_reference_match",
            nutrition_match_state="sr28_match",
            sr28_code="175043",
            sr28_description="Leavening agents, yeast, baker's, active dry",
            fndds_code="75236000",
            fndds_description="Yeast",
            esha_code="28000",
            esha_description="Yeast, baker's, dry active",
            esha_match_type="esha_terminal_proxy:code:28000",
        )
        row["canonical_normalized"] = "nutritional yeast"
        row["canonical_shopping_item"] = "nutritional yeast"

        with patch("run_surface_signal_repair.load_graph_consensus_esha_codes", return_value={"nutritional yeast": "7784"}):
            repair_rows([row])

        self.assertEqual("", row["sr28_code"])
        self.assertEqual("", row["fndds_code"])
        self.assertEqual("7784", row["esha_code"])
        self.assertEqual("Yeast, nutritional, flakes", row["esha_description"])

    def test_graph_consensus_malt_vinegar_stops_using_barley_flour(self):
        row = make_dirty_row(
            "malt vinegar",
            nutrition_code="HXP-PRODUCT-MALT-VINEGAR",
            nutrition_code_type="hestia_product_proxy_candidate",
            nutrition_match_state="product_proxy_candidate",
            sr28_code="173469",
            sr28_description="Vinegar, cider",
            fndds_code="64401000",
            fndds_description="Vinegar",
            esha_code="93145",
            esha_description="Flour, barley, malted",
            esha_match_type="esha_terminal_proxy:code:93145",
        )

        with patch("run_surface_signal_repair.load_graph_consensus_esha_codes", return_value={"malt vinegar": "41309"}):
            repair_rows([row])

        self.assertEqual("", row["sr28_code"])
        self.assertEqual("64401000", row["fndds_code"])
        self.assertEqual("41309", row["esha_code"])
        self.assertEqual("Vinegar, malt", row["esha_description"])


class SurfaceSignalRepairDessertAndAvocadoTests(unittest.TestCase):
    def test_ripe_hass_avocado_stops_using_frozen_halves(self):
        row = make_dirty_row(
            "ripe hass avocado",
            nutrition_code="HXP-SR28-171706-RIPE-HASS-AVOCADO",
            nutrition_code_type="hestia_reference_proxy_candidate",
            nutrition_match_state="reference_proxy_candidate",
            sr28_code="171706",
            sr28_description="Avocados, raw, California",
            esha_code="44419",
            esha_description="Avocado, halves, fs",
            esha_match_type="canonical_to_esha",
            proxy_code="171706",
            proxy_description="Avocados, raw, California",
            proxy_reason="avocado spelling/proxy candidate; avocado backbone",
            product_proxy_code="HXP-SR28-171706-RIPE-HASS-AVOCADO",
            product_anchor_code="171706",
            product_anchor_description="Avocados, raw, California",
        )

        repair_rows([row])

        self.assertEqual("171706", row["sr28_code"])
        self.assertEqual("63105010", row["fndds_code"])
        self.assertEqual("3210", row["esha_code"])
        self.assertEqual("Avocado, California, fresh", row["esha_description"])

    def test_banana_cream_pudding_stops_using_babyfood_and_heavy_cream(self):
        row = make_dirty_row(
            "banana cream pudding",
            nutrition_code="HXP-PRODUCT-BANANA-CREAM-PUDDING",
            nutrition_code_type="hestia_product_proxy_candidate",
            nutrition_match_state="product_proxy_candidate",
            sr28_code="169872",
            sr28_description="Babyfood, dessert, banana pudding, strained",
            fndds_code="12130100",
            fndds_description="Cream, heavy",
            esha_code="502",
            esha_description="Cream, whipping, heavy",
            esha_match_type="esha_terminal_proxy:code:502",
            proxy_code="170859",
            proxy_description="Cream, fluid, heavy whipping",
            proxy_reason="pudding proxy candidate; review flavor and prepared/dry state",
            product_proxy_code="HXP-PRODUCT-BANANA-CREAM-PUDDING",
            product_anchor_code="170859",
            product_anchor_description="Cream, fluid, heavy whipping",
        )

        repair_rows([row])

        self.assertEqual("", row["sr28_code"])
        self.assertEqual("", row["fndds_code"])
        self.assertEqual("2738", row["esha_code"])
        self.assertEqual("Pudding, banana cream, instant, serving", row["esha_description"])
        self.assertEqual("reviewed_nutrition_unknown", row["nutrition_match_state"])

    def test_american_custard_mix_stops_using_babyfood_and_flan(self):
        row = make_dirty_row(
            "american custard mix",
            nutrition_code="HXP-FNDDS-13210300-AMERICAN-CUSTARD-MIX",
            nutrition_code_type="hestia_reference_proxy_candidate",
            nutrition_match_state="reference_proxy_candidate",
            sr28_code="171379",
            sr28_description="Babyfood, dessert, custard pudding, vanilla, strained",
            fndds_code="13210300",
            fndds_description="Custard",
            esha_code="52414",
            esha_description="Custard, flan",
            esha_match_type="esha_bridge:exact:custard",
            proxy_code="171725",
            proxy_description="Custard",
            proxy_reason="custard proxy candidate; review flavor/fat state",
            product_proxy_code="HXP-FNDDS-13210300-AMERICAN-CUSTARD-MIX",
            product_anchor_code="171725",
            product_anchor_description="Custard-apple, (bullock's-heart), raw",
        )

        repair_rows([row])

        self.assertEqual("168772", row["sr28_code"])
        self.assertEqual("13210300", row["fndds_code"])
        self.assertEqual("2795", row["esha_code"])
        self.assertEqual("Custard, dessert, Americana, dry mix, serving", row["esha_description"])

    def test_creme_anglaise_with_accent_stops_using_babyfood_and_flan(self):
        row = make_dirty_row(
            "crème anglaise",
            nutrition_code="HXP-FNDDS-13210300-CREME-ANGLAISE",
            nutrition_code_type="hestia_reference_proxy_candidate",
            nutrition_match_state="reference_proxy_candidate",
            sr28_code="171379",
            sr28_description="Babyfood, dessert, custard pudding, vanilla, strained",
            fndds_code="13210300",
            fndds_description="Custard",
            esha_code="52414",
            esha_description="Custard, flan",
            esha_match_type="esha_bridge:exact:custard",
            proxy_code="171725",
            proxy_description="Custard",
            proxy_reason="creme anglaise proxy candidate; custard backbone",
            product_proxy_code="HXP-FNDDS-13210300-CREME-ANGLAISE",
            product_anchor_code="171725",
            product_anchor_description="Custard-apple, (bullock's-heart), raw",
        )

        repair_rows([row])

        self.assertEqual("", row["sr28_code"])
        self.assertEqual("13210300", row["fndds_code"])
        self.assertEqual("2663", row["esha_code"])
        self.assertEqual("Custard, vanilla, prepared from dry mix with whole milk", row["esha_description"])

    def test_custard_stops_using_custard_apple_and_babyfood(self):
        row = make_dirty_row(
            "custard",
            nutrition_code="HXP-SR28-171725-CUSTARD",
            nutrition_code_type="hestia_reference_proxy_candidate",
            nutrition_match_state="reference_proxy_candidate",
            sr28_code="171379",
            sr28_description="Babyfood, dessert, custard pudding, vanilla, strained",
            esha_code="52414",
            esha_description="Custard, flan",
            esha_match_type="exact",
            proxy_code="171725",
            proxy_description="Custard-apple, (bullock's-heart), raw",
            proxy_reason="custard backbone",
            product_anchor_code="171725",
            product_anchor_description="Custard-apple, (bullock's-heart), raw",
        )

        repair_rows([row])

        self.assertEqual("", row["sr28_code"])
        self.assertEqual("13210300", row["fndds_code"])
        self.assertEqual("2613", row["esha_code"])
        self.assertEqual("Custard, egg, prepared from dry mix with whole milk", row["esha_description"])

    def test_cheesecake_yogurt_stops_using_babyfood_and_plain_yogurt(self):
        row = make_dirty_row(
            "berry cheesecake yogurt",
            nutrition_code="HXP-SR28-171284-BERRY-CHEESECAKE-YOGURT",
            nutrition_code_type="hestia_reference_proxy_candidate",
            nutrition_match_state="reference_proxy_candidate",
            sr28_code="167726",
            sr28_description="Babyfood, mixed fruit yogurt, strained",
            fndds_code="11411100",
            fndds_description="Yogurt, whole milk, plain",
            esha_code="2013",
            esha_description="Yogurt, plain, whole milk, 8g protein, 8oz container",
            esha_match_type="esha_terminal_proxy:code:2013",
            proxy_code="171284",
            proxy_description="Yogurt, plain, whole milk",
            proxy_reason="forced family floor; replaced wrong-family nutrition backbone",
            product_proxy_code="HXP-SR28-171284-BERRY-CHEESECAKE-YOGURT",
            product_anchor_code="171284",
            product_anchor_description="Yogurt, plain, whole milk",
        )

        repair_rows([row])

        self.assertEqual("170889", row["sr28_code"])
        self.assertEqual("11430000", row["fndds_code"])
        self.assertEqual("72485", row["esha_code"])
        self.assertEqual("Yogurt, Thick & Creamy, raspberry cheesecake, low fat", row["esha_description"])

    def test_mango_baby_food_gets_infant_mango_esha(self):
        row = make_dirty_row(
            "mango baby food",
            nutrition_code="SR28:171341",
            nutrition_code_type="sr28_reference_match",
            nutrition_match_state="sr28_match",
            sr28_code="171341",
            sr28_description="Babyfood, fruit dessert, mango with tapioca",
        )

        repair_rows([row])

        self.assertEqual("171341", row["sr28_code"])
        self.assertEqual("23860", row["esha_code"])
        self.assertEqual("Infant Dessert, 2nd Foods, tropical, mango", row["esha_description"])


if __name__ == "__main__":
    unittest.main()
