import unittest
from implementation.canonical_signature.brand_stripper import strip_brand


class BrandStripperTests(unittest.TestCase):
    def test_strips_explicit_brand_name_prefix(self):
        out, brand = strip_brand("natures place, organic apples", brand_name="natures place")
        self.assertEqual(out, "organic apples")
        self.assertEqual(brand, "natures place")

    def test_strips_explicit_brand_name_inline(self):
        out, brand = strip_brand("madhava raw organic agave nectar", brand_name="madhava")
        self.assertEqual(out, "raw organic agave nectar")
        self.assertEqual(brand, "madhava")

    def test_strips_brand_owner_when_brand_name_missing(self):
        out, brand = strip_brand("goldens fresh sliced apples", brand_name=None,
                                 brand_owner="goldens")
        self.assertEqual(out, "fresh sliced apples")
        self.assertEqual(brand, "goldens")

    def test_falls_back_to_comma_prefix_heuristic(self):
        out, brand = strip_brand("fresh selections, veggie tray with apples",
                                 brand_name=None, brand_owner=None,
                                 brand_vocabulary=frozenset({"fresh selections"}))
        self.assertEqual(out, "veggie tray with apples")
        self.assertEqual(brand, "fresh selections")

    def test_no_strip_when_no_brand_signal(self):
        out, brand = strip_brand("apples", brand_name=None, brand_owner=None,
                                 brand_vocabulary=frozenset())
        self.assertEqual(out, "apples")
        self.assertEqual(brand, "")

    def test_does_not_strip_brand_when_it_is_the_whole_string(self):
        out, brand = strip_brand("madhava", brand_name="madhava")
        self.assertEqual(out, "madhava")
        self.assertEqual(brand, "")
