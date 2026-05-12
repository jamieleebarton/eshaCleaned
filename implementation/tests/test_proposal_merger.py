import csv
import tempfile
import unittest
from pathlib import Path

from implementation.proposal_merger import (
    merge_concepts_batch,
    merge_rules_batch,
    merge_contracts_batch,
    apply_parent_contract_updates,
)


def _write_csv(path, fieldnames, rows):
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


class TestMergeConceptsBatch(unittest.TestCase):
    def test_appends_rows_preserving_existing(self):
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "seed.csv"
            fields = ["alias", "canonical_concept", "family", "trust_state", "nutrition_state",
                      "shopping_state", "anchor_system", "anchor_code", "anchor_description",
                      "product_query", "review_status", "evidence_notes"]
            _write_csv(target, fields, [{"alias": "old", "canonical_concept": "old|||",
                                         "family": "legacy", "trust_state": "reviewed_usda_anchor",
                                         "nutrition_state": "reviewed_usda_anchor",
                                         "shopping_state": "shopping_candidates_strong",
                                         "anchor_system": "SR28", "anchor_code": "1",
                                         "anchor_description": "x", "product_query": "old",
                                         "review_status": "approved", "evidence_notes": "legacy"}])
            new_rows = [{"alias": "new", "canonical_concept": "new|||",
                         "family": "new_fam", "trust_state": "reviewed_usda_anchor",
                         "nutrition_state": "reviewed_usda_anchor",
                         "shopping_state": "shopping_candidates_strong",
                         "anchor_system": "", "anchor_code": "",
                         "anchor_description": "", "product_query": "new",
                         "review_status": "proposed", "evidence_notes": "new"}]
            added = merge_concepts_batch(target, new_rows)
            self.assertEqual(added, 1)
            with open(target) as fh:
                out = list(csv.DictReader(fh))
            self.assertEqual(len(out), 2)
            self.assertEqual(out[0]["alias"], "old")
            self.assertEqual(out[1]["alias"], "new")


class TestApplyParentContractUpdates(unittest.TestCase):
    def test_modifies_existing_forbidden(self):
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "contracts.csv"
            fields = ["contract_id", "concept_keys", "policy", "allowed_categories",
                      "required_all", "required_any", "forbidden_any",
                      "apply_common_forbidden", "notes"]
            _write_csv(target, fields, [{
                "contract_id": "potato_chips",
                "concept_keys": '["potato chips|||"]',
                "policy": "direct_buy",
                "allowed_categories": "[]",
                "required_all": '["potato","chips"]',
                "required_any": "[]",
                "forbidden_any": '["candied"]',
                "apply_common_forbidden": "yes",
                "notes": ""
            }])
            updates = [{
                "action": "extend_forbidden_any",
                "parent_concept_key": "potato chips|||",
                "contract_id": "potato_chips",
                "existing_forbidden_any": '["candied"]',
                "new_forbidden_any": '["barbecue", "candied", "sour cream and onion"]',
                "children_added": "2",
                "notes": "",
            }]
            modified = apply_parent_contract_updates(target, updates)
            self.assertEqual(modified, 1)
            with open(target) as fh:
                rows = list(csv.DictReader(fh))
            self.assertEqual(rows[0]["forbidden_any"],
                             '["barbecue", "candied", "sour cream and onion"]')


if __name__ == "__main__":
    unittest.main()
