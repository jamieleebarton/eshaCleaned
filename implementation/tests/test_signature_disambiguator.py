import unittest
from implementation.canonical_signature.disambiguator import (
    CanonicalCandidate, disambiguate,
)


class DisambiguatorTests(unittest.TestCase):
    def test_picks_candidate_with_matching_flavor(self):
        candidates = [
            (CanonicalCandidate(id="applesauce_plain", form=None, state=None,
                                flavor=None, style=None), 0.85),
            (CanonicalCandidate(id="applesauce_cinnamon", form=None, state=None,
                                flavor="cinnamon", style=None), 0.82),
        ]
        winner = disambiguate(candidates, product_form=None, product_state=None,
                              product_flavor="cinnamon", product_style=None)
        self.assertEqual(winner.id, "applesauce_cinnamon")

    def test_picks_candidate_with_matching_form(self):
        candidates = [
            (CanonicalCandidate(id="apple_whole", form="whole", state=None,
                                flavor=None, style=None), 0.80),
            (CanonicalCandidate(id="apple_sliced", form="sliced", state=None,
                                flavor=None, style=None), 0.78),
        ]
        winner = disambiguate(candidates, product_form="sliced", product_state=None,
                              product_flavor=None, product_style=None)
        self.assertEqual(winner.id, "apple_sliced")

    def test_lexical_score_breaks_ties_when_no_attributes(self):
        candidates = [
            (CanonicalCandidate(id="a", form=None, state=None, flavor=None, style=None), 0.50),
            (CanonicalCandidate(id="b", form=None, state=None, flavor=None, style=None), 0.60),
        ]
        winner = disambiguate(candidates, product_form=None, product_state=None,
                              product_flavor=None, product_style=None)
        self.assertEqual(winner.id, "b")

    def test_mismatch_penalized(self):
        candidates = [
            (CanonicalCandidate(id="ice_cream_vanilla", form=None, state=None,
                                flavor="vanilla", style=None), 0.90),
            (CanonicalCandidate(id="ice_cream_plain", form=None, state=None,
                                flavor=None, style=None), 0.85),
        ]
        winner = disambiguate(candidates, product_form=None, product_state=None,
                              product_flavor="chocolate", product_style=None)
        self.assertEqual(winner.id, "ice_cream_plain")
