import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from graph.queries.score_suspicion import score_all  # noqa: E402


def _vec(*xs):
    v = np.array(xs, dtype=np.float32)
    return v / np.linalg.norm(v)


def _fixture():
    # Two clean clusters: milk (vecs near +x), popcorn (vecs near +y).
    embeddings = {
        "Product:milk_a":   _vec(1.0, 0.05, 0.0),
        "Product:milk_b":   _vec(0.95, 0.0, 0.05),
        "Product:popcorn":  _vec(0.05, 1.0, 0.0),
        "ESHACode:1004":    _vec(0.98, 0.02, 0.0),   # milk
        "ESHACode:5500":    _vec(0.02, 0.98, 0.0),   # popcorn
        "ProductCategory:Milk":    _vec(0.97, 0.0, 0.03),
        "ProductCategory:Snacks":  _vec(0.0, 0.97, 0.03),
    }
    products = pd.DataFrame([
        # popcorn is mis-mapped to milk code 1004; everything else is correct
        {"gtin_upc": "milk_a",  "assigned_code": "1004", "category": "Milk",
         "description": "WHOLE MILK"},
        {"gtin_upc": "milk_b",  "assigned_code": "1004", "category": "Milk",
         "description": "2% MILK"},
        {"gtin_upc": "popcorn", "assigned_code": "1004", "category": "Snacks",
         "description": "BUTTERED POPCORN"},
    ])
    return embeddings, products


class ScoreAllTest(unittest.TestCase):
    def test_correctly_mapped_product_has_low_suspicion(self):
        embeddings, products = _fixture()
        out = score_all(embeddings, products)
        row = out.loc[out["gtin_upc"] == "milk_a"].iloc[0]
        self.assertLess(row["suspicion"], 0.3)
        self.assertEqual(row["disagreement_kind"], "agree")

    def test_wrong_label_product_is_flagged(self):
        embeddings, products = _fixture()
        out = score_all(embeddings, products)
        row = out.loc[out["gtin_upc"] == "popcorn"].iloc[0]
        self.assertGreater(row["suspicion"], 0.7)
        self.assertEqual(row["disagreement_kind"], "wrong_label")
        self.assertEqual(row["text_view_code"], "5500")
        self.assertEqual(row["top1_code"], "5500")

    def test_assigned_rank_is_position_in_text_view_ranking(self):
        embeddings, products = _fixture()
        out = score_all(embeddings, products)
        row = out.loc[out["gtin_upc"] == "popcorn"].iloc[0]
        # popcorn assigned to milk code 1004, but 5500 is closer
        self.assertEqual(row["assigned_rank"], 2)


if __name__ == "__main__":
    unittest.main()
