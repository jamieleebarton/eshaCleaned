import sys
import unittest
from pathlib import Path


ROOT = Path("/Users/jamiebarton/Desktop/esha_audit_bundle")
V2 = ROOT / "retail_mapper" / "v2"
if str(V2) not in sys.path:
    sys.path.insert(0, str(V2))

import build_semantic_taxonomy_tree as tree_builder  # noqa: E402


class SemanticTaxonomyTreeTests(unittest.TestCase):
    def test_builds_category_product_and_facet_nodes(self) -> None:
        rows = [
            {
                "fdc_id": "2500391",
                "gtin_upc": "41570054185",
                "title": "UNSWEETENED CHOCOLATE ALMONDMILK",
                "canonical_path": "Beverage > Plant Milk > Almond Milk",
                "canonical_label": "Almond Milk (Chocolate, Unsweetened)",
                "retail_type": "single",
                "review_flags": "",
                "variant": "",
                "flavor": "chocolate",
                "form_texture_cut": "",
                "processing_storage": "",
                "claims": "unsweetened",
                "attributes_json": "{}",
            },
            {
                "fdc_id": "2485358",
                "gtin_upc": "99482493769",
                "title": "UNSWEETENED CHOCOLATE ORGANIC ALMONDMILK",
                "canonical_path": "Beverage > Plant Milk > Almond Milk",
                "canonical_label": "Almond Milk (Chocolate, Unsweetened, Organic)",
                "retail_type": "single",
                "review_flags": "",
                "variant": "",
                "flavor": "chocolate",
                "form_texture_cut": "",
                "processing_storage": "",
                "claims": "unsweetened | organic",
                "attributes_json": "{}",
            },
        ]

        nodes, edges, assignments = tree_builder.build_from_rows(rows)
        by_path = {node.path: node for node in nodes.values()}

        self.assertEqual(len(assignments), 2)
        self.assertIn("Beverage", by_path)
        self.assertIn("Beverage > Plant Milk", by_path)
        self.assertIn("Beverage > Plant Milk > Almond Milk", by_path)
        self.assertIn("Beverage > Plant Milk > Almond Milk > @flavor", by_path)
        self.assertIn("Beverage > Plant Milk > Almond Milk > @flavor > chocolate", by_path)
        self.assertIn("Beverage > Plant Milk > Almond Milk > @claims > unsweetened", by_path)
        self.assertIn("Beverage > Plant Milk > Almond Milk > @claims > organic", by_path)
        self.assertEqual(by_path["Beverage > Plant Milk > Almond Milk"].product_count, 2)
        self.assertEqual(by_path["Beverage > Plant Milk > Almond Milk > @flavor > chocolate"].product_count, 2)
        self.assertEqual(by_path["Beverage > Plant Milk > Almond Milk > @claims > organic"].product_count, 1)
        self.assertGreater(len(edges), 0)


if __name__ == "__main__":
    unittest.main()

