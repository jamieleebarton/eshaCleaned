import importlib.util
import sys
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
V2 = REPO / "retail_mapper" / "v2"
SCRIPT = V2 / "build_consensus_shape_taxonomy_overrides.py"

sys.path.insert(0, str(V2))
spec = importlib.util.spec_from_file_location("build_consensus_shape_taxonomy_overrides", SCRIPT)
shape = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(shape)


def row(**values):
    base = {
        "fdc_id": "1",
        "title": "",
        "branded_food_category": "Pasta by Shape & Type",
        "product_identity_fixed": "Macaroni",
        "canonical_label": "",
        "variant": "",
        "form_texture_cut": "",
        "canonical_path": "Pantry > Pasta > Macaroni > Shells",
        "retail_leaf_path": "Pantry > Pasta > Macaroni > Shells",
        "modifier": "",
        "fndds_desc": "",
        "sr28_desc": "",
        "esha_desc": "",
        "matched_key": "",
    }
    base.update(values)
    return base


class ConsensusShapeOverrideTests(unittest.TestCase):
    def test_orzo_is_not_nested_under_macaroni_shells(self):
        override = shape.build_override(
            row(
                title="ORGANIC MACARONI PRODUCT, ORZO",
                retail_leaf_path="Pantry > Pasta > Macaroni > Shells > Orzo > Organic",
                modifier="Orzo > Organic",
            )
        )

        self.assertEqual("Pantry > Pasta", override["category_path_fixed"])
        self.assertEqual("Orzo", override["product_identity_fixed"])
        self.assertEqual("Organic", override["modifier"])

    def test_shells_keep_shell_identity_and_size_modifier(self):
        override = shape.build_override(
            row(
                title="MEDIUM SHELLS ENRICHED MACARONI PRODUCT",
                retail_leaf_path="Pantry > Pasta > Macaroni > Shells > Medium",
                modifier="Medium",
            )
        )

        self.assertEqual("Shells", override["product_identity_fixed"])
        self.assertEqual("Medium", override["modifier"])

    def test_plain_generic_macaroni_only_removes_bad_shell_parent(self):
        override = shape.build_override(
            row(
                title="MACARONI PRODUCT",
                retail_leaf_path="Pantry > Pasta > Macaroni > Shells > Plain",
                modifier="Plain",
            )
        )

        self.assertEqual("Macaroni", override["product_identity_fixed"])
        self.assertEqual("<blank>", override["modifier"])

    def test_spaghetti_linguine_stack_uses_linguine_identity(self):
        override = shape.build_override(
            row(
                title="ORGANIC SPAGHETTI PRODUCT, LINGUINE",
                canonical_path="Pantry > Pasta > Spaghetti > Linguine",
                retail_leaf_path="Pantry > Pasta > Spaghetti > Linguine > Organic",
                modifier="Linguine > Organic",
            )
        )

        self.assertEqual("Pantry > Pasta", override["category_path_fixed"])
        self.assertEqual("Linguine", override["product_identity_fixed"])
        self.assertEqual("Organic", override["modifier"])

    def test_title_shape_beats_stale_reference_shape(self):
        override = shape.build_override(
            row(
                title="ORZI MACARONI PRODUCT",
                retail_leaf_path="Pantry > Pasta > Macaroni > Shells > Plain",
                modifier="Plain",
                sr28_desc="Macaroni, elbow, dry",
            )
        )

        self.assertEqual("Orzo", override["product_identity_fixed"])


if __name__ == "__main__":
    unittest.main()
