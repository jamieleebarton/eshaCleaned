import unittest
from implementation.canonical_signature.vocabularies import (
    FLUFF_TOKENS,
    COMPOSITE_TRIGGERS,
    SEED_FLAVOR_TOKENS,
    Vocabularies,
)


class VocabularyConstantsTests(unittest.TestCase):
    def test_fluff_includes_known_marketing_words(self):
        for w in ("organic", "premium", "fresh-picked", "all-natural", "100%"):
            self.assertIn(w, FLUFF_TOKENS, f"{w} should be fluff")

    def test_composite_triggers_include_with_and_filled(self):
        for w in ("with", "filled", "stuffed", "topped", "&"):
            self.assertIn(w, COMPOSITE_TRIGGERS)

    def test_seed_flavors_include_common_variants(self):
        for w in ("vanilla", "chocolate", "strawberry", "cinnamon"):
            self.assertIn(w, SEED_FLAVOR_TOKENS)


class VocabulariesFromCanonicalSurfaceTests(unittest.TestCase):
    def test_loaded_vocabularies_have_nonempty_attribute_sets(self):
        v = Vocabularies.from_canonical_surface_default()
        self.assertGreater(len(v.form_vocabulary), 0, "form attrs should be populated")
        self.assertGreater(len(v.state_vocabulary), 0, "state attrs should be populated")
        self.assertGreater(len(v.style_vocabulary), 0, "style attrs should be populated")
        self.assertGreater(len(v.brand_vocabulary), 0, "brand candidates should be populated")
        self.assertGreater(len(v.head_noun_vocabulary), 0, "canonical heads should be populated")

    def test_fluff_takes_precedence_over_style(self):
        # 'organic' appears as a style attribute in canonical_surface but is also fluff;
        # fluff classification wins so unrelated organic-marketing tokens get stripped.
        v = Vocabularies.from_canonical_surface_default()
        self.assertIn("organic", v.fluff_tokens)
