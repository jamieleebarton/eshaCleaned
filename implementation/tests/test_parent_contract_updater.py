import csv
import json
import tempfile
import unittest
from pathlib import Path

from implementation.parent_contract_updater import (
    parent_from_concept_key,
    collect_child_tokens_by_parent,
    build_parent_updates,
    run_parent_updater,
)


class TestParentFromConceptKey(unittest.TestCase):
    def test_strips_variant(self):
        self.assertEqual(parent_from_concept_key("potato chips|sour cream and onion||"), "potato chips|||")

    def test_strips_form(self):
        self.assertEqual(parent_from_concept_key("cinnamon||ground|"), "cinnamon|||")

    def test_already_parent(self):
        self.assertEqual(parent_from_concept_key("ice cream|||"), "ice cream|||")


class TestCollectChildTokens(unittest.TestCase):
    def test_groups_by_parent_and_unions_tokens(self):
        children = [
            {"canonical_concept": "potato chips|sour cream and onion||",
             "_modifiers": '["sour cream and onion"]'},
            {"canonical_concept": "potato chips|barbecue||", "_modifiers": '["barbecue"]'},
            {"canonical_concept": "ice cream|mint||", "_modifiers": '["mint"]'},
        ]
        out = collect_child_tokens_by_parent(children)
        self.assertIn("potato chips|||", out)
        self.assertEqual(
            sorted(out["potato chips|||"]),
            sorted(["sour cream and onion", "barbecue"]),
        )
        self.assertEqual(out["ice cream|||"], ["mint"])


class TestBuildParentUpdates(unittest.TestCase):
    def test_unions_forbidden_with_existing(self):
        existing_contracts = [{
            "contract_id": "potato_chips",
            "concept_keys": '["potato chips|||"]',
            "policy": "direct_buy",
            "allowed_categories": '["Snacks"]',
            "required_all": '["potato", "chips"]',
            "required_any": "[]",
            "forbidden_any": '["candied"]',
            "apply_common_forbidden": "yes",
            "notes": "",
        }]
        child_tokens = {"potato chips|||": ["sour cream and onion", "barbecue"]}
        updates = build_parent_updates(existing_contracts, child_tokens)
        self.assertEqual(len(updates), 1)
        u = updates[0]
        self.assertEqual(u["contract_id"], "potato_chips")
        # Forbidden must be union of existing + new
        new_forbidden = json.loads(u["new_forbidden_any"])
        self.assertIn("candied", new_forbidden)
        self.assertIn("sour cream and onion", new_forbidden)
        self.assertIn("barbecue", new_forbidden)

    def test_emits_update_for_parent_not_in_existing(self):
        child_tokens = {"garam masala|||": ["paste"]}
        updates = build_parent_updates([], child_tokens)
        # Parent has no contract yet — emit a new-contract proposal
        self.assertEqual(len(updates), 1)
        self.assertEqual(updates[0]["action"], "create_new_parent_contract")


if __name__ == "__main__":
    unittest.main()
