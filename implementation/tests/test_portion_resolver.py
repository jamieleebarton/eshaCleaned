# implementation/tests/test_portion_resolver.py
import unittest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from portion_resolver import resolve_grams


class PortionResolverTests(unittest.TestCase):
    def test_butter_one_cup(self):
        # SR28 butter_salted 173410 has "1 cup" portion in food_portion.csv
        g = resolve_grams(sr28_fdc_id="173410", fndds_code="", pseudo_code="",
                           qty=1.0, unit="cup")
        self.assertIsNotNone(g)
        self.assertAlmostEqual(g, 227, delta=10)  # USDA: 1 cup butter ≈ 227g

    def test_butter_one_tbsp(self):
        g = resolve_grams(sr28_fdc_id="173410", fndds_code="", pseudo_code="",
                           qty=1.0, unit="tbsp")
        self.assertIsNotNone(g)
        self.assertAlmostEqual(g, 14.2, delta=1.5)  # 1 tbsp butter ≈ 14.2g

    def test_large_egg(self):
        g = resolve_grams(sr28_fdc_id="171287", fndds_code="", pseudo_code="",
                           qty=1.0, unit="large")
        self.assertIsNotNone(g)
        self.assertAlmostEqual(g, 50, delta=5)  # 1 large egg ≈ 50g

    def test_unit_alias_c_maps_to_cup(self):
        g1 = resolve_grams(sr28_fdc_id="173410", fndds_code="", pseudo_code="",
                            qty=1.0, unit="cup")
        g2 = resolve_grams(sr28_fdc_id="173410", fndds_code="", pseudo_code="",
                            qty=1.0, unit="c")
        self.assertEqual(g1, g2)

    def test_unit_alias_t_maps_to_tsp(self):
        g1 = resolve_grams(sr28_fdc_id="173410", fndds_code="", pseudo_code="",
                            qty=1.0, unit="tsp")
        g2 = resolve_grams(sr28_fdc_id="173410", fndds_code="", pseudo_code="",
                            qty=1.0, unit="t")
        self.assertEqual(g1, g2)

    def test_unknown_unit_returns_none(self):
        g = resolve_grams(sr28_fdc_id="173410", fndds_code="", pseudo_code="",
                           qty=1.0, unit="splorch")
        self.assertIsNone(g)

    def test_no_code_returns_none(self):
        g = resolve_grams(sr28_fdc_id="", fndds_code="", pseudo_code="",
                           qty=1.0, unit="cup")
        self.assertIsNone(g)

    def test_gram_unit_is_identity(self):
        g = resolve_grams(sr28_fdc_id="173410", fndds_code="", pseudo_code="",
                           qty=50.0, unit="g")
        self.assertEqual(g, 50.0)

    def test_kilogram_unit(self):
        g = resolve_grams(sr28_fdc_id="173410", fndds_code="", pseudo_code="",
                           qty=1.5, unit="kg")
        self.assertEqual(g, 1500.0)

    def test_ounce_is_weight(self):
        g = resolve_grams(sr28_fdc_id="173410", fndds_code="", pseudo_code="",
                           qty=1.0, unit="oz")
        self.assertAlmostEqual(g, 28.3495, delta=0.01)

    def test_pound_is_weight(self):
        g = resolve_grams(sr28_fdc_id="173410", fndds_code="", pseudo_code="",
                           qty=1.0, unit="lb")
        self.assertAlmostEqual(g, 453.592, delta=0.01)

    def test_capital_T_maps_to_tbsp(self):
        """Recipe convention: T is tablespoon, t is teaspoon. Case matters."""
        g_tbsp = resolve_grams(sr28_fdc_id="173410", fndds_code="", pseudo_code="",
                                qty=1.0, unit="T")
        g_expected = resolve_grams(sr28_fdc_id="173410", fndds_code="", pseudo_code="",
                                    qty=1.0, unit="tbsp")
        self.assertEqual(g_tbsp, g_expected, "T must map to tbsp, not tsp")

    def test_lowercase_t_still_maps_to_tsp(self):
        g_t = resolve_grams(sr28_fdc_id="173410", fndds_code="", pseudo_code="",
                            qty=1.0, unit="t")
        g_tsp = resolve_grams(sr28_fdc_id="173410", fndds_code="", pseudo_code="",
                               qty=1.0, unit="tsp")
        self.assertEqual(g_t, g_tsp, "t must map to tsp")


if __name__ == "__main__":
    unittest.main()
