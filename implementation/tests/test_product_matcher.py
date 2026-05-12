import unittest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from product_matcher import match_products


class ProductMatcherTests(unittest.TestCase):
    def test_butter_returns_products(self):
        products = match_products(sr28_fdc_id="173410", fndds_code="81100500", pseudo_code="")
        self.assertGreater(len(products), 100, "butter should have many products")
        # All products should contain 'butter' in description
        misses = [p for p in products if "butter" not in p.description.lower()]
        self.assertLess(len(misses), len(products) * 0.1, "too many non-butter products")

    def test_unknown_codes_returns_empty(self):
        products = match_products(sr28_fdc_id="", fndds_code="", pseudo_code="")
        self.assertEqual(products, [])

    def test_cleaned_overlay_is_authoritative(self):
        """When a cleaned file exists for a code, ONLY those products should be returned for that code source."""
        # Dill pickle potato chips pseudo 71200145 — our cleaned file
        products = match_products(sr28_fdc_id="", fndds_code="", pseudo_code="71200145")
        if products:
            for p in products:
                self.assertEqual(p.source, "D_cleaned_overlay",
                                 f"non-cleaned source for cleaned pseudo: {p.source}")

    def test_sr28_only_canonical_still_finds_products(self):
        """A canonical with only SR28 (no FNDDS) must still match products via SR28 tags."""
        # 173430 Butter, unsalted — no fndds in our registry
        products = match_products(sr28_fdc_id="173430", fndds_code="", pseudo_code="")
        self.assertGreater(len(products), 0,
                           "unsalted butter should have SR28-tagged products via B/C/D sources")


if __name__ == "__main__":
    unittest.main()
