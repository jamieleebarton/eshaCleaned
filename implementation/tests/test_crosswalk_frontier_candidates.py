from __future__ import annotations

import unittest

from implementation.build_crosswalk_frontier_candidates import (
    best_crosswalk_candidate,
    build_crosswalk_form_index,
    confidence,
)


class CrosswalkFrontierCandidateTests(unittest.TestCase):
    def candidate_for(self, frontier_row, crosswalk_rows):
        forms, index = build_crosswalk_form_index(crosswalk_rows)
        return best_crosswalk_candidate(frontier_row, forms, index)

    def test_prefers_tight_food_description_over_incidental_overlap(self):
        row, source, _form, score, _reason = self.candidate_for(
            {
                "concept_key": "sweet onion|yellow||",
                "display": "1 cup chopped yellow sweet onion",
            },
            [
                {
                    "sr28_fdc_id": "169397",
                    "sr28_description": "Pickles, chowchow, with cauliflower onion mustard, sweet",
                    "match_type": "unmatched_sr28",
                },
                {
                    "sr28_fdc_id": "170008",
                    "sr28_description": "Onions, sweet, raw",
                    "match_type": "unmatched_sr28",
                },
            ],
        )

        self.assertEqual("SR28", source)
        self.assertEqual("170008", row["sr28_fdc_id"])
        self.assertEqual("review", confidence(score))

    def test_candy_taxonomy_prefix_is_not_removed_for_fresh_truffle(self):
        row, source, _form, score, reason = self.candidate_for(
            {
                "concept_key": "truffle|black||fresh",
                "display": "1 fresh black truffle",
            },
            [
                {
                    "sr28_fdc_id": "169580",
                    "sr28_description": "Candies, truffles, prepared-from-recipe",
                    "match_type": "unmatched_sr28",
                },
            ],
        )

        self.assertEqual("SR28", source)
        self.assertEqual("169580", row["sr28_fdc_id"])
        self.assertLessEqual(score, 72)
        self.assertIn("state_not_explicit", reason)

    def test_missing_powder_state_caps_exact_base_match(self):
        row, source, _form, score, reason = self.candidate_for(
            {
                "concept_key": "chicken soup||powder|",
                "display": "2 tablespoons chicken soup powder",
            },
            [
                {
                    "fndds_food_code": "28340660",
                    "fndds_description": "Soup, chicken",
                    "match_type": "unmatched_fndds",
                },
            ],
        )

        self.assertEqual("FNDDS", source)
        self.assertEqual("28340660", row["fndds_food_code"])
        self.assertEqual(72, score)
        self.assertEqual("same_token_set_state_not_explicit", reason)


if __name__ == "__main__":
    unittest.main()
