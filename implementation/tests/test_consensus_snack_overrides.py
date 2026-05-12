import importlib.util
import sys
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
V2 = REPO / "retail_mapper" / "v2"
SCRIPT = V2 / "build_consensus_snack_taxonomy_overrides.py"

sys.path.insert(0, str(V2))
spec = importlib.util.spec_from_file_location("build_consensus_snack_taxonomy_overrides", SCRIPT)
snack = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(snack)


def row(**values):
    base = {
        "fdc_id": "1",
        "title": "",
        "branded_food_category": "Chips, Pretzels & Snacks",
        "canonical_label": "",
        "category_path_fixed": "Snack > Veggie Snacks",
        "product_identity_fixed": "Veggie Straws",
        "canonical_path": "Snack > Veggie Snacks > Veggie Straws",
        "retail_leaf_path": "Snack > Veggie Snacks > Veggie Straws",
        "modifier": "",
        "fndds_desc": "",
    }
    base.update(values)
    return base


class ConsensusSnackOverrideTests(unittest.TestCase):
    def test_green_peas_are_not_veggie_straws(self):
        override = snack.build_override(
            row(
                title="SPICY SRIRACHA FLAVORED CHILI GARLIC FLAVORED GREEN PEAS",
                modifier="Spicy Sriracha Chili Garlic",
                retail_leaf_path="Snack > Veggie Snacks > Veggie Straws > Spicy Sriracha Chili Garlic",
            )
        )

        self.assertEqual("Snack > Veggie Snacks", override["category_path_fixed"])
        self.assertEqual("Green Pea Snacks", override["product_identity_fixed"])
        self.assertEqual("Spicy Sriracha Chili Garlic", override["modifier"])

    def test_actual_veggie_straws_are_kept(self):
        self.assertIsNone(
            snack.build_override(
                row(
                    title="GARDEN VEGGIE STRAWS, SEA SALT",
                    modifier="Plain",
                    retail_leaf_path="Snack > Veggie Snacks > Veggie Straws > Plain",
                )
            )
        )

    def test_funyuns_route_to_onion_rings(self):
        override = snack.build_override(
            row(
                title="FUNYUNS, ONION FLAVORED RINGS, FLAMIN' HOT",
                modifier="Onion Hot",
                retail_leaf_path="Snack > Veggie Snacks > Veggie Straws > Onion Hot",
            )
        )

        self.assertEqual("Snack", override["category_path_fixed"])
        self.assertEqual("Onion Rings", override["product_identity_fixed"])
        self.assertEqual("Hot", override["modifier"])

    def test_seaweed_snack_routes_to_seaweed_snacks(self):
        override = snack.build_override(
            row(
                title="ROASTED SEAWEED SNACK, SEA SALT",
                modifier="Seaweed",
                retail_leaf_path="Snack > Veggie Snacks > Veggie Straws > Seaweed",
            )
        )

        self.assertEqual("Snack", override["category_path_fixed"])
        self.assertEqual("Seaweed Snacks", override["product_identity_fixed"])
        self.assertEqual("<blank>", override["modifier"])


if __name__ == "__main__":
    unittest.main()
