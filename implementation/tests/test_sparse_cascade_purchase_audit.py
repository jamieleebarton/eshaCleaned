from __future__ import annotations

import sys
import unittest
from pathlib import Path


IMPLEMENTATION = Path(__file__).resolve().parents[1]
if str(IMPLEMENTATION) not in sys.path:
    sys.path.insert(0, str(IMPLEMENTATION))

from run_sparse_cascade_purchase_audit import (  # noqa: E402
    build_purchase_records,
    classify_record_blockers,
    extract_recipe_ids_from_plan_result,
    is_hard_cart_blocker,
    issue_bucket,
    recipe_smoke_plan,
    select_deepseek_candidates,
    serialize_selections,
)


def packet_record(**overrides: object) -> dict:
    base = {
        "record_id": "recipe_smoke_known_blockers:506745:1",
        "source_record_id": "506745:1",
        "plan": {
            "plan_id": "recipe_smoke_known_blockers",
            "config_id": "recipe_smoke",
            "stores": ["walmart", "kroger"],
            "week": 0,
        },
        "recipe": {"recipe_num": "506745", "recipe_name": "Booyah", "line_index": 1},
        "ingredient": {
            "original_recipe_text": "1/2 gallon beef gravy",
            "parsed_item": "beef gravy",
            "normalized_shopping_item": "Gravy, instant beef, dry",
            "recipe_grams": 1893.0,
            "retail_purchase_grams": 1893.0,
        },
        "calculator": {
            "canonical_name": "beef gravy",
            "shopping_canonical": "beef gravy",
            "nutrition_state": "reviewed_local_label_anchor",
            "nutrition_source": "esha_tier_a_label_median",
            "nutrition_anchor": {"source": "ESHA", "code": "53023", "description": "Gravy, beef, canned"},
            "esha_code": "53023",
            "esha_description": "Gravy, beef, canned",
            "shopping_state": "shopping_candidates_strong",
            "path": [],
        },
        "store_checks": [
            {
                "store": "walmart",
                "status": "selected",
                "selected": {
                    "name": "Great Value Homestyle Beef Flavored Gravy, 12 oz Glass Jar",
                    "upc": "2574382081",
                    "package_grams": 340.0,
                    "packages": 6,
                    "checkout_usd": 8.82,
                },
            },
            {"store": "kroger", "status": "missing", "selected": None},
        ],
        "accepted_examples": [],
        "rejected_examples": [{"name": "Great Value Brown Gravy Mix, 0.87 oz"}],
    }
    base.update(overrides)
    return base


class SparseCascadePurchaseAuditTests(unittest.TestCase):
    def test_extract_recipe_ids_prefers_used_ids_and_dedupes(self) -> None:
        result = {"used_recipe_ids": [10, "11", 10, 0], "selections": [(99, 98, "Main", "Side", 1.0)]}

        self.assertEqual(extract_recipe_ids_from_plan_result(result), ["10", "11"])

    def test_extract_recipe_ids_from_new_and_old_selection_shapes(self) -> None:
        result = {
            "selections": [
                (101, 202, 303, "Main", "Side", "Side2", 4.5, None, None, None),
                (404, 505, "Old Main", "Old Side", 3.0),
                (0, 0, "SKIPPED", "Eating out", 0.0),
            ]
        }

        self.assertEqual(extract_recipe_ids_from_plan_result(result), ["101", "202", "303", "404", "505"])
        serialized = serialize_selections(result["selections"])
        self.assertEqual(serialized[0]["side2_recipe_id"], 303)
        self.assertEqual(serialized[1]["main_name"], "Old Main")

    def test_build_purchase_records_preserves_original_text_and_plan_metadata(self) -> None:
        report = {
            "recipes": [
                {
                    "recipe_num": "506745",
                    "recipe_name": "Booyah",
                    "lines": [
                        {
                            "input": "1/2 gallon beef gravy",
                            "original_item": "beef gravy",
                            "normalized_shopping_item": "Gravy, instant beef, dry",
                            "grams": 1893.0,
                            "shopping_grams": 1893.0,
                            "canonical_name": "beef gravy",
                            "shopping_canonical": "beef gravy",
                            "nutrition_state": "reviewed_local_label_anchor",
                            "nutrition_source": "esha_tier_a_label_median",
                            "esha_code": "53023",
                            "esha_description": "Gravy, beef, canned",
                            "shopping_state": "shopping_candidates_strong",
                            "walmart": {"name": "Great Value Homestyle Beef Flavored Gravy, 12 oz Glass Jar"},
                            "kroger": None,
                        }
                    ],
                }
            ]
        }

        records, missing = build_purchase_records(plan_runs=[recipe_smoke_plan(["506745"])], report=report)

        self.assertFalse(missing)
        self.assertEqual(records[0]["ingredient"]["original_recipe_text"], "1/2 gallon beef gravy")
        self.assertEqual(records[0]["plan"]["plan_id"], "recipe_smoke_known_blockers")
        self.assertTrue(records[0]["record_id"].startswith("recipe_smoke_known_blockers:"))

    def test_classify_flags_dry_normalized_gravy_without_rejecting_ready_gravy(self) -> None:
        blockers = classify_record_blockers(packet_record())
        issues = {(blocker.store, blocker.issue_type) for blocker in blockers}

        self.assertIn(("recipe", "wrong_form_candidate"), issues)
        self.assertIn(("kroger", "catalog_gap"), issues)
        self.assertNotIn(("walmart", "wrong_form_candidate"), issues)

    def test_classify_rejects_selected_dry_mix_for_prepared_gravy(self) -> None:
        record = packet_record(
            store_checks=[
                {
                    "store": "walmart",
                    "status": "selected",
                    "selected": {
                        "name": "Great Value Brown Gravy Mix, 0.87 oz",
                        "package_grams": 24.7,
                        "packages": 77,
                    },
                }
            ],
            plan={"plan_id": "p", "config_id": "cfg", "stores": ["walmart"], "week": 1},
        )

        blockers = classify_record_blockers(record)

        self.assertTrue(any(blocker.issue_type == "wrong_form_candidate" and blocker.store == "walmart" for blocker in blockers))

    def test_classify_veal_shopping_gap(self) -> None:
        record = packet_record(
            ingredient={
                "original_recipe_text": "1/2 gallon veal or 1/2 gallon lamb, leftovers",
                "parsed_item": "veal",
                "normalized_shopping_item": "veal",
                "recipe_grams": 1893.0,
                "retail_purchase_grams": 1893.0,
            },
            calculator={
                "canonical_name": "veal",
                "shopping_canonical": "",
                "nutrition_state": "nutrition_unknown",
                "nutrition_source": "",
                "nutrition_anchor": {"source": "", "code": "", "description": ""},
                "shopping_state": "shopping_gap",
                "path": [],
            },
            store_checks=[
                {"store": "walmart", "status": "missing", "selected": None},
                {"store": "kroger", "status": "missing", "selected": None},
            ],
        )

        blockers = classify_record_blockers(record)
        issue_types = [blocker.issue_type for blocker in blockers]

        self.assertIn("bad_recipe_or_unshoppable", issue_types)
        self.assertIn("nutrition_missing_or_wrong_anchor", issue_types)
        self.assertGreaterEqual(issue_types.count("shopping_gap"), 2)
        shopping_gaps = [blocker for blocker in blockers if blocker.issue_type == "shopping_gap"]
        self.assertTrue(all(blocker.severity == "warning" for blocker in shopping_gaps))
        self.assertTrue(all(not is_hard_cart_blocker(blocker) for blocker in shopping_gaps))

    def test_bologna_roll_wrong_form_moves_to_triage_not_hard_blocker(self) -> None:
        record = packet_record(
            recipe={"recipe_num": "209947", "recipe_name": "Brown Sugar Coated Bologna", "line_index": 1},
            ingredient={
                "original_recipe_text": "1 (5-6 lb) roll all-beef bologna",
                "parsed_item": "all-beef bologna",
                "normalized_shopping_item": "Bologna, beef",
                "recipe_grams": 2495.0,
                "retail_purchase_grams": 2495.0,
            },
            calculator={
                "canonical_name": "beef bologna",
                "shopping_canonical": "beef bologna",
                "nutrition_state": "exact_usda_anchor",
                "nutrition_source": "sr28_direct",
                "nutrition_anchor": {"source": "SR28", "code": "172012", "description": "Bologna, beef"},
                "sr28_fdc_id": "172012",
                "shopping_state": "shopping_candidates_strong",
                "path": [],
            },
            store_checks=[
                {
                    "store": "walmart",
                    "status": "selected",
                    "selected": {
                        "name": "Wunderbar German Brand Beef Bologna, Deli Sliced",
                        "package_grams": 453.0,
                        "packages": 6,
                    },
                }
            ],
            plan={"plan_id": "p", "config_id": "cfg", "stores": ["walmart"], "week": 1},
        )

        blockers = classify_record_blockers(record)
        bologna = [blocker for blocker in blockers if blocker.issue_type == "wrong_form"][0]

        self.assertEqual(bologna.severity, "warning")
        self.assertEqual(bologna.decision, "needs_human")
        self.assertEqual(issue_bucket(bologna), "manual_substitution_or_scrub")
        self.assertFalse(is_hard_cart_blocker(bologna))

    def test_non_food_record_does_not_emit_nutrition_blocker(self) -> None:
        record = packet_record(
            ingredient={
                "original_recipe_text": "1 can (12 oz) wood chips for smoking",
                "parsed_item": "wood chips",
                "normalized_shopping_item": "wood chips",
                "recipe_grams": 340.0,
                "retail_purchase_grams": 340.0,
            },
            calculator={
                "canonical_name": "",
                "shopping_canonical": "",
                "nutrition_state": "non_food",
                "nutrition_source": "non_ingredient_surface",
                "nutrition_anchor": {"source": "", "code": "", "description": ""},
                "shopping_state": "non_food",
                "path": [],
            },
            store_checks=[],
            plan={"plan_id": "p", "config_id": "cfg", "stores": ["walmart"], "week": 1},
        )

        blockers = classify_record_blockers(record)

        self.assertEqual(blockers, [])

    def test_low_quantity_seasoning_nutrition_gap_moves_to_triage(self) -> None:
        record = packet_record(
            ingredient={
                "original_recipe_text": "2 tablespoons garlic salt",
                "parsed_item": "garlic salt",
                "normalized_shopping_item": "garlic salt",
                "recipe_grams": 18.0,
                "retail_purchase_grams": 18.0,
            },
            calculator={
                "canonical_name": "garlic salt",
                "shopping_canonical": "garlic salt",
                "nutrition_state": "nutrition_unknown",
                "nutrition_source": "nutrition_unknown",
                "nutrition_anchor": {"source": "", "code": "", "description": ""},
                "shopping_state": "shopping_candidates_strong",
                "path": [],
            },
            store_checks=[
                {
                    "store": "walmart",
                    "status": "selected",
                    "selected": {
                        "name": "Badia Garlic Salt, 4.5 oz",
                        "package_grams": 127.0,
                        "packages": 1,
                    },
                }
            ],
            plan={"plan_id": "p", "config_id": "cfg", "stores": ["walmart"], "week": 1},
        )

        blockers = classify_record_blockers(record)
        seasoning = [blocker for blocker in blockers if blocker.issue_type == "seasoning_nutrition_gap"][0]

        self.assertEqual(seasoning.severity, "warning")
        self.assertEqual(issue_bucket(seasoning), "low_risk_nutrition_gap")
        self.assertFalse(is_hard_cart_blocker(seasoning))

    def test_deepseek_candidate_selection_prioritizes_blocked_and_high_risk_records(self) -> None:
        blocked = packet_record(record_id="blocked")
        low_risk = packet_record(
            record_id="low",
            ingredient={
                "original_recipe_text": "1 cup flour",
                "parsed_item": "flour",
                "normalized_shopping_item": "flour",
                "recipe_grams": 125.0,
                "retail_purchase_grams": 125.0,
            },
            calculator={
                "canonical_name": "flour",
                "shopping_canonical": "flour",
                "nutrition_state": "reviewed_local_label_anchor",
                "nutrition_source": "esha",
                "nutrition_anchor": {"source": "ESHA", "code": "1", "description": "Flour"},
                "shopping_state": "shopping_candidates_strong",
            },
        )
        blockers = classify_record_blockers(blocked)

        candidates = select_deepseek_candidates([low_risk, blocked], blockers, limit=1)

        self.assertEqual([record["record_id"] for record in candidates], ["blocked"])


if __name__ == "__main__":
    unittest.main()
