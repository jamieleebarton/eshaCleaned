import unittest
from implementation.family_lookup import infer_family


class TestInferFamily(unittest.TestCase):
    def test_bread_family(self):
        self.assertEqual(infer_family("bread"), "bread")
        self.assertEqual(infer_family("bread crumbs"), "bread")
        self.assertEqual(infer_family("garlic bread"), "bread")

    def test_cookie_family(self):
        self.assertEqual(infer_family("cookie"), "cookie")
        self.assertEqual(infer_family("cookies"), "cookie")

    def test_chip_family(self):
        self.assertEqual(infer_family("potato chips"), "snack")
        self.assertEqual(infer_family("tortilla chips"), "snack")

    def test_ice_cream_family(self):
        self.assertEqual(infer_family("ice cream"), "frozen_dairy")
        self.assertEqual(infer_family("light ice cream"), "frozen_dairy")

    def test_spice_blend_family(self):
        self.assertEqual(infer_family("garam masala"), "spice_blend")
        self.assertEqual(infer_family("taco seasoning"), "spice_blend")
        self.assertEqual(infer_family("italian seasoning"), "spice_blend")

    def test_salt_family(self):
        self.assertEqual(infer_family("kosher salt"), "salt")
        self.assertEqual(infer_family("sea salt"), "salt")

    def test_bean_family(self):
        self.assertEqual(infer_family("black beans"), "legume")
        self.assertEqual(infer_family("pinto beans"), "legume")

    def test_sauce_family(self):
        self.assertEqual(infer_family("salsa"), "sauce")
        self.assertEqual(infer_family("hoisin sauce"), "sauce")
        self.assertEqual(infer_family("gochujang"), "sauce")

    def test_cheese_family(self):
        self.assertEqual(infer_family("cheddar"), "cheese")
        self.assertEqual(infer_family("parmesan"), "cheese")

    def test_unknown_falls_back(self):
        self.assertEqual(infer_family("xylophone"), "other")


if __name__ == "__main__":
    unittest.main()
