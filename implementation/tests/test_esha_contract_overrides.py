from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
IMPLEMENTATION_ROOT = ROOT / "implementation"
if str(IMPLEMENTATION_ROOT) not in sys.path:
    sys.path.insert(0, str(IMPLEMENTATION_ROOT))

from esha_contracts import contract_source_module, evaluate_facts
from esha_contracts.contract_base import ProductFacts


def facts(description: str, category: str, ingredients: str = "") -> ProductFacts:
    return ProductFacts.from_components(description, category, ingredients)


class ContractOverrideTests(unittest.TestCase):
    def test_plain_cow_milk_contracts_reject_flavored_and_wrong_fat_variants(self) -> None:
        self.assertEqual(contract_source_module("1"), "esha_contracts")
        self.assertEqual(evaluate_facts("1", facts("WHOLE MILK", "Milk")).status, "accept")
        self.assertEqual(evaluate_facts("1", facts("2% REDUCED FAT MILK", "Milk")).status, "reject")

        self.assertEqual(contract_source_module("2"), "esha_contracts")
        self.assertEqual(evaluate_facts("2", facts("2% REDUCED FAT MILK", "Milk")).status, "accept")
        self.assertEqual(evaluate_facts("2", facts("2% CHOCOLATE MILK", "Milk")).status, "reject")
        self.assertEqual(evaluate_facts("2", facts("1/2% LOWFAT MILK", "Milk")).status, "reject")

        self.assertEqual(contract_source_module("4"), "esha_contracts")
        self.assertEqual(evaluate_facts("4", facts("1% LOWFAT MILK", "Milk")).status, "accept")
        self.assertEqual(evaluate_facts("4", facts("2% REDUCED FAT MILK", "Milk")).status, "reject")

    def test_plain_animal_milk_overrides_block_cheese_and_yogurt(self) -> None:
        self.assertEqual(contract_source_module("42"), "esha_contracts")
        self.assertEqual(evaluate_facts("42", facts("SHEEP MILK FETA", "Cheese")).status, "reject")
        self.assertEqual(evaluate_facts("42", facts("SHEEP MILK", "Milk")).status, "accept")

        self.assertEqual(contract_source_module("23"), "esha_contracts")
        self.assertEqual(evaluate_facts("23", facts("PLAIN CHEVRE FRESH GOAT MILK CHEESE", "Cheese")).status, "reject")
        self.assertEqual(evaluate_facts("23", facts("PLAIN GOAT MILK YOGURT", "Yogurt")).status, "reject")
        self.assertEqual(evaluate_facts("23", facts("EVAPORATED GOAT MILK", "Milk")).status, "reject")
        self.assertEqual(evaluate_facts("23", facts("NONFAT POWDERED GOAT MILK", "Milk Additives")).status, "reject")
        self.assertEqual(evaluate_facts("23", facts("YO-GOAT PLAIN CULTURED GOAT MILK", "Milk")).status, "reject")
        self.assertEqual(evaluate_facts("23", facts("GOAT MILK", "Milk")).status, "accept")

    def test_carob_contract_requires_actual_carob_drink_identity(self) -> None:
        self.assertEqual(contract_source_module("43"), "esha_contracts")
        self.assertEqual(
            evaluate_facts("43", facts("NATURAL POWDER DRINK MIX, LEMON LIME", "Powdered Drinks")).status,
            "reject",
        )
        self.assertEqual(
            evaluate_facts("43", facts("CAROB DRINK MIX", "Powdered Drinks", "Carob powder")).status,
            "accept",
        )

    def test_low_sodium_milk_contract_rejects_generic_milk(self) -> None:
        self.assertEqual(contract_source_module("52"), "esha_contracts")
        self.assertEqual(evaluate_facts("52", facts("CONDENSED MILK", "Milk")).status, "reject")
        self.assertEqual(evaluate_facts("52", facts("LOW SODIUM MILK", "Milk")).status, "accept")

    def test_skim_milk_dry_mix_contract_rejects_hot_cocoa(self) -> None:
        self.assertEqual(contract_source_module("67"), "esha_contracts")
        self.assertEqual(
            evaluate_facts(
                "67",
                facts(
                    "MILK CHOCOLATE HOT COCOA MIX, MILK CHOCOLATE",
                    "Powdered Drinks",
                    "Sugar, Cocoa, Nonfat Milk, Coconut Oil",
                ),
            ).status,
            "reject",
        )
        self.assertEqual(
            evaluate_facts(
                "67",
                facts("MIX'N DRINK INSTANT SKIM MILK", "Milk", "Nonfat Dry Milk, Vitamin A, Vitamin D3"),
            ).status,
            "accept",
        )

    def test_rice_milk_vanilla_contract_rejects_chocolate_bars(self) -> None:
        self.assertEqual(contract_source_module("615"), "esha_contracts")
        self.assertEqual(
            evaluate_facts(
                "615",
                facts(
                    "MILK CHOCOLATE WITH CRISPED RICE, MILK CHOCOLATE",
                    "Chocolate",
                    "Milk Chocolate, Rice, Vanilla",
                ),
            ).status,
            "reject",
        )
        self.assertEqual(
            evaluate_facts(
                "615",
                facts("SHOPRITE, RICE MILK, VANILLA, VANILLA", "Plant Based Milk", "Brown Rice, Vanilla Extract"),
            ).status,
            "accept",
        )

    def test_vanilla_ready_drink_contract_rejects_orange_vanilla_seltzer(self) -> None:
        self.assertEqual(contract_source_module("618"), "esha_contracts")
        self.assertEqual(
            evaluate_facts("618", facts("12OZ 6PK ORANGE VANILLA SELTZER", "Non Alcoholic Beverages Ready to Drink")).status,
            "reject",
        )
        self.assertEqual(
            evaluate_facts("618", facts("VANILLA CLASSIC RICE DRINK, VANILLA", "Other Drinks")).status,
            "reject",
        )
        self.assertEqual(
            evaluate_facts("618", facts("VANILLA LATTE ICED ESPRESSO BEVERAGE, VANILLA LATTE", "Other Drinks")).status,
            "reject",
        )
        self.assertEqual(
            evaluate_facts("618", facts("VANILLA DRINK, VANILLA", "Other Drinks")).status,
            "accept",
        )

    def test_seltzer_water_contract_rejects_maple_and_lemonade_variants(self) -> None:
        self.assertEqual(contract_source_module("4791"), "esha_contracts")
        self.assertEqual(
            evaluate_facts("4791", facts("SMITH & SALMON, MAPLE SELTZER", "Plant Based Water", "Carbonated Maple Sap")).status,
            "reject",
        )
        self.assertEqual(
            evaluate_facts(
                "4791",
                facts(
                    "SPARKLING BLOOD ORANGE LEMONADE SELTZER'ADE, BLOOD ORANGE; LEMONADE",
                    "Water",
                    "Carbonated Water, Lemon Juice, Orange Flavor",
                ),
            ).status,
            "reject",
        )
        self.assertEqual(
            evaluate_facts("4791", facts("ORANGE SELTZER WATER, ORANGE", "Water", "Carbonated Water, Natural Flavor")).status,
            "accept",
        )

    def test_flavored_water_focus_and_spark_contracts(self) -> None:
        self.assertEqual(contract_source_module("37261"), "esha_contracts")
        self.assertEqual(
            evaluate_facts(
                "37261",
                facts("PINEAPPLE + GINGER + GINSENG FOCUS FUNCTIONAL ENERGY WATER BEVERAGE", "Water"),
            ).status,
            "accept",
        )
        self.assertEqual(
            evaluate_facts("37261", facts("HUCKLEBERRY FLAVOR FOCUS DRINK ENHANCER", "Liquid Water Enhancer")).status,
            "reject",
        )

        self.assertEqual(contract_source_module("37282"), "esha_contracts")
        self.assertEqual(evaluate_facts("37282", facts("SPARKLING WATER, GRAPEFRUIT", "Water")).status, "accept")
        self.assertEqual(
            evaluate_facts("37282", facts("SPARKLING BLOOD ORANGE LEMONADE", "Water")).status,
            "reject",
        )

        self.assertEqual(contract_source_module("37281"), "esha_contracts")
        self.assertEqual(
            evaluate_facts("37281", facts("STUR, LIQUID WATER ENHANCER, COCONUT WATER + LIME", "Liquid Water Enhancer")).status,
            "accept",
        )
        self.assertEqual(
            evaluate_facts("37281", facts("STUR, LIQUID TEA INFUSION, BLACK TEA + LEMON", "Liquid Water Enhancer")).status,
            "reject",
        )

    def test_cheddar_cheese_sauce_contract_rejects_pasta_dinners(self) -> None:
        self.assertEqual(contract_source_module("9558"), "esha_contracts")
        self.assertEqual(
            evaluate_facts(
                "9558",
                facts(
                    "DELUXE MACARONI & CHEESE DINNER WITH CREAMY CHEDDAR SAUCE, CHEDDAR CHEESE",
                    "Pasta Dinners",
                ),
            ).status,
            "reject",
        )
        self.assertEqual(
            evaluate_facts(
                "9558",
                facts(
                    "CHEDDAR SHELLS & CHEESE SAUCE, CHEDDAR",
                    "Pasta Dinners",
                ),
            ).status,
            "reject",
        )
        self.assertEqual(
            evaluate_facts(
                "9558",
                facts("CHEDDAR CHEESE SAUCE, CHEDDAR CHEESE", "Ketchup, Mustard, BBQ & Cheese Sauce"),
            ).status,
            "accept",
        )
        self.assertEqual(
            evaluate_facts(
                "9558",
                facts("NO DAIRY CHEDDAR CHEEZ STYLE PLANT BASED SAUCE", "Ketchup, Mustard, BBQ & Cheese Sauce"),
            ).status,
            "reject",
        )
        self.assertEqual(
            evaluate_facts(
                "9558",
                facts("VEGAN VALLEY, NACHO CHEDDAR CHEEZE SAUCE", "Ketchup, Mustard, BBQ & Cheese Sauce"),
            ).status,
            "reject",
        )

    def test_infant_green_bean_potato_contract_rejects_plain_green_beans(self) -> None:
        self.assertEqual(contract_source_module("436"), "esha_contracts")
        self.assertEqual(evaluate_facts("436", facts("CUT GREEN BEANS", "Frozen Vegetables")).status, "reject")
        self.assertEqual(
            evaluate_facts(
                "436",
                facts(
                    "BABY FOOD GREEN BEAN POTATO",
                    "Baby/Infant Foods/Beverages",
                    "Green Bean, Potato, Water",
                ),
            ).status,
            "accept",
        )

    def test_agra_peas_and_greens_contract_rejects_plain_peas(self) -> None:
        self.assertEqual(contract_source_module("16477"), "esha_contracts")
        self.assertEqual(evaluate_facts("16477", facts("GREEN PEAS", "Frozen Vegetables")).status, "reject")
        self.assertEqual(
            evaluate_facts("16477", facts("AGRA PEAS & GREENS SIDE DISH", "Frozen Prepared Sides")).status,
            "accept",
        )

    def test_spicy_tempeh_contract_rejects_black_bean_burgers(self) -> None:
        self.assertEqual(contract_source_module("16514"), "esha_contracts")
        self.assertEqual(
            evaluate_facts(
                "16514",
                facts("SPICY BLACK BEAN VEGGIE BURGERS", "Frozen Patties and Burgers"),
            ).status,
            "reject",
        )
        self.assertEqual(
            evaluate_facts("16514", facts("SPICY TEMPEH", "Other Meats", "Tempeh, jalapeno pepper")).status,
            "accept",
        )

    def test_vegetarian_jerky_contract_rejects_other_meat_alternatives(self) -> None:
        self.assertEqual(contract_source_module("16515"), "esha_contracts")
        self.assertEqual(
            evaluate_facts("16515", facts("ORIGINAL VEGETARIAN CHORIZO, ORIGINAL", "Other Meats")).status,
            "reject",
        )
        self.assertEqual(
            evaluate_facts("16515", facts("PINEAPPLE HABANERO ORIGINAL VEGAN JERKY", "Other Snacks")).status,
            "reject",
        )
        self.assertEqual(
            evaluate_facts("16515", facts("ORIGINAL VEGAN JERKY", "Other Snacks")).status,
            "accept",
        )

    def test_original_frozen_breakfast_and_tempeh_contracts(self) -> None:
        self.assertEqual(contract_source_module("12470"), "esha_contracts")
        self.assertEqual(evaluate_facts("12470", facts("APPLE CINNAMON WAFFLES", "Frozen Pancakes, Waffles, French Toast & Crepes")).status, "accept")
        self.assertEqual(evaluate_facts("12470", facts("ICE CREAM WAFFLE CONE", "Ice Cream & Frozen Yogurt")).status, "reject")

        self.assertEqual(contract_source_module("16642"), "esha_contracts")
        self.assertEqual(evaluate_facts("16642", facts("FROZEN PANCAKES, BUTTERMILK", "Frozen Pancakes, Waffles, French Toast & Crepes")).status, "accept")
        self.assertEqual(evaluate_facts("16642", facts("POTATO PANCAKE", "Frozen Pancakes, Waffles, French Toast & Crepes")).status, "reject")
        self.assertEqual(evaluate_facts("16642", facts("BERRY BITE-SIZED PANCAKES", "Frozen Pancakes, Waffles, French Toast & Crepes")).status, "reject")
        self.assertEqual(evaluate_facts("16642", facts("BUTTERMILK FLAVORED MINI PANCAKES", "Frozen Pancakes, Waffles, French Toast & Crepes")).status, "reject")

        self.assertEqual(contract_source_module("16643"), "esha_contracts")
        self.assertEqual(evaluate_facts("16643", facts("BUTTERMILK MINI PANCAKES", "Frozen Pancakes, Waffles, French Toast & Crepes")).status, "accept")
        self.assertEqual(evaluate_facts("16643", facts("BLUEBERRY PANCAKES", "Frozen Pancakes, Waffles, French Toast & Crepes")).status, "reject")

        self.assertEqual(contract_source_module("16646"), "esha_contracts")
        self.assertEqual(evaluate_facts("16646", facts("BLUEBERRY PANCAKES", "Frozen Pancakes, Waffles, French Toast & Crepes")).status, "accept")
        self.assertEqual(evaluate_facts("16646", facts("BUTTERMILK PANCAKES", "Frozen Pancakes, Waffles, French Toast & Crepes")).status, "reject")

        self.assertEqual(contract_source_module("45213"), "esha_contracts")
        self.assertEqual(evaluate_facts("45213", facts("HOMESTYLE WAFFLES", "Frozen Pancakes, Waffles, French Toast & Crepes")).status, "accept")
        self.assertEqual(evaluate_facts("45213", facts("BLUEBERRY FLAVORED WAFFLE", "Frozen Pancakes, Waffles, French Toast & Crepes")).status, "reject")
        self.assertEqual(evaluate_facts("45213", facts("APPLE CINNAMON WAFFLES", "Frozen Pancakes, Waffles, French Toast & Crepes")).status, "reject")
        self.assertEqual(evaluate_facts("45213", facts("BIRTHDAY CAKE BELGIAN WAFFLES", "Frozen Pancakes, Waffles, French Toast & Crepes")).status, "reject")

        self.assertEqual(contract_source_module("52742"), "esha_contracts")
        self.assertEqual(evaluate_facts("52742", facts("BLUEBERRY FLAVORED WAFFLE", "Frozen Pancakes, Waffles, French Toast & Crepes")).status, "accept")
        self.assertEqual(evaluate_facts("52742", facts("APPLE CINNAMON WAFFLES", "Frozen Pancakes, Waffles, French Toast & Crepes")).status, "reject")

        self.assertEqual(contract_source_module("91243"), "esha_contracts")
        self.assertEqual(evaluate_facts("91243", facts("ORIGINAL TEMPEH, ORIGINAL", "Other Meats")).status, "accept")
        self.assertEqual(evaluate_facts("91243", facts("BUFFALO TEMPEH PRECUT STRIPS, BUFFALO", "Other Meats")).status, "reject")

    def test_wild_rice_pancake_contract_rejects_soup_mix(self) -> None:
        self.assertEqual(contract_source_module("16693"), "esha_contracts")
        self.assertEqual(
            evaluate_facts("16693", facts("CREAMY WILD RICE SOUP MIX, CREAMY WILD RICE", "Other Soups")).status,
            "reject",
        )
        self.assertEqual(
            evaluate_facts("16693", facts("WILD RICE PANCAKE MIX", "Cake, Cookie & Cupcake Mixes")).status,
            "accept",
        )

    def test_ten_grain_waffle_contract_accepts_pancake_waffle_mix(self) -> None:
        self.assertEqual(contract_source_module("16695"), "esha_contracts")
        self.assertEqual(
            evaluate_facts("16695", facts("10 GRAIN PANCAKE & WAFFLE MIX, 10 GRAIN", "Cake, Cookie & Cupcake Mixes")).status,
            "accept",
        )
        self.assertEqual(
            evaluate_facts("16695", facts("7 GRAIN PANCAKE & WAFFLE MIX", "Cake, Cookie & Cupcake Mixes")).status,
            "reject",
        )

    def test_grated_parmesan_contract_rejects_filled_pasta(self) -> None:
        self.assertEqual(contract_source_module("1075"), "esha_contracts")
        self.assertEqual(
            evaluate_facts(
                "1075",
                facts(
                    "FOUR CHEESE RAVIOLI FILLED WITH RICOTTA, MOZZARELLA, ROMANO & PARMESAN CHEESES, FOUR CHEESE",
                    "Pasta by Shape & Type",
                ),
            ).status,
            "reject",
        )
        self.assertEqual(
            evaluate_facts("1075", facts("PARMESAN & ROMANO GRATED CHEESES", "Cheese")).status,
            "reject",
        )
        self.assertEqual(
            evaluate_facts("1075", facts("GRATED GARLIC & HERB PARMESAN CHEESE", "Cheese")).status,
            "reject",
        )
        self.assertEqual(
            evaluate_facts("1075", facts("PARMESAN STYLE GRATED CHEESE ALTERNATIVE", "Cheese")).status,
            "reject",
        )
        self.assertEqual(
            evaluate_facts("1075", facts("GRATED COTIJA WHOLE MILK CHEESE, MEXICAN STYLE PARMESAN", "Cheese")).status,
            "reject",
        )
        self.assertEqual(
            evaluate_facts("1075", facts("GRATED PARMESAN CHEESE, PARMESAN", "Cheese")).status,
            "accept",
        )

    def test_plain_cheddar_contract_rejects_blends(self) -> None:
        self.assertEqual(contract_source_module("33342"), "esha_contracts")
        self.assertEqual(
            evaluate_facts("33342", facts("CHEDDAR & MOZZARELLA BLEND SHREDDED CHEESE", "Cheese")).status,
            "reject",
        )
        self.assertEqual(
            evaluate_facts("33342", facts("PLANT-BASED CHEDDAR CHEESE", "Cheese")).status,
            "reject",
        )
        self.assertEqual(
            evaluate_facts("33342", facts("ENGLISH CHEDDAR CHEESE BLENDED WITH ALE", "Cheese")).status,
            "reject",
        )
        self.assertEqual(
            evaluate_facts("33342", facts("SHARP CHEDDAR CHEESE", "Cheese")).status,
            "reject",
        )
        self.assertEqual(
            evaluate_facts("33342", facts("CHEDDAR CHEESE", "Cheese")).status,
            "accept",
        )

    def test_shredded_cheddar_contract_rejects_blends_and_requires_shredded_form(self) -> None:
        self.assertEqual(contract_source_module("1008"), "esha_contracts")
        self.assertEqual(
            evaluate_facts("1008", facts("CHEDDAR JACK SHREDDED CHEESE A BLEND OF CHEDDAR & MONTEREY JACK CHEESES", "Cheese")).status,
            "reject",
        )
        self.assertEqual(
            evaluate_facts("1008", facts("MEDIUM CHEDDAR DELI STYLE SLICED CHEESE", "Cheese")).status,
            "reject",
        )
        self.assertEqual(
            evaluate_facts("1008", facts("PLANT-BASED CHEDDAR STYLE SHREDS CHEESE", "Cheese")).status,
            "reject",
        )
        self.assertEqual(
            evaluate_facts("1008", facts("SHREDDED CHEDDAR CHEESE", "Cheese")).status,
            "accept",
        )


if __name__ == "__main__":
    unittest.main()
