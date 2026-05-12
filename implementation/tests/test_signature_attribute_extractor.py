import unittest
from implementation.canonical_signature.attribute_extractor import (
    extract_attributes, ExtractionResult,
)
from implementation.canonical_signature.vocabularies import (
    FLUFF_TOKENS, SEED_FLAVOR_TOKENS,
)


class AttributeExtractorTests(unittest.TestCase):
    def setUp(self):
        self.form_vocab = frozenset({"sliced", "whole", "diced", "liquid", "powder", "chopped"})
        self.state_vocab = frozenset({"raw", "frozen", "fresh", "cooked", "dried"})
        self.style_vocab = frozenset({"organic", "kosher"})
        self.packaging_vocab = frozenset({"packets", "tray", "cup", "bag"})

    def _extract(self, text):
        return extract_attributes(
            text,
            fluff=FLUFF_TOKENS,
            flavors=SEED_FLAVOR_TOKENS,
            forms=self.form_vocab,
            states=self.state_vocab,
            styles=self.style_vocab,
            packaging=self.packaging_vocab,
        )

    def test_strips_fluff_and_returns_residual(self):
        r = self._extract("organic fresh-picked apples")
        self.assertEqual(r.residual, "apples")
        self.assertIn("fresh-picked", r.fluff_stripped)

    def test_extracts_form(self):
        r = self._extract("sliced apples")
        self.assertEqual(r.form, "sliced")
        self.assertEqual(r.residual, "apples")

    def test_extracts_state_form_and_style(self):
        r = self._extract("raw organic sliced apples")
        # 'organic' is in fluff by default — gets stripped, not promoted to style.
        self.assertEqual(r.state, "raw")
        self.assertEqual(r.form, "sliced")
        self.assertEqual(r.residual, "apples")

    def test_extracts_flavor(self):
        r = self._extract("cinnamon applesauce")
        self.assertEqual(r.flavor, "cinnamon")
        self.assertEqual(r.residual, "applesauce")

    def test_extracts_packaging(self):
        r = self._extract("agave nectar packets")
        self.assertEqual(r.packaging, "packets")
        self.assertEqual(r.residual, "agave nectar")

    def test_head_noun_is_rightmost_residual_token(self):
        r = self._extract("blue agave nectar")
        self.assertEqual(r.residual, "blue agave nectar")
        self.assertEqual(r.head_noun, "nectar")

    def test_multiword_residual_preserved(self):
        r = self._extract("agave nectar")
        self.assertEqual(r.residual, "agave nectar")
