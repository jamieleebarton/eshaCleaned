import unittest

from implementation.build_concept_anchor_poc import extract_concept, score_anchor, Anchor


class ConceptAnchorPocTests(unittest.TestCase):
    def test_oyster_word_splits_by_lane(self):
        seafood = extract_concept("FRESH PACIFIC OYSTERS", "Fish & Seafood")
        mushroom = extract_concept("OYSTER MUSHROOMS", "Baking Additives & Extracts")

        self.assertIsNotNone(seafood)
        self.assertIsNotNone(mushroom)
        self.assertEqual(seafood.path, "seafood/oyster/pacific/fresh+raw/generic")
        self.assertEqual(mushroom.path, "mushroom/mushroom/oyster/generic/generic")

    def test_category_does_not_supply_identity(self):
        concept = extract_concept(
            "SARDINES IN OLIVE OIL",
            "Canned Seafood:48 | Canned Tuna:1",
        )

        self.assertIsNotNone(concept)
        self.assertEqual(concept.identity, "sardine")

    def test_composite_anchor_is_penalized_for_plain_product(self):
        product = extract_concept("COOKED SHRIMP", "Frozen Fish & Seafood")
        spring_roll = extract_concept("spring roll, fried, shrimp, wild, thai, frozen", "")
        cooked = extract_concept("shrimp, cooked", "")

        self.assertIsNotNone(product)
        self.assertIsNotNone(spring_roll)
        self.assertIsNotNone(cooked)

        spring_roll_match = score_anchor(
            product,
            Anchor("esha", "25959", "spring roll, fried, shrimp, wild, thai, frozen", "", spring_roll),
        )
        cooked_match = score_anchor(
            product,
            Anchor("esha", "19141", "shrimp, cooked", "", cooked),
        )

        self.assertIsNotNone(spring_roll_match)
        self.assertIsNotNone(cooked_match)
        self.assertLess(spring_roll_match.score, cooked_match.score)

    def test_produce_mushroom_defaults_to_fresh_not_dried(self):
        product = extract_concept("GOLDEN OYSTER MUSHROOMS", "Pre-Packaged Fruit & Vegetables")
        dried = extract_concept("mushrooms, oyster, dried", "")
        fresh = extract_concept("mushrooms, oyster, fresh", "")

        self.assertIsNotNone(product)
        self.assertIsNotNone(dried)
        self.assertIsNotNone(fresh)
        self.assertEqual(product.path, "mushroom/mushroom/golden+oyster/fresh+raw/generic")
        self.assertIsNone(score_anchor(product, Anchor("esha", "6110", "mushrooms, oyster, dried", "", dried)))
        self.assertIsNotNone(score_anchor(product, Anchor("esha", "7948", "mushrooms, oyster, fresh", "", fresh)))

    def test_generic_mushroom_does_not_safely_pick_dried_anchor(self):
        product = extract_concept("KING OYSTER MUSHROOMS", "Other Deli")
        dried = extract_concept("mushrooms, oyster, dried", "")

        self.assertIsNotNone(product)
        self.assertIsNotNone(dried)
        match = score_anchor(product, Anchor("esha", "6110", "mushrooms, oyster, dried", "", dried))
        self.assertIsNotNone(match)
        self.assertLess(match.score, 68.0)

    def test_seasoned_mushroom_does_not_safely_pick_plain_fresh_anchor(self):
        product = extract_concept("SHAWARMA STYLE SHREDS SHREDDED KING OYSTER MUSHROOMS WITH SMOKY SPICE", "Other Deli")
        fresh = extract_concept("mushrooms, oyster, fresh", "")

        self.assertIsNotNone(product)
        self.assertIsNotNone(fresh)
        match = score_anchor(product, Anchor("esha", "7948", "mushrooms, oyster, fresh", "", fresh))
        self.assertIsNotNone(match)
        self.assertLess(match.score, 68.0)


if __name__ == "__main__":
    unittest.main()
