import unittest
from implementation.canonical_signature.pipeline import (
    CanonicalSignaturePipeline, ProductRow,
)
from implementation.canonical_signature.vocabularies import Vocabularies, FLUFF_TOKENS, SEED_FLAVOR_TOKENS


def _make_pipeline():
    canonical_rows = [
        # id, normalized text, form, state, flavor, style
        ("apple_raw",          "apples raw",                None,     "raw",   None,       None),
        ("apple_sliced",       "apples sliced",             "sliced", None,    None,       None),
        ("applesauce",         "applesauce",                None,     None,    None,       None),
        ("applesauce_cin",     "applesauce cinnamon",       None,     None,    "cinnamon", None),
        ("agave_nectar",       "agave nectar",              None,     None,    None,       None),
        ("agave_nectar_raw",   "agave nectar raw",          None,     "raw",   None,       None),
        ("ice_cream_vanilla",  "ice cream vanilla",         None,     None,    "vanilla",  None),
        ("ice_cream_chocolate","ice cream chocolate",       None,     None,    "chocolate",None),
        ("bun_filled_meat",    "steamed bun filled meat",   None,     None,    None,       None),
    ]
    vocab = Vocabularies(
        fluff_tokens=FLUFF_TOKENS,
        noise_tokens=frozenset({"oz", "count", "pack", "bag", "size"}),
        composite_triggers=frozenset({"with", "filled", "stuffed", "topped", "&"}),
        flavor_vocabulary=SEED_FLAVOR_TOKENS,
        form_vocabulary=frozenset({"sliced", "whole", "diced", "liquid", "powder"}),
        state_vocabulary=frozenset({"raw", "frozen", "fresh", "cooked", "dried"}),
        style_vocabulary=frozenset({"organic", "kosher"}),
        packaging_vocabulary=frozenset({"packets", "tray", "cup", "bag"}),
        brand_vocabulary=frozenset({"natures place", "madhava", "goldens"}),
        head_noun_vocabulary=frozenset(r[1] for r in canonical_rows),
        canonical_head_tokens=frozenset(r[1].split()[-1] for r in canonical_rows),
    )
    category_map = {"steamed/stuffed buns": "bun_filled_meat"}
    return CanonicalSignaturePipeline.build(canonical_rows, vocab, category_map)


class PipelineGoldenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pipe = _make_pipeline()

    def _process(self, desc, brand_name=None, brand_owner=None, category=None):
        return self.pipe.process(ProductRow(
            description=desc, brand_name=brand_name, brand_owner=brand_owner,
            branded_food_category=category,
        ))

    def test_brand_prefix_is_stripped(self):
        sig, trace, anchor = self._process("NATURE'S PLACE, ORGANIC APPLES",
                                           brand_name="NATURE'S PLACE")
        self.assertEqual(trace.stripped_brand, "natures place")
        self.assertIn("organic", trace.stripped_fluff)
        self.assertIn(anchor, ("apple_raw", "apple_sliced", "applesauce"))

    def test_cinnamon_applesauce_picks_cinnamon_variant(self):
        sig, trace, anchor = self._process("CINNAMON APPLESAUCE")
        self.assertEqual(anchor, "applesauce_cin")
        self.assertEqual(sig.flavor, "cinnamon")

    def test_plain_applesauce_picks_plain_variant(self):
        sig, trace, anchor = self._process("APPLESAUCE")
        self.assertEqual(anchor, "applesauce")

    def test_vanilla_ice_cream_picks_vanilla_variant(self):
        sig, trace, anchor = self._process("VANILLA ICE CREAM")
        self.assertEqual(anchor, "ice_cream_vanilla")

    def test_chocolate_ice_cream_picks_chocolate_variant(self):
        sig, trace, anchor = self._process("CHOCOLATE ICE CREAM")
        self.assertEqual(anchor, "ice_cream_chocolate")

    def test_raw_agave_picks_raw_variant(self):
        sig, trace, anchor = self._process("MADHAVA, RAW ORGANIC AGAVE NECTAR",
                                           brand_name="MADHAVA")
        self.assertEqual(anchor, "agave_nectar_raw")
        self.assertEqual(sig.state, "raw")

    def test_composite_routes_via_category(self):
        sig, trace, anchor = self._process(
            "CHAR-SIU MANAPUA STEAMED BUN WITH ROAST SWEET PORK FILLING",
            category="Steamed/Stuffed Buns",
        )
        self.assertTrue(sig.composite)
        self.assertEqual(trace.match_layer, "L7_category")
        self.assertEqual(anchor, "bun_filled_meat")

    def test_composite_unresolved_when_no_category_match(self):
        sig, trace, anchor = self._process(
            "FRESH SELECTIONS, VEGGIE TRAY WITH APPLES",
            brand_name="FRESH SELECTIONS",
            category="Unknown Random Category",
        )
        self.assertTrue(sig.composite)
        self.assertEqual(trace.match_layer, "L7_unresolved")
        self.assertIsNone(anchor)

    def test_signature_groups_collapse_correctly(self):
        results = [
            self._process("APPLESAUCE"),
            self._process("ORGANIC APPLESAUCE"),
            self._process("PREMIUM APPLESAUCE"),
            self._process("AUTHENTIC APPLESAUCE"),
        ]
        sigs = {r[0] for r in results}
        self.assertEqual(len(sigs), 1, f"All should collapse to one signature, got {sigs}")
