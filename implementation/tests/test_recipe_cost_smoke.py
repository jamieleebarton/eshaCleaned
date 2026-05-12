import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from run_recipe_cost_smoke import (  # noqa: E402
    RetailOffer,
    _is_no_purchase_surface,
    _normalized_package_grams,
    _ranked_offers,
    _shopping_needed_grams,
)


class RecipeCostSmokeTests(unittest.TestCase):
    def test_normalizes_shell_egg_carton_package_grams(self):
        self.assertEqual(
            _normalized_package_grams(
                name="Marketside Large Cage-Free Brown Eggs, 12 Count",
                search_term="egg",
                canonical_surface="egg",
                grams=12000.0,
            ),
            600.0,
        )
        self.assertEqual(
            _normalized_package_grams(
                name="Kroger Grade A Large Eggs",
                search_term="egg",
                canonical_surface="egg",
                grams=58.96696,
            ),
            600.0,
        )

    def test_leaves_non_egg_packages_alone(self):
        self.assertEqual(
            _normalized_package_grams(
                name="Great Value All-Purpose Flour",
                search_term="flour",
                canonical_surface="all purpose flour",
                grams=907.2,
            ),
            907.2,
        )

    def test_ranks_package_options_by_checkout_cost(self):
        products = [
            {
                "source": "retail_surface_bridge:walmart",
                "gtin_upc": "194346055227",
                "description": "Great Value Homestyle Beef Flavored Gravy, 12 oz Glass Jar",
                "reason": "contains_required_canonical_terms",
            },
            {
                "source": "retail_surface_bridge:walmart",
                "gtin_upc": "13000797702",
                "description": "Heinz HomeStyle Beef Gravy Value Size, 18 oz Jar",
                "reason": "contains_required_canonical_terms",
            },
        ]
        offers = {
            (
                "retail_surface_bridge:walmart",
                "194346055227",
            ): RetailOffer(
                retail_source="walmart",
                upc="194346055227",
                name="Great Value Homestyle Beef Flavored Gravy, 12 oz Glass Jar",
                grams=340.2,
                cents=147,
                cpg=1.47 / 340.2,
                search_term="beef gravy",
                canonical_surface="beef gravy",
                canonical_shopping_item="beef gravy",
            ),
            (
                "retail_surface_bridge:walmart",
                "13000797702",
            ): RetailOffer(
                retail_source="walmart",
                upc="13000797702",
                name="Heinz HomeStyle Beef Gravy Value Size, 18 oz Jar",
                grams=510.3,
                cents=218,
                cpg=2.18 / 510.3,
                search_term="beef gravy",
                canonical_surface="beef gravy",
                canonical_shopping_item="beef gravy",
            ),
        }

        ranked = _ranked_offers(products, offers, "walmart", 1893.0)

        self.assertEqual(ranked[0]["upc"], "13000797702")
        self.assertEqual(ranked[0]["packages"], 4)
        self.assertEqual(ranked[1]["upc"], "194346055227")
        self.assertEqual(ranked[1]["packages"], 6)

    def test_adjusts_cooked_rice_to_dry_purchase_grams(self):
        grams, note = _shopping_needed_grams(
            display="7 gallons cooked rice",
            item="rice",
            lab={"shopping_canonical": "rice", "canonical_name": "rice"},
            recipe_grams=26496.0,
        )

        self.assertEqual(grams, 8832.0)
        self.assertIn("cooked rice", note)

    def test_leaves_dried_legume_purchase_grams_alone(self):
        grams, note = _shopping_needed_grams(
            display="2 lbs dried split peas, soaked and cooked",
            item="dried split peas",
            lab={"shopping_canonical": "split pea", "canonical_name": "split pea"},
            recipe_grams=907.0,
        )

        self.assertEqual(grams, 907.0)
        self.assertEqual(note, "")

    def test_treats_plain_temperature_water_as_no_purchase_only(self):
        self.assertTrue(_is_no_purchase_surface("1 cup boiling water"))
        self.assertTrue(_is_no_purchase_surface("hot water"))
        self.assertFalse(_is_no_purchase_surface("coconut water"))
        self.assertFalse(_is_no_purchase_surface("rose water"))


if __name__ == "__main__":
    unittest.main()
