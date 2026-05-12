import unittest
from implementation.canonical_signature.composite_router import (
    is_composite, route_composite, CompositeRouting,
)


class CompositeDetectionTests(unittest.TestCase):
    def test_with_triggers_composite(self):
        self.assertTrue(is_composite("steamed bun with roast pork filling"))

    def test_filled_triggers_composite(self):
        self.assertTrue(is_composite("ravioli filled cheese"))

    def test_ampersand_word_triggers_composite(self):
        self.assertTrue(is_composite("rice & beans"))

    def test_simple_string_is_not_composite(self):
        self.assertFalse(is_composite("organic apples"))

    def test_and_alone_does_not_trigger(self):
        # 'and' is intentionally NOT a trigger.
        self.assertFalse(is_composite("macaroni and cheese"))


class CompositeRoutingTests(unittest.TestCase):
    def setUp(self):
        self.category_map = {
            "steamed/stuffed buns": "bun_filled_meat",
            "frozen meals - ethnic": "frozen_meal_mixed",
        }

    def test_routes_via_known_category(self):
        result = route_composite("CHAR-SIU MANAPUA STEAMED BUN WITH ROAST SWEET PORK FILLING",
                                 branded_food_category="Steamed/Stuffed Buns",
                                 category_to_anchor=self.category_map)
        self.assertEqual(result.layer, "L7_category")
        self.assertEqual(result.anchor_id, "bun_filled_meat")

    def test_unresolved_when_category_unknown(self):
        result = route_composite("rice & beans & corn",
                                 branded_food_category="Unknown Category",
                                 category_to_anchor=self.category_map)
        self.assertEqual(result.layer, "L7_unresolved")
        self.assertIsNone(result.anchor_id)

    def test_unresolved_when_category_missing(self):
        result = route_composite("rice & beans",
                                 branded_food_category=None,
                                 category_to_anchor=self.category_map)
        self.assertEqual(result.layer, "L7_unresolved")
