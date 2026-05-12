import csv
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import surface_lab_calculator as lab  # noqa: E402


class SurfaceLabDataSourceTests(unittest.TestCase):
    def setUp(self):
        self.original_surface = lab.SURFACE_CSV
        self.original_product_map = lab.PRODUCT_ESHA_MAP_CSV
        self.original_retail_bridge = lab.RETAIL_SURFACE_BRIDGE_CSV

    def tearDown(self):
        lab.configure_data_sources(
            surface_csv=self.original_surface,
            product_esha_map_csv=self.original_product_map,
            retail_surface_bridge_csv=self.original_retail_bridge,
        )

    def test_configured_surface_and_product_map_feed_calculator(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            surface_csv = tmp / "surface.csv"
            product_map_csv = tmp / "product_map.csv"
            retail_bridge_csv = tmp / "retail_bridge.csv"

            with surface_csv.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=[
                        "canonical_surface",
                        "canonical_normalized",
                        "canonical_shopping_item",
                        "record_type",
                        "nutrition_match_state",
                        "nutrition_code_type",
                        "sr28_code",
                        "fndds_code",
                        "esha_code",
                        "esha_description",
                    ],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "canonical_surface": "test sauce",
                        "canonical_normalized": "test sauce",
                        "canonical_shopping_item": "test sauce",
                        "record_type": "ingredient",
                        "esha_code": "999001",
                        "esha_description": "Sauce, test",
                    }
                )

            with product_map_csv.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=[
                        "gtin_upc",
                        "product_description",
                        "branded_food_category",
                        "brand_owner",
                        "brand_name",
                        "best_esha_code",
                        "score_num",
                    ],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "gtin_upc": "111",
                        "product_description": "TEST SAUCE",
                        "branded_food_category": "Condiments",
                        "brand_owner": "ACME",
                        "best_esha_code": "999001",
                        "score_num": "10",
                    }
                )
                writer.writerow(
                    {
                        "gtin_upc": "222",
                        "product_description": "WRONG CANDY",
                        "branded_food_category": "Candy",
                        "brand_owner": "ACME",
                        "best_esha_code": "999001",
                        "score_num": "99",
                    }
                )

            with retail_bridge_csv.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=[
                        "retail_source",
                        "upc",
                        "name",
                        "search_term",
                        "canonical_match_status",
                        "canonical_surface",
                        "canonical_normalized",
                        "canonical_shopping_item",
                        "product_query",
                    ],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "retail_source": "walmart",
                        "upc": "333",
                        "name": "TEST SAUCE",
                        "search_term": "test sauce",
                        "canonical_match_status": "assigned",
                        "canonical_surface": "test sauce",
                        "canonical_normalized": "test sauce",
                        "canonical_shopping_item": "test sauce",
                        "product_query": "test sauce",
                    }
                )

            lab.configure_data_sources(
                surface_csv=surface_csv,
                product_esha_map_csv=product_map_csv,
                retail_surface_bridge_csv=retail_bridge_csv,
            )
            result = lab.calculate_lab(display="test sauce", item="test sauce", grams=100)

            self.assertEqual(result.canonical_name, "test sauce")
            self.assertEqual([p.gtin_upc for p in result.products], ["333"])
            self.assertEqual(result.products[0].source, "retail_surface_bridge:walmart")

    def test_retail_bridge_category_does_not_create_identity_overlap(self):
        wrong = lab.LabProduct(
            gtin_upc="111",
            description="Garlic",
            brand_name="kroger",
            category="onion",
            source="retail_surface_bridge:kroger",
        )
        right = lab.LabProduct(
            gtin_upc="222",
            description="Yellow Onion",
            brand_name="kroger",
            category="",
            source="retail_surface_bridge:kroger",
        )

        accepted, rejected = lab._review_products([wrong, right], "onion")

        self.assertEqual([p.gtin_upc for p in accepted], ["222"])
        self.assertEqual(rejected[0].reason, "missing_onion_identity")

    def test_plain_mayo_and_pumpkin_pie_mix_reject_flavored_or_prepared_products(self):
        plain_mayo = lab.LabProduct(
            gtin_upc="111",
            description="Real Mayonnaise",
            brand_name="walmart",
            category="Salad Dressing & Mayonnaise",
            source="fts_search",
        )
        garlic_mayo = lab.LabProduct(
            gtin_upc="222",
            description="Roasted Garlic Mayonnaise",
            brand_name="walmart",
            category="Salad Dressing & Mayonnaise",
            source="fts_search",
        )
        canned_pumpkin_pie_mix = lab.LabProduct(
            gtin_upc="333",
            description="Organic Pumpkin Pie Mix",
            brand_name="walmart",
            category="Canned Vegetables",
            source="fts_search",
        )
        pumpkin_scone_mix = lab.LabProduct(
            gtin_upc="444",
            description="Pumpkin Pie Spice Scone Mix",
            brand_name="walmart",
            category="Cake, Cookie & Cupcake Mixes",
            source="fts_search",
        )

        mayo, rejected_mayo = lab._review_products([plain_mayo, garlic_mayo], "mayonnaise")
        pumpkin, rejected_pumpkin = lab._review_products(
            [canned_pumpkin_pie_mix, pumpkin_scone_mix],
            "pumpkin pie mix",
        )

        self.assertEqual([p.gtin_upc for p in mayo], ["111"])
        self.assertEqual(rejected_mayo[0].reason, "not_plain_mayonnaise:garlic")
        self.assertEqual([p.gtin_upc for p in pumpkin], ["333"])
        self.assertEqual(rejected_pumpkin[0].reason, "not_plain_pumpkin_pie_mix:cake/cookie/scone/spice")

    def test_generic_milk_buys_whole_milk_not_lowfat_or_lactose_free(self):
        lowfat = lab.LabProduct(
            gtin_upc="111",
            description="Organic Lactose Free 2% Reduced Fat Milk",
            brand_name="walmart",
            category="Milk",
            source="retail_surface_bridge:walmart",
        )
        whole = lab.LabProduct(
            gtin_upc="222",
            description="Whole Milk",
            brand_name="walmart",
            category="Milk",
            source="retail_surface_bridge:walmart",
        )

        accepted, rejected = lab._review_products([lowfat, whole], "milk")

        self.assertEqual([p.gtin_upc for p in accepted], ["222"])
        self.assertEqual(rejected[0].reason, "not_whole_milk:2%/fat/free/lactose/reduced")

    def test_recipe_smoke_specific_product_filters(self):
        buttermilk_dressing = lab.LabProduct(
            gtin_upc="111",
            description="Creamy Buttermilk Ranch Dressing",
            brand_name="kroger",
            category="",
            source="retail_surface_bridge:kroger",
        )
        buttermilk_muffins = lab.LabProduct(
            gtin_upc="112",
            description="Thomas' Buttermilk English Muffins",
            brand_name="kroger",
            category="",
            source="retail_surface_bridge:kroger",
        )
        liquid_buttermilk = lab.LabProduct(
            gtin_upc="222",
            description="Kroger Cultured 1% Lowfat Buttermilk Quart",
            brand_name="kroger",
            category="",
            source="retail_surface_bridge:kroger",
        )
        flavored_cream_cheese = lab.LabProduct(
            gtin_upc="333",
            description="Great Value Brown Sugar & Cinnamon Cream Cheese",
            brand_name="walmart",
            category="",
            source="retail_surface_bridge:walmart",
        )
        plain_cream_cheese = lab.LabProduct(
            gtin_upc="444",
            description="Kroger Original Cream Cheese",
            brand_name="kroger",
            category="",
            source="retail_surface_bridge:kroger",
        )
        orange_mango = lab.LabProduct(
            gtin_upc="555",
            description="Kroger Orange Mango Fruit Juice Drink",
            brand_name="kroger",
            category="",
            source="retail_surface_bridge:kroger",
        )
        plain_orange_juice = lab.LabProduct(
            gtin_upc="666",
            description="Simply Orange Orange Juice",
            brand_name="walmart",
            category="",
            source="retail_surface_bridge:walmart",
        )
        canned_orange = lab.LabProduct(
            gtin_upc="777",
            description="Del Monte Mandarin Oranges in 100% Fruit Juice",
            brand_name="walmart",
            category="",
            source="retail_surface_bridge:walmart",
        )
        fresh_orange = lab.LabProduct(
            gtin_upc="888",
            description="Fresh Cara Cara Oranges, 3 lb Bag",
            brand_name="walmart",
            category="",
            source="retail_surface_bridge:walmart",
        )

        buttermilk, rejected_buttermilk = lab._review_products([buttermilk_dressing, buttermilk_muffins, liquid_buttermilk], "buttermilk")
        cream_cheese, rejected_cream_cheese = lab._review_products([flavored_cream_cheese, plain_cream_cheese], "cream cheese")
        orange_juice, rejected_orange_juice = lab._review_products([orange_mango, plain_orange_juice], "orange juice")
        orange, rejected_orange = lab._review_products([canned_orange, fresh_orange], "orange")

        self.assertEqual([p.gtin_upc for p in buttermilk], ["222"])
        self.assertEqual(rejected_buttermilk[0].reason, "not_plain_buttermilk:dressing/ranch")
        self.assertEqual(rejected_buttermilk[1].reason, "not_plain_buttermilk:english/muffins")
        self.assertEqual([p.gtin_upc for p in cream_cheese], ["444"])
        self.assertEqual(rejected_cream_cheese[0].reason, "not_plain_cream_cheese:brown/cinnamon/sugar")
        self.assertEqual([p.gtin_upc for p in orange_juice], ["666"])
        self.assertEqual(rejected_orange_juice[0].reason, "not_plain_orange_juice:drink/mango")
        self.assertEqual([p.gtin_upc for p in orange], ["888"])
        self.assertEqual(rejected_orange[0].reason, "not_plain_fresh_orange:juice/mandarin")

    def test_plant_milk_filters_prepared_drinks_and_yogurts(self):
        plain_oat = lab.LabProduct(
            gtin_upc="111",
            description="Oatly Dairy-Free Shelf-Stable Original Oat Milk",
            brand_name="kroger",
            category="",
            source="retail_surface_bridge:kroger",
        )
        coconut_yogurt = lab.LabProduct(
            gtin_upc="222",
            description="So Delicious Raspberry Dairy Free Vegan Coconut Milk Yogurt Cup",
            brand_name="kroger",
            category="",
            source="retail_surface_bridge:kroger",
        )
        coconut_drink = lab.LabProduct(
            gtin_upc="333",
            description="Kuii Drinks Coconut Milk with Nata de Coco",
            brand_name="kroger",
            category="",
            source="retail_surface_bridge:kroger",
        )

        oat, rejected_oat = lab._review_products([plain_oat], "oat milk")
        coconut, rejected_coconut = lab._review_products([coconut_yogurt, coconut_drink], "coconut milk")

        self.assertEqual([p.gtin_upc for p in oat], ["111"])
        self.assertEqual(rejected_oat, [])
        self.assertEqual(coconut, [])
        self.assertEqual(rejected_coconut[0].reason, "not_plain_coconut_milk:yogurt")
        self.assertEqual(rejected_coconut[1].reason, "not_plain_coconut_milk:drinks/nata")

    def test_fndds_cheese_surfaces_preserve_cheese_identity_before_approved_rules(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            surface_csv = tmp / "surface.csv"
            product_map_csv = tmp / "product_map.csv"
            retail_bridge_csv = tmp / "retail_bridge.csv"

            with surface_csv.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=[
                        "canonical_surface",
                        "canonical_normalized",
                        "canonical_shopping_item",
                        "record_type",
                        "nutrition_match_state",
                        "nutrition_code_type",
                        "sr28_code",
                        "fndds_code",
                        "esha_code",
                        "esha_description",
                    ],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "canonical_surface": "swiss cheese",
                        "canonical_normalized": "swiss cheese",
                        "canonical_shopping_item": "swiss cheese",
                        "record_type": "ingredient",
                        "esha_code": "1280",
                        "esha_description": "Cheese, swiss",
                    }
                )
                writer.writerow(
                    {
                        "canonical_surface": "provolone cheese",
                        "canonical_normalized": "provolone cheese",
                        "canonical_shopping_item": "provolone cheese",
                        "record_type": "ingredient",
                        "esha_code": "1258",
                        "esha_description": "Cheese, provolone",
                    }
                )
                writer.writerow(
                    {
                        "canonical_surface": "cheddar cheese",
                        "canonical_normalized": "cheddar cheese",
                        "canonical_shopping_item": "cheddar cheese",
                        "record_type": "ingredient",
                        "esha_code": "633",
                        "esha_description": "Cheese, cheddar",
                    }
                )

            product_map_csv.write_text("gtin_upc,product_description,best_esha_code,score_num\n", encoding="utf-8")
            retail_bridge_csv.write_text(
                "retail_source,upc,name,search_term,canonical_match_status,canonical_surface,canonical_normalized,canonical_shopping_item,product_query\n",
                encoding="utf-8",
            )

            lab.configure_data_sources(
                surface_csv=surface_csv,
                product_esha_map_csv=product_map_csv,
                retail_surface_bridge_csv=retail_bridge_csv,
            )

            self.assertEqual(lab.calculate_lab(display="Cheese, swiss", item="Cheese, swiss").canonical_name, "swiss cheese")
            self.assertEqual(
                lab.calculate_lab(display="Cheese, provolone", item="Cheese, provolone").canonical_name,
                "provolone cheese",
            )


if __name__ == "__main__":
    unittest.main()
