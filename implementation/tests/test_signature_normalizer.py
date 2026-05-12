import unittest
from implementation.canonical_signature.normalizer import normalize


class NormalizerTests(unittest.TestCase):
    def test_lowercases(self):
        self.assertEqual(normalize("APPLES"), "apples")

    def test_preserves_commas(self):
        self.assertEqual(normalize("NATURE'S PLACE, ORGANIC APPLES"),
                         "natures place, organic apples")

    def test_strips_apostrophes_and_periods(self):
        self.assertEqual(normalize("McDonald's Inc."), "mcdonalds inc")

    def test_expands_abbreviations(self):
        self.assertEqual(normalize("ORG. APPLES W/ CINNAMON"),
                         "organic apples with cinnamon")

    def test_collapses_whitespace(self):
        self.assertEqual(normalize("  apple    sauce  "), "apple sauce")

    def test_unicode_nfkd(self):
        self.assertEqual(normalize("CAFÉ"), "cafe")

    def test_ampersand_kept_only_when_word_separator(self):
        self.assertEqual(normalize("PIECES & STEMS"), "pieces and stems")
        self.assertEqual(normalize("A&W ROOT BEER"), "a&w root beer")
