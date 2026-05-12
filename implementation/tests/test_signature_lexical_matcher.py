import unittest
from implementation.canonical_signature.lexical_matcher import LexicalMatcher


class LexicalMatcherTests(unittest.TestCase):
    def setUp(self):
        self.corpus = [
            ("apple_raw",       "apples raw"),
            ("apple_sliced",    "apples sliced"),
            ("applesauce",      "applesauce"),
            ("applesauce_cin",  "applesauce cinnamon"),
            ("agave_nectar",    "agave nectar"),
            ("ice_cream_van",   "ice cream vanilla"),
            ("ice_cream_choc",  "ice cream chocolate"),
        ]
        self.matcher = LexicalMatcher.fit(self.corpus)

    def test_top_match_for_exact_input(self):
        results = self.matcher.match("agave nectar", k=3)
        self.assertEqual(results[0][0], "agave_nectar")
        self.assertGreater(results[0][1], 0.9)

    def test_top_match_for_morphological_variant(self):
        # 'apple sauce' (split) should match 'applesauce' via char n-grams
        results = self.matcher.match("apple sauce", k=3)
        ids = [r[0] for r in results]
        self.assertIn("applesauce", ids[:2])

    def test_returns_top_k_sorted_descending(self):
        results = self.matcher.match("apples", k=3)
        self.assertEqual(len(results), 3)
        scores = [r[1] for r in results]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_zero_score_when_residual_is_empty(self):
        results = self.matcher.match("", k=3)
        self.assertEqual(results, [])
