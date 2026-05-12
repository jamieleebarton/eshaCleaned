import unittest
from implementation.concept_candidate_parser import (
    ConceptCandidate,
    parse_fndds_description,
)
from implementation.concept_candidate_parser import derive_sibling_forbidden


class TestParseFnddsDescription(unittest.TestCase):
    def test_potato_chips_sour_cream_and_onion(self):
        c = parse_fndds_description("Potato chips, sour cream and onion flavored")
        self.assertEqual(c.base, "potato chips")
        self.assertEqual(c.modifiers, ["sour cream and onion"])
        self.assertFalse(c.is_brand_specific)
        self.assertFalse(c.is_NS)
        self.assertFalse(c.is_prepared_dish)

    def test_potato_chips_ruffled_bbq(self):
        c = parse_fndds_description("Potato chips, ruffled, barbecue flavored")
        self.assertEqual(c.base, "potato chips")
        self.assertEqual(c.modifiers, ["ruffled", "barbecue"])

    def test_strips_NS_noise(self):
        c = parse_fndds_description("Yogurt, frozen, NS as to flavor, NS as to type of milk")
        self.assertEqual(c.base, "yogurt")
        self.assertEqual(c.modifiers, ["frozen"])
        self.assertTrue(c.is_NS)

    def test_brand_detection_uppercase_token(self):
        c = parse_fndds_description("Ice creams, BREYERS, All Natural Light Vanilla")
        self.assertTrue(c.is_brand_specific)
        self.assertEqual(c.brand, "BREYERS")

    def test_prepared_dish_skipped(self):
        c = parse_fndds_description(
            "Bread pudding made with evaporated milk and rum"
        )
        self.assertTrue(c.is_prepared_dish)

    def test_cone_not_prepared_dish(self):
        c = parse_fndds_description("Yogurt, frozen, cone, chocolate")
        self.assertFalse(c.is_prepared_dish)

    def test_sandwich_variant_not_prepared_dish(self):
        c = parse_fndds_description("Yogurt, frozen, sandwich")
        self.assertFalse(c.is_prepared_dish)

    def test_strips_flavored_suffix(self):
        c = parse_fndds_description("Potato chips, cheese flavored")
        self.assertEqual(c.modifiers, ["cheese"])

    def test_ground_spice_preserves_form(self):
        c = parse_fndds_description("Spices, cinnamon, ground")
        self.assertEqual(c.base, "cinnamon")
        self.assertIn("ground", c.modifiers)
        self.assertEqual(c.form, "ground")

    def test_modifiers_lowercased(self):
        c = parse_fndds_description("Potato chips, BARBECUE flavored")
        self.assertEqual(c.modifiers, ["barbecue"])


class TestNfsAbbreviation(unittest.TestCase):
    def test_nfs_classified_as_NS_not_brand(self):
        c = parse_fndds_description("Ice cream, NFS")
        self.assertTrue(c.is_NS)
        self.assertFalse(c.is_brand_specific)

    def test_bare_NS_classified_as_NS(self):
        c = parse_fndds_description("Potato chips, NS")
        self.assertTrue(c.is_NS)
        self.assertFalse(c.is_brand_specific)


class TestFlavorsOtherThan(unittest.TestCase):
    def test_flavors_other_than_quarantined(self):
        c = parse_fndds_description("Yogurt, frozen, flavors other than chocolate")
        self.assertTrue(c.is_NS)


class TestDeriveSiblingForbidden(unittest.TestCase):
    def test_chip_flavors_forbid_each_other(self):
        siblings = [
            ConceptCandidate(raw_description="", base="potato chips", modifiers=["plain"]),
            ConceptCandidate(raw_description="", base="potato chips", modifiers=["barbecue"]),
            ConceptCandidate(raw_description="", base="potato chips", modifiers=["sour cream and onion"]),
            ConceptCandidate(raw_description="", base="potato chips", modifiers=["cheese"]),
        ]
        result = derive_sibling_forbidden(siblings)
        sco = next(c for c in result if "sour cream and onion" in c["modifiers"])
        self.assertIn("barbecue", sco["forbidden"])
        self.assertIn("cheese", sco["forbidden"])
        self.assertIn("plain", sco["forbidden"])
        self.assertNotIn("sour cream and onion", sco["forbidden"])

    def test_shared_modifier_not_forbidden(self):
        siblings = [
            ConceptCandidate(raw_description="", base="potato chips", modifiers=["ruffled", "plain"]),
            ConceptCandidate(raw_description="", base="potato chips", modifiers=["ruffled", "barbecue"]),
        ]
        result = derive_sibling_forbidden(siblings)
        bbq = next(c for c in result if "barbecue" in c["modifiers"])
        self.assertNotIn("ruffled", bbq["forbidden"])
        self.assertIn("plain", bbq["forbidden"])


if __name__ == "__main__":
    unittest.main()
