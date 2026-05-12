import unittest
from implementation.canonical_signature.embedding_matcher import EmbeddingMatcher


class EmbeddingMatcherTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.corpus = [
            ("ice_cream",       "ice cream"),
            ("frozen_yogurt",   "frozen yogurt"),
            ("agave_nectar",    "agave nectar"),
            ("honey",           "honey"),
            ("apple_raw",       "apples raw"),
            ("bell_pepper",     "bell pepper"),
            ("sweet_pepper",    "sweet pepper"),
        ]
        cls.matcher = EmbeddingMatcher.fit(cls.corpus)

    def test_semantic_neighbors_pulled_into_top_k(self):
        # 'frozen dessert' should be near ice cream / frozen yogurt
        results = self.matcher.rerank("frozen dessert", candidate_ids=[i for i, _ in self.corpus], k=3)
        ids = [r[0] for r in results]
        self.assertTrue("ice_cream" in ids or "frozen_yogurt" in ids,
                        f"expected dessert neighbor in top-3, got {ids}")

    def test_rerank_only_considers_provided_candidates(self):
        results = self.matcher.rerank("frozen dessert",
                                      candidate_ids=["agave_nectar", "honey"], k=2)
        ids = {r[0] for r in results}
        self.assertEqual(ids, {"agave_nectar", "honey"})
