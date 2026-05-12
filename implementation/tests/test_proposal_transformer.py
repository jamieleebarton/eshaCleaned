import csv
import tempfile
import unittest
from pathlib import Path

from implementation.proposal_transformer import (
    reshape_concept_row,
    reshape_rule_row,
    reshape_contract_row,
    explode_rule_to_exact,
    classify_tier,
    dedupe_against_existing,
    run_transformer,
)


class TestReshapeConceptRow(unittest.TestCase):
    def test_fndds_concept_gets_usda_trust(self):
        row = {
            "concept_key": "potato chips|sour cream and onion||",
            "base": "potato chips",
            "variant": "sour cream and onion",
            "form": "",
            "state": "",
            "modifiers": '["sour cream and onion"]',
            "forbidden_tokens": '["barbecue", "cheese", "plain"]',
            "raw_description": "Potato chips, sour cream and onion flavored",
            "recipe_miss_count": "4",
        }
        out = reshape_concept_row(row, source="PHASE1")
        self.assertEqual(out["canonical_concept"], "potato chips|sour cream and onion||")
        self.assertEqual(out["family"], "snack")
        self.assertEqual(out["trust_state"], "reviewed_usda_anchor")
        self.assertEqual(out["review_status"], "proposed")
        self.assertEqual(out["alias"], "sour cream and onion potato chips")
        self.assertIn("FNDDS description", out["evidence_notes"])

    def test_local_label_concept_gets_proxy_state(self):
        row = {
            "concept_key": "ice cream|mint chocolate chip||",
            "parent_concept_phrase": "ice cream",
            "parent_anchor_system": "SR28",
            "parent_anchor_code": "167575",
            "parent_description": "Ice creams, vanilla",
            "distinguishing_modifiers": '["mint", "chocolate chip"]',
            "forbidden_tokens": '["barbecue", "plain"]',
            "source_miss_surface": "mint chocolate chip ice cream",
            "recipe_miss_count": "12",
        }
        out = reshape_concept_row(row, source="PHASE2")
        self.assertEqual(out["nutrition_state"], "reviewed_proxy")
        self.assertEqual(out["anchor_system"], "SR28")
        self.assertEqual(out["anchor_code"], "167575")
        self.assertIn("Nearest parent", out["evidence_notes"])


class TestExplodeRuleToExact(unittest.TestCase):
    def test_expands_contains_all_to_per_surface_exact(self):
        proposal_rule = {
            "rule_id": "fndds_proposed_potato_chips_sour_cream_and_onion",
            "match_type": "contains_all",
            "input_surface": "sour cream and onion potato chips",
            "canonical_concept_key": "potato chips|sour cream and onion||",
        }
        observed_surfaces = [
            "sour cream and onion potato chips",
            "ruffles sour cream and onion chips",
            "2 cups sour cream and onion potato chips",
        ]
        rules = explode_rule_to_exact(proposal_rule, observed_surfaces)
        self.assertEqual(len(rules), 3)
        self.assertTrue(all(r["match_type"] == "exact" for r in rules))
        self.assertEqual(
            {r["input_surface"] for r in rules},
            set(observed_surfaces),
        )
        # Rule IDs must be unique per expanded row
        self.assertEqual(len({r["rule_id"] for r in rules}), 3)


class TestClassifyTier(unittest.TestCase):
    def test_fndds_clean_variant_auto(self):
        row = {"trust_state": "reviewed_usda_anchor", "family": "snack",
               "recipe_miss_count": "5", "modifiers": '["sour cream and onion"]'}
        self.assertEqual(classify_tier(row), "auto")

    def test_brand_token_rejects(self):
        row = {"trust_state": "reviewed_usda_anchor", "family": "snack",
               "recipe_miss_count": "10", "modifiers": '["ORTEGA"]'}
        self.assertEqual(classify_tier(row), "rejected")

    def test_low_count_goes_to_review(self):
        row = {"trust_state": "reviewed_usda_anchor", "family": "snack",
               "recipe_miss_count": "2", "modifiers": '["ruffled"]'}
        self.assertEqual(classify_tier(row), "review")

    def test_proxy_goes_to_review(self):
        row = {"trust_state": "reviewed_local_label_anchor", "family": "frozen_dairy",
               "recipe_miss_count": "12", "modifiers": '["mint chocolate chip"]'}
        self.assertEqual(classify_tier(row), "review")

    def test_family_other_goes_to_review(self):
        row = {"trust_state": "reviewed_usda_anchor", "family": "other",
               "recipe_miss_count": "10", "modifiers": '["xyz"]'}
        self.assertEqual(classify_tier(row), "review")

    def test_recipe_follows_rejects(self):
        row = {"trust_state": "reviewed_usda_anchor", "family": "spice_blend",
               "recipe_miss_count": "10", "modifiers": '["recipe follows"]'}
        self.assertEqual(classify_tier(row), "rejected")


class TestDedupeAgainstExisting(unittest.TestCase):
    def test_drops_existing_concept_key(self):
        proposed = [{"canonical_concept": "cinnamon|||"},
                    {"canonical_concept": "cinnamon|smoked||"}]
        existing = {"cinnamon|||"}
        out = dedupe_against_existing(proposed, existing, key_field="canonical_concept")
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["canonical_concept"], "cinnamon|smoked||")


if __name__ == "__main__":
    unittest.main()
