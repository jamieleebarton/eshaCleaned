import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from graph.queries.embed_nodes import build_node_texts  # noqa: E402


class BuildNodeTextsTest(unittest.TestCase):
    def _fake_conn(self, query_results):
        conn = MagicMock()
        def execute(q, _params=None):
            for key, rows in query_results.items():
                if key in q:
                    result = MagicMock()
                    result.has_next.side_effect = [True] * len(rows) + [False]
                    result.get_next.side_effect = [list(r) for r in rows]
                    return result
            raise AssertionError(f"no fake result for: {q}")
        conn.execute.side_effect = execute
        return conn

    def test_product_text_concatenates_description_and_tokens(self):
        conn = self._fake_conn({
            "(p:Product)":         [("0001", "WHOLE MILK 1 GAL", ["milk", "whole", "gallon"])],
            "(e:ESHACode)":        [],
            "(c:ProductCategory)": [],
            "(c:ESHACategory)":    [],
        })
        texts = build_node_texts(conn)
        self.assertEqual(texts["Product:0001"], "WHOLE MILK 1 GAL milk whole gallon")

    def test_esha_code_text_concatenates_code_and_description(self):
        conn = self._fake_conn({
            "(p:Product)":         [],
            "(e:ESHACode)":        [("1004", "Milk, fluid, whole")],
            "(c:ProductCategory)": [],
            "(c:ESHACategory)":    [],
        })
        texts = build_node_texts(conn)
        self.assertEqual(texts["ESHACode:1004"], "1004 Milk, fluid, whole")

    def test_category_texts_use_name(self):
        conn = self._fake_conn({
            "(p:Product)":         [],
            "(e:ESHACode)":        [],
            "(c:ProductCategory)": [("Milk",)],
            "(c:ESHACategory)":    [("dairy",)],
        })
        texts = build_node_texts(conn)
        self.assertEqual(texts["ProductCategory:Milk"], "Milk")
        self.assertEqual(texts["ESHACategory:dairy"], "dairy")


import tempfile
import numpy as np
from unittest.mock import patch
from graph.queries.embed_nodes import embed_all, _content_hash  # noqa: E402


class EmbedAllCacheTest(unittest.TestCase):
    def _conn(self):
        return MagicMock()  # only used via build_node_texts, which we patch

    def test_cache_hit_skips_model_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / "emb.npz"
            texts = {"Product:1": "milk", "ESHACode:1004": "1004 milk fluid"}
            digest = _content_hash("test-model", texts)
            ids = sorted(texts)
            np.savez(
                cache,
                ids=np.array(ids),
                vectors=np.zeros((len(ids), 4), dtype=np.float32),
                digest=np.array(digest),
            )
            with patch("graph.queries.embed_nodes.build_node_texts", return_value=texts):
                with patch("sentence_transformers.SentenceTransformer") as model_cls:
                    out = embed_all(self._conn(), model_name="test-model", cache_path=cache)
                    model_cls.assert_not_called()
            self.assertEqual(set(out), {"Product:1", "ESHACode:1004"})
            self.assertEqual(out["Product:1"].shape, (4,))

    def test_cache_miss_invokes_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / "emb.npz"
            texts = {"Product:1": "milk"}
            with patch("graph.queries.embed_nodes.build_node_texts", return_value=texts):
                fake_model = MagicMock()
                fake_model.encode.return_value = np.array([[0.1, 0.2, 0.3, 0.4]], dtype=np.float32)
                with patch("sentence_transformers.SentenceTransformer", return_value=fake_model):
                    out = embed_all(self._conn(), model_name="test-model", cache_path=cache)
                    fake_model.encode.assert_called_once()
            self.assertTrue(cache.exists())
            np.testing.assert_array_almost_equal(out["Product:1"], [0.1, 0.2, 0.3, 0.4], decimal=5)


if __name__ == "__main__":
    unittest.main()
